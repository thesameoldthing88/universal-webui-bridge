# Simple Guide for Web LLMs (Grok, ChatGPT, Claude)

## The Problem

Google and other login systems **block automated browsers**. This is a security feature that can't be bypassed.

## ✅ The Simple Solution

### For Grok, ChatGPT, Claude (sites with Google login):

**Step 1: Launch YOUR Chrome with debugging**

Double-click this file I've created for you:
```
Launch_Chrome_For_Bridge.bat
```

**Step 2: Log in normally**
- Go to www.grok.com in that Chrome window
- Log in with your Google account (this works because it's YOUR Chrome)
- Stay logged in, keep the tab open

**Step 3: In the Bridge GUI**
1. Select "Custom" in the dropdown
2. Enter URL: `https://www.grok.com`
3. **Check** "Use Existing Chrome"
4. Click **Connect**

The bridge will connect to your already-logged-in Chrome!

---

## 🚫 Don't try these (they won't work):

❌ Trying to log in through the bridge's browser (Google blocks it)
❌ Using "Headless Mode" for sites requiring login
❌ Any automated login attempts (Google security prevents this)

---

## ✅ DO this instead:

✅ Use "Local LLM" mode for OpenWebUI, LM Studio (no login needed)
✅ Use "Existing Chrome" mode for Grok, ChatGPT, Claude
✅ Keep your Chrome browser open after logging in
✅ The bridge will use your existing session

---

## 🔥 Even Easier: Skip the GUI

**Just use the Python script directly:**

```python
import asyncio
from webui_bridge import UniversalWebUIBridge

async def main():
    # Step 1: Launch Chrome with: chrome.exe --remote-debugging-port=9222
    # Step 2: Log into Grok in that Chrome
    # Step 3: Run this:
    
    bridge = UniversalWebUIBridge(
        use_existing_browser=True,  # Use your logged-in Chrome
        existing_browser_endpoint="http://localhost:9222"
    )
    
    await bridge.connect("https://www.grok.com")
    
    print("Connected!")
    await bridge.send("Hello!")
    response = await bridge.wait_for_response()
    print(response)
    
    await bridge.close()

asyncio.run(main())
```

---

## 💡 What if it still doesn't connect?

**Check Chrome debugging port:**
```cmd
# In new Command Prompt:
netstat -ano | findstr 9222

# If nothing shows, Chrome isn't running in debug mode
```

**Verify the launch command:**
```cmd
cd "C:\Program Files\Google\Chrome\Application"
chrome.exe --remote-debugging-port=9222
```

**Check if the bridge can see Chrome:**
```python
import requests
print(requests.get("http://localhost:9222/json").text)
# Should show Chrome pages
```

---

## 🎯 TL;DR (Too Long; Didn't Read)

1. **Launch Chrome with debugging** using the .bat file
2. **Log into Grok manually** in that Chrome window
3. **Keep Chrome open**
4. **Check "Use Existing Chrome"** in the GUI
5. **Click Connect** - it should work now!

The key is: **Log in FIRST in your Chrome, THEN connect the bridge.**
