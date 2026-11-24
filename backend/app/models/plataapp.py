"""
Database models for Finanzy - Supabase with Demo DB fallback
"""
from typing import Optional
import uuid
from datetime import date as date_type
from app.core.supabase import SupabaseDB
from app.core.config import settings
from app.models import whatsapp as whatsapp_db
from app.models.demo_db import (
    DemoTransaccionDB,
    DemoCategoriaDB,
    DemoPresupuestoDB,
    DemoMetaDB,
    DemoRecurrenteDB,
)

def _supabase_ok() -> bool:
    return bool(settings.SUPABASE_URL and settings.SUPABASE_KEY)


def _de_usuario(registro: Optional[dict], usuario_id: str) -> Optional[dict]:
    """Devuelve el registro solo si pertenece al usuario (modo demo)."""
    if registro and str(registro.get("usuario_id")) == str(usuario_id):
        return registro
    return None


def _mes_rango(mes: str):
    """Devuelve (first_day, next_month_first_day) para filtrar por mes en Supabase."""
    year, month = int(mes[:4]), int(mes[5:7])
    first = date_type(year, month, 1).isoformat()
    if month == 12:
        nxt = date_type(year + 1, 1, 1).isoformat()
    else:
        nxt = date_type(year, month + 1, 1).isoformat()
    return first, nxt


