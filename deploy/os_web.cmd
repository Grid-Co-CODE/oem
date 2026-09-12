@echo off
rem OS Creator web (os_creator/os_web): o servico que a Plataforma de Performance publica em /os/* (12/09/2026).
rem Mesmo desenho do gemeo_ingest.cmd: pythonw REAL (o alias do WindowsApps sobe um stub), log em append.
cd /d "C:\GridcoBuild\oem\os_creator"
set OS_WEB_PORTA=5090
"C:\Users\Levi Maia\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe" -m os_web.servir >> "C:\GridcoBuild\oem\logs\os_web.log" 2>&1
