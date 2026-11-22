import React, { useCallback, useEffect, useState } from 'react'
import apiClient from '@/lib/api-client'
import { apiErrorMessage } from '@/components/DialogProvider'
import ErrorState from '@/components/ErrorState'
import { useCurrencyStore } from '@/store/currency'
import { comparablePrevious, monthOf, pctChange, shiftMonth, sumByTipo, upToToday, type MovimientoBase } from '@/lib/month-stats'

interface SummaryCardProps {
  title: string
  value: number
  type: 'ingreso' | 'gasto' | 'balance'
  /** Valor del mes anterior (CHG-006); `null` si no se pudo cargar. */
  previous: number | null
  previousLabel: string
  /** Valor que se compara: en el mes en curso, sin lo anotado con fecha posterior a hoy. */
  current: number
}

/** "▲ 12 % más que octubre": flecha + palabras, el color solo acompaña. */
function Comparison({ type, current: value, previous, previousLabel }: Omit<SummaryCardProps, 'title' | 'value'>) {
  const fmt = useCurrencyStore(s => s.fmt)
  if (previous === null) return <>Período actual</>
  if (type === 'balance') {
    const diff = value - previous
    if (Math.round(diff) === 0) return <>Igual que {previousLabel}</>
    return <span className={diff > 0 ? 'text-emerald-700 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}>
      {diff > 0 ? '▲' : '▼'} {fmt(Math.abs(diff))} {diff > 0 ? 'más' : 'menos'} que {previousLabel}
    </span>
  }
  const change = pctChange(value, previous)
  if (change === null) return <>Sin datos de {previousLabel} para comparar</>
  if (Math.round(change) === 0) return <>Igual que {previousLabel}</>
  const up = change > 0
  const bad = type === 'gasto' ? up : !up
  return <span className={bad ? 'text-red-600 dark:text-red-400' : 'text-emerald-700 dark:text-emerald-400'}>
    {up ? '▲' : '▼'} {Math.round(Math.abs(change)).toLocaleString('es-CO')} % {up ? 'más' : 'menos'} que {previousLabel}
  </span>
}

function SummaryCard({ title, value, type, previous, previousLabel, current }: SummaryCardProps) {
  const fmt = useCurrencyStore(s => s.fmt)
  const config = {
    ingreso: {
      gradient: 'from-emerald-500 to-teal-600',
      bg: 'bg-emerald-50',
      text: 'text-emerald-600',
      ring: 'ring-emerald-100',
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.25 18 9 11.25l4.306 4.306a11.95 11.95 0 0 1 5.814-5.519l2.74-1.22m0 0-5.94-2.281m5.94 2.28-2.28 5.941" />
        </svg>
      )
    },
    gasto: {
      gradient: 'from-red-500 to-rose-600',
      bg: 'bg-red-50',
      text: 'text-red-600',
      ring: 'ring-red-100',
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.25 6 9 12.75l4.286-4.286a11.948 11.948 0 0 1 4.306 6.43l.776 2.898m0 0 3.182-5.511m-3.182 5.51-5.511-3.181" />
        </svg>
      )
    },
    balance: {
      gradient: 'from-blue-500 to-indigo-600',
      bg: 'bg-blue-50',
      text: 'text-blue-600',
      ring: 'ring-blue-100',
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v12m-3-2.818.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
        </svg>
      )
    }
  }

  const c = config[type]
  const isNegative = type === 'balance' && value < 0

  return (
    <div className={`card overflow-hidden`}>
      <div className={`h-1 bg-gradient-to-r ${c.gradient}`} />
      <div className="p-4 sm:p-5">
        <div className="flex items-center justify-between mb-2 sm:mb-4">
          <p className="text-sm font-semibold text-slate-600">{title}</p>
          <div className={`w-9 h-9 sm:w-10 sm:h-10 rounded-xl ${c.bg} ring-1 ${c.ring} flex items-center justify-center ${c.text}`} aria-hidden>
            {c.icon}
          </div>
        </div>
        <p className={`text-2xl sm:text-3xl font-bold tracking-tight tabular-nums break-words ${isNegative ? 'text-red-600' : 'text-slate-900'}`}>
          {fmt(value)}
        </p>
        <p className="text-xs text-slate-500 mt-1"><Comparison type={type} current={current} previous={previous} previousLabel={previousLabel} /></p>
      </div>
    </div>
  )
}

export default function DashboardSummary({ mes }: { mes: string }) {
  const [summary, setSummary] = useState({ ingresos: 0, gastos: 0, balance: 0 })
  // Lo que se compara con el mes anterior: en el mes en curso, sin lo anotado con fecha posterior a hoy
  const [comparable, setComparable] = useState({ ingresos: 0, gastos: 0, balance: 0 })
  const [previous, setPrevious] = useState<{ ingresos: number; gastos: number; balance: number } | null>(null)
  const previousMonth = shiftMonth(mes, -1)
  const today = new Date()
  // En el mes en curso se compara con el mes anterior hasta el mismo día
  const previousLabel = new Date(Number(previousMonth.slice(0, 4)), Number(previousMonth.slice(5, 7)) - 1, 1)
    .toLocaleDateString('es-ES', { month: 'long' }) + (mes === monthOf(today) ? ` al día ${today.getDate()}` : '')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // Devuelve una función de cancelación: si cambia el mes antes de que llegue
  // la respuesta anterior, esa respuesta se ignora.
  const fetchSummary = useCallback(() => {
    let active = true
    // El mes anterior es solo para comparar: si falla, la tarjeta dice "Período actual".
    const anterior = apiClient.get<MovimientoBase[]>(`/api/v1/transacciones?mes=${shiftMonth(mes, -1)}`)
      .then(r => {
        const items = comparablePrevious(r.data, mes, new Date())
        const ingresos = sumByTipo(items, 'ingreso')
        const gastos = sumByTipo(items, 'gasto')
        return { ingresos, gastos, balance: ingresos - gastos }
      })
      .catch(() => null)
    const totales = (items: MovimientoBase[]) => {
      const ingresos = sumByTipo(items, 'ingreso')
      const gastos = sumByTipo(items, 'gasto')
      return { ingresos, gastos, balance: ingresos - gastos }
    }
    Promise.all([apiClient.get<MovimientoBase[]>(`/api/v1/transacciones?mes=${mes}`), anterior])
      .then(([response, prev]) => {
        if (!active) return
        setSummary(totales(response.data))
        setComparable(totales(upToToday(response.data, mes, new Date())))
        setPrevious(prev)
        setError('')
      })
      .catch(err => {
        if (active) setError(apiErrorMessage(err, 'No se pudo cargar el resumen del mes.'))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [mes])

  useEffect(() => fetchSummary(), [fetchSummary])

  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 sm:gap-4">
        {[1, 2, 3].map(i => (
          <div key={i} className="card h-28 sm:h-36 animate-pulse bg-slate-100" />
        ))}
      </div>
    )
  }

  if (error) {
    return <ErrorState message={error} onRetry={() => { setLoading(true); fetchSummary() }} />
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3 sm:gap-4">
      <SummaryCard title="Ingresos" value={summary.ingresos} type="ingreso" previous={previous?.ingresos ?? null} previousLabel={previousLabel} current={comparable.ingresos} />
      <SummaryCard title="Gastos" value={summary.gastos} type="gasto" previous={previous?.gastos ?? null} previousLabel={previousLabel} current={comparable.gastos} />
      <SummaryCard title="Balance" value={summary.balance} type="balance" previous={previous?.balance ?? null} previousLabel={previousLabel} current={comparable.balance} />
    </div>
  )
}
