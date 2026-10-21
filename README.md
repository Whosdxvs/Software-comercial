# GestPro v2.0

## FLUJO DE DESARROLLO

### Subir cambios al repositorio
```
git add .
git commit -m "Explicacion corta de lo que programaste"
git push origin main
```

### Bajar cambios del otro
```
git pull origin main
```

---

## DISTRIBUCION DEL .EXE

El `.exe` no necesita setup. Se pasa el archivo a la otra persona y queda funcionando con una base de datos en blanco para que empiece a trabajar.

> **IMPORTANTE:** El `.exe` ya **no incluye** el archivo `licencia.dat`. Al abrirlo por primera vez le pedira al cliente que ingrese su **llave de licencia**.

---

## PASOS PARA ACTUALIZAR EL .EXE

1. Eliminar las carpetas `dist/` y `build/`
2. Ejecutar:
```
pyinstaller --onefile --windowed --collect-data escpos Software.py
```

---

## SISTEMA DE LICENCIAS (Key de uso unico)

El nuevo sistema usa **llaves Base64 firmadas criptograficamente** almacenadas en la base de datos del cliente. Cada llave es de **uso unico** — una vez activada en una instalacion, queda vinculada a ella.

### Como funciona

1. El desarrollador genera una llave con `generar_licencia.py` (script privado, **no esta en el repo**).
2. Se entrega la llave al cliente (WhatsApp, correo, etc.).
3. Al abrir el programa por primera vez (o si la licencia expiro), aparece la ventana de activacion.
4. El cliente pega la llave y presiona **Activar Software**.
5. La llave queda guardada en la base de datos. Ya no se pide de nuevo.

### Como generar una llave

Ejecutar en la carpeta del proyecto (solo el desarrollador tiene este script):
```
python generar_licencia.py
```

Aparecera el menu:
```
========================================================
    GENERADOR DE LICENCIAS -- GestPro v2.0
========================================================
  1. Licencia de 30 dias
  2. Licencia de 90 dias
  3. Licencia de 365 dias
  4. Licencia PERMANENTE
  5. Licencia personalizada (dias)
  0. Salir
========================================================
```

Seleccionar la opcion deseada. El programa imprimira la llave generada, por ejemplo:
```
**********************************************************
  LLAVE GENERADA -- PERMANENTE
**********************************************************

eyJpZCI6ImY4N2Q4ZWEyIiwiY3JlYXRlZF9hdCI6IjIwMjYtMDYt
MjIiLCJwZXJtYW5lbnQiOnRydWV9fGYwMDkzYzhiOWVhMzNiOWM2
Zjk4Y2RhOWExY2RiNjFmNmQ3ZjFiYzg5ZjA5NGVkNjQzMTc1MjVk
MmFjM2ExOTA=

**********************************************************

  Copia esta llave y entregasela al cliente.
  El cliente la pega en la ventana de activacion
  al abrir GestPro por primera vez.
```

### Tipos de licencia

| Tipo | Descripcion |
|---|---|
| 30 dias | Licencia de prueba o mensual |
| 90 dias | Licencia trimestral |
| 365 dias | Licencia anual |
| Permanente | Sin fecha de vencimiento |
| Personalizada | N dias definidos por el desarrollador |

### Seguridad

- Las llaves estan firmadas con **HMAC-SHA256** — no pueden falsificarse sin la clave secreta.
- Proteccion **anti-manipulacion de reloj**: si el cliente atrasa la fecha del sistema, la licencia se bloquea automaticamente.
- El archivo `generar_licencia.py` **nunca** debe compartirse ni subirse al repositorio.
- La clave secreta solo existe en el codigo fuente privado del desarrollador.

---

## ACCESO MÓVIL Y WEB (Celular y Tablet)

GestPro cuenta con un servidor web y aplicación móvil integrada que permite acceder desde cualquier smartphone en el navegador web (Safari, Chrome, etc.):

- **Analíticas en vivo**: Métricas de ventas, ganancias netas, margen operativo, gráficos de tendencia y top productos.
- **Punto de Venta Móvil (POS)**: Catálogo táctil, carrito interactivo, cálculo de cambio, cobros en efectivo/tarjeta/transferencia/crédito, y comprobante digital con botón de envío directo a **WhatsApp**.
- **Lector de Código de Barras**: Escanea productos directamente con la cámara del celular.
- **Control de Caja**: Consulta de saldo esperado en tiempo real, arqueo, ingresos, retiros y apertura/cierre de turnos.
- **Inventario & Clientes**: Ajuste de stock rápido, alertas de stock mínimo, gestión de deudas y abonos.

### Cómo iniciar el servidor móvil:

1. **Opción 1 (Doble Clic)**: Ejecutar el archivo `Iniciar_Servidor_Movil.bat`.
2. **Opción 2 (Desde la App de Escritorio)**: Abrir GestPro en PC e ir a la pestaña **📱 Acceso Móvil**, donde verás el estado y el código QR listo para escanear.
3. **Opción 3 (Comando)**:
   ```bash
   python web_server.py
   ```

Apunta la cámara de tu celular al código QR mostrado o abre la dirección IP que aparece (ej: `http://192.168.1.5:8000`) estando conectado al mismo Wi-Fi.

> **Tip:** En tu celular puedes pulsar en las opciones del navegador **"Agregar a pantalla de inicio"** para usar GestPro como una app móvil a pantalla completa.

---

## ARCHIVOS IMPORTANTES

| Archivo | Descripcion |
|---|---|
| `Software.py` | Codigo fuente principal de escritorio |
| `web_server.py` | Servidor backend FastAPI para acceso móvil y web |
| `web/` | Aplicacion web SPA (HTML, CSS moderno, JS, PWA) |
| `Iniciar_Servidor_Movil.bat` | Acceso directo para iniciar el servidor movil |
| `generar_licencia.py` | Script privado del desarrollador (NO en repo) |
| `GestPro.db` | Base de datos SQLite del cliente (NO en repo) |
| `.venv/` | Entorno virtual Python (NO en repo) |


