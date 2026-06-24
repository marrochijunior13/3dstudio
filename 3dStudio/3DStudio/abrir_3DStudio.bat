@echo off
cd /d "%~dp0"
python -m pip install pillow numpy scipy -q
python app_corrigido.py
pause
