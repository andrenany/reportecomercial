@echo off
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
title ADL - Actualizar GitHub

echo ========================================
echo  Regenerar todo y subir a GitHub
echo ========================================
echo.
echo  Se actualiza la informacion y el codigo:
echo   - Dashboard unificado, Solo facturacion, Reglas y fotos de pendiente
echo   - Consulta facturacion: serie, casos, facturas y calendario veterinario
echo     ^(planilla: CO km, aumentos UF, otros CO y tabla del mes^)
echo   - Resumen cantidad y proyeccion Prophet
echo.
echo  No sube: credenciales.env ni temporales de Excel ^(~$^)
echo.

where python >nul 2>&1
if errorlevel 1 (set "PY=py -3") else (set "PY=python")

echo 0^) Trayendo lo ultimo de GitHub...
git status --porcelain | findstr /r "." >nul
if errorlevel 1 (
  git pull --rebase origin main
  if errorlevel 1 (
    echo ERROR al traer cambios de GitHub.
    pause
    exit /b 1
  )
) else (
  echo    Hay cambios locales. Se regenera encima y se sube todo junto.
)

echo.
echo 1^) Dashboards desde Excel de red...
%PY% -u generar_dashboard.py
if errorlevel 1 (
  echo ERROR al generar dashboards Excel.
  pause
  exit /b 1
)

echo.
echo 2^) Reportes SQL ^(FVivaldi y planilla de costos^)...
if not exist "credenciales.env" (
  echo ERROR: falta credenciales.env en esta carpeta.
  echo Sin ese archivo no se actualiza consulta ni resumen cantidad.
  pause
  exit /b 1
)
echo    Consulta facturacion / calendario veterinario...
echo    Si alertas_correo.env tiene correos, avisa el operativo no ingresado del mes.
%PY% -u generar_consulta_facturacion.py
if errorlevel 1 (
  echo ERROR al generar consulta_facturacion.html ^(SQL^).
  echo Revisa red / credenciales.env / driver ODBC SQL Server.
  pause
  exit /b 1
)
echo    Resumen cantidad + proyeccion Prophet...
%PY% -u generar_resumen_cantidad.py
if errorlevel 1 (
  echo ERROR al generar resumen_cantidad.html ^(SQL / Prophet^).
  echo Revisa red / credenciales.env / Prophet.
  pause
  exit /b 1
)

echo.
echo 3^) Preparando commit ^(sin secretos ni temporales^)...
git add -A
git reset HEAD -- credenciales.env sql_config.local.json .env 2>nul
for /f "delims=" %%F in ('git ls-files "*~$*"') do git rm --cached --ignore-unmatch -- "%%F"
git status --short

git diff --cached --quiet
if %errorlevel%==0 (
  echo No hay cambios para subir. La informacion regenerada ya estaba al dia.
  pause
  exit /b 0
)

git commit -m "Actualiza dashboards, consulta de facturacion con calendario y planilla, y resumen cantidad"
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
echo   https://andrenany.github.io/reportecomercial/resumen_cantidad.html
echo.
echo Repo: https://github.com/andrenany/reportecomercial
echo.
echo Acceso PVE ^(solo calendario^): usuario pve / clave 1234
echo.
pause
