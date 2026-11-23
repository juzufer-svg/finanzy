'use client'

/**
 * Transacciones recurrentes (CHG-012, A1 · REQ-F-016): arriendo, sueldo, suscripciones…
 * Cada una es una plantilla con frecuencia; cuando llega su fecha aparece como pendiente y la
 * persona la confirma u omite (INV-025). La próxima fecha la calcula el backend (INV-026).
 */
import React, { useCallback, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import apiClient, { hasStoredSession } from '@/lib/api-client'
import { useDialog, apiErrorMessage } from '@/components/DialogProvider'
import ErrorState from '@/components/ErrorState'
import PageHeader from '@/components/PageHeader'
import EmptyState from '@/components/EmptyState'
import PendingRecurring from '@/components/PendingRecurring'
import { useCurrencyStore } from '@/store/currency'
import { MEDIOS_PAGO, MEDIO_POR_DEFECTO, medioPagoLabel } from '@/lib/payment-methods'
import { FRECUENCIAS, frecuenciaTexto, localDate, cuandoTexto, totalMensualEstimado, type Recurrente } from '@/lib/recurrentes'
import { shortDate } from '@/lib/month-stats'
import MoneyPrefix from '@/components/MoneyPrefix'

interface Category { id: string; nombre: string; tipo: string; icono?: string }

type FormState = {
  tipo: 'gasto' | 'ingreso'
  categoria_id: string
  monto: string
  descripcion: string
  medio_pago: string
  frecuencia: string
  proxima_fecha: string
  activa: boolean
}

const nuevoForm = (): FormState => ({
  tipo: 'gasto', categoria_id: '', monto: '', descripcion: '', medio_pago: MEDIO_POR_DEFECTO,
  frecuencia: 'mensual', proxima_fecha: localDate(new Date()), activa: true,
})

const IconRepeat = () => (
  <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" />
  </svg>
)

function RecurringForm({ initial, editing, categories, onCancel, onSaved, onConflict }: {
  initial: FormState
  editing: Recurrente | null
  categories: Category[]
  onCancel: () => void
  onSaved: () => void
  /** La próxima fecha cambió mientras se editaba: hay que recargar los datos. */
  onConflict: (mensaje: string) => void
}) {
  const toBase = useCurrencyStore(s => s.toBase)
  const [form, setForm] = useState<FormState>(initial)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setForm(p => ({ ...p, [k]: v }))
  const cats = categories.filter(c => c.tipo === form.tipo)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    const { proxima_fecha, ...resto } = form
    const body = {
      ...resto,
      // Escrito en la moneda elegida; al editar sin tocarlo se conserva el valor exacto (CHG-013)
      monto: toBase(form.monto, editing ? { base: editing.monto, text: initial.monto } : undefined),
      descripcion: form.descripcion.trim(),
      medio_pago: form.medio_pago || null,
      // Al editar, la fecha solo se envía si la persona la cambió, junto con la que vio (INV-026):
      // así guardar el monto nunca hace retroceder una fecha que ya se registró desde pendientes.
      ...(!editing ? { proxima_fecha } : proxima_fecha !== editing.proxima_fecha ? { proxima_fecha, proxima_fecha_vista: editing.proxima_fecha } : {}),
    }
    try {
      if (editing) await apiClient.put(`/api/v1/recurrentes/${editing.id}`, body)
      else await apiClient.post('/api/v1/recurrentes', body)
      onSaved()
    } catch (err) {
      const mensaje = apiErrorMessage(err, 'No se pudo guardar la recurrente.')
      // 409: la fecha cambió mientras se editaba; se avisa y se recarga con los datos vigentes
      if ((err as { response?: { status?: number } })?.response?.status === 409) onConflict(mensaje)
      else setError(mensaje)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="card p-4 sm:p-6 space-y-4 animate-slide-in" aria-labelledby="rec-form-titulo">
      <div className="flex items-center justify-between">
        <h2 id="rec-form-titulo" className="text-sm font-bold text-slate-900">{editing ? 'Editar recurrente' : 'Nueva recurrente'}</h2>
        <button type="button" onClick={onCancel} aria-label="Cerrar formulario" className="w-9 h-9 flex items-center justify-center rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 text-xl leading-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">&times;</button>
      </div>
      {error && <div role="alert" className="p-3 rounded-lg bg-red-50 border border-red-200 text-sm font-medium text-red-700">{error}</div>}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <fieldset>
          <legend className="label">Tipo</legend>
          <div className="grid grid-cols-2 gap-2">
            {(['gasto', 'ingreso'] as const).map(t => (
              <label key={t} className={`flex items-center justify-center p-2.5 rounded-lg border-2 cursor-pointer has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-blue-500 has-[:focus-visible]:ring-offset-2 text-sm font-semibold transition-all ${
                form.tipo === t
                  ? t === 'gasto' ? 'border-red-500 bg-red-50 text-red-700' : 'border-emerald-500 bg-emerald-50 text-emerald-700'
                  : 'border-slate-200 text-slate-500 hover:border-slate-300'
              }`}>
                <input type="radio" name="rec-tipo" className="sr-only" checked={form.tipo === t}
                  onChange={() => setForm(p => ({ ...p, tipo: t, categoria_id: '' }))} />
                {t === 'gasto' ? '↓ Gasto' : '↑ Ingreso'}
              </label>
            ))}
          </div>
        </fieldset>
        <div>
          <label htmlFor="rec-descripcion" className="label">Nombre</label>
          <input id="rec-descripcion" type="text" value={form.descripcion} onChange={e => set('descripcion', e.target.value)}
            placeholder="Ej.: Arriendo, Sueldo, Netflix" required maxLength={255} autoComplete="off" className="input-field" />
        </div>
        <div>
          <label htmlFor="rec-monto" className="label">Monto</label>
          <div className="relative">
            <MoneyPrefix />
            <input id="rec-monto" type="number" inputMode="decimal" step="0.01" min="0.01" value={form.monto}
              onChange={e => set('monto', e.target.value)} required placeholder="0.00" className="input-field !pl-12" />
          </div>
        </div>
        <div>
          <label htmlFor="rec-categoria" className="label">Categoría</label>
          <select id="rec-categoria" value={form.categoria_id} onChange={e => set('categoria_id', e.target.value)} className="input-field">
            <option value="">Sin categoría</option>
            {cats.map(c => <option key={c.id} value={c.id}>{c.icono ? `${c.icono} ${c.nombre}` : c.nombre}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="rec-frecuencia" className="label">Se repite</label>
          <select id="rec-frecuencia" value={form.frecuencia} onChange={e => set('frecuencia', e.target.value)} className="input-field" aria-describedby="rec-frecuencia-ayuda">
            {FRECUENCIAS.map(f => <option key={f.value} value={f.value}>{f.label}</option>)}
          </select>
          <p id="rec-frecuencia-ayuda" className="text-xs text-slate-500 mt-1">{FRECUENCIAS.find(f => f.value === form.frecuencia)?.ayuda}</p>
        </div>
        <div>
          <label htmlFor="rec-fecha" className="label">{editing ? 'Próxima fecha' : 'Primera fecha'}</label>
          <input id="rec-fecha" type="date" value={form.proxima_fecha} onChange={e => set('proxima_fecha', e.target.value)} required className="input-field" />
        </div>
        <div>
          <label htmlFor="rec-medio" className="label">Medio de pago</label>
          <select id="rec-medio" value={form.medio_pago} onChange={e => set('medio_pago', e.target.value)} className="input-field">
            {MEDIOS_PAGO.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
            <option value="">Sin especificar</option>
          </select>
        </div>
      </div>

      <div className="flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
        <button type="button" onClick={onCancel} className="btn-secondary">Cancelar</button>
        <button type="submit" disabled={saving} className="btn-primary disabled:opacity-50">
          {saving ? 'Guardando…' : editing ? 'Guardar cambios' : 'Crear recurrente'}
        </button>
      </div>
    </form>
  )
}

export default function RecurringPage() {
  const router = useRouter()
  const toInput = useCurrencyStore(s => s.toInput)
  const fmt = useCurrencyStore(s => s.fmt)
  const { confirm, notify } = useDialog()
  const [items, setItems] = useState<Recurrente[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  // null = formulario cerrado; { editing: null } = crear; { editing: r } = editar
  const [form, setForm] = useState<{ editing: Recurrente | null; key: number } | null>(null)
  const [pendingKey, setPendingKey] = useState(0)
  const hoy = localDate(new Date())

  const fetchData = useCallback((isActive: () => boolean = () => true) => {
    return Promise.all([
      apiClient.get<Recurrente[]>('/api/v1/recurrentes'),
      apiClient.get<Category[]>('/api/v1/categorias'),
    ])
      .then(([rec, cats]) => {
        if (!isActive()) return
        setItems(rec.data)
        setCategories(cats.data)
        setLoadError('')
      })
      .catch(err => {
        if (isActive()) setLoadError(apiErrorMessage(err, 'No se pudieron cargar tus recurrentes.'))
      })
      .finally(() => {
        if (isActive()) setLoading(false)
      })
  }, [])

  useEffect(() => {
    if (!hasStoredSession()) { router.push('/auth/login'); return }
    let active = true
    fetchData(() => active)
    return () => { active = false }
  }, [fetchData, router])

  const refrescar = () => { fetchData(); setPendingKey(k => k + 1) }

  // Sin proxima_fecha: pausar o activar nunca cambia la fecha (INV-026)
  const cuerpo = (r: Recurrente, cambios: Partial<Recurrente> = {}) => ({
    tipo: r.tipo, categoria_id: r.categoria_id || '', monto: r.monto, descripcion: r.descripcion || '',
    medio_pago: r.medio_pago ?? null, frecuencia: r.frecuencia, activa: r.activa,
    ...cambios,
  })

  const togglePausa = async (r: Recurrente) => {
    try {
      await apiClient.put(`/api/v1/recurrentes/${r.id}`, cuerpo(r, { activa: !r.activa }))
      notify(r.activa ? 'Recurrente pausada' : 'Recurrente activada', 'success')
      refrescar()
    } catch (err) {
      notify(apiErrorMessage(err, 'No se pudo cambiar el estado.'), 'error')
      refrescar()
    }
  }

  const eliminar = async (r: Recurrente) => {
    const ok = await confirm({
      title: `¿Eliminar «${r.descripcion || 'esta recurrente'}»?`,
      description: 'Dejará de proponerse. Las transacciones que ya registraste con ella se conservan.',
      confirmLabel: 'Eliminar',
      danger: true,
    })
    if (!ok) return
    try {
      await apiClient.delete(`/api/v1/recurrentes/${r.id}`)
      notify('Recurrente eliminada', 'success')
      if (form?.editing?.id === r.id) setForm(null)
      refrescar()
    } catch (err) {
      notify(apiErrorMessage(err, 'No se pudo eliminar.'), 'error')
    }
  }

  const initialFor = (r: Recurrente | null): FormState => r
    ? {
        tipo: r.tipo === 'ingreso' ? 'ingreso' : 'gasto', categoria_id: r.categoria_id || '', monto: toInput(r.monto),
        descripcion: r.descripcion || '', medio_pago: r.medio_pago ?? '', frecuencia: r.frecuencia,
        proxima_fecha: r.proxima_fecha, activa: r.activa,
      }
    : nuevoForm()

  const gastoMes = totalMensualEstimado(items, 'gasto')
  const ingresoMes = totalMensualEstimado(items, 'ingreso')

  return (
    <div className="space-y-6">
      <PageHeader
        title="Recurrentes"
        subtitle="Ingresos y gastos que se repiten"
        actions={
          <button type="button" onClick={() => setForm(form && !form.editing ? null : { editing: null, key: Date.now() })} className="btn-primary" aria-expanded={!!form && !form.editing}>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            {form && !form.editing ? 'Cancelar' : 'Nueva recurrente'}
          </button>
        }
      />

      {form && (
        <RecurringForm
          key={form.key}
          initial={initialFor(form.editing)}
          editing={form.editing}
          categories={categories}
          onCancel={() => setForm(null)}
          onConflict={mensaje => { notify(mensaje, 'error'); setForm(null); refrescar() }}
          onSaved={() => { notify(form.editing ? 'Recurrente actualizada' : 'Recurrente creada', 'success'); setForm(null); refrescar() }}
        />
      )}

      {/* Registrar u omitir cierra una edición abierta: así nunca se guarda con una fecha vieja */}
      <PendingRecurring refreshKey={pendingKey} onChanged={id => {
        // Si se estaba editando esa misma recurrente, la edición se cierra con aviso (su fecha cambió)
        if (form?.editing?.id === id) { setForm(null); notify('La edición se cerró porque esa recurrente cambió de fecha. Ábrela de nuevo.', 'info') }
        fetchData()
      }} />

      {loadError ? (
        <ErrorState message={loadError} onRetry={() => { setLoading(true); fetchData() }} />
      ) : loading ? (
        <div className="space-y-3">{[1, 2, 3].map(i => <div key={i} className="card h-20 animate-pulse bg-slate-100" />)}</div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={<IconRepeat />}
          title="Aún no tienes recurrentes"
          description="Agrega tu arriendo, sueldo o suscripciones una sola vez. Cuando llegue la fecha te los proponemos para registrarlos con un toque."
          actionLabel="Crear la primera"
          onAction={() => setForm({ editing: null, key: Date.now() })}
        />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:gap-4">
            <div className="card p-3 sm:p-4 border-l-4 border-red-400 min-w-0">
              <p className="text-xs text-slate-500">Gastos fijos al mes (aprox.)</p>
              <p className="text-base sm:text-xl font-bold text-red-600 mt-0.5 tabular-nums break-words">{fmt(gastoMes)}</p>
            </div>
            <div className="card p-3 sm:p-4 border-l-4 border-emerald-400 min-w-0">
              <p className="text-xs text-slate-500">Ingresos fijos al mes (aprox.)</p>
              <p className="text-base sm:text-xl font-bold text-emerald-600 mt-0.5 tabular-nums break-words">{fmt(ingresoMes)}</p>
            </div>
          </div>

          <ul className="card divide-y divide-slate-100">
            {items.map(r => {
              const cat = categories.find(c => c.id === r.categoria_id)
              return (
                <li key={r.id} className={`p-3 sm:p-4 flex flex-wrap sm:flex-nowrap items-center gap-x-3 gap-y-1 group ${r.activa ? '' : 'opacity-60'}`}>
                  <span className={`w-11 h-11 rounded-xl flex items-center justify-center text-xl flex-shrink-0 ${r.tipo === 'ingreso' ? 'bg-emerald-50' : 'bg-red-50'}`} aria-hidden>
                    {cat?.icono || (r.tipo === 'ingreso' ? '↑' : '↓')}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 min-w-0">
                      <p className="text-sm font-semibold text-slate-900 truncate">{r.descripcion || cat?.nombre || 'Recurrente'}</p>
                      {!r.activa && <span className="badge-amber flex-shrink-0">Pausada</span>}
                    </div>
                    <p className="text-xs text-slate-500 truncate">
                      {frecuenciaTexto(r.frecuencia, r.dia_ancla)} · {cat?.nombre ?? 'Sin categoría'}{r.medio_pago ? ` · ${medioPagoLabel(r.medio_pago)}` : ''}
                    </p>
                    {r.activa && (
                      <p className="text-xs text-slate-400 mt-0.5">Próxima: {shortDate(r.proxima_fecha, true)} ({cuandoTexto(r.proxima_fecha, hoy).toLowerCase()})</p>
                    )}
                  </div>
                  <p className={`text-sm font-bold tabular-nums whitespace-nowrap ${r.tipo === 'ingreso' ? 'text-emerald-600' : 'text-red-600'}`}>
                    {r.tipo === 'ingreso' ? '+' : '-'}{fmt(r.monto)}
                  </p>
                  {/* En el celular los botones van en su propia línea: así el nombre no se corta */}
                  <div className="flex items-center justify-end gap-0.5 reveal-on-hover transition-opacity w-full sm:w-auto flex-shrink-0">
                    <button type="button" onClick={() => togglePausa(r)} title={r.activa ? 'Pausar' : 'Activar'}
                      aria-label={`${r.activa ? 'Pausar' : 'Activar'} ${r.descripcion || 'recurrente'}`}
                      className="p-2 text-slate-400 hover:text-amber-600 hover:bg-amber-50 rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
                      {r.activa ? (
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.75 5.25v13.5m-7.5-13.5v13.5" /></svg>
                      ) : (
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.347a1.125 1.125 0 0 1 0 1.972l-11.54 6.347a1.125 1.125 0 0 1-1.667-.986V5.653Z" /></svg>
                      )}
                    </button>
                    <button type="button" onClick={() => setForm({ editing: r, key: Date.now() })} title="Editar" aria-label={`Editar ${r.descripcion || 'recurrente'}`}
                      className="p-2 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125" /></svg>
                    </button>
                    <button type="button" onClick={() => eliminar(r)} title="Eliminar" aria-label={`Eliminar ${r.descripcion || 'recurrente'}`}
                      className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" /></svg>
                    </button>
                  </div>
                </li>
              )
            })}
          </ul>
        </>
      )}
    </div>
  )
}