class TransaccionDB:

    @staticmethod
    async def crear(usuario_id: str, categoria_id: str, monto: float,
                    descripcion: str, fecha: str, tipo: str, medio_pago: Optional[str] = None) -> dict:
        if not _supabase_ok():
            return await DemoTransaccionDB.crear(usuario_id, categoria_id, monto, descripcion, fecha, tipo, medio_pago)
        try:
            client = SupabaseDB.get_client()
            row = {
                "id": str(uuid.uuid4()),
                "usuario_id": usuario_id,
                "categoria_id": categoria_id if categoria_id else None,
                "monto": monto,
                "descripcion": descripcion,
                "fecha": fecha,
                "tipo": tipo,
            }
            if medio_pago is not None:  # columna de CHG-007; sin dato se deja NULL
                row["medio_pago"] = medio_pago
            result = client.table("transacciones").insert(row).execute()
            return result.data[0]
        except Exception as e:
            print(f"[Supabase] transacciones.crear error: {e}")
            raise

    @staticmethod
    async def obtener_por_usuario(usuario_id: str, mes: Optional[str] = None) -> list:
        if not _supabase_ok():
            return await DemoTransaccionDB.obtener_por_usuario(usuario_id, mes)
        try:
            client = SupabaseDB.get_client()
            q = client.table("transacciones").select("*").eq("usuario_id", usuario_id).order("fecha", desc=True)
            if mes:
                first, nxt = _mes_rango(mes)
                q = q.gte("fecha", first).lt("fecha", nxt)
            result = q.execute()
            return result.data
        except Exception as e:
            print(f"[Supabase] transacciones.obtener error: {e}")
            raise

    # ---- Lectura para exportar (CHG-018, INV-042/INV-044): síncrona, para correr en un hilo ----

    @staticmethod
    def nombres_de_categorias_propias(usuario_id: str) -> dict:
        """{id: nombre} de las categorías DEL USUARIO (nunca siembra ni lee las de otros: INV-042)."""
        if not _supabase_ok():
            return {c["id"]: c.get("nombre", "") for c in DemoCategoriaDB._categorias.values()
                    if str(c.get("usuario_id")) == str(usuario_id)}
        try:
            client = SupabaseDB.get_client()
            nombres, desde = {}, 0
            while True:
                filas = (client.table("categorias").select("id,nombre").eq("usuario_id", usuario_id)
                         .order("id").range(desde, desde + 999).execute().data)
                nombres.update({str(f["id"]): f.get("nombre", "") for f in filas})
                if len(filas) < 1000:
                    return nombres
                desde += 1000
        except Exception as e:
            print(f"[Supabase] categorias.exportar error: {type(e).__name__}")
            raise

    @staticmethod
    def pagina_para_exportar(usuario_id: str, desde_mes: str, hasta_mes: str, inicio: int, cantidad: int) -> list:
        """Una página de transacciones DEL USUARIO entre dos meses (YYYY-MM, ambos incluidos), ordenadas por fecha,
        creación e id. Cada fila: fecha, tipo, categoria_id, descripcion, medio_pago, monto, whatsapp (bool).
        PostgREST corta en 1000 filas: quien llama pagina con `inicio` y `cantidad` ≤ 1000 (INV-044)."""
        primero, _ = _mes_rango(desde_mes)
        _, siguiente = _mes_rango(hasta_mes)
        if not _supabase_ok():
            ids_whatsapp = {r["transaccion_id"] for r in whatsapp_db._Memoria.registros
                            if str(r["usuario_id"]) == str(usuario_id)}
            propias = [t for t in DemoTransaccionDB._transacciones.values()
                       if str(t["usuario_id"]) == str(usuario_id) and primero <= str(t["fecha"])[:10] < siguiente]
            propias.sort(key=lambda t: str(t["fecha"])[:10])  # estable: respeta el orden de creación
            return [{
                "fecha": t["fecha"], "tipo": t["tipo"], "categoria_id": t.get("categoria_id"),
                "descripcion": t.get("descripcion"), "medio_pago": t.get("medio_pago"), "monto": t["monto"],
                "whatsapp": t["id"] in ids_whatsapp,
            } for t in propias[inicio:inicio + cantidad]]
        try:
            client = SupabaseDB.get_client()
            filas = (client.table("transacciones")
                     .select("fecha,tipo,categoria_id,descripcion,medio_pago,monto,whatsapp_registros(transaccion_id)")
                     .eq("usuario_id", usuario_id).gte("fecha", primero).lt("fecha", siguiente)
                     .order("fecha").order("created_at").order("id")
                     .range(inicio, inicio + cantidad - 1).execute().data)
            return [{
                "fecha": f["fecha"], "tipo": f["tipo"], "categoria_id": f.get("categoria_id"),
                "descripcion": f.get("descripcion"), "medio_pago": f.get("medio_pago"), "monto": f["monto"],
                # WhatsApp = existe fila en whatsapp_registros (objeto o lista según la relación; vacío = App)
                "whatsapp": bool(f.get("whatsapp_registros")),
            } for f in filas]
        except Exception as e:
            print(f"[Supabase] transacciones.exportar error: {type(e).__name__}")
            raise

    @staticmethod
    async def obtener_por_id(transaccion_id: str, usuario_id: str) -> Optional[dict]:
        if not _supabase_ok():
            return _de_usuario(await DemoTransaccionDB.obtener_por_id(transaccion_id), usuario_id)
        try:
            client = SupabaseDB.get_client()
            result = client.table("transacciones").select("*").eq("id", transaccion_id).eq("usuario_id", usuario_id).limit(1).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"[Supabase] transacciones.obtener_por_id error: {e}")
            raise

    @staticmethod
    async def actualizar(transaccion_id: str, usuario_id: str, **kwargs) -> Optional[dict]:
        if not _supabase_ok():
            if not _de_usuario(await DemoTransaccionDB.obtener_por_id(transaccion_id), usuario_id):
                return None
            return await DemoTransaccionDB.actualizar(transaccion_id, **kwargs)
        try:
            allowed = {'categoria_id', 'monto', 'descripcion', 'fecha', 'tipo'}
            updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
            if "medio_pago" in kwargs:  # None aquí significa "quitar el medio de pago"
                updates["medio_pago"] = kwargs["medio_pago"]
            if updates.get("categoria_id") == "":  # igual que en crear: "" = sin categoría (columna uuid)
                updates["categoria_id"] = None
            client = SupabaseDB.get_client()
            result = client.table("transacciones").update(updates).eq("id", transaccion_id).eq("usuario_id", usuario_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"[Supabase] transacciones.actualizar error: {e}")
            raise

    @staticmethod
    async def eliminar(transaccion_id: str, usuario_id: str) -> bool:
        if not _supabase_ok():
            if not _de_usuario(await DemoTransaccionDB.obtener_por_id(transaccion_id), usuario_id):
                return False
            return await DemoTransaccionDB.eliminar(transaccion_id)
        try:
            client = SupabaseDB.get_client()
            client.table("transacciones").delete().eq("id", transaccion_id).eq("usuario_id", usuario_id).execute()
            return True
        except Exception as e:
            print(f"[Supabase] transacciones.eliminar error: {e}")
            raise

    @staticmethod
    async def obtener_resumen(usuario_id: str, mes: str) -> dict:
        transacciones = await TransaccionDB.obtener_por_usuario(usuario_id, mes)
        ingresos = sum(float(t["monto"]) for t in transacciones if t["tipo"] == "ingreso")
        gastos = sum(float(t["monto"]) for t in transacciones if t["tipo"] == "gasto")
        return {
            "ingresos": ingresos,
            "gastos": gastos,
            "balance": ingresos - gastos,
            "total_transacciones": len(transacciones),
        }


