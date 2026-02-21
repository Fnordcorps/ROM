@echo off
echo Building ROM...
python -m PyInstaller --onefile --windowed --name ROM ^
  --icon="y:/RomManager/icon.ico" ^
  --add-data "y:/RomManager/icon.ico;." ^
  --add-data "y:/RomManager/banner.png;." ^
  --collect-all customtkinter ^
  --distpath ./package --workpath ./build --specpath ./build ^
  main.py
echo.
echo Build complete! EXE is in package\ROM.exe
pause
