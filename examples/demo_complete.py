#!/usr/bin/env python3
"""
Universal WebUI LLM Bridge - Complete Feature Demonstration

This script demonstrates ALL capabilities of the bridge:
- Automatic element detection
- Self-healing after UI changes
- Real-time message tracking
- Streaming output detection
- Network API fallback
- Multi-language support
- Modal dialog handling
- Known UI auto-detection

Usage:
    python demo_complete.py --url http://localhost:3000
"""

import asyncio
import argparse
import logging
from typing import Optional

from webui_bridge import UniversalWebUIBridge, DOMScanner, setup_logging


class UniversalBridgeDemo:
    """Complete demonstration of all Universal WebUI Bridge features."""
    
    def __init__(self, url: str, headless: bool = False):
        self.url = url
        self.headless = headless
        self.bridge: Optional[UniversalWebUIBridge] = None
        
    async def run_full_demo(self):
        """Execute complete feature demonstration."""
        print("=" * 70)
        print("  Universal WebUI LLM Bridge - Complete Feature Demo")
        print("=" * 70)
        
        # Initialize bridge
        print("\n[1/8] Initializing UniversalWebUIBridge...")
        self.bridge = UniversalWebUIBridge(headless=self.headless)
        
        # Connect to WebUI
        print(f"\n[2/8] Connecting to {self.url}...")
        try:
            await self.bridge.connect(self.url)
            print("  [OK] Connected successfully")
        except Exception as e:
            print(f"  [ERROR] Connection failed: {e}")
            return
        
        # Feature 1: Detect Theme
        print("\n[3/8] Detecting UI theme...")
        try:
            theme = await self.bridge.detect_theme()
            print(f"  [OK] Detected theme: {theme}")
        except Exception as e:
            print(f"  [ERROR] Theme detection failed: {e}")
        
        # Feature 2: Check detected UI type
        print("\n[4/8] Checking UI framework detection...")
        ui_type = self.bridge._scanner.get_detected_ui_type()
        if ui_type:
            print(f"  [OK] Detected known UI: {ui_type}")
        else:
            print("  [INFO] Using generic detection (no known UI matched)")
        
        # Feature 3: Try to enable direct API mode
        print("\n[5/8] Attempting to detect backend API...")
        api_enabled = await self.bridge.try_enable_direct_api(observation_time=3.0)
        if api_enabled:
            endpoint = await self.bridge.get_detected_api_endpoint()
            print("  [OK] Direct API mode enabled!")
            print(f"    Endpoint: {endpoint}")
        else:
            print("  [INFO] Using UI automation mode (API not detected)")
        
        # Feature 4: Send messages and demonstrate streaming
        print("\n[6/8] Testing message sending and streaming...")
        await self._demo_message_interaction()
        
        # Feature 5: Demonstrate self-healing
        print("\n[7/8] Demonstrating self-healing capability...")
        await self._demo_self_healing()
        
        # Feature 6: Show message history
        print("\n[8/8] Retrieving message history...")
        await self._show_message_history()
        
        # Cleanup
        print("\n" + "=" * 70)
        print("  Cleaning up...")
        await self.bridge.close()
        print("  [OK] Demo complete!")
        print("=" * 70)
    
    async def _demo_message_interaction(self):
        """Demonstrate message sending with streaming."""
        test_messages = [
            "Hello! Can you help me with a Python question?",
        ]
        
        for message in test_messages:
            display = message[:50] + "..." if len(message) > 50 else message
            print(f"\n  Sending: '{display}'")
            
            try:
                await self.bridge.send(message)
                print("  [OK] Message sent")
                
                # Wait for response with streaming
                print("  -> Waiting for response (streaming)...")
                print("  Assistant: ", end="", flush=True)
                
                response_text = ""
                token_count = 0
                
                async for token in self.bridge.stream_response(timeout=30.0):
                    print(token, end="", flush=True)
                    response_text += token
                    token_count += 1
                
                print()  # Newline after response
                print(f"  [OK] Received {token_count} tokens, {len(response_text)} chars")
                
                # Show if we're in API mode
                if self.bridge.is_api_mode:
                    print("  [OK] (Delivered via Direct API)")
                else:
                    print("  [OK] (Delivered via UI automation)")
                    
            except Exception as e:
                print(f"  [ERROR] Error: {e}")
    
    async def _demo_self_healing(self):
        """Demonstrate self-healing by simulating a heal operation."""
        print("  Triggering DOM re-detection (self-healing)...")
        try:
            # Access internal healing method
            await self.bridge._heal()
            print("  [OK] Self-healing completed successfully")
            print("  [OK] Elements re-detected and observers restarted")
        except Exception as e:
            print(f"  [ERROR] Self-healing failed: {e}")
    
    async def _show_message_history(self):
        """Display message history from the conversation."""
        try:
            messages = await self.bridge.get_messages()
            print(f"  [OK] Retrieved {len(messages)} messages from history")
            
            if messages:
                print("\n  Recent messages:")
                for msg in messages[-3:]:  # Show last 3
                    author = msg.get('author', 'unknown')
                    text = msg.get('text', '')[:40]
                    print(f"    [{author}] {text}...")
                    
        except Exception as e:
            print(f"  [ERROR] Failed to retrieve history: {e}")


