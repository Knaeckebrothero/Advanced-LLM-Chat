"""
Smoke test for one model: does it work with this runtime, and how should it be configured?

    python -m backend.llm.smoke_test --env               # the environment model (OPENAI_* / ANTHROPIC_*)
    python -m backend.llm.smoke_test --model 12          # catalog model llm_models.id = 12
    python -m backend.llm.smoke_test --env --checks basic,tools --json

Checks (docs/model_provider_strategy.md, "Smoke tests per provider and model"):
- basic:     one completion without tools
- tools:     streaming with tools bound: is a tool call assembled correctly from the chunks?
- chain:     a three-step tool chain, with and without passing reasoning back
             (decides reasoning_passback; Claude always gets its thinking blocks back)
- reasoning: where the thinking text arrives (reasoning_content, reasoning, <think> tags, thinking blocks)
- effort:    which reasoning_effort values are accepted, and whether temperature is
- vision:    image input through image_url (only for models with supports_vision)

Every check makes real API calls with short prompts; the effort check makes one call per value.
"""
import argparse
import asyncio
import json
import logging
import struct
import sys
import time
import zlib
from dataclasses import dataclass, field, replace
from typing import Any, Optional

from .agent_loop import complete, run_agent
from .client import create_client
from .common import ThinkTagParser
from .tools import Tool, ToolRegistry
from .types import KIND_ANTHROPIC, ModelConfig, Usage, model_from_env

ALL_CHECKS = ("basic", "tools", "chain", "reasoning", "effort", "vision")
OPENAI_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
CLAUDE_EFFORTS = ("low", "medium", "high", "xhigh", "max")

# Values the tools hand out; the model can only report them by calling the tools
SECRET_CODE = "K7-ORCHID-42"
CHAIN_CODES = ("amber-17", "cobalt-58", "violet-93")


@dataclass
class CheckResult:
    name: str
    ok: Optional[bool]          # None = informational / skipped
    summary: str
    seconds: float = 0.0
    details: dict = field(default_factory=dict)


def _short_error(error: Exception) -> str:
    """A one-line error, e.g. '400: Unsupported value: ...'."""
    status = getattr(error, "status_code", None)
    message = getattr(error, "message", None) or str(error)
    message = " ".join(str(message).split())
    if len(message) > 160:
        message = message[:157] + "..."
    return f"{status}: {message}" if status else f"{type(error).__name__}: {message}"


async def _run(config: ModelConfig, client: Any, prompt: str, tools: Optional[ToolRegistry] = None,
               max_steps: int = 6) -> dict:
    """Run the agent loop and summarize what happened."""
    started = time.monotonic()
    text, steps, usage = [], [], Usage()
    async for kind, data in run_agent(config, [{"role": "user", "content": prompt}],
                                      system_prompt="You are being tested. Follow the instructions exactly.",
                                      tools=tools, max_steps=max_steps, client=client):
        if kind == "token":
            text.append(data)
        elif kind == "step":
            steps.append(data)
        elif kind == "usage":
            usage = data
    final_steps = {}
    for step in steps:
        final_steps[step.id] = step  # replacements keep the last version
    steps = list(final_steps.values())
    return {
        "text": "".join(text),
        "tool_calls": [s for s in steps if s.type == "tool_call"],
        "thinking": [s for s in steps if s.type == "thought"],
        "usage": usage,
        "seconds": time.monotonic() - started,
    }


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

