@echo off
cd /d D:\GT_plan\backend
call ..\.venv\Scripts\activate.bat
uvicorn app.main:app --host 0.0.0.0 --port 9980 --reload
