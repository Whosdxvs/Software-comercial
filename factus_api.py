"""
factus_api.py — Cliente para la API REST de Factus
Proveedor Tecnológico de Facturación Electrónica en Colombia (DIAN).

Este módulo encapsula:
  - Autenticación OAuth2 (grant_type=password)
  - Creación y validación de facturas electrónicas
  - Mapeo de métodos de pago internos → códigos DIAN
"""
import json
import time
import logging
import requests

log = logging.getLogger("GestPro.Factus")

# ── URLs de la API ────────────────────────────────────────────
SANDBOX_URL    = "https://api-sandbox.factus.com.co"
PRODUCTION_URL = "https://api.factus.com.co"

# ── Mapeo de formas de pago internas → códigos DIAN ──────────
PAYMENT_METHOD_MAP = {
    "efectivo":      "10",   # Efectivo
    "tarjeta":       "48",   # Tarjeta de crédito
    "transferencia": "47",   # Transferencia débito bancaria
    "crédito":       "10",   # Por defecto efectivo
    "otro":          "10",   # Por defecto efectivo
    "mixto":         "10",   # Por defecto efectivo
}

# ── Códigos de tipo de documento de identidad ─────────────────
DOC_TYPE_MAP = {
    "CC":  "13",  # Cédula de ciudadanía
    "NIT": "31",  # NIT
    "CE":  "22",  # Cédula de extranjería
    "PP":  "41",  # Pasaporte
    "TI":  "12",  # Tarjeta de identidad
}


