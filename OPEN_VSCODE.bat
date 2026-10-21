@echo off
setlocal
chcp 65001 >nul
where code >nul 2>&1
if errorlevel 1 goto standard_locations
call code --new-window "%~dp0Mira-Beauty.code-workspace"
if errorlevel 1 goto failed
exit /b 0
:standard_locations
if not exist "%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe" goto system_location
start "" "%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe" --new-window "%~dp0Mira-Beauty.code-workspace"
exit /b 0
:system_location
if not exist "%ProgramFiles%\Microsoft VS Code\Code.exe" goto failed
start "" "%ProgramFiles%\Microsoft VS Code\Code.exe" --new-window "%~dp0Mira-Beauty.code-workspace"
exit /b 0
:failed
echo Не удалось автоматически открыть VS Code.
echo Откройте VS Code, нажмите File - Open Folder.
echo Выберите эту папку: %~dp0
pause
exit /b 1