class CategoriaDB:

    _DEFAULT_SEED = [
        {"nombre": "Salario",        "icono": "💼", "tipo": "ingreso"},
        {"nombre": "Freelance",      "icono": "💻", "tipo": "ingreso"},
        {"nombre": "Comida",         "icono": "🍔", "tipo": "gasto"},
        {"nombre": "Transporte",     "icono": "🚗", "tipo": "gasto"},
        {"nombre": "Hogar",          "icono": "🏠", "tipo": "gasto"},
        {"nombre": "Salud",          "icono": "💊", "tipo": "gasto"},
        {"nombre": "Entretenimiento","icono": "🎮", "tipo": "gasto"},
    ]

    @staticmethod
    async def crear(usuario_id: str, nombre: str, icono: str, tipo: str) -> dict:
        if not _supabase_ok():
            return await DemoCategoriaDB.crear(usuario_id, nombre, icono, tipo)
        try:
            client = SupabaseDB.get_client()
            row = {"id": str(uuid.uuid4()), "usuario_id": usuario_id, "nombre": nombre, "icono": icono, "tipo": tipo}
            result = client.table("categorias").insert(row).execute()
            return result.data[0]
        except Exception as e:
            print(f"[Supabase] categorias.crear error: {e}")
            raise

    @staticmethod
    async def obtener_por_usuario(usuario_id: str) -> list:
        if not _supabase_ok():
            return await DemoCategoriaDB.obtener_por_usuario(usuario_id)
        try:
            client = SupabaseDB.get_client()
            result = client.table("categorias").select("*").eq("usuario_id", usuario_id).execute()
            cats = result.data
            # Seed default categories for new user if none exist
            if not cats:
                seed = [{"id": str(uuid.uuid4()), "usuario_id": usuario_id, **c} for c in CategoriaDB._DEFAULT_SEED]
                cats = []
                for item in seed:
                    try:
                        seeded = client.table("categorias").insert(item).execute()
                        if seeded.data:
                            cats.extend(seeded.data)
                    except Exception as seed_err:
                        print(f"[Supabase] categorias.seed error: {seed_err}")
                # Si otra petición sembró al mismo tiempo, la restricción UNIQUE rechazó estas filas
                # (INV-028): se relee lo que quedó guardado para no devolver categorías que no existen.
                cats = client.table("categorias").select("*").eq("usuario_id", usuario_id).execute().data
            return cats
        except Exception as e:
            print(f"[Supabase] categorias.obtener error: {e}")
            raise

    @staticmethod
    async def obtener_por_id(categoria_id: str, usuario_id: str) -> Optional[dict]:
        if not _supabase_ok():
            return _de_usuario(await DemoCategoriaDB.obtener_por_id(categoria_id), usuario_id)
        try:
            client = SupabaseDB.get_client()
            result = client.table("categorias").select("*").eq("id", categoria_id).eq("usuario_id", usuario_id).limit(1).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"[Supabase] categorias.obtener_por_id error: {e}")
            raise

    @staticmethod
    async def actualizar(categoria_id: str, usuario_id: str, nombre: str, icono: str, tipo: str) -> Optional[dict]:
        if not _supabase_ok():
            if not _de_usuario(await DemoCategoriaDB.obtener_por_id(categoria_id), usuario_id):
                return None
            return await DemoCategoriaDB.actualizar(categoria_id, nombre, icono, tipo)
        try:
            client = SupabaseDB.get_client()
            result = client.table("categorias").update({"nombre": nombre, "icono": icono, "tipo": tipo}).eq("id", categoria_id).eq("usuario_id", usuario_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"[Supabase] categorias.actualizar error: {e}")
            raise

    @staticmethod
    async def eliminar(categoria_id: str, usuario_id: str) -> bool:
        if not _supabase_ok():
            if not _de_usuario(await DemoCategoriaDB.obtener_por_id(categoria_id), usuario_id):
                return False
            return await DemoCategoriaDB.eliminar(categoria_id)
        try:
            client = SupabaseDB.get_client()
            client.table("categorias").delete().eq("id", categoria_id).eq("usuario_id", usuario_id).execute()
            return True
        except Exception as e:
            print(f"[Supabase] categorias.eliminar error: {e}")
            raise


