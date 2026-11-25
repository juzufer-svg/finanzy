/**
 * Cuentas de dinero (CHG-019 fase a, UC-016, CT-012): tipos y utilidades puras.
 * Sin dependencias de React ni del navegador, para poder probarlas con `npm test`.
 *
 * Vocabulario: «cuenta de dinero» = la entidad nueva (dónde está el dinero); «cuenta» sola = cuenta de usuario.
 * Los montos viajan y se guardan en COP (INV-047); la conversión a la moneda de visualización la hace la pantalla
 * con `fmt/toInput/toBase`. El saldo lo calcula el servidor: aquí solo se lee y se muestra.
 */

export type TipoCuenta = 'efectivo' | 'ahorros_corriente' | 'billetera_digital' | 'tarjeta_credito'

export const TIPOS_CUENTA: { value: TipoCuenta; label: string; ayuda: string }[] = [
  { value: 'efectivo', label: 'Efectivo', ayuda: 'Dinero en billetera o en casa' },
  { value: 'ahorros_corriente', label: 'Ahorros o corriente', ayuda: 'Cuenta de un banco' },
  { value: 'billetera_digital', label: 'Billetera digital', ayuda: 'Nequi, Daviplata y similares' },
  { value: 'tarjeta_credito', label: 'Tarjeta de crédito', ayuda: 'Es la única que puede quedar en deuda' },
]

/** Largo máximo del nombre (CT-012: 1-100). */
export const NOMBRE_CUENTA_MAX = 100
/** Tope de saldo inicial y de montos con cuenta, en COP (INV-051). */
export const TOPE_COP = 9_999_999_999.99
/** Máximo de cuentas de dinero por usuario (INV-050); el servidor lo hace cumplir. */
export const MAX_CUENTAS = 20

export interface Cuenta {
  id: string
  nombre: string
  /** `null` si el servidor envía un tipo que esta versión no conoce. */
  tipo: TipoCuenta | null
  /** En COP. */
  saldo_inicial: number
  /** En COP, calculado por el servidor; `null` si no vino un número válido. */
  saldo: number | null
  archivada: boolean
}

const esObjeto = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)

/** Número o texto numérico finito (el servidor puede serializar los decimales como texto); si no, `null`. */
function aNumero(v: unknown): number | null {
  if (typeof v === 'number') return Number.isFinite(v) ? v : null
  if (typeof v === 'string' && v.trim() !== '') {
    const n = Number(v)
    return Number.isFinite(n) ? n : null
  }
  return null
}

const TIPOS_VALIDOS = new Set<string>(TIPOS_CUENTA.map(t => t.value))

/** Etiqueta del tipo; un tipo desconocido se muestra como «Otra». */
export function tipoLabel(tipo: unknown): string {
  return TIPOS_CUENTA.find(t => t.value === tipo)?.label ?? 'Otra'
}

/** Texto del estado (siempre con palabra, no solo color). */
export function estadoLabel(archivada: boolean): string {
  return archivada ? 'Archivada' : 'No archivada'
}

export const esTarjeta = (tipo: unknown): boolean => tipo === 'tarjeta_credito'

/** Valida y normaliza una cuenta de la respuesta; lista blanca de campos. `null` si no es utilizable. */
export function normalizarCuenta(raw: unknown): Cuenta | null {
  if (!esObjeto(raw)) return null
  if (typeof raw.id !== 'string' || raw.id === '' || typeof raw.nombre !== 'string') return null
  return {
    id: raw.id,
    nombre: raw.nombre,
    tipo: typeof raw.tipo === 'string' && TIPOS_VALIDOS.has(raw.tipo) ? (raw.tipo as TipoCuenta) : null,
    saldo_inicial: aNumero(raw.saldo_inicial) ?? 0,
    saldo: aNumero(raw.saldo),
    archivada: raw.archivada === true,
  }
}

/** Lista de cuentas de la respuesta de `GET /cuentas`, por nombre; ignora lo que no tenga la forma esperada. */
export function normalizarCuentas(raw: unknown): Cuenta[] {
  if (!Array.isArray(raw)) return []
  const lista: Cuenta[] = []
  for (const item of raw) {
    const c = normalizarCuenta(item)
    if (c) lista.push(c)
  }
  return lista.sort((a, b) => a.nombre.localeCompare(b.nombre, 'es', { sensitivity: 'base' }))
}

/** Separa las cuentas no archivadas de las archivadas (la pantalla las muestra en secciones distintas). */
export function separarCuentas(cuentas: Cuenta[]): { activas: Cuenta[]; archivadas: Cuenta[] } {
  return { activas: cuentas.filter(c => !c.archivada), archivadas: cuentas.filter(c => c.archivada) }
}

/** Nombre para mostrar en listas y selectores: «Ahorros (archivada)». */
export function nombreVisible(c: Pick<Cuenta, 'nombre' | 'archivada'>): string {
  return c.archivada ? `${c.nombre} (archivada)` : c.nombre
}