async def check_basic(config: ModelConfig, client: Any) -> CheckResult:
    started = time.monotonic()
    text, usage = await complete(config, [{"role": "user", "content": "Reply with the single word: pong"}],
                                 client=client)
    ok = "pong" in text.lower()
    return CheckResult("basic completion", ok, f'reply "{text[:60]}"', time.monotonic() - started,
                       {"reply": text, "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens})


async def check_tools(config: ModelConfig, client: Any) -> CheckResult:
    calls = []

    async def get_secret(name: str) -> dict:
        calls.append(name)
        return {"name": name, "code": SECRET_CODE}

    tools = ToolRegistry([Tool(
        name="get_secret", description="Get the secret code stored under a name.",
        parameters={"type": "object", "properties": {"name": {"type": "string", "description": "The name"}},
                    "required": ["name"]},
        func=get_secret,
    )])
    run = await _run(config, client, "Call the get_secret tool with name 'alpha', then tell me the code it returns.", tools)
    arguments = [json.loads(step.content) if step.content.startswith("{") else step.content for step in run["tool_calls"]]
    assembled = bool(arguments) and arguments[0] == {"name": "alpha"}
    answered = SECRET_CODE in run["text"]
    ok = assembled and answered
    summary = (f"arguments {json.dumps(arguments[0]) if arguments else 'none'}; "
               f"{'code in answer' if answered else 'code missing from answer'}")
    return CheckResult("streamed tool call", ok, summary, run["seconds"],
                       {"arguments": arguments, "answer": run["text"][:200]})


async def _chain(config: ModelConfig, client: Any) -> dict:
    order = []

    def make(step: int):
        async def tool(token: str) -> str:
            order.append((step, token))
            expected = "start" if step == 0 else CHAIN_CODES[step - 1]
            if token != expected:
                return f"Error: wrong input '{token}', expected the result of the previous step"
            return CHAIN_CODES[step]
        return tool

    names = ("step_one", "step_two", "step_three")
    tools = ToolRegistry([
        Tool(name=name, description=f"Step {i + 1} of a chain: takes a token and returns the next token.",
             parameters={"type": "object", "properties": {"token": {"type": "string"}}, "required": ["token"]},
             func=make(i))
        for i, name in enumerate(names)
    ])
    prompt = ("Call step_one with token 'start'. Then call step_two with the token step_one returned. "
              "Then call step_three with the token step_two returned. Call the tools one at a time. "
              "Finally reply with the token step_three returned.")
    run = await _run(config, client, prompt, tools, max_steps=6)
    ok = [step for step, _ in order] == [0, 1, 2] and CHAIN_CODES[2] in run["text"]
    return {"ok": ok, "order": order, "run": run}


async def check_chain(config: ModelConfig, client: Any) -> list[CheckResult]:
    variants = [("thinking blocks passed back", config)] if config.kind == KIND_ANTHROPIC else [
        ("passback on", replace(config, reasoning_passback=True)),
        ("passback off", replace(config, reasoning_passback=False)),
    ]
    results = []
    for label, variant in variants:
        started = time.monotonic()
        try:
            chain = await _chain(variant, client)
            run = chain["run"]
            summary = (f"{len(run['tool_calls'])} tool calls {[token for _, token in chain['order']]}, "
                       f"{'final token in answer' if CHAIN_CODES[2] in run['text'] else 'final token missing'}, "
                       f"{len(run['thinking'])} thinking step(s)")
            results.append(CheckResult(f"3-step chain ({label})", chain["ok"], summary, run["seconds"],
                                       {"order": chain["order"], "answer": run["text"][:200]}))
        except Exception as e:
            results.append(CheckResult(f"3-step chain ({label})", False, _short_error(e), time.monotonic() - started))
    return results


async def check_reasoning(config: ModelConfig, client: Any) -> CheckResult:
    """Where the thinking text arrives, from the raw stream."""
    prompt = "What is 17 * 23? Work it out step by step, then give the number."
    started = time.monotonic()
    if config.kind == KIND_ANTHROPIC:
        run = await _run(config, client, prompt)
        chars = sum(len(step.content) for step in run["thinking"])
        where = f"thinking blocks ({chars} chars)" if chars else "no thinking text (display omitted or no thinking)"
        return CheckResult("reasoning location", None, where, run["seconds"], {"thinking_chars": chars})

    from .openai_chat import REASONING_FIELDS, apply_extra_body, request_options
    kwargs = {"model": config.model_id, "messages": [{"role": "user", "content": prompt}], "stream": True,
              **request_options(config)}
    apply_extra_body(config, kwargs)
    found = {name: 0 for name in REASONING_FIELDS}
    extra_keys: set[str] = set()
    think_chars = 0
    parser = ThinkTagParser()
    stream = await client.chat.completions.create(**kwargs)
    async for chunk in stream:
        if not chunk.choices or chunk.choices[0].delta is None:
            continue
        delta = chunk.choices[0].delta
        extra = getattr(delta, "model_extra", None) or {}
        extra_keys.update(key for key, value in extra.items() if value not in (None, "", []))
        for name in REASONING_FIELDS:
            value = getattr(delta, name, None) or extra.get(name)
            if isinstance(value, str):
                found[name] += len(value)
        if delta.content:
            think_chars += sum(len(part) for kind, part in parser.feed(delta.content) if kind == "reasoning")
    places = [f"{name} ({chars} chars)" for name, chars in found.items() if chars]
    if think_chars:
        places.append(f"<think> tags ({think_chars} chars)")
    summary = ", ".join(places) or "no reasoning text in the stream"
    if extra_keys:
        summary += f"; other delta fields: {', '.join(sorted(extra_keys))}"
    return CheckResult("reasoning location", None, summary, time.monotonic() - started,
                       {"fields": found, "think_tag_chars": think_chars, "extra_delta_fields": sorted(extra_keys)})


async def check_effort(config: ModelConfig, client: Any) -> list[CheckResult]:
    values = CLAUDE_EFFORTS if config.kind == KIND_ANTHROPIC else OPENAI_EFFORTS
    accepted, rejected = [], {}
    started = time.monotonic()
    for value in values:
        try:
            await complete(replace(config, reasoning_effort=value), [{"role": "user", "content": "Reply with OK."}],
                           client=client)
            accepted.append(value)
        except Exception as e:
            rejected[value] = _short_error(e)
    effort = CheckResult("reasoning_effort", bool(accepted) or None,
                         f"accepted: {', '.join(accepted) or 'none'}; rejected: {', '.join(rejected) or 'none'}",
                         time.monotonic() - started, {"accepted": accepted, "rejected": rejected})

    started = time.monotonic()
    if config.kind == KIND_ANTHROPIC:
        temperature = CheckResult("temperature=0.5", None, "not sent: Claude rejects sampling parameters")
    else:
        try:
            await complete(replace(config, temperature=0.5), [{"role": "user", "content": "Reply with OK."}],
                           client=client)
            temperature = CheckResult("temperature=0.5", True, "accepted", time.monotonic() - started)
        except Exception as e:
            temperature = CheckResult("temperature=0.5", False, f"rejected: {_short_error(e)}",
                                      time.monotonic() - started)
    return [effort, temperature]


def _png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """A solid-color PNG, without an imaging library."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    row = b"\x00" + bytes(rgb) * width
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(row * height)) + chunk(b"IEND", b""))


async def check_vision(config: ModelConfig, client: Any) -> CheckResult:
    import base64
    if not config.supports_vision:
        return CheckResult("image input", None, "skipped: the model is not marked supports_vision")
    image = base64.b64encode(_png(64, 64, (220, 20, 20))).decode()
    started = time.monotonic()
    text, _ = await complete(config, [{"role": "user", "content": [
        {"type": "text", "text": "What color is this square? Answer with one word."},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image}"}},
    ]}], client=client)
    return CheckResult("image input", "red" in text.lower(), f'reply "{text[:60]}"', time.monotonic() - started,
                       {"reply": text})


CHECKS = {
    "basic": check_basic,
    "tools": check_tools,
    "chain": check_chain,
    "reasoning": check_reasoning,
    "effort": check_effort,
    "vision": check_vision,
}


async def run_checks(config: ModelConfig, checks: list[str]) -> list[CheckResult]:
    """Run the selected checks; a failing check doesn't stop the others."""
    client = create_client(config)
    results: list[CheckResult] = []
    for name in checks:
        started = time.monotonic()
        try:
            if name in ("tools", "chain") and not config.supports_tools:
                results.append(CheckResult(name, None, "skipped: the model is not marked supports_tools"))
                continue
            outcome = await CHECKS[name](config, client)
            results.extend(outcome if isinstance(outcome, list) else [outcome])
        except Exception as e:
            results.append(CheckResult(name, False, _short_error(e), time.monotonic() - started))
    return results


def print_report(config: ModelConfig, results: list[CheckResult]) -> None:
    print(f"\nSmoke test: {config.display_name} ({config.model_id})")
    print(f"  provider {config.provider_name}, kind {config.kind}, base URL {config.base_url or 'SDK default'}")
    print(f"  configured: tools={config.supports_tools}, vision={config.supports_vision}, reasoning={config.reasoning}, "
          f"passback={config.reasoning_passback}, effort={config.reasoning_effort}, temperature={config.temperature}\n")
    width = max(len(result.name) for result in results) + 2
    for result in results:
        status = {True: "OK  ", False: "FAIL", None: "info"}[result.ok]
        seconds = f"{result.seconds:5.1f}s" if result.seconds else "      "
        print(f"  {result.name.ljust(width, '.')} {status} {seconds}  {result.summary}")
    failed = [result.name for result in results if result.ok is False]
    print(f"\n{'All checks passed' if not failed else 'Failed: ' + ', '.join(failed)}\n")


def _load_config(args) -> ModelConfig:
    if args.env:
        config = model_from_env()
        if config is None:
            raise SystemExit("No environment model: set OPENAI_API_KEY or ANTHROPIC_API_KEY")
        return config
    try:
        from backend.catalog.resolver import get_model_config
    except ImportError as e:
        raise SystemExit(f"The model catalog is not available ({e}); use --env")
    return get_model_config(args.model)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test one model against the LLM runtime")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--env", action="store_true", help="test the environment model (OPENAI_* / ANTHROPIC_*)")
    source.add_argument("--model", type=int, help="test a catalog model by its llm_models id")
    parser.add_argument("--checks", default=",".join(ALL_CHECKS),
                        help=f"comma-separated subset of: {', '.join(ALL_CHECKS)} (default: all)")
    parser.add_argument("--json", action="store_true", help="print the results as JSON instead of a report")
    parser.add_argument("--verbose", action="store_true", help="show the runtime's log output")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    if not args.verbose:
        logging.getLogger("backend").setLevel(logging.ERROR)

    checks = [name.strip() for name in args.checks.split(",") if name.strip()]
    unknown = [name for name in checks if name not in CHECKS]
    if unknown:
        parser.error(f"unknown checks: {', '.join(unknown)}")

    config = _load_config(args)
    results = asyncio.run(run_checks(config, checks))
    if args.json:
        print(json.dumps([{"name": r.name, "ok": r.ok, "summary": r.summary, "seconds": round(r.seconds, 2),
                           "details": r.details} for r in results], indent=2, default=str))
    else:
        print_report(config, results)
    return 1 if any(result.ok is False for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())
