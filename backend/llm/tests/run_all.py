"""
Run every offline test script of the LLM runtime (no API keys or database needed).

    python -m backend.llm.tests.run_all
"""
import asyncio
import importlib
import logging
import sys

MODULES = ("test_openai_loop", "test_anthropic_loop", "test_history")


def main() -> int:
    logging.getLogger("backend").setLevel(logging.CRITICAL)
    failed = []
    for name in MODULES:
        print(f"== {name}")
        module = importlib.import_module(f"backend.llm.tests.{name}")
        if asyncio.run(module.main()):
            failed.append(name)
        print()
    print("All test scripts passed" if not failed else f"Failed: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
