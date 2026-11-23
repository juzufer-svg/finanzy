'use client'

import React, { useCallback, useEffect, useState } from 'react'
import apiClient, { hasStoredSession } from '@/lib/api-client'
import BudgetCard from '@/components/BudgetCard'
import { useDialog, apiErrorMessage } from '@/components/DialogProvider'
import ErrorState from '@/components/ErrorState'
import PageHeader from '@/components/PageHeader'
import PeriodPicker from '@/components/PeriodPicker'
import { usePeriodStore } from '@/store/period'
import { useRouter } from 'next/navigation'
import { monthTitle, shiftMonth } from '@/lib/month-stats'
import { useCurrencyStore } from '@/store/currency'
import MoneyPrefix from '@/components/MoneyPrefix'

interface Transaction {
  id: string
  categoria_id: string
  tipo: 'ingreso' | 'gasto'
  monto: number
  descripcion: string
  fecha: string
}

interface Budget {
  id: string
  categoria_id: string
  limite_mensual: number
  mes_ano: string
}

interface Category {
  id: string
  nombre: string
  icono: string
  tipo: string
}

function EditBudgetModal({ budget, categories, onClose, onSaved }: {
  budget: Budget
  categories: Category[]
  onClose: () => void
  onSaved: () => void
}) {
  const toInput = useCurrencyStore(s => s.toInput)
  const toBase = useCurrencyStore(s => s.toBase)
  // Límite en la moneda elegida; si no se toca, se conserva el valor exacto (CHG-013)
  const [limiteInicial] = useState(() => toInput(budget.limite_mensual))
  const [limite, setLimite] = useState(limiteInicial)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const cat = categories.find(c => c.id === budget.categoria_id)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      await apiClient.put(`/api/v1/presupuestos/${budget.id}`, {
        limite_mensual: toBase(limite, { base: budget.limite_mensual, text: limiteInicial })
      })
      onSaved()
      onClose()
    } catch (err) {
      setError(apiErrorMessage(err, 'Error al actualizar el presupuesto'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4 pt-[max(1rem,env(safe-area-inset-top))] pb-[max(1rem,env(safe-area-inset-bottom))]" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-5 sm:p-6 max-h-[calc(100dvh-2rem)] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-base font-bold text-slate-900">Editar Presupuesto</h3>
          <button type="button" onClick={onClose} aria-label="Cerrar" className="w-9 h-9 flex items-center justify-center rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 text-xl leading-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">&times;</button>
        </div>
        {cat && (
          <p className="text-sm text-slate-500 mb-4">
            Categoría: <span className="font-semibold text-slate-700">{cat.icono} {cat.nombre}</span>
          </p>
        )}
        {error && <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">{error}</div>}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="bud-nuevo-limite-mensual" className="block text-xs font-semibold text-slate-700 mb-1.5">Nuevo Límite Mensual</label>
            <div className="relative">
              <MoneyPrefix />
              <input id="bud-nuevo-limite-mensual" type="number" value={limite} onChange={e => setLimite(e.target.value)}
                required step="0.01" min="0.01" autoFocus
                className="w-full !pl-12 pr-3 py-2.5 text-sm border-2 border-slate-200 rounded-lg focus:border-blue-500 focus:outline-none bg-slate-50 focus:bg-white" />
            </div>
          </div>
          <button type="submit" disabled={loading}
            className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-semibold rounded-lg transition-colors">
            {loading ? 'Guardando...' : 'Guardar cambios'}
          </button>
        </form>
      </div>
    </div>
  )
}

export default function BudgetsPage() {
  const router = useRouter()
  const toBase = useCurrencyStore(s => s.toBase)
  const [budgets, setBudgets] = useState<Budget[]>([])
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [loading, setLoading] = useState(true)
  // Período compartido por todas las vistas (CHG-009)
  const currentMonth = usePeriodStore(s => s.mes)
  // Mes de los datos en pantalla: si no coincide con el período, se está cargando el nuevo
  const [loadedMonth, setLoadedMonth] = useState<string | null>(null)
  const stale = loadedMonth !== null && loadedMonth !== currentMonth
  const [showForm, setShowForm] = useState(false)
  const [formData, setFormData] = useState({ categoria_id: '', limite_mensual: '' })
  const [saving, setSaving] = useState(false)
  const [editingBudget, setEditingBudget] = useState<Budget | null>(null)
  const [loadError, setLoadError] = useState('')
  const [copying, setCopying] = useState(false)
  const { confirm, notify } = useDialog()
  const previousMonth = shiftMonth(currentMonth, -1)

  // isActive permite ignorar respuestas que llegan tarde (cambio de mes o vista cerrada)
  const fetchData = useCallback((isActive: () => boolean = () => true) => {
    return Promise.all([
      apiClient.get(`/api/v1/presupuestos/${currentMonth}`),
      apiClient.get(`/api/v1/transacciones?mes=${currentMonth}`),
      apiClient.get('/api/v1/categorias')
    ])
      .then(([budRes, transRes, catRes]) => {
        if (!isActive()) return
        setBudgets(budRes.data)
        setTransactions(transRes.data)
        setCategories(catRes.data)
        setLoadError('')
      })
      .catch(err => {
        if (isActive()) setLoadError(apiErrorMessage(err, 'No se pudieron cargar tus presupuestos.'))
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      await apiClient.post('/api/v1/presupuestos', {
        ...formData,
        limite_mensual: toBase(formData.limite_mensual),
        mes_ano: currentMonth
      })
      await fetchData()
      setShowForm(false)
      setFormData({ categoria_id: '', limite_mensual: '' })
      notify('Presupuesto creado', 'success')
    } catch (err) {
      notify(apiErrorMessage(err, 'No se pudo crear el presupuesto.'), 'error')
    } finally {
      setSaving(false)
    }
  }

  // Copia los límites del mes anterior a este (CHG-012, A3). Los que ya existen aquí no se tocan.
  const handleCopyPrevious = async () => {
    const desde = monthTitle(previousMonth, false).toLowerCase()
    const ok = await confirm({
      title: `¿Copiar los presupuestos de ${desde}?`,
      description: `Se crean en ${monthTitle(currentMonth).toLowerCase()} los límites que tenías en ${desde}. Los que ya definiste para este mes se conservan.`,
      confirmLabel: 'Copiar',
    })
    if (!ok) return
    setCopying(true)
    try {
      const { data } = await apiClient.post('/api/v1/presupuestos/copiar', { desde: previousMonth, hacia: currentMonth })
      await fetchData()
      if (data.copiados === 0 && data.omitidos === 0) notify(`No había presupuestos en ${desde}.`, 'info')
      else if (data.copiados === 0) notify('Este mes ya tenía todos esos presupuestos.', 'info')
      else notify(`${data.copiados} ${data.copiados === 1 ? 'presupuesto copiado' : 'presupuestos copiados'}${data.omitidos ? ` (${data.omitidos} ya existían)` : ''}.`, 'success')
    } catch (err) {
      notify(apiErrorMessage(err, 'No se pudieron copiar los presupuestos.'), 'error')
    } finally {
      setCopying(false)
    }
  }

  const handleDeleteBudget = async (id: string) => {
    const ok = await confirm({
      title: '¿Eliminar este presupuesto?',
      description: 'Tus transacciones no se borran, solo el límite mensual.',
      confirmLabel: 'Eliminar',
      danger: true,
    })
    if (!ok) return
    try {
      await apiClient.delete(`/api/v1/presupuestos/${id}`)
      setBudgets(prev => prev.filter(b => b.id !== id))
      notify('Presupuesto eliminado', 'success')
    } catch (err) {
      notify(apiErrorMessage(err, 'No se pudo eliminar el presupuesto.'), 'error')
    }
  }

  return (
    <div className="space-y-6">
      {editingBudget && (
        <EditBudgetModal
          budget={editingBudget}
          categories={categories}
          onClose={() => setEditingBudget(null)}
          onSaved={fetchData}
        />
      )}
      <PageHeader
        wideActions
        title="Presupuestos"
        subtitle="Límites de gasto del período"
        actions={<>
          <PeriodPicker />
          <button type="button" onClick={handleCopyPrevious} disabled={copying || loading || stale} className="btn-secondary disabled:opacity-50"
            title={`Copiar los presupuestos de ${monthTitle(previousMonth).toLowerCase()}`}>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.75 17.25v3.375c0 .621-.504 1.125-1.125 1.125h-9.75a1.125 1.125 0 0 1-1.125-1.125V7.875c0-.621.504-1.125 1.125-1.125H6.75a9.06 9.06 0 0 1 1.5.124m7.5 10.376h3.375c.621 0 1.125-.504 1.125-1.125V11.25c0-4.46-3.243-8.161-7.5-8.876a9.06 9.06 0 0 0-1.5-.124H9.375c-.621 0-1.125.504-1.125 1.125v3.5m7.5 10.375H9.375a1.125 1.125 0 0 1-1.125-1.125v-9.25m12 6.625v-1.875a3.375 3.375 0 0 0-3.375-3.375h-1.5a1.125 1.125 0 0 1-1.125-1.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H9.75" />
            </svg>
            {copying ? 'Copiando…' : 'Copiar mes anterior'}
          </button>
          <button type="button" onClick={() => setShowForm(!showForm)} className="btn-primary" aria-expanded={showForm}>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={showForm ? "M6 18 18 6M6 6l12 12" : "M12 4.5v15m7.5-7.5h-15"} />
            </svg>
            {showForm ? 'Cancelar' : 'Nuevo presupuesto'}
          </button>
        </>}
      />

      {/* Form */}
      {showForm && (
        <div className="card p-4 sm:p-6 animate-slide-in">
          <h2 className="text-sm font-bold text-slate-900 mb-4 flex items-center gap-2">
            <div className="w-6 h-6 bg-blue-100 rounded flex items-center justify-center">
              <svg className="w-3.5 h-3.5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
            </div>
            Crear Presupuesto
          </h2>
          <form onSubmit={handleSubmit} className="grid grid-cols-1 sm:grid-cols-3 gap-4 items-end">
            <div>
              <label htmlFor="bud-categoria" className="label">Categoría</label>
              <select id="bud-categoria"
                value={formData.categoria_id}
                onChange={(e) => setFormData({ ...formData, categoria_id: e.target.value })}
                required className="input-field"
              >
                <option value="">Selecciona una categoría</option>
                {/* Solo las que aún no tienen presupuesto este mes: uno por categoría y mes (INV-028) */}
                {categories.filter(c => c.tipo === 'gasto' && !budgets.some(b => b.categoria_id === c.id)).map(cat => (
                  <option key={cat.id} value={cat.id}>{cat.nombre}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="bud-limite-mensual" className="label">Límite Mensual</label>
              <div className="relative">
                <MoneyPrefix />
                <input id="bud-limite-mensual" type="number" value={formData.limite_mensual}
                  onChange={(e) => setFormData({ ...formData, limite_mensual: e.target.value })}
                  required step="0.01" min="0.01" placeholder="0.00" className="input-field !pl-12" />
              </div>
            </div>
            <button type="submit" disabled={saving} className="btn-primary justify-center py-2.5">
              {saving ? 'Guardando...' : 'Crear Presupuesto'}
            </button>
          </form>
        </div>
      )}

      {/* Cards */}
      {loadError ? (
        <ErrorState message={loadError} onRetry={() => { setLoading(true); fetchData() }} />
      ) : loading || stale ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map(i => <div key={i} className="card h-44 animate-pulse bg-slate-100" />)}
        </div>
      ) : budgets.length === 0 ? (
        <div className="card px-6 py-12 sm:p-16 flex flex-col items-center text-center">
          <div className="w-14 h-14 bg-slate-100 rounded-2xl flex items-center justify-center mb-4">
            <svg className="w-7 h-7 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 6v12m-3-2.818.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
            </svg>
          </div>
          <h3 className="text-base font-semibold text-slate-700">Sin presupuestos</h3>
          <p className="text-sm text-slate-500 mt-1 mb-4">Define cuánto quieres gastar como máximo en cada categoría y te avisaremos al llegar al 75 %.</p>
          <div className="flex flex-col sm:flex-row gap-2">
            <button type="button" onClick={() => setShowForm(true)} className="btn-primary">
              Crear primer presupuesto
            </button>
            <button type="button" onClick={handleCopyPrevious} disabled={copying} className="btn-secondary disabled:opacity-50">
              {copying ? 'Copiando…' : `Copiar los de ${monthTitle(previousMonth, false).toLowerCase()}`}
            </button>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {budgets.map((budget) => {
            const gastado = transactions
              .filter(t => t.categoria_id === budget.categoria_id && t.tipo === 'gasto')
              .reduce((sum, t) => sum + t.monto, 0)
            const cat = categories.find(c => c.id === budget.categoria_id)
            return (
              <BudgetCard
                key={budget.id}
                categoria={cat ? `${cat.icono || ''} ${cat.nombre}`.trim() : budget.categoria_id.slice(0, 8)}
                limite={budget.limite_mensual}
                gastado={gastado}
                icono={cat?.icono || ''}
                onEdit={() => setEditingBudget(budget)}
                onDelete={() => handleDeleteBudget(budget.id)}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}
