@echo off
cd /d "%~dp0"
echo Starting Universal LLM Bridge...
echo.
python -m streamlit run src/webui_bridge_v2/ui.py --server.address 127.0.0.1 --server.port 8501
pause