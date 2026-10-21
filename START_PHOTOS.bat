@echo off
setlocal
chcp 65001 >nul
set "MIRA_PORT=5019"
set "MIRA_HOST=127.0.0.1"
echo.
echo Mira Beauty - версия с 19 настоящими фотографиями
echo Папка проекта: %~dp0
echo Новый адрес: http://127.0.0.1:5019
echo Прежняя вкладка на порту 5000 относится к другому запуску.
echo.
call "%~dp0START.bat"
endlocal
