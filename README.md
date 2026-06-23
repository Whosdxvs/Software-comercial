# GestionPro v2.0

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
    GENERADOR DE LICENCIAS -- GestionPro v2.0
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
  al abrir GestionPro por primera vez.
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

## ARCHIVOS IMPORTANTES

| Archivo | Descripcion |
|---|---|
| `Software.py` | Codigo fuente principal |
| `generar_licencia.py` | Script privado del desarrollador (NO en repo) |
| `gestionpro.db` | Base de datos SQLite del cliente (NO en repo) |
| `.venv/` | Entorno virtual Python (NO en repo) |
