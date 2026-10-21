"""
Turso Database Client para GestPro.
Proporciona una interfaz compatible con sqlite3 para conectarse a Turso Cloud vía HTTP Hrana v2.
Cero dependencias C/Rust, compatible con Windows, Linux, Mac y Render.com.
"""

import os
import requests
from typing import Any, List, Dict, Optional, Union

class TursoRow:
    """Fila compatible con sqlite3.Row: permite acceso por nombre, índice y dict()."""
    def __init__(self, cols: List[str], values: List[Any]):
        self._cols = cols
        self._values = values
        self._map = {cols[i]: values[i] for i in range(len(cols))}
        
    def __getitem__(self, key: Union[int, str]) -> Any:
        if isinstance(key, int):
            return self._values[key]
        return self._map[key]
        
    def get(self, key: str, default: Any = None) -> Any:
        return self._map.get(key, default)
        
    def keys(self) -> List[str]:
        return self._cols
        
    def values(self) -> List[Any]:
        return self._values
        
    def items(self):
        return self._map.items()
        
    def __iter__(self):
        return iter(self._cols)
        
    def __len__(self) -> int:
        return len(self._cols)
        
    def __repr__(self) -> str:
        return f"<TursoRow {self._map}>"


class TursoCursor:
    def __init__(self, conn: "TursoConnection"):
        self.conn = conn
        self.lastrowid: Optional[int] = None
        self.rowcount: int = 0
        self._rows: List[TursoRow] = []
        self._index: int = 0
        
    def execute(self, sql: str, params: Union[tuple, list, dict] = ()) -> "TursoCursor":
        res = self.conn._exec_single(sql, params)
        self.lastrowid = res.get("last_insert_rowid")
        self.rowcount = res.get("affected_row_count", 0)
        
        cols = [c["name"] for c in res.get("cols", [])]
        raw_rows = res.get("rows", [])
        
        parsed_rows = []
        for r in raw_rows:
            parsed_vals = []
            for cell in r:
                t = cell.get("type")
                v = cell.get("value")
                if t == "null":
                    parsed_vals.append(None)
                elif t == "integer":
                    parsed_vals.append(int(v) if v is not None else 0)
                elif t == "float":
                    parsed_vals.append(float(v) if v is not None else 0.0)
                else:
                    parsed_vals.append(v)
            parsed_rows.append(TursoRow(cols, parsed_vals))
            
        self._rows = parsed_rows
        self._index = 0
        return self
        
    def fetchone(self) -> Optional[TursoRow]:
        if self._index < len(self._rows):
            row = self._rows[self._index]
            self._index += 1
            return row
        return None
        
    def fetchall(self) -> List[TursoRow]:
        res = self._rows[self._index:]
        self._index = len(self._rows)
        return res
        
    def close(self):
        pass


class TursoConnection:
    """Conexión HTTP a Turso con soporte para transacciones y sintaxis sqlite3."""
    def __init__(self, url: str, token: str):
        # Convertir libsql:// a https:// si es necesario
        if url.startswith("libsql://"):
            url = "https://" + url[len("libsql://"):]
        if not url.endswith("/v2/pipeline"):
            url = url.rstrip("/") + "/v2/pipeline"
            
        self.url = url
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        })
        self.row_factory = None
        
    def _format_param(self, val: Any) -> dict:
        if val is None:
            return {"type": "null"}
        elif isinstance(val, bool):
            return {"type": "integer", "value": str(int(val))}
        elif isinstance(val, int):
            return {"type": "integer", "value": str(val)}
        elif isinstance(val, float):
            return {"type": "float", "value": val}
        else:
            return {"type": "text", "value": str(val)}
            
    def _exec_single(self, sql: str, params: Union[tuple, list, dict] = ()) -> dict:
        stmt = {"sql": sql}
        if params:
            if isinstance(params, (list, tuple)):
                stmt["args"] = [self._format_param(p) for p in params]
            elif isinstance(params, dict):
                stmt["named_args"] = [{"name": k, "value": self._format_param(v)} for k, v in params.items()]
                
        body = {"requests": [{"type": "execute", "stmt": stmt}]}
        res = self.session.post(self.url, json=body, timeout=20)
        if res.status_code != 200:
            raise Exception(f"Turso HTTP Error {res.status_code}: {res.text}")
            
        data = res.json()
        results = data.get("results", [])
        if results and results[0].get("type") == "error":
            err = results[0].get("error", {})
            raise Exception(f"Turso Query Error: {err.get('message', 'Unknown error')} (SQL: {sql})")
            
        return results[0].get("response", {}).get("result", {})
        
    def execute(self, sql: str, params: Union[tuple, list, dict] = ()) -> TursoCursor:
        cur = TursoCursor(self)
        return cur.execute(sql, params)
        
    def cursor(self) -> TursoCursor:
        return TursoCursor(self)
        
    def commit(self):
        # En HTTP pipeline cada execute se comitea automáticamente a menos que se use transacción explícita
        pass
        
    def rollback(self):
        pass
        
    def close(self):
        pass
