'use client'

/**
 * Recurrentes pendientes (CHG-012, INV-025): las que ya llegaron a su fecha y esperan que la
 * persona las confirme (con el monto ajustable) u omita. Nada se registra sin su confirmación.
 */
import React, { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import apiClient from '@/lib/api-client'
import { useDialog, apiErrorMessage } from '@/components/DialogProvider'
import ErrorState from '@/components/ErrorState'
import { useCurrencyStore } from '@/store/currency'
import { cuandoTexto, localDate, type Recurrente } from '@/lib/recurrentes'
import { shortDate } from '@/lib/month-stats'
import MoneyPrefix from '@/components/MoneyPrefix'

interface Category { id: string; nombre: string; icono?: string }

export default function PendingRecurring({ onChanged, hideWhenEmpty = false, refreshKey = 0 }: {
  /** Se llama después de registrar u omitir (para recargar la vista que lo contiene). */
  onChanged?: (recurrenteId: string) => void
  /** En el Inicio no se muestra nada si no hay pendientes. */
  hideWhenEmpty?: boolean
  /** Cambiarlo fuerza una recarga (p. ej. tras crear una recurrente en la misma página). */
  refreshKey?: number
}) {
  const fmt = useCurrencyStore(s => s.fmt)
  const toInput = useCurrencyStore(s => s.toInput)
  const toBase = useCurrencyStore(s => s.toBase)
  const { confirm, notify } = useDialog()
  const [items, setItems] = useState<Recurrente[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')
  const [montos, setMontos] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState<string | null>(null)
  const hoy = localDate(new Date())

  const fetchPending = useCallback((isActive: () => boolean = () => true) => {
    return Promise.all([
      apiClient.get<Recurrente[]>(`/api/v1/recurrentes/pendientes?hasta=${hoy}`),
      apiClient.get<Category[]>('/api/v1/categorias'),
    ])
      .then(([pend, cats]) => {
        if (!isActive()) return
        setItems(pend.data)
        setCategories(cats.data)
        setMontos({})
        setError('')
      })
      .catch(err => {
        if (isActive()) setError(apiErrorMessage(err, 'No se pudieron cargar las recurrentes pendientes.'))
      })
      .finally(() => {
        if (isActive()) setLoaded(true)
      })
  }, [hoy])

  useEffect(() => {
    let active = true
    fetchPending(() => active)
    return () => { active = false }
  }, [fetchPending, refreshKey])

  const nombre = (r: Recurrente) => {
    const cat = categories.find(c => c.id === r.categoria_id)
    return r.descripcion || cat?.nombre || 'Recurrente'
  }

  const registrar = async (r: Recurrente) => {
    // El monto se escribe en la moneda elegida. Si no se tocó, no se envía: el backend usa el de la
    // plantilla tal cual (sin redondeos de la conversión, CHG-013)
    const texto = montos[r.id]
    const propuesto = toInput(r.monto)
    const monto = texto === undefined || texto === '' || texto.trim() === propuesto ? undefined : toBase(texto)
    if (monto !== undefined && !(monto > 0)) {
      notify('Escribe un monto mayor que 0.', 'error')
      return
    }
    setBusy(r.id)
    try {
      await apiClient.post(`/api/v1/recurrentes/${r.id}/confirmar`, { ocurrencia: r.proxima_fecha, ...(monto !== undefined ? { monto } : {}) })
      notify(`${nombre(r)} registrado`, 'success')
      await fetchPending()
      onChanged?.(r.id)
    } catch (err) {
      notify(apiErrorMessage(err, 'No se pudo registrar.'), 'error')
      await fetchPending()
    } finally {
      setBusy(null)
    }
  }

  const omitir = async (r: Recurrente) => {
    const ok = await confirm({
      title: `¿Omitir ${nombre(r)} del ${shortDate(r.proxima_fecha)}?`,
      description: 'No se registra nada para esta fecha. La recurrente sigue activa para las próximas.',
      confirmLabel: 'Omitir',
    })
    if (!ok) return
    setBusy(r.id)
    try {
      await apiClient.post(`/api/v1/recurrentes/${r.id}/omitir`, { ocurrencia: r.proxima_fecha })
      await fetchPending()
      onChanged?.(r.id)
    } catch (err) {
      notify(apiErrorMessage(err, 'No se pudo omitir.'), 'error')
      await fetchPending()
    } finally {
      setBusy(null)
    }
  }

  if (!loaded) return hideWhenEmpty ? null : <div className="card h-24 animate-pulse bg-slate-100" />
  // En el Inicio un error aquí no debe tapar el resto: se muestra solo en la página de Recurrentes
  if (error) return hideWhenEmpty ? null : <ErrorState message={error} onRetry={() => { setLoaded(false); fetchPending() }} />
  if (items.length === 0) {
    if (hideWhenEmpty) return null
    return (
      <div className="card p-4 sm:p-5 flex items-center gap-3">
        <span className="w-9 h-9 rounded-lg bg-emerald-100 text-emerald-600 flex items-center justify-center flex-shrink-0" aria-hidden>✓</span>
        <p className="text-sm text-slate-600">No tienes recurrentes pendientes. Te avisaremos aquí y en el Inicio cuando llegue la fecha de alguna.</p>
      </div>
    )
  }

  return (
    <section className="card overflow-hidden border-l-4 border-amber-400" aria-labelledby="pendientes-titulo">
      <div className="px-4 sm:px-5 pt-4 sm:pt-5 pb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id="pendientes-titulo" className="text-base font-bold text-slate-900">
            Pendientes por confirmar <span className="badge-amber ml-1 align-middle">{items.length}</span>
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">Revisa el monto y regístralas con un toque. Nada se registra sin tu confirmación.</p>
        </div>
        {hideWhenEmpty && <Link href="/dashboard/recurring" className="text-xs font-semibold text-blue-600 hover:underline flex-shrink-0">Ver todas</Link>}
      </div>
      <ul className="divide-y divide-slate-100">
        {items.map(r => {
          const cat = categories.find(c => c.id === r.categoria_id)
          const atrasada = r.proxima_fecha < hoy
          return (
            <li key={r.id} className="px-4 sm:px-5 py-3 flex flex-col sm:flex-row sm:items-center gap-3">
              <div className="flex items-center gap-3 min-w-0 flex-1">
                <span className={`w-10 h-10 rounded-xl flex items-center justify-center text-xl flex-shrink-0 ${r.tipo === 'ingreso' ? 'bg-emerald-50' : 'bg-red-50'}`} aria-hidden>
                  {cat?.icono || (r.tipo === 'ingreso' ? '↑' : '↓')}
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-slate-900 truncate">{nombre(r)}</p>
                  <p className={`text-xs ${atrasada ? 'text-amber-700 dark:text-amber-400' : 'text-slate-500'}`}>
                    {r.tipo === 'ingreso' ? 'Ingreso' : 'Gasto'} · {shortDate(r.proxima_fecha)} · {cuandoTexto(r.proxima_fecha, hoy)}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2 sm:flex-shrink-0">
                <label htmlFor={`pend-monto-${r.id}`} className="sr-only">Monto de {nombre(r)}</label>
                <div className="relative flex-1 sm:w-36 sm:flex-none">
                  <MoneyPrefix />
                  <input id={`pend-monto-${r.id}`} type="number" inputMode="decimal" step="0.01" min="0.01"
                    value={montos[r.id] ?? toInput(r.monto)}
                    onChange={e => setMontos(p => ({ ...p, [r.id]: e.target.value }))}
                    className="input-field !pl-12 !py-2 tabular-nums" title={`Propuesto: ${fmt(r.monto)}`} />
                </div>
                <button type="button" onClick={() => registrar(r)} disabled={busy === r.id} className="btn-primary !px-3 disabled:opacity-50">
                  {busy === r.id ? '…' : 'Registrar'}
                </button>
                <button type="button" onClick={() => omitir(r)} disabled={busy === r.id} className="btn-secondary !px-3 disabled:opacity-50" aria-label={`Omitir ${nombre(r)} del ${shortDate(r.proxima_fecha)}`}>
                  Omitir
                </button>
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
