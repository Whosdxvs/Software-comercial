#!/usr/bin/env python3
"""
GestPro MÃ³vil & Web Server
Servidor HTTP / REST API para acceso mÃ³vil y web a GestPro Comercial.
Compatible al 100% con la base de datos GestPro.db.
"""

import os
import sys
import socket
import sqlite3
import hashlib
import json
import base64
import io
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List, Dict, Any

# Zona horaria local: UTC-5 (Colombia / Venezuela / Ecuador / PerÃº)
TZ_LOCAL = timezone(timedelta(hours=-5))

def local_now() -> datetime:
    """Retorna la hora actual en la zona horaria local (UTC-5)."""
    return datetime.now(timezone.utc).astimezone(TZ_LOCAL).replace(tzinfo=None)

from fastapi import FastAPI, HTTPException, Request, Depends, Query, status
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import qrcode

# Asegurar codificaciÃ³n UTF-8 en consola de Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# â”€â”€ ConfiguraciÃ³n de Rutas y Base de Datos â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "GestPro.db"))
WEB_DIR = os.path.join(BASE_DIR, "web")

TURSO_DATABASE_URL = os.environ.get("TURSO_DATABASE_URL")
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN")

def get_db():
    """Retorna conexiÃ³n a Turso Cloud si estÃ¡ configurado, o a SQLite local por defecto."""
    if TURSO_DATABASE_URL and TURSO_AUTH_TOKEN:
        try:
            from turso_db import TursoConnection
            return TursoConnection(TURSO_DATABASE_URL, TURSO_AUTH_TOKEN)
        except Exception as e:
            print(f"[Aviso] No se pudo conectar a Turso ({e}), usando base local.")
            
    con = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA busy_timeout = 5000")
    con.execute("PRAGMA foreign_keys = ON")
    return con

def init_db_schema():
    """Inicializa la base de datos con tablas, migraciones y usuario admin si no existen."""
    db_dir = os.path.dirname(os.path.abspath(DB_PATH))
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
        
    con = get_db()
    try:
        tables = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
        if not tables:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'vendedor', active INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL, sku INTEGER UNIQUE,
                barcode TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT 'General',
                price REAL NOT NULL DEFAULT 0, cost REAL NOT NULL DEFAULT 0,
                supplier TEXT NOT NULL DEFAULT '', stock INTEGER NOT NULL DEFAULT 0,
                min_stock INTEGER NOT NULL DEFAULT 5, unit TEXT NOT NULL DEFAULT 'unidad',
                active INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL, document TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '',
                address TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
                debt REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (date('now')));
            CREATE TABLE IF NOT EXISTS cash_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                opened_at TEXT NOT NULL, closed_at TEXT,
                initial_cash REAL NOT NULL DEFAULT 0,
                actual_cash REAL DEFAULT 0, expected_cash REAL DEFAULT 0, difference REAL DEFAULT 0, notes TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'open');
            CREATE TABLE IF NOT EXISTS cash_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL REFERENCES cash_sessions(id) ON DELETE CASCADE,
                type TEXT NOT NULL, amount REAL NOT NULL,
                description TEXT NOT NULL, timestamp TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER REFERENCES clients(id),
                user_id INTEGER REFERENCES users(id),
                session_id INTEGER REFERENCES cash_sessions(id),
                date TEXT NOT NULL DEFAULT (date('now')),
                time TEXT NOT NULL DEFAULT (time('now')),
                subtotal REAL NOT NULL DEFAULT 0, discount REAL NOT NULL DEFAULT 0,
                total REAL NOT NULL DEFAULT 0,
                payment_method TEXT NOT NULL DEFAULT 'efectivo',
                notes TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS sale_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
                product_id INTEGER REFERENCES products(id),
                product_name TEXT NOT NULL, quantity REAL NOT NULL,
                unit_price REAL NOT NULL, subtotal REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS client_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id),
                session_id INTEGER REFERENCES cash_sessions(id),
                amount REAL NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                timestamp TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                session_id INTEGER REFERENCES cash_sessions(id),
                date TEXT NOT NULL DEFAULT (date('now')),
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                timestamp TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id INTEGER REFERENCES sales(id),
                invoice_num TEXT NOT NULL DEFAULT '',
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                subtotal REAL NOT NULL DEFAULT 0,
                discount REAL NOT NULL DEFAULT 0,
                tax_iva REAL NOT NULL DEFAULT 0,
                total REAL NOT NULL DEFAULT 0,
                payment_method TEXT NOT NULL DEFAULT 'efectivo',
                cufe TEXT NOT NULL DEFAULT '',
                pdf_url TEXT NOT NULL DEFAULT '',
                dian_status TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS pos_locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                address TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS pos_inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                location_id INTEGER NOT NULL REFERENCES pos_locations(id),
                product_id INTEGER NOT NULL REFERENCES products(id),
                stock INTEGER NOT NULL DEFAULT 0,
                UNIQUE(location_id, product_id));
            CREATE TABLE IF NOT EXISTS inventory_transfers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_location_id INTEGER NOT NULL REFERENCES pos_locations(id),
                to_location_id INTEGER NOT NULL REFERENCES pos_locations(id),
                product_id INTEGER NOT NULL REFERENCES products(id),
                quantity INTEGER NOT NULL,
                user_id INTEGER NOT NULL REFERENCES users(id),
                timestamp TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '');
            """)
            con.commit()

            con.execute("INSERT OR IGNORE INTO config VALUES('business_name', 'Mi Negocio')")
            con.execute("INSERT OR IGNORE INTO config VALUES('currency_symbol', '$')")
            con.execute("INSERT OR IGNORE INTO config VALUES('tax_percent', '0')")
            con.execute(
                "INSERT OR IGNORE INTO users(username,password,role) VALUES(?,?,?)",
                ("admin", hash_pw("admin123"), "admin")
            )
            con.execute("INSERT OR IGNORE INTO pos_locations(name, address, phone) VALUES('Principal', '', '')")
            for cat in ["General", "ElectrÃ³nica", "Ropa", "Alimentos", "Hogar", "Bebidas", "Salud"]:
                con.execute("INSERT OR IGNORE INTO categories(name) VALUES(?)", (cat,))
            con.commit()

        migrations = [
            ("sales", "session_id", "INTEGER REFERENCES cash_sessions(id)"),
            ("sales", "discount", "REAL NOT NULL DEFAULT 0"),
            ("sales", "subtotal", "REAL NOT NULL DEFAULT 0"),
            ("sale_items", "product_id", "INTEGER REFERENCES products(id)"),
            ("products", "min_stock", "INTEGER NOT NULL DEFAULT 5"),
            ("products", "unit", "TEXT NOT NULL DEFAULT 'unidad'"),
            ("cash_sessions", "actual_cash", "REAL DEFAULT 0"),
            ("cash_sessions", "expected_cash", "REAL DEFAULT 0"),
            ("cash_sessions", "difference", "REAL DEFAULT 0"),
            ("cash_sessions", "notes", "TEXT NOT NULL DEFAULT ''"),
            ("clients", "debt", "REAL NOT NULL DEFAULT 0"),
            ("invoices", "cufe", "TEXT NOT NULL DEFAULT ''"),
            ("invoices", "pdf_url", "TEXT NOT NULL DEFAULT ''"),
            ("invoices", "dian_status", "TEXT NOT NULL DEFAULT ''"),
            ("sales", "location_id", "INTEGER REFERENCES pos_locations(id)"),
            ("cash_sessions", "location_id", "INTEGER REFERENCES pos_locations(id)"),
            ("expenses", "location_id", "INTEGER REFERENCES pos_locations(id)"),
        ]
        for table, col, defn in migrations:
            try:
                cols = {r["name"] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}
                if col not in cols:
                    con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {defn}")
                    con.commit()
            except Exception:
                pass
    finally:
        con.close()

# Ejecutar inicializaciÃ³n al cargar
try:
    init_db_schema()
except Exception as e:
    print("Aviso al inicializar base de datos:", e)

def get_lan_ip() -> str:
    """Detecta la IP local de la mÃ¡quina en la red Wi-Fi / LAN."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

# â”€â”€ Inicializar FastAPI â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
app = FastAPI(
    title="GestPro MÃ³vil API",
    description="Backend web y mÃ³vil para el sistema GestPro",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# â”€â”€ Modelos Pydantic â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class LoginRequest(BaseModel):
    username: str
    password: str

class SaleItemRequest(BaseModel):
    product_id: int
    product_name: str
    quantity: float
    unit_price: float
    subtotal: float

class CreateSaleRequest(BaseModel):
    client_id: Optional[int] = None
    items: List[SaleItemRequest]
    discount: float = 0.0
    payment_method: str = "efectivo"
    notes: Optional[str] = ""
    session_id: Optional[int] = None
    cash_received: Optional[float] = 0.0

class ProductCreateRequest(BaseModel):
    name: str
    sku: Optional[int] = None
    barcode: Optional[str] = ""
    category: Optional[str] = "General"
    price: float
    cost: float = 0.0
    supplier: Optional[str] = ""
    stock: int = 0
    min_stock: int = 5
    unit: Optional[str] = "unidad"

class ProductUpdateRequest(BaseModel):
    name: str
    sku: Optional[int] = None
    barcode: Optional[str] = ""
    category: Optional[str] = "General"
    price: float
    cost: float = 0.0
    supplier: Optional[str] = ""
    stock: int = 0
    min_stock: int = 5
    unit: Optional[str] = "unidad"

class StockAdjustmentRequest(BaseModel):
    delta: int
    notes: Optional[str] = ""

class ClientCreateRequest(BaseModel):
    name: str
    document: Optional[str] = ""
    phone: Optional[str] = ""
    email: Optional[str] = ""
    address: Optional[str] = ""
    notes: Optional[str] = ""

class ClientPaymentRequest(BaseModel):
    amount: float
    notes: Optional[str] = ""

class OpenCashRequest(BaseModel):
    initial_cash: float
    notes: Optional[str] = ""

class CloseCashRequest(BaseModel):
    actual_cash: float
    notes: Optional[str] = ""

class CashTransactionRequest(BaseModel):
    type: str  # income o outcome
    amount: float
    description: str

class ExpenseCreateRequest(BaseModel):
    category: str
    amount: float
    description: Optional[str] = ""
    affect_cash: bool = True

class CategoryCreateRequest(BaseModel):
    name: str

# â”€â”€ Helper de AutenticaciÃ³n BÃ¡sica â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def get_current_user_from_header(request: Request) -> Dict[str, Any]:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        # Permitir fallback a usuario admin por defecto si no hay token o si se usa sesiÃ³n rÃ¡pida
        con = get_db()
        user = con.execute("SELECT id, username, role FROM users WHERE active=1 ORDER BY id LIMIT 1").fetchone()
        con.close()
        if user:
            return dict(user)
        raise HTTPException(status_code=401, detail="No autorizado")
    
    token = auth.replace("Bearer ", "").strip()
    try:
        data = json.loads(base64.b64decode(token).decode("utf-8"))
        con = get_db()
        user = con.execute("SELECT id, username, role FROM users WHERE id=? AND active=1", (data.get("id"),)).fetchone()
        con.close()
        if not user:
            raise HTTPException(status_code=401, detail="Usuario no encontrado o inactivo")
        return dict(user)
    except Exception:
        raise HTTPException(status_code=401, detail="Token invÃ¡lido")

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# RUTAS API: AUTENTICACIÃ“N
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
@app.post("/api/auth/login")
def login(req: LoginRequest):
    u = req.username.strip().lower()
    p = req.password.strip()
    con = get_db()
    row = con.execute("SELECT id, username, role FROM users WHERE username=? AND password=? AND active=1",
                      (u, hash_pw(p))).fetchone()
    con.close()
    if not row:
        raise HTTPException(status_code=400, detail="Usuario o contraseÃ±a incorrectos")
    user_dict = dict(row)
    token = base64.b64encode(json.dumps(user_dict).encode("utf-8")).decode("utf-8")
    return {"token": token, "user": user_dict}

@app.get("/api/auth/me")
def me(user: Dict[str, Any] = Depends(get_current_user_from_header)):
    return {"user": user}

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# RUTAS API: CONFIGURACIÃ“N & ESTADO
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
@app.get("/api/config")
def get_config():
    con = get_db()
    rows = con.execute("SELECT key, value FROM config").fetchall()
    con.close()
    cfg = {r["key"]: r["value"] for r in rows}
    return {
        "business_name": cfg.get("business_name", "GestPro Comercial"),
        "business_type": cfg.get("business_type", "Comercio"),
        "currency_symbol": cfg.get("currency_symbol", "$"),
        "currency_code": cfg.get("currency_code", "COP"),
        "phone": cfg.get("phone", ""),
        "address": cfg.get("address", ""),
        "invoice_prefix": cfg.get("invoice_prefix", "FAC"),
    }

@app.get("/api/system/network-info")
def get_network_info(port: int = 8000):
    lan_ip = get_lan_ip()
    url = f"http://{lan_ip}:{port}"
    
    # Generar QR en base64
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")
    
    return {
        "lan_ip": lan_ip,
        "port": port,
        "url": url,
        "qr_base64": qr_b64,
        "server_time": local_now().strftime("%Y-%m-%d %H:%M:%S")
    }

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# RUTAS API: DASHBOARD & ANALÃTICAS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
@app.get("/api/dashboard/stats")
def get_dashboard_stats(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    today = date.today().isoformat()
    d1 = start_date or today
    d2 = end_date or today
    
    con = get_db()
    # Ventas, ingresos, descuentos
    row_sales = con.execute(
        "SELECT COUNT(*) cnt, COALESCE(SUM(total),0) revenue, COALESCE(SUM(discount),0) disc FROM sales WHERE date BETWEEN ? AND ?",
        (d1, d2)
    ).fetchone()
    
    # Ganancia bruta estimada (Precio de venta - Costo de compra) - Descuentos
    row_profit = con.execute(
        """SELECT COALESCE(SUM(si.subtotal - si.quantity * COALESCE(p.cost, 0)), 0) profit
           FROM sale_items si JOIN sales s ON si.sale_id = s.id
           LEFT JOIN products p ON si.product_id = p.id
           WHERE s.date BETWEEN ? AND ?""",
        (d1, d2)
    ).fetchone()
    gross_profit = float(row_profit["profit"]) if row_profit else 0.0
    discount = float(row_sales["disc"]) if row_sales else 0.0
    net_profit = gross_profit - discount
    
    # Gastos
    row_exp = con.execute(
        "SELECT COALESCE(SUM(amount),0) total FROM expenses WHERE date BETWEEN ? AND ?",
        (d1, d2)
    ).fetchone()
    total_expenses = float(row_exp["total"]) if row_exp else 0.0
    
    # Ganancia final neta (Ganancia ventas - Gastos)
    operating_profit = net_profit - total_expenses
    
    # Productos en alerta de stock bajo
    row_low = con.execute(
        "SELECT COUNT(*) cnt FROM products WHERE active=1 AND stock <= min_stock"
    ).fetchone()
    low_stock_count = int(row_low["cnt"]) if row_low else 0
    
    # Valor del inventario
    row_inv = con.execute(
        "SELECT COALESCE(SUM(price * stock),0) venta, COALESCE(SUM(cost * stock),0) costo FROM products WHERE active=1"
    ).fetchone()
    
    con.close()
    
    sales_cnt = int(row_sales["cnt"]) if row_sales else 0
    revenue = float(row_sales["revenue"]) if row_sales else 0.0
    avg_ticket = (revenue / sales_cnt) if sales_cnt > 0 else 0.0
    
    return {
        "start_date": d1,
        "end_date": d2,
        "sales_count": sales_cnt,
        "revenue": revenue,
        "discount": discount,
        "net_profit": net_profit,
        "expenses": total_expenses,
        "operating_profit": operating_profit,
        "avg_ticket": avg_ticket,
        "low_stock_count": low_stock_count,
        "inventory_value_sell": float(row_inv["venta"]) if row_inv else 0.0,
        "inventory_value_cost": float(row_inv["costo"]) if row_inv else 0.0,
    }

@app.get("/api/dashboard/charts")
def get_dashboard_charts(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    today = date.today()
    d1 = start_date or (today - timedelta(days=6)).isoformat()
    d2 = end_date or today.isoformat()
    
    con = get_db()
    
    # Ventas por dÃ­a
    sales_days = con.execute(
        "SELECT date, COALESCE(SUM(total),0) rev, COUNT(*) cnt FROM sales WHERE date BETWEEN ? AND ? GROUP BY date ORDER BY date",
        (d1, d2)
    ).fetchall()
    
    # Ventas por mÃ©todo de pago
    sales_payments = con.execute(
        "SELECT payment_method pm, COALESCE(SUM(total),0) total, COUNT(*) cnt FROM sales WHERE date BETWEEN ? AND ? GROUP BY payment_method",
        (d1, d2)
    ).fetchall()
    
    # Ventas por categorÃ­a
    sales_cats = con.execute(
        """SELECT COALESCE(p.category, 'General') cat, SUM(si.subtotal) rev, SUM(si.quantity) qty
           FROM sale_items si JOIN sales s ON si.sale_id = s.id
           LEFT JOIN products p ON si.product_id = p.id
           WHERE s.date BETWEEN ? AND ?
           GROUP BY cat ORDER BY rev DESC LIMIT 8""",
        (d1, d2)
    ).fetchall()
    
    # Top 10 productos mÃ¡s vendidos
    top_prods = con.execute(
        """SELECT si.product_name pname, SUM(si.quantity) qty, SUM(si.subtotal) rev
           FROM sale_items si JOIN sales s ON si.sale_id = s.id
           WHERE s.date BETWEEN ? AND ?
           GROUP BY si.product_name ORDER BY qty DESC LIMIT 10""",
        (d1, d2)
    ).fetchall()
    
    con.close()
    
    return {
        "by_day": [dict(r) for r in sales_days],
        "by_payment": [dict(r) for r in sales_payments],
        "by_category": [dict(r) for r in sales_cats],
        "top_products": [dict(r) for r in top_prods]
    }

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# RUTAS API: PRODUCTOS & CATEGORÃAS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
@app.get("/api/products")
def get_products(
    search: Optional[str] = "",
    category: Optional[str] = "",
    low_stock_only: bool = False,
    limit: int = 100,
    offset: int = 0
):
    con = get_db()
    p = []
    q = "SELECT * FROM products WHERE active=1"
    if search:
        s = f"%{search}%"
        q += " AND (name LIKE ? OR CAST(sku AS TEXT) LIKE ? OR barcode LIKE ? OR supplier LIKE ?)"
        p += [s, s, s, s]
    if category and category not in ("Todas", ""):
        q += " AND category=?"
        p.append(category)
    if low_stock_only:
        q += " AND stock <= min_stock"
        
    q += " ORDER BY name LIMIT ? OFFSET ?"
    p += [limit, offset]
    
    rows = con.execute(q, p).fetchall()
    
    # Total de productos que cumplen la condiciÃ³n
    count_q = "SELECT COUNT(*) cnt FROM products WHERE active=1"
    cp = []
    if search:
        s = f"%{search}%"
        count_q += " AND (name LIKE ? OR CAST(sku AS TEXT) LIKE ? OR barcode LIKE ? OR supplier LIKE ?)"
        cp += [s, s, s, s]
    if category and category not in ("Todas", ""):
        count_q += " AND category=?"
        cp.append(category)
    if low_stock_only:
        count_q += " AND stock <= min_stock"
    total_cnt = con.execute(count_q, cp).fetchone()["cnt"]
    
    con.close()
    return {"products": [dict(r) for r in rows], "total": total_cnt}

@app.get("/api/products/by-barcode/{code}")
def get_product_by_barcode(code: str):
    con = get_db()
    # Buscar por barcode exacto o por SKU
    row = con.execute(
        "SELECT * FROM products WHERE active=1 AND (barcode=? OR CAST(sku AS TEXT)=?) LIMIT 1",
        (code.strip(), code.strip())
    ).fetchone()
    con.close()
    if not row:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return dict(row)

@app.get("/api/products/{id}")
def get_product(id: int):
    con = get_db()
    row = con.execute("SELECT * FROM products WHERE id=? AND active=1", (id,)).fetchone()
    con.close()
    if not row:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return dict(row)

def generate_sku(con) -> int:
    import random
    used = {r["sku"] for r in con.execute("SELECT sku FROM products WHERE sku IS NOT NULL").fetchall()}
    while True:
        sku = random.randint(100000, 999999)
        if sku not in used:
            return sku

@app.post("/api/products")
def create_product(
    req: ProductCreateRequest,
    user: Dict[str, Any] = Depends(get_current_user_from_header)
):
    con = get_db()
    sku = req.sku if req.sku else generate_sku(con)
    cur = con.execute(
        """INSERT INTO products(name, sku, barcode, category, price, cost, supplier, stock, min_stock, unit, active)
           VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
        (req.name.strip(), int(sku), (req.barcode or "").strip(), req.category or "General",
         float(req.price), float(req.cost), (req.supplier or "").strip(),
         int(req.stock), int(req.min_stock), req.unit or "unidad")
    )
    prod_id = cur.lastrowid
    
    # Sincronizar pos_inventory para la sede principal si existe
    loc = con.execute("SELECT id FROM pos_locations WHERE active=1 ORDER BY id LIMIT 1").fetchone()
    if loc and int(req.stock) > 0:
        con.execute(
            """INSERT INTO pos_inventory(location_id, product_id, stock) VALUES(?,?,?)
               ON CONFLICT(location_id, product_id) DO UPDATE SET stock=stock+?""",
            (loc["id"], prod_id, int(req.stock), int(req.stock))
        )
    con.commit()
    prod = con.execute("SELECT * FROM products WHERE id=?", (prod_id,)).fetchone()
    con.close()
    return dict(prod)

@app.put("/api/products/{id}")
def update_product(
    id: int,
    req: ProductUpdateRequest,
    user: Dict[str, Any] = Depends(get_current_user_from_header)
):
    con = get_db()
    sku = req.sku if req.sku else id
    con.execute(
        """UPDATE products SET name=?, sku=?, barcode=?, category=?, price=?, cost=?,
           supplier=?, stock=?, min_stock=?, unit=? WHERE id=?""",
        (req.name.strip(), int(sku), (req.barcode or "").strip(), req.category or "General",
         float(req.price), float(req.cost), (req.supplier or "").strip(),
         int(req.stock), int(req.min_stock), req.unit or "unidad", id)
    )
    con.commit()
    prod = con.execute("SELECT * FROM products WHERE id=?", (id,)).fetchone()
    con.close()
    return dict(prod)

@app.post("/api/products/{id}/adjust-stock")
def adjust_stock(
    id: int,
    req: StockAdjustmentRequest,
    user: Dict[str, Any] = Depends(get_current_user_from_header)
):
    con = get_db()
    con.execute("UPDATE products SET stock = stock + ? WHERE id=?", (req.delta, id))
    loc = con.execute("SELECT id FROM pos_locations WHERE active=1 ORDER BY id LIMIT 1").fetchone()
    if loc:
        con.execute(
            """INSERT INTO pos_inventory(location_id, product_id, stock) VALUES(?,?,?)
               ON CONFLICT(location_id, product_id) DO UPDATE SET stock=stock+?""",
            (loc["id"], id, req.delta, req.delta)
        )
    con.commit()
    prod = con.execute("SELECT * FROM products WHERE id=?", (id,)).fetchone()
    con.close()
    return dict(prod)

@app.get("/api/categories")
def get_categories():
    con = get_db()
    rows = con.execute("SELECT id, name FROM categories ORDER BY name").fetchall()
    con.close()
    return [dict(r) for r in rows]

@app.post("/api/categories")
def create_category(req: CategoryCreateRequest):
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="El nombre de la categorÃ­a es obligatorio")
    con = get_db()
    try:
        cur = con.execute("INSERT OR IGNORE INTO categories(name) VALUES(?)", (name,))
        con.commit()
        cat_id = cur.lastrowid
    finally:
        con.close()
    return {"id": cat_id, "name": name}

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# RUTAS API: CLIENTES
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
@app.get("/api/clients")
def get_clients(search: Optional[str] = ""):
    con = get_db()
    q = "SELECT * FROM clients"
    p = []
    if search:
        s = f"%{search}%"
        q += " WHERE name LIKE ? OR phone LIKE ? OR document LIKE ?"
        p = [s, s, s]
    q += " ORDER BY name"
    rows = con.execute(q, p).fetchall()
    con.close()
    return [dict(r) for r in rows]

@app.post("/api/clients")
def create_client(req: ClientCreateRequest):
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="El nombre del cliente es obligatorio")
    con = get_db()
    cur = con.execute(
        """INSERT INTO clients(name, document, phone, email, address, notes, debt, created_at)
           VALUES(?, ?, ?, ?, ?, ?, 0, ?)""",
        (name, req.document or "", req.phone or "", req.email or "", req.address or "",
         req.notes or "", date.today().isoformat())
    )
    cid = cur.lastrowid
    con.commit()
    row = con.execute("SELECT * FROM clients WHERE id=?", (cid,)).fetchone()
    con.close()
    return dict(row)

@app.post("/api/clients/{id}/payment")
def add_client_payment(
    id: int,
    req: ClientPaymentRequest,
    user: Dict[str, Any] = Depends(get_current_user_from_header)
):
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="El monto del abono debe ser mayor a 0")
    con = get_db()
    client = con.execute("SELECT * FROM clients WHERE id=?", (id,)).fetchone()
    if not client:
        con.close()
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
        
    # Buscar sesiÃ³n de caja abierta
    sess = con.execute("SELECT id FROM cash_sessions WHERE status='open' ORDER BY id DESC LIMIT 1").fetchone()
    sess_id = sess["id"] if sess else None
    
    now_str = local_now().strftime("%Y-%m-%d %H:%M:%S")
    con.execute(
        "INSERT INTO client_payments(client_id, user_id, session_id, amount, notes, timestamp) VALUES(?,?,?,?,?,?)",
        (id, user["id"], sess_id, req.amount, req.notes or "", now_str)
    )
    con.execute("UPDATE clients SET debt = debt - ? WHERE id=?", (req.amount, id))
    
    # Si hay sesiÃ³n de caja abierta, registrar ingreso
    if sess_id:
        desc = f"Abono cliente: {client['name']}"
        if req.notes:
            desc += f" ({req.notes})"
        con.execute(
            "INSERT INTO cash_transactions(session_id, type, amount, description, timestamp) VALUES(?,?,?,?,?)",
            (sess_id, "income", req.amount, desc, now_str)
        )
    con.commit()
    updated_client = con.execute("SELECT * FROM clients WHERE id=?", (id,)).fetchone()
    con.close()
    return dict(updated_client)

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# RUTAS API: CAJA (SESIONES & ARQUEO)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
@app.get("/api/cash/current")
def get_current_cash(user: Dict[str, Any] = Depends(get_current_user_from_header)):
    con = get_db()
    # Buscar sesiÃ³n abierta del usuario actual o la mÃ¡s reciente activa
    sess = con.execute(
        "SELECT cs.*, u.username uname FROM cash_sessions cs LEFT JOIN users u ON cs.user_id=u.id WHERE cs.status='open' ORDER BY cs.id DESC LIMIT 1"
    ).fetchone()
    
    if not sess:
        con.close()
        return {"status": "closed", "session": None}
    
    sid = sess["id"]
    # Ventas en efectivo
    cash_s = con.execute(
        "SELECT COALESCE(SUM(total),0) v, COUNT(*) c FROM sales WHERE session_id=? AND payment_method='efectivo'",
        (sid,)
    ).fetchone()
    # Ventas por otros mÃ©todos
    other_s = con.execute(
        "SELECT COALESCE(SUM(total),0) v, COUNT(*) c FROM sales WHERE session_id=? AND payment_method!='efectivo'",
        (sid,)
    ).fetchone()
    # Ingresos manuales
    inc = con.execute(
        "SELECT COALESCE(SUM(amount),0) v FROM cash_transactions WHERE session_id=? AND type='income'",
        (sid,)
    ).fetchone()
    # Salidas / Gastos
    out = con.execute(
        "SELECT COALESCE(SUM(amount),0) v FROM cash_transactions WHERE session_id=? AND type='outcome'",
        (sid,)
    ).fetchone()
    
    # Transacciones recientes
    txs = con.execute(
        "SELECT * FROM cash_transactions WHERE session_id=? ORDER BY id DESC LIMIT 15",
        (sid,)
    ).fetchall()
    
    initial = float(sess["initial_cash"])
    expected = initial + float(cash_s["v"]) + float(inc["v"]) - float(out["v"])
    
    con.close()
    
    return {
        "status": "open",
        "session": {
            "id": sess["id"],
            "user_id": sess["user_id"],
            "username": sess["uname"],
            "opened_at": sess["opened_at"],
            "initial_cash": initial,
            "cash_sales": float(cash_s["v"]),
            "other_sales": float(other_s["v"]),
            "incomes": float(inc["v"]),
            "outcomes": float(out["v"]),
            "expected_cash": expected,
            "sales_count": int(cash_s["c"]) + int(other_s["c"]),
            "transactions": [dict(t) for t in txs]
        }
    }

@app.post("/api/cash/open")
def open_cash(
    req: OpenCashRequest,
    user: Dict[str, Any] = Depends(get_current_user_from_header)
):
    con = get_db()
    # Verificar si ya hay una abierta
    active = con.execute("SELECT id FROM cash_sessions WHERE status='open' LIMIT 1").fetchone()
    if active:
        con.close()
        raise HTTPException(status_code=400, detail="Ya existe una sesiÃ³n de caja abierta.")
    
    loc = con.execute("SELECT id FROM pos_locations WHERE active=1 ORDER BY id LIMIT 1").fetchone()
    loc_id = loc["id"] if loc else None
    
    now_str = local_now().strftime("%Y-%m-%d %H:%M:%S")
    cur = con.execute(
        "INSERT INTO cash_sessions(user_id, location_id, opened_at, initial_cash, status) VALUES(?,?,?,?,?)",
        (user["id"], loc_id, now_str, float(req.initial_cash), "open")
    )
    sid = cur.lastrowid
    con.commit()
    con.close()
    return {"message": "Caja abierta con Ã©xito", "session_id": sid}

@app.post("/api/cash/close")
def close_cash(
    req: CloseCashRequest,
    user: Dict[str, Any] = Depends(get_current_user_from_header)
):
    con = get_db()
    sess = con.execute("SELECT * FROM cash_sessions WHERE status='open' ORDER BY id DESC LIMIT 1").fetchone()
    if not sess:
        con.close()
        raise HTTPException(status_code=400, detail="No hay ninguna sesiÃ³n de caja abierta para cerrar.")
    
    sid = sess["id"]
    cash_s = con.execute(
        "SELECT COALESCE(SUM(total),0) v FROM sales WHERE session_id=? AND payment_method='efectivo'",
        (sid,)
    ).fetchone()
    inc = con.execute(
        "SELECT COALESCE(SUM(amount),0) v FROM cash_transactions WHERE session_id=? AND type='income'",
        (sid,)
    ).fetchone()
    out = con.execute(
        "SELECT COALESCE(SUM(amount),0) v FROM cash_transactions WHERE session_id=? AND type='outcome'",
        (sid,)
    ).fetchone()
    
    expected = float(sess["initial_cash"]) + float(cash_s["v"]) + float(inc["v"]) - float(out["v"])
    diff = float(req.actual_cash) - expected
    now_str = local_now().strftime("%Y-%m-%d %H:%M:%S")
    
    con.execute(
        """UPDATE cash_sessions SET closed_at=?, actual_cash=?, expected_cash=?, difference=?, notes=?, status='closed'
           WHERE id=?""",
        (now_str, float(req.actual_cash), expected, diff, req.notes or "", sid)
    )
    con.commit()
    con.close()
    return {
        "message": "Caja cerrada correctamente",
        "session_id": sid,
        "expected_cash": expected,
        "actual_cash": req.actual_cash,
        "difference": diff
    }

@app.post("/api/cash/transaction")
def add_cash_movement(
    req: CashTransactionRequest,
    user: Dict[str, Any] = Depends(get_current_user_from_header)
):
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser superior a 0")
    if req.type not in ("income", "outcome"):
        raise HTTPException(status_code=400, detail="El tipo de transacciÃ³n debe ser 'income' o 'outcome'")
        
    con = get_db()
    sess = con.execute("SELECT id FROM cash_sessions WHERE status='open' ORDER BY id DESC LIMIT 1").fetchone()
    if not sess:
        con.close()
        raise HTTPException(status_code=400, detail="No hay una sesiÃ³n de caja abierta")
    
    now_str = local_now().strftime("%Y-%m-%d %H:%M:%S")
    con.execute(
        "INSERT INTO cash_transactions(session_id, type, amount, description, timestamp) VALUES(?,?,?,?,?)",
        (sess["id"], req.type, float(req.amount), req.description.strip(), now_str)
    )
    con.commit()
    con.close()
    return {"message": "Movimiento registrado con Ã©xito"}

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# RUTAS API: VENTAS & POS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
@app.post("/api/sales")
def create_sale(
    req: CreateSaleRequest,
    user: Dict[str, Any] = Depends(get_current_user_from_header)
):
    if not req.items:
        raise HTTPException(status_code=400, detail="El carrito de venta no puede estar vacÃ­o")
        
    con = get_db()
    # Buscar sesiÃ³n de caja abierta
    sess = con.execute("SELECT id FROM cash_sessions WHERE status='open' ORDER BY id DESC LIMIT 1").fetchone()
    session_id = sess["id"] if sess else None
    
    # Sede activa
    loc = con.execute("SELECT id FROM pos_locations WHERE active=1 ORDER BY id LIMIT 1").fetchone()
    loc_id = loc["id"] if loc else None
    
    now = local_now()
    subtotal = sum(i.subtotal for i in req.items)
    discount = float(req.discount or 0)
    total = max(0.0, subtotal - discount)
    
    cur = con.execute(
        """INSERT INTO sales(client_id, user_id, session_id, location_id, date, time, subtotal, discount, total, payment_method, notes)
           VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (req.client_id, user["id"], session_id, loc_id, now.strftime("%Y-%m-%d"),
         now.strftime("%H:%M:%S"), subtotal, discount, total, req.payment_method, req.notes or "")
    )
    sale_id = cur.lastrowid
    
    # Insertar items y descontar stock
    for item in req.items:
        con.execute(
            """INSERT INTO sale_items(sale_id, product_id, product_name, quantity, unit_price, subtotal)
               VALUES(?, ?, ?, ?, ?, ?)""",
            (sale_id, item.product_id, item.product_name, item.quantity, item.unit_price, item.subtotal)
        )
        # Descontar stock global
        con.execute("UPDATE products SET stock = stock - ? WHERE id=?", (item.quantity, item.product_id))
        if loc_id:
            con.execute(
                """INSERT INTO pos_inventory(location_id, product_id, stock) VALUES(?,?,?)
                   ON CONFLICT(location_id, product_id) DO UPDATE SET stock = stock - ?""",
                (loc_id, item.product_id, -item.quantity, item.quantity)
            )
            
    # Si es a crÃ©dito, aumentar la deuda del cliente
    if req.payment_method == "crÃ©dito" and req.client_id:
        con.execute("UPDATE clients SET debt = debt + ? WHERE id=?", (total, req.client_id))
        
    con.commit()
    
    # Obtener nombre del negocio para el recibo
    cfg_name = con.execute("SELECT value FROM config WHERE key='business_name'").fetchone()
    b_name = cfg_name["value"] if cfg_name else "GestPro"
    
    con.close()
    
    return {
        "id": sale_id,
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "subtotal": subtotal,
        "discount": discount,
        "total": total,
        "payment_method": req.payment_method,
        "items_count": len(req.items),
        "business_name": b_name,
        "session_id": session_id,
        "message": "Venta registrada con Ã©xito"
    }

@app.get("/api/sales")
def get_sales(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    today = date.today().isoformat()
    d1 = start_date or today
    d2 = end_date or today
    
    con = get_db()
    rows = con.execute(
        """SELECT s.*, COALESCE(c.name, 'Mostrador') client_name, u.username uname,
                  (SELECT COUNT(*) FROM sale_items WHERE sale_id = s.id) items_count
           FROM sales s
           LEFT JOIN clients c ON s.client_id = c.id
           LEFT JOIN users u ON s.user_id = u.id
           WHERE s.date BETWEEN ? AND ?
           ORDER BY s.date DESC, s.time DESC
           LIMIT ? OFFSET ?""",
        (d1, d2, limit, offset)
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]

@app.get("/api/sales/{id}")
def get_sale_detail(id: int):
    con = get_db()
    sale = con.execute(
        """SELECT s.*, COALESCE(c.name, 'Mostrador') client_name, c.phone client_phone, u.username uname
           FROM sales s
           LEFT JOIN clients c ON s.client_id = c.id
           LEFT JOIN users u ON s.user_id = u.id
           WHERE s.id = ?""",
        (id,)
    ).fetchone()
    
    if not sale:
        con.close()
        raise HTTPException(status_code=404, detail="Venta no encontrada")
        
    items = con.execute("SELECT * FROM sale_items WHERE sale_id = ?", (id,)).fetchall()
    con.close()
    
    res = dict(sale)
    res["items"] = [dict(i) for i in items]
    return res

@app.post("/api/sales/{id}/cancel")
def cancel_sale(
    id: int,
    user: Dict[str, Any] = Depends(get_current_user_from_header)
):
    con = get_db()
    sale = con.execute("SELECT * FROM sales WHERE id=?", (id,)).fetchone()
    if not sale:
        con.close()
        raise HTTPException(status_code=404, detail="Venta no encontrada")
        
    loc_id = sale["location_id"]
    items = con.execute("SELECT * FROM sale_items WHERE sale_id=?", (id,)).fetchall()
    
    # Restaurar stock
    for i in items:
        if i["product_id"]:
            con.execute("UPDATE products SET stock = stock + ? WHERE id=?", (i["quantity"], i["product_id"]))
            if loc_id:
                con.execute(
                    """INSERT INTO pos_inventory(location_id, product_id, stock) VALUES(?,?,?)
                       ON CONFLICT(location_id, product_id) DO UPDATE SET stock = stock + ?""",
                    (loc_id, i["product_id"], i["quantity"], i["quantity"])
                )
                
    # Si fue a crÃ©dito, rebajar la deuda
    if sale["payment_method"] == "crÃ©dito" and sale["client_id"]:
        con.execute("UPDATE clients SET debt = MAX(0, debt - ?) WHERE id=?", (sale["total"], sale["client_id"]))
        
    con.execute("DELETE FROM sales WHERE id=?", (id,))
    con.commit()
    con.close()
    return {"message": f"Venta #{id} anulada correctamente y stock devuelto"}

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# RUTAS API: GASTOS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
@app.get("/api/expenses")
def get_expenses(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    today = date.today().isoformat()
    d1 = start_date or today
    d2 = end_date or today
    
    con = get_db()
    rows = con.execute(
        """SELECT e.*, u.username uname
           FROM expenses e
           LEFT JOIN users u ON e.user_id = u.id
           WHERE e.date BETWEEN ? AND ?
           ORDER BY e.timestamp DESC""",
        (d1, d2)
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]

@app.post("/api/expenses")
def create_expense(
    req: ExpenseCreateRequest,
    user: Dict[str, Any] = Depends(get_current_user_from_header)
):
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="El valor del gasto debe ser mayor a 0")
        
    con = get_db()
    sess = con.execute("SELECT id FROM cash_sessions WHERE status='open' ORDER BY id DESC LIMIT 1").fetchone()
    session_id = sess["id"] if (req.affect_cash and sess) else None
    
    loc = con.execute("SELECT id FROM pos_locations WHERE active=1 ORDER BY id LIMIT 1").fetchone()
    loc_id = loc["id"] if loc else None
    
    now = local_now()
    cur = con.execute(
        """INSERT INTO expenses(user_id, session_id, location_id, date, category, amount, description, timestamp)
           VALUES(?, ?, ?, ?, ?, ?, ?, ?)""",
        (user["id"], session_id, loc_id, now.strftime("%Y-%m-%d"), req.category.strip(),
         float(req.amount), (req.description or "").strip(), now.strftime("%Y-%m-%d %H:%M:%S"))
    )
    eid = cur.lastrowid
    
    # Si afecta caja y hay sesiÃ³n abierta, registrar la salida
    if session_id:
        desc = f"Gasto: {req.category.strip()}"
        if req.description:
            desc += f" ({req.description.strip()})"
        con.execute(
            "INSERT INTO cash_transactions(session_id, type, amount, description, timestamp) VALUES(?,?,?,?,?)",
            (session_id, "outcome", float(req.amount), desc, now.strftime("%Y-%m-%d %H:%M:%S"))
        )
        
    con.commit()
    con.close()
    return {"id": eid, "message": "Gasto registrado correctamente"}

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# SERVIR FRONTEND ESTÃTICO & PWA
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Montar carpeta web si existe
if os.path.isdir(WEB_DIR):
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

@app.get("/")
def index_page():
    index_path = os.path.join(WEB_DIR, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h2>GestPro MÃ³vil: Carpeta web no encontrada.</h2>")

@app.get("/manifest.json")
def get_manifest():
    manifest_path = os.path.join(WEB_DIR, "manifest.json")
    if os.path.isfile(manifest_path):
        return FileResponse(manifest_path, media_type="application/json")
    return JSONResponse({})

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# EJECUCIÃ“N PRINCIPAL CON BANNER Y QR
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
def print_banner(host: str, port: int):
    lan_ip = get_lan_ip()
    local_url = f"http://localhost:{port}"
    lan_url = f"http://{lan_ip}:{port}"
    
    try:
        print("\n" + "=" * 62)
        print("      [OK] GESTPRO MOVIL - SERVIDOR INICIADO CORRECTAMENTE")
        print("=" * 62)
        print(f"  * En esta PC:        {local_url}")
        print(f"  * En tu celular:     {lan_url}")
        print("-" * 62)
        print("  Escanea este codigo QR con la camara de tu celular:")
        print("  (Asegurate de estar conectado al mismo Wi-Fi)")
        print("-" * 62)
        qr = qrcode.QRCode(border=1)
        qr.add_data(lan_url)
        qr.make(fit=True)
        f = io.StringIO()
        qr.print_ascii(out=f, invert=True)
        print(f.getvalue())
    except Exception as e:
        print(f"  [Abre el enlace directamente en tu celular]: {lan_url}")
    print("=" * 62)
    print("  Presiona Ctrl + C en esta ventana para detener el servidor.")
    print("=" * 62 + "\n")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="GestPro MÃ³vil Web Server")
    default_port = int(os.environ.get("PORT", 8000))
    parser.add_argument("--port", type=int, default=default_port, help=f"Puerto de escucha (default: {default_port})")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host IP (default: 0.0.0.0)")
    args = parser.parse_args()
    
    # Asegurar modo WAL en la base de datos
    try:
        _c = get_db()
        _c.execute("PRAGMA journal_mode = WAL")
        _c.close()
    except Exception as e:
        print("Aviso al verificar WAL:", e)
        
    print_banner(args.host, args.port)
    uvicorn.run("web_server:app", host=args.host, port=args.port, reload=False, log_level="warning")