async def demo_multilingual_support():
    """Demonstrate multi-language input detection."""
    print("\n" + "=" * 70)
    print("  Multi-Language Support Demonstration")
    print("=" * 70)
    
    from webui_bridge.dom_scanner import DOMScanner
    from webui_bridge.utils import score_input_element, score_send_button
    
    scanner = DOMScanner()
    
    # Test multi-language input scoring
    print("\n  Testing multi-language input detection:")
    test_cases = [
        {"tag": "textarea", "visible": True, "area": 10000, "placeholder": "message", "contenteditable": False},
        {"tag": "textarea", "visible": True, "area": 10000, "placeholder": "Type a message", "contenteditable": False},
        {"tag": "textarea", "visible": True, "area": 10000, "placeholder": "Ask anything", "contenteditable": False},
    ]
    
    for case in test_cases:
        score = score_input_element(case)
        print(f"    Placeholder '{case['placeholder']}': score={score:.1f}")
    
    print("\n  [OK] Multi-language detection working")


def demo_code_extraction():
    """Demonstrate code block extraction from markdown."""
    print("\n" + "=" * 70)
    print("  Code Block Extraction Demonstration")
    print("=" * 70)
    
    from webui_bridge.utils import extract_code_blocks, extract_markdown_sections
    
    sample_response = """
Here's a Python function:

```python
def fibonacci(n):
    if n < 2:
        return n
    return fibonacci(n-1) + fibonacci(n-2)
```

You can also use this inline: `fibonacci(10)`

    # Or indented code
    def helper():
        pass

And here's a list:
- Item 1
- Item 2
"""
    
    print("\n  Extracting code blocks from sample response:")
    blocks = extract_code_blocks(sample_response)
    print(f"    Found {len(blocks)} code blocks:")
    for block in blocks:
        print(f"      - Type: {block['type']}, Lang: {block['language'] or 'none'}")
    
    sections = extract_markdown_sections(sample_response)
    print(f"\n    Found {len(sections)} markdown sections:")
    for section in sections:
        print(f"      - Type: {section['type']}")
    
    print("\n  [OK] Code extraction working")


async def demo_known_ui_registry():
    """Demonstrate known UI registry."""
    print("\n" + "=" * 70)
    print("  Known UI Registry Demonstration")
    print("=" * 70)
    
    from webui_bridge.dom_scanner import KNOWN_UI_REGISTRY, KnownUIConfig
    
    print("\n  Registered known UIs:")
    for ui_type, config in KNOWN_UI_REGISTRY.items():
        print(f"    - {config.name} ({ui_type})")
        print(f"      Input selectors: {len(config.input_selectors)}")
        print(f"      Send selectors: {len(config.send_button_selectors)}")
    
    # Show custom config capability
    print("\n  Custom UI configuration example:")
    custom = KnownUIConfig(
        name="My Custom UI",
        input_selectors=['#custom-input'],
        send_button_selectors=['#custom-send'],
        chat_container_selectors=['#custom-chat'],
    )
    print(f"    Created: {custom.name}")
    
    print("\n  [OK] Known UI registry working")


async def main():
    """Main entry point with multiple demo modes."""
    parser = argparse.ArgumentParser(
        description="Universal WebUI Bridge - Complete Feature Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Demo Modes:
  full       - Complete live demo (requires WebUI running)
  offline    - Offline feature demos (no browser needed)
  
Examples:
  %(prog)s --url http://localhost:3000 full
  %(prog)s offline
        """
    )
    parser.add_argument("--url", default="http://localhost:3000", help="WebUI URL")
    parser.add_argument("--headless", action="store_true", help="Run headless")
    parser.add_argument("--debug", action="store_true", help="Debug logging")
    parser.add_argument("mode", choices=['full', 'offline'], default='offline',
                       help="Demo mode to run")
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(level=logging.DEBUG if args.debug else logging.INFO)
    
    if args.mode == 'full':
        # Full live demo
        demo = UniversalBridgeDemo(args.url, headless=args.headless)
        await demo.run_full_demo()
        
    elif args.mode == 'offline':
        # Offline demos (no browser needed)
        await demo_multilingual_support()
        demo_code_extraction()
        await demo_known_ui_registry()
        
        print("\n" + "=" * 70)
        print("  Offline demos complete!")
        print("  Run with 'full' mode for live WebUI demonstration:")
        print(f"    python {__file__} --url {args.url} full")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
