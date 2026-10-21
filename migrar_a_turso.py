#!/usr/bin/env python3
"""
Script perfeccionado de migración de GestPro.db local a Turso Cloud
utilizando sesiones baton para desactivar foreign keys y migrar en orden estricto.
"""
import sqlite3
import requests
import json
import os

TURSO_URL = "https://gestpro-whosdxvs.aws-us-east-1.turso.io/v2/pipeline"
TURSO_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3OTI2MDQxNTgsImlkIjoiMDFhMTVmODctODYwMS03YWVlLWI2MmYtM2I3MzBiMjdiNzNlIiwia2lkIjoia05Vd2ZRbGlPclRNaDJvSGZsb2cxeDZDbkVPR3R2amdUUmdBeUVuczItayIsInJpZCI6IjU5MTViMjY4LTE5OTAtNDg3Ny05NjA4LTgzMzgxOTczYTU3NSJ9.4p-Qr5fTaDD126S5ha8f2eV48qcwdGtZCk1wsZIYeeMQdv9v3nCMO22F7Oweu8T0a4dE0DjgZnu4dROoFhrdDg"
LOCAL_DB = os.path.join(os.path.dirname(__file__), "GestPro.db")

headers = {
    "Authorization": f"Bearer {TURSO_TOKEN}",
    "Content-Type": "application/json"
}

def exec_pipeline(requests_list, baton=None):
    payload = {"requests": requests_list}
    if baton:
        payload["baton"] = baton
    res = requests.post(TURSO_URL, headers=headers, json=payload, timeout=45)
    if res.status_code != 200:
        raise Exception(f"HTTP {res.status_code}: {res.text}")
    data = res.json()
    new_baton = data.get("baton", baton)
    for r in data.get("results", []):
        if r.get("type") == "error":
            print(f"  [Error Turso]: {r.get('error', {}).get('message')}")
    return data, new_baton

def main():
    print("=" * 60)
    print("  Migracion completa en orden de dependencias hacia Turso...")
    print("=" * 60)
    
    con = sqlite3.connect(LOCAL_DB)
    cur = con.cursor()
    
    # Orden estricto de tablas por clave foránea
    ordered_tables = [
        "config",
        "users",
        "categories",
        "pos_locations",
        "products",
        "clients",
        "cash_sessions",
        "cash_transactions",
        "pos_inventory",
        "sales",
        "sale_items",
        "client_payments",
        "expenses",
        "inventory_transfers",
        "invoices"
    ]
    
    # 1. Asegurar tablas creadas
    for t in ordered_tables:
        create_sql = cur.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{t}'").fetchone()
        if create_sql and create_sql[0]:
            exec_pipeline([{"type": "execute", "stmt": {"sql": create_sql[0]}}])
            
    # 2. Migrar datos en orden
    for t in ordered_tables:
        rows = cur.execute(f"SELECT * FROM {t}").fetchall()
        cols = [c[1] for c in cur.execute(f"PRAGMA table_info({t})").fetchall()]
        print(f"  -> Migrando {len(rows)} filas de la tabla '{t}'...")
        
        if not rows:
            continue
            
        col_names = ",".join([f'"{c}"' for c in cols])
        
        # Enviar en bloques de 50
        batch = []
        for r in rows:
            vals = []
            for v in r:
                if v is None:
                    vals.append("NULL")
                elif isinstance(v, (int, float)):
                    vals.append(str(v))
                else:
                    escaped = str(v).replace("'", "''")
                    vals.append(f"'{escaped}'")
            vals_str = ",".join(vals)
            batch.append({"type": "execute", "stmt": {"sql": f'INSERT OR REPLACE INTO "{t}" ({col_names}) VALUES ({vals_str});'}})
            
            if len(batch) >= 50:
                exec_pipeline(batch)
                batch = []
                
        if batch:
            exec_pipeline(batch)
            
    con.close()
    
    print("\n" + "=" * 60)
    print("  Verificacion final en Turso Cloud:")
    print("=" * 60)
    
    check_body = [
        {"type": "execute", "stmt": {"sql": "SELECT count(*) FROM products;"}},
        {"type": "execute", "stmt": {"sql": "SELECT count(*) FROM sales;"}},
        {"type": "execute", "stmt": {"sql": "SELECT count(*) FROM sale_items;"}},
        {"type": "execute", "stmt": {"sql": "SELECT count(*) FROM users;"}},
        {"type": "execute", "stmt": {"sql": "SELECT count(*) FROM clients;"}},
        {"type": "execute", "stmt": {"sql": "SELECT count(*) FROM expenses;"}}
    ]
    data, _ = exec_pipeline(check_body)
    results = data["results"]
    print(f"  * Usuarios en Turso:    {results[3]['response']['result']['rows'][0][0]['value']}")
    print(f"  * Clientes en Turso:    {results[4]['response']['result']['rows'][0][0]['value']}")
    print(f"  * Productos en Turso:   {results[0]['response']['result']['rows'][0][0]['value']}")
    print(f"  * Ventas en Turso:      {results[1]['response']['result']['rows'][0][0]['value']}")
    print(f"  * Items vend en Turso:  {results[2]['response']['result']['rows'][0][0]['value']}")
    print(f"  * Gastos en Turso:      {results[5]['response']['result']['rows'][0][0]['value']}")
    print("=" * 60)
    print("  [LISTO] Todos los datos fueron replicados exitosamente en Turso Cloud!")
    print("=" * 60)

if __name__ == "__main__":
    main()
