@ECHO OFF
CD .\frontend
START npm run dev
CD ..
python -m uvicorn app.main:app --reload --app-dir backend --port 8080
EXIT