/**
 * Opciones del selector «Cuenta (opcional)»: solo las no archivadas. Si la transacción que se edita ya tiene una
 * cuenta archivada, esa se conserva como opción para no perderla sin querer.
 */
export function opcionesSelector(cuentas: Cuenta[], cuentaActualId?: string | null): { id: string; label: string }[] {
  return cuentas
    .filter(c => !c.archivada || (!!cuentaActualId && c.id === cuentaActualId))
    .map(c => ({ id: c.id, label: nombreVisible(c) }))
}

/** Nombre de la cuenta de una transacción para mostrarlo en la lista; `null` si no tiene o no se conoce. */
export function nombreDeCuenta(cuentas: Cuenta[], cuentaId: unknown): string | null {
  if (typeof cuentaId !== 'string' || cuentaId === '') return null
  return cuentas.find(c => c.id === cuentaId)?.nombre ?? null
}

/**
 * Parte de `cuenta_id` para `PUT /transacciones/{id}` (CT-003 v1.2): sin cambio no se envía (conserva la cuenta y no
 * revalida el monto); vacío = quitar (`null`); otro valor = reemplazar.
 */
export function cuentaIdParaPut(original: string | null | undefined, elegido: string): { cuenta_id?: string | null } {
  const antes = original || ''
  if (elegido === antes) return {}
  return { cuenta_id: elegido || null }
}

/** Monto con signo para mostrar un saldo (puede ser negativo en una tarjeta): «-$1.000». */
export function textoSaldo(saldo: number | null, fmt: (n: number) => string): string {
  if (saldo === null) return '—'
  return saldo < 0 ? `-${fmt(Math.abs(saldo))}` : fmt(saldo)
}

/** Aclaración en texto cuando una tarjeta de crédito está en negativo (no solo color). */
export function notaDeuda(c: Pick<Cuenta, 'tipo' | 'saldo'>): string | null {
  return esTarjeta(c.tipo) && c.saldo !== null && c.saldo < 0 ? 'Deuda' : null
}

export interface DatosCuenta { nombre: string; tipo: string; saldoInicial: number }

/** Validación del formulario (antes de enviar). `saldoInicial` ya viene en COP. Devuelve el mensaje o `null`. */
export function validarCuenta(d: DatosCuenta): string | null {
  const nombre = d.nombre.trim()
  if (nombre === '') return 'Escribe un nombre para la cuenta.'
  if (nombre.length > NOMBRE_CUENTA_MAX) return `El nombre admite hasta ${NOMBRE_CUENTA_MAX} caracteres.`
  if (!TIPOS_VALIDOS.has(d.tipo)) return 'Elige un tipo de cuenta.'
  if (!Number.isFinite(d.saldoInicial)) return 'Escribe un saldo inicial válido (puede ser 0).'
  if (Math.abs(d.saldoInicial) > TOPE_COP) return 'El saldo inicial supera el máximo permitido (9.999.999.999,99 en pesos colombianos).'
  if (d.saldoInicial < 0 && !esTarjeta(d.tipo)) return 'Solo las tarjetas de crédito pueden tener saldo negativo.'
  return null
}

/** Cuerpo de `PUT /cuentas/{id}` con solo lo que cambió (el tipo no se envía: no es editable). */
export function cambiosCuenta(
  original: Pick<Cuenta, 'nombre' | 'saldo_inicial'>,
  nuevo: { nombre: string; saldoInicial: number },
): { nombre?: string; saldo_inicial?: number } {
  const cambios: { nombre?: string; saldo_inicial?: number } = {}
  const nombre = nuevo.nombre.trim()
  if (nombre !== original.nombre) cambios.nombre = nombre
  if (nuevo.saldoInicial !== original.saldo_inicial) cambios.saldo_inicial = nuevo.saldoInicial
  return cambios
}

/**
 * Mensaje para el usuario a partir de un error de axios (o similar). 409 y 422 con texto del servidor lo muestran tal
 * cual (saldo insuficiente, cuenta archivada, nombre repetido, máximo de 20…); 404, 503 y sin conexión tienen texto propio.
 */
export function mensajeErrorCuenta(err: unknown, fallback: string): string {
  const e = err as { response?: { status?: number; data?: { detail?: unknown } } } | null | undefined
  const response = e?.response
  if (!response) return 'No hay conexión con el servidor. Revisa tu internet e intenta de nuevo.'
  const detail = response.data?.detail
  const status = response.status
  if (status === 503) return 'El servicio de cuentas no está disponible por ahora. No se guardó nada; intenta de nuevo en unos minutos.'
  if (status === 404) return typeof detail === 'string' && detail ? detail : 'Esta cuenta ya no existe. Actualiza la página.'
  if (status === 429) return 'Demasiados intentos. Espera unos minutos.'
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail) && detail.length > 0) return 'Revisa los datos ingresados.'
  return fallback
}
