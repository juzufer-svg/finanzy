"""
Traducción de los errores de la regla de cuentas de dinero (CHG-019, CT-012) a respuestas HTTP.

La BD (o la BD demo) lanza un error con el SQLSTATE en `code`: FZ001 saldo negativo, FZ002 cuenta archivada, FZ003 tope de
cuentas, 23505 nombre repetido, 23503 llave foránea, 23514 CHECK. Aquí se convierten SIEMPRE en un mensaje fijo y legible:
nunca se devuelve ni se registra el texto de la BD (INV-048). Cualquier otro error se deja pasar tal cual.
"""
from typing import Optional

from fastapi import HTTPException

MSG_SALDO = "Saldo insuficiente en la cuenta: esto la dejaría en negativo. Solo las tarjetas de crédito pueden quedar en negativo."
MSG_ARCHIVADA = "La cuenta está archivada. Desarchívala para registrar movimientos."
MSG_TOPE = "Llegaste al máximo de 20 cuentas de dinero."
MSG_NOMBRE = "Ya tienes una cuenta con ese nombre."
MSG_NO_ENCONTRADA = "Cuenta no encontrada"
MSG_CON_MOVIMIENTOS = "Esta cuenta tiene movimientos. Archívala en lugar de eliminarla."
MSG_MONTO = "El monto de esta cuenta no cumple lo permitido."


def codigo_de(error: Exception) -> Optional[str]:
    codigo = getattr(error, "code", None)
    return str(codigo) if codigo is not None else None


def traducir(error: Exception, al_eliminar_cuenta: bool = False) -> Optional[HTTPException]:
    """La respuesta HTTP que corresponde al error de la regla de cuentas, o None si no es uno de ellos."""
    codigo = codigo_de(error)
    if codigo == "FZ001":
        return HTTPException(status_code=409, detail=MSG_SALDO)
    if codigo == "FZ002":
        return HTTPException(status_code=409, detail=MSG_ARCHIVADA)
    if codigo == "FZ003":
        return HTTPException(status_code=409, detail=MSG_TOPE)
    if codigo == "23505":
        return HTTPException(status_code=409, detail=MSG_NOMBRE)
    if codigo == "23503":
        if al_eliminar_cuenta:   # NO ACTION: la cuenta tiene transacciones (INV-050)
            return HTTPException(status_code=409, detail=MSG_CON_MOVIMIENTOS)
        return HTTPException(status_code=404, detail=MSG_NO_ENCONTRADA)   # cuenta ajena o inexistente (INV-046)
    if codigo == "23514":
        return HTTPException(status_code=422, detail=MSG_MONTO)
    return None


def relanzar(error: Exception, al_eliminar_cuenta: bool = False):
    """Lanza el HTTPException equivalente o, si el error no es de esta regla, el error original."""
    http = traducir(error, al_eliminar_cuenta)
    if http is None:
        raise error
    raise http from None
