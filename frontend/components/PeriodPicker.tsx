'use client'

import { useEffect, useId, useRef, useState } from 'react'
import { usePeriodStore } from '@/store/period'
import { monthOf, monthTitle, shiftMonth } from '@/lib/month-stats'

const MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
const MESES_LARGOS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']

const IconChevron = ({ dir }: { dir: 'left' | 'right' }) => (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
      d={dir === 'left' ? 'M15.75 19.5 8.25 12l7.5-7.5' : 'm8.25 4.5 7.5 7.5-7.5 7.5'} />
  </svg>
)

/**
 * Selector del período (CHG-009). Usa el período compartido (`usePeriodStore`): lo que se elige
 * aquí lo ven todas las vistas y se mantiene al navegar o recargar.
 *
 * Diseño: [‹] [📅 Noviembre de 2026 ▾] [›] y, si no es el mes actual, "Mes actual".
 * El botón central abre un calendario de meses con cambio de año.
 */
export default function PeriodPicker() {
  const mes = usePeriodStore(s => s.mes)
  const setMes = usePeriodStore(s => s.setMes)
  const resetMes = usePeriodStore(s => s.resetMes)
  const [open, setOpen] = useState(false)
  const [anioVista, setAnioVista] = useState(() => Number(mes.slice(0, 4)))
  const wrapperRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const selectedRef = useRef<HTMLButtonElement>(null)
  const panelId = useId()

  const hoy = monthOf(new Date())
  const esMesActual = mes === hoy
  const [anioSel, mesSel] = [Number(mes.slice(0, 4)), Number(mes.slice(5, 7))]

  const abrir = () => { setAnioVista(anioSel); setOpen(true) }
  const cerrar = (devolverFoco = true) => {
    setOpen(false)
    if (devolverFoco) triggerRef.current?.focus()
  }
  const elegir = (nuevo: string) => { setMes(nuevo); cerrar() }

  // Al abrir: foco en el mes elegido; clic fuera o Esc cierran (solo listeners, sin setState síncrono)
  useEffect(() => {
    if (!open) return
    selectedRef.current?.focus()
    const onPointer = (e: PointerEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setOpen(false); triggerRef.current?.focus() }
    }
    document.addEventListener('pointerdown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  // Flechas dentro de la cuadrícula: izquierda/derecha ±1 mes, arriba/abajo ±3 (una fila)
  const onGridKey = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const pasos: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -3, ArrowDown: 3 }
    const paso = pasos[e.key]
    if (paso === undefined) return
    const botones = Array.from(e.currentTarget.querySelectorAll<HTMLButtonElement>('button[data-mes]'))
    const actual = botones.indexOf(document.activeElement as HTMLButtonElement)
    if (actual < 0) return
    e.preventDefault()
    botones[Math.min(11, Math.max(0, actual + paso))]?.focus()
  }

  const navBtn = 'w-10 h-10 flex items-center justify-center rounded-lg text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:hover:bg-slate-700 dark:hover:text-white transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500'

  return (
    <div
      ref={wrapperRef}
      className="relative flex items-center gap-2 w-full sm:w-auto"
      // Salir del calendario con Tab lo cierra (si el foco va a otro elemento de la página)
      onBlur={e => {
        if (open && e.relatedTarget && !wrapperRef.current?.contains(e.relatedTarget as Node)) setOpen(false)
      }}
    >
      <div className="flex flex-1 sm:flex-none items-center rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-800 p-0.5" role="group" aria-label="Período">
        <button type="button" onClick={() => setMes(shiftMonth(mes, -1))} className={navBtn}
          aria-label={`Mes anterior: ${monthTitle(shiftMonth(mes, -1))}`} title="Mes anterior">
          <IconChevron dir="left" />
        </button>

        <button
          ref={triggerRef}
          type="button"
          onClick={() => (open ? cerrar() : abrir())}
          aria-haspopup="dialog"
          aria-expanded={open}
          aria-controls={open ? panelId : undefined}
          aria-label={`Período: ${monthTitle(mes)}. Elegir otro mes`}
          className="h-10 flex-1 min-w-0 sm:flex-none sm:min-w-[10.5rem] px-2 sm:px-3 flex items-center justify-center gap-2 rounded-lg text-sm font-semibold text-slate-900 dark:text-white hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
        >
          <svg className="w-4 h-4 text-blue-600 dark:text-teal-300 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25m-18 0A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75m-18 0v-7.5A2.25 2.25 0 0 1 5.25 9h13.5A2.25 2.25 0 0 1 21 11.25v7.5" />
          </svg>
          <span className="tabular-nums whitespace-nowrap">{monthTitle(mes)}</span>
          <svg className={`w-3.5 h-3.5 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="m19.5 8.25-7.5 7.5-7.5-7.5" />
          </svg>
        </button>

        <button type="button" onClick={() => setMes(shiftMonth(mes, 1))} className={navBtn}
          aria-label={`Mes siguiente: ${monthTitle(shiftMonth(mes, 1))}`} title="Mes siguiente">
          <IconChevron dir="right" />
        </button>
      </div>

      {!esMesActual && (
        <button type="button" onClick={() => { resetMes(); triggerRef.current?.focus() }}
          className="h-10 px-2 sm:px-3 flex-shrink-0 rounded-lg text-sm font-semibold text-blue-700 hover:bg-blue-50 dark:text-teal-300 dark:hover:bg-teal-900/30 whitespace-nowrap transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          aria-label={`Volver al mes actual: ${monthTitle(hoy)}`}>
          <span className="sm:hidden">Hoy</span>
          <span className="hidden sm:inline">Mes actual</span>
        </button>
      )}

      {open && (
        <div
          id={panelId}
          role="dialog"
          aria-label="Elegir mes"
          className="absolute inset-x-0 sm:left-auto sm:right-0 top-full mt-2 z-40 sm:w-72 rounded-2xl border border-slate-200 bg-[#fff] p-3 shadow-xl dark:border-slate-700 dark:bg-slate-800 animate-fade-in"
        >
          {/* Año */}
          <div className="flex items-center justify-between mb-2">
            <button type="button" onClick={() => setAnioVista(a => Math.max(2000, a - 1))} className={navBtn}
              aria-label={`Año anterior: ${anioVista - 1}`}>
              <IconChevron dir="left" />
            </button>
            <p className="text-sm font-bold text-slate-900 dark:text-white tabular-nums" aria-live="polite">{anioVista}</p>
            <button type="button" onClick={() => setAnioVista(a => Math.min(2100, a + 1))} className={navBtn}
              aria-label={`Año siguiente: ${anioVista + 1}`}>
              <IconChevron dir="right" />
            </button>
          </div>

          {/* Meses */}
          <div className="grid grid-cols-3 gap-1.5" onKeyDown={onGridKey}>
            {MESES.map((nombre, i) => {
              const valor = `${anioVista}-${String(i + 1).padStart(2, '0')}`
              const seleccionado = anioVista === anioSel && i + 1 === mesSel
              const esHoy = valor === hoy
              return (
                <button
                  key={valor}
                  ref={seleccionado ? selectedRef : undefined}
                  type="button"
                  data-mes={valor}
                  onClick={() => elegir(valor)}
                  aria-pressed={seleccionado}
                  aria-label={`${MESES_LARGOS[i]} de ${anioVista}${esHoy ? ' (mes actual)' : ''}`}
                  className={`relative h-11 rounded-lg text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
                    seleccionado
                      ? 'bg-blue-600 text-white shadow-sm'
                      : 'text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700'
                  }`}
                >
                  {nombre}
                  {esHoy && (
                    <span aria-hidden className={`absolute bottom-1.5 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full ${seleccionado ? 'bg-[#fff]' : 'bg-blue-600 dark:bg-teal-300'}`} />
                  )}
                </button>
              )
            })}
          </div>

          <div className="flex items-center justify-between mt-3 pt-3 border-t border-slate-100 dark:border-slate-700">
            <span className="text-xs text-slate-500 dark:text-slate-400">Se aplica a todas las pestañas</span>
            <button type="button" onClick={() => { resetMes(); cerrar() }}
              className="text-sm font-semibold text-blue-700 hover:text-blue-800 dark:text-teal-300 rounded px-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
              Mes actual
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
