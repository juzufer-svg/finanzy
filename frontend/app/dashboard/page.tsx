'use client'

/**
 * Inicio (antes "Dashboard"; CHG-012, B1): resumen del mes con lo que pide atención primero.
 * - Recurrentes pendientes por confirmar (A1).
 * - Avisos de presupuestos al 75 % o excedidos (A6).
 * - Gasto por categoría, avance de las metas y últimas transacciones.
 */
import React, { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import apiClient, { hasStoredSession } from '@/lib/api-client'
import DashboardSummary from '@/components/DashboardSummary'
import TransactionList from '@/components/TransactionList'
import ErrorState from '@/components/ErrorState'
import EmptyState from '@/components/EmptyState'
import PendingRecurring from '@/components/PendingRecurring'
import { apiErrorMessage } from '@/components/DialogProvider'
import PageHeader from '@/components/PageHeader'
import PeriodPicker from '@/components/PeriodPicker'
import { usePeriodStore } from '@/store/period'
import { useCurrencyStore } from '@/store/currency'
import { budgetAlerts, topSpending, type MovimientoBase } from '@/lib/month-stats'

interface Category { id: string; nombre: string; tipo: string; icono?: string }
interface Budget { id: string; categoria_id: string; limite_mensual: number }
interface Goal { id: string; nombre: string; monto_objetivo: number; monto_actual: number; porcentaje_completado?: number | null }

function SectionHeader({ id, title, subtitle, href, linkLabel }: { id: string; title: string; subtitle?: string; href?: string; linkLabel?: string }) {
  return (
    <div className="flex items-start justify-between gap-3 mb-4">
      <div className="min-w-0">
        <h2 id={id} className="text-base font-bold text-slate-900">{title}</h2>
        {subtitle && <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>}
      </div>
      {href && (
        <Link href={href} className="text-xs font-semibold text-blue-600 hover:underline flex-shrink-0 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
          {linkLabel ?? 'Ver todo'}
        </Link>
      )}
    </div>
  )
}

export default function Inicio() {
  const router = useRouter()
  const fmt = useCurrencyStore(s => s.fmt)
  const [loading, setLoading] = useState(true)
  // Período compartido por todas las vistas (CHG-009)
  const currentMonth = usePeriodStore(s => s.mes)
  // Mes de los datos en pantalla: si no coincide con el período, se está cargando el nuevo
  const [loadedMonth, setLoadedMonth] = useState<string | null>(null)
  const stale = loadedMonth !== null && loadedMonth !== currentMonth
  const [transactions, setTransactions] = useState<MovimientoBase[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [budgets, setBudgets] = useState<Budget[]>([])
  const [goals, setGoals] = useState<Goal[]>([])
  const [loadError, setLoadError] = useState('')
  // Sube al registrar una recurrente pendiente: recarga las tarjetas de resumen
  const [refreshKey, setRefreshKey] = useState(0)

  // isActive permite ignorar respuestas que llegan tarde (cambio de mes o vista cerrada)
  const fetchData = useCallback((isActive: () => boolean = () => true) => {
    return Promise.all([
      apiClient.get(`/api/v1/transacciones?mes=${currentMonth}`),
      apiClient.get('/api/v1/categorias'),
      apiClient.get(`/api/v1/presupuestos/${currentMonth}`),
      apiClient.get('/api/v1/metas'),
    ])
      .then(([transRes, catRes, budRes, goalRes]) => {
        if (!isActive()) return
        setTransactions(transRes.data)
        setCategories(catRes.data)
        setBudgets(budRes.data)
        setGoals(goalRes.data)
        setLoadError('')
      })
      .catch(err => {
        if (isActive()) setLoadError(apiErrorMessage(err, 'No se pudieron cargar tus datos.'))
      })
      .finally(() => {
        if (isActive()) { setLoading(false); setLoadedMonth(currentMonth) }
      })
  }, [currentMonth])

  useEffect(() => {
    if (!hasStoredSession()) { router.push('/auth/login'); return }
    let active = true
    fetchData(() => active)
    return () => { active = false }
  }, [fetchData, router])

  const header = (
    <PageHeader wideActions title="Inicio" subtitle="Tu resumen del período" actions={<PeriodPicker />} />
  )

  if (loading) {
    return (
      <div className="space-y-6">
        {header}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 sm:gap-4">
          {[1, 2, 3].map(i => <div key={i} className="card h-28 sm:h-36 animate-pulse bg-slate-100" />)}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {[1, 2].map(i => <div key={i} className="card h-56 animate-pulse bg-slate-100" />)}
        </div>
      </div>
    )
  }

  if (loadError) {
    return (
      <div className="space-y-6">
        {header}
        <ErrorState message={loadError} onRetry={() => { setLoading(true); fetchData() }} />
      </div>
    )
  }

  const alerts = budgetAlerts(budgets, transactions, categories)
  const top = topSpending(transactions, categories, 5)
  const maxTop = Math.max(...top.map(t => t.total), 1)
  const totalGasto = top.reduce((s, t) => s + t.total, 0)
  const activeGoals = goals
    .filter(g => Number(g.monto_actual) < Number(g.monto_objetivo))
    .sort((a, b) => (b.porcentaje_completado ?? 0) - (a.porcentaje_completado ?? 0))
    .slice(0, 3)
  const completedGoals = goals.length - goals.filter(g => Number(g.monto_actual) < Number(g.monto_objetivo)).length
  const iconOf = (nombre: string) => categories.find(c => c.nombre === nombre)?.icono

  return (
    <div className="space-y-6">
      {header}

      {/* Recurrentes que ya llegaron a su fecha (no ocupa espacio si no hay) */}
      <PendingRecurring hideWhenEmpty onChanged={() => { fetchData(); setRefreshKey(k => k + 1) }} />

      {/* Avisos de presupuesto (A6) */}
      {alerts.length > 0 && !stale && (
        <section className="card p-4 sm:p-5 border-l-4 border-red-400" aria-labelledby="alertas-titulo">
          <SectionHeader id="alertas-titulo" title="Presupuestos que necesitan atención" href="/dashboard/budgets" linkLabel="Ver presupuestos" />
          <ul className="space-y-3">
            {alerts.map(a => {
              const excedido = a.estado === 'excedido'
              return (
                <li key={a.categoria_id}>
                  <div className="flex items-center justify-between gap-3 text-sm">
                    <span className="font-semibold text-slate-800 truncate">
                      {iconOf(a.nombre) && <span aria-hidden className="mr-1">{iconOf(a.nombre)}</span>}{a.nombre}
                    </span>
                    <span className={`text-xs font-bold whitespace-nowrap ${excedido ? 'text-red-600 dark:text-red-400' : 'text-amber-700 dark:text-amber-400'}`}>
                      {excedido ? `Excedido · ${Math.round(a.porcentaje)} %` : `Cerca del límite · ${Math.round(a.porcentaje)} %`}
                    </span>
                  </div>
                  <div className="mt-1.5 w-full bg-slate-100 rounded-full h-2 overflow-hidden" role="progressbar"
                    aria-label={`Uso del presupuesto de ${a.nombre}`} aria-valuenow={Math.round(Math.min(a.porcentaje, 100))} aria-valuemin={0} aria-valuemax={100}>
                    <div className={`h-2 rounded-full ${excedido ? 'bg-red-500' : 'bg-amber-500'}`} style={{ width: `${Math.min(a.porcentaje, 100)}%` }} />
                  </div>
                  <p className="text-xs text-slate-500 mt-1 tabular-nums">
                    {fmt(a.gastado)} de {fmt(a.limite)}{excedido ? ` · ${fmt(a.gastado - a.limite)} por encima` : ` · quedan ${fmt(a.limite - a.gastado)}`}
                  </p>
                </li>
              )
            })}
          </ul>
        </section>
      )}

      {/* Tarjetas de ingresos, gastos y balance */}
      <DashboardSummary key={refreshKey} mes={currentMonth} />

      <div className={`grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6 transition-opacity ${stale ? 'opacity-50' : ''}`} aria-busy={stale}>
        {/* Gasto por categoría */}
        <section className="card p-4 sm:p-6" aria-labelledby="gasto-cat-titulo">
          <SectionHeader id="gasto-cat-titulo" title="En qué gastaste" subtitle="Categorías con más gasto del período" href="/dashboard/reports" linkLabel="Ver reportes" />
          {top.length === 0 ? (
            <EmptyState compact title="Sin gastos en este período" description="Cuando registres gastos verás aquí en qué se va tu dinero." actionLabel="Registrar un gasto" actionHref="/dashboard/transactions?nueva=1" />
          ) : (
            <ul className="space-y-3">
              {top.map(t => (
                <li key={t.nombre}>
                  <div className="flex items-center justify-between gap-3 text-sm">
                    <span className="text-slate-700 truncate">
                      {iconOf(t.nombre) && <span aria-hidden className="mr-1">{iconOf(t.nombre)}</span>}{t.nombre}
                    </span>
                    <span className="font-semibold text-slate-900 tabular-nums whitespace-nowrap">
                      {fmt(t.total)} <span className="text-xs font-normal text-slate-500">· {Math.round((t.total / totalGasto) * 100)} %</span>
                    </span>
                  </div>
                  <div className="mt-1.5 w-full bg-slate-100 rounded-full h-2 overflow-hidden" aria-hidden>
                    <div className="h-2 rounded-full bg-gradient-to-r from-blue-500 to-indigo-500" style={{ width: `${(t.total / maxTop) * 100}%` }} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Metas */}
        <section className="card p-4 sm:p-6" aria-labelledby="metas-titulo">
          <SectionHeader
            id="metas-titulo"
            title="Tus metas"
            subtitle={completedGoals > 0 ? `${completedGoals} ${completedGoals === 1 ? 'meta cumplida' : 'metas cumplidas'} 🎉` : 'Avance de tus metas de ahorro'}
            href="/dashboard/goals"
            linkLabel="Ver metas"
          />
          {activeGoals.length === 0 ? (
            <EmptyState compact
              title={goals.length === 0 ? 'Aún no tienes metas' : '¡Cumpliste todas tus metas!'}
              description={goals.length === 0 ? 'Ponle nombre y monto a algo que quieras lograr y sigue tu avance.' : 'Crea una nueva para seguir ahorrando.'}
              actionLabel="Crear una meta" actionHref="/dashboard/goals" />
          ) : (
            <ul className="space-y-4">
              {activeGoals.map(g => {
                const pct = Math.min(g.porcentaje_completado ?? (Number(g.monto_actual) / Number(g.monto_objetivo)) * 100, 100)
                return (
                  <li key={g.id}>
                    <div className="flex items-center justify-between gap-3 text-sm">
                      <span className="font-semibold text-slate-800 truncate">{g.nombre}</span>
                      <span className="text-xs font-bold text-violet-700 dark:text-violet-300 tabular-nums">{Math.round(pct)} %</span>
                    </div>
                    <div className="mt-1.5 w-full bg-slate-100 rounded-full h-2 overflow-hidden" role="progressbar"
                      aria-label={`Avance de la meta ${g.nombre}`} aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
                      <div className="h-2 rounded-full bg-gradient-to-r from-violet-500 to-fuchsia-500" style={{ width: `${pct}%` }} />
                    </div>
                    <p className="text-xs text-slate-500 mt-1 tabular-nums">{fmt(g.monto_actual)} de {fmt(g.monto_objetivo)}</p>
                  </li>
                )
              })}
            </ul>
          )}
        </section>
      </div>

      {/* Últimas transacciones */}
      <section className="card p-4 sm:p-6" aria-labelledby="recientes-titulo">
        <SectionHeader id="recientes-titulo" title="Transacciones recientes" subtitle="Últimas 5 del período" href="/dashboard/transactions" linkLabel="Ver todas" />
        <div aria-busy={stale} className={`transition-opacity ${stale ? 'opacity-50' : ''}`}>
          <TransactionList transactions={transactions.slice(0, 5)} categories={categories} emptyAction />
        </div>
      </section>
    </div>
  )
}
