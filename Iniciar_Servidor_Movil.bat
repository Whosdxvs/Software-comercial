@echo off
title Servidor GestPro Movil y Web
color 0A
cls
echo ====================================================================
echo               GESTPRO COMERCIAL - SERVIDOR MOVIL & WEB
echo ====================================================================
echo.
echo   Conecta tu celular a la misma red Wi-Fi de esta computadora.
echo   Al iniciar veras la direccion IP y el codigo QR para escanear.
echo.
echo ====================================================================
echo.
python web_server.py
echo.
pause
