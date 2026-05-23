import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from webui_bridge.bridge import UniversalWebUIBridge
from webui_bridge.dom_scanner import DOMScanner
from webui_bridge.message_stream import MessageStream
from webui_bridge.theme_detector import Theme, ThemeDetector
from webui_bridge.utils import (
    classify_message_author,
    extract_code_blocks,
    extract_markdown_sections,
    score_chat_container,
    score_input_element,
    score_send_button,
    strip_markdown,
)


# ------------------------------------------------------------------
# Utils tests
# ------------------------------------------------------------------

def test_score_input_element_textarea():
    info = {
        "tag": "textarea",
        "type": "",
        "role": "textbox",
        "placeholder": "Type a message...",
        "contenteditable": False,
        "visible": True,
        "area": 10000,
    }
    assert score_input_element(info) > 5.0


def test_score_input_element_hidden():
    info = {"tag": "textarea", "visible": False, "area": 0}
    assert score_input_element(info) == 0.0


def test_score_send_button():
    info = {
        "tag": "button",
        "role": "button",
        "text": "Send",
        "ariaLabel": "send message",
        "visible": True,
        "hasSvgChild": True,
        "hasClickListener": True,
        "rect": {"x": 100, "y": 200, "width": 40, "height": 40},
    }
    input_rect = {"x": 10, "y": 200, "width": 80, "height": 40}
    assert score_send_button(info, input_rect) > 5.0


def test_score_chat_container():
    info = {
        "tag": "div",
        "visible": True,
        "childCount": 20,
        "hasScrollbar": True,
        "textDensity": 0.5,
        "mutationCount": 10,
    }
    assert score_chat_container(info) > 3.0


def test_classify_message_author():
    assert classify_message_author("You: hello", None) == "user"
    assert classify_message_author("Assistant: hi", None) == "assistant"
    assert classify_message_author("hi", "user") == "assistant"
    assert classify_message_author("hi", "assistant") == "user"


def test_extract_code_blocks_fenced():
    text = "```python\nprint(1)\n```"
    blocks = extract_code_blocks(text)
    assert len(blocks) == 1
    assert blocks[0]["language"] == "python"
    assert "print(1)" in blocks[0]["code"]
    assert blocks[0]["type"] == "fenced"
    assert blocks[0]["start_index"] == 0
    assert blocks[0]["end_index"] == len(text)


def test_extract_code_blocks_inline():
    text = "Use `pip install` to get started."
    blocks = extract_code_blocks(text)
    assert len(blocks) == 1
    assert blocks[0]["code"] == "pip install"
    assert blocks[0]["type"] == "inline"
    assert blocks[0]["language"] == ""


def test_extract_code_blocks_indented():
    text = "    def hello():\n        print('world')\n"
    blocks = extract_code_blocks(text)
    assert len(blocks) == 1
    assert blocks[0]["type"] == "indented"
    assert "def hello():" in blocks[0]["code"]


def test_extract_code_blocks_combined():
    text = (
        "```js\nconsole.log(1);\n```\n"
        "    indented line\n"
        "Run `npm start` now."
    )
    blocks = extract_code_blocks(text)
    assert len(blocks) == 3
    assert blocks[0]["type"] == "fenced"
    assert blocks[1]["type"] == "indented"
    assert blocks[2]["type"] == "inline"


def test_extract_markdown_sections_headers():
    text = "# Title\n## Sub\nBody"
    sections = extract_markdown_sections(text)
    assert sections[0]["type"] == "header"
    assert sections[0]["level"] == 1
    assert sections[1]["type"] == "header"
    assert sections[1]["level"] == 2
    assert sections[2]["type"] == "paragraph"


def test_extract_markdown_sections_list():
    text = "- first\n- second\n\npara"
    sections = extract_markdown_sections(text)
    assert sections[0]["type"] == "list"
    assert sections[1]["type"] == "paragraph"


def test_extract_markdown_sections_code():
    text = "```py\nx = 1\n```\n\n    indented\n"
    sections = extract_markdown_sections(text)
    code_sections = [s for s in sections if s["type"] == "code"]
    assert len(code_sections) == 2