class PresupuestoDB:

    @staticmethod
    async def crear(usuario_id: str, categoria_id: str, limite_mensual: float, mes_ano: str) -> dict:
        if not _supabase_ok():
            return await DemoPresupuestoDB.crear(usuario_id, categoria_id, limite_mensual, mes_ano)
        try:
            client = SupabaseDB.get_client()
            row = {
                "id": str(uuid.uuid4()),
                "usuario_id": usuario_id,
                "categoria_id": categoria_id,
                "limite_mensual": limite_mensual,
                "mes_ano": mes_ano,
            }
            result = client.table("presupuestos").insert(row).execute()
            return result.data[0]
        except Exception as e:
            print(f"[Supabase] presupuestos.crear error: {e}")
            raise

    @staticmethod
    async def obtener_por_usuario_mes(usuario_id: str, mes_ano: str) -> list:
        if not _supabase_ok():
            return await DemoPresupuestoDB.obtener_por_usuario_mes(usuario_id, mes_ano)
        try:
            client = SupabaseDB.get_client()
            result = client.table("presupuestos").select("*")\
                .eq("usuario_id", usuario_id).eq("mes_ano", mes_ano).execute()
            return result.data
        except Exception as e:
            print(f"[Supabase] presupuestos.obtener error: {e}")
            raise

    @staticmethod
    async def obtener_por_id(presupuesto_id: str, usuario_id: str) -> Optional[dict]:
        if not _supabase_ok():
            return _de_usuario(await DemoPresupuestoDB.obtener_por_id(presupuesto_id), usuario_id)
        try:
            client = SupabaseDB.get_client()
            result = client.table("presupuestos").select("*").eq("id", presupuesto_id).eq("usuario_id", usuario_id).limit(1).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"[Supabase] presupuestos.obtener_por_id error: {e}")
            raise

    @staticmethod
    async def actualizar(presupuesto_id: str, usuario_id: str, limite_mensual: float) -> Optional[dict]:
        if not _supabase_ok():
            if not _de_usuario(await DemoPresupuestoDB.obtener_por_id(presupuesto_id), usuario_id):
                return None
            return await DemoPresupuestoDB.actualizar(presupuesto_id, limite_mensual)
        try:
            client = SupabaseDB.get_client()
            result = client.table("presupuestos").update({"limite_mensual": limite_mensual})\
                .eq("id", presupuesto_id).eq("usuario_id", usuario_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"[Supabase] presupuestos.actualizar error: {e}")
            raise

    @staticmethod
    async def eliminar(presupuesto_id: str, usuario_id: str) -> bool:
        if not _supabase_ok():
            if not _de_usuario(await DemoPresupuestoDB.obtener_por_id(presupuesto_id), usuario_id):
                return False
            return await DemoPresupuestoDB.eliminar(presupuesto_id)
        try:
            client = SupabaseDB.get_client()
            client.table("presupuestos").delete().eq("id", presupuesto_id).eq("usuario_id", usuario_id).execute()
            return True
        except Exception as e:
            print(f"[Supabase] presupuestos.eliminar error: {e}")
            raise


