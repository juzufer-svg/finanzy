'use client'

import React, { useCallback, useEffect, useState } from 'react'
import apiClient, { hasStoredSession } from '@/lib/api-client'
import { useRouter } from 'next/navigation'
import { useCurrencyStore } from '@/store/currency'
import ErrorState from '@/components/ErrorState'
import SpendingChart from '@/components/SpendingChart'
import { apiErrorMessage } from '@/components/DialogProvider'
import {
  type CategoriaBase, type MovimientoBase, type PresupuestoBase,
  comparablePrevious, compareByCategory, cumulativeByDay, dailyAverage, daysInMonth, elapsedDays, monthOf, pctChange,
  projectMonthEnd, shiftMonth, sumByTipo, totalBudget, totalsByPaymentMethod, upToToday,
} from '@/lib/month-stats'
import { medioPagoLabel } from '@/lib/payment-methods'

interface Datos {
  actuales: MovimientoBase[]
  anteriores: MovimientoBase[]
  categorias: (CategoriaBase & { icono?: string })[]
  presupuestos: PresupuestoBase[]
}

const VACIO: Datos = { actuales: [], anteriores: [], categorias: [], presupuestos: [] }

const nombreMes = (mes: string, conAnio = true) =>
  new Date(Number(mes.slice(0, 4)), Number(mes.slice(5, 7)) - 1, 1)
    .toLocaleDateString('es-ES', conAnio ? { month: 'long', year: 'numeric' } : { month: 'long' })

const mayuscula = (t: string) => t.charAt(0).toUpperCase() + t.slice(1)

const pct = (n: number) => `${Math.round(Math.abs(n)).toLocaleString('es-CO')} %`

/** Texto de variación con flecha y palabra (nunca solo color). `subirEsMalo` para gastos. */
function Variacion({ valor, contra, subirEsMalo }: { valor: number | null; contra: string; subirEsMalo: boolean }) {
  if (valor === null) return <span className="text-slate-500">Sin datos de {contra} para comparar</span>
  if (Math.round(valor) === 0) return <span className="text-slate-500">Igual que {contra}</span>
  const sube = valor > 0
  const malo = sube === subirEsMalo
  return (
    <span className={malo ? 'text-red-600 dark:text-red-400' : 'text-emerald-700 dark:text-emerald-400'}>
      {sube ? '▲' : '▼'} {pct(valor)} {sube ? 'más' : 'menos'} que {contra}
    </span>
  )
}

