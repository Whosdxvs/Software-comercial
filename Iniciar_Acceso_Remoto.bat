@echo off
chcp 65001 >nul 2>&1
title GestPro - Acceso Remoto (Internet)
color 0A
cls
echo ====================================================================
echo     GESTPRO COMERCIAL - ACCESO REMOTO DESDE CUALQUIER LUGAR
echo ====================================================================
echo.
echo   Este script inicia el servidor web de GestPro y crea un enlace
echo   publico seguro (HTTPS) con Cloudflare Tunnel para que puedas
echo   acceder desde tu celular con datos moviles, sin estar en el
echo   Wi-Fi del negocio.
echo.
echo   1. Se inicia el servidor GestPro en el puerto 8000
echo   2. Se crea un tunel seguro con Cloudflare (gratis)
echo   3. Aparecera un enlace HTTPS que puedes abrir en tu celular
echo.
echo   IMPORTANTE: Deja esta ventana abierta mientras uses GestPro
echo   desde afuera. Si la cierras se corta el acceso remoto.
echo.
echo ====================================================================
echo.

:: Verificar que cloudflared exista
where cloudflared >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] cloudflared no esta instalado.
    echo Ejecuta en PowerShell:
    echo   winget install Cloudflare.cloudflared
    echo.
    pause
    exit /b 1
)

:: Iniciar el servidor web en segundo plano
echo [1/2] Iniciando servidor GestPro en puerto 8000...
start /B python web_server.py --port 8000

:: Esperar a que el servidor arranque
timeout /t 3 /nobreak >nul

:: Verificar que el servidor este corriendo
python -c "import socket; s=socket.socket(); s.settimeout(2); r=s.connect_ex(('127.0.0.1',8000)); s.close(); exit(0 if r==0 else 1)" >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] El servidor no pudo iniciar en el puerto 8000.
    echo Verifica que no haya otro programa usando ese puerto.
    pause
    exit /b 1
)
echo [OK] Servidor GestPro activo en http://localhost:8000
echo.

:: Crear el tunel con Cloudflare
echo [2/2] Creando tunel seguro con Cloudflare...
echo.
echo ====================================================================
echo   Espera unos segundos. Aparecera una linea que dice:
echo.
echo     https://XXXXXX.trycloudflare.com
echo.
echo   Copia ese enlace y abrelo en tu celular desde CUALQUIER lugar.
echo   Funciona con datos moviles, otra red Wi-Fi, etc.
echo ====================================================================
echo.
cloudflared tunnel --url http://localhost:8000
