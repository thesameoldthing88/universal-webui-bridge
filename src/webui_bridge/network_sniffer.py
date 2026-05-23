import json
import logging
import re
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

from playwright.async_api import Request, Response

logger = logging.getLogger(__name__)


class NetworkSniffer:
    """
    Detects backend API endpoints by intercepting network requests.
    """

    def __init__(self):
        self._page: Optional[Any] = None
        self._detected_endpoint: Optional[str] = None
        self._candidates: List[Dict] = []
        self._attached = False

    async def attach(self, page: Any) -> None:
        """Attach to a page and start intercepting requests."""
        if self._attached:
            await self.detach()
        self._page = page
        # Intercept all requests
        await self._page.route("**/*", self._handle_request)
        # Also capture responses to analyze payloads
        self._page.on("response", self._handle_response)
        self._attached = True
        logger.info("NetworkSniffer attached")

    async def detach(self) -> None:
        """Detach and stop intercepting."""
        if not self._attached or not self._page:
            return
        # Remove all routes
        await self._page.unroute("**/*", self._handle_request)
        # Remove response listener
        self._page.remove_listener("response", self._handle_response)
        self._page = None
        self._attached = False
        logger.info("NetworkSniffer detached")

    async def _handle_request(self, request: Request) -> None:
        """Intercept and record request details."""
        # We only care about certain types of requests
        if request.method not in ({"POST", "PUT", "PATCH"}):
            await request.continue_()
            return

        url = request.url
        method = request.method
        headers = dict(request.headers)
        # Post data might be empty for now; we'll get it if needed
        post_data = None
        try:
            # For POST, we can try to get the post data
            post_data = await request.post_data()
        except Exception:
            pass

        # Record candidate
        candidate = {
            "url": url,
            "method": method,
            "headers": headers,
            "post_data": post_data,
            "timestamp": request.timestamp(),
            "resource_type": request.resource_type,
        }
        self._candidates.append(candidate)
        logger.debug("Recorded API request: %s %s", method, url)

        # Continue the request normally
        await request.continue_()

    async def _handle_response(self, response: Response) -> None:
        """Intercept responses to analyze content."""
        # We could match responses to requests, but for simplicity
        # we'll just note successful JSON responses that look like chat responses.
        if response.status != 200:
            return

        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return

        try:
            json_data = await response.json()
        except Exception:
            return

        # Heuristic: does the JSON look like a chat response?
        # Look for common fields: message, content, text, etc.
        if isinstance(json_data, dict):
            chat_indicators = {"message", "content", "text", "reply", "answer"}
            if any(key in json_data for key in chat_indicators):
                # Also check if the request that caused this was a POST to a chat-like endpoint
                # We'll need to match request to response; for now, we'll just note the URL
                # but we can improve by storing request-id mapping.
                # For simplicity, we'll just consider the endpoint as a candidate.
                # We'll rely on request-side heuristics for now.
                pass
        # We could store response data, but for detection we focus on requests.

    def _is_chat_endpoint_candidate(self, url: str) -> bool:
        """Heuristic to determine if a URL looks like a chat API endpoint."""
        url_lower = url.lower()
        # Patterns that suggest a chat/completion endpoint
        patterns = [
            r'/chat',
            r'/message',
            r'/completions',
            r'/generate',
            r'/predict',
            r'/llm',
            r'/ai',
            r'/v[0-9]+/chat',
            r'/v[0-9]+/completions',
            r'/api/chat',
            r'/api/message',
        ]
        for pattern in patterns:
            if re.search(pattern, url_lower):
                return True
        return False

    async def detect_chat_endpoint(self, min_candidates: int = 2) -> Optional[str]:
        """
        Analyze captured requests and return the most likely chat endpoint.

        Args:
            min_candidates: minimum number of similar requests needed to consider an endpoint.

        Returns:
            The detected endpoint URL, or None if not confident.
        """
        if not self._candidates:
            logger.warning("No requests captured for analysis")
            return None

        # Group by URL (ignoring query parameters for simplicity)
        from urllib.parse import urlparse
        grouped: Dict[str, List[Dict]] = {}
        for cand in self._candidates:
            if not cand["method"] == "POST":
                continue
            url = cand["url"]
            parsed = urlparse(url)
            # Use path and netloc as key, ignore query and fragment
            key = f"{parsed.netloc}{parsed.path}"
            grouped.setdefault(key, []).append(cand)

        # Score each group
        best_key: Optional[str] = None
        best_score = 0
        for key, cands in grouped.items():
            if len(cands) < min_candidates:
                continue
            score = len(cands)  # basic frequency
            # Boost if URL looks like chat endpoint
            if self._is_chat_endpoint_candidate(key):
                score += 2
            # Boost if any candidate has post_data that looks like a chat payload
            for cand in cands:
                post_data = cand.get("post_data")
                if post_data:
                    # Try to parse as JSON
                    try:
                        data = json.loads(post_data)
                        if isinstance(data, dict):
                            # Look for typical chat input fields
                            if any(field in data for field in ("prompt", "messages", "input", "question")):
                                score += 1
                                break
                    except Exception:
                        pass
            if score > best_score:
                best_score = score
                best_key = key

        if best_key:
            # Reconstruct full URL? We don't have the full URL with query.
            # We'll return the first candidate's URL that matches the key.
            for cand in self._candidates:
                parsed = urlparse(cand["url"])
                if f"{parsed.netloc}{parsed.path}" == best_key:
                    self._detected_endpoint = cand["url"]
                    logger.info("Detected chat endpoint: %s (score: %d)", self._detected_endpoint, best_score)
                    return self._detected_endpoint

        logger.warning("Could not confidently detect chat endpoint")
        return None

    def get_detected_endpoint(self) -> Optional[str]:
        """Return the last detected endpoint."""
        return self._detected_endpoint

    def get_candidates(self) -> List[Dict]:
        """Return all captured request candidates."""
        return self._candidates.copy()

    async def clear(self) -> None:
        """Clear captured candidates."""
        self._candidates.clear()
        self._detected_endpoint = None

    # ------------------------------------------------------------------
    # Direct API communication
    # ------------------------------------------------------------------

    async def send_via_api(
        self,
        message: str,
        endpoint: Optional[str] = None,
        payload_template: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """
        Send a message via the detected API endpoint.
        
        Uses Playwright's fetch API to make direct HTTP requests.
        
        Args:
            message: The message text to send
            endpoint: URL to use (defaults to detected endpoint)
            payload_template: Optional template dict to merge with message
            
        Returns:
            JSON response dict or None if request failed
        """
        if not self._page:
            logger.error("No page available for API request")
            return None
            
        target = endpoint or self._detected_endpoint
        if not target:
            logger.error("No API endpoint available. Call detect_chat_endpoint() first or provide endpoint.")
            return None
        
        # Build payload - try to infer format from captured requests
        payload = self._build_payload(message, payload_template)
        
        try:
            # Use Playwright's fetch via page.evaluate
            result = await self._page.evaluate(
                """async ({url, body}) => {
                    const response = await fetch(url, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify(body)
                    });
                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                    }
                    return await response.json();
                }""",
                {"url": target, "body": payload}
            )
            logger.info("API request successful to %s", target)
            return result
        except Exception as exc:
            logger.error("API request failed: %s", exc)
            return None
    
    def _build_payload(
        self,
        message: str,
        template: Optional[Dict] = None,
    ) -> Dict:
        """Build request payload, inferring format from captured requests if available."""
        if template:
            # Deep copy and inject message
            payload = json.loads(json.dumps(template))
            # Try common message field paths
            if "messages" in payload:
                payload["messages"].append({"role": "user", "content": message})
            elif "prompt" in payload:
                payload["prompt"] = message
            elif "input" in payload:
                payload["input"] = message
            elif "question" in payload:
                payload["question"] = message
            else:
                payload["message"] = message
            return payload
        
        # Try to infer from captured candidates
        if self._candidates:
            # Find a candidate with JSON post_data
            for cand in reversed(self._candidates):
                post_data = cand.get("post_data")
                if post_data:
                    try:
                        data = json.loads(post_data)
                        if isinstance(data, dict):
                            # Clone and replace message
                            payload = json.loads(json.dumps(data))
                            # Replace the last message or prompt
                            if "messages" in payload and isinstance(payload["messages"], list):
                                # Check if last message is user message
                                if payload["messages"] and payload["messages"][-1].get("role") == "user":
                                    payload["messages"][-1]["content"] = message
                                else:
                                    payload["messages"].append({"role": "user", "content": message})
                                return payload
                            elif "prompt" in payload:
                                payload["prompt"] = message
                                return payload
                            elif "input" in payload:
                                payload["input"] = message
                                return payload
                    except Exception:
                        continue
        
        # Default format: OpenAI-compatible
        return {
            "messages": [{"role": "user", "content": message}],
            "stream": False
        }
    
    async def stream_via_api(
        self,
        message: str,
        endpoint: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream response via API (for SSE endpoints).
        
        Yields response chunks as they arrive.
        """
        if not self._page:
            logger.error("No page available for streaming API request")
            return
            
        target = endpoint or self._detected_endpoint
        if not target:
            logger.error("No API endpoint available for streaming")
            return
        
        payload = self._build_payload(message)
        payload["stream"] = True
        
        try:
            # Use fetch with streaming response reading
            # This is more complex via page.evaluate - we'll read line by line
            response = await self._page.evaluate(
                """async ({url, body}) => {
                    const response = await fetch(url, {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(body)
                    });
                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                    }
                    // For SSE, we need to read the body
                    const reader = response.body.getReader();
                    const decoder = new TextDecoder();
                    let chunks = [];
                    while (true) {
                        const {done, value} = await reader.read();
                        if (done) break;
                        chunks.push(decoder.decode(value, {stream: true}));
                    }
                    return chunks.join('\\n');
                }""",
                {"url": target, "body": payload}
            )
            
            # Parse SSE format (data: lines)
            for line in response.split('\\n'):
                line = line.strip()
                if line.startswith('data: '):
                    data = line[6:]
                    if data == '[DONE]':
                        break
                    try:
                        json_data = json.loads(data)
                        # Extract content from various formats
                        content = (
                            json_data.get('choices', [{}])[0].get('delta', {}).get('content') or
                            json_data.get('content') or
                            json_data.get('message', {}).get('content') or
                            ''
                        )
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
                        
        except Exception as exc:
            logger.error("API streaming failed: %s", exc)