def test_strip_markdown():
    md = "# Header\n**bold** and *italic*\n`code`\n[link](http://a.b)\n- item"
    plain = strip_markdown(md)
    assert "#" not in plain
    assert "**" not in plain
    assert "`" not in plain
    assert "[link]" not in plain
    assert "(http://a.b)" not in plain
    assert plain.startswith("Header")
    assert "bold" in plain
    assert "italic" in plain
    assert "code" in plain
    assert "link" in plain
    assert "item" in plain


# ------------------------------------------------------------------
# DOMScanner Enhanced functionality tests
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dom_scanner_modal_detection():
    """Test modal dialog detection."""
    from webui_bridge.dom_scanner import DOMScanner
    
    page = MagicMock()
    # Mock modal dialog present
    page.evaluate = AsyncMock(return_value={
        "selector": '[role="dialog"]',
        "element": "div",
        "hasInput": True
    })
    
    scanner = DOMScanner(use_known_uis=False)
    modal_info = await scanner._detect_modal_context(page)
    
    assert modal_info is not None
    assert modal_info["selector"] == '[role="dialog"]'


@pytest.mark.asyncio
async def test_dom_scanner_known_ui_registry():
    """Test the known UI registry."""
    from webui_bridge.dom_scanner import KNOWN_UI_REGISTRY, KnownUIConfig
    
    # Verify registry contains expected UIs
    assert "openwebui" in KNOWN_UI_REGISTRY
    assert "oobabooga" in KNOWN_UI_REGISTRY
    
    # Verify structure
    config = KNOWN_UI_REGISTRY["openwebui"]
    assert len(config.input_selectors) > 0
    assert len(config.send_button_selectors) > 0


def test_dom_scanner_custom_config():
    """Test custom UI configuration."""
    from webui_bridge.dom_scanner import DOMScanner, KnownUIConfig
    
    custom = KnownUIConfig(
        name="Custom UI",
        input_selectors=['#my-input'],
        send_button_selectors=['#my-send'],
        chat_container_selectors=['#my-chat'],
    )
    
    scanner = DOMScanner()
    scanner.set_custom_config(custom)
    
    assert scanner._custom_config == custom


@pytest.mark.asyncio
async def test_dom_scanner_use_known_uis_false():
    """Test that use_known_uis=False skips known UI detection."""
    from webui_bridge.dom_scanner import DOMScanner
    
    scanner = DOMScanner(use_known_uis=False)
    
    page = MagicMock()
    page.evaluate = AsyncMock(side_effect=[
        None, None, None, None,  # theme detection
        None,  # modal context
        [{"tag": "textarea", "selector": "textarea", "rect": {}}],  # input
        None,  # modal context
        [{"tag": "button", "selector": "button", "rect": {}}],  # send
        None,  # modal container
        [{"tag": "div", "selector": "div", "rect": {}}],  # chat
    ])
    
    # This should work without calling the full known UI registry
    result = await scanner.full_scan(page)
    assert isinstance(result, dict)


# ------------------------------------------------------------------
# MessageStream tests
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_message_stream_inject_mock():
    page = MagicMock()
    page.add_init_script = AsyncMock()
    stream = MessageStream()
    await stream.inject(page)
    page.add_init_script.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_last_message_with_blocks():
    page = MagicMock()
    page.evaluate = AsyncMock(
        return_value=[
            {"author": "user", "text": "hi"},
            {
                "author": "assistant",
                "text": "```python\nprint(1)\n```\n# heading\nparagraph",
            },
        ]
    )
    stream = MessageStream()
    msg = await stream.get_last_message_with_blocks(page)
    assert msg is not None
    assert msg["author"] == "assistant"
    assert len(msg["code_blocks"]) == 1
    assert msg["code_blocks"][0]["type"] == "fenced"
    assert len(msg["markdown_sections"]) == 3
    assert msg["markdown_sections"][0]["type"] == "code"
    assert msg["markdown_sections"][1]["type"] == "header"
    assert msg["markdown_sections"][2]["type"] == "paragraph"


# ------------------------------------------------------------------
# ThemeDetector tests
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_theme_detector_media_query_dark():
    page = MagicMock()
    page.evaluate = AsyncMock(return_value=True)
    detector = ThemeDetector()
    theme = await detector.detect(page)
    assert theme == Theme.DARK


