@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv
    if errorlevel 1 goto errore
)
if not exist ".venv\installazione_ok" (
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto errore
    echo OK>".venv\installazione_ok"
)
".venv\Scripts\python.exe" -m streamlit run app.py
if errorlevel 1 goto errore
exit /b 0
:errore
echo Verifica di avere Python 3.12 e una connessione Internet.
pause
exit /b 1
