@echo off\nset OPENAI_BASE_URL=http://localhost:8000/v1\nset OPENAI_API_KEY=webui-bridge\npi --provider openai --model webui-bridge -p "say hello world"\npause
