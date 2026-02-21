@echo off
echo Building ROM Duplicate Manager...
pyinstaller --onefile --windowed --name RomDuplicateManager --collect-all customtkinter main.py
echo.
echo Build complete! EXE is in dist\RomDuplicateManager.exe
pause
