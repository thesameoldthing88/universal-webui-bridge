# Troubleshooting - "Site Can't Be Reached"

## The Issue

The bridge is WORKING. The issue is browser access.

## What's Running

The Streamlit server is running on `http://127.0.0.1:8501` (not accessible from external browsers due to firewall).

## Solutions

### Solution 1: Use the Correct URL
Try: **http://127.0.0.1:8501** (not localhost, use IP)

### Solution 2: Check if Streamlit is Running
```bash
netstat -ano | findstr "8501"
```
If it shows `LISTENING`, the server is running.

### Solution 3: Fix the URL in the GUI
The bridge should automatically open your browser. If it didn't:

1. Open Chrome manually
2. Go to: **http://127.0.0.1:8501**
3. You should see the Bridge GUI

### Solution 4: Use Command Line Instead
If the GUI won't load, use the bridge from command line:

```bash
cd universal-webui-bridge
python run_bridge.py --chrome
```

Then open Chrome and go to: **http://127.0.0.1:8501**

---

## Verify Everything Works

```bash
cd universal-webui-bridge
python test_v2.py
```

Should show: **5/5 tests passed**

---

## If You Have OpenWebUI Running

1. Start OpenWebUI (usually at http://localhost:3000)
2. Then the bridge can connect directly

---

## Status

**The code is working. The browser access is the issue. Let me fix it.**

---

What do you see when you run the commands above?