class MetaDB:

    @staticmethod
    async def crear(usuario_id: str, nombre: str, monto_objetivo: float, fecha_objetivo: str) -> dict:
        if not _supabase_ok():
            return await DemoMetaDB.crear(usuario_id, nombre, monto_objetivo, fecha_objetivo)
        try:
            client = SupabaseDB.get_client()
            row = {
                "id": str(uuid.uuid4()),
                "usuario_id": usuario_id,
                "nombre": nombre,
                "monto_objetivo": monto_objetivo,
                "monto_actual": 0,
                "fecha_objetivo": fecha_objetivo,
            }
            result = client.table("metas").insert(row).execute()
            return result.data[0]
        except Exception as e:
            print(f"[Supabase] metas.crear error: {e}")
            raise

    @staticmethod
    async def obtener_por_usuario(usuario_id: str) -> list:
        if not _supabase_ok():
            return await DemoMetaDB.obtener_por_usuario(usuario_id)
        try:
            client = SupabaseDB.get_client()
            result = client.table("metas").select("*").eq("usuario_id", usuario_id).execute()
            return result.data
        except Exception as e:
            print(f"[Supabase] metas.obtener error: {e}")
            raise

    @staticmethod
    async def obtener_por_id(meta_id: str, usuario_id: str) -> Optional[dict]:
        if not _supabase_ok():
            return _de_usuario(await DemoMetaDB.obtener_por_id(meta_id), usuario_id)
        try:
            client = SupabaseDB.get_client()
            result = client.table("metas").select("*").eq("id", meta_id).eq("usuario_id", usuario_id).limit(1).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"[Supabase] metas.obtener_por_id error: {e}")
            raise

    @staticmethod
    async def actualizar_progreso(meta_id: str, usuario_id: str, updates: dict) -> Optional[dict]:
        if not _supabase_ok():
            if not _de_usuario(await DemoMetaDB.obtener_por_id(meta_id), usuario_id):
                return None
            return await DemoMetaDB.actualizar_progreso(meta_id, updates)
        try:
            allowed = {'nombre', 'monto_objetivo', 'monto_actual', 'fecha_objetivo'}
            data = {k: v for k, v in updates.items() if k in allowed and v is not None}
            client = SupabaseDB.get_client()
            result = client.table("metas").update(data).eq("id", meta_id).eq("usuario_id", usuario_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"[Supabase] metas.actualizar error: {e}")
            raise

    @staticmethod
    async def eliminar(meta_id: str, usuario_id: str) -> bool:
        if not _supabase_ok():
            if not _de_usuario(await DemoMetaDB.obtener_por_id(meta_id), usuario_id):
                return False
            return await DemoMetaDB.eliminar(meta_id)
        try:
            client = SupabaseDB.get_client()
            client.table("metas").delete().eq("id", meta_id).eq("usuario_id", usuario_id).execute()
            return True
        except Exception as e:
            print(f"[Supabase] metas.eliminar error: {e}")
            raise

    # Códigos de error que indican que la función SQL aún no está instalada (o el esquema
    # no coincide): en ese caso la ruta usa el método anterior, así nada se rompe.
    _RPC_NO_DISPONIBLE = {"PGRST202", "42883", "42703", "42P01"}

    @staticmethod
    async def abonar(meta_id: str, usuario_id: str, monto: float, fecha: str, descripcion: str) -> Optional[dict]:
        """Abono atómico con la función SQL `abonar_meta` (CHG-004, INV-008).

        Suma a la meta y registra el gasto en una sola transacción de PostgreSQL, con la
        meta bloqueada mientras tanto (dos abonos simultáneos no se pisan).
        Devuelve la meta actualizada, o None si no existe o es de otro usuario.
        Lanza AbonoAtomicoNoDisponible si no hay Supabase o la función no está instalada.
        """
        if not _supabase_ok():
            raise AbonoAtomicoNoDisponible("modo demo")
        client = SupabaseDB.get_client()
        try:
            result = client.rpc("abonar_meta", {
                "p_meta_id": meta_id,
                "p_usuario_id": usuario_id,
                "p_monto": monto,
                "p_fecha": fecha,
                "p_descripcion": descripcion,
            }).execute()
        except Exception as e:
            codigo = str(getattr(e, "code", "") or "")
            mensaje = str(getattr(e, "message", "") or e)
            # 22P02: el id no es un UUID válido → se trata como meta inexistente (404)
            if codigo in ("P0002", "22P02") or "meta_no_encontrada" in mensaje:
                return None
            if codigo in MetaDB._RPC_NO_DISPONIBLE:
                print(f"[Supabase] abonar_meta no disponible ({codigo}); se usa el método anterior")
                raise AbonoAtomicoNoDisponible(codigo) from e
            print(f"[Supabase] metas.abonar error: {codigo} {mensaje}")
            raise
        datos = result.data
        if isinstance(datos, list):
            return datos[0] if datos else None
        return datos or None


class AbonoAtomicoNoDisponible(Exception):
    """La función SQL `abonar_meta` no se puede usar (modo demo o migración sin aplicar)."""