class FactusClient:
    """
    Cliente para comunicarse con la API de Factus.
    Maneja autenticación, cache de token y envío de facturas.
    """

    def __init__(self, db):
        """
        Inicializa el cliente leyendo las credenciales de la tabla config de la BD.

        Parámetros esperados en config:
          - factus_client_id
          - factus_client_secret
          - factus_username       (email registrado en Factus)
          - factus_password
          - factus_numbering_range_id
          - factus_environment    ('sandbox' o 'production')
        """
        self.db = db
        self._token = None
        self._token_expires_at = 0

        # Leer credenciales desde la BD
        self.client_id            = db.cfg("factus_client_id")
        self.client_secret        = db.cfg("factus_client_secret")
        self.username             = db.cfg("factus_username")
        self.password             = db.cfg("factus_password")
        self.municipality_code    = db.cfg("factus_municipality_code") or "68001"
        try:
            self.numbering_range_id = int(db.cfg("factus_numbering_range_id") or "0")
        except (ValueError, TypeError):
            self.numbering_range_id = 0

        # Determinar entorno (sandbox por defecto)
        env = db.cfg("factus_environment") or "sandbox"
        self.base_url = PRODUCTION_URL if env == "production" else SANDBOX_URL

    def is_configured(self) -> bool:
        """Verifica si las credenciales mínimas están configuradas."""
        return all([
            self.client_id,
            self.client_secret,
            self.username,
            self.password,
            self.numbering_range_id > 0,
        ])

    # ─────────────────────────────────────────────────────────
    # Autenticación OAuth2
    # ─────────────────────────────────────────────────────────
    def _authenticate(self):
        """
        Obtiene un access_token mediante OAuth2 (grant_type=password).
        El token se cachea hasta que expire (~60 minutos).
        """
        if self._token and time.time() < self._token_expires_at:
            return

        url = f"{self.base_url}/oauth/token"
        payload = {
            "grant_type":    "password",
            "client_id":     self.client_id,
            "client_secret": self.client_secret,
            "username":      self.username,
            "password":      self.password,
        }

        log.info("Autenticando con Factus API...")
        resp = requests.post(url, data=payload, timeout=30)

        if resp.status_code != 200:
            error_detail = resp.text[:500]
            raise FactusError(
                f"Error de autenticación con Factus (HTTP {resp.status_code}).\n"
                f"Verifica tus credenciales en Configuración → Facturación Electrónica.\n"
                f"Detalle: {error_detail}"
            )

        data = resp.json()
        self._token = data.get("access_token")
        expires_in = data.get("expires_in", 3600)
        self._token_expires_at = time.time() + expires_in - 300  # 5 min de margen
        log.info("Autenticación con Factus exitosa.")

    def _headers(self) -> dict:
        """Retorna los headers necesarios para las peticiones autenticadas."""
        self._authenticate()
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }

    # ─────────────────────────────────────────────────────────
    # Crear y validar factura electrónica
    # ─────────────────────────────────────────────────────────
    def crear_factura(self, sale_id, items, calc, customer_data, reference_code):
        """
        Envía una factura electrónica a la DIAN a través de Factus.

        Parámetros:
            sale_id       : int — ID de la venta en la BD local
            items         : lista de dicts con los ítems de la venta
                            (product_id, product_name, quantity, unit_price, subtotal)
            calc          : dict con {sub, disc, iva, total}
            customer_data : dict con {doc_type, identification, name, email}
            reference_code: str — identificador único (número de factura local)

        Retorna:
            dict con {cufe, number, pdf_url, status, message}
        """
        if not self.is_configured():
            raise FactusError(
                "Las credenciales de Factus no están configuradas.\n"
                "Ve a Configuración → Facturación Electrónica y completa los datos."
            )

        # ── Construir ítems para Factus ──
        factus_items = []
        for item in items:
            qty   = float(item.get("quantity", 1))
            price = float(item.get("unit_price", 0))
            tax_rate = "19.00" if calc.get("iva", 0) > 0 else "0.00"

            factus_items.append({
                "code_reference":  str(item.get("product_id", "PROD")),
                "name":            item.get("product_name", "Producto")[:100],
                "quantity":        f"{qty:.2f}",
                "discount_rate":   "0.00",
                "price":           f"{price:.2f}",
                "unit_measure_code": "94",   # unidad
                "standard_code":     "999",
                "taxes": [{"code": "01", "rate": tax_rate}]
            })

        # ── Datos del cliente ──
        doc_type  = customer_data.get("doc_type", "CC")
        id_code   = DOC_TYPE_MAP.get(doc_type, "13")
        legal_org = "1" if doc_type == "NIT" else "2"

        customer_payload = {
            "identification_document_code": id_code,
            "identification": customer_data.get("identification", "222222222222"),
            "address":  customer_data.get("address", "calle 1 # 1-1") or "calle 1 # 1-1",
            "email":    customer_data.get("email", "consumidor@final.com"),
            "phone":    customer_data.get("phone", "0000000000") or "0000000000",
            "legal_organization_code": legal_org,
            "tribute_code":  "ZZ",
            "municipality_code": self.municipality_code,
        }
        name_val = customer_data.get("name", "Consumidor Final")
        if legal_org == "1":
            customer_payload["company"]    = name_val
            customer_payload["trade_name"] = name_val
        else:
            customer_payload["names"] = name_val

        # ── Método de pago ──
        pay_internal = customer_data.get("payment_method", "efectivo").lower()
        pay_code     = PAYMENT_METHOD_MAP.get(pay_internal, "10")
        due_date     = time.strftime("%Y-%m-%d")

        # ── JSON completo ──
        factura_json = {
            "reference_code":       reference_code,
            "document":             "01",
            "numbering_range_id":   self.numbering_range_id,
            "operation_type":       "10",
            "send_email":           True,
            "payment_details": [{
                "payment_form":        1,
                "payment_method_code": pay_code,
                "reference_code":      f"pago-{reference_code}",
                "amount":              f"{calc.get('total', 0):.2f}",
                "due_date":            due_date,
            }],
            "cash_rounding_amount": "0.00",
            "observation":          f"Venta #{sale_id} — GestPro",
            "customer":             customer_payload,
            "items":                factus_items,
        }

        # ── Enviar a Factus ──
        url = f"{self.base_url}/v2/bills/validate"
        log.info(f"Enviando factura electrónica a Factus: {reference_code}")

        try:
            resp = requests.post(url, json=factura_json, headers=self._headers(), timeout=60)
        except requests.ConnectionError:
            raise FactusError(
                "No se pudo conectar con el servidor de Factus.\n"
                "Verifica tu conexión a internet."
            )
        except requests.Timeout:
            raise FactusError(
                "La solicitud a Factus tardó demasiado.\n"
                "Intenta de nuevo en unos segundos."
            )

        # ── Procesar respuesta ──
        if resp.status_code in (200, 201):
            data = resp.json()
            bill = data.get("data", data.get("bill", data))
            cufe    = bill.get("cufe", "")
            number  = bill.get("number", reference_code)
            pdf_url = bill.get("pdf_url", bill.get("public_url", ""))
            log.info(f"✅ Factura electrónica emitida: {number} | CUFE: {cufe[:20]}...")
            return {
                "cufe":    cufe,
                "number":  number,
                "pdf_url": pdf_url,
                "status":  "success",
                "message": f"Factura {number} emitida exitosamente ante la DIAN.",
            }
        else:
            try:
                error_data = resp.json()
                detail = json.dumps(error_data, indent=2, ensure_ascii=False)
            except Exception:
                detail = resp.text[:500]
            log.error(f"Payload enviado: {json.dumps(factura_json, indent=2)}")
            log.error(f"Respuesta API: {detail}")
            raise FactusError(
                f"Error al emitir factura electrónica (HTTP {resp.status_code}):\n{detail}"
            )


class FactusError(Exception):
    """Excepción personalizada para errores de la API de Factus."""
    pass

