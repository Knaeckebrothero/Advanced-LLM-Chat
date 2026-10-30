"""
A tiny OpenAI-compatible Chat Completions server for offline tests.

Each request is answered by the next scripted responder: a function that gets
the request body and returns either a list of stream chunks (sent as SSE) or a
dict (a non-streaming response). Request bodies are recorded so tests can
check what the runtime sent, e.g. that reasoning_content was passed back.

    server = FakeOpenAIServer()
    server.script(lambda body: [chunk(content="Hi"), chunk(finish_reason="stop"), usage_chunk(5, 2)])
    with server:
        ...  # AsyncOpenAI(base_url=server.base_url, api_key="test")
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Optional, Union

Responder = Callable[[dict], Union[list, dict]]


def chunk(content: Optional[str] = None, *, reasoning_content: Optional[str] = None,
          reasoning: Optional[str] = None, tool_calls: Optional[list] = None,
          finish_reason: Optional[str] = None, model: str = "fake-model") -> dict:
    """One chat.completion.chunk with a single choice."""
    delta: dict[str, Any] = {}
    if content is not None:
        delta["content"] = content
    if reasoning_content is not None:
        delta["reasoning_content"] = reasoning_content
    if reasoning is not None:
        delta["reasoning"] = reasoning
    if tool_calls is not None:
        delta["tool_calls"] = tool_calls
    return {
        "id": "chatcmpl-fake",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


def tool_call_delta(index: int, *, id: Optional[str] = None, name: Optional[str] = None,
                    arguments: Optional[str] = None) -> dict:
    """A streamed tool-call fragment."""
    function: dict[str, Any] = {}
    if name is not None:
        function["name"] = name
    if arguments is not None:
        function["arguments"] = arguments
    delta: dict[str, Any] = {"index": index, "function": function}
    if id is not None:
        delta["id"] = id
        delta["type"] = "function"
    return delta


def usage_chunk(prompt_tokens: int, completion_tokens: int, reasoning_tokens: Optional[int] = None,
                cached_tokens: Optional[int] = None) -> dict:
    """The final usage-only chunk sent with stream_options.include_usage."""
    usage: dict[str, Any] = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }
    if reasoning_tokens is not None:
        usage["completion_tokens_details"] = {"reasoning_tokens": reasoning_tokens}
    if cached_tokens is not None:
        usage["prompt_tokens_details"] = {"cached_tokens": cached_tokens}
    return {"id": "chatcmpl-fake", "object": "chat.completion.chunk", "created": int(time.time()),
            "model": "fake-model", "choices": [], "usage": usage}


def completion(content: str, prompt_tokens: int = 10, completion_tokens: int = 5) -> dict:
    """A non-streaming chat.completion."""
    return {
        "id": "chatcmpl-fake",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "fake-model",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                  "total_tokens": prompt_tokens + completion_tokens},
    }


class FakeOpenAIServer:
    """Serves scripted responses on 127.0.0.1 and records the requests."""

    def __init__(self):
        self.requests: list[dict] = []
        self.errors: list[str] = []
        self._responders: list[Responder] = []
        self._lock = threading.Lock()
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                with server._lock:
                    server.requests.append(body)
                    responder = server._responders.pop(0) if server._responders else None
                if responder is None:
                    server.errors.append(f"Unexpected request #{len(server.requests)}")
                    return self._send_json(500, {"error": {"message": "no scripted response left"}})
                try:
                    result = responder(body)
                except AssertionError as e:
                    server.errors.append(f"Request #{len(server.requests)}: {e}")
                    return self._send_json(400, {"error": {"message": f"fake server assertion: {e}"}})
                if isinstance(result, dict):
                    return self._send_json(200, result)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for item in result:
                    self.wfile.write(f"data: {json.dumps(item)}\n\n".encode())
                    self.wfile.flush()
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()

            def _send_json(self, code: int, payload: dict):
                data = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread: Optional[threading.Thread] = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._httpd.server_address[1]}/v1"

    def script(self, *responders: Responder) -> None:
        """Queue responders for the next requests, in order."""
        self._responders.extend(responders)

    def reset(self) -> None:
        self.requests.clear()
        self.errors.clear()
        self._responders.clear()

    def __enter__(self) -> "FakeOpenAIServer":
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
