#!/usr/bin/env python3
"""
GestiónPro v2.0 Comercial
Sistema de gestión para cualquier tipo de negocio.
SQLite · Inventario · POS · Caja · Informes · Excel · Gráficos
"""
import sqlite3, hashlib, hmac, json, logging, random, os, sys, zipfile, glob
from datetime import datetime, date, timedelta
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    import customtkinter as ctk
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
except ImportError:
    raise SystemExit("Ejecuta: pip install customtkinter")

try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

try:
    import pandas as pd
    HAS_PD = True
except ImportError:
    HAS_PD = False

try:
    from escpos.printer import Usb, Serial, Network, Win32Raw
    HAS_ESCPOS = True
except ImportError:
    HAS_ESCPOS = False

# ── Logging ──────────────────────────────────────────────────
_log_file = f"gestionpro_{date.today():%Y%m%d}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(_log_file, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("GestiónPro")

# ── Licencia (sistema de key de uso único) ───────────────────
import base64 as _b64
import uuid as _uuid

_SECRET_KEY = b"G3st10nPr0_2026_KEY_S3cr3t4_X7k9Qm"
_LIC_INFO = None

class LicenseManager:
    """Gestiona la validación y activación de llaves de licencia.
    La llave se almacena en la tabla config de la BD SQLite.
    """
    def __init__(self, db):
        self.db = db

    def validate_license_string(self, key_str: str) -> dict:
        """Verifica criptográficamente la llave.
        Retorna un dict con los datos del payload o lanza ValueError.
        """
        try:
            decoded = _b64.b64decode(key_str).decode("utf-8")
            payload_str, signature = decoded.split("|", 1)
            expected = hmac.new(_SECRET_KEY, payload_str.encode("utf-8"),
                                hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, signature):
                raise ValueError("Firma inválida. La llave fue alterada.")
            return json.loads(payload_str)
        except (ValueError, KeyError):
            raise
        except Exception:
            raise ValueError("Llave de licencia inválida o corrupta.")

    def check_current_status(self) -> dict:
        """Verifica el estado de la licencia almacenada en la BD.
        Retorna: {"valid": bool, "reason": str}
        """
        lic_key = self.db.cfg("license_key")
        if not lic_key:
            return {"valid": False, "reason": "No hay licencia instalada."}
        try:
            payload = self.validate_license_string(lic_key)
        except ValueError as e:
            return {"valid": False, "reason": str(e)}

        # Protección anti-manipulación de reloj
        last_seen = self.db.cfg("license_last_seen_date")
        today_iso = date.today().isoformat()
        if last_seen and today_iso < last_seen:
            return {"valid": False,
                    "reason": "Se detectó manipulación del reloj del sistema. Licencia bloqueada."}
        self.db.set_cfg("license_last_seen_date", today_iso)

        if payload.get("permanent", False):
            log.info("Licencia PERMANENTE activa.")
            return {"valid": True, "reason": "Licencia permanente."}

        # Calcular expiración desde la fecha de activación
        activation_str = self.db.cfg("license_activation_date")
        if not activation_str:
            return {"valid": False, "reason": "Error en la fecha de activación."}
        activation = date.fromisoformat(activation_str)
        days_allowed = payload.get("days", 0)
        days_passed = (date.today() - activation).days
        if days_passed > days_allowed:
            return {"valid": False,
                    "reason": f"La licencia de {days_allowed} días ha expirado."}
        remaining = days_allowed - days_passed
        log.info(f"Licencia válida — {remaining} día(s) restante(s).")
        return {"valid": True, "reason": f"Quedan {remaining} días de licencia."}

    def activate(self, key_str: str):
        """Activa una nueva llave y la guarda en la BD. Lanza ValueError si falla."""
        payload = self.validate_license_string(key_str)
        # Si es la misma llave ya guardada, verificar que siga vigente
        current_key = self.db.cfg("license_key")
        if current_key and key_str == current_key:
            status = self.check_current_status()
            if not status["valid"]:
                raise ValueError("Esta llave ya fue utilizada y ha expirado.")
            return True
        # Guardar llave nueva
        self.db.set_cfg("license_key", key_str)
        self.db.set_cfg("license_activation_date", date.today().isoformat())
        self.db.set_cfg("license_last_seen_date", date.today().isoformat())
        log.info(f"Licencia activada — ID: {payload.get('id','?')}")
        return True


class ActivationWindow(ctk.CTk):
    """Ventana de activación: el usuario pega su llave de licencia."""
    def __init__(self, db):
        super().__init__()
        self._db = db
        self._lm = LicenseManager(db)
        self.success = False
        self.title("GestiónPro — Activación de Software")
        self.geometry("480x340")
        self.resizable(False, False)
        self.configure(fg_color="#181818")
        self._build()

    def _build(self):
        card = ctk.CTkFrame(self, fg_color="#252525", corner_radius=12)
        card.pack(fill="both", expand=True, padx=24, pady=24)

        ctk.CTkLabel(card, text="🔒", font=("Segoe UI", 44)).pack(pady=(18, 0))
        ctk.CTkLabel(card, text="Activación Requerida",
                     font=("Segoe UI", 18, "bold"), text_color="#f0f0f0").pack(pady=(4, 0))

        status = self._lm.check_current_status()
        reason = status.get("reason", "Introduce tu llave de licencia.")
        ctk.CTkLabel(card, text=reason, font=("Segoe UI", 10),
                     text_color="#e74c3c", wraplength=380).pack(pady=(6, 14))

        ctk.CTkLabel(card, text="Llave de Licencia:", font=("Segoe UI", 10),
                     text_color="#888888").pack(anchor="w", padx=30)
        self._e_key = ctk.CTkEntry(card, width=400, placeholder_text="Pega aquí tu código de licencia...",
                                   font=("Segoe UI", 10))
        self._e_key.pack(padx=30, pady=(4, 18))

        ctk.CTkButton(card, text="Activar Software", command=self._activate,
                      width=220, height=42, fg_color="#4682DC", hover_color="#5a96f0",
                      font=("Segoe UI", 12, "bold")).pack()
        ctk.CTkLabel(card, text="Contacta a tu proveedor para obtener una licencia.",
                     font=("Segoe UI", 9), text_color="#555555").pack(side="bottom", pady=14)

    def _activate(self):
        from tkinter import messagebox
        key = self._e_key.get().strip()
        if not key:
            messagebox.showerror("Error", "Debes ingresar una llave.", parent=self)
            return
        try:
            self._lm.activate(key)
            messagebox.showinfo("Éxito",
                "¡Software activado correctamente!\nGracias por confiar en GestiónPro.", parent=self)
            self.success = True
            self.destroy()
        except ValueError as e:
            messagebox.showerror("Error de Activación", str(e), parent=self)
            self._e_key.delete(0, "end")


def check_license_and_run(db) -> bool:
    """Verifica la licencia. Si es válida retorna True.
    Si no, muestra la ventana de activación. Retorna True solo si se activa con éxito.
    """
    global _LIC_INFO
    lm = LicenseManager(db)
    
    def _set_info():
        global _LIC_INFO
        try:
            payload = lm.validate_license_string(db.cfg("license_key"))
            _LIC_INFO = {"permanente": payload.get("permanent", False)}
            if not _LIC_INFO["permanente"]:
                activation = date.fromisoformat(db.cfg("license_activation_date"))
                days_allowed = payload.get("days", 0)
                days_passed = (date.today() - activation).days
                _LIC_INFO["dias_restantes"] = max(0, days_allowed - days_passed)
        except Exception:
            _LIC_INFO = None

    status = lm.check_current_status()
    if status["valid"]:
        _set_info()
        return True
    win = ActivationWindow(db)
    win.mainloop()
    if win.success:
        _set_info()
    return win.success

# ── Paleta ────────────────────────────────────────────────────
BG     = "#181818"; SIDEBAR = "#1e1e1e"; CARD = "#252525"
ACC    = "#4682DC"; ACCH   = "#5a96f0"; TEXT = "#f0f0f0"
DIM    = "#888888"; OK     = "#3dba6e"; ERR  = "#e74c3c"
WARN   = "#f39c12"; PURPLE = "#8e44ad"

# ── Escala Responsiva ─────────────────────────────────────────
# Referencia base: 1366×768 (portátil estándar = SCALE 1.0).
# En monitores más grandes el factor sube → fuentes y widgets más grandes.
# Se llama _init_scale() desde main() antes de crear ninguna ventana.
SCALE: float = 1.0

def _init_scale():
    """Detecta la resolución real y actualiza el factor global SCALE."""
    global SCALE
    try:
        _tmp = tk.Tk()
        _tmp.withdraw()
        sw = _tmp.winfo_screenwidth()
        sh = _tmp.winfo_screenheight()
        _tmp.destroy()
        # Base: 1366×768 (portátil típico).
        # 1366×768  → SCALE ≈ 1.00  (portátil, se ve bien)
        # 1920×1080 → SCALE ≈ 1.40  (PC escritorio, texto más grande)
        # 2560×1440 → SCALE ≈ 1.80  (2K, llega al tope)
        base_w, base_h = 1366, 768
        SCALE = min(sw / base_w, sh / base_h)
        # Clampear: nunca menos de 0.75 ni más de 1.80
        SCALE = max(0.75, min(SCALE, 1.80))
        log.info(f"Pantalla: {sw}×{sh}  →  SCALE={SCALE:.3f}")
    except Exception:
        SCALE = 1.0

def _sc(n: int) -> int:
    """Escala un valor de píxeles según la resolución de la pantalla."""
    return max(1, int(round(n * SCALE)))


