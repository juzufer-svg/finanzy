"""
In-memory demo database for testing without Supabase
Use this when real Supabase credentials are not available
"""
import threading
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Dict
import uuid


class ErrorBD(Exception):
    """Equivalente en memoria al error de la BD real: lleva el SQLSTATE en `code` (FZ001 saldo negativo, FZ002 cuenta
    archivada, FZ003 tope de cuentas, 23505 nombre repetido, 23503 llave foránea, 23514 CHECK). Sin texto de la BD."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _dec(valor) -> Decimal:
    return valor if isinstance(valor, Decimal) else Decimal(str(valor))


def _efecto(tipo: str, monto) -> Decimal:
    """Efecto de una transacción sobre el saldo de su cuenta de dinero (igual que `cuenta_saldo_actual`)."""
    if tipo == "ingreso":
        return _dec(monto)
    if tipo == "gasto":
        return -_dec(monto)
    return Decimal(0)


class DemoTransaccionDB:
    """In-memory transacciones database"""
    
    _transacciones: Dict[str, dict] = {}
    
    @staticmethod
    async def crear(usuario_id: str, categoria_id: str, monto: float,
                    descripcion: str, fecha: str, tipo: str, medio_pago: Optional[str] = None,
                    cuenta_id: Optional[str] = None) -> dict:
        """Create transaction"""
        trans_id = str(uuid.uuid4())
        # Las reglas de las cuentas de dinero (INV-046/048/050) se evalúan ANTES de guardar: nada queda a medias
        DemoCuentaDB.validar_transaccion(usuario_id, None, {"cuenta_id": cuenta_id, "tipo": tipo, "monto": monto})
        transaccion = {
            "id": trans_id,
            "usuario_id": usuario_id,
            "categoria_id": categoria_id,
            "monto": monto,
            "descripcion": descripcion,
            "fecha": fecha,
            "tipo": tipo,
            "medio_pago": medio_pago,
            "cuenta_id": cuenta_id,
        }
        DemoTransaccionDB._transacciones[trans_id] = transaccion
        return transaccion
    
    @staticmethod
    async def obtener_por_usuario(usuario_id: str, mes: Optional[str] = None) -> list:
        """Get user transactions"""
        transacciones = [t for t in DemoTransaccionDB._transacciones.values() 
                        if t["usuario_id"] == usuario_id]
        
        if mes:
            transacciones = [t for t in transacciones if t["fecha"].startswith(mes)]
        
        return transacciones
    
    @staticmethod
    async def obtener_por_id(transaccion_id: str):
        """Get transaction by ID"""
        return DemoTransaccionDB._transacciones.get(transaccion_id)

    @staticmethod
    async def actualizar(transaccion_id: str, **kwargs) -> dict:
        """Update transaction"""
        if transaccion_id in DemoTransaccionDB._transacciones:
            allowed = {'categoria_id', 'monto', 'descripcion', 'fecha', 'tipo', 'medio_pago', 'cuenta_id'}
            actual = DemoTransaccionDB._transacciones[transaccion_id]
            cambios = {k: v for k, v in kwargs.items() if k in allowed}
            DemoCuentaDB.validar_transaccion(actual["usuario_id"], actual, {**actual, **cambios})  # antes de tocar nada
            actual.update(cambios)
            return actual
        return None

    @staticmethod
    async def eliminar(transaccion_id: str) -> bool:
        """Delete transaction"""
        if transaccion_id in DemoTransaccionDB._transacciones:
            actual = DemoTransaccionDB._transacciones[transaccion_id]
            DemoCuentaDB.validar_transaccion(actual["usuario_id"], actual, None)
            del DemoTransaccionDB._transacciones[transaccion_id]
            return True
        return False


class DemoCuentaDB:
    """Cuentas de dinero en memoria (CHG-019). SOLO existe sin Supabase y fuera de producción (`auth_estado._modo`).
    Implementa las MISMAS reglas que los disparadores `fz001_*`/`fz003_*` de `backend/sql/2026-11-25_cuentas.sql`:
    saldo derivado, FZ001 (saldo negativo salvo tarjeta), FZ002 (archivada = congelada), FZ003 (tope de 20),
    nombre único sin distinguir mayúsculas ni espacios (23505) y propiedad de la cuenta (23503)."""

    TOPE = 20
    _cuentas: Dict[str, dict] = {}
    _lock = threading.RLock()

    @staticmethod
    def _clave(nombre: str) -> str:
        return str(nombre).strip().lower()

    @staticmethod
    def saldo(cuenta: dict) -> Decimal:
        total = _dec(cuenta["saldo_inicial"])
        for t in DemoTransaccionDB._transacciones.values():
            if t.get("cuenta_id") == cuenta["id"] and t["usuario_id"] == cuenta["usuario_id"]:
                total += _efecto(t["tipo"], t["monto"])
        for tr in DemoTransferenciaDB._transferencias.values():   # CHG-024: recibidas suman, enviadas restan (INV-047)
            if tr["usuario_id"] == cuenta["usuario_id"]:
                if tr["cuenta_destino_id"] == cuenta["id"]:
                    total += _dec(tr["monto"])
                if tr["cuenta_origen_id"] == cuenta["id"]:
                    total -= _dec(tr["monto"])
        return total

    @staticmethod
    def _publica(cuenta: dict) -> dict:
        return {
            "id": cuenta["id"], "usuario_id": cuenta["usuario_id"], "nombre": cuenta["nombre"], "tipo": cuenta["tipo"],
            "saldo_inicial": float(cuenta["saldo_inicial"]), "saldo": float(DemoCuentaDB.saldo(cuenta)),
            "archivada": cuenta["archivada"], "created_at": cuenta["created_at"],
        }

    @staticmethod
    def validar_transaccion(usuario_id: str, vieja: Optional[dict], nueva: Optional[dict]) -> None:
        """Equivale a `fz001_saldo_transacciones` (INSERT: vieja=None; DELETE: nueva=None) más la llave foránea compuesta."""
        with DemoCuentaDB._lock:
            if vieja and nueva and _dec(nueva["monto"]) == _dec(vieja["monto"]) and nueva["tipo"] == vieja["tipo"] \
                    and nueva.get("cuenta_id") == vieja.get("cuenta_id"):
                return   # sin cambio real de monto, tipo ni cuenta
            ids = sorted({f["cuenta_id"] for f in (vieja, nueva) if f and f.get("cuenta_id")})
            if not ids:
                return
            propias = []
            for cid in ids:
                c = DemoCuentaDB._cuentas.get(cid)
                if c and c["usuario_id"] == usuario_id:
                    propias.append(c)
            for c in propias:
                if c["archivada"]:
                    raise ErrorBD("FZ002")
            for c in propias:
                if c["tipo"] == "tarjeta_credito":
                    continue
                delta = Decimal(0)
                if nueva and nueva.get("cuenta_id") == c["id"]:
                    delta += _efecto(nueva["tipo"], nueva["monto"])
                if vieja and vieja.get("cuenta_id") == c["id"]:
                    delta -= _efecto(vieja["tipo"], vieja["monto"])
                if delta < 0 and DemoCuentaDB.saldo(c) + delta < 0:
                    raise ErrorBD("FZ001")
            # Llave foránea compuesta (cuenta_id, usuario_id): una cuenta ajena o inexistente no se puede usar
            if nueva and nueva.get("cuenta_id"):
                c = DemoCuentaDB._cuentas.get(nueva["cuenta_id"])
                if not c or c["usuario_id"] != usuario_id:
                    raise ErrorBD("23503")

    @staticmethod
    async def crear(usuario_id: str, nombre: str, tipo: str, saldo_inicial: Decimal) -> dict:
        with DemoCuentaDB._lock:
            propias = [c for c in DemoCuentaDB._cuentas.values() if c["usuario_id"] == usuario_id]
            if len(propias) >= DemoCuentaDB.TOPE:
                raise ErrorBD("FZ003")
            if any(DemoCuentaDB._clave(c["nombre"]) == DemoCuentaDB._clave(nombre) for c in propias):
                raise ErrorBD("23505")
            if saldo_inicial < 0 and tipo != "tarjeta_credito":
                raise ErrorBD("23514")
            cuenta = {
                "id": str(uuid.uuid4()), "usuario_id": usuario_id, "nombre": nombre, "tipo": tipo,
                "saldo_inicial": _dec(saldo_inicial), "archivada": False,
                "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            DemoCuentaDB._cuentas[cuenta["id"]] = cuenta
            return DemoCuentaDB._publica(cuenta)

    @staticmethod
    def _de(cuenta_id: str, usuario_id: str) -> Optional[dict]:
        c = DemoCuentaDB._cuentas.get(cuenta_id)
        return c if c and c["usuario_id"] == usuario_id else None

    @staticmethod
    async def obtener_por_id(cuenta_id: str, usuario_id: str) -> Optional[dict]:
        with DemoCuentaDB._lock:
            c = DemoCuentaDB._de(cuenta_id, usuario_id)
            return dict(c, saldo_inicial=float(c["saldo_inicial"])) if c else None

    @staticmethod
    async def listar(usuario_id: str) -> list:
        with DemoCuentaDB._lock:
            propias = [c for c in DemoCuentaDB._cuentas.values() if c["usuario_id"] == usuario_id]
            propias.sort(key=lambda c: (c["nombre"].lower(), c["id"]))
            return [DemoCuentaDB._publica(c) for c in propias]

    @staticmethod
    async def actualizar(cuenta_id: str, usuario_id: str, cambios: dict) -> Optional[dict]:
        with DemoCuentaDB._lock:
            c = DemoCuentaDB._de(cuenta_id, usuario_id)
            if c is None:
                return None
            if "nombre" in cambios and any(
                    o["id"] != c["id"] and o["usuario_id"] == usuario_id
                    and DemoCuentaDB._clave(o["nombre"]) == DemoCuentaDB._clave(cambios["nombre"])
                    for o in DemoCuentaDB._cuentas.values()):
                raise ErrorBD("23505")
            if "saldo_inicial" in cambios:
                nuevo = _dec(cambios["saldo_inicial"])
                if nuevo < 0 and c["tipo"] != "tarjeta_credito":
                    raise ErrorBD("23514")
                if nuevo < c["saldo_inicial"] and c["tipo"] != "tarjeta_credito" \
                        and DemoCuentaDB.saldo(c) + (nuevo - c["saldo_inicial"]) < 0:
                    raise ErrorBD("FZ001")
            for k, v in cambios.items():
                c[k] = _dec(v) if k == "saldo_inicial" else v
            return DemoCuentaDB._publica(c)

    @staticmethod
    async def eliminar(cuenta_id: str, usuario_id: str) -> bool:
        with DemoCuentaDB._lock:
            c = DemoCuentaDB._de(cuenta_id, usuario_id)
            if c is None:
                return False
            if any(t.get("cuenta_id") == cuenta_id for t in DemoTransaccionDB._transacciones.values()):
                raise ErrorBD("23503")   # NO ACTION: con movimientos no se elimina (INV-050)
            if any(cuenta_id in (t["cuenta_origen_id"], t["cuenta_destino_id"])
                   for t in DemoTransferenciaDB._transferencias.values()):
                raise ErrorBD("23503")   # ni con transferencias (CHG-024)
            del DemoCuentaDB._cuentas[cuenta_id]
            return True


class DemoTransferenciaDB:
    """Transferencias en memoria (CHG-024). Mismas reglas que el disparador `fz001_saldo_transferencias` y los CHECK/llaves
    compuestas de la tabla: cuentas propias (23503), distintas y monto > 0 (23514), ninguna archivada (FZ002) y el origen
    (si no es tarjeta de crédito) no puede quedar en negativo (FZ001). Al borrar, el destino no puede quedar en negativo."""

    _transferencias: Dict[str, dict] = {}

    @staticmethod
    def _publica(t: dict) -> dict:
        return {
            "id": t["id"], "usuario_id": t["usuario_id"], "cuenta_origen_id": t["cuenta_origen_id"],
            "cuenta_destino_id": t["cuenta_destino_id"], "monto": float(t["monto"]), "fecha": t["fecha"],
            "descripcion": t["descripcion"], "created_at": t["created_at"],
        }

    @staticmethod
    async def crear(usuario_id: str, origen_id: str, destino_id: str, monto: Decimal, fecha: str,
                    descripcion: Optional[str]) -> dict:
        with DemoCuentaDB._lock:
            origen, destino = DemoCuentaDB._de(origen_id, usuario_id), DemoCuentaDB._de(destino_id, usuario_id)
            if origen is None or destino is None:
                raise ErrorBD("23503")
            if origen_id == destino_id or _dec(monto) <= 0:
                raise ErrorBD("23514")
            if origen["archivada"] or destino["archivada"]:
                raise ErrorBD("FZ002")
            if origen["tipo"] != "tarjeta_credito" and DemoCuentaDB.saldo(origen) - _dec(monto) < 0:
                raise ErrorBD("FZ001")
            t = {"id": str(uuid.uuid4()), "usuario_id": usuario_id, "cuenta_origen_id": origen_id,
                 "cuenta_destino_id": destino_id, "monto": _dec(monto), "fecha": fecha, "descripcion": descripcion,
                 "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
            DemoTransferenciaDB._transferencias[t["id"]] = t
            return DemoTransferenciaDB._publica(t)

    @staticmethod
    async def listar(usuario_id: str, mes: Optional[str] = None) -> list:
        """Las del usuario, más recientes primero: fecha desc, id desc."""
        with DemoCuentaDB._lock:
            filas = [t for t in DemoTransferenciaDB._transferencias.values()
                     if t["usuario_id"] == usuario_id and (not mes or t["fecha"].startswith(mes))]
            filas.sort(key=lambda t: (t["fecha"], t["id"]), reverse=True)
            return [DemoTransferenciaDB._publica(t) for t in filas]

    @staticmethod
    async def obtener_por_id(transferencia_id: str, usuario_id: str) -> Optional[dict]:
        with DemoCuentaDB._lock:
            t = DemoTransferenciaDB._transferencias.get(transferencia_id)
            return DemoTransferenciaDB._publica(t) if t and t["usuario_id"] == usuario_id else None

    @staticmethod
    async def eliminar(transferencia_id: str, usuario_id: str) -> bool:
        with DemoCuentaDB._lock:
            t = DemoTransferenciaDB._transferencias.get(transferencia_id)
            if t is None or t["usuario_id"] != usuario_id:
                return False
            origen, destino = DemoCuentaDB._cuentas.get(t["cuenta_origen_id"]), DemoCuentaDB._cuentas.get(t["cuenta_destino_id"])
            if (origen and origen["archivada"]) or (destino and destino["archivada"]):
                raise ErrorBD("FZ002")
            if destino and destino["tipo"] != "tarjeta_credito" and DemoCuentaDB.saldo(destino) - _dec(t["monto"]) < 0:
                raise ErrorBD("FZ001")
            del DemoTransferenciaDB._transferencias[transferencia_id]
            return True


class DemoCategoriaDB:
    """In-memory categorias database"""

    # Igual que en Supabase: cada usuario recibe su propia copia de las
    # categorías por defecto la primera vez que las pide.
    _DEFAULTS = [
        {"nombre": "Salario", "icono": "💼", "tipo": "ingreso"},
        {"nombre": "Freelance", "icono": "💻", "tipo": "ingreso"},
        {"nombre": "Comida", "icono": "🍔", "tipo": "gasto"},
        {"nombre": "Transporte", "icono": "🚗", "tipo": "gasto"},
        {"nombre": "Hogar", "icono": "🏠", "tipo": "gasto"},
        {"nombre": "Salud", "icono": "💊", "tipo": "gasto"},
        {"nombre": "Entretenimiento", "icono": "🎮", "tipo": "gasto"},
    ]
    _categorias: Dict[str, dict] = {}

    @staticmethod
    async def crear(usuario_id: str, nombre: str, icono: str, tipo: str) -> dict:
        """Create category"""
        cat_id = str(uuid.uuid4())
        categoria = {
            "id": cat_id,
            "usuario_id": usuario_id,
            "nombre": nombre,
            "icono": icono,
            "tipo": tipo
        }
        DemoCategoriaDB._categorias[cat_id] = categoria
        return categoria
    
    @staticmethod
    async def obtener_por_usuario(usuario_id: str) -> list:
        """Get user categories (seeding the defaults on first access)"""
        cats = [c for c in DemoCategoriaDB._categorias.values() if c["usuario_id"] == usuario_id]
        if not cats:
            for d in DemoCategoriaDB._DEFAULTS:
                cats.append(await DemoCategoriaDB.crear(usuario_id, d["nombre"], d["icono"], d["tipo"]))
        return cats
    
    @staticmethod
    async def obtener_por_id(categoria_id: str) -> dict:
        """Get category by ID"""
        return DemoCategoriaDB._categorias.get(categoria_id)

    @staticmethod
    async def actualizar(categoria_id: str, nombre: str, icono: str, tipo: str) -> dict:
        """Update category"""
        if categoria_id in DemoCategoriaDB._categorias:
            DemoCategoriaDB._categorias[categoria_id].update({"nombre": nombre, "icono": icono, "tipo": tipo})
            return DemoCategoriaDB._categorias[categoria_id]
        return None

    @staticmethod
    async def eliminar(categoria_id: str) -> bool:
        """Delete category"""
        if categoria_id in DemoCategoriaDB._categorias:
            del DemoCategoriaDB._categorias[categoria_id]
            return True
        return False


class DemoPresupuestoDB:
    """In-memory presupuestos database"""
    
    _presupuestos: Dict[str, dict] = {}
    
    @staticmethod
    async def crear(usuario_id: str, categoria_id: str, limite_mensual: float, mes_ano: str) -> dict:
        """Create budget (UNIQUE usuario + categoría + mes, como en la BD real: INV-028)"""
        if any(p["usuario_id"] == usuario_id and p["categoria_id"] == categoria_id and p["mes_ano"] == mes_ano
               for p in DemoPresupuestoDB._presupuestos.values()):
            raise ValueError("duplicate key value violates unique constraint (23505)")
        pres_id = str(uuid.uuid4())
        presupuesto = {
            "id": pres_id,
            "usuario_id": usuario_id,
            "categoria_id": categoria_id,
            "limite_mensual": limite_mensual,
            "mes_ano": mes_ano
        }
        DemoPresupuestoDB._presupuestos[pres_id] = presupuesto
        return presupuesto
    
    @staticmethod
    async def obtener_por_usuario_mes(usuario_id: str, mes_ano: str) -> list:
        """Get user budgets for month"""
        return [p for p in DemoPresupuestoDB._presupuestos.values()
                if p["usuario_id"] == usuario_id and p["mes_ano"] == mes_ano]

    @staticmethod
    async def obtener_por_id(presupuesto_id: str):
        """Get budget by id"""
        return DemoPresupuestoDB._presupuestos.get(presupuesto_id)

    @staticmethod
    async def actualizar(presupuesto_id: str, limite_mensual: float) -> dict:
        """Update budget limit"""
        if presupuesto_id in DemoPresupuestoDB._presupuestos:
            DemoPresupuestoDB._presupuestos[presupuesto_id]["limite_mensual"] = limite_mensual
            return DemoPresupuestoDB._presupuestos[presupuesto_id]
        return None

    @staticmethod
    async def eliminar(presupuesto_id: str) -> bool:
        """Delete budget"""
        if presupuesto_id in DemoPresupuestoDB._presupuestos:
            del DemoPresupuestoDB._presupuestos[presupuesto_id]
            return True
        return False


class DemoMetaDB:
    """In-memory metas database"""
    
    _metas: Dict[str, dict] = {}
    
    @staticmethod
    async def crear(usuario_id: str, nombre: str, monto_objetivo: float, fecha_objetivo: str) -> dict:
        """Create goal"""
        meta_id = str(uuid.uuid4())
        meta = {
            "id": meta_id,
            "usuario_id": usuario_id,
            "nombre": nombre,
            "monto_objetivo": monto_objetivo,
            "monto_actual": 0,
            "fecha_objetivo": fecha_objetivo
        }
        DemoMetaDB._metas[meta_id] = meta
        return meta
    
    @staticmethod
    async def obtener_por_usuario(usuario_id: str) -> list:
        """Get user goals"""
        return [m for m in DemoMetaDB._metas.values() if m["usuario_id"] == usuario_id]

    @staticmethod
    async def obtener_por_id(meta_id: str) -> dict:
        """Get goal by ID"""
        return DemoMetaDB._metas.get(meta_id)
    
    @staticmethod
    async def actualizar_progreso(meta_id: str, updates: dict) -> dict:
        """Update goal fields"""
        if meta_id in DemoMetaDB._metas:
            for k, v in updates.items():
                if v is not None:
                    DemoMetaDB._metas[meta_id][k] = v
            return DemoMetaDB._metas[meta_id]
        return None

    @staticmethod
    async def eliminar(meta_id: str) -> bool:
        """Delete goal"""
        if meta_id in DemoMetaDB._metas:
            del DemoMetaDB._metas[meta_id]
            return True
        return False

    @staticmethod
    async def abonar_con_cuenta(meta_id: str, usuario_id: str, monto: float, fecha: str, descripcion: str,
                                cuenta_id: str) -> Optional[dict]:
        """Equivale a `abonar_meta(..., p_cuenta_id)` (CHG-025, INV-052): las reglas de las cuentas de dinero (FZ001, FZ002,
        23503) se evalúan ANTES de escribir nada, así que si fallan no cambian ni la meta, ni la categoría «Ahorro»
        ni el saldo. None si la meta no existe o es de otro usuario."""
        await DemoCategoriaDB.obtener_por_usuario(usuario_id)   # siembra las categorías por defecto como el flujo normal
        with DemoCuentaDB._lock:
            meta = DemoMetaDB._metas.get(meta_id)
            if not meta or meta["usuario_id"] != usuario_id:
                return None
            DemoCuentaDB.validar_transaccion(usuario_id, None, {"cuenta_id": cuenta_id, "tipo": "gasto", "monto": monto})
            ahorro = next((c for c in DemoCategoriaDB._categorias.values()
                           if c["usuario_id"] == usuario_id and c["nombre"] == "Ahorro"), None)
            if ahorro is None:
                ahorro = {"id": str(uuid.uuid4()), "usuario_id": usuario_id, "nombre": "Ahorro", "icono": "🐷", "tipo": "gasto"}
                DemoCategoriaDB._categorias[ahorro["id"]] = ahorro
            trans_id = str(uuid.uuid4())
            DemoTransaccionDB._transacciones[trans_id] = {
                "id": trans_id, "usuario_id": usuario_id, "categoria_id": ahorro["id"], "monto": monto,
                "descripcion": descripcion or "Abono a meta de ahorro", "fecha": fecha, "tipo": "gasto",
                "medio_pago": None, "cuenta_id": cuenta_id,
            }
            meta["monto_actual"] = float(meta.get("monto_actual") or 0) + monto
            return meta


class DemoRecurrenteDB:
    """Transacciones recurrentes en memoria (CHG-012)"""

    _recurrentes: Dict[str, dict] = {}

    @staticmethod
    async def crear(usuario_id: str, datos: dict) -> dict:
        rec_id = str(uuid.uuid4())
        recurrente = {"id": rec_id, "usuario_id": usuario_id, **datos}
        DemoRecurrenteDB._recurrentes[rec_id] = recurrente
        return dict(recurrente)

    @staticmethod
    async def obtener_por_usuario(usuario_id: str) -> list:
        return sorted(
            (dict(r) for r in DemoRecurrenteDB._recurrentes.values() if r["usuario_id"] == usuario_id),
            key=lambda r: r["proxima_fecha"],
        )

    @staticmethod
    async def obtener_por_id(recurrente_id: str) -> Optional[dict]:
        r = DemoRecurrenteDB._recurrentes.get(recurrente_id)
        return dict(r) if r else None

    @staticmethod
    async def actualizar(recurrente_id: str, datos: dict) -> Optional[dict]:
        r = DemoRecurrenteDB._recurrentes.get(recurrente_id)
        if not r:
            return None
        r.update(datos)
        return dict(r)

    @staticmethod
    async def avanzar(recurrente_id: str, esperada: str, nueva: str) -> Optional[dict]:
        """Cambia la próxima fecha solo si sigue siendo `esperada` (compare-and-set)."""
        r = DemoRecurrenteDB._recurrentes.get(recurrente_id)
        if not r or r["proxima_fecha"] != esperada:
            return None
        r["proxima_fecha"] = nueva
        return dict(r)

    @staticmethod
    async def eliminar(recurrente_id: str) -> bool:
        return DemoRecurrenteDB._recurrentes.pop(recurrente_id, None) is not None

    @staticmethod
    async def confirmar(usuario_id: str, recurrente_id: str, ocurrencia: str, siguiente: str, monto: Optional[float],
                        fecha: Optional[str], cuenta_id: Optional[str], cuenta_indicada: bool) -> Optional[dict]:
        """Equivale a la función SQL `confirmar_recurrente` (CHG-025, INV-052, ADR-009 punto 13): todo o nada y bajo el mismo
        bloqueo que las demás reglas de cuentas. Comprueba que esté activa y que la fecha sea la que vio la persona
        (`ErrorBD("OCURRENCIA_CAMBIADA")`), evalúa las reglas de las cuentas de dinero ANTES de escribir (FZ001, FZ002, 23503)
        y solo entonces crea la transacción y avanza la fecha. None si la recurrente no existe o es de otro usuario."""
        with DemoCuentaDB._lock:
            r = DemoRecurrenteDB._recurrentes.get(recurrente_id)
            if not r or r["usuario_id"] != usuario_id:
                return None
            if not r.get("activa") or r["proxima_fecha"] != ocurrencia:
                raise ErrorBD("OCURRENCIA_CAMBIADA")
            cuenta = cuenta_id if cuenta_indicada else r.get("cuenta_id")
            valor = monto if monto is not None else r["monto"]
            DemoCuentaDB.validar_transaccion(usuario_id, None, {"cuenta_id": cuenta, "tipo": r["tipo"], "monto": valor})
            trans_id = str(uuid.uuid4())
            transaccion = {
                "id": trans_id, "usuario_id": usuario_id, "categoria_id": r.get("categoria_id") or None, "monto": valor,
                "descripcion": r.get("descripcion") or "", "fecha": fecha or ocurrencia, "tipo": r["tipo"],
                "medio_pago": r.get("medio_pago"), "cuenta_id": cuenta,
            }
            DemoTransaccionDB._transacciones[trans_id] = transaccion
            r["proxima_fecha"] = siguiente
            return dict(transaccion)
