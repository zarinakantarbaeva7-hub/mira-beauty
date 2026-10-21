@echo off
setlocal
chcp 65001 >nul
pushd "%~dp0"
if errorlevel 1 goto folder_error

echo.
echo Mira Beauty - подготовка и запуск

echo.
if exist ".venv\Scripts\python.exe" goto environment_ready

py -3 -c "import sys; raise SystemExit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 goto create_with_py

python -c "import sys; raise SystemExit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 goto create_with_python

echo Python 3.10 или новее не найден.
echo Установите Python с python.org и включите Add Python to PATH.
goto failed

:create_with_py
py -3 -m venv ".venv"
if errorlevel 1 goto failed
goto environment_ready

:create_with_python
python -m venv ".venv"
if errorlevel 1 goto failed

:environment_ready
".venv\Scripts\python.exe" -c "import sys; raise SystemExit(sys.version_info < (3, 10))"
if errorlevel 1 goto version_error

".venv\Scripts\python.exe" -m pip --disable-pip-version-check install -r requirements.txt
if errorlevel 1 goto failed

".venv\Scripts\python.exe" app.py setup-admin
if errorlevel 1 goto failed

set "MIRA_OPEN_BROWSER=1"
echo.
echo Запускается сайт. Оставьте это окно открытым.
echo Чтобы остановить сервер, нажмите Ctrl+C.
echo.
".venv\Scripts\python.exe" app.py
if errorlevel 1 goto failed

popd
endlocal
exit /b 0

:version_error
echo Окружение .venv использует неподходящую версию Python.
echo Переименуйте папку .venv и запустите START.bat снова.
goto failed

:folder_error
echo Не удалось открыть папку проекта.
pause
endlocal
exit /b 1

:failed
echo.
echo Запуск не завершён. Скопируйте сообщение об ошибке выше.
pause
popd
endlocal
exit /b 1