# ═══════════════════════════════════════════════════════════════
# BASE DE DATOS
# ═══════════════════════════════════════════════════════════════
class DB:
    def __init__(self, path="gestionpro.db"):
        self.con = sqlite3.connect(path, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON")
        self._schema()
        self._seed()
        log.info(f"Base de datos: {os.path.abspath(path)}")

    def all(self, sql, p=()):
        return [dict(r) for r in self.con.execute(sql, p).fetchall()]
    def one(self, sql, p=()):
        r = self.con.execute(sql, p).fetchone()
        return dict(r) if r else None
    def run(self, sql, p=()):
        c = self.con.execute(sql, p)
        self.con.commit()
        return c.lastrowid

    def _schema(self):
        self.con.executescript("""
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
            actual_cash REAL DEFAULT 0, status TEXT NOT NULL DEFAULT 'open');
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
        """)
        self.con.commit()
        self._migrate()

    def _migrate(self):
        """Agrega columnas faltantes a tablas existentes (compatibilidad hacia adelante)."""
        migrations = [
            ("sales",          "session_id",    "INTEGER REFERENCES cash_sessions(id)"),
            ("sales",          "discount",      "REAL NOT NULL DEFAULT 0"),
            ("sales",          "subtotal",      "REAL NOT NULL DEFAULT 0"),
            ("sale_items",     "product_id",    "INTEGER REFERENCES products(id)"),
            ("products",       "min_stock",     "INTEGER NOT NULL DEFAULT 5"),
            ("products",       "unit",          "TEXT NOT NULL DEFAULT 'unidad'"),
            ("cash_sessions",  "actual_cash",   "REAL DEFAULT 0"),
            ("clients",        "debt",          "REAL NOT NULL DEFAULT 0"),
            ("invoices",       "cufe",          "TEXT NOT NULL DEFAULT ''"),
            ("invoices",       "pdf_url",       "TEXT NOT NULL DEFAULT ''"),
            ("invoices",       "dian_status",   "TEXT NOT NULL DEFAULT ''"),
        ]
        existing = {}
        for table, col, defn in migrations:
            if table not in existing:
                existing[table] = {r["name"] for r in
                    self.all(f"PRAGMA table_info({table})")}
            if col not in existing[table]:
                try:
                    self.con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {defn}")
                    self.con.commit()
                    log.info(f"Migración: columna '{col}' agregada a '{table}'")
                    existing[table].add(col)
                except Exception as ex:
                    log.warning(f"Migración omitida ({table}.{col}): {ex}")

    def _seed(self):
        for k, v in [
            ("business_name", "Mi Negocio"), ("business_type", "Tienda General"),
            ("currency_symbol", "$"), ("currency_code", "COP"),
            ("address", ""), ("phone", ""), ("tax_percent", "0"),
            ("low_stock_limit", "5"), ("logo_path", ""),
            ("printer_name", ""), ("printer_enabled", "0"),
            ("printer_width", "80mm (estándar)"),
            # ── Facturación Electrónica Factus (DIAN) — Credenciales Sandbox V2 ──
            ("invoice_prefix",            "FAC"),
            ("invoice_next",              "1"),
            ("factus_client_id",          "a2159eae-5d86-454f-b786-790a9c3f96ca"),
            ("factus_client_secret",      "uvzljVQXLvzCujKFBa5NxwWTeHdb9uGjaHR1z7ud"),
            ("factus_username",           "sandboxv2@factus.com.co"),
            ("factus_password",           "sandbox2026%"),
            ("factus_numbering_range_id", "389"),
            ("factus_environment",        "sandbox"),
            ("factus_municipality_code",  "68001"),
        ]:
            self.con.execute("INSERT OR IGNORE INTO config VALUES(?,?)", (k, v))
        self.con.execute(
            "INSERT OR IGNORE INTO users(username,password,role) VALUES(?,?,?)",
            ("admin", self._hp("admin123"), "admin"))
        # Solo sembrar categorías si la tabla está vacía (primer arranque)
        if not self.all("SELECT 1 FROM categories LIMIT 1"):
            for cat in ["General","Electrónica","Ropa","Alimentos","Hogar",
                        "Deportes","Libros","Bebidas","Juguetes","Salud"]:
                self.con.execute("INSERT OR IGNORE INTO categories(name) VALUES(?)", (cat,))
        self.con.commit()

    def _hp(self, pw): return hashlib.sha256(pw.encode()).hexdigest()
    def cfg(self, k):
        r = self.one("SELECT value FROM config WHERE key=?", (k,))
        return r["value"] if r else ""
    def set_cfg(self, k, v): self.run("INSERT OR REPLACE INTO config VALUES(?,?)", (k, v))
    def login(self, u, p):
        return self.one("SELECT * FROM users WHERE username=? AND password=? AND active=1", (u, self._hp(p)))

    # ── Usuarios ─────────────────────────────────────────────
    def get_users(self): return self.all("SELECT * FROM users ORDER BY username")
    def add_user(self, u, p, r): self.run("INSERT INTO users(username,password,role) VALUES(?,?,?)", (u,self._hp(p),r))
    def upd_user(self, id, u, p, r, a):
        if p: self.run("UPDATE users SET username=?,password=?,role=?,active=? WHERE id=?", (u,self._hp(p),r,a,id))
        else: self.run("UPDATE users SET username=?,role=?,active=? WHERE id=?", (u,r,a,id))
    def del_user(self, id): self.run("DELETE FROM users WHERE id=?", (id,))

    # ── Categorías ───────────────────────────────────────────
    def get_categories(self): return [r["name"] for r in self.all("SELECT name FROM categories ORDER BY name")]
    def add_category(self, name): self.run("INSERT OR IGNORE INTO categories(name) VALUES(?)", (name,))
    def del_category(self, name): self.run("DELETE FROM categories WHERE name=?", (name,))

    # ── Productos ────────────────────────────────────────────
    def _gen_sku(self):
        used = {r["sku"] for r in self.all("SELECT sku FROM products WHERE sku IS NOT NULL")}
        while True:
            sku = random.randint(100000, 999999)
            if sku not in used: return sku

    def get_products(self, search="", category="", page=1, page_size=100):
        p = []; q = "SELECT * FROM products WHERE active=1"
        if search:
            q += " AND (name LIKE ? OR CAST(sku AS TEXT) LIKE ? OR supplier LIKE ? OR barcode LIKE ?)"
            s = f"%{search}%"; p += [s,s,s,s]
        if category and category not in ("Todas",""):
            q += " AND category=?"; p.append(category)
        q += " ORDER BY name"
        rows = self.all(q, p)
        total = len(rows)
        start = (page-1)*page_size
        return rows[start:start+page_size], total

    def get_all_products(self, search="", category=""):
        p = []; q = "SELECT * FROM products WHERE active=1"
        if search:
            q += " AND (name LIKE ? OR CAST(sku AS TEXT) LIKE ? OR supplier LIKE ? OR barcode LIKE ?)"
            s = f"%{search}%"; p += [s,s,s,s]
        if category and category not in ("Todas",""):
            q += " AND category=?"; p.append(category)
        return self.all(q+" ORDER BY name", p)

    def get_product(self, id): return self.one("SELECT * FROM products WHERE id=?", (id,))
    def get_product_by_sku(self, sku): return self.one("SELECT * FROM products WHERE sku=? AND active=1", (sku,))

    def add_product(self, name, sku, barcode, category, price, cost, supplier, stock, min_stock, unit):
        if not sku: sku = self._gen_sku()
        self.run(
            "INSERT INTO products(name,sku,barcode,category,price,cost,supplier,stock,min_stock,unit)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (name,int(sku),barcode,category,float(price),float(cost),supplier,int(stock),int(min_stock),unit))
        log.info(f"Producto creado: {name} SKU:{sku}")

    def upd_product(self, id, name, sku, barcode, category, price, cost, supplier, stock, min_stock, unit):
        self.run(
            "UPDATE products SET name=?,sku=?,barcode=?,category=?,price=?,cost=?,"
            "supplier=?,stock=?,min_stock=?,unit=? WHERE id=?",
            (name,int(sku),barcode,category,float(price),float(cost),supplier,int(stock),int(min_stock),unit,id))

    def del_product(self, id): self.run("UPDATE products SET active=0 WHERE id=?", (id,))
    def adj_stock(self, id, delta): self.run("UPDATE products SET stock=stock+? WHERE id=?", (delta,id))
    def low_stock(self): return self.all("SELECT * FROM products WHERE active=1 AND stock<=min_stock ORDER BY stock")
    def inventory_value(self):
        return self.one("SELECT COALESCE(SUM(price*stock),0) venta, COALESCE(SUM(cost*stock),0) costo FROM products WHERE active=1")

    def clean_data(self):
        fixed = 0
        for p in self.all("SELECT * FROM products WHERE active=1"):
            ch = {}
            if not p["name"] or not p["name"].strip(): ch["name"] = f"Producto_{p['sku']}"
            if p["cost"] < 0: ch["cost"] = abs(p["cost"])
            if p["price"] <= 0: ch["price"] = max(float(p.get("cost",0))*1.2, 1000)
            if p["stock"] < 0: ch["stock"] = 0
            if not p["category"] or not p["category"].strip(): ch["category"] = "General"
            if ch:
                sets = ", ".join(f"{k}=?" for k in ch)
                self.run(f"UPDATE products SET {sets} WHERE id=?", list(ch.values())+[p["id"]])
                fixed += 1
        self.con.commit()
        log.info(f"Limpieza completada: {fixed} productos corregidos")
        return fixed

    def import_excel(self, filepath):
        if not HAS_PD: raise ImportError("pip install pandas openpyxl")
        df = pd.read_excel(filepath)
        col_map = {
            "name":     ["Nombre","nombre","Producto","producto"],
            "cost":     ["PrecioCompra","precio_compra","Precio Compra","Costo","costo"],
            "price":    ["PrecioVenta","precio_venta","Precio Venta","Precio","precio"],
            "stock":    ["Cantidad","cantidad","Stock","stock"],
            "sku":      ["SKU","sku","Codigo","código"],
            "supplier": ["Proveedor","proveedor"],
            "category": ["Categoría","categoria","Category"],
            "barcode":  ["Barcode","barcode","EAN"],
            "unit":     ["Unidad","unidad","Unit"],
        }
        found = {}
        for key, options in col_map.items():
            for opt in options:
                if opt in df.columns: found[key] = opt; break
        if "name" not in found: raise ValueError("No se encontró columna 'Nombre'")
        imported = dupes = errors = 0
        existing_names = {p["name"].lower() for p in self.get_all_products()}
        existing_skus  = {p["sku"] for p in self.get_all_products()}
        for _, row in df.iterrows():
            try:
                name = str(row[found["name"]]).strip().capitalize()
                if not name or name.lower() in ("nan",""): errors+=1; continue
                if name.lower() in existing_names: dupes+=1; continue
                cost     = float(row[found["cost"]])     if "cost"     in found else 0.0
                price    = float(row[found["price"]])    if "price"    in found else cost*1.5
                stock    = int(float(row[found["stock"]])) if "stock"  in found else 0
                supplier = str(row[found["supplier"]]).strip() if "supplier" in found else "Importado"
                category = str(row[found["category"]]).strip() if "category" in found else "General"
                unit     = str(row[found["unit"]]).strip()     if "unit"     in found else "unidad"
                barcode  = str(row[found["barcode"]]).strip()  if "barcode"  in found else ""
                sku = None
                if "sku" in found:
                    raw = row[found["sku"]]
                    if pd.notna(raw) and int(float(raw)) > 0:
                        sv = int(float(raw))
                        if sv not in existing_skus: sku = sv; existing_skus.add(sku)
                if not sku: sku = self._gen_sku(); existing_skus.add(sku)
                if pd.isna(cost) or cost<0: cost=0
                if pd.isna(price) or price<=0: price=cost*1.5
                if pd.isna(stock) or stock<0: stock=0
                if not supplier or supplier.lower() in ("nan",""): supplier="Importado"
                if not category or category.lower() in ("nan",""): category="General"
                self.add_product(name, sku, barcode, category, price, cost, supplier, stock, 5, unit)
                existing_names.add(name.lower()); imported+=1
            except Exception as exc:
                log.warning(f"Error importando fila: {exc}"); errors+=1
        log.info(f"Excel importado: {imported} nuevos, {dupes} duplicados, {errors} errores")
        return {"importados": imported, "duplicados": dupes, "errores": errors}

    def export_excel(self, filepath):
        if not HAS_PD: raise ImportError("pip install pandas openpyxl")
        products = self.get_all_products()
        df = pd.DataFrame(products)
        df = df.rename(columns={"name":"Nombre","sku":"SKU","barcode":"Código Barras",
            "category":"Categoría","price":"PrecioVenta","cost":"PrecioCompra",
            "supplier":"Proveedor","stock":"Cantidad","min_stock":"Stock Mínimo","unit":"Unidad"})
        with pd.ExcelWriter(filepath, engine="openpyxl") as w:
            df[["Nombre","SKU","Código Barras","Categoría","PrecioVenta","PrecioCompra",
                "Proveedor","Cantidad","Stock Mínimo","Unidad"]].to_excel(w, sheet_name="Inventario", index=False)
        log.info(f"Inventario exportado: {filepath}")

    # ── Clientes ─────────────────────────────────────────────
    def get_clients(self, search=""):
        p=[]; q="SELECT * FROM clients"
        if search: q+=" WHERE name LIKE ? OR phone LIKE ? OR document LIKE ?"; s=f"%{search}%"; p=[s,s,s]
        return self.all(q+" ORDER BY name", p)
    def add_client(self, name, doc, phone, email, addr, notes):
        self.run("INSERT INTO clients(name,document,phone,email,address,notes) VALUES(?,?,?,?,?,?)", (name,doc,phone,email,addr,notes))
    def upd_client(self, id, name, doc, phone, email, addr, notes):
        self.run("UPDATE clients SET name=?,document=?,phone=?,email=?,address=?,notes=? WHERE id=?", (name,doc,phone,email,addr,notes,id))
    def del_client(self, id): self.run("DELETE FROM clients WHERE id=?", (id,))
    def add_client_payment(self, client_id, user_id, session_id, amount, notes):
        # Registrar el pago
        self.run("INSERT INTO client_payments(client_id,user_id,session_id,amount,notes,timestamp) VALUES(?,?,?,?,?,?)",
                 (client_id, user_id, session_id, amount, notes, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        # Reducir deuda
        self.run("UPDATE clients SET debt = debt - ? WHERE id=?", (amount, client_id))
        # Registrar en la caja si hay turno abierto
        if session_id:
            client = self.one("SELECT name FROM clients WHERE id=?", (client_id,))
            cname = client["name"] if client else str(client_id)
            desc = f"Abono de deuda: {cname}"
            if notes: desc += f" ({notes})"
            self.add_cash_transaction(session_id, "income", amount, desc)

    # ── Caja / Sesiones ──────────────────────────────────────
    def get_active_session(self, user_id):
        return self.one("SELECT * FROM cash_sessions WHERE user_id=? AND status='open'", (user_id,))

    def open_session(self, user_id, initial_cash):
        sid = self.run("INSERT INTO cash_sessions(user_id,opened_at,initial_cash,status) VALUES(?,?,?,?)",
                       (user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), float(initial_cash), "open"))
        log.info(f"Caja abierta: sesión #{sid} inicial ${initial_cash:.0f}")
        return sid

    def close_session(self, session_id, actual_cash):
        self.run("UPDATE cash_sessions SET closed_at=?,actual_cash=?,status='closed' WHERE id=?",
                 (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), float(actual_cash), session_id))
        log.info(f"Caja cerrada: sesión #{session_id}, real ${actual_cash:.0f}")

    # ── Facturación Electrónica ───────────────────────────────
    def next_invoice_number(self):
        """Genera el siguiente número de factura correlativo con prefijo (ej: FAC-000001)."""
        prefix = self.cfg("invoice_prefix") or "FAC"
        try:
            nxt = int(self.cfg("invoice_next") or "1")
        except (ValueError, TypeError):
            nxt = 1
        num = f"{prefix}-{nxt:06d}"
        self.set_cfg("invoice_next", str(nxt + 1))
        return num

    def create_invoice(self, sale_id, payment_method, discount, tax_iva, notes=""):
        """Crea un registro de factura electrónica en la BD local."""
        sale = self.one("SELECT * FROM sales WHERE id=?", (sale_id,))
        if not sale:
            return None
        num      = self.next_invoice_number()
        subtotal = float(sale.get("subtotal", 0))
        total    = subtotal - float(discount) + float(tax_iva)
        now      = datetime.now()
        inv_id   = self.run(
            "INSERT INTO invoices(sale_id,invoice_num,date,time,"
            "subtotal,discount,tax_iva,total,payment_method,notes) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (sale_id, num,
             now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"),
             subtotal, float(discount), float(tax_iva), total,
             payment_method, notes))
        log.info(f"Factura local {num} creada — Total ${total:.0f}")
        return {"id": inv_id, "num": num, "total": total}

    def update_invoice_dian(self, inv_id, cufe, pdf_url, dian_status="emitida"):
        """Actualiza una factura con los datos recibidos de la DIAN (CUFE y PDF)."""
        self.run(
            "UPDATE invoices SET cufe=?, pdf_url=?, dian_status=? WHERE id=?",
            (cufe, pdf_url, dian_status, inv_id))
        log.info(f"Factura #{inv_id} actualizada con CUFE de la DIAN.")

    def get_invoice(self, inv_id):
        """Retorna una factura por ID."""
        return self.one("SELECT * FROM invoices WHERE id=?", (inv_id,))

    def add_cash_transaction(self, session_id, t_type, amount, description):
        return self.run(
            "INSERT INTO cash_transactions(session_id,type,amount,description,timestamp) VALUES(?,?,?,?,?)",
            (session_id, t_type, float(amount), description, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    def get_session_summary(self, session_id):
        sess = self.one("SELECT * FROM cash_sessions WHERE id=?", (session_id,))
        if not sess: return None
        cash_s  = self.one("SELECT COALESCE(SUM(total),0) v, COUNT(*) c FROM sales WHERE session_id=? AND payment_method='efectivo'", (session_id,))
        other_s = self.one("SELECT COALESCE(SUM(total),0) v, COUNT(*) c FROM sales WHERE session_id=? AND payment_method!='efectivo'", (session_id,))
        inc     = self.one("SELECT COALESCE(SUM(amount),0) v FROM cash_transactions WHERE session_id=? AND type='income'", (session_id,))
        out     = self.one("SELECT COALESCE(SUM(amount),0) v FROM cash_transactions WHERE session_id=? AND type='outcome'", (session_id,))
        initial = sess["initial_cash"]
        expected = initial + cash_s["v"] + inc["v"] - out["v"]
        return {
            "id": sess["id"], "opened_at": sess["opened_at"], "closed_at": sess["closed_at"],
            "initial_cash": initial, "cash_sales": cash_s["v"], "other_sales": other_s["v"],
            "incomes": inc["v"], "outcomes": out["v"], "expected_cash": expected,
            "actual_cash": sess["actual_cash"], "status": sess["status"],
            "sales_count": cash_s["c"] + other_s["c"],
        }

    # ── Ventas ───────────────────────────────────────────────
    def create_sale(self, client_id, user_id, items, discount, payment, notes="", session_id=None):
        now = datetime.now()
        sub = sum(i["subtotal"] for i in items)
        total = sub - (discount or 0)
        sid = self.run(
            "INSERT INTO sales(client_id,user_id,session_id,date,time,subtotal,discount,total,payment_method,notes)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (client_id, user_id, session_id, now.strftime("%Y-%m-%d"), now.strftime("%H:%M"),
             sub, discount or 0, total, payment, notes))
        for i in items:
            self.run("INSERT INTO sale_items(sale_id,product_id,product_name,quantity,unit_price,subtotal)"
                     " VALUES(?,?,?,?,?,?)",
                     (sid, i["product_id"], i["product_name"], i["quantity"], i["unit_price"], i["subtotal"]))
            self.adj_stock(i["product_id"], -i["quantity"])
        
        # ── Si es a crédito, aumentar deuda del cliente ──
        if payment == "crédito" and client_id:
            self.run("UPDATE clients SET debt = debt + ? WHERE id=?", (total, client_id))
            
        log.info(f"Venta #{sid}: {len(items)} ítem(s), total ${total:.0f}, pago:{payment}")
        return sid

    def delete_sale(self, sale_id):
        for i in self.get_sale_items(sale_id):
            if i["product_id"]: self.adj_stock(i["product_id"], i["quantity"])
        self.run("DELETE FROM sales WHERE id=?", (sale_id,))
        log.info(f"Venta #{sale_id} anulada, stock restaurado")

    def get_sales(self, d1, d2):
        return self.all(
            "SELECT s.*, COALESCE(c.name,'Mostrador') cn, u.username uname"
            " FROM sales s LEFT JOIN clients c ON s.client_id=c.id"
            " LEFT JOIN users u ON s.user_id=u.id"
            " WHERE s.date BETWEEN ? AND ? ORDER BY s.date DESC, s.time DESC", (d1,d2))
    def get_sale_items(self, sid): return self.all("SELECT * FROM sale_items WHERE sale_id=?", (sid,))

    def summary(self, d1, d2):
        return self.one("SELECT COUNT(*) cnt, COALESCE(SUM(total),0) revenue,"
                        " COALESCE(SUM(discount),0) disc FROM sales WHERE date BETWEEN ? AND ?", (d1,d2))
    def profit_summary(self, d1, d2):
        return self.one(
            "SELECT COALESCE(SUM(si.subtotal - si.quantity*COALESCE(p.cost,0)),0) profit"
            " FROM sale_items si JOIN sales s ON si.sale_id=s.id"
            " LEFT JOIN products p ON si.product_id=p.id"
            " WHERE s.date BETWEEN ? AND ?", (d1,d2))
    def expenses_summary(self, d1, d2):
        return self.one("SELECT COALESCE(SUM(amount),0) total FROM expenses WHERE date BETWEEN ? AND ?", (d1,d2))
    def top_products(self, d1, d2, n=10):
        return self.all(
            "SELECT si.product_name pname, SUM(si.quantity) qty, SUM(si.subtotal) rev"
            " FROM sale_items si JOIN sales s ON si.sale_id=s.id"
            " WHERE s.date BETWEEN ? AND ? GROUP BY si.product_name ORDER BY qty DESC LIMIT ?", (d1,d2,n))

    # ── Gastos ───────────────────────────────────────────────
    def get_expenses(self, d1, d2):
        return self.all(
            "SELECT e.*, u.username uname FROM expenses e"
            " JOIN users u ON e.user_id = u.id"
            " WHERE e.date BETWEEN ? AND ? ORDER BY e.timestamp DESC", (d1, d2))

    def add_expense(self, user_id, session_id, category, amount, description, affect_cash=True):
        now = datetime.now()
        eid = self.run(
            "INSERT INTO expenses(user_id,session_id,date,category,amount,description,timestamp) VALUES(?,?,?,?,?,?,?)",
            (user_id, session_id if affect_cash else None, now.strftime("%Y-%m-%d"), category, amount, description, now.strftime("%Y-%m-%d %H:%M:%S")))
        if affect_cash and session_id:
            desc = f"Gasto: {category}"
            if description: desc += f" ({description})"
            self.add_cash_transaction(session_id, "outcome", amount, desc)
        log.info(f"Gasto registrado: {category} ${amount:.0f}")
        return eid
    def sales_by_day(self, d1, d2):
        return self.all("SELECT date, COALESCE(SUM(total),0) rev, COUNT(*) cnt"
                        " FROM sales WHERE date BETWEEN ? AND ? GROUP BY date ORDER BY date", (d1,d2))
    def sales_by_payment(self, d1, d2):
        return self.all("SELECT payment_method pm, COALESCE(SUM(total),0) total"
                        " FROM sales WHERE date BETWEEN ? AND ? GROUP BY payment_method", (d1,d2))
    def sales_by_category(self, d1, d2):
        return self.all(
            "SELECT COALESCE(p.category,'Sin categoría') cat, SUM(si.subtotal) rev"
            " FROM sale_items si JOIN sales s ON si.sale_id=s.id"
            " LEFT JOIN products p ON si.product_id=p.id"
            " WHERE s.date BETWEEN ? AND ? GROUP BY cat ORDER BY rev DESC", (d1,d2))

    def export_sales_excel(self, filepath, d1, d2):
        if not HAS_PD: raise ImportError("pip install pandas openpyxl")
        sales = self.get_sales(d1, d2)
        rows = []
        for s in sales:
            for it in self.get_sale_items(s["id"]):
                rows.append({"ID Venta":s["id"],"Fecha":s["date"],"Hora":s["time"],
                    "Cliente":s["cn"],"Vendedor":s["uname"],"Producto":it["product_name"],
                    "Cantidad":it["quantity"],"Precio Unitario":it["unit_price"],
                    "Subtotal":it["subtotal"],"Total Venta":s["total"],"Pago":s["payment_method"]})
        pd.DataFrame(rows).to_excel(filepath, index=False)
        log.info(f"Ventas exportadas: {filepath}")

    def close(self): self.con.close()


# ═══════════════════════════════════════════════════════════════
# HELPERS DE UI
# ═══════════════════════════════════════════════════════════════
_DB: DB = None

def fmt(v) -> str:
    sym = _DB.cfg("currency_symbol") if _DB else "$"
    try:    return f"{sym} {float(v):,.0f}"
    except: return f"{sym} 0"

def style_tree():
    s = ttk.Style(); s.theme_use("clam")
    s.configure("G.Treeview", background=CARD, foreground=TEXT, fieldbackground=CARD,
                rowheight=_sc(28), font=("Segoe UI", _sc(10)), borderwidth=0)
    s.configure("G.Treeview.Heading", background="#111", foreground=ACC,
                font=("Segoe UI", _sc(10), "bold"), relief="flat")
    s.map("G.Treeview", background=[("selected",ACC)], foreground=[("selected","white")])
    s.configure("TScrollbar", background="#333", troughcolor="#222", arrowcolor="#888", borderwidth=0)

def W_entry(m, ph="", w=200, pw=False):
    return ctk.CTkEntry(m, width=_sc(w), placeholder_text=ph, show="*" if pw else "", font=("Segoe UI", _sc(11)))
def W_label(m, t, size=11, color=TEXT, bold=False, **kw):
    return ctk.CTkLabel(m, text=t, font=("Segoe UI", _sc(size), "bold" if bold else "normal"), text_color=color, **kw)
def W_btn(m, t, cmd, color=ACC, w=130, h=34):
    return ctk.CTkButton(m, text=t, command=cmd, width=_sc(w), height=_sc(h),
                         fg_color=color, hover_color=ACCH, font=("Segoe UI", _sc(11), "bold"))
def W_card(m, **kw): return ctk.CTkFrame(m, fg_color=CARD, corner_radius=_sc(10), **kw)
def W_combo(m, vals, w=200): return ctk.CTkComboBox(m, values=vals, width=_sc(w), font=("Segoe UI", _sc(11)))
def W_sep(m): ctk.CTkFrame(m, fg_color="#2e2e2e", height=1).pack(fill="x", padx=8, pady=3)

def make_tree(parent, cols, hdrs, widths, height=None):
    kw = {"height": height} if height else {}
    tree = ttk.Treeview(parent, columns=cols, show="headings", style="G.Treeview", **kw)
    for c, h, w in zip(cols, hdrs, widths):
        tree.heading(c, text=h); tree.column(c, width=_sc(w), minwidth=_sc(30))
    sb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y", pady=5, padx=(0,4))
    tree.pack(fill="both", expand=True, padx=5, pady=5)
    return tree


# ═══════════════════════════════════════════════════════════════
# WIZARD DE PRIMER ARRANQUE
# ═══════════════════════════════════════════════════════════════
class SetupWizard(ctk.CTk):
    """Asistente de configuración inicial — se muestra solo la primera vez."""

    BUSINESS_TYPES = [
        "Tienda General", "Minimercado", "Papelería", "Ferretería",
        "Droguería", "Restaurante", "Cafetería", "Panadería",
        "Licorería", "Tienda de Ropa", "Tienda de Tecnología",
        "Veterinaria", "Peluquería", "Otro",
    ]
    CURRENCIES = [
        ("$", "COP — Peso colombiano"),
        ("$", "USD — Dólar americano"),
        ("€", "EUR — Euro"),
        ("S/", "PEN — Sol peruano"),
        ("$", "MXN — Peso mexicano"),
        ("Bs", "VES — Bolívar"),
    ]

    def __init__(self, db: DB):
        super().__init__()
        self.db = db
        self.completed = False
        self._step = 0
        self.title("GestiónPro — Configuración Inicial")
        w, h = _sc(560), _sc(520)
        self.geometry(f"{w}x{h}")
        self.resizable(False, False)
        self.configure(fg_color=BG)
        self._data = {
            "business_name": "", "business_type": self.BUSINESS_TYPES[0],
            "currency_symbol": "$", "currency_code": "COP",
            "address": "", "phone": "", "tax_percent": "0",
            "admin_user": "admin", "admin_pass": "",
        }
        self._frames: list[ctk.CTkFrame] = []
        self._build()

    # ── Barra de pasos ────────────────────────────────────────
    def _build(self):
        self._top = ctk.CTkFrame(self, fg_color=SIDEBAR, height=_sc(62), corner_radius=0)
        self._top.pack(fill="x")
        self._top.pack_propagate(False)
        self._step_labels: list[ctk.CTkLabel] = []
        steps = ["Bienvenida", "Negocio", "Moneda", "Admin", "¡Listo!"]
        row = ctk.CTkFrame(self._top, fg_color="transparent")
        row.pack(expand=True)
        for i, name in enumerate(steps):
            lbl = ctk.CTkLabel(row, text=f"  {i+1}. {name}  ",
                               font=("Segoe UI", _sc(10)),
                               text_color=DIM, corner_radius=_sc(6))
            lbl.pack(side="left", padx=_sc(3), pady=_sc(16))
            self._step_labels.append(lbl)

        self._body = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self._body.pack(fill="both", expand=True)

        self._build_step0()
        self._build_step1()
        self._build_step2()
        self._build_step3()
        self._build_step4()
        self._show_step(0)

    def _show_step(self, idx):
        self._step = idx
        for f in self._frames:
            f.pack_forget()
        self._frames[idx].pack(fill="both", expand=True, padx=_sc(40), pady=_sc(20))
        for i, lbl in enumerate(self._step_labels):
            if i == idx:
                lbl.configure(text_color=TEXT, fg_color=ACC)
            elif i < idx:
                lbl.configure(text_color=OK, fg_color="transparent")
            else:
                lbl.configure(text_color=DIM, fg_color="transparent")

    def _nav_bar(self, parent, back=True, next_text="Siguiente  →", cmd_next=None):
        """Barra inferior con botones Atrás / Siguiente."""
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.pack(side="bottom", fill="x", pady=(_sc(10), 0))
        if back:
            W_btn(bar, "←  Atrás", lambda: self._show_step(self._step - 1),
                  color="#333", w=120, h=38).pack(side="left")
        W_btn(bar, next_text, cmd_next or (lambda: self._show_step(self._step + 1)),
              w=180, h=38).pack(side="right")

    # ── Paso 0: Bienvenida ────────────────────────────────────
    def _build_step0(self):
        f = ctk.CTkFrame(self._body, fg_color="transparent")
        self._frames.append(f)
        W_label(f, "🏪", size=48).pack(pady=(_sc(30), _sc(8)))
        W_label(f, "¡Bienvenido a GestiónPro!", size=22, bold=True, color=ACC).pack()
        W_label(f, "Sistema de gestión para tu negocio", size=12, color=DIM).pack(pady=(_sc(4), _sc(20)))
        msg = ("Vamos a configurar tu negocio en unos pocos pasos.\n"
               "Solo tomará un minuto y podrás cambiar\n"
               "todo después desde Configuración.")
        W_label(f, msg, size=11, color=TEXT).pack(pady=_sc(8))
        self._nav_bar(f, back=False, next_text="Comenzar  →")

    # ── Paso 1: Nombre y tipo de negocio ──────────────────────
    def _build_step1(self):
        f = ctk.CTkFrame(self._body, fg_color="transparent")
        self._frames.append(f)
        W_label(f, "📋  Tu Negocio", size=18, bold=True, color=ACC).pack(anchor="w")
        W_label(f, "¿Cómo se llama tu negocio?", size=10, color=DIM).pack(anchor="w", pady=(_sc(16), _sc(4)))
        self._e_name = W_entry(f, "Ej: Tienda La Esquina", w=440)
        self._e_name.pack(anchor="w")

        W_label(f, "Tipo de negocio", size=10, color=DIM).pack(anchor="w", pady=(_sc(14), _sc(4)))
        self._cb_type = W_combo(f, self.BUSINESS_TYPES, w=440)
        self._cb_type.set(self.BUSINESS_TYPES[0])
        self._cb_type.pack(anchor="w")

        W_label(f, "Dirección (opcional)", size=10, color=DIM).pack(anchor="w", pady=(_sc(14), _sc(4)))
        self._e_addr = W_entry(f, "Ej: Calle 10 #25-30", w=440)
        self._e_addr.pack(anchor="w")

        W_label(f, "Teléfono / Contacto (opcional)", size=10, color=DIM).pack(anchor="w", pady=(_sc(14), _sc(4)))
        self._e_phone = W_entry(f, "Ej: 300 123 4567", w=440)
        self._e_phone.pack(anchor="w")

        self._l_err1 = W_label(f, "", color=ERR, size=10)
        self._l_err1.pack(pady=(_sc(6), 0))

        def _next1():
            name = self._e_name.get().strip()
            if not name:
                self._l_err1.configure(text="El nombre del negocio es obligatorio")
                return
            self._l_err1.configure(text="")
            self._data["business_name"] = name
            self._data["business_type"] = self._cb_type.get()
            self._data["address"] = self._e_addr.get().strip()
            self._data["phone"] = self._e_phone.get().strip()
            self._show_step(2)

        self._nav_bar(f, back=True, cmd_next=_next1)

    # ── Paso 2: Moneda e impuesto ─────────────────────────────
    def _build_step2(self):
        f = ctk.CTkFrame(self._body, fg_color="transparent")
        self._frames.append(f)
        W_label(f, "💲  Moneda e Impuestos", size=18, bold=True, color=ACC).pack(anchor="w")

        W_label(f, "Moneda", size=10, color=DIM).pack(anchor="w", pady=(_sc(16), _sc(4)))
        currency_names = [c[1] for c in self.CURRENCIES]
        self._cb_currency = W_combo(f, currency_names, w=440)
        self._cb_currency.set(currency_names[0])
        self._cb_currency.pack(anchor="w")

        W_label(f, "Impuesto sobre ventas (%)", size=10, color=DIM).pack(anchor="w", pady=(_sc(14), _sc(4)))
        W_label(f, "Pon 0 si no aplica impuesto", size=9, color=DIM).pack(anchor="w")
        self._e_tax = W_entry(f, "0", w=200)
        self._e_tax.insert(0, "0")
        self._e_tax.pack(anchor="w", pady=(_sc(4), 0))

        W_label(f, "Stock mínimo por defecto", size=10, color=DIM).pack(anchor="w", pady=(_sc(14), _sc(4)))
        W_label(f, "Alerta cuando un producto baje de esta cantidad", size=9, color=DIM).pack(anchor="w")
        self._e_stock = W_entry(f, "5", w=200)
        self._e_stock.insert(0, "5")
        self._e_stock.pack(anchor="w", pady=(_sc(4), 0))

        self._l_err2 = W_label(f, "", color=ERR, size=10)
        self._l_err2.pack(pady=(_sc(6), 0))

        def _next2():
            try:
                tax = float(self._e_tax.get().strip())
                stock_min = int(self._e_stock.get().strip())
                if tax < 0 or stock_min < 0:
                    raise ValueError
            except ValueError:
                self._l_err2.configure(text="Valores numéricos inválidos")
                return
            self._l_err2.configure(text="")
            # Buscar símbolo y código de la moneda seleccionada
            sel = self._cb_currency.get()
            for sym, label in self.CURRENCIES:
                if label == sel:
                    self._data["currency_symbol"] = sym
                    self._data["currency_code"] = label[:3]
                    break
            self._data["tax_percent"] = str(int(tax)) if tax == int(tax) else str(tax)
            self._data["low_stock_limit"] = str(stock_min)
            self._show_step(3)

        self._nav_bar(f, back=True, cmd_next=_next2)

    # ── Paso 3: Contraseña del admin ──────────────────────────
    def _build_step3(self):
        f = ctk.CTkFrame(self._body, fg_color="transparent")
        self._frames.append(f)
        W_label(f, "🔐  Contraseña del Administrador", size=18, bold=True, color=ACC).pack(anchor="w")
        W_label(f, "El usuario administrador será:", size=10, color=DIM).pack(anchor="w", pady=(_sc(16), _sc(2)))

        W_label(f, "Usuario", size=10, color=DIM).pack(anchor="w", pady=(_sc(8), _sc(4)))
        self._e_admin_user = W_entry(f, "admin", w=440)
        self._e_admin_user.insert(0, "admin")
        self._e_admin_user.pack(anchor="w")

        W_label(f, "Nueva contraseña", size=10, color=DIM).pack(anchor="w", pady=(_sc(14), _sc(4)))
        self._e_pass1 = W_entry(f, "••••••••", w=440, pw=True)
        self._e_pass1.pack(anchor="w")

        W_label(f, "Confirmar contraseña", size=10, color=DIM).pack(anchor="w", pady=(_sc(14), _sc(4)))
        self._e_pass2 = W_entry(f, "••••••••", w=440, pw=True)
        self._e_pass2.pack(anchor="w")

        self._l_err3 = W_label(f, "", color=ERR, size=10)
        self._l_err3.pack(pady=(_sc(6), 0))

        def _next3():
            user = self._e_admin_user.get().strip().lower()
            p1 = self._e_pass1.get()
            p2 = self._e_pass2.get()
            if not user:
                self._l_err3.configure(text="El nombre de usuario es obligatorio")
                return
            if len(p1) < 4:
                self._l_err3.configure(text="La contraseña debe tener al menos 4 caracteres")
                return
            if p1 != p2:
                self._l_err3.configure(text="Las contraseñas no coinciden")
                return
            self._l_err3.configure(text="")
            self._data["admin_user"] = user
            self._data["admin_pass"] = p1
            # Actualizar el resumen en paso 4
            self._update_summary()
            self._show_step(4)

        self._nav_bar(f, back=True, cmd_next=_next3)

    # ── Paso 4: Confirmación ──────────────────────────────────
    def _build_step4(self):
        f = ctk.CTkFrame(self._body, fg_color="transparent")
        self._frames.append(f)
        W_label(f, "✅  ¡Todo listo!", size=22, bold=True, color=OK).pack(pady=(_sc(10), _sc(12)))
        W_label(f, "Revisa la configuración de tu negocio:", size=11, color=DIM).pack()
        self._summary_card = W_card(f)
        self._summary_card.pack(fill="x", pady=_sc(14))
        # Se llenará dinámicamente
        self._summary_labels: list[ctk.CTkLabel] = []
        self._nav_bar(f, back=True, next_text="🚀  Iniciar GestiónPro", cmd_next=self._finish)

    def _update_summary(self):
        for w in self._summary_card.winfo_children():
            w.destroy()
        items = [
            ("Negocio", self._data["business_name"]),
            ("Tipo", self._data["business_type"]),
            ("Moneda", f"{self._data['currency_symbol']}  ({self._data['currency_code']})"),
            ("Impuesto", f"{self._data['tax_percent']}%"),
            ("Dirección", self._data["address"] or "—"),
            ("Teléfono", self._data["phone"] or "—"),
            ("Admin", self._data["admin_user"]),
        ]
        for label, value in items:
            row = ctk.CTkFrame(self._summary_card, fg_color="transparent")
            row.pack(fill="x", padx=_sc(20), pady=_sc(4))
            W_label(row, label, size=10, color=DIM).pack(side="left")
            W_label(row, value, size=10, bold=True, color=TEXT).pack(side="right")

    def _finish(self):
        d = self._data
        # Guardar toda la configuración
        for key in ["business_name", "business_type", "currency_symbol",
                     "currency_code", "address", "phone", "tax_percent"]:
            self.db.set_cfg(key, d[key])
        if "low_stock_limit" in d:
            self.db.set_cfg("low_stock_limit", d["low_stock_limit"])
        # Actualizar usuario admin
        admin = self.db.one("SELECT * FROM users WHERE username='admin'")
        if admin:
            self.db.run("UPDATE users SET username=?, password=?, role='admin' WHERE id=?",
                        (d["admin_user"], self.db._hp(d["admin_pass"]), admin["id"]))
        else:
            self.db.add_user(d["admin_user"], d["admin_pass"], "admin")
        # Marcar wizard como completado
        self.db.set_cfg("wizard_done", "1")
        log.info(f"Wizard completado — Negocio: {d['business_name']}")
        self.completed = True
        self.destroy()


# ═══════════════════════════════════════════════════════════════
# LOGIN
# ═══════════════════════════════════════════════════════════════
class LoginWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.result = None
        self.title(f"GestiónPro — {_DB.cfg('business_name')}")
        w, h = _sc(460), _sc(540)
        self.geometry(f"{w}x{h}"); self.resizable(False, False)
        self.configure(fg_color=BG)
        self._build()

    def _build(self):
        card = W_card(self); card.pack(expand=True, padx=_sc(40), pady=_sc(45), fill="both")

        # ── Logo: imagen de config o emoji por defecto ─────────────────
        logo_path = _DB.cfg("logo_path")
        logo_shown = False
        if logo_path and os.path.isfile(logo_path):
            try:
                from PIL import Image
                pil_img = Image.open(logo_path).convert("RGBA")
                # Redimensionar proporcional: máx 160×110px
                max_w, max_h = _sc(160), _sc(110)
                orig_w, orig_h = pil_img.size
                ratio = min(max_w / orig_w, max_h / orig_h)
                new_w = max(1, int(orig_w * ratio))
                new_h = max(1, int(orig_h * ratio))
                pil_img = pil_img.resize((new_w, new_h), Image.LANCZOS)
                ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img,
                                       size=(new_w, new_h))
                ctk.CTkLabel(card, image=ctk_img, text="",
                             fg_color="transparent").pack(pady=(_sc(18), _sc(6)))
                logo_shown = True
            except Exception:
                pass
        if not logo_shown:
            W_label(card, "🏪", size=42).pack(pady=(_sc(30), _sc(4)))

        W_label(card, _DB.cfg("business_name"), size=20, bold=True, color=ACC,
                wraplength=_sc(340)).pack()
        W_label(card, _DB.cfg("business_type"), size=11, color=DIM).pack(pady=(_sc(2), _sc(26)))
        W_label(card, "Usuario", size=10, color=DIM).pack(anchor="w", padx=_sc(36))
        self.eu = W_entry(card, "usuario", w=320); self.eu.pack(padx=_sc(36), pady=(_sc(2), _sc(10)))
        W_label(card, "Contraseña", size=10, color=DIM).pack(anchor="w", padx=_sc(36))
        self.ep = W_entry(card, "••••••••", w=320, pw=True); self.ep.pack(padx=_sc(36), pady=(_sc(2), _sc(6)))
        self.lerr = W_label(card, "", color=ERR, size=10); self.lerr.pack()
        W_btn(card, "  Ingresar  →", self._login, w=320, h=42).pack(padx=_sc(36), pady=(_sc(8), _sc(30)))
        self.eu.bind("<Return>", lambda _: self.ep.focus())
        self.ep.bind("<Return>", lambda _: self._login())

    def _login(self):
        u = self.eu.get().strip().lower(); p = self.ep.get().strip()
        if not u or not p: self.lerr.configure(text="Completa todos los campos"); return
        row = _DB.login(u, p)
        if row: log.info(f"Login: {u}"); self.result = row; self.destroy()
        else: self.lerr.configure(text="❌  Usuario o contraseña incorrectos"); self.ep.delete(0,"end")


# ═══════════════════════════════════════════════════════════════
# VENTANA PRINCIPAL
# ═══════════════════════════════════════════════════════════════
class MainWindow(ctk.CTk):
    def __init__(self, user: dict):
        super().__init__()
        self.user = user
        self.title(f"GestiónPro — {_DB.cfg('business_name')}")
        self.geometry(f"{_sc(1220)}x{_sc(740)}"); self.minsize(_sc(900), _sc(580))
        self.configure(fg_color=BG)
        style_tree(); self._build(); self._nav(DashboardPanel)

    def _build(self):
        sb = ctk.CTkFrame(self, fg_color=SIDEBAR, width=_sc(215), corner_radius=0)
        sb.pack(side="left", fill="y"); sb.pack_propagate(False)
        ctk.CTkFrame(sb, fg_color=ACC, height=_sc(3), corner_radius=0).pack(fill="x")
        W_label(sb, "🏪", size=30).pack(pady=(_sc(18), 0))
        W_label(sb, _DB.cfg("business_name"), size=12, bold=True, color=ACC, wraplength=_sc(190)).pack()
        W_label(sb, f"👤  {self.user['username']}  ·  {self.user['role']}", size=9, color=DIM).pack(pady=(_sc(2), _sc(10)))
        W_sep(sb)
        self._nav_btns: dict = {}
        items = [
            ("📊  Dashboard",       DashboardPanel),
            ("📦  Inventario",      InventarioPanel),
            ("👥  Clientes",        ClientesPanel),
            ("🛒  Punto de Venta",  VentaPanel),
            ("💸  Gastos",          GastosPanel),
            ("💰  Caja",            CierreCajaPanel),
            ("📄  Informes",        InformesPanel),
        ]
        if self.user["role"] == "admin":
            items += [
                ("📂  Categorías",    CategoriasPanel),
                ("👤  Usuarios",      UsuariosPanel),
                ("⚙  Configuración", ConfigPanel),
            ]
        for text, PanelCls in items:
            b = ctk.CTkButton(sb, text=text, anchor="w", height=_sc(42),
                fg_color="transparent", hover_color="#2a2a2a",
                font=("Segoe UI", _sc(11)), corner_radius=_sc(8),
                command=lambda pc=PanelCls: self._nav(pc))
            b.pack(fill="x", padx=_sc(8), pady=_sc(2))
            self._nav_btns[PanelCls] = b
        W_sep(sb)
        W_btn(sb, "🚪  Cerrar sesión", self.destroy, color="#2a2a2a", w=195).pack(pady=_sc(10), padx=_sc(10))
        # ── Indicador de licencia al fondo de la sidebar ──
        lic_frame = ctk.CTkFrame(sb, fg_color="transparent")
        lic_frame.pack(side="bottom", fill="x", padx=_sc(10), pady=(_sc(4), _sc(10)))
        if _LIC_INFO:
            if _LIC_INFO["permanente"]:
                lic_icon = "🟢"
                lic_text = "Licencia permanente"
                lic_color = OK
            else:
                dias = _LIC_INFO["dias_restantes"]
                if dias > 90:
                    lic_icon = "🟢"; lic_color = OK
                elif dias > 30:
                    lic_icon = "🟡"; lic_color = WARN
                else:
                    lic_icon = "🔴"; lic_color = ERR
                lic_text = f"{dias} días de licencia"
            W_label(lic_frame, f"{lic_icon}  {lic_text}", size=9, color=lic_color).pack()
        self.content = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.content.pack(side="left", fill="both", expand=True)

    def _nav(self, PanelCls):
        for w in self.content.winfo_children(): w.destroy()
        panel = PanelCls(self.content, _DB, self.user)
        panel.pack(fill="both", expand=True, padx=20, pady=15)
        for cls, btn in self._nav_btns.items():
            btn.configure(fg_color=ACC if cls==PanelCls else "transparent")


# ═══════════════════════════════════════════════════════════════
# PANEL BASE
# ═══════════════════════════════════════════════════════════════
class BasePanel(ctk.CTkFrame):
    def __init__(self, master, db: DB, user: dict, title=""):
        super().__init__(master, fg_color="transparent")
        self.db = db; self.user = user
        if title: W_label(self, title, size=18, bold=True).pack(anchor="w", pady=(0,10))


# ═══════════════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════════════
class DashboardPanel(BasePanel):
    def __init__(self, master, db, user):
        super().__init__(master, db, user); self._build()

    def _build(self):
        today = date.today(); d1 = today.isoformat(); d30 = (today-timedelta(days=30)).isoformat()
        hdr = ctk.CTkFrame(self, fg_color="transparent"); hdr.pack(fill="x", pady=(0,12))
        W_label(hdr, "📊 Dashboard", size=18, bold=True).pack(side="left")
        W_label(hdr, today.strftime("   %A %d de %B %Y"), size=11, color=DIM).pack(side="left", pady=6)

        s  = self.db.summary(d1, d1); pr = self.db.profit_summary(d1, d1)
        ls = self.db.low_stock();     iv = self.db.inventory_value()
        exp = self.db.expenses_summary(d1, d1)
        net_profit = pr["profit"] - exp["total"]

        row = ctk.CTkFrame(self, fg_color="transparent"); row.pack(fill="x")
        for icon, lbl, val, color in [
            ("💰","Ingresos Hoy",   fmt(s["revenue"]),  OK),
            ("📈","Ganancia Neta",  fmt(net_profit),    PURPLE),
            ("💸","Gastos Hoy",     fmt(exp["total"]),  WARN),
            ("🛒","Ventas Hoy",     str(s["cnt"]),      ACC),
            ("⚠️","Stock Crítico",  str(len(ls)),        ERR if ls else DIM),
        ]:
            c = W_card(row); c.pack(side="left", expand=True, fill="x", padx=(0,6))
            W_label(c, icon, size=26).pack(pady=(14,2))
            W_label(c, str(val), size=18, bold=True, color=color).pack()
            W_label(c, lbl, size=9, color=DIM).pack(pady=(0,14))

        bot = ctk.CTkFrame(self, fg_color="transparent"); bot.pack(fill="both", expand=True, pady=(12,0))
        top = self.db.top_products(d30, d1, 7)
        lc = W_card(bot); lc.pack(side="left", fill="both", expand=True, padx=(0,8))
        W_label(lc, "🏆  Más vendidos — 30 días", bold=True, color=ACC, size=11).pack(pady=(14,4))
        W_sep(lc)
        if top:
            for i, p in enumerate(top, 1):
                r = ctk.CTkFrame(lc, fg_color="transparent"); r.pack(fill="x", padx=16, pady=3)
                W_label(r, f"{i}.  {p['pname']}", size=10).pack(side="left")
                W_label(r, f"{int(p['qty'])} uds  ·  {fmt(p['rev'])}", size=10, color=DIM).pack(side="right")
        else:
            W_label(lc, "Sin ventas aún", color=DIM, size=10).pack(pady=20)
        rc = W_card(bot); rc.pack(side="left", fill="both", expand=True)
        W_label(rc, "⚠️  Stock Crítico", bold=True, color=WARN, size=11).pack(pady=(14,4))
        W_sep(rc)
        if ls:
            for p in ls[:7]:
                r = ctk.CTkFrame(rc, fg_color="transparent"); r.pack(fill="x", padx=16, pady=3)
                W_label(r, p["name"], size=10).pack(side="left")
                W_label(r, f"{p['stock']} {p['unit']}", size=10, color=ERR).pack(side="right")
        else:
            W_label(rc, "✅  Inventario OK", color=OK, size=10).pack(pady=12)
        W_sep(rc)
        W_label(rc, f"Inventario (venta): {fmt(iv['venta'])}", size=10, color=OK).pack(padx=14, pady=2, anchor="w")
        W_label(rc, f"Inventario (costo): {fmt(iv['costo'])}", size=10, color=DIM).pack(padx=14, pady=(0,12), anchor="w")


# ═══════════════════════════════════════════════════════════════
# INVENTARIO
# ═══════════════════════════════════════════════════════════════
class InventarioPanel(BasePanel):
    PAGE_SIZE = 100
    def __init__(self, master, db, user):
        super().__init__(master, db, user, "📦 Inventario")
        self._sel = None; self._page = 1; self._build(); self._refresh()

    def _build(self):
        is_admin = self.user["role"] == "admin"
        tb1 = ctk.CTkFrame(self, fg_color="transparent"); tb1.pack(fill="x", pady=(0,4))
        self.e_search = W_entry(tb1, "🔍  Nombre, SKU, proveedor...", w=270); self.e_search.pack(side="left")
        self.e_search.bind("<KeyRelease>", lambda _: self._go_page(1))
        W_label(tb1, "  Categoría:", size=10, color=DIM).pack(side="left")
        cats = ["Todas"] + self.db.get_categories()
        self.cb_cat = W_combo(tb1, cats, w=150); self.cb_cat.pack(side="left", padx=(4,12))
        self.cb_cat.bind("<ButtonRelease>", lambda _: self.after(100, lambda: self._go_page(1)))
        self.l_val = W_label(tb1, "", size=10, color=OK); self.l_val.pack(side="right", padx=8)

        tb2 = ctk.CTkFrame(self, fg_color="transparent"); tb2.pack(fill="x", pady=(0,6))
        W_btn(tb2, "➕ Nuevo",    self._new,    w=110).pack(side="left")
        W_btn(tb2, "✏️ Editar",   self._edit,   w=110, color="#444").pack(side="left", padx=3)
        W_btn(tb2, "📦 Stock",    self._adj,    w=100, color=WARN).pack(side="left", padx=3)
        if is_admin: W_btn(tb2, "🗑 Eliminar", self._del, w=110, color=ERR).pack(side="left", padx=3)
        W_btn(tb2, "📥 Excel",    self._import, w=100, color="#444").pack(side="left", padx=3)
        W_btn(tb2, "📤 Exportar", self._export, w=110, color="#444").pack(side="left", padx=3)
        if is_admin: W_btn(tb2, "🧹 Limpiar", self._clean, w=120, color="#555").pack(side="left", padx=3)

        frm = W_card(self); frm.pack(fill="both", expand=True)
        self.tree = make_tree(frm,
            ("id","sku","name","category","price","cost","margin","supplier","stock","unit"),
            ("ID","SKU","Nombre","Categoría","P.Venta","P.Compra","Margen","Proveedor","Stock","Unidad"),
            (40,80,185,95,95,90,70,140,60,65))
        self.tree.tag_configure("low", foreground=ERR)
        self.tree.bind("<<TreeviewSelect>>", lambda _: self._on_sel())
        self.tree.bind("<Double-1>", lambda _: self._edit())

        pf = ctk.CTkFrame(self, fg_color="transparent"); pf.pack(fill="x", pady=(4,0))
        W_btn(pf, "«", lambda: self._go_page(1),             color="#333", w=36, h=28).pack(side="left")
        W_btn(pf, "‹", lambda: self._go_page(self._page-1),  color="#333", w=36, h=28).pack(side="left", padx=2)
        self.l_page = W_label(pf, "Pág 1 / 1", size=10, color=DIM); self.l_page.pack(side="left", padx=6)
        W_btn(pf, "›", lambda: self._go_page(self._page+1),  color="#333", w=36, h=28).pack(side="left")
        W_btn(pf, "»", lambda: self._go_page(9999),           color="#333", w=36, h=28).pack(side="left", padx=2)
        self.l_count = W_label(pf, "", size=10, color=DIM); self.l_count.pack(side="right", padx=8)

    def _on_sel(self):
        s = self.tree.selection()
        self._sel = int(self.tree.item(s[0])["values"][0]) if s else None

    def _refresh(self):
        cat    = self.cb_cat.get() if hasattr(self,"cb_cat") else "Todas"
        search = self.e_search.get().strip() if hasattr(self,"e_search") else ""
        rows, total = self.db.get_products(search, cat, self._page, self.PAGE_SIZE)
        max_page = max(1, (total+self.PAGE_SIZE-1)//self.PAGE_SIZE)
        if self._page > max_page: self._page = max_page
        self.tree.delete(*self.tree.get_children())
        low_ids = {p["id"] for p in self.db.low_stock()}
        for p in rows:
            margin = ((p["price"]-p["cost"])/p["price"]*100) if p["price"]>0 else 0
            tag = ("low",) if p["id"] in low_ids else ()
            self.tree.insert("","end", tags=tag, values=(
                p["id"],p["sku"],p["name"],p["category"],
                fmt(p["price"]),fmt(p["cost"]),f"{margin:.1f}%",
                p["supplier"],p["stock"],p["unit"]))
        start = (self._page-1)*self.PAGE_SIZE+1 if total else 0
        end   = min(self._page*self.PAGE_SIZE, total)
        self.l_page.configure(text=f"Pág {self._page} / {max_page}")
        self.l_count.configure(text=f"Mostrando {start}–{end} de {total} productos")
        iv = self.db.inventory_value()
        self.l_val.configure(text=f"Stock: {fmt(iv['venta'])} (venta)  ·  {fmt(iv['costo'])} (costo)")

    def _go_page(self, p):
        cat = self.cb_cat.get(); search = self.e_search.get().strip()
        _, total = self.db.get_products(search, cat, 1, self.PAGE_SIZE)
        max_page = max(1, (total+self.PAGE_SIZE-1)//self.PAGE_SIZE)
        self._page = max(1, min(p, max_page))
        self._refresh()

    def _form(self, title, data=None):
        dlg = ctk.CTkToplevel(self); dlg.title(title); dlg.geometry(f"{_sc(700)}x{_sc(480)}"); dlg.grab_set()
        dlg.configure(fg_color=BG)
        W_label(dlg, title, size=16, bold=True, color=ACC).pack(pady=(20,10))
        
        container = ctk.CTkFrame(dlg, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=_sc(20), pady=_sc(10))
        container.columnconfigure(0, weight=1, pad=_sc(15))
        container.columnconfigure(1, weight=1, pad=_sc(15))

        cats = self.db.get_categories()
        fields = [
            ("Nombre *",              "name",      str,   ""),
            ("SKU (vacío=automático)","sku",        str,   ""),
            ("Código de barras",       "barcode",   str,   ""),
            ("Categoría",              "category",  "combo", cats[0] if cats else "General"),
            ("Precio de Venta *",      "price",     float, "0"),
            ("Precio de Compra",       "cost",      float, "0"),
            ("Proveedor",              "supplier",  str,   ""),
            ("Stock Inicial",          "stock",     int,   "0"),
            ("Stock Mínimo",           "min_stock", int,   "5"),
            ("Unidad (kg, lt, caja…)", "unit",      str,   "unidad"),
        ]
        entries = {}
        for i, (lbl, key, typ, default) in enumerate(fields):
            row = i // 2
            col = i % 2
            f_frame = ctk.CTkFrame(container, fg_color="transparent")
            f_frame.grid(row=row, column=col, sticky="ew", padx=_sc(8), pady=_sc(8))
            
            W_label(f_frame, lbl, size=10, color=DIM).pack(anchor="w", pady=(0, 2))
            if typ == "combo":
                w = W_combo(f_frame, cats, w=300); w.pack(fill="x")
                w.set(str(data.get(key, default)) if data else default)
            else:
                w = W_entry(f_frame, w=300)
                val = str(data.get(key,"")) if data else default
                if val: w.insert(0, val)
                w.pack(fill="x")
            entries[key] = w

        def save():
            try:
                name     = entries["name"].get().strip().capitalize()
                if not name: messagebox.showerror("Error","Nombre obligatorio",parent=dlg); return
                sku_raw  = entries["sku"].get().strip()
                sku      = int(sku_raw) if sku_raw else None
                barcode  = entries["barcode"].get().strip()
                category = entries["category"].get().strip() or "General"
                price    = float(entries["price"].get())
                cost     = float(entries["cost"].get())
                supplier = entries["supplier"].get().strip().capitalize()
                stock    = int(entries["stock"].get())
                min_stock= int(entries["min_stock"].get())
                unit     = entries["unit"].get().strip() or "unidad"
            except ValueError:
                messagebox.showerror("Error","Verifica los valores numéricos",parent=dlg); return
            if data: self.db.upd_product(data["id"],name,sku or data["sku"],barcode,category,price,cost,supplier,stock,min_stock,unit)
            else:    self.db.add_product(name,sku,barcode,category,price,cost,supplier,stock,min_stock,unit)
            dlg.destroy(); self._refresh()
        W_btn(dlg, "💾 Guardar", save, w=426, h=40).pack(padx=_sc(26), pady=_sc(14))

    def _adj(self):
        if not self._sel: messagebox.showinfo("Info","Selecciona un producto"); return
        p = self.db.get_product(self._sel)
        dlg = ctk.CTkToplevel(self); dlg.title("Ajustar Stock"); dlg.geometry("340x230"); dlg.grab_set()
        dlg.configure(fg_color=BG)
        W_label(dlg, p["name"], size=13, bold=True).pack(pady=(20,4))
        W_label(dlg, f"Stock actual: {p['stock']} {p['unit']}", color=DIM).pack()
        W_label(dlg, "Cantidad a sumar (+) o restar (-)", size=10, color=DIM).pack(pady=(14,2))
        e = W_entry(dlg, "ej: 50 ó -10", w=250); e.pack()
        def go():
            try: delta = int(e.get())
            except: messagebox.showerror("Error","Número entero requerido",parent=dlg); return
            if p["stock"]+delta<0: messagebox.showerror("Error","Stock no puede ser negativo",parent=dlg); return
            self.db.adj_stock(self._sel, delta); dlg.destroy(); self._refresh()
        W_btn(dlg, "✅ Aplicar", go, w=250, h=38).pack(pady=14)

    def _import(self):
        if not HAS_PD: messagebox.showwarning("Sin pandas","pip install pandas openpyxl"); return
        path = filedialog.askopenfilename(filetypes=[("Excel","*.xlsx *.xls")])
        if not path: return
        try:
            res = self.db.import_excel(path); self._go_page(1)
            messagebox.showinfo("Importación",f"✅ Importados: {res['importados']}\n⚠️ Duplicados: {res['duplicados']}\n❌ Errores: {res['errores']}")
        except Exception as exc: messagebox.showerror("Error",str(exc))

    def _export(self):
        if not HAS_PD: messagebox.showwarning("Sin pandas","pip install pandas openpyxl"); return
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel","*.xlsx")],
               initialfile=f"inventario_{date.today()}.xlsx")
        if not path: return
        try: self.db.export_excel(path); messagebox.showinfo("Exportado",f"Guardado:\n{path}")
        except Exception as exc: messagebox.showerror("Error",str(exc))

    def _clean(self):
        if not messagebox.askyesno("Limpiar datos","Corregirá precios negativos, nombres vacíos,\nstocks negativos y categorías faltantes.\n\n¿Continuar?"): return
        n = self.db.clean_data()
        messagebox.showinfo("Limpieza completada",f"Productos corregidos: {n}")
        self._refresh()

    def _new(self): self._form("Nuevo Producto")
    def _edit(self):
        if not self._sel: messagebox.showinfo("Info","Selecciona un producto"); return
        self._form("Editar Producto", self.db.get_product(self._sel))
    def _del(self):
        if not self._sel: messagebox.showinfo("Info","Selecciona un producto"); return
        if messagebox.askyesno("Confirmar","¿Desactivar este producto?"):
            self.db.del_product(self._sel); self._sel=None; self._refresh()


# ═══════════════════════════════════════════════════════════════
# CLIENTES
# ═══════════════════════════════════════════════════════════════
class ClientesPanel(BasePanel):
    def __init__(self, master, db, user):
        super().__init__(master, db, user, "👥 Clientes")
        self._sel = None; self._build(); self._refresh()

    def _build(self):
        tb = ctk.CTkFrame(self, fg_color="transparent"); tb.pack(fill="x", pady=(0,8))
        self.e_s = W_entry(tb, "🔍  Buscar...", w=260); self.e_s.pack(side="left")
        self.e_s.bind("<KeyRelease>", lambda _: self._refresh())
        W_btn(tb,"➕ Nuevo",   self._new,  w=110).pack(side="left", padx=(10,0))
        W_btn(tb,"✏️ Editar",  self._edit, w=110, color="#444").pack(side="left", padx=4)
        W_btn(tb,"🗑 Eliminar",self._del,  w=110, color=ERR).pack(side="left", padx=(0,10))
        W_btn(tb,"💰 Abonar",  self._pay_debt, w=110, color=OK).pack(side="left")
        frm = W_card(self); frm.pack(fill="both", expand=True)
        self.tree = make_tree(frm,
            ("id","name","document","phone","email","debt","address","created_at"),
            ("ID","Nombre","Documento","Teléfono","Email","Deuda","Dirección","Registro"),
            (40,175,100,110,175,90,175,90))
        self.tree.tag_configure("debt", foreground=WARN)
        self.tree.bind("<<TreeviewSelect>>", lambda _: self._on_sel())
        self.tree.bind("<Double-1>", lambda _: self._edit())

    def _on_sel(self):
        s = self.tree.selection()
        self._sel = int(self.tree.item(s[0])["values"][0]) if s else None

    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        for c in self.db.get_clients(self.e_s.get().strip()):
            tag = ("debt",) if c["debt"] > 0 else ()
            self.tree.insert("","end", tags=tag, values=(
                c["id"],c["name"],c["document"],c["phone"],c["email"],
                fmt(c["debt"]),c["address"],c["created_at"]))

    def _pay_debt(self):
        if not self._sel: messagebox.showinfo("Info","Selecciona un cliente"); return
        client = next((c for c in self.db.get_clients() if c["id"]==self._sel), None)
        if not client or client["debt"] <= 0:
            messagebox.showinfo("Info", "El cliente seleccionado no tiene deuda activa."); return
            
        dlg = ctk.CTkToplevel(self); dlg.title("Abonar a Deuda"); dlg.geometry(f"{_sc(360)}x{_sc(340)}"); dlg.grab_set()
        dlg.configure(fg_color=BG)
        W_label(dlg, f"Abono: {client['name']}", size=14, bold=True, color=ACC).pack(pady=(20,4))
        W_label(dlg, f"Deuda actual: {fmt(client['debt'])}", size=11, color=WARN).pack(pady=(0,14))
        
        W_label(dlg, "Monto a abonar:", size=10, color=DIM).pack(anchor="w", padx=_sc(26))
        e_amount = W_entry(dlg, w=300); e_amount.pack(padx=_sc(26), pady=2)
        e_amount.focus()
        
        W_label(dlg, "Notas (opcional):", size=10, color=DIM).pack(anchor="w", padx=_sc(26), pady=(10,0))
        e_notes = W_entry(dlg, w=300); e_notes.pack(padx=_sc(26), pady=2)
        
        def save():
            try: amount = float(e_amount.get().strip() or 0)
            except: amount = 0
            if amount <= 0: messagebox.showerror("Error", "Ingresa un monto válido mayor a 0", parent=dlg); return
            if amount > client["debt"]:
                messagebox.showerror("Error", f"El abono no puede superar la deuda ({fmt(client['debt'])})", parent=dlg); return
            
            sess = self.db.get_active_session(self.user["id"])
            sess_id = sess["id"] if sess else None
            self.db.add_client_payment(client["id"], self.user["id"], sess_id, amount, e_notes.get().strip())
            
            dlg.destroy(); self._refresh()
            msg = f"Abono de {fmt(amount)} registrado exitosamente."
            if not sess_id: msg += "\n(No sumado a caja porque no hay turno abierto)"
            messagebox.showinfo("Abono Registrado", msg)
            
        W_btn(dlg, "✅ Confirmar Abono", save, w=300, h=40, color=OK).pack(pady=20)

    def _form(self, title, data=None):
        dlg = ctk.CTkToplevel(self); dlg.title(title); dlg.geometry(f"{_sc(700)}x{_sc(360)}"); dlg.grab_set()
        dlg.configure(fg_color=BG)
        W_label(dlg, title, size=16, bold=True, color=ACC).pack(pady=(20,10))
        
        container = ctk.CTkFrame(dlg, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=_sc(20), pady=_sc(10))
        container.columnconfigure(0, weight=1, pad=_sc(15))
        container.columnconfigure(1, weight=1, pad=_sc(15))

        fields = [("Nombre *","name"),("Documento / NIT","document"),("Teléfono","phone"),
                  ("Email","email"),("Dirección","address"),("Notas","notes")]
        entries = {}
        for i, (lbl, key) in enumerate(fields):
            row = i // 2
            col = i % 2
            f_frame = ctk.CTkFrame(container, fg_color="transparent")
            f_frame.grid(row=row, column=col, sticky="ew", padx=_sc(8), pady=_sc(8))
            
            W_label(f_frame, lbl, size=10, color=DIM).pack(anchor="w", pady=(0, 2))
            e = W_entry(f_frame, w=300)
            if data and data.get(key): e.insert(0, str(data[key]))
            e.pack(fill="x"); entries[key] = e
        def save():
            n = entries["name"].get().strip()
            if not n: messagebox.showerror("Error","Nombre obligatorio",parent=dlg); return
            args = (n, entries["document"].get().strip(), entries["phone"].get().strip(),
                    entries["email"].get().strip(), entries["address"].get().strip(), entries["notes"].get().strip())
            if data: self.db.upd_client(data["id"], *args)
            else:    self.db.add_client(*args)
            dlg.destroy(); self._refresh()
        W_btn(dlg, "💾 Guardar", save, w=378, h=40).pack(padx=_sc(26), pady=_sc(14))

    def _new(self): self._form("Nuevo Cliente")
    def _edit(self):
        if not self._sel: messagebox.showinfo("Info","Selecciona un cliente"); return
        data = next((c for c in self.db.get_clients() if c["id"]==self._sel), None)
        if data: self._form("Editar Cliente", data)
    def _del(self):
        if not self._sel: messagebox.showinfo("Info","Selecciona un cliente"); return
        if messagebox.askyesno("Confirmar","¿Eliminar este cliente?"):
            self.db.del_client(self._sel); self._sel=None; self._refresh()


# ═══════════════════════════════════════════════════════════════
# PUNTO DE VENTA
# ═══════════════════════════════════════════════════════════════
class VentaPanel(BasePanel):
    def __init__(self, master, db, user):
        super().__init__(master, db, user)
        self.cart = []; self._build()

    def _build(self):
        for w in self.winfo_children(): w.destroy()
        W_label(self, "🛒 Punto de Venta", size=18, bold=True).pack(anchor="w", pady=(0,10))
        self.active_sess = self.db.get_active_session(self.user["id"])
        if not self.active_sess: self._build_apertura()
        else:                    self._build_pos()

    def _build_apertura(self):
        frm = W_card(self); frm.pack(expand=True, padx=80, pady=50, fill="both")
        W_label(frm, "🔑 Apertura de Caja", size=17, bold=True, color=ACC).pack(pady=(35,8))
        W_label(frm, "Para registrar ventas debes iniciar un turno e indicar\nel dinero inicial que tienes en caja.",
                size=11, color=DIM, wraplength=400, justify="center").pack()
        W_label(frm, "Efectivo inicial en caja", size=11, color=DIM).pack(pady=(25,2))
        e_init = W_entry(frm, "ej: 50000", w=280); e_init.insert(0,"0"); e_init.pack()
        l_err  = W_label(frm, "", color=ERR, size=10); l_err.pack(pady=4)
        def open_box():
            try: val = float(e_init.get().strip())
            except: l_err.configure(text="❌ Ingresa un número válido"); return
            if val < 0: l_err.configure(text="❌ El monto no puede ser negativo"); return
            self.db.open_session(self.user["id"], val)
            self._build()
        W_btn(frm, "▶  Iniciar Turno", open_box, w=280, h=42).pack(pady=16)
        e_init.bind("<Return>", lambda _: open_box())

    def _build_pos(self):
        body = ctk.CTkFrame(self, fg_color="transparent"); body.pack(fill="both", expand=True)

        # ── Catálogo ──
        lf = W_card(body); lf.pack(side="left", fill="both", expand=True, padx=(0,8))
        W_label(lf, "Catálogo", bold=True, color=ACC).pack(pady=(12,6))
        srch = ctk.CTkFrame(lf, fg_color="transparent"); srch.pack(fill="x", padx=10)
        self.e_prod = W_entry(srch, "🔍  Nombre, SKU o código barras...", w=250); self.e_prod.pack(side="left")
        self.e_prod.bind("<KeyRelease>", lambda _: self._search_prod())
        self.e_prod.bind("<Return>",     lambda _: self._scan_or_add())
        W_label(srch, "  Cant:", size=10).pack(side="left", padx=(8,2))
        self.e_qty = W_entry(srch, "1", w=65); self.e_qty.insert(0,"1"); self.e_qty.pack(side="left")
        frp = ctk.CTkFrame(lf, fg_color="#1a1a1a", corner_radius=8)
        frp.pack(fill="both", expand=True, padx=10, pady=8)
        self.ptree = make_tree(frp,
            ("id","sku","name","price","stock"),
            ("ID","SKU","Producto","Precio","Stock"),
            (40,80,225,110,70))
        self.ptree.tag_configure("nostock", foreground="#555")
        self.ptree.bind("<Double-1>", lambda _: self._add())
        self._search_prod()
        btn_row = ctk.CTkFrame(lf, fg_color="transparent"); btn_row.pack(fill="x", padx=10, pady=(0,10))
        W_btn(btn_row, "➕  Agregar al carrito", self._add, w=240, h=34).pack(side="left")
        W_btn(btn_row, "🔄 Actualizar", self._build, color="#333", w=120, h=34).pack(side="right")

        # ── Carrito ──
        rf = W_card(body); rf.pack(side="left", fill="y")
        rf.configure(width=_sc(400)); rf.pack_propagate(False)

        sess_bar = ctk.CTkFrame(rf, fg_color="#1a2a1a", corner_radius=6)
        sess_bar.pack(fill="x", padx=10, pady=(8,0))
        opened = self.active_sess["opened_at"]
        W_label(sess_bar, f"⏱  Turno abierto desde {opened[11:16]}", size=9, color=OK).pack(pady=4)

        W_label(rf, "🛒  Carrito", bold=True, color=ACC).pack(pady=(8,4))
        
        # ── Controles inferiores (anclados abajo) ──
        bf = ctk.CTkFrame(rf, fg_color="transparent")
        bf.pack(side="bottom", fill="x")

        sf = ctk.CTkFrame(bf, fg_color="transparent"); sf.pack(fill="x", padx=12, pady=4)
        def srow(lbl, attr, color=TEXT):
            r = ctk.CTkFrame(sf, fg_color="transparent"); r.pack(fill="x", pady=1)
            W_label(r, lbl, size=10, color=DIM).pack(side="left")
            lw = W_label(r, fmt(0), size=11, bold=True, color=color); lw.pack(side="right")
            setattr(self, attr, lw)
        srow("Subtotal:", "l_sub")

        W_label(bf, "Descuento", size=10, color=DIM).pack(anchor="w", padx=12)
        self.e_disc = W_entry(bf, "0", w=374); self.e_disc.insert(0,"0"); self.e_disc.pack(padx=12, pady=2)
        self.e_disc.bind("<KeyRelease>", lambda _: self._upd_total())
        ctk.CTkFrame(bf, fg_color="#333", height=1).pack(fill="x", padx=12, pady=4)
        srow("TOTAL:", "l_total", OK)

        W_label(bf, "Cliente", size=10, color=DIM).pack(anchor="w", padx=12, pady=(4,0))
        clist = ["(sin cliente)"]+[f"{c['id']} – {c['name']}" for c in self.db.get_clients()]
        self.cb_cli = W_combo(bf, clist, w=374); self.cb_cli.pack(padx=12, pady=2)

        W_label(bf, "Método de Pago", size=10, color=DIM).pack(anchor="w", padx=12, pady=(4,0))
        self.cb_pay = W_combo(bf, ["efectivo","tarjeta","transferencia","crédito","otro"], w=374)
        self.cb_pay.pack(padx=12, pady=2)

        W_label(bf, "Notas (opcional)", size=10, color=DIM).pack(anchor="w", padx=12, pady=(4,0))
        self.e_notes = W_entry(bf, "", w=374); self.e_notes.pack(padx=12, pady=2)

        br = ctk.CTkFrame(bf, fg_color="transparent"); br.pack(fill="x", padx=_sc(12), pady=(_sc(8), _sc(12)))
        W_btn(br, "🗑 Quitar",  self._remove, color="#444", w=100, h=36).pack(side="left", fill="x", expand=True)
        W_btn(br, "🧹 Limpiar", self._clear,  color="#444", w=100, h=36).pack(side="left", fill="x", expand=True, padx=(_sc(4), _sc(4)))
        W_btn(br, "✅ COBRAR",  self._checkout, color=OK, w=120, h=36).pack(side="left", fill="x", expand=True)

        # ── Tabla del carrito (expande para llenar el espacio restante arriba) ──
        frca = ctk.CTkFrame(rf, fg_color="#1a1a1a", corner_radius=8)
        frca.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self.ctree = make_tree(frca,
            ("name","qty","price","sub"),
            ("Producto","Cant","Precio","Subtotal"),
            (155,50,92,92), height=5)

    # ── Lógica del carrito ────────────────────────────────────
    def _search_prod(self):
        self.ptree.delete(*self.ptree.get_children())
        for p in self.db.get_all_products(self.e_prod.get().strip()):
            tag = ("nostock",) if p["stock"]<=0 else ()
            self.ptree.insert("","end", tags=tag, values=(p["id"],p["sku"],p["name"],fmt(p["price"]),p["stock"]))

    def _scan_or_add(self):
        """Enter en búsqueda: intenta por SKU exacto, si no agrega el primero de la lista."""
        text = self.e_prod.get().strip()
        if not text: return
        try:
            sku = int(text)
            p = self.db.get_product_by_sku(sku)
            if p:
                for item in self.ptree.get_children():
                    if int(self.ptree.item(item)["values"][0]) == p["id"]:
                        self.ptree.selection_set(item)
                        self._add(); self.e_prod.delete(0,"end"); self._search_prod(); return
        except ValueError:
            pass
        children = self.ptree.get_children()
        if children: self.ptree.selection_set(children[0]); self._add()

    def _add(self):
        sel = self.ptree.selection()
        if not sel: return
        pid = int(self.ptree.item(sel[0])["values"][0])
        p   = self.db.get_product(pid)
        if not p: return
        try:    qty = float(self.e_qty.get())
        except: qty = 1
        if qty <= 0: return
        if p["stock"] < qty:
            messagebox.showwarning("Stock insuficiente", f"Solo hay {p['stock']} {p['unit']} disponibles"); return
        for item in self.cart:
            if item["product_id"] == pid:
                if p["stock"] < item["quantity"]+qty:
                    messagebox.showwarning("Stock","Sin stock suficiente"); return
                item["quantity"] += qty
                item["subtotal"] = round(item["quantity"]*item["unit_price"], 2)
                self._upd_cart(); return
        self.cart.append({"product_id":pid,"product_name":p["name"],"quantity":qty,
                          "unit_price":p["price"],"subtotal":round(qty*p["price"],2)})
        self._upd_cart()

    def _upd_cart(self):
        self.ctree.delete(*self.ctree.get_children())
        sub = 0
        for it in self.cart:
            self.ctree.insert("","end", values=(it["product_name"],it["quantity"],fmt(it["unit_price"]),fmt(it["subtotal"])))
            sub += it["subtotal"]
        self.l_sub.configure(text=fmt(sub))
        self._upd_total()

    def _upd_total(self):
        sub = sum(i["subtotal"] for i in self.cart)
        try:    disc = float(self.e_disc.get() or 0)
        except: disc = 0
        self.l_total.configure(text=fmt(sub-disc))

    def _remove(self):
        sel = self.ctree.selection()
        if not sel: return
        idx = self.ctree.index(sel[0])
        if 0<=idx<len(self.cart): self.cart.pop(idx); self._upd_cart()

    def _clear(self): self.cart=[]; self._upd_cart()

    def _checkout(self):
        if not self.cart: messagebox.showinfo("Carrito vacío","Agrega productos primero"); return
        try:    disc = float(self.e_disc.get() or 0)
        except: disc = 0
        sub   = sum(i["subtotal"] for i in self.cart)
        total = sub - disc
        payment = self.cb_pay.get()
        if payment == "crédito":
            cv = self.cb_cli.get()
            if not cv or cv == "(sin cliente)":
                messagebox.showerror("Crédito", "Para ventas a crédito (fiado) es OBLIGATORIO seleccionar un cliente.")
                return

        if payment == "efectivo":
            # ── Calculadora de cambio ──
            dlg = ctk.CTkToplevel(self); dlg.title("Cobrar — Calculadora de Cambio")
            dlg.geometry("360x320"); dlg.grab_set(); dlg.configure(fg_color=BG)
            W_label(dlg, "TOTAL A COBRAR", size=11, color=DIM).pack(pady=(24,4))
            W_label(dlg, fmt(total), size=32, bold=True, color=OK).pack()
            W_sep(dlg)
            W_label(dlg, "Efectivo recibido:", size=10, color=DIM).pack(pady=(14,2))
            e_rec = W_entry(dlg, "0", w=280); e_rec.pack(); e_rec.focus()
            l_cambio = W_label(dlg, fmt(0), size=24, bold=True, color=ACC); l_cambio.pack(pady=6)
            W_label(dlg, "Cambio", size=9, color=DIM).pack()

            def upd(*_):
                try:    rec = float(e_rec.get() or 0)
                except: rec = 0
                cambio = rec - total
                l_cambio.configure(text=fmt(max(0,cambio)), text_color=OK if cambio>=0 else ERR)

            e_rec.bind("<KeyRelease>", upd)

            def confirmar():
                try:    rec = float(e_rec.get() or 0)
                except: rec = 0
                if rec < total:
                    messagebox.showwarning("Pago insuficiente",f"El pago mínimo es {fmt(total)}",parent=dlg); return
                cambio = rec - total
                dlg.withdraw()
                dlg.destroy()
                # Abrir diálogo DIAN después de confirmar efectivo
                FacturacionDialog(self, self.db, self.user, self.cart, sub, disc, total, payment, cambio, self._on_sale_done)

            W_btn(dlg, "✅  Confirmar y Registrar", confirmar, color=OK, w=280, h=44).pack(padx=40, pady=14)
            e_rec.bind("<Return>", lambda _: confirmar())
        else:
            FacturacionDialog(self, self.db, self.user, self.cart, sub, disc, total, payment, 0, self._on_sale_done)

    def _on_sale_done(self):
        self._clear(); self._search_prod()

    def _register_sale(self, sub, disc, total, payment, cambio,
                       notes="", dian_data=None):
        """Registra la venta en la BD y opcionalmente emite factura electrónica DIAN."""
        try:
            cv = self.cb_cli.get(); client_id = None
            if cv and cv != "(sin cliente)":
                try:
                    client_id = int(cv.strip().split()[0])
                except Exception:
                    client_id = None
            self.active_sess = self.db.get_active_session(self.user["id"])
            sess_id = self.active_sess["id"] if self.active_sess else None
            sid = self.db.create_sale(client_id, self.user["id"], self.cart, disc, payment, notes, sess_id)
            self._gen_ticket(sid, sub, disc, total, payment, notes, cambio)
            msg = f"Venta #{sid}\n\nTotal: {fmt(total)}\nPago:  {payment}"
            if cambio > 0: msg += f"\nCambio: {fmt(cambio)}"
            messagebox.showinfo("✅ Venta registrada", msg)
        except Exception as e:
            log.error(f"Error registrando venta: {e}", exc_info=True)
            messagebox.showerror("❌ Error al registrar venta",
                f"No se pudo guardar la venta:\n\n{e}\n\nRevisa el archivo de log para más detalles.")



    def _gen_ticket(self, sid, sub, disc, total, payment, notes, cambio):
        sym = self.db.cfg("currency_symbol")
        bname = self.db.cfg("business_name"); btype = self.db.cfg("business_type")
        phone = self.db.cfg("phone");         addr  = self.db.cfg("address")
        # ── Siempre guardar ticket .txt como respaldo ──
        try:
            os.makedirs("tickets", exist_ok=True)
            W  = 42
            lines = ["="*W, bname.center(W)]
            if btype: lines.append(btype.center(W))
            if addr:  lines.append(addr.center(W))
            if phone: lines.append(f"Tel: {phone}".center(W))
            lines += ["="*W, f"Ticket #{sid}".ljust(W),
                      f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}".ljust(W),
                      f"Cajero: {self.user['username']}".ljust(W), "-"*W,
                      f"{'CANT':<5} {'PRODUCTO':<25} {'TOTAL':>10}", "-"*W]
            for it in self.cart:
                qty = str(int(it["quantity"])); name = it["product_name"][:25]
                tot = f"{sym}{it['subtotal']:.0f}"
                lines.append(f"{qty:<5} {name:<25} {tot:>10}")
            lines += ["-"*W, f"{'Subtotal:':<30} {sym}{sub:>10,.0f}"]
            if disc > 0: lines.append(f"{'Descuento:':<30} -{sym}{disc:>9,.0f}")
            lines += ["-"*W, f"{'TOTAL:':<30} {sym}{total:>10,.0f}", "-"*W,
                      f"Pago: {payment.capitalize()}".ljust(W)]
            if cambio > 0: lines.append(f"Cambio: {sym}{cambio:.0f}".ljust(W))
            if notes: lines.append(f"Notas: {notes}".ljust(W))
            lines += ["="*W, "Gracias por su compra!".center(W), "\n\n\n"]
            path = f"tickets/ticket_{sid}.txt"
            with open(path, "w", encoding="utf-8") as f: f.write("\n".join(lines))
            log.info(f"Ticket .txt generado: {os.path.abspath(path)}")
        except Exception as e:
            log.warning(f"Error generando ticket .txt: {e}")
        # ── Impresora térmica (si está habilitada) ──
        if self.db.cfg("printer_enabled") == "1":
            self._print_thermal(sid, sub, disc, total, payment, notes, cambio,
                                sym, bname, btype, phone, addr)

    def _print_thermal(self, sid, sub, disc, total, payment, notes, cambio,
                       sym, bname, btype, phone, addr):
        """Imprime ticket profesional en impresora térmica POS 80mm."""
        if not HAS_ESCPOS:
            log.warning("python-escpos no instalado — pip install python-escpos")
            return
        printer_name = self.db.cfg("printer_name").strip()
        if not printer_name:
            log.warning("Impresora térmica habilitada pero sin nombre configurado")
            return
        try:
            p = Win32Raw(printer_name)
            # ── Encabezado ──
            p.set(align='center', bold=True, width=2, height=2)
            p.text(bname + "\n")
            p.set(align='center', bold=False, width=1, height=1)
            if btype: p.text(btype + "\n")
            if addr:  p.text(addr + "\n")
            if phone: p.text(f"Tel: {phone}\n")
            p.text("="*48 + "\n")
            # ── Info de la venta ──
            p.set(align='left')
            p.text(f"Ticket: #{sid}\n")
            p.text(f"Fecha:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            p.text(f"Cajero: {self.user['username']}\n")
            p.text("-"*48 + "\n")
            # ── Columnas ──
            p.set(align='left', bold=True)
            p.text(f"{'CANT':<6}{'PRODUCTO':<28}{'TOTAL':>14}\n")
            p.set(bold=False)
            p.text("-"*48 + "\n")
            # ── Ítems ──
            for it in self.cart:
                qty  = f"{int(it['quantity'])}"
                name = it["product_name"][:28]
                tot  = f"{sym}{it['subtotal']:,.0f}"
                p.text(f"{qty:<6}{name:<28}{tot:>14}\n")
            p.text("-"*48 + "\n")
            # ── Totales ──
            p.set(align='right')
            p.text(f"Subtotal: {sym}{sub:,.0f}\n")
            if disc > 0:
                p.text(f"Descuento: -{sym}{disc:,.0f}\n")
            p.set(bold=True, width=2, height=2)
            p.text(f"TOTAL: {sym}{total:,.0f}\n")
            p.set(bold=False, width=1, height=1)
            p.text("-"*48 + "\n")
            # ── Pago ──
            p.set(align='left')
            p.text(f"Pago: {payment.capitalize()}\n")
            if cambio > 0:
                p.text(f"Cambio: {sym}{cambio:,.0f}\n")
            if notes:
                p.text(f"Notas: {notes}\n")
            # ── Pie ──
            p.text("="*48 + "\n")
            p.set(align='center')
            p.text("Gracias por su compra!\n")
            p.text("\n\n\n")
            p.cut()
            p.close()
            log.info(f"Ticket #{sid} impreso en '{printer_name}'")
        except Exception as e:
            log.error(f"Error imprimiendo en térmica: {e}")
            messagebox.showwarning("Impresora",
                f"No se pudo imprimir el ticket:\n{e}\n\nEl ticket .txt fue guardado como respaldo.")



# ═══════════════════════════════════════════════════════════════
# FACTURACIÓN ELECTRÓNICA DIAN — DIÁLOGO
# ═══════════════════════════════════════════════════════════════
class FacturacionDialog(ctk.CTkToplevel):
    """
    Diálogo que aparece al cobrar una venta.
    - Registra la venta en la BD.
    - Opcionalmente emite factura electrónica ante la DIAN vía Factus.
    """
    def __init__(self, master, db, user, cart, sub, disc, total,
                 payment, cambio, on_done_cb):
        super().__init__(master)
        self.db        = db
        self.user      = user
        self.cart      = cart
        self.sub       = sub
        self.disc      = disc
        self.total     = total
        self.payment   = payment
        self.cambio    = cambio
        self.on_done   = on_done_cb

        self.title("💳 Registrar Venta")
        self.geometry(f"{_sc(480)}x{_sc(560)}")
        self.resizable(True, True)
        self.configure(fg_color=BG)
        self.grab_set()
        self._build()
        self.wait_window()

    def _build(self):
        # ── Botones fijos al fondo ──
        btn_bar = ctk.CTkFrame(self, fg_color=CARD, corner_radius=0, height=_sc(64))
        btn_bar.pack(side="bottom", fill="x"); btn_bar.pack_propagate(False)
        brow = ctk.CTkFrame(btn_bar, fg_color="transparent")
        brow.pack(fill="both", expand=True, padx=_sc(16), pady=_sc(10))
        W_btn(brow, "✕ Cancelar", self.destroy, color="#444", w=130, h=40).pack(side="left")
        W_btn(brow, "✅ Registrar Venta", self._emit, color=OK, w=250, h=40).pack(side="right")

        # ── Área scrollable ──
        scroll = ctk.CTkScrollableFrame(self, fg_color=CARD, corner_radius=0)
        scroll.pack(side="top", fill="both", expand=True)

        W_label(scroll, "🛒 Resumen de Venta", size=15, bold=True, color=ACC).pack(pady=(14,4))

        # Resumen de ítems
        items_box = ctk.CTkFrame(scroll, fg_color=CARD2, corner_radius=8)
        items_box.pack(fill="x", padx=12, pady=6)
        W_label(items_box, "🧾 Ítems", size=9, color=DIM).pack(anchor="w", padx=10, pady=(6,2))
        for it in self.cart:
            r = ctk.CTkFrame(items_box, fg_color="transparent"); r.pack(fill="x", padx=10, pady=1)
            qty_s = f"x{int(it['quantity'])}" if it['quantity'] == int(it['quantity']) else f"{it['quantity']}"
            W_label(r, f"{qty_s}  {it['product_name']}", size=10).pack(side="left")
            W_label(r, fmt(it["subtotal"]), size=10, color=OK).pack(side="right")
        ctk.CTkFrame(items_box, fg_color="transparent", height=_sc(6)).pack()

        # IVA opcional
        iva_row = ctk.CTkFrame(scroll, fg_color="transparent"); iva_row.pack(fill="x", padx=12, pady=(6,0))
        W_label(iva_row, "IVA (%):", size=10, color=DIM).pack(side="left")
        self.e_iva_pct = W_entry(iva_row, "0", w=80)
        # Precargar el tax_percent configurado
        tax_pct = self.db.cfg("tax_percent") or "0"
        self.e_iva_pct.insert(0, tax_pct)
        self.e_iva_pct.pack(side="left", padx=8)
        self.e_iva_pct.bind("<KeyRelease>", lambda _: self._upd_totals())
        W_label(iva_row, "(0 = sin IVA)", size=9, color=DIM).pack(side="left")

        # Panel de totales
        tot_box = ctk.CTkFrame(scroll, fg_color=CARD2, corner_radius=8)
        tot_box.pack(fill="x", padx=12, pady=6)
        for attr, lbl_txt, color in [
            ("_l_sub",   "Subtotal:",     TEXT),
            ("_l_disc",  "Descuento:",    ERR),
            ("_l_iva",   "IVA:",          DIM),
            ("_l_total", "TOTAL FINAL:",  OK),
        ]:
            rw = ctk.CTkFrame(tot_box, fg_color="transparent"); rw.pack(fill="x", padx=12, pady=2)
            bold = attr == "_l_total"; sz = 13 if bold else 10
            W_label(rw, lbl_txt, size=sz, color=color, bold=bold).pack(side="left")
            v = W_label(rw, fmt(0), size=sz, color=color, bold=bold); v.pack(side="right")
            setattr(self, attr, v)

        # Notas
        W_label(scroll, "Notas (opcional):", size=9, color=DIM).pack(anchor="w", padx=12, pady=(6,0))
        self.e_notes = W_entry(scroll, "", w=430); self.e_notes.pack(padx=12, pady=(0,4))

        # ── Sección Facturación Electrónica DIAN ──
        self._apply_dian = tk.BooleanVar(value=False)
        dian_chk = ctk.CTkCheckBox(
            scroll, text="📄 Emitir Factura Electrónica DIAN",
            variable=self._apply_dian,
            checkmark_color="white", fg_color="#2980b9", hover_color="#3498db",
            command=self._toggle_dian,
            font=("Segoe UI", _sc(11), "bold"))
        dian_chk.pack(anchor="w", padx=12, pady=(10,2))

        self._dian_frame = ctk.CTkFrame(scroll, fg_color=CARD2, corner_radius=8)
        W_label(self._dian_frame, "📋 Datos del cliente para la DIAN:", size=10, bold=True, color="#3498db").pack(
            anchor="w", padx=10, pady=(8,4))

        # Tipo doc
        dr = ctk.CTkFrame(self._dian_frame, fg_color="transparent"); dr.pack(fill="x", padx=10, pady=2)
        W_label(dr, "Tipo doc:", size=9, color=DIM).pack(side="left")
        self._cb_doc_type = W_combo(dr, ["CC","NIT","CE","PP","TI"], w=100)
        self._cb_doc_type.set("CC"); self._cb_doc_type.pack(side="right")

        # NIT/Cédula
        nr = ctk.CTkFrame(self._dian_frame, fg_color="transparent"); nr.pack(fill="x", padx=10, pady=2)
        W_label(nr, "NIT / Cédula:", size=9, color=DIM).pack(side="left")
        self._e_nit = W_entry(nr, "222222222222", w=200)
        self._e_nit.insert(0, "222222222222"); self._e_nit.pack(side="right")

        # Nombre
        nmr = ctk.CTkFrame(self._dian_frame, fg_color="transparent"); nmr.pack(fill="x", padx=10, pady=2)
        W_label(nmr, "Nombre:", size=9, color=DIM).pack(side="left")
        self._e_dian_name = W_entry(nmr, "Consumidor Final", w=200)
        self._e_dian_name.insert(0, "Consumidor Final"); self._e_dian_name.pack(side="right")

        # Email
        emr = ctk.CTkFrame(self._dian_frame, fg_color="transparent"); emr.pack(fill="x", padx=10, pady=(2,8))
        W_label(emr, "Email:", size=9, color=DIM).pack(side="left")
        self._e_email = W_entry(emr, "correo@ejemplo.com", w=200)
        self._e_email.pack(side="right")

        ctk.CTkFrame(scroll, fg_color="transparent", height=_sc(10)).pack()
        self._upd_totals()

    def _toggle_dian(self):
        if self._apply_dian.get():
            self._dian_frame.pack(fill="x", padx=12, pady=4)
        else:
            self._dian_frame.pack_forget()

    def _upd_totals(self):
        try: iva_pct = float(self.e_iva_pct.get() or 0) / 100
        except: iva_pct = 0
        iva   = round((self.sub - self.disc) * iva_pct, 0)
        total_final = self.sub - self.disc + iva
        self._l_sub.configure(text=fmt(self.sub))
        self._l_disc.configure(text=f"- {fmt(self.disc)}")
        self._l_iva.configure(text=fmt(iva))
        self._l_total.configure(text=fmt(total_final))
        self._iva = iva
        self._total_final = total_final

    def _emit(self):
        self._upd_totals()
        notes = self.e_notes.get().strip()

        # ── Obtener cliente seleccionado en VentaPanel ──
        try:
            cv = self.master.cb_cli.get()
            client_id = int(cv.strip().split()[0]) if cv and cv != "(sin cliente)" else None
        except Exception:
            client_id = None

        # ── Refrescar sesión y registrar venta ──
        try:
            active_sess = self.db.get_active_session(self.user["id"])
            sess_id = active_sess["id"] if active_sess else None
            sid = self.db.create_sale(
                client_id, self.user["id"], self.cart,
                self.disc, self.payment, notes, sess_id)
        except Exception as e:
            log.error(f"Error registrando venta: {e}", exc_info=True)
            messagebox.showerror("❌ Error", f"No se pudo guardar la venta:\n{e}", parent=self)
            return

        # ── Ticket de venta ──
        try:
            from_panel = self.master
            if hasattr(from_panel, "_gen_ticket"):
                from_panel._gen_ticket(sid, self.sub, self.disc, self._total_final, self.payment, notes, self.cambio)
        except Exception as te:
            log.warning(f"No se pudo generar ticket: {te}")

        msg_venta = f"Venta #{sid}\n\nTotal: {fmt(self._total_final)}\nPago:  {self.payment}"
        if self.cambio > 0: msg_venta += f"\nCambio: {fmt(self.cambio)}"

        # ── Facturación Electrónica DIAN ──
        if self._apply_dian.get():
            try:
                from factus_api import FactusClient, FactusError
                factus = FactusClient(self.db)
                if not factus.is_configured():
                    messagebox.showwarning(
                        "Facturación Electrónica",
                        "Las credenciales de Factus no están configuradas.\n"
                        "Ve a Configuración → Facturación Electrónica y completa los datos.",
                        parent=self)
                else:
                    inv = self.db.create_invoice(sid, self.payment, self.disc, self._iva, notes)
                    if inv:
                        customer_data = {
                            "doc_type":       self._cb_doc_type.get(),
                            "identification": self._e_nit.get().strip() or "222222222222",
                            "name":           self._e_dian_name.get().strip() or "Consumidor Final",
                            "email":          self._e_email.get().strip() or "consumidor@final.com",
                            "phone":          "",
                            "address":        self.db.cfg("address") or "calle 1 # 1-1",
                            "payment_method": self.payment,
                        }
                        calc = {
                            "sub": self.sub, "disc": self.disc,
                            "iva": self._iva, "total": self._total_final,
                        }
                        result = factus.crear_factura(
                            sid, self.cart, calc, customer_data, inv["num"])
                        self.db.update_invoice_dian(
                            inv["id"], result.get("cufe",""), result.get("pdf_url",""))
                        cufe_short = result.get("cufe","")[:30]
                        messagebox.showinfo(
                            "✅ Factura Electrónica DIAN",
                            f"¡Factura emitida ante la DIAN exitosamente!\n\n"
                            f"Número:  {result.get('number','')}\n"
                            f"CUFE:    {cufe_short}...\n\n"
                            f"{result.get('message','')}",
                            parent=self)
            except ImportError:
                messagebox.showerror("Error",
                    "No se encontró el módulo factus_api.py.\n"
                    "Verifica que el archivo existe en la carpeta del programa.", parent=self)
            except Exception as fe:
                messagebox.showerror("Error Facturación Electrónica",
                    f"No se pudo emitir la factura electrónica:\n\n{str(fe)}", parent=self)

        messagebox.showinfo("✅ Venta registrada", msg_venta)
        self.destroy()
        if self.on_done:
            self.on_done()


# ═══════════════════════════════════════════════════════════════
# CIERRE DE CAJA
# ═══════════════════════════════════════════════════════════════
class CierreCajaPanel(BasePanel):
    def __init__(self, master, db, user):
        super().__init__(master, db, user, "💰 Turno y Cierre de Caja")
        self._build()

    def _build(self):
        self.tabs = ctk.CTkTabview(self, fg_color=CARD, corner_radius=10)
        self.tabs.pack(fill="both", expand=True)
        self.tabs.add("📊 Turno Activo")
        self.tabs.add("📋 Historial")
        self._build_historial()
        self._load_turno()

    def _load_turno(self):
        tab = self.tabs.tab("📊 Turno Activo")
        for w in tab.winfo_children(): w.destroy()
        sess = self.db.get_active_session(self.user["id"])
        if sess: self._show_active(tab, sess)
        else:    self._show_no_session(tab)

    def _show_no_session(self, tab):
        frm = W_card(tab); frm.pack(expand=True, padx=60, pady=40, fill="x")
        W_label(frm, "⏸  Sin turno activo", size=16, bold=True, color=WARN).pack(pady=(30,8))
        W_label(frm, "No hay ningún turno abierto. Puedes abrir uno aquí o desde el Punto de Venta.", size=11, color=DIM, wraplength=400, justify="center").pack()
        W_label(frm, "Efectivo inicial en caja", size=11, color=DIM).pack(pady=(20,2))
        e_init = W_entry(frm, "ej: 50000", w=280); e_init.insert(0, "0"); e_init.pack()
        l_err  = W_label(frm, "", color=ERR, size=10); l_err.pack(pady=4)
        def open_box():
            try: val = float(e_init.get().strip())
            except: l_err.configure(text="❌ Ingresa un número válido"); return
            if val < 0: l_err.configure(text="❌ El monto no puede ser negativo"); return
            self.db.open_session(self.user["id"], val)
            self._load_turno()
        W_btn(frm, "▶  Abrir Turno", open_box, w=280, h=42).pack(pady=12)
        e_init.bind("<Return>", lambda _: open_box())

    def _show_active(self, tab, sess):
        summary = self.db.get_session_summary(sess["id"])
        if not summary: return
        sf = ctk.CTkScrollableFrame(tab, fg_color="transparent"); sf.pack(fill="both", expand=True)

        # Info header
        hdr = W_card(sf); hdr.pack(fill="x", padx=4, pady=(4,6))
        hr  = ctk.CTkFrame(hdr, fg_color="transparent"); hr.pack(fill="x", padx=16, pady=10)
        W_label(hr, f"⏱  Turno abierto: {summary['opened_at']}", bold=True, color=OK).pack(side="left")
        W_btn(hr, "🔄 Actualizar", self._load_turno, color="#333", w=110, h=26).pack(side="right")

        # Stats cards
        stats = ctk.CTkFrame(sf, fg_color="transparent"); stats.pack(fill="x", padx=4)
        for icon, lbl, val, color in [
            ("💵","Inicial en caja",   fmt(summary["initial_cash"]),  DIM),
            ("🛒","Ventas Efectivo",   fmt(summary["cash_sales"]),    OK),
            ("💳","Otras Ventas",      fmt(summary["other_sales"]),   ACC),
            ("➕","Ingresos extra",    fmt(summary["incomes"]),       PURPLE),
            ("➖","Egresos / Gastos",  fmt(summary["outcomes"]),      WARN),
            ("🎯","Esperado en caja",  fmt(summary["expected_cash"]), OK),
        ]:
            c = W_card(stats); c.pack(side="left", expand=True, fill="x", padx=(0,4))
            W_label(c, icon, size=20).pack(pady=(8,2))
            W_label(c, str(val), size=13, bold=True, color=color).pack()
            W_label(c, lbl, size=8, color=DIM).pack(pady=(0,8))

        # Registrar ingreso/egreso
        tc = W_card(sf); tc.pack(fill="x", padx=4, pady=6)
        W_label(tc, "Registrar Ingreso o Egreso Manual", bold=True, color=ACC).pack(pady=(10,6))
        tr = ctk.CTkFrame(tc, fg_color="transparent"); tr.pack(fill="x", padx=12, pady=(0,12))
        self.cb_ttype = W_combo(tr, ["➖ Egreso (gasto / retiro)","➕ Ingreso (abono / otro)"], w=230)
        self.cb_ttype.pack(side="left")
        self.e_tdesc  = W_entry(tr, "Descripción (ej: pago luz)", w=200); self.e_tdesc.pack(side="left", padx=6)
        self.e_tamt   = W_entry(tr, "Monto", w=110); self.e_tamt.pack(side="left")
        W_btn(tr, "Registrar", lambda: self._add_trans(sess["id"]), w=100, h=30).pack(side="left", padx=6)

        # Recent transactions
        trans_list = self.db.all(
            "SELECT * FROM cash_transactions WHERE session_id=? ORDER BY timestamp DESC LIMIT 8", (sess["id"],))
        if trans_list:
            for t in trans_list:
                tr2 = ctk.CTkFrame(tc, fg_color="transparent"); tr2.pack(fill="x", padx=16, pady=1)
                icon = "➖" if t["type"]=="outcome" else "➕"
                clr  = ERR  if t["type"]=="outcome" else OK
                W_label(tr2, f"{icon}  {t['description']} — {t['timestamp'][11:16]}", size=9).pack(side="left")
                W_label(tr2, fmt(t["amount"]), size=9, color=clr).pack(side="right")

        # Cierre
        cc = W_card(sf); cc.pack(fill="x", padx=4, pady=4)
        cr = ctk.CTkFrame(cc, fg_color="transparent"); cr.pack(fill="x", padx=16, pady=12)
        W_label(cr, "💰  Efectivo real al cerrar:", bold=True).pack(side="left")
        self.e_actual = W_entry(cr, "0", w=150); self.e_actual.pack(side="left", padx=10)
        W_btn(cr, "⏹  Cerrar Turno",
              lambda: self._close(sess["id"], summary["expected_cash"]),
              color=ERR, w=160).pack(side="right")

    def _add_trans(self, sess_id):
        desc = self.e_tdesc.get().strip()
        if not desc: messagebox.showinfo("Info","Ingresa una descripción"); return
        try: amount = float(self.e_tamt.get())
        except: messagebox.showerror("Error","Monto inválido"); return
        if amount <= 0: return
        t_type = "outcome" if "Egreso" in self.cb_ttype.get() else "income"
        self.db.add_cash_transaction(sess_id, t_type, amount, desc)
        self.e_tdesc.delete(0,"end"); self.e_tamt.delete(0,"end")
        self._load_turno()

    def _close(self, sess_id, expected):
        try: actual = float(self.e_actual.get())
        except: messagebox.showerror("Error","Ingresa el monto real"); return
        diff = actual - expected
        cuadro = abs(diff) < 1

        # Mensaje de confirmación antes de cerrar
        confirm_msg = (
            f"──────────────────────────────\n"
            f"  RESUMEN DE CIERRE DE CAJA\n"
            f"──────────────────────────────\n\n"
            f"  💰 Esperado en caja:  {fmt(expected)}\n"
            f"  💵 Real contado:      {fmt(actual)}\n"
            f"  📊 Diferencia:        {fmt(diff)}\n\n"
            f"{'  ✅ CAJA CUADRADA' if cuadro else f'  ⚠️ DESCUADRE DE {fmt(abs(diff))}'}\n\n"
            f"──────────────────────────────\n"
            f"¿Confirmar cierre del turno?"
        )
        if not messagebox.askyesno("Confirmar Cierre de Caja", confirm_msg):
            return

        self.db.close_session(sess_id, actual)

        # Mensaje de resultado después del cierre
        if cuadro:
            resultado_titulo = "✅ Caja Cerrada — CUADRÓ"
            resultado_msg = (
                f"El turno fue cerrado exitosamente.\n\n"
                f"✅  ¡La caja CUADRÓ perfectamente!\n\n"
                f"   Esperado: {fmt(expected)}\n"
                f"   Real:     {fmt(actual)}\n"
                f"   Diferencia: {fmt(diff)}"
            )
        elif diff > 0:
            resultado_titulo = "⚠️ Caja Cerrada — SOBRANTE"
            resultado_msg = (
                f"El turno fue cerrado exitosamente.\n\n"
                f"⚠️  Hubo un SOBRANTE en caja.\n\n"
                f"   Esperado:  {fmt(expected)}\n"
                f"   Real:      {fmt(actual)}\n"
                f"   Sobrante:  +{fmt(diff)}\n\n"
                f"Verifica ingresos no registrados."
            )
        else:
            resultado_titulo = "⚠️ Caja Cerrada — FALTANTE"
            resultado_msg = (
                f"El turno fue cerrado exitosamente.\n\n"
                f"⚠️  Hubo un FALTANTE en caja.\n\n"
                f"   Esperado:  {fmt(expected)}\n"
                f"   Real:      {fmt(actual)}\n"
                f"   Faltante:  {fmt(diff)}\n\n"
                f"Verifica egresos o ventas no contabilizadas."
            )

        messagebox.showinfo(resultado_titulo, resultado_msg)
        self._load_turno()
        self._build_historial()

    def _build_historial(self):
        tab = self.tabs.tab("📋 Historial")
        for w in tab.winfo_children(): w.destroy()
        sessions = self.db.all(
            "SELECT cs.*, u.username FROM cash_sessions cs"
            " LEFT JOIN users u ON cs.user_id=u.id"
            " WHERE cs.status='closed' ORDER BY cs.id DESC LIMIT 30")
        if not sessions:
            W_label(tab,"Sin cierres registrados aún", color=DIM, size=12).pack(expand=True); return
        frm = W_card(tab); frm.pack(fill="both", expand=True)
        tree = make_tree(frm,
            ("opened_at","closed_at","initial","actual","user"),
            ("Apertura","Cierre","Efectivo Inicial","Efectivo Final","Usuario"),
            (160,160,130,130,120))
        for s in sessions:
            tree.insert("","end", values=(
                s["opened_at"], s["closed_at"] or "—",
                fmt(s["initial_cash"]), fmt(s["actual_cash"] or 0), s["username"] or "—"))


# ═══════════════════════════════════════════════════════════════
# GASTOS
# ═══════════════════════════════════════════════════════════════
class GastosPanel(BasePanel):
    def __init__(self, master, db, user):
        super().__init__(master, db, user, "💸 Gastos Operativos")
        self._build(); self._load()

    def _build(self):
        ctrl = ctk.CTkFrame(self, fg_color="transparent"); ctrl.pack(fill="x", pady=(0,8))
        W_label(ctrl,"Desde:", size=10, color=DIM).pack(side="left")
        self.e_d1 = W_entry(ctrl, w=120); self.e_d1.insert(0, date.today().isoformat()); self.e_d1.pack(side="left", padx=(4,12))
        W_label(ctrl,"Hasta:", size=10, color=DIM).pack(side="left")
        self.e_d2 = W_entry(ctrl, w=120); self.e_d2.insert(0, date.today().isoformat()); self.e_d2.pack(side="left", padx=4)
        W_btn(ctrl,"🔍 Ver",   self._load,              w=90).pack(side="left", padx=8)
        W_btn(ctrl,"Hoy",  lambda: self._range(0),  color="#333", w=60).pack(side="left", padx=2)
        W_btn(ctrl,"7d",   lambda: self._range(7),  color="#333", w=55).pack(side="left", padx=2)
        W_btn(ctrl,"30d",  lambda: self._range(30), color="#333", w=60).pack(side="left", padx=2)
        
        W_btn(ctrl,"➕ Nuevo Gasto", self._new_expense, color=WARN, w=140).pack(side="right")

        self.f_sum = ctk.CTkFrame(self, fg_color="transparent"); self.f_sum.pack(fill="x", pady=(0,8))
        
        frm = W_card(self); frm.pack(fill="both", expand=True)
        self.tree = make_tree(frm,
            ("id","date","category","amount","description","user"),
            ("ID","Fecha","Categoría","Monto","Descripción","Usuario"),
            (40,100,150,120,300,100))

    def _range(self, days):
        t = date.today()
        self.e_d1.delete(0,"end"); self.e_d1.insert(0,(t-timedelta(days=days)).isoformat())
        self.e_d2.delete(0,"end"); self.e_d2.insert(0,t.isoformat())
        self._load()

    def _load(self):
        try:
            d1 = self.e_d1.get().strip(); d2 = self.e_d2.get().strip()
            if not d1 or not d2: return
            
            for w in self.f_sum.winfo_children(): w.destroy()
            summ = self.db.expenses_summary(d1, d2)
            
            c = W_card(self.f_sum); c.pack(side="left", fill="x", padx=(0,5))
            W_label(c, f"Total Gastos: {fmt(summ['total'])}", size=14, bold=True, color=WARN).pack(padx=20, pady=10)

            self.tree.delete(*self.tree.get_children())
            for e in self.db.get_expenses(d1, d2):
                self.tree.insert("","end", values=(
                    e["id"], e["date"], e["category"], fmt(e["amount"]), e["description"], e["uname"]
                ))
        except Exception as exc:
            messagebox.showerror("Error", f"Error cargando gastos:\n{exc}")

    def _new_expense(self):
        dlg = ctk.CTkToplevel(self); dlg.title("Registrar Nuevo Gasto")
        dlg.geometry(f"{_sc(600)}x{_sc(320)}"); dlg.grab_set(); dlg.configure(fg_color=BG)
        
        W_label(dlg, "Nuevo Gasto", size=16, bold=True, color=ACC).pack(pady=(20,10))
        
        container = ctk.CTkFrame(dlg, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=_sc(20), pady=_sc(10))
        container.columnconfigure(0, weight=1, pad=_sc(15))
        container.columnconfigure(1, weight=1, pad=_sc(15))

        f_cat = ctk.CTkFrame(container, fg_color="transparent")
        f_cat.grid(row=0, column=0, sticky="ew", padx=_sc(8), pady=_sc(8))
        W_label(f_cat, "Categoría *", size=10, color=DIM).pack(anchor="w", pady=(0, 2))
        cats = ["Arriendo", "Servicios Públicos", "Transporte", "Insumos/Papelería", "Nómina", "Mantenimiento", "Otro"]
        cb_cat = W_combo(f_cat, cats, w=260); cb_cat.pack(fill="x")
        
        f_amt = ctk.CTkFrame(container, fg_color="transparent")
        f_amt.grid(row=0, column=1, sticky="ew", padx=_sc(8), pady=_sc(8))
        W_label(f_amt, "Monto *", size=10, color=DIM).pack(anchor="w", pady=(0, 2))
        e_amount = W_entry(f_amt, w=260); e_amount.pack(fill="x")
        
        f_desc = ctk.CTkFrame(container, fg_color="transparent")
        f_desc.grid(row=1, column=0, sticky="ew", padx=_sc(8), pady=_sc(8))
        W_label(f_desc, "Descripción (opcional)", size=10, color=DIM).pack(anchor="w", pady=(0, 2))
        e_desc = W_entry(f_desc, w=260); e_desc.pack(fill="x")
        
        f_chk = ctk.CTkFrame(container, fg_color="transparent")
        f_chk.grid(row=1, column=1, sticky="ew", padx=_sc(8), pady=_sc(8))
        chk_var = tk.StringVar(value="1")
        chk = ctk.CTkCheckBox(f_chk, text="Sacar de la caja actual", 
                              variable=chk_var, onvalue="1", offvalue="0",
                              font=("Segoe UI", _sc(10)), text_color=DIM)
        chk.pack(anchor="w", pady=(20, 0))
        
        def save():
            cat = cb_cat.get().strip()
            try: amount = float(e_amount.get().strip())
            except: amount = 0
            if not cat or amount <= 0:
                messagebox.showerror("Error", "Categoría y monto mayor a 0 son obligatorios", parent=dlg); return
            
            affect_cash = (chk_var.get() == "1")
            sess_id = None
            if affect_cash:
                sess = self.db.get_active_session(self.user["id"])
                if not sess:
                    messagebox.showerror("Error", "No hay un turno de caja abierto para registrar el egreso.", parent=dlg); return
                sess_id = sess["id"]
                
            self.db.add_expense(self.user["id"], sess_id, cat, amount, e_desc.get().strip(), affect_cash)
            dlg.destroy(); self._load()
            messagebox.showinfo("✅", f"Gasto registrado: {fmt(amount)}")
            
        W_btn(dlg, "💾 Guardar Gasto", save, w=320, h=42, color=OK).pack(pady=(10, 20))


# ═══════════════════════════════════════════════════════════════
# INFORMES
# ═══════════════════════════════════════════════════════════════
class InformesPanel(BasePanel):
    def __init__(self, master, db, user):
        super().__init__(master, db, user, "📄 Informes y Análisis")
        self._fig = None   # referencia a la figura matplotlib activa
        self._build()
        self._load()

    def _build(self):
        ctrl = ctk.CTkFrame(self, fg_color="transparent"); ctrl.pack(fill="x", pady=(0,8))
        W_label(ctrl,"Desde:", size=10, color=DIM).pack(side="left")
        self.e_d1 = W_entry(ctrl, w=120); self.e_d1.insert(0, date.today().isoformat()); self.e_d1.pack(side="left", padx=(4,12))
        W_label(ctrl,"Hasta:", size=10, color=DIM).pack(side="left")
        self.e_d2 = W_entry(ctrl, w=120); self.e_d2.insert(0, date.today().isoformat()); self.e_d2.pack(side="left", padx=4)
        W_btn(ctrl,"🔍 Ver",   self._load,              w=90).pack(side="left", padx=8)
        W_btn(ctrl,"Hoy",  lambda: self._range(0),  color="#333", w=60).pack(side="left", padx=2)
        W_btn(ctrl,"7d",   lambda: self._range(7),  color="#333", w=55).pack(side="left", padx=2)
        W_btn(ctrl,"30d",  lambda: self._range(30), color="#333", w=60).pack(side="left", padx=2)
        W_btn(ctrl,"90d",  lambda: self._range(90), color="#333", w=60).pack(side="left", padx=2)
        W_btn(ctrl,"📤 Excel", self._export_excel,   color="#444", w=100).pack(side="right")
        self.f_sum = ctk.CTkFrame(self, fg_color="transparent"); self.f_sum.pack(fill="x", pady=(0,8))
        self.tabs = ctk.CTkTabview(self, fg_color=CARD, corner_radius=10)
        self.tabs.pack(fill="both", expand=True)
        self.tabs.add("📋 Ventas"); self.tabs.add("📊 Gráficos"); self.tabs.add("🏆 Productos")

        tv = self.tabs.tab("📋 Ventas")
        self.stree = make_tree(tv,
            ("id","date","time","client","user","subtotal","disc","total","pay"),
            ("ID","Fecha","Hora","Cliente","Vendedor","Subtotal","Desc","Total","Pago"),
            (40,90,55,150,100,100,78,100,90))
        self.stree.bind("<Double-1>", self._detail)
        self.f_chart = self.tabs.tab("📊 Gráficos")
        pt = self.tabs.tab("🏆 Productos")
        self.ptree = make_tree(pt, ("name","qty","rev"),("Producto","Unidades","Ingresos"),(300,100,160))

    def _range(self, days):
        t = date.today()
        self.e_d1.delete(0,"end"); self.e_d1.insert(0,(t-timedelta(days=days)).isoformat())
        self.e_d2.delete(0,"end"); self.e_d2.insert(0,t.isoformat())
        self._load()

    def _load(self):
        try:
            d1 = self.e_d1.get().strip(); d2 = self.e_d2.get().strip()
            if not d1 or not d2: return
            for w in self.f_sum.winfo_children(): w.destroy()
            summ = self.db.summary(d1, d2); pr = self.db.profit_summary(d1, d2)
            avg = summ["revenue"] / summ["cnt"] if summ["cnt"] else 0
            for icon, lbl, val, color in [
                ("💰","Ingresos",    fmt(summ["revenue"]), OK),
                ("📈","Ganancia",    fmt(pr["profit"]),     PURPLE),
                ("🛒","Ventas",      str(summ["cnt"]),      ACC),
                ("💸","Descuentos",  fmt(summ["disc"]),     WARN),
                ("🎫","Ticket Prom.",fmt(avg),               DIM),
            ]:
                c = W_card(self.f_sum); c.pack(side="left", expand=True, fill="x", padx=(0,5))
                W_label(c, icon, size=22).pack(pady=(10,2))
                W_label(c, str(val), size=15, bold=True, color=color).pack()
                W_label(c, lbl, size=9, color=DIM).pack(pady=(0,10))

            self.stree.delete(*self.stree.get_children())
            for sale in self.db.get_sales(d1, d2):
                self.stree.insert("","end", values=(sale["id"],sale["date"],sale["time"],sale["cn"],sale["uname"],
                    fmt(sale["subtotal"]),fmt(sale["discount"]),fmt(sale["total"]),sale["payment_method"]))
            self.ptree.delete(*self.ptree.get_children())
            for p in self.db.top_products(d1, d2, 30):
                self.ptree.insert("","end", values=(p["pname"],int(p["qty"]),fmt(p["rev"])))
            if HAS_MPL:
                self._draw_charts(d1, d2)
            else:
                for w in self.f_chart.winfo_children(): w.destroy()
                W_label(self.f_chart, "Instala matplotlib: pip install matplotlib",
                        color=DIM, size=12).pack(expand=True)
        except Exception as exc:
            log.error(f"Error cargando informes: {exc}", exc_info=True)
            messagebox.showerror("Error en Informes",
                f"No se pudo cargar el panel de informes:\n\n{exc}")

    def _draw_charts(self, d1, d2):
        try:
            # Limpiar canvas anterior y cerrar figura para liberar memoria
            for w in self.f_chart.winfo_children(): w.destroy()
            if self._fig is not None:
                try: self._fig.clf()
                except Exception: pass
                self._fig = None

            days = self.db.sales_by_day(d1, d2)
            pay  = self.db.sales_by_payment(d1, d2)
            cats = self.db.sales_by_category(d1, d2)
            clrs = [ACC, OK, WARN, ERR, PURPLE, "#1abc9c", "#e67e22"]

            self._fig = Figure(figsize=(10, 4), facecolor=CARD)

            ax1 = self._fig.add_subplot(131); ax1.set_facecolor("#1a1a1a")
            if days:
                ax1.bar([d["date"][-5:] for d in days], [d["rev"] for d in days],
                        color=ACC, width=0.65)
                ax1.set_title("Ventas por Día", color=TEXT, fontsize=9)
                ax1.tick_params(colors=DIM, labelsize=7)
                # Usamos set_xticklabels en lugar de plt.setp para evitar conflictos de estado global
                ax1.set_xticklabels([d["date"][-5:] for d in days],
                                    rotation=45, ha="right", fontsize=7, color=DIM)
            else:
                ax1.text(0.5, 0.5, "Sin datos", ha="center", va="center",
                         color=DIM, transform=ax1.transAxes)
            for sp in ax1.spines.values(): sp.set_color("#333")

            ax2 = self._fig.add_subplot(132); ax2.set_facecolor("#1a1a1a")
            if pay:
                ax2.pie([p["total"] for p in pay], labels=[p["pm"] for p in pay],
                        colors=clrs[:len(pay)], autopct="%1.1f%%",
                        textprops={"color": TEXT, "fontsize": 8},
                        wedgeprops={"linewidth": 0.5, "edgecolor": "#1a1a1a"})
                ax2.set_title("Método de Pago", color=TEXT, fontsize=9)
            else:
                ax2.text(0.5, 0.5, "Sin datos", ha="center", va="center",
                         color=DIM, transform=ax2.transAxes)

            ax3 = self._fig.add_subplot(133); ax3.set_facecolor("#1a1a1a")
            if cats:
                ax3.barh([c["cat"][:14] for c in cats[:6]], [c["rev"] for c in cats[:6]],
                         color=clrs[:min(len(cats), len(clrs))])
                ax3.set_title("Por Categoría", color=TEXT, fontsize=9)
                ax3.tick_params(colors=DIM, labelsize=7)
            else:
                ax3.text(0.5, 0.5, "Sin datos", ha="center", va="center",
                         color=DIM, transform=ax3.transAxes)
            for sp in ax3.spines.values(): sp.set_color("#333")

            self._fig.tight_layout(pad=2.0)
            canvas = FigureCanvasTkAgg(self._fig, self.f_chart)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True, padx=5, pady=5)
        except Exception as exc:
            log.error(f"Error dibujando gráficos: {exc}", exc_info=True)
            for w in self.f_chart.winfo_children(): w.destroy()
            W_label(self.f_chart,
                    f"⚠️ Error al cargar gráficos:\n{exc}\n\nVerifica que matplotlib esté instalado correctamente.",
                    color=ERR, size=11, wraplength=600).pack(expand=True)

    def _detail(self, _):
        sel = self.stree.selection()
        if not sel: return
        sid   = int(self.stree.item(sel[0])["values"][0])
        items = self.db.get_sale_items(sid)
        dlg   = ctk.CTkToplevel(self); dlg.title(f"Detalle Venta #{sid}")
        dlg.geometry("500x420"); dlg.grab_set(); dlg.configure(fg_color=BG)
        W_label(dlg, f"Venta #{sid}", size=14, bold=True, color=ACC).pack(pady=(18,8))
        frm = ctk.CTkFrame(dlg, fg_color=CARD, corner_radius=8); frm.pack(fill="both", expand=True, padx=12, pady=5)
        t = make_tree(frm,("name","qty","price","sub"),("Producto","Cant","Precio","Subtotal"),(215,60,110,110))
        for i in items:
            t.insert("","end", values=(i["product_name"],i["quantity"],fmt(i["unit_price"]),fmt(i["subtotal"])))
        bot = ctk.CTkFrame(dlg, fg_color="transparent"); bot.pack(fill="x", padx=12, pady=8)
        W_label(bot, f"Total: {fmt(sum(i['subtotal'] for i in items))}", bold=True, color=OK).pack(side="left", pady=4)
        def anular():
            if messagebox.askyesno("Anular Venta",
                f"¿Anular venta #{sid} y reponer el stock?\nEsta acción no se puede deshacer.", parent=dlg):
                self.db.delete_sale(sid); dlg.destroy(); self._load()
                messagebox.showinfo("✅","Venta anulada y stock restaurado.")
        W_btn(bot, "🗑️ Anular Venta", anular, color=ERR, w=130).pack(side="right")

    def _export_excel(self):
        if not HAS_PD: messagebox.showwarning("Sin pandas","pip install pandas openpyxl"); return
        d1=self.e_d1.get().strip(); d2=self.e_d2.get().strip()
        path = filedialog.asksaveasfilename(defaultextension=".xlsx",filetypes=[("Excel","*.xlsx")],
               initialfile=f"ventas_{d1}_a_{d2}.xlsx")
        if not path: return
        try: self.db.export_sales_excel(path,d1,d2); messagebox.showinfo("Exportado",f"Guardado:\n{path}")
        except Exception as exc: messagebox.showerror("Error",str(exc))


# ═══════════════════════════════════════════════════════════════
# CATEGORÍAS
# ═══════════════════════════════════════════════════════════════
class CategoriasPanel(BasePanel):
    def __init__(self, master, db, user):
        super().__init__(master, db, user, "🏷️ Gestión de Categorías")
        self._build(); self._refresh()

    def _build(self):
        body = ctk.CTkFrame(self, fg_color="transparent"); body.pack(fill="both", expand=True)
        lf = W_card(body); lf.pack(side="left", fill="both", expand=True, padx=(0,12))
        W_label(lf, "Categorías existentes", bold=True, color=ACC).pack(pady=(14,6))
        W_sep(lf)
        frm = ctk.CTkFrame(lf, fg_color="transparent"); frm.pack(fill="both", expand=True, padx=10, pady=5)
        self.lbox = tk.Listbox(frm, bg=CARD, fg=TEXT, font=("Segoe UI",11),
                               selectbackground=ACC, relief="flat", activestyle="none", borderwidth=0)
        self.lbox.pack(fill="both", expand=True)
        W_btn(lf, "🗑 Eliminar seleccionada", self._del, color=ERR, w=250).pack(pady=10)
        rf = W_card(body); rf.pack(side="left", fill="y", ipadx=10)
        rf.configure(width=280); rf.pack_propagate(False)
        W_label(rf, "Nueva categoría", bold=True, color=ACC).pack(pady=(14,8))
        W_sep(rf)
        W_label(rf, "Nombre", size=10, color=DIM).pack(anchor="w", padx=20, pady=(12,2))
        self.e_new = W_entry(rf, "ej: Ferretería", w=240); self.e_new.pack(padx=20)
        W_btn(rf, "➕ Agregar", self._add, w=240, h=38).pack(padx=20, pady=12)

    def _refresh(self):
        self.lbox.delete(0,"end")
        for cat in self.db.get_categories(): self.lbox.insert("end", cat)

    def _add(self):
        name = self.e_new.get().strip()
        if not name: messagebox.showinfo("Info","Escribe un nombre"); return
        self.db.add_category(name); self.e_new.delete(0,"end"); self._refresh()

    def _del(self):
        sel = self.lbox.curselection()
        if not sel: messagebox.showinfo("Info","Selecciona una categoría"); return
        name = self.lbox.get(sel[0])
        if messagebox.askyesno("Confirmar",f"¿Eliminar '{name}'?"):
            self.db.del_category(name); self._refresh()


# ═══════════════════════════════════════════════════════════════
# USUARIOS
# ═══════════════════════════════════════════════════════════════
class UsuariosPanel(BasePanel):
    def __init__(self, master, db, user):
        super().__init__(master, db, user, "👤 Gestión de Usuarios")
        self._sel = None; self._build(); self._refresh()

    def _build(self):
        tb = ctk.CTkFrame(self, fg_color="transparent"); tb.pack(fill="x", pady=(0,8))
        W_btn(tb,"➕ Nuevo",   self._new,  w=110).pack(side="left")
        W_btn(tb,"✏️ Editar",  self._edit, w=110, color="#444").pack(side="left", padx=4)
        W_btn(tb,"🗑 Eliminar",self._del,  w=110, color=ERR).pack(side="left")
        frm = W_card(self); frm.pack(fill="both", expand=True)
        self.tree = make_tree(frm, ("id","username","role","active"),
                              ("ID","Usuario","Rol","Estado"), (50,250,150,120))
        self.tree.bind("<<TreeviewSelect>>", lambda _: self._on_sel())
        self.tree.bind("<Double-1>", lambda _: self._edit())

    def _on_sel(self):
        s = self.tree.selection()
        self._sel = int(self.tree.item(s[0])["values"][0]) if s else None

    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        for u in self.db.get_users():
            self.tree.insert("","end", values=(u["id"],u["username"],u["role"],
                "✅ Activo" if u["active"] else "❌ Inactivo"))

    def _form(self, title, data=None):
        dlg = ctk.CTkToplevel(self); dlg.title(title); dlg.geometry(f"{_sc(600)}x{_sc(320)}"); dlg.grab_set()
        dlg.configure(fg_color=BG)
        W_label(dlg, title, size=16, bold=True, color=ACC).pack(pady=(20,10))
        
        container = ctk.CTkFrame(dlg, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=_sc(20), pady=_sc(10))
        container.columnconfigure(0, weight=1, pad=_sc(15))
        container.columnconfigure(1, weight=1, pad=_sc(15))

        f_user = ctk.CTkFrame(container, fg_color="transparent")
        f_user.grid(row=0, column=0, sticky="ew", padx=_sc(8), pady=_sc(8))
        W_label(f_user,"Usuario *", size=10, color=DIM).pack(anchor="w", pady=(0, 2))
        eu = W_entry(f_user, w=260); eu.pack(fill="x")
        if data: eu.insert(0, data["username"])

        f_pw = ctk.CTkFrame(container, fg_color="transparent")
        f_pw.grid(row=0, column=1, sticky="ew", padx=_sc(8), pady=_sc(8))
        W_label(f_pw,"Contraseña"+((" (vacío = no cambiar)") if data else " *"), size=10, color=DIM).pack(anchor="w", pady=(0, 2))
        ep = W_entry(f_pw, pw=True, w=260); ep.pack(fill="x")

        f_rol = ctk.CTkFrame(container, fg_color="transparent")
        f_rol.grid(row=1, column=0, sticky="ew", padx=_sc(8), pady=_sc(8))
        W_label(f_rol,"Rol", size=10, color=DIM).pack(anchor="w", pady=(0, 2))
        rc = W_combo(f_rol,["admin","vendedor","consulta"], w=260); rc.pack(fill="x")
        if data: rc.set(data["role"])

        f_act = ctk.CTkFrame(container, fg_color="transparent")
        f_act.grid(row=1, column=1, sticky="ew", padx=_sc(8), pady=_sc(8))
        av = tk.IntVar(value=1 if not data else data["active"])
        ctk.CTkCheckBox(f_act,text="Usuario Activo",variable=av,font=("Segoe UI",11)).pack(anchor="w", pady=(20, 0))
        def save():
            u=eu.get().strip(); p=ep.get().strip()
            if not u: messagebox.showerror("Error","Usuario obligatorio",parent=dlg); return
            if not data and not p: messagebox.showerror("Error","Contraseña obligatoria",parent=dlg); return
            try:
                if data: self.db.upd_user(data["id"],u,p,rc.get(),av.get())
                else:    self.db.add_user(u,p,rc.get())
                dlg.destroy(); self._refresh()
            except Exception as exc: messagebox.showerror("Error",str(exc),parent=dlg)
        W_btn(dlg,"💾 Guardar",save,w=348,h=40).pack(padx=26,pady=10)

    def _new(self): self._form("Nuevo Usuario")
    def _edit(self):
        if not self._sel: messagebox.showinfo("Info","Selecciona un usuario"); return
        data = next((u for u in self.db.get_users() if u["id"]==self._sel),None)
        if data: self._form("Editar Usuario",data)
    def _del(self):
        if not self._sel: messagebox.showinfo("Info","Selecciona un usuario"); return
        u = next((x for x in self.db.get_users() if x["id"]==self._sel),None)
        if u and u["username"]=="admin": messagebox.showwarning("Protegido","No puedes eliminar el usuario admin"); return
        if u and u["id"]==self.user["id"]: messagebox.showwarning("Protegido","No puedes eliminar tu propia cuenta"); return
        if messagebox.askyesno("Confirmar","¿Eliminar este usuario?"):
            self.db.del_user(self._sel); self._sel=None; self._refresh()


# ═══════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════
class ConfigPanel(BasePanel):
    def __init__(self, master, db, user):
        super().__init__(master, db, user, "⚙ Configuración del Negocio")
        self._build()

    def _build(self):
        # ── Contenedor principal scrollable ──────────────────────────
        sf = ctk.CTkScrollableFrame(self, fg_color="transparent")
        sf.pack(fill="both", expand=True)

        # ── Dos columnas ─────────────────────────────────────────────
        cols = ctk.CTkFrame(sf, fg_color="transparent")
        cols.pack(fill="both", expand=True)
        cols.columnconfigure(0, weight=1)
        cols.columnconfigure(1, weight=1)

        # ══════════════════════════════════════════════════════════════
        # COLUMNA IZQUIERDA — Datos del negocio
        # ══════════════════════════════════════════════════════════════
        left = W_card(cols)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=0)

        W_label(left, "Datos del negocio", bold=True, color=ACC).pack(pady=(16, 4))
        W_sep(left)

        fields = [
            ("Nombre del negocio",            "business_name"),
            ("Tipo de negocio",               "business_type"),
            ("Símbolo de moneda (ej: $)",     "currency_symbol"),
            ("Código de moneda (ej: COP)",    "currency_code"),
            ("Dirección",                     "address"),
            ("Teléfono / Contacto",           "phone"),
            ("% Impuesto (0 = sin impuesto)", "tax_percent"),
            ("Stock mínimo por defecto",      "low_stock_limit"),
            ("Máximo descuadre sin admin (0=sin límite)", "max_diff_allowed"),
        ]
        self.entries = {}
        grid_l = ctk.CTkFrame(left, fg_color="transparent")
        grid_l.pack(padx=20, pady=10, fill="x")
        for i, (lbl, key) in enumerate(fields):
            W_label(grid_l, lbl, size=10, color=DIM).grid(
                row=i, column=0, sticky="w", pady=6, padx=(0, 16))
            e = W_entry(grid_l, w=200)
            v = self.db.cfg(key)
            if v: e.insert(0, v)
            e.grid(row=i, column=1, sticky="w")
            self.entries[key] = e

        W_sep(left)
        W_btn(left, "💾  Guardar configuración general", self._save,
              w=300, h=42).pack(pady=(12, 6))
        W_label(left, f"Log del día: {_log_file}", size=9, color=DIM).pack(pady=(0, 12))

        # ══════════════════════════════════════════════════════════════
        # COLUMNA DERECHA — Logo + Impresora POS
        # ══════════════════════════════════════════════════════════════
        right = W_card(cols)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=0)

        # ── Logo ────────────────────────────────────────────────────
        W_label(right, "Logo del negocio", bold=True, color=ACC).pack(pady=(16, 2))
        W_label(right, "Aparece en la pantalla de inicio de sesión",
                size=9, color=DIM).pack()
        W_sep(right)

        logo_row = ctk.CTkFrame(right, fg_color="transparent")
        logo_row.pack(fill="x", padx=20, pady=(10, 8))
        current = self.db.cfg("logo_path") or ""
        self._logo_lbl = W_label(logo_row,
            os.path.basename(current) if current else "Sin logo",
            size=10, color=OK if current else DIM)
        self._logo_lbl.pack(side="left", fill="x", expand=True)

        def _pick_logo():
            path = filedialog.askopenfilename(
                title="Seleccionar logo",
                filetypes=[("Imágenes", "*.png *.jpg *.jpeg *.webp *.bmp"), ("Todos", "*.*")])
            if path:
                self.db.set_cfg("logo_path", path)
                self._logo_lbl.configure(text=os.path.basename(path), text_color=OK)
                log.info(f"Logo actualizado: {path}")

        def _clear_logo():
            self.db.set_cfg("logo_path", "")
            self._logo_lbl.configure(text="Sin logo", text_color=DIM)
            log.info("Logo eliminado")

        W_btn(logo_row, "📂  Seleccionar", _pick_logo, w=140, h=32).pack(side="left", padx=(4, 4))
        W_btn(logo_row, "✕  Quitar", _clear_logo, color="#444", w=90, h=32).pack(side="left")

        # ── Impresora POS ────────────────────────────────────────────
        W_sep(right)
        W_label(right, "🖨  Impresora POS", bold=True, color=ACC).pack(pady=(14, 2))
        W_label(right, "Configura tu impresora térmica", size=9, color=DIM).pack()
        W_sep(right)

        pr_grid = ctk.CTkFrame(right, fg_color="transparent")
        pr_grid.pack(padx=20, pady=(10, 8), fill="x")
        pr_grid.columnconfigure(1, weight=1)

        # ── Lista de impresoras via pywin32 ──────────────────────────
        def _get_printers():
            try:
                import win32print
                printers = [p[2] for p in win32print.EnumPrinters(
                    win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)]
                return printers if printers else ["(sin impresoras)"]
            except Exception:
                return ["(pywin32 no disponible)"]

        saved_printer = self.db.cfg("printer_name") or ""
        printer_list = _get_printers()
        if saved_printer and saved_printer not in printer_list:
            printer_list.insert(0, saved_printer)

        W_label(pr_grid, "Impresora", size=10, color=DIM).grid(
            row=0, column=0, sticky="w", pady=6, padx=(0, 12))
        self._cb_printer = W_combo(pr_grid, printer_list, w=220)
        if saved_printer and saved_printer in printer_list:
            self._cb_printer.set(saved_printer)
        elif printer_list:
            self._cb_printer.set(printer_list[0])
        self._cb_printer.grid(row=0, column=1, sticky="w")

        W_label(pr_grid, "Ancho", size=10, color=DIM).grid(
            row=1, column=0, sticky="w", pady=6, padx=(0, 12))
        widths = ["58mm", "80mm (estándar)", "104mm"]
        saved_w = self.db.cfg("printer_width") or "80mm (estándar)"
        self._cb_width = W_combo(pr_grid, widths, w=220)
        self._cb_width.set(saved_w if saved_w in widths else widths[1])
        self._cb_width.grid(row=1, column=1, sticky="w")

        # Checkbox impresión automática
        self._pr_auto_var = tk.IntVar(
            value=1 if self.db.cfg("printer_enabled") == "1" else 0)
        ctk.CTkCheckBox(pr_grid, text="Imprimir automáticamente al cobrar",
                        variable=self._pr_auto_var,
                        font=("Segoe UI", _sc(10))).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        def _save_printer():
            name = self._cb_printer.get().strip()
            self.db.set_cfg("printer_name", name)
            self.db.set_cfg("printer_width", self._cb_width.get())
            self.db.set_cfg("printer_enabled", str(self._pr_auto_var.get()))
            messagebox.showinfo("✅ Impresora", f"Configuración guardada:\n{name}")
            log.info(f"Impresora guardada: {name}")

        def _test_printer():
            name = self._cb_printer.get().strip()
            if not name or name.startswith("("):
                messagebox.showwarning("Impresora", "Selecciona una impresora válida"); return
            try:
                import win32print, win32api
                bname = self.db.cfg("business_name") or "GestiónPro"
                ticket = (
                    f"{'='*40}\n"
                    f"   {bname}\n"
                    f"{'='*40}\n"
                    f"   PRUEBA DE IMPRESORA\n"
                    f"   La impresora funciona.\n"
                    f"{'='*40}\n\n\n\n"
                )
                hprn = win32print.OpenPrinter(name)
                try:
                    win32print.StartDocPrinter(hprn, 1, ("Test", None, "RAW"))
                    win32print.StartPagePrinter(hprn)
                    win32print.WritePrinter(hprn, ticket.encode("cp437", errors="replace"))
                    win32print.EndPagePrinter(hprn)
                    win32print.EndDocPrinter(hprn)
                finally:
                    win32print.ClosePrinter(hprn)
                messagebox.showinfo("✅ Impresora", f"Ticket enviado a:\n{name}")
            except ImportError:
                messagebox.showerror("Error", "pywin32 no está instalado.\npip install pywin32")
            except Exception as ex:
                messagebox.showerror("❌ Error de impresora", str(ex))

        def _refresh_printers():
            fresh = _get_printers()
            self._cb_printer.configure(values=fresh)
            if fresh: self._cb_printer.set(fresh[0])

        btn_row = ctk.CTkFrame(right, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(10, 16))
        W_btn(btn_row, "💾  Guardar imp.", _save_printer, w=140, h=36).pack(side="left")
        W_btn(btn_row, "🧪  Prueba", _test_printer, color=OK, w=90, h=36).pack(side="left", padx=6)
        W_btn(btn_row, "🔍  Buscar", _refresh_printers, color="#444", w=90, h=36).pack(side="left")

        # ══════════════════════════════════════════════════════════════
        # FILA 1 — Facturación Electrónica DIAN (Factus)
        # ══════════════════════════════════════════════════════════════
        factus_card = W_card(cols)
        factus_card.grid(row=1, column=0, columnspan=2, sticky="ew",
                         padx=0, pady=(8, 0))

        W_label(factus_card, "📄 Facturación Electrónica DIAN — Factus",
                bold=True, color="#3498db").pack(pady=(16, 2))
        W_label(factus_card,
                "Completa estos datos para emitir facturas electrónicas válidas ante la DIAN de Colombia.",
                size=9, color=DIM).pack()
        W_sep(factus_card)

        factus_grid = ctk.CTkFrame(factus_card, fg_color="transparent")
        factus_grid.pack(padx=20, pady=10, fill="x")
        factus_grid.columnconfigure(1, weight=1)
        factus_grid.columnconfigure(3, weight=1)

        factus_fields = [
            # (fila, col_lbl, col_entry, label, key, es_password)
            (0, 0, 1, "Client ID",            "factus_client_id",          False),
            (0, 2, 3, "Client Secret",         "factus_client_secret",       True),
            (1, 0, 1, "Email (usuario Factus)","factus_username",            False),
            (1, 2, 3, "Contraseña Factus",     "factus_password",             True),
            (2, 0, 1, "Numbering Range ID",    "factus_numbering_range_id",  False),
            (2, 2, 3, "Código Municipio DIAN", "factus_municipality_code",   False),
            (3, 0, 1, "Prefijo de Factura",    "invoice_prefix",             False),
        ]
        self._factus_entries = {}
        env_options = ["sandbox", "production"]
        for row_i, col_l, col_e, lbl_txt, key, is_pw in factus_fields:
            W_label(factus_grid, lbl_txt, size=10, color=DIM).grid(
                row=row_i, column=col_l, sticky="w", pady=6, padx=(0 if col_l==0 else 16, 8))
            e = W_entry(factus_grid, pw=is_pw, w=200)
            v = self.db.cfg(key)
            if v: e.insert(0, v)
            e.grid(row=row_i, column=col_e, sticky="ew", pady=6)
            self._factus_entries[key] = e

        # Entorno (combo)
        W_label(factus_grid, "Entorno", size=10, color=DIM).grid(
            row=3, column=2, sticky="w", pady=6, padx=(16, 8))
        self._cb_factus_env = W_combo(factus_grid, env_options, w=200)
        saved_env = self.db.cfg("factus_environment") or "sandbox"
        self._cb_factus_env.set(saved_env if saved_env in env_options else "sandbox")
        self._cb_factus_env.grid(row=3, column=3, sticky="ew", pady=6)

        # Info ayuda
        W_label(factus_card,
                "🔑 Obtén tus credenciales en factus.com.co → Desarrolladores → Aplicaciones",
                size=9, color=DIM).pack(pady=(0, 4))
        W_label(factus_card,
                "🌐 Usa 'sandbox' para pruebas y 'production' cuando tengas habilitación de la DIAN.",
                size=9, color=DIM).pack(pady=(0, 4))

        def _save_factus():
            for key, widget in self._factus_entries.items():
                self.db.set_cfg(key, widget.get().strip())
            self.db.set_cfg("factus_environment", self._cb_factus_env.get())
            messagebox.showinfo("✅ Factus",
                "Credenciales de Factus guardadas correctamente.\n"
                "Podrás emitir facturas DIAN desde el Punto de Venta.")
            log.info("Configuración de Factus actualizada.")

        W_btn(factus_card, "💾  Guardar configuración Factus",
              _save_factus, color="#2980b9", w=280, h=42).pack(pady=(8, 16))

    def _save(self):
        for key, e in self.entries.items():
            self.db.set_cfg(key, e.get().strip())
        messagebox.showinfo("✅ Guardado",
            "Configuración guardada.\nReinicia para aplicar cambios de nombre/logo.")
        log.info("Configuración general actualizada")




