(function() {
    'use strict';

    const BUFFER_KEY = '__WEBUI_BRIDGE_MESSAGES';
    const STATE_KEY = '__WEBUI_BRIDGE_STATE';

    if (window[BUFFER_KEY]) {
        return;
    }

    window[BUFFER_KEY] = [];
    window[STATE_KEY] = {
        chatSelector: null,
        lastText: '',
        streamingIds: [],
        streamingTimeouts: {},
        lastMutationTime: 0,
        lastTextChangeTime: 0,
    };

    const SCROLL_THRESHOLD = 50;

    function isNearBottom(el) {
        if (!el) return false;
        return (el.scrollHeight - el.scrollTop - el.clientHeight) <= SCROLL_THRESHOLD;
    }

    function scrollToBottom(el) {
        if (!el) return;
        el.scrollTop = el.scrollHeight;
    }

    function now() {
        return new Date().toISOString();
    }

    function generateId() {
        return 'msg_' + Math.random().toString(36).slice(2) + '_' + Date.now();
    }

    function isAssistantLike(el) {
        const classes = (el.className || '').toLowerCase();
        const text = (el.textContent || '').substring(0, 60).toLowerCase();
        const authorEl = el.querySelector('[data-author], [data-role], [data-message-author]');
        if (authorEl) {
            const author = (authorEl.textContent || '').toLowerCase();
            if (author.includes('user') || author.includes('you') || author.includes('human')) return false;
            if (author.includes('assistant') || author.includes('bot') || author.includes('ai') || author.includes('model')) return true;
        }
        if (classes.includes('assistant') || classes.includes('bot') || classes.includes('ai') || classes.includes('model')) return true;
        if (classes.includes('user') || classes.includes('human') || classes.includes('me')) return false;
        if (text.startsWith('assistant:') || text.startsWith('bot:') || text.startsWith('ai:')) return true;
        if (text.startsWith('you:') || text.startsWith('user:') || text.startsWith('human:')) return false;
        return null;
    }

    function classifyAuthor(el, index) {
        const explicit = isAssistantLike(el);
        if (explicit !== null) return explicit ? 'assistant' : 'user';
        const prev = window[BUFFER_KEY][window[BUFFER_KEY].length - 1];
        if (prev) {
            return prev.author === 'user' ? 'assistant' : 'user';
        }
        return index % 2 === 0 ? 'assistant' : 'user';
    }

    function closestMessage(el) {
        if (!el) return null;
        let current = el;
        for (let i = 0; i < 8 && current; i++) {
            const cls = (current.className || '').toLowerCase();
            const tag = current.tagName?.toLowerCase() || '';
            if (cls.includes('message') || cls.includes('chat') || cls.includes('bubble') || tag === 'li') {
                return current;
            }
            current = current.parentElement;
        }
        return el;
    }

    function extractText(el) {
        const clone = el.cloneNode(true);
        clone.querySelectorAll('script, style, svg, button, input, textarea').forEach(e => e.remove());
        return (clone.innerText || clone.textContent || '').trim();
    }

    function markStreaming(msgId) {
        const buffer = window[BUFFER_KEY];
        const state = window[STATE_KEY];
        const msg = buffer.find(m => m.id === msgId);
        if (msg) {
            msg.streaming = true;
        }
        if (!state.streamingIds.includes(msgId)) {
            state.streamingIds.push(msgId);
        }
        if (state.streamingTimeouts[msgId]) {
            clearTimeout(state.streamingTimeouts[msgId]);
        }
        state.streamingTimeouts[msgId] = setTimeout(() => {
            const m = buffer.find(x => x.id === msgId);
            if (m) {
                m.streaming = false;
            }
            state.streamingIds = state.streamingIds.filter(id => id !== msgId);
            delete state.streamingTimeouts[msgId];
        }, 1000);
    }

    function observeContainer(container) {
        if (!container) return;

        const observer = new MutationObserver((mutations) => {
            let processedAny = false;
            for (const m of mutations) {
                if (m.type === 'childList') {
                    for (const node of m.addedNodes) {
                        if (node.nodeType !== 1) continue;
                        const text = extractText(node);
                        if (!text) continue;
                        const author = classifyAuthor(node, window[BUFFER_KEY].length);
                        const msg = {
                            id: generateId(),
                            author: author,
                            text: text,
                            timestamp: now(),
                            streaming: false,
                            element: node,
                        };
                        window[BUFFER_KEY].push(msg);
                        processedAny = true;
                        if (author === 'assistant') {
                            markStreaming(msg.id);
                        }
                    }
                } else if (m.type === 'characterData') {
                    const target = m.target;
                    if (target.parentElement) {
                        const msgEl = closestMessage(target.parentElement) || target.parentElement;
                        const text = extractText(msgEl);
                        const buffer = window[BUFFER_KEY];
                        let matched = buffer.find(mg => mg.element === msgEl);
                        if (!matched) {
                            matched = buffer.find(mg => msgEl.contains(mg.element) || mg.element.contains(msgEl));
                        }
                        if (matched) {
                            const changed = matched.text !== text;
                            matched.text = text;
                            markStreaming(matched.id);
                            window[STATE_KEY].lastMutationTime = Date.now();
                            if (changed) {
                                window[STATE_KEY].lastTextChangeTime = Date.now();
                                processedAny = true;
                            }
                        }
                    }
                }
            }
            if (processedAny) {
                window.dispatchEvent(new CustomEvent('webui_bridge_message', { detail: window[BUFFER_KEY].slice(-1)[0] }));
                const container = window[STATE_KEY].chatSelector;
                if (container && isNearBottom(container)) {
                    scrollToBottom(container);
                }
            }
        });

        observer.observe(container, { childList: true, subtree: true, characterData: true });
        window[STATE_KEY].observer = observer;
        window[STATE_KEY].chatSelector = container;

        const existing = container.querySelectorAll('div, li, article, section');
        existing.forEach((el, idx) => {
            const text = extractText(el);
            if (!text || text.length < 3) return;
            window[BUFFER_KEY].push({
                id: generateId(),
                author: classifyAuthor(el, idx),
                text: text,
                timestamp: now(),
                streaming: false,
                element: el,
            });
        });
    }

    function findChatContainer() {
        const candidates = [];
        document.querySelectorAll('div, section, article, main, ul, ol').forEach(el => {
            const rect = el.getBoundingClientRect();
            if (rect.width <= 0 || rect.height <= 0) return;
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') return;
            const childCount = el.children.length;
            if (childCount < 2) return;
            const text = el.innerText || '';
            const textDensity = text.length / (rect.width * rect.height + 1);
            const overflowY = style.overflowY;
            const hasScrollbar = (overflowY === 'auto' || overflowY === 'scroll') && el.scrollHeight > el.clientHeight;
            let score = 0;
            score += Math.min(childCount * 0.2, 3);
            if (hasScrollbar) score += 1.5;
            if (textDensity > 0.0003) score += 1.5;
            candidates.push({ el, score });
        });
        candidates.sort((a, b) => b.score - a.score);
        return candidates[0]?.el || null;
    }

    function hasLoadingIndicators(el) {
        if (!el) return false;
        const selectors = [
            '.loading', '.spinner', '.typing', '.thinking', '.generating',
            '.animate', '.pulse',
            '[class*="loading"]', '[class*="spinner"]', '[class*="typing"]',
            '[class*="thinking"]', '[class*="generating"]', '[class*="animate"]',
            '[class*="pulse"]',
        ];
        for (const sel of selectors) {
            if (el.querySelector(sel)) return true;
        }
        return false;
    }

    function hasEllipsisPattern(text) {
        if (!text) return false;
        return /(\.{3,}|…|thinking\.{0,3})/i.test(text);
    }

    window.__webui_bridge_is_generating = function() {
        const buffer = window[BUFFER_KEY];
        let lastAssistant = null;
        for (let i = buffer.length - 1; i >= 0; i--) {
            if (buffer[i].author === 'assistant') {
                lastAssistant = buffer[i];
                break;
            }
        }
        if (!lastAssistant) return false;

        const state = window[STATE_KEY];
        const now = Date.now();

        // 1. Recent text changes (within 500ms)
        if (state.lastTextChangeTime && (now - state.lastTextChangeTime) < 500) {
            return true;
        }

        // 2. Recent mutations on assistant messages (within 500ms)
        if (state.lastMutationTime && (now - state.lastMutationTime) < 500) {
            return true;
        }

        // 3. Spinner / loading indicators inside the message element
        if (hasLoadingIndicators(lastAssistant.element)) {
            return true;
        }

        // 4. Ellipsis patterns in the message text
        if (hasEllipsisPattern(lastAssistant.text)) {
            return true;
        }

        // 5. Explicit streaming flag
        if (lastAssistant.streaming) {
            return true;
        }

        return false;
    };

    window.__webui_bridge_start = function(selector) {
        const container = selector ? document.querySelector(selector) : findChatContainer();
        if (!container) {
            console.error('[WebUI Bridge] Chat container not found');
            return false;
        }
        observeContainer(container);
        console.log('[WebUI Bridge] Observing container', container);
        return true;
    };

    window.__webui_bridge_get_messages = function() {
        return window[BUFFER_KEY].map(m => ({
            id: m.id,
            author: m.author,
            text: m.text,
            timestamp: m.timestamp,
            streaming: m.streaming,
        }));
    };

    window.__webui_bridge_clear = function() {
        window[BUFFER_KEY] = [];
        window[STATE_KEY].lastText = '';
        window[STATE_KEY].streamingIds = [];
        window[STATE_KEY].lastMutationTime = 0;
        window[STATE_KEY].lastTextChangeTime = 0;
        for (const tid of Object.values(window[STATE_KEY].streamingTimeouts || {})) {
            clearTimeout(tid);
        }
        window[STATE_KEY].streamingTimeouts = {};
    };

    window.__webui_bridge_stop = function() {
        if (window[STATE_KEY].observer) {
            window[STATE_KEY].observer.disconnect();
            window[STATE_KEY].observer = null;
        }
    };

    window.__webui_bridge_scroll_to_bottom = function(selector) {
        const el = selector ? document.querySelector(selector) : window[STATE_KEY].chatSelector;
        scrollToBottom(el);
    };
})();