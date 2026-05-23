#!/usr/bin/env python3
"""
Demo for Universal WebUI Bridge with Direct API Mode.

This example shows how to:
1. Connect to a WebUI
2. Attempt to detect the backend API endpoint
3. Use direct API mode for faster, more reliable messaging
4. Automatically fall back to UI automation if API fails

Usage:
    python demo_api_mode.py --url http://localhost:3000

Requirements:
    - WebUI running at the specified URL
    - Playwright browsers installed: playwright install
"""

import argparse
import asyncio
import logging

from webui_bridge import UniversalWebUIBridge, setup_logging


async def interactive_session(url: str, headless: bool = False) -> None:
    """Run an interactive chat session with automatic API detection."""
    bridge = UniversalWebUIBridge(headless=headless)
    
    print(f"🚀 Connecting to {url}...")
    try:
        await bridge.connect(url)
        print("✅ Connected successfully!")
        
        # Try to detect and enable direct API mode
        print("🔍 Analyzing network traffic to detect backend API...")
        api_enabled = await bridge.try_enable_direct_api(observation_time=5.0)
        
        if api_enabled:
            endpoint = await bridge.get_detected_api_endpoint()
            print(f"⚡ API mode enabled! Using direct endpoint:")
            print(f"   {endpoint}")
            print("   (Faster and more reliable than UI automation)")
        else:
            print("ℹ️  API detection failed. Using UI automation mode.")
            print("   (Sending messages via browser DOM interactions)")
        
        print("\n" + "=" * 60)
        print("Chat Interface Ready!")
        print("Commands:")
        print("  /api       - Check API mode status")
        print("  /detect    - Retry API endpoint detection")
        print("  /ui        - Switch to UI automation mode")
        print("  /quit      - Exit")
        print("=" * 60 + "\n")
        
        while True:
            user_input = input("You: ").strip()
            
            # Handle commands
            if user_input.lower() == "/quit":
                break
            elif user_input.lower() == "/api":
                if bridge.is_api_mode:
                    endpoint = await bridge.get_detected_api_endpoint()
                    print(f"   API mode: ACTIVE")
                    print(f"   Endpoint: {endpoint}")
                else:
                    print("   API mode: INACTIVE (using UI automation)")
                continue
            elif user_input.lower() == "/detect":
                print("   Retrying API detection...")
                success = await bridge.try_enable_direct_api(observation_time=5.0)
                print(f"   {'✅ API enabled!' if success else '❌ Detection failed'}")
                continue
            elif user_input.lower() == "/ui":
                await bridge.disable_direct_api()
                print("   Switched to UI automation mode")
                continue
            elif not user_input:
                continue
            
            # Send message
            try:
                await bridge.send(user_input)
                
                if bridge.is_api_mode:
                    # In API mode, we get response immediately
                    print("Assistant: (via API)")
                else:
                    # In UI mode, wait for streaming response
                    print("Assistant: ", end="", flush=True)
                    async for token in bridge.stream_response(timeout=120.0):
                        print(token, end="", flush=True)
                    print()
                    
            except Exception as exc:
                print(f"❌ Error: {exc}")
    
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as exc:
        print(f"\n❌ Connection error: {exc}")
    finally:
        await bridge.close()
        print("\n👋 Disconnected")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Universal WebUI Bridge - API Mode Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --url http://localhost:3000
  %(prog)s --url http://localhost:8080 --headless --debug
        """
    )
    parser.add_argument(
        "--url",
        required=True,
        help="URL of the LLM WebUI (e.g., http://localhost:3000)"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode (no visible window)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(level=logging.DEBUG if args.debug else logging.INFO)
    
    # Run the demo
    try:
        asyncio.run(interactive_session(args.url, headless=args.headless))
    except Exception as exc:
        print(f"Fatal error: {exc}")
        raise


if __name__ == "__main__":
    main()