export default function ReportsPage() {
  const router = useRouter()
  const fmt = useCurrencyStore(s => s.fmt)
  const [datos, setDatos] = useState<Datos>(VACIO)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [currentMonth, setCurrentMonth] = useState(() => monthOf(new Date()))
  const mesAnterior = shiftMonth(currentMonth, -1)

  // isActive permite ignorar respuestas que llegan tarde (cambio de mes o vista cerrada)
  const fetchData = useCallback((isActive: () => boolean = () => true) => {
    return Promise.all([
      apiClient.get(`/api/v1/transacciones?mes=${currentMonth}`),
      apiClient.get(`/api/v1/transacciones?mes=${shiftMonth(currentMonth, -1)}`),
      apiClient.get('/api/v1/categorias'),
      apiClient.get(`/api/v1/presupuestos/${currentMonth}`),
    ])
      .then(([actRes, antRes, catRes, presRes]) => {
        if (!isActive()) return
        setDatos({ actuales: actRes.data, anteriores: antRes.data, categorias: catRes.data, presupuestos: presRes.data })
        setLoadError('')
      })
      .catch(err => {
        if (isActive()) setLoadError(apiErrorMessage(err, 'No se pudieron cargar tus reportes.'))
      })
      .finally(() => {
        if (isActive()) setLoading(false)
      })
  }, [currentMonth])

  useEffect(() => {
    if (!hasStoredSession()) { router.push('/auth/login'); return }
    let active = true
    fetchData(() => active)
    return () => { active = false }
  }, [fetchData, router])

  const cambiarMes = (delta: number) => { setLoading(true); setCurrentMonth(m => shiftMonth(m, delta)) }

  // ---- Cálculos (CHG-006) ----
  const hoy = new Date()
  const { actuales, anteriores, categorias, presupuestos } = datos
  const ingresos = sumByTipo(actuales, 'ingreso')
  const gastos = sumByTipo(actuales, 'gasto')
  // En el mes en curso se compara con el mes anterior hasta el mismo día (no con el mes completo)
  const comparables = comparablePrevious(anteriores, currentMonth, hoy)
  // Lo anotado con fecha posterior a hoy no cuenta para el promedio, la proyección ni la comparación
  const ocurridos = upToToday(actuales, currentMonth, hoy)
  const gastosHoy = sumByTipo(ocurridos, 'gasto')
  const programados = gastos - gastosHoy
  const gastosAnt = sumByTipo(comparables, 'gasto')
  const ingresosAnt = sumByTipo(comparables, 'ingreso')
  const balance = ingresos - gastos
  const dias = daysInMonth(currentMonth)
  const transcurridos = elapsedDays(currentMonth, hoy)
  const promedio = dailyAverage(gastosHoy, currentMonth, hoy)
  const proyeccionRitmo = projectMonthEnd(gastosHoy, currentMonth, hoy)
  // Nunca por debajo de lo ya anotado para este mes (incluye lo programado)
  const proyeccion = proyeccionRitmo === null ? null : Math.max(proyeccionRitmo, gastos)
  const presupuesto = totalBudget(presupuestos, categorias)
  const esMesActual = currentMonth === monthOf(hoy)
  const anteriorCorto = nombreMes(mesAnterior, false) + (currentMonth === monthOf(hoy) ? ` al día ${hoy.getDate()}` : '')
  const actualCorto = nombreMes(currentMonth, false)
  const nombreCat = (id: string) => categorias.find(c => c.id === id)?.nombre || 'Sin categoría'
  const iconoCat = (id: string) => categorias.find(c => c.id === id)?.icono || '📁'
  const comparacion = compareByCategory(ocurridos, comparables, 'gasto')
  const ahorro = ingresos > 0 ? (balance / ingresos) * 100 : null
  const variacionTotal = pctChange(gastosHoy, gastosAnt)
  const porMedio = totalsByPaymentMethod(actuales, 'gasto')
  const maxMedio = porMedio[0]?.total || 1

  // Frase principal: la conclusión primero
  let titular = `Aún no hay gastos en ${actualCorto}.`
  if (gastos > 0) {
    if (presupuesto > 0 && gastos > presupuesto) titular = `Te pasaste del presupuesto de ${actualCorto} por ${fmt(gastos - presupuesto)}.`
    else if (proyeccion !== null && presupuesto > 0 && proyeccion > presupuesto) titular = `Al ritmo actual cerrarías ${actualCorto} en ${fmt(proyeccion)}: ${fmt(proyeccion - presupuesto)} por encima del presupuesto.`
    else if (presupuesto > 0) titular = `Llevas ${fmt(gastos)} gastados en ${actualCorto}: el ${pct((gastos / presupuesto) * 100)} del presupuesto.`
    else titular = `Llevas ${fmt(gastos)} gastados en ${actualCorto}.`
  }
  const top = comparacion.find(f => f.actual > 0)
  const subtitular = top && gastos > 0
    ? `${nombreCat(top.categoriaId)} se lleva el ${pct((top.actual / gastos) * 100)} del gasto.`
    : ''

  const tarjetas: { titulo: string; valor: string; detalle: React.ReactNode; borde: string }[] = [
    { titulo: 'Ingresos', valor: fmt(ingresos), borde: 'border-emerald-400',
      detalle: <Variacion valor={pctChange(sumByTipo(ocurridos, 'ingreso'), ingresosAnt)} contra={anteriorCorto} subirEsMalo={false} /> },
    { titulo: 'Gastos', valor: fmt(gastos), borde: 'border-red-400',
      detalle: <>
        <Variacion valor={variacionTotal} contra={anteriorCorto} subirEsMalo />
        {programados > 0 && <span className="block text-slate-500">Incluye {fmt(programados)} con fecha posterior a hoy</span>}
      </> },
    { titulo: 'Balance', valor: fmt(balance), borde: balance >= 0 ? 'border-blue-400' : 'border-orange-400',
      detalle: <span className="text-slate-500">{ahorro === null ? 'Sin ingresos registrados' : ahorro >= 0 ? `Ahorras el ${pct(ahorro)} de lo que ganaste` : 'Gastas más de lo que ganas'}</span> },
    { titulo: 'Gasto diario promedio', valor: promedio === null ? '—' : fmt(promedio), borde: 'border-violet-400',
      detalle: <span className="text-slate-500">{transcurridos === 0 ? 'El mes no ha empezado' : esMesActual ? `En ${transcurridos} de ${dias} días` : `Mes completo (${dias} días)`}</span> },
    esMesActual
      ? { titulo: 'Proyección al cierre', valor: proyeccion === null ? '—' : fmt(proyeccion), borde: 'border-amber-400',
          detalle: presupuesto > 0 && proyeccion !== null
            ? (proyeccion > presupuesto
                ? <span className="text-red-600 dark:text-red-400">⚠ Superaría el presupuesto por {fmt(proyeccion - presupuesto)}</span>
                : <span className="text-emerald-700 dark:text-emerald-400">✓ Dentro del presupuesto ({fmt(presupuesto)})</span>)
            : <span className="text-slate-500">Al ritmo de gasto actual</span> }
      : { titulo: 'Presupuesto usado', valor: presupuesto > 0 ? pct((gastos / presupuesto) * 100) : '—', borde: 'border-amber-400',
          detalle: presupuesto > 0
            ? (gastos > presupuesto
                ? <span className="text-red-600 dark:text-red-400">⚠ Excedido por {fmt(gastos - presupuesto)}</span>
                : <span className="text-slate-500">Sobraron {fmt(presupuesto - gastos)}</span>)
            : <span className="text-slate-500">Sin presupuestos este mes</span> },
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="page-header mb-0">
          <h1 className="page-title">Reportes y Análisis</h1>
          <p className="page-subtitle capitalize">{nombreMes(currentMonth)}</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => cambiarMes(-1)} className="btn-secondary" aria-label="Mes anterior">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.75 19.5 8.25 12l7.5-7.5" />
            </svg>
            <span className="hidden sm:inline">Anterior</span>
          </button>
          <button onClick={() => cambiarMes(1)} className="btn-primary" aria-label="Mes siguiente">
            <span className="hidden sm:inline">Siguiente</span>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="m8.25 4.5 7.5 7.5-7.5 7.5" />
            </svg>
          </button>
        </div>
      </div>

      {loadError ? (
        <ErrorState message={loadError} onRetry={() => { setLoading(true); fetchData() }} />
      ) : loading ? (
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
          {[1, 2, 3, 4, 5].map(i => <div key={i} className="card h-24 animate-pulse bg-slate-100" />)}
        </div>
      ) : (
        <>
          {/* Conclusión del mes */}
          <div className="card p-5">
            <p className="text-lg sm:text-xl font-bold text-slate-900">{titular}</p>
            {subtitular && <p className="text-sm text-slate-500 mt-1">{subtitular}</p>}
          </div>

          {/* Indicadores */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
            {tarjetas.map(t => (
              <div key={t.titulo} className={`card p-4 border-l-4 ${t.borde} min-w-0`}>
                <p className="text-xs text-slate-500 font-medium">{t.titulo}</p>
                <p className="text-xl font-bold text-slate-900 mt-1 truncate">{t.valor}</p>
                <p className="text-xs mt-1">{t.detalle}</p>
              </div>
            ))}
          </div>

          {/* Gráfico */}
          <div className="card p-5">
            <h2 className="text-sm font-bold text-slate-900 mb-3">Gasto acumulado día a día</h2>
            {gastos === 0 && sumByTipo(anteriores, 'gasto') === 0 ? (
              <p className="text-sm text-slate-500 py-8 text-center">Registra gastos para ver cómo avanza tu mes.</p>
            ) : (
              <SpendingChart
                actual={cumulativeByDay(actuales, currentMonth, 'gasto', transcurridos)}
                anterior={cumulativeByDay(anteriores, mesAnterior, 'gasto')}
                dias={dias}
                presupuesto={presupuesto}
                etiquetaActual={nombreMes(currentMonth)}
                etiquetaAnterior={nombreMes(mesAnterior)}
              />
            )}
          </div>

          {/* Gasto por medio de pago (CHG-007) */}
          {porMedio.length > 0 && (
            <div className="card p-5">
              <h2 className="text-sm font-bold text-slate-900 mb-3">Gastos por medio de pago</h2>
              <ul className="space-y-2.5">
                {porMedio.map(m => (
                  <li key={m.medio || 'sin'} className="grid grid-cols-[8.5rem_minmax(0,1fr)_auto] sm:grid-cols-[10rem_minmax(0,1fr)_7.5rem_3rem] items-center gap-3 text-sm">
                    <span className="text-slate-800 truncate">{medioPagoLabel(m.medio)}</span>
                    <span className="h-3 rounded-r bg-slate-100 dark:bg-slate-700" aria-hidden>
                      <span className="block h-full rounded-r bg-blue-600 dark:bg-blue-500" style={{ width: `${Math.max((m.total / maxMedio) * 100, 1)}%` }} />
                    </span>
                    <span className="text-right tabular-nums font-semibold text-slate-900 whitespace-nowrap">{fmt(m.total)}</span>
                    <span className="hidden sm:block text-right tabular-nums text-xs text-slate-500">{gastos > 0 ? pct((m.total / gastos) * 100) : ''}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Comparación por categoría */}
          <div className="card p-5">
            <h2 className="text-sm font-bold text-slate-900 mb-3">Gastos por categoría: {actualCorto} vs {anteriorCorto}</h2>
            {comparacion.length === 0 ? (
              <p className="text-sm text-slate-500">No hay gastos en estos dos meses.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-slate-500 border-b border-slate-200 dark:border-slate-700">
                      <th scope="col" className="py-2 pr-2 font-medium">Categoría</th>
                      <th scope="col" className="py-2 px-2 font-medium text-right">{mayuscula(actualCorto)}</th>
                      <th scope="col" className="py-2 px-2 font-medium text-right">{mayuscula(anteriorCorto)}</th>
                      <th scope="col" className="py-2 pl-2 font-medium text-right">Variación</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comparacion.map(f => {
                      const sube = f.variacion !== null && Math.round(f.variacion) > 0
                      const baja = f.variacion !== null && Math.round(f.variacion) < 0
                      return (
                        <tr key={f.categoriaId || 'sin'} className="border-b border-slate-100 dark:border-slate-700/60 last:border-0">
                          <td className="py-2 pr-2 text-slate-800"><span aria-hidden className="mr-1.5">{iconoCat(f.categoriaId)}</span>{nombreCat(f.categoriaId)}</td>
                          <td className="py-2 px-2 text-right tabular-nums font-semibold text-slate-900 whitespace-nowrap">{fmt(f.actual)}</td>
                          <td className="py-2 px-2 text-right tabular-nums text-slate-500 whitespace-nowrap">{fmt(f.anterior)}</td>
                          <td className={`py-2 pl-2 text-right tabular-nums whitespace-nowrap ${sube ? 'text-red-600 dark:text-red-400' : baja ? 'text-emerald-700 dark:text-emerald-400' : 'text-slate-500'}`}>
                            {f.variacion === null ? (f.actual > 0 ? 'Nueva' : '—') : sube ? `▲ ${pct(f.variacion)}` : baja ? `▼ ${pct(f.variacion)}` : 'Igual'}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                  <tfoot>
                    <tr className="border-t border-slate-200 dark:border-slate-700 font-semibold">
                      <td className="py-2 pr-2 text-slate-900">Total</td>
                      <td className="py-2 px-2 text-right tabular-nums text-slate-900 whitespace-nowrap">{fmt(gastos)}</td>
                      <td className="py-2 px-2 text-right tabular-nums text-slate-500 whitespace-nowrap">{fmt(gastosAnt)}</td>
                      <td className="py-2 pl-2 text-right tabular-nums text-slate-700 whitespace-nowrap">
                        {variacionTotal === null ? '—' : `${variacionTotal > 0 ? '▲' : '▼'} ${pct(variacionTotal)}`}
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