class RecurrenteDB:
    """Transacciones recurrentes (CHG-012). Toda consulta filtra por usuario_id (INV-001)."""

    _COLUMNAS = {"categoria_id", "tipo", "monto", "descripcion", "medio_pago",
                 "frecuencia", "dia_ancla", "proxima_fecha", "activa"}

    @staticmethod
    def _normalizar(datos: dict) -> dict:
        fila = {k: v for k, v in datos.items() if k in RecurrenteDB._COLUMNAS}
        if "categoria_id" in fila and not fila["categoria_id"]:
            fila["categoria_id"] = None  # "" = sin categoría (columna uuid)
        return fila

    @staticmethod
    def _salida(fila: Optional[dict]) -> Optional[dict]:
        if fila and fila.get("proxima_fecha") is not None:
            fila["proxima_fecha"] = str(fila["proxima_fecha"])[:10]
        return fila

    @staticmethod
    async def crear(usuario_id: str, datos: dict) -> dict:
        fila = RecurrenteDB._normalizar(datos)
        if not _supabase_ok():
            return await DemoRecurrenteDB.crear(usuario_id, fila)
        try:
            client = SupabaseDB.get_client()
            row = {"id": str(uuid.uuid4()), "usuario_id": usuario_id, **fila}
            result = client.table("recurrentes").insert(row).execute()
            return RecurrenteDB._salida(result.data[0])
        except Exception as e:
            print(f"[Supabase] recurrentes.crear error: {e}")
            raise

    @staticmethod
    async def obtener_por_usuario(usuario_id: str) -> list:
        if not _supabase_ok():
            return await DemoRecurrenteDB.obtener_por_usuario(usuario_id)
        try:
            client = SupabaseDB.get_client()
            result = client.table("recurrentes").select("*").eq("usuario_id", usuario_id)\
                .order("proxima_fecha").execute()
            return [RecurrenteDB._salida(r) for r in result.data]
        except Exception as e:
            print(f"[Supabase] recurrentes.obtener error: {e}")
            raise

    @staticmethod
    async def obtener_por_id(recurrente_id: str, usuario_id: str) -> Optional[dict]:
        if not _supabase_ok():
            return _de_usuario(await DemoRecurrenteDB.obtener_por_id(recurrente_id), usuario_id)
        try:
            client = SupabaseDB.get_client()
            result = client.table("recurrentes").select("*").eq("id", recurrente_id)\
                .eq("usuario_id", usuario_id).limit(1).execute()
            return RecurrenteDB._salida(result.data[0]) if result.data else None
        except Exception as e:
            print(f"[Supabase] recurrentes.obtener_por_id error: {e}")
            raise

    @staticmethod
    async def actualizar(recurrente_id: str, usuario_id: str, datos: dict,
                         esperada: Optional[str] = None) -> Optional[dict]:
        """Actualiza los campos. Con `esperada`, solo si la próxima fecha sigue siendo esa (compare-and-set)."""
        fila = RecurrenteDB._normalizar(datos)
        if not _supabase_ok():
            actual = _de_usuario(await DemoRecurrenteDB.obtener_por_id(recurrente_id), usuario_id)
            if not actual or (esperada is not None and actual["proxima_fecha"] != esperada):
                return None
            return await DemoRecurrenteDB.actualizar(recurrente_id, fila)
        try:
            client = SupabaseDB.get_client()
            q = client.table("recurrentes").update(fila).eq("id", recurrente_id).eq("usuario_id", usuario_id)
            if esperada is not None:
                q = q.eq("proxima_fecha", esperada)
            result = q.execute()
            return RecurrenteDB._salida(result.data[0]) if result.data else None
        except Exception as e:
            print(f"[Supabase] recurrentes.actualizar error: {e}")
            raise

    @staticmethod
    async def avanzar(recurrente_id: str, usuario_id: str, esperada: str, nueva: str) -> Optional[dict]:
        """Pasa la próxima fecha de `esperada` a `nueva` solo si no cambió entretanto (compare-and-set).

        Devuelve None si otra petición ya la movió: así un doble toque no registra dos veces (INV-026).
        """
        if not _supabase_ok():
            if not _de_usuario(await DemoRecurrenteDB.obtener_por_id(recurrente_id), usuario_id):
                return None
            return await DemoRecurrenteDB.avanzar(recurrente_id, esperada, nueva)
        try:
            client = SupabaseDB.get_client()
            result = client.table("recurrentes").update({"proxima_fecha": nueva})\
                .eq("id", recurrente_id).eq("usuario_id", usuario_id)\
                .eq("proxima_fecha", esperada).execute()
            return RecurrenteDB._salida(result.data[0]) if result.data else None
        except Exception as e:
            print(f"[Supabase] recurrentes.avanzar error: {e}")
            raise

    @staticmethod
    async def eliminar(recurrente_id: str, usuario_id: str) -> bool:
        if not _supabase_ok():
            if not _de_usuario(await DemoRecurrenteDB.obtener_por_id(recurrente_id), usuario_id):
                return False
            return await DemoRecurrenteDB.eliminar(recurrente_id)
        try:
            client = SupabaseDB.get_client()
            client.table("recurrentes").delete().eq("id", recurrente_id).eq("usuario_id", usuario_id).execute()
            return True
        except Exception as e:
            print(f"[Supabase] recurrentes.eliminar error: {e}")
            raise
