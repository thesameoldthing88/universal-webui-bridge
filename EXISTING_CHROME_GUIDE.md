# Using Your Existing Chrome Browser

## The Problem

By default, the Universal LLM Bridge opens a **new, clean browser window** where you have to:
- Log in to your LLM service again
- Re-enter passwords
- Go through 2FA
- Set up everything again

## The Solution: Connect to Existing Chrome

You can connect the bridge to your **already-open Chrome browser** with all your logins saved!

---

## How To Do It (Windows)

### Step 1: Close All Chrome Windows

Make sure Chrome is completely closed (check Task Manager if needed).

### Step 2: Start Chrome with Remote Debugging

**Option A: Using Command Prompt**
```bash
1. Press Win+R, type "cmd", press Enter
2. Paste this command:

"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222

3. Press Enter
```

**Option B: Using PowerShell**
```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
```

**Option C: Create a Shortcut (Easiest for future use)**
1. Right-click on Desktop → New → Shortcut
2. Enter location:
   ```
   "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
   ```
3. Name it "Chrome (Bridge Mode)"
4. Click Finish
5. Use this shortcut whenever you want to use the bridge

### Step 3: Log Into Your LLM

- Go to ChatGPT, Claude, or your LLM
- Log in normally (it will remember you!)

### Step 4: Start the Bridge GUI

1. Run the Universal LLM Bridge GUI:
   ```bash
   python run_gui.py
   ```

2. Go to **🔗 Connect** page

3. **Check the box**: "Use Existing Chrome (keep logins)"

4. Enter your LLM URL (or use preset)

5. Click **"Connect"**

✅ Done! The bridge will connect to your already-logged-in Chrome!

---

## How To Do It (Mac)

### Step 1: Close Chrome

Press Cmd+Q to fully quit Chrome.

### Step 2: Start Chrome with Remote Debugging

Open Terminal and run:
```bash
/Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222
```

Or create an Automator script for easy reuse.

### Step 3: Log In

Open your LLM and log in (cookies will be saved).

### Step 4: Start Bridge

Same as Windows - check "Use Existing Chrome" in the GUI.

---

## How To Do It (Linux)

```bash
# Close Chrome
killall chrome

# Start with remote debugging
google-chrome --remote-debugging-port=9222

# Or if using Chromium:
chromium-browser --remote-debugging-port=9222
```

Then use the GUI as normal.

---

## Alternative: Use Chrome User Data Directory

If you want the bridge to launch Chrome but with YOUR profile (bookmarks, logins, extensions):

### Find Your Chrome Profile Path

**Windows:**
```
C:\Users\YOUR_USERNAME\AppData\Local\Google\Chrome\User Data
```

**Mac:**
```
/Users/YOUR_USERNAME/Library/Application Support/Google/Chrome
```

**Linux:**
```
/home/YOUR_USERNAME/.config/google-chrome
```

### Use in Bridge (Python API)

```python
from webui_bridge import UniversalWebUIBridge
import asyncio

async def main():
    # Connect to Chrome with your profile
    bridge = UniversalWebUIBridge(
        use_existing_browser=True,
        existing_browser_endpoint="http://localhost:9222"
    )
    
    # Connect to Claude (already logged in!)
    await bridge.connect("https://claude.ai")
    
    # Send message
    await bridge.send("Hello!")
    response = await bridge.wait_for_response()
    print(response)

asyncio.run(main())
```

---

## Troubleshooting

### "Cannot connect to existing browser"

**Solution:**
1. Make sure Chrome was started with `--remote-debugging-port=9222`
2. Check if port is in use: `netstat -ano | findstr 9222` (Windows)
3. Try a different port: `--remote-debugging-port=9223`

### "Port already in use"

**Solution:**
```bash
# Find process using port 9222
# Windows:
netstat -ano | findstr 9222
taskkill /PID [THE_PID] /F

# Mac/Linux:
lsof -ti:9222 | xargs kill -9
```

### Chrome won't start in debug mode

**Solution:** Make sure ALL Chrome windows are closed first. Check Task Manager (Windows) or Activity Monitor (Mac) for "chrome" processes.

### Login still required

**Solution:** You need to log in AFTER starting Chrome in debug mode, not before. The debugging mode only exposes the API - it doesn't automatically log you in.

---

## Security Notes

⚠️ **Warning:** Using `--remote-debugging-port` allows any program on your computer to control Chrome. Only do this on trusted, personal computers.

**Best practices:**
- Use port 9222 only locally (default is safe)
- Don't expose this port externally
- Close Chrome when done
- Don't use on public/shared computers

---

## Quick Reference Card

```
┌─────────────────────────────────────────┐
│  USING EXISTING CHROME WITH BRIDGE      │
├─────────────────────────────────────────┤
│  1. Close all Chrome windows            │
│  2. Run Chrome with debug port:         │
│     chrome --remote-debugging-port=9222 │
│  3. Log into your LLM                   │
│  4. Check "Use Existing Chrome" in GUI  │
│  5. Click Connect                       │
└─────────────────────────────────────────┘
```

---

## Example Scenarios

### Scenario 1: Claude Web Already Logged In

```
✓ Chrome already open with claude.ai logged in
✓ Start Chrome with: --remote-debugging-port=9222
✓ Bridge connects to existing tab
✓ No re-login needed!
```

### Scenario 2: Multiple LLMs

```
✓ Open Claude in Tab 1 (logged in)
✓ Open OpenWebUI in Tab 2 (logged in)
✓ Bridge can switch between them
✓ No need to log in each time
```

### Scenario 3: Work Computer

```
✓ Chrome has work SSO configured
✓ Starting Chrome with debug flag
✓ Bridge uses existing SSO session
✓ Access work LLM without re-auth
```

---

**Need help?** Check the Diagnostics page in the GUI or enable debug logging in Settings.
