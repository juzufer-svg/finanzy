"""
In-memory demo database for testing without Supabase
Use this when real Supabase credentials are not available
"""
from typing import Optional, Dict, List
import uuid


class DemoTransaccionDB:
    """In-memory transacciones database"""
    
    _transacciones: Dict[str, dict] = {}
    
    @staticmethod
    async def crear(usuario_id: str, categoria_id: str, monto: float,
                    descripcion: str, fecha: str, tipo: str, medio_pago: Optional[str] = None) -> dict:
        """Create transaction"""
        trans_id = str(uuid.uuid4())
        transaccion = {
            "id": trans_id,
            "usuario_id": usuario_id,
            "categoria_id": categoria_id,
            "monto": monto,
            "descripcion": descripcion,
            "fecha": fecha,
            "tipo": tipo,
            "medio_pago": medio_pago,
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
    async def obtener_resumen(usuario_id: str, mes: str) -> dict:
        """Get transactions summary"""
        transacciones = await DemoTransaccionDB.obtener_por_usuario(usuario_id, mes)
        
        ingresos = sum(t["monto"] for t in transacciones if t["tipo"] == "ingreso")
        gastos = sum(t["monto"] for t in transacciones if t["tipo"] == "gasto")
        
        return {
            "ingresos": ingresos,
            "gastos": gastos,
            "balance": ingresos - gastos,
            "total_transacciones": len(transacciones)
        }
    
    @staticmethod
    async def obtener_por_id(transaccion_id: str):
        """Get transaction by ID"""
        return DemoTransaccionDB._transacciones.get(transaccion_id)

    @staticmethod
    async def actualizar(transaccion_id: str, **kwargs) -> dict:
        """Update transaction"""
        if transaccion_id in DemoTransaccionDB._transacciones:
            allowed = {'categoria_id', 'monto', 'descripcion', 'fecha', 'tipo', 'medio_pago'}
            for k, v in kwargs.items():
                if k in allowed:
                    DemoTransaccionDB._transacciones[transaccion_id][k] = v
            return DemoTransaccionDB._transacciones[transaccion_id]
        return None

    @staticmethod
    async def eliminar(transaccion_id: str) -> bool:
        """Delete transaction"""
        if transaccion_id in DemoTransaccionDB._transacciones:
            del DemoTransaccionDB._transacciones[transaccion_id]
            return True
        return False


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
        """Create budget"""
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
