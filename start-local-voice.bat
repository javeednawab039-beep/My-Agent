@echo off
cd /d "%~dp0"
py -3.13 -c "import pywhispercpp, websockets, cv2, cryptography"
if errorlevel 1 (
  py -3.13 -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Could not install the local voice server dependencies.
    pause
    exit /b 1
  )
)
py -3.13 -u local_voice_server.py
if errorlevel 1 (
  echo The local voice server stopped with an error.
  pause
  exit /b 1
)
