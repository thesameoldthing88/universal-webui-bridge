import argparse
import asyncio
import logging

from webui_bridge import UniversalWebUIBridge, setup_logging


async def interactive_chat(url: str, headless: bool = False) -> None:
    bridge = UniversalWebUIBridge(headless=headless)
    await bridge.connect(url)
    print(f"Connected to {url}")
    print("Type your message and press Enter. Type 'quit' to exit.\n")

    try:
        while True:
            user_input = input("You: ").strip()
            if user_input.lower() in {"quit", "exit", "q"}:
                break
            if not user_input:
                continue

            await bridge.send(user_input)
            print("Assistant: ", end="", flush=True)

            async for token in bridge.stream_response(timeout=120.0):
                print(token, end="", flush=True)
            print()
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        await bridge.close()
        print("Disconnected.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Universal WebUI LLM Bridge Demo")
    parser.add_argument("--url", required=True, help="URL of the LLM WebUI")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    setup_logging(level=logging.DEBUG if args.debug else logging.INFO)
    asyncio.run(interactive_chat(args.url, headless=args.headless))


if __name__ == "__main__":
    main()
