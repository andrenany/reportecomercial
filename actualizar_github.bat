@echo off
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
title ADL - Actualizar GitHub

echo ========================================
echo  Regenerar dashboard y subir a GitHub
echo ========================================
echo.

where python >nul 2>&1
if errorlevel 1 (set "PY=py -3") else (set "PY=python")

echo 1^) Generando dashboards desde Excel...
%PY% -u generar_dashboard.py
if errorlevel 1 (
  echo ERROR al generar.
  pause
  exit /b 1
)

echo.
echo 2^) Subiendo a GitHub...
git add -A
git status --short
git diff --cached --quiet
if %errorlevel%==0 (
  echo No hay cambios para subir.
  pause
  exit /b 0
)

git commit -m "Actualiza dashboards de facturacion"
if errorlevel 1 (
  echo ERROR en commit.
  pause
  exit /b 1
)

git push -u origin main
if errorlevel 1 (
  echo.
  echo ERROR al push. Revisa login de GitHub ^(Git Credential Manager^).
  pause
  exit /b 1
)

echo.
echo OK. Link tipico de GitHub Pages ^(si esta activado^):
echo   https://andrenany.github.io/reportecomercial/
echo.
echo Repo: https://github.com/andrenany/reportecomercial
echo.
pause