@pytest.mark.asyncio
async def test_theme_detector_media_query_light():
    page = MagicMock()
    page.evaluate = AsyncMock(return_value=False)
    detector = ThemeDetector()
    theme = await detector.detect(page)
    assert theme == Theme.LIGHT


@pytest.mark.asyncio
async def test_theme_detector_class_names():
    page = MagicMock()
    page.evaluate = AsyncMock(side_effect=[None, "dark", None])
    detector = ThemeDetector()
    theme = await detector.detect(page)
    assert theme == Theme.DARK


@pytest.mark.asyncio
async def test_theme_detector_data_attribute():
    page = MagicMock()
    page.evaluate = AsyncMock(side_effect=[None, None, "light"])
    detector = ThemeDetector()
    theme = await detector.detect(page)
    assert theme == Theme.LIGHT


@pytest.mark.asyncio
async def test_theme_detector_brightness():
    page = MagicMock()
    page.evaluate = AsyncMock(side_effect=[None, None, None, 0.1])
    detector = ThemeDetector()
    theme = await detector.detect(page)
    assert theme == Theme.DARK


@pytest.mark.asyncio
async def test_theme_detector_unknown():
    page = MagicMock()
    page.evaluate = AsyncMock(side_effect=[None, None, None, None])
    detector = ThemeDetector()
    theme = await detector.detect(page)
    assert theme == Theme.UNKNOWN


# ------------------------------------------------------------------
# DOMScanner theme integration tests
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dom_scanner_full_scan_returns_theme():
    page = MagicMock()
    # Increase side_effect to account for extra _try_selectors calls
    page.evaluate = AsyncMock(side_effect=[
        None,  # media query
        None,  # class names
        None,  # data attribute
        0.2,   # brightness -> dark
        # detect_known_ui - _try_selectors calls (3 element types x 3 UIs = 9, simplified below)
        *[None] * 15,  # Extra calls for known UI detection attempts
        None,  # detect_modal_context
        [
            {"tag": "textarea", "visible": True, "area": 5000, "placeholder": "Message", "selector": "textarea", "rect": {"x": 10, "y": 500, "width": 600, "height": 50}},
        ],
        None,  # _try_selectors in detect_send_button
        None,  # detect_modal_send_button
        [
            {"tag": "button", "visible": True, "text": "Send", "hasSvgChild": False, "rect": {"x": 0, "y": 0}, "selector": "button"},
        ],
        *[None] * 5,  # More calls for _try_selectors
        None,  # detect_modal_chat_container
        [
            {"tag": "div", "visible": True, "childCount": 10, "hasScrollbar": True, "textDensity": 0.5, "selector": "div"},
        ],
    ])

    scanner = DOMScanner(min_confidence=1.0, use_known_uis=False)
    result = await scanner.full_scan(page)

    assert result["theme"] == "dark"


@pytest.mark.asyncio
async def test_dom_scanner_dark_theme_score_adjustment():
    """Test that dark theme boosts scores."""
    from webui_bridge.dom_scanner import DOMScanner
    from webui_bridge.theme_detector import Theme
    
    scanner = DOMScanner()
    scanner._theme = Theme.DARK
    
    # Test score adjustment
    base_score = 2.0
    adjusted = scanner._apply_theme_adjustment(base_score)
    assert adjusted == 2.2  # Should add 0.2 for dark theme
    
    # Light theme shouldn't add bonus
    scanner._theme = Theme.LIGHT
    adjusted = scanner._apply_theme_adjustment(base_score)
    assert adjusted == 2.0


# ------------------------------------------------------------------
# Bridge theme tests
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bridge_detect_theme_raises_when_not_connected():
    bridge = UniversalWebUIBridge()
    with pytest.raises(RuntimeError, match="not connected"):
        await bridge.detect_theme()


@pytest.mark.asyncio
async def test_bridge_detect_theme_mock():
    bridge = UniversalWebUIBridge()
    bridge._connected = True
    bridge._page = MagicMock()
    bridge._page.evaluate = AsyncMock(return_value=True)
    theme = await bridge.detect_theme()
    assert theme == "dark"


# ------------------------------------------------------------------
# Generation detection tests
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bridge_is_generating_raises_when_not_connected():
    bridge = UniversalWebUIBridge()
    with pytest.raises(RuntimeError, match="not connected"):
        await bridge.is_generating()


@pytest.mark.asyncio
async def test_message_stream_is_generating_mock():
    page = MagicMock()
    page.evaluate = AsyncMock(return_value=True)
    stream = MessageStream()
    result = await stream.is_generating(page)
    assert result is True
    page.evaluate.assert_awaited_once_with("() => window.__webui_bridge_is_generating()")


@pytest.mark.asyncio
async def test_message_stream_wait_for_generation_complete_mock():
    page = MagicMock()
    page.evaluate = AsyncMock(side_effect=[True, True, False])
    stream = MessageStream()
    result = await stream.wait_for_generation_complete(page, timeout=1.0, poll_interval=0.05)
    assert result is True
    assert page.evaluate.call_count == 3


@pytest.mark.asyncio
async def test_message_stream_wait_for_generation_complete_timeout_mock():
    page = MagicMock()
    page.evaluate = AsyncMock(return_value=True)
    stream = MessageStream()
    result = await stream.wait_for_generation_complete(page, timeout=0.1, poll_interval=0.05)
    assert result is False


@pytest.mark.asyncio
async def test_bridge_wait_for_response_with_generation_complete():
    bridge = UniversalWebUIBridge()
    bridge._connected = True
    bridge._page = MagicMock()
    bridge._stream = MagicMock()
    bridge._stream.get_messages = AsyncMock(return_value=[])
    bridge._stream.wait_for_new_assistant_message = AsyncMock(return_value={"text": "hello"})
    bridge._stream.wait_for_generation_complete = AsyncMock(return_value=True)

    result = await bridge.wait_for_response(wait_for_generation_complete=True)
    assert result == "hello"
    bridge._stream.wait_for_generation_complete.assert_awaited_once()


# ------------------------------------------------------------------
# Bridge tests
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bridge_send_raises_when_not_connected():
    bridge = UniversalWebUIBridge()
    with pytest.raises(RuntimeError, match="not connected"):
        await bridge.send("hello")


@pytest.mark.asyncio
async def test_bridge_wait_for_response_raises_when_not_connected():
    bridge = UniversalWebUIBridge()
    with pytest.raises(RuntimeError, match="not connected"):
        await bridge.wait_for_response()


@pytest.mark.asyncio
async def test_bridge_get_messages_raises_when_not_connected():
    bridge = UniversalWebUIBridge()
    with pytest.raises(RuntimeError, match="not connected"):
        await bridge.get_messages()


# ------------------------------------------------------------------
# NetworkSniffer tests
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_network_sniffer_attach_detach():
    from webui_bridge.network_sniffer import NetworkSniffer
    
    sniffer = NetworkSniffer()
    page = MagicMock()
    page.route = AsyncMock()
    page.unroute = AsyncMock()
    page.on = MagicMock()
    page.remove_listener = MagicMock()
    
    await sniffer.attach(page)
    assert sniffer._attached is True
    assert sniffer._page is page
    page.route.assert_awaited_once()
    page.on.assert_called_once_with("response", sniffer._handle_response)
    
    await sniffer.detach()
    assert sniffer._attached is False
    assert sniffer._page is None


@pytest.mark.asyncio
async def test_network_sniffer_detect_chat_endpoint_basic():
    from webui_bridge.network_sniffer import NetworkSniffer
    
    sniffer = NetworkSniffer()
    
    # Simulate captured requests
    sniffer._candidates = [
        {"url": "https://example.com/api/chat", "method": "POST", "headers": {}, "post_data": None, "timestamp": 1.0, "resource_type": "xhr"},
        {"url": "https://example.com/api/chat", "method": "POST", "headers": {}, "post_data": '{"messages": [{"role": "user", "content": "hi"}]}', "timestamp": 2.0, "resource_type": "xhr"},
    ]
    
    result = await sniffer.detect_chat_endpoint(min_candidates=1)
    assert result is not None
    assert "chat" in result


