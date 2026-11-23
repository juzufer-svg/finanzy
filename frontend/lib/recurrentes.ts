// Transacciones recurrentes (CHG-012). Funciones puras, sin React ni alias, probadas con `npm test`.
// El cálculo de la próxima fecha lo hace el backend (app/utils/recurrencia.py, INV-026); aquí solo se muestra.

export const FRECUENCIAS = [
  { value: 'mensual', label: 'Mensual', ayuda: 'El mismo día de cada mes' },
  { value: 'quincenal', label: 'Quincenal', ayuda: 'Dos veces al mes, cada 15 días' },
  { value: 'semanal', label: 'Semanal', ayuda: 'Cada 7 días' },
] as const

export type Frecuencia = (typeof FRECUENCIAS)[number]['value']

export interface Recurrente {
  id: string
  categoria_id: string | null
  tipo: 'ingreso' | 'gasto' | string
  monto: number
  descripcion?: string | null
  medio_pago?: string | null
  frecuencia: Frecuencia | string
  dia_ancla: number
  proxima_fecha: string
  activa: boolean
}

const pad = (n: number) => String(n).padStart(2, '0')

/** Fecha local `YYYY-MM-DD` (la del navegador, no UTC). */
export function localDate(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/** Describe cuándo se repite: "Mensual, el día 5", "Quincenal, días 15 y 30", "Semanal". */
export function frecuenciaTexto(frecuencia: string, diaAncla: number): string {
  if (frecuencia === 'mensual') return diaAncla >= 29 ? `Mensual, el día ${diaAncla} (o el último del mes)` : `Mensual, el día ${diaAncla}`
  if (frecuencia === 'quincenal') {
    const primero = diaAncla <= 15 ? diaAncla : diaAncla - 15
    return `Quincenal, días ${primero} y ${primero + 15}`
  }
  if (frecuencia === 'semanal') return 'Semanal'
  return frecuencia
}

/** Días entre hoy y la fecha (negativo = atrasada). Ambas `YYYY-MM-DD` locales. */
export function diasHasta(fecha: string, hoy: string): number {
  const [a, m, d] = fecha.split('-').map(Number)
  const [ha, hm, hd] = hoy.split('-').map(Number)
  return Math.round((Date.UTC(a, m - 1, d) - Date.UTC(ha, hm - 1, hd)) / 86_400_000)
}

/** "Hoy", "Mañana", "En 3 días", "Hace 2 días". */
export function cuandoTexto(fecha: string, hoy: string): string {
  const dias = diasHasta(fecha, hoy)
  if (dias === 0) return 'Hoy'
  if (dias === 1) return 'Mañana'
  if (dias === -1) return 'Ayer'
  return dias > 0 ? `En ${dias} días` : `Hace ${-dias} días`
}

/** Total mensual aproximado de las recurrentes activas de un tipo (semanal ≈ 52/12 veces al mes). */
export function totalMensualEstimado(items: Recurrente[], tipo: string): number {
  const veces: Record<string, number> = { mensual: 1, quincenal: 2, semanal: 52 / 12 }
  return items
    .filter(r => r.activa && r.tipo === tipo)
    .reduce((s, r) => s + Number(r.monto) * (veces[r.frecuencia] ?? 0), 0)
}