# ═══════════════════════════════════════════════════════════════
# BACKUP AUTOMÁTICO
# ═══════════════════════════════════════════════════════════════
def _backup_db(db_path="gestionpro.db"):
    """Crea un backup .zip del .db en backups/ y rota los últimos 7."""
    try:
        # Ruta del .db relativa al ejecutable/script
        base_dir = os.path.dirname(os.path.abspath(
            sys.executable if getattr(sys, 'frozen', False) else __file__
        ))
        db_full = os.path.join(base_dir, db_path)
        if not os.path.isfile(db_full):
            log.warning(f"Backup omitido: no se encontró {db_full}")
            return
        # Crear carpeta backups/
        bk_dir = os.path.join(base_dir, "backups")
        os.makedirs(bk_dir, exist_ok=True)
        # Nombre: gestionpro_20260609_1225.zip
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        zip_name = f"gestionpro_{ts}.zip"
        zip_path = os.path.join(bk_dir, zip_name)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(db_full, os.path.basename(db_full))
        log.info(f"Backup creado: {zip_path}")
        # Rotación: conservar solo los últimos 7
        backups = sorted(glob.glob(os.path.join(bk_dir, "gestionpro_*.zip")))
        while len(backups) > 7:
            old = backups.pop(0)
            os.remove(old)
            log.info(f"Backup antiguo eliminado: {os.path.basename(old)}")
    except Exception as e:
        log.error(f"Error al crear backup: {e}")


# ═══════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════
def main():
    global _DB
    log.info("=== GestiónPro v2.0 iniciando ===")
    # ── Inicializar BD y escala primero ──
    _DB = DB()
    _init_scale()
    # ── Validar / Activar licencia ──
    if not check_license_and_run(_DB):
        _DB.close()
        log.info("Sin licencia válida — saliendo.")
        sys.exit(0)
    # ── Wizard de primer arranque ──
    if _DB.cfg("wizard_done") != "1":
        wiz = SetupWizard(_DB)
        wiz.mainloop()
        if not wiz.completed:
            _DB.close()
            log.info("Wizard cancelado — saliendo")
            return
    login = LoginWindow()
    login.mainloop()
    if login.result:
        app = MainWindow(login.result)
        app.mainloop()
    _DB.close()
    _backup_db()    # backup automático al cerrar
    log.info("=== GestiónPro cerrado ===")

if __name__ == "__main__":
    main()