/**
 * Utilidades de la exportación a CSV/Excel (CHG-018, CT-011, INV-044, INV-045).
 *
 * Sin dependencias del navegador ni de React: se prueban con `npm test` (tests/exportar.test.mjs).
 * El proxy (app/api/v1/[...path]/route.ts) usa `cabecerasDeDescarga`.
 */

export type FormatoExportacion = 'csv' | 'xlsx'

/** Tope de meses por archivo (CT-011). El servidor lo vuelve a comprobar. */
export const MAX_MESES_EXPORTAR = 12

export const MENSAJE_413 = 'El archivo es demasiado grande. Elige menos meses.'
export const MENSAJE_ERROR_DEFECTO = 'No se pudo descargar el archivo. Intenta de nuevo.'

const MES = /^(\d{4})-(0[1-9]|1[0-2])$/

function partes(mes: string): [number, number] | null {
  const m = MES.exec(mes)
  if (!m) return null
  const anio = Number(m[1])
  if (anio < 2000 || anio > 2100) return null
  return [anio, Number(m[2])]
}

/** Cantidad de meses del rango (ambos incluidos), o null si algún mes no es `AAAA-MM` válido. */
export function mesesDelRango(desde: string, hasta: string): number | null {
  const a = partes(desde)
  const b = partes(hasta)
  if (!a || !b) return null
  return (b[0] - a[0]) * 12 + (b[1] - a[1]) + 1
}

export type ResultadoRango = { ok: true } | { ok: false; motivo: string }

/** ¿Se puede pedir este rango? Mismos mensajes que el servidor (CT-011); el servidor lo comprueba otra vez. */
export function rangoValido(desde: string, hasta: string): ResultadoRango {
  const n = mesesDelRango(desde, hasta)
  if (n === null) return { ok: false, motivo: 'Elige un mes inicial y uno final válidos.' }
  if (n < 1) return { ok: false, motivo: 'El mes inicial no puede ser posterior al final.' }
  if (n > MAX_MESES_EXPORTAR) return { ok: false, motivo: `Puedes exportar hasta ${MAX_MESES_EXPORTAR} meses por archivo.` }
  return { ok: true }
}

/** Nombre de respaldo del archivo, igual al que manda el servidor (sin datos personales). */
export function nombreDeArchivo(desde: string, hasta: string | undefined | null, formato: FormatoExportacion): string {
  const rango = !hasta || hasta === desde ? desde : `${desde}_a_${hasta}`
  return `finanzy-transacciones-${rango}.${formato === 'xlsx' ? 'xlsx' : 'csv'}`
}

/**
 * Nombre del archivo según `Content-Disposition`. Solo se acepta un nombre ASCII seguro
 * (letras, números, punto, guion y guion bajo); si no, se usa `respaldo`.
 */
export function nombreDesdeContentDisposition(valor: string | null | undefined, respaldo: string): string {
  const m = /filename="?([^";]+)"?/i.exec(valor || '')
  const nombre = m?.[1]?.trim() || ''
  return /^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$/.test(nombre) && !nombre.includes('..') ? nombre : respaldo
}

type LectorDeCabeceras = { get(nombre: string): string | null }

/**
 * Cabeceras del backend que el proxy reenvía al navegador.
 * - Siempre `Content-Type` (si existe).
 * - `Content-Disposition` solo en `exportaciones/*` y solo si es un adjunto (`attachment`).
 * (`Cache-Control: no-store` lo pone el proxy aparte, en toda respuesta.)
 */
export function cabecerasDeDescarga(path: string, upstream: LectorDeCabeceras): Record<string, string> {
  const salida: Record<string, string> = {}
  const tipo = upstream.get('content-type')
  if (tipo) salida['Content-Type'] = tipo
  if (path === 'exportaciones' || path.startsWith('exportaciones/')) {
    const disposicion = upstream.get('content-disposition')
    if (disposicion && /^attachment\b/i.test(disposicion)) salida['Content-Disposition'] = disposicion
  }
  return salida
}

type ErrorConRespuesta = { response?: { status?: number; data?: unknown } }

/**
 * Con `responseType: 'blob'` los errores (422, 429, 503, 413…) llegan como Blob, no como objeto.
 * Lee su JSON y lo deja en `err.response.data` para que `apiErrorMessage` muestre el `detail`.
 * Si el cuerpo no es JSON (p. ej. el 413 opaco de Vercel) usa un mensaje claro por defecto.
 * Devuelve el mismo error recibido.
 */
export async function errorDeBlob<T>(err: T): Promise<T> {
  const respuesta = (err as ErrorConRespuesta | null)?.response
  if (!respuesta) return err
  let datos: unknown = respuesta.data
  if (typeof Blob !== 'undefined' && datos instanceof Blob) {
    try {
      datos = JSON.parse(await datos.text())
    } catch {
      datos = undefined
    }
  }
  const esObjeto = typeof datos === 'object' && datos !== null && !Array.isArray(datos)
  if (!esObjeto || typeof (datos as { detail?: unknown }).detail !== 'string') {
    datos = respuesta.status === 413 ? { detail: MENSAJE_413 } : {}
  }
  respuesta.data = datos
  return err
}
