/**
 * Rango de fechas permitido en transacciones y transferencias (CHG-027, INV-063): del 1 de enero de 2026 a hoy + 365 días,
 * con «hoy» en hora de Colombia (UTC−5 fijo). El servidor decide; esto solo ayuda (`min`/`max` y validación previa).
 * Puro, sin React, para probarlo con `npm test`.
 */
import { diaDeInstante } from './monitor.ts'

export const FECHA_MINIMA = '2026-01-01'
export const DIAS_ADELANTE = 365

/** Día de Colombia (`YYYY-MM-DD`) de un instante; no depende de la zona del navegador. */
export function hoyColombia(ahora: Date = new Date()): string {
  return diaDeInstante(ahora.toISOString()) ?? FECHA_MINIMA
}

/** `YYYY-MM-DD` + `dias` días. */
function sumarDias(dia: string, dias: number): string {
  const [a, m, d] = dia.split('-').map(Number)
  return new Date(Date.UTC(a, m - 1, d + dias)).toISOString().slice(0, 10)
}

/** Límites de los campos fecha: `min` fijo y `max` = hoy de Colombia + 365 días. */
export function rangoFechas(ahora: Date = new Date()): { min: string; max: string } {
  return { min: FECHA_MINIMA, max: sumarDias(hoyColombia(ahora), DIAS_ADELANTE) }
}

/** `YYYY-MM-DD` → `dd/mm/aaaa`. */
function ddmmaaaa(dia: string): string {
  const [a, m, d] = dia.split('-')
  return `${d}/${m}/${a}`
}

/** Mismo texto que el servidor (INV-063). */
export function mensajeFueraDeRango(ahora: Date = new Date()): string {
  return `La fecha debe estar entre el 1 de enero de 2026 y el ${ddmmaaaa(rangoFechas(ahora).max)}`
}

/** `null` si la fecha está en rango (o no tiene formato `YYYY-MM-DD`: eso lo juzgan otras validaciones); si no, el mensaje. */
export function validarRangoFecha(fecha: string, ahora: Date = new Date()): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(fecha)) return null
  const { min, max } = rangoFechas(ahora)
  return fecha >= min && fecha <= max ? null : mensajeFueraDeRango(ahora)
}
