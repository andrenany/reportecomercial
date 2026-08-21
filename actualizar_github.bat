@echo off
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
title ADL - Actualizar GitHub

echo ========================================
echo  Regenerar reportes y subir a GitHub
echo ========================================
echo.
echo  Incluye:
echo   - Dashboard unificado + Solo facturacion ^(Excel red^)
echo   - Consulta facturacion / calendario vet ^(SQL FVivaldi^)
echo   - Reglas, login y auth
echo.
echo  NO sube: credenciales.env ^(esta en .gitignore^)
echo.

where python >nul 2>&1
if errorlevel 1 (set "PY=py -3") else (set "PY=python")

echo 1^) Generando dashboards desde Excel de red...
%PY% -u generar_dashboard.py
if errorlevel 1 (
  echo ERROR al generar dashboards Excel.
  pause
  exit /b 1
)

echo.
echo 2^) Generando Consulta facturacion ^(SQL vw_FVivaldiWebSalud^)...
if not exist "credenciales.env" (
  echo AVISO: no esta credenciales.env — se omite la consulta SQL.
  echo         Copia/crea credenciales.env en esta carpeta para regenerarla.
) else (
  %PY% -u generar_consulta_facturacion.py
  if errorlevel 1 (
    echo ERROR al generar consulta_facturacion.html ^(SQL^).
    echo Revisa red / credenciales.env / driver ODBC SQL Server.
    pause
    exit /b 1
  )
)

echo.
echo 3^) Preparando commit ^(sin secretos^)...
git add -A
git reset HEAD -- credenciales.env 2>nul
git status --short

git diff --cached --quiet
if %errorlevel%==0 (
  echo No hay cambios para subir.
  pause
  exit /b 0
)

git commit -m "Actualiza dashboards, consulta SQL FVivaldi y calendario veterinarios"
if errorlevel 1 (
  echo ERROR en commit.
  pause
  exit /b 1
)

echo.
echo 4^) Subiendo a GitHub...
git push -u origin main
if errorlevel 1 (
  echo.
  echo ERROR al push. Revisa login de GitHub ^(Git Credential Manager^).
  pause
  exit /b 1
)

echo.
echo OK. GitHub Pages ^(si esta activado^):
echo   https://andrenany.github.io/reportecomercial/
echo   https://andrenany.github.io/reportecomercial/login.html
echo   https://andrenany.github.io/reportecomercial/consulta_facturacion.html
echo.
echo Repo: https://github.com/andrenany/reportecomercial
echo.
echo Acceso PVE ^(solo calendario^): usuario pve / clave 1234
echo.
pause
