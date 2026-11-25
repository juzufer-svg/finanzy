/**
 * Transferencias entre cuentas de dinero (CHG-024, UC-016, CT-012 §Transferencias): utilidades puras.
 * Los montos viajan en COP; el servidor aplica las reglas (saldo, archivadas, tope); aquí solo se valida antes de enviar.
 */

import { TOPE_COP, type Cuenta } from './cuentas.ts'

export const DESCRIPCION_MAX = 255

export interface Transferencia {
  id: string
  cuenta_origen_id: string
  cuenta_destino_id: string
  /** En COP. */
  monto: number
  fecha: string
  descripcion: string
}

const esObjeto = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)

/** Valida una transferencia de la respuesta; `null` si no es utilizable. */
export function normalizarTransferencia(raw: unknown): Transferencia | null {
  if (!esObjeto(raw)) return null
  const { id, cuenta_origen_id: o, cuenta_destino_id: d, fecha } = raw
  if (typeof id !== 'string' || !id || typeof o !== 'string' || typeof d !== 'string' || typeof fecha !== 'string') return null
  const monto = typeof raw.monto === 'number' ? raw.monto : typeof raw.monto === 'string' && raw.monto.trim() !== '' ? Number(raw.monto) : NaN
  if (!Number.isFinite(monto)) return null
  return { id, cuenta_origen_id: o, cuenta_destino_id: d, monto, fecha, descripcion: typeof raw.descripcion === 'string' ? raw.descripcion : '' }
}

/** Lista de la respuesta de `GET /transferencias`, más recientes primero. */
export function normalizarTransferencias(raw: unknown): Transferencia[] {
  if (!Array.isArray(raw)) return []
  const lista: Transferencia[] = []
  for (const item of raw) {
    const t = normalizarTransferencia(item)
    if (t) lista.push(t)
  }
  return lista.sort((a, b) => b.fecha.localeCompare(a.fecha))
}

/** Fecha local `YYYY-MM-DD`. */
export function fechaLocal(d: Date = new Date()): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** Mes `YYYY-MM` de una fecha local. */
export function mesDe(d: Date = new Date()): string {
  return fechaLocal(d).slice(0, 7)
}

/** Mes anterior o siguiente (`delta` = -1 / +1) de un `YYYY-MM`. */
export function desplazarMes(mes: string, delta: number): string {
  const [a, m] = mes.split('-').map(Number)
  const idx = a * 12 + (m - 1) + delta
  return `${Math.floor(idx / 12)}-${String((idx % 12) + 1).padStart(2, '0')}`
}

/** «noviembre de 2026». */
export function mesLabel(mes: string): string {
  const [a, m] = mes.split('-').map(Number)
  return new Date(a, m - 1, 1).toLocaleDateString('es-CO', { month: 'long', year: 'numeric' })
}

/** Cuentas que pueden elegirse como origen o destino: solo las no archivadas. */
export function cuentasParaTransferir(cuentas: Cuenta[]): Cuenta[] {
  return cuentas.filter(c => !c.archivada)
}

export interface DatosTransferencia { origen: string; destino: string; monto: number; fecha: string; descripcion: string }

/** Validación en el cliente (el servidor la repite). `monto` ya viene en COP. Devuelve el mensaje o `null`. */
export function validarTransferencia(d: DatosTransferencia): string | null {
  if (!d.origen) return 'Elige la cuenta de origen.'
  if (!d.destino) return 'Elige la cuenta de destino.'
  if (d.origen === d.destino) return 'Elige dos cuentas distintas.'
  if (!Number.isFinite(d.monto) || d.monto <= 0) return 'Escribe un monto mayor que 0.'
  if (d.monto > TOPE_COP) return 'El monto supera el máximo permitido (9.999.999.999,99 en pesos colombianos).'
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d.fecha)) return 'Elige una fecha válida.'
  if (d.descripcion.trim().length > DESCRIPCION_MAX) return `La nota admite hasta ${DESCRIPCION_MAX} caracteres.`
  return null
}

/** Cuerpo de `POST /transferencias`. */
export function cuerpoTransferencia(d: DatosTransferencia): Record<string, unknown> {
  const cuerpo: Record<string, unknown> = {
    cuenta_origen_id: d.origen,
    cuenta_destino_id: d.destino,
    monto: d.monto,
    fecha: d.fecha,
  }
  const nota = d.descripcion.trim()
  if (nota) cuerpo.descripcion = nota
  return cuerpo
}