def test_network_sniffer_is_chat_endpoint_candidate():
    from webui_bridge.network_sniffer import NetworkSniffer
    
    sniffer = NetworkSniffer()
    assert sniffer._is_chat_endpoint_candidate("https://api.openai.com/v1/chat/completions") is True
    assert sniffer._is_chat_endpoint_candidate("https://example.com/api/message") is True
    assert sniffer._is_chat_endpoint_candidate("https://example.com/api/generate") is True
    assert sniffer._is_chat_endpoint_candidate("https://example.com/api/predict") is True
    assert sniffer._is_chat_endpoint_candidate("https://example.com/static/main.js") is False


@pytest.mark.asyncio
async def test_network_sniffer_get_candidates():
    from webui_bridge.network_sniffer import NetworkSniffer
    
    sniffer = NetworkSniffer()
    candidate = {"url": "https://example.com/api/test", "method": "POST", "headers": {}, "post_data": None}
    sniffer._candidates = [candidate]
    
    candidates = sniffer.get_candidates()
    assert len(candidates) == 1
    assert candidates[0]["url"] == "https://example.com/api/test"


@pytest.mark.asyncio
async def test_network_sniffer_clear():
    from webui_bridge.network_sniffer import NetworkSniffer
    
    sniffer = NetworkSniffer()
    sniffer._candidates = [{"url": "test"}]
    sniffer._detected_endpoint = "https://example.com/api"
    
    await sniffer.clear()
    assert len(sniffer._candidates) == 0
    assert sniffer._detected_endpoint is None


# ------------------------------------------------------------------
# Bridge API mode tests
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bridge_try_enable_direct_api_raises_when_not_connected():
    bridge = UniversalWebUIBridge()
    with pytest.raises(RuntimeError, match="not connected"):
        await bridge.try_enable_direct_api()


@pytest.mark.asyncio
async def test_bridge_is_api_mode_property():
    bridge = UniversalWebUIBridge()
    # Not connected, should be False
    assert bridge.is_api_mode is False
    
    # Simulate connection and API mode
    bridge._connected = True
    bridge._api_mode = True
    # But endpoint not detected, still False
    assert bridge.is_api_mode is False
    
    # Now set endpoint
    bridge._sniffer._detected_endpoint = "https://example.com/api"
    assert bridge.is_api_mode is True


@pytest.mark.asyncio
async def test_bridge_disable_direct_api():
    bridge = UniversalWebUIBridge()
    bridge._api_mode = True
    await bridge.disable_direct_api()
    assert bridge._api_mode is False
    assert bridge.is_api_mode is False


@pytest.mark.asyncio
async def test_bridge_get_detected_api_endpoint():
    bridge = UniversalWebUIBridge()
    bridge._sniffer._detected_endpoint = "https://api.example.com/chat"
    endpoint = await bridge.get_detected_api_endpoint()
    assert endpoint == "https://api.example.com/chat"


@pytest.mark.asyncio
async def test_bridge_send_uses_api_mode_when_enabled():
    bridge = UniversalWebUIBridge()
    bridge._connected = True
    bridge._page = MagicMock()
    bridge._api_mode = True
    
    # Mock sniffer to return success
    bridge._sniffer = MagicMock()
    bridge._sniffer.send_via_api = AsyncMock(return_value={"content": "API response"})
    bridge._sniffer.get_detected_endpoint.return_value = "https://api.example.com"
    
    await bridge.send("Hello via API")
    
    # Should have called sniffer.send_via_api
    bridge._sniffer.send_via_api.assert_awaited_once_with("Hello via API")


@pytest.mark.asyncio
async def test_bridge_send_falls_back_to_ui_when_api_fails():
    bridge = UniversalWebUIBridge()
    bridge._connected = True
    bridge._page = MagicMock()
    bridge._api_mode = True
    
    # Mock _send_once to succeed
    bridge._send_once = AsyncMock()
    bridge._stream = MagicMock()
    bridge._stream.scroll_to_bottom = AsyncMock()
    
    # Mock sniffer to fail (return None)
    bridge._sniffer = MagicMock()
    bridge._sniffer.send_via_api = AsyncMock(return_value=None)
    bridge._sniffer.get_detected_endpoint.return_value = "https://api.example.com"
    
    await bridge.send("Hello fallback")
    
    # Should have attempted API, then fallen back to UI
    bridge._sniffer.send_via_api.assert_awaited_once()
    bridge._send_once.assert_awaited_once_with("Hello fallback")
