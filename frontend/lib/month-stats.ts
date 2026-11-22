// Cálculos del mes para el tablero, los reportes y el buscador de transacciones (CHG-006).
// Funciones puras, sin React ni imports con alias, para poder probarlas con `npm test`
// (node --test, ver tests/month-stats.test.mjs). Los montos llegan en la moneda base (COP).

export interface MovimientoBase {
  id: string
  categoria_id: string | null
  tipo: 'ingreso' | 'gasto' | string
  monto: number
  descripcion?: string | null
  fecha: string
  medio_pago?: string | null
}

export interface CategoriaBase {
  id: string
  nombre: string
  tipo: string
}

export interface PresupuestoBase {
  categoria_id: string
  limite_mensual: number
}

const pad = (n: number) => String(n).padStart(2, '0')

/** Mes `YYYY-MM` de una fecha local. */
export function monthOf(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}`
}

/**
 * Nombre del mes para títulos: "Noviembre de 2026" (o "Noviembre" sin año).
 * Solo la primera letra va en mayúscula; la clase CSS `capitalize` daba "Noviembre De 2026".
 */
export function monthTitle(mes: string, conAnio = true): string {
  const texto = new Date(Number(mes.slice(0, 4)), Number(mes.slice(5, 7)) - 1, 1)
    .toLocaleDateString('es-ES', conAnio ? { month: 'long', year: 'numeric' } : { month: 'long' })
  return texto.charAt(0).toUpperCase() + texto.slice(1)
}

const MESES_CORTOS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']

/**
 * Fecha corta para listas: "2026-11-05" → "5 nov" (o "5 nov 2026").
 * Se arma a mano para que se vea igual en Chrome y en Safari. Si no tiene el formato esperado, se deja igual.
 */
export function shortDate(fecha: string, conAnio = false): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(fecha || '')
  const mes = m ? MESES_CORTOS[Number(m[2]) - 1] : undefined
  if (!m || !mes) return fecha
  return `${Number(m[3])} ${mes}${conAnio ? ` ${m[1]}` : ''}`
}

/** `true` si el texto es un mes válido `YYYY-MM` (años 2000-2100). Protege lo que se lee del almacenamiento. */
export function isValidMonth(mes: unknown): mes is string {
  if (typeof mes !== 'string') return false
  const m = /^(\d{4})-(0[1-9]|1[0-2])$/.exec(mes)
  return !!m && Number(m[1]) >= 2000 && Number(m[1]) <= 2100
}

/** Mes anterior o siguiente (`delta` = -1 / +1) de un mes `YYYY-MM`. */
export function shiftMonth(mes: string, delta: number): string {
  const [y, m] = mes.split('-').map(Number)
  const d = new Date(y, m - 1 + delta, 1)
  return monthOf(d)
}

/** Días reales del mes (28 a 31). */
export function daysInMonth(mes: string): number {
  const [y, m] = mes.split('-').map(Number)
  return new Date(y, m, 0).getDate()
}

/**
 * Días del mes que ya pasaron, contando hoy: el mes completo si ya terminó,
 * el día de hoy si es el mes en curso y 0 si todavía no empieza.
 */
export function elapsedDays(mes: string, today: Date): number {
  const actual = monthOf(today)
  if (mes < actual) return daysInMonth(mes)
  if (mes > actual) return 0
  return today.getDate()
}

/** Suma de los montos de un tipo (`gasto` o `ingreso`). */
export function sumByTipo(items: MovimientoBase[], tipo: string): number {
  return items.reduce((s, t) => (t.tipo === tipo ? s + Number(t.monto) : s), 0)
}

/** Gasto diario promedio con los días reales transcurridos; `null` si el mes no ha empezado. */
export function dailyAverage(total: number, mes: string, today: Date): number | null {
  const dias = elapsedDays(mes, today)
  return dias > 0 ? total / dias : null
}

/**
 * Proyección al cierre: al ritmo actual, cuánto se habrá gastado el último día.
 * Solo tiene sentido en el mes en curso; para meses cerrados o futuros devuelve `null`.
 */
export function projectMonthEnd(total: number, mes: string, today: Date): number | null {
  if (mes !== monthOf(today)) return null
  const dias = elapsedDays(mes, today)
  return dias > 0 ? (total / dias) * daysInMonth(mes) : null
}

/** Variación porcentual frente al valor anterior; `null` si no hay base para comparar. */
export function pctChange(actual: number, anterior: number): number | null {
  if (!anterior) return null
  return ((actual - anterior) / anterior) * 100
}

/** Total por categoría para un tipo; la clave `''` agrupa lo que no tiene categoría. */
export function totalsByCategory(items: MovimientoBase[], tipo: string): Record<string, number> {
  const out: Record<string, number> = {}
  for (const t of items) {
    if (t.tipo !== tipo) continue
    const k = t.categoria_id || ''
    out[k] = (out[k] || 0) + Number(t.monto)
  }
  return out
}

export interface FilaComparacion {
  categoriaId: string
  actual: number
  anterior: number
  variacion: number | null
}

/** Compara el gasto por categoría de dos meses; ordena de mayor a menor gasto actual. */
export function compareByCategory(actuales: MovimientoBase[], anteriores: MovimientoBase[], tipo = 'gasto'): FilaComparacion[] {
  const a = totalsByCategory(actuales, tipo)
  const b = totalsByCategory(anteriores, tipo)
  const ids = Array.from(new Set([...Object.keys(a), ...Object.keys(b)]))
  return ids
    .map(id => ({ categoriaId: id, actual: a[id] || 0, anterior: b[id] || 0, variacion: pctChange(a[id] || 0, b[id] || 0) }))
    .sort((x, y) => y.actual - x.actual || y.anterior - x.anterior)
}

/**
 * Gasto acumulado día a día: posición i = total gastado del día 1 al día i+1.
 * Con `hastaDia` se corta la serie (por ejemplo, en el día de hoy).
 */
export function cumulativeByDay(items: MovimientoBase[], mes: string, tipo = 'gasto', hastaDia?: number): number[] {
  const dias = daysInMonth(mes)
  const porDia = new Array<number>(dias).fill(0)
  for (const t of items) {
    if (t.tipo !== tipo || !t.fecha.startsWith(mes)) continue
    const d = Number(t.fecha.slice(8, 10))
    if (d >= 1 && d <= dias) porDia[d - 1] += Number(t.monto)
  }
  let acumulado = 0
  const serie = porDia.map(v => (acumulado += v))
  return hastaDia === undefined ? serie : serie.slice(0, Math.max(0, Math.min(hastaDia, dias)))
}

/** Suma de los límites de presupuesto de las categorías de gasto (el presupuesto total del mes). */
export function totalBudget(presupuestos: PresupuestoBase[], categorias: CategoriaBase[]): number {
  const deGasto = new Set(categorias.filter(c => c.tipo === 'gasto').map(c => c.id))
  return presupuestos.reduce((s, p) => (deGasto.has(p.categoria_id) ? s + Number(p.limite_mensual) : s), 0)
}

/** Texto en minúsculas y sin tildes, para buscar sin importar cómo se escribió. */
export function normalizeText(texto: string): string {
  return texto.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim()
}

export interface FiltroMovimientos {
  texto?: string
  categoriaId?: string // '' = todas; '__sin__' = sin categoría
  medioPago?: string   // '' = todos; '__sin__' = sin especificar
}

/** Filtra por texto (descripción o nombre de la categoría), categoría y medio de pago. */
export function filterTransactions<T extends MovimientoBase>(items: T[], filtro: FiltroMovimientos, categorias: CategoriaBase[]): T[] {
  const q = normalizeText(filtro.texto || '')
  const nombres = new Map(categorias.map(c => [c.id, normalizeText(c.nombre)]))
  const existe = (id: string | null) => !!id && nombres.has(id)
  return items.filter(t => {
    if (filtro.categoriaId === '__sin__' ? existe(t.categoria_id) : filtro.categoriaId && t.categoria_id !== filtro.categoriaId) return false
    if (filtro.medioPago === '__sin__' ? !!t.medio_pago : filtro.medioPago && t.medio_pago !== filtro.medioPago) return false
    if (!q) return true
    const desc = normalizeText(t.descripcion || '')
    const cat = (t.categoria_id && nombres.get(t.categoria_id)) || ''
    return desc.includes(q) || cat.includes(q)
  })
}

/** Gasto por medio de pago (CHG-007), de mayor a menor; la clave `''` = sin especificar. */
export function totalsByPaymentMethod(items: MovimientoBase[], tipo = 'gasto'): { medio: string; total: number }[] {
  const out: Record<string, number> = {}
  for (const t of items) {
    if (t.tipo !== tipo) continue
    const k = t.medio_pago || ''
    out[k] = (out[k] || 0) + Number(t.monto)
  }
  return Object.entries(out).map(([medio, total]) => ({ medio, total })).sort((a, b) => b.total - a.total)
}

/**
 * Movimientos del mes anterior que se pueden comparar con `mes`: si `mes` es el mes en curso,
 * solo hasta el mismo día (p. ej. del 1 al 22), para no comparar medio mes con un mes completo.
 */
export function comparablePrevious<T extends MovimientoBase>(anteriores: T[], mes: string, today: Date): T[] {
  if (mes !== monthOf(today)) return anteriores
  const dia = today.getDate()
  return anteriores.filter(t => Number(t.fecha.slice(8, 10)) <= dia)
}

/**
 * Movimientos del mes que ya ocurrieron: en el mes en curso quita los que tienen fecha posterior a hoy
 * (p. ej. un arriendo anotado para el día 30), para que no inflen el promedio, la proyección ni la
 * comparación con el mes anterior. En otros meses devuelve todo.
 */
export function upToToday<T extends MovimientoBase>(items: T[], mes: string, today: Date): T[] {
  if (mes !== monthOf(today)) return items
  const dia = today.getDate()
  return items.filter(t => !t.fecha.startsWith(mes) || Number(t.fecha.slice(8, 10)) <= dia)
}
