@ECHO OFF
CD .\frontend
START npm run dev
CD ..
START python -m uvicorn app.main:app --reload --app-dir backend
EXIT