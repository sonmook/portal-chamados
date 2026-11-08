@echo off
setlocal DisableDelayedExpansion
pushd "%~dp0" || exit /b 1
if not exist ".venv\Scripts\python.exe" (
    echo Ambiente .venv nao encontrado nesta pasta.
    echo Consulte docs\inicializacao-windows.md para preparar o ambiente.
    popd
    exit /b 1
)
".venv\Scripts\python.exe" -u scripts\iniciar_local.py %*
set "PORTAL_EXIT=%ERRORLEVEL%"
popd
exit /b %PORTAL_EXIT%
