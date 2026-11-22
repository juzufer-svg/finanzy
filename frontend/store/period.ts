'use client'

import { create } from 'zustand'
import { isValidMonth, monthOf } from '@/lib/month-stats'

/**
 * Período (mes `YYYY-MM`) compartido por todas las vistas del dashboard (CHG-009).
 *
 * - Un solo valor para Dashboard, Transacciones, Presupuestos y Reportes: al cambiarlo en una
 *   vista, las demás lo muestran igual.
 * - Se guarda en `sessionStorage`: sobrevive a navegar entre menús y a recargar la página, pero
 *   una pestaña nueva arranca en el mes actual, que es lo que casi siempre se quiere.
 * - Se borra al cerrar sesión y cuando la sesión vence (ver `lib/api-client.ts`, misma clave).
 * - Solo guarda el mes: no es un dato sensible.
 */
export const PERIOD_STORAGE_KEY = 'finanzy_periodo'
const STORAGE_KEY = PERIOD_STORAGE_KEY

const currentMonth = () => monthOf(new Date())

function readStored(): string {
  if (typeof window === 'undefined') return currentMonth()
  try {
    const value = sessionStorage.getItem(STORAGE_KEY)
    if (isValidMonth(value)) return value
  } catch {
    // Sin almacenamiento (modo privado estricto): se usa el mes actual
  }
  return currentMonth()
}

function writeStored(mes: string | null) {
  try {
    if (mes) sessionStorage.setItem(STORAGE_KEY, mes)
    else sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // Sin almacenamiento: el período vive solo en memoria
  }
}

interface PeriodStore {
  /** Mes seleccionado, `YYYY-MM`. */
  mes: string
  /** Cambia el período; ignora valores con formato inválido. */
  setMes: (mes: string) => void
  /** Vuelve al mes actual (también al cerrar sesión). */
  resetMes: () => void
}

export const usePeriodStore = create<PeriodStore>((set) => ({
  mes: readStored(),
  setMes: (mes) => {
    if (!isValidMonth(mes)) return
    writeStored(mes)
    set({ mes })
  },
  resetMes: () => {
    writeStored(null)
    set({ mes: currentMonth() })
  },
}))
