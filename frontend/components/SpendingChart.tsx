'use client'

import React, { useEffect, useRef, useState } from 'react'
import { useCurrencyStore } from '@/store/currency'

// Gráfico del gasto acumulado día a día (CHG-006). SVG propio, sin librerías.
// Serie del mes (azul), mes anterior (gris, de contexto) y línea punteada del presupuesto total.
// Colores validados con el verificador de paletas (contraste ≥ 3:1 en claro y oscuro).

interface SpendingChartProps {
  /** Acumulado del mes elegido, hasta hoy si es el mes en curso. */
  actual: number[]
  /** Acumulado completo del mes anterior. */
  anterior: number[]
  /** Días del mes elegido (eje X). */
  dias: number
  /** Suma de presupuestos de gasto del mes; 0 si no hay. */
  presupuesto: number
  etiquetaActual: string
  etiquetaAnterior: string
}

const ALTO = 260

function pasoRedondo(bruto: number): number {
  const base = Math.pow(10, Math.floor(Math.log10(Math.max(bruto, 1))))
  const f = bruto / base
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * base
}
const M = { top: 16, right: 16, bottom: 28, left: 64 }

export default function SpendingChart({ actual, anterior, dias, presupuesto, etiquetaActual, etiquetaAnterior }: SpendingChartProps) {
  const fmt = useCurrencyStore(s => s.fmt)
  const convert = useCurrencyStore(s => s.convert)
  const contenedor = useRef<HTMLDivElement>(null)
  const [ancho, setAncho] = useState(640)
  const [dia, setDia] = useState<number | null>(null)

  useEffect(() => {
    const el = contenedor.current
    if (!el) return
    const ro = new ResizeObserver(entries => {
      const w = Math.round(entries[0].contentRect.width)
      if (w > 0) setAncho(w)
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const estrecho = ancho < 480
  const left = estrecho ? 48 : M.left
  // Eje Y con pasos "redondos" (1, 2, 2,5 o 5 × 10ⁿ) para que las etiquetas se lean bien
  const maxDato = Math.max(presupuesto, ...actual, ...anterior.slice(0, dias), 1)
  const paso = pasoRedondo(maxDato / 4)
  const maxY = Math.max(Math.ceil((maxDato * 1.05) / paso) * paso, paso)
  const x = (d: number) => left + ((d - 1) / Math.max(dias - 1, 1)) * (ancho - left - M.right)
  const y = (v: number) => M.top + (1 - v / maxY) * (ALTO - M.top - M.bottom)
  const linea = (serie: number[]) => serie.map((v, i) => `${i ? 'L' : 'M'}${x(i + 1).toFixed(1)},${y(v).toFixed(1)}`).join('')

  // Montos compactos en la moneda elegida para el eje Y (p. ej. "$1,5 M", "$250 mil")
  const simbolo = fmt(0).replace(/[\d.,\s]/g, '') || '$'
  const compacto = (v: number) => {
    const c = convert(v)
    if (Math.abs(c) >= 999_500) return `${simbolo}${(c / 1e6).toLocaleString('es-CO', { maximumFractionDigits: 1 })} M`
    if (Math.abs(c) >= 1e3) return `${simbolo}${Math.round(c / 1e3).toLocaleString('es-CO')} mil`
    return `${simbolo}${Math.round(c)}`
  }

  const marcasY: number[] = []
  for (let v = 0; v <= maxY + paso / 2; v += paso) marcasY.push(v)
  const pasoX = estrecho ? 7 : 5
  const marcasX: number[] = []
  for (let d = 1; d <= dias; d += pasoX) marcasX.push(d)

  const anteriorVisible = anterior.slice(0, dias)
  const ultimo = actual.length
  const diaActivo = dia !== null ? Math.min(Math.max(dia, 1), dias) : null

  const mover = (clientX: number) => {
    const el = contenedor.current
    if (!el) return
    const px = clientX - el.getBoundingClientRect().left
    const d = Math.round(((px - left) / Math.max(ancho - left - M.right, 1)) * (dias - 1)) + 1
    setDia(Math.min(Math.max(d, 1), dias))
  }

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowRight') { e.preventDefault(); setDia(d => Math.min((d ?? 0) + 1, dias)) }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); setDia(d => Math.max((d ?? 2) - 1, 1)) }
    else if (e.key === 'Escape') setDia(null)
  }

  const valorDia = (serie: number[], d: number) => (d <= serie.length ? serie[d - 1] : null)
  // El recuadro va al lado contrario del cursor para no tapar la línea que se está leyendo
  const tooltipIzq = diaActivo
    ? Math.min(Math.max(x(diaActivo) > ancho / 2 ? x(diaActivo) - 192 : x(diaActivo) + 12, 0), ancho - 190)
    : 0

  return (
    <div>
      {/* Leyenda: la identidad nunca depende solo del color */}
      <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-600 mb-2">
        <span className="inline-flex items-center gap-1.5"><span aria-hidden className="inline-block w-4 border-t-2 border-blue-600 dark:border-blue-500" />{etiquetaActual}</span>
        {anterior.some(v => v > 0) && (
          <span className="inline-flex items-center gap-1.5"><span aria-hidden className="inline-block w-4 border-t-2 border-slate-500" />{etiquetaAnterior}</span>
        )}
        {presupuesto > 0 && (
          <span className="inline-flex items-center gap-1.5"><span aria-hidden className="inline-block w-4 border-t-2 border-dashed border-slate-700 dark:border-slate-300" />Presupuesto</span>
        )}
      </div>

      <div
        ref={contenedor}
        className="relative w-full select-none rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
        style={{ height: ALTO }}
        tabIndex={0}
        role="img"
        aria-label={`Gasto acumulado día a día de ${etiquetaActual}${ultimo ? `: ${fmt(actual[ultimo - 1])} al día ${ultimo}` : ''}${presupuesto > 0 ? `, presupuesto ${fmt(presupuesto)}` : ''}. Usa las flechas para recorrer los días.`}
        onPointerMove={e => mover(e.clientX)}
        onPointerLeave={() => setDia(null)}
        onKeyDown={onKey}
        onBlur={() => setDia(null)}
      >
        <svg width={ancho} height={ALTO} className="absolute inset-0 overflow-visible" aria-hidden>
          {marcasY.map(v => (
            <g key={v}>
              <line x1={left} x2={ancho - M.right} y1={y(v)} y2={y(v)} className="stroke-slate-200 dark:stroke-slate-700" strokeWidth={1} />
              <text x={left - 8} y={y(v) + 4} textAnchor="end" fontSize={11} className="fill-slate-500 dark:fill-slate-400">{compacto(v)}</text>
            </g>
          ))}
          {marcasX.map(d => (
            <text key={d} x={x(d)} y={ALTO - 8} textAnchor="middle" fontSize={11} className="fill-slate-500 dark:fill-slate-400">{d}</text>
          ))}

          {presupuesto > 0 && (
            <g>
              <line x1={left} x2={ancho - M.right} y1={y(presupuesto)} y2={y(presupuesto)} strokeDasharray="6 5" strokeWidth={1.5} className="stroke-slate-700 dark:stroke-slate-300" />
              <text x={ancho - M.right} y={y(presupuesto) - 6} textAnchor="end" fontSize={11} className="fill-slate-700 dark:fill-slate-300">Presupuesto {compacto(presupuesto)}</text>
            </g>
          )}

          {anteriorVisible.some(v => v > 0) && (
            <path d={linea(anteriorVisible)} fill="none" strokeWidth={2} strokeLinejoin="round" className="stroke-slate-500" />
          )}

          {ultimo > 0 && (
            <>
              <path d={linea(actual)} fill="none" strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" className="stroke-blue-600 dark:stroke-blue-500" />
              <circle cx={x(ultimo)} cy={y(actual[ultimo - 1])} r={5} strokeWidth={2} className="fill-blue-600 dark:fill-blue-500 stroke-white dark:stroke-slate-800" />
            </>
          )}

          {diaActivo !== null && (
            <line x1={x(diaActivo)} x2={x(diaActivo)} y1={M.top} y2={ALTO - M.bottom} strokeWidth={1} className="stroke-slate-400" />
          )}
        </svg>

        {diaActivo !== null && (
          <div
            className="absolute top-2 z-10 pointer-events-none rounded-lg border border-slate-200 bg-[#fff] dark:bg-slate-900 dark:border-slate-700 px-3 py-2 text-xs shadow-lg w-[180px]"
            style={{ left: tooltipIzq }}
            aria-live="polite"
          >
            <p className="font-semibold text-slate-900">Día {diaActivo}</p>
            {valorDia(actual, diaActivo) !== null ? (
              <p className="text-slate-700">Acumulado: <span className="font-semibold">{fmt(valorDia(actual, diaActivo) as number)}</span></p>
            ) : (
              <p className="text-slate-500">Aún no llega este día</p>
            )}
            {valorDia(actual, diaActivo) !== null && (
              <p className="text-slate-500">
                Ese día: {fmt((valorDia(actual, diaActivo) as number) - (diaActivo > 1 ? (valorDia(actual, diaActivo - 1) as number) : 0))}
              </p>
            )}
            {anteriorVisible.some(v => v > 0) && valorDia(anteriorVisible, diaActivo) !== null && (
              <p className="text-slate-500">{etiquetaAnterior}: {fmt(valorDia(anteriorVisible, diaActivo) as number)}</p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
