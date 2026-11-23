'use client'

/**
 * Categorías (CHG-012, A5): antes era una ventana escondida dentro de Transacciones.
 * Crear, editar y eliminar categorías propias de ingreso o gasto (REQ-F-006).
 */
import React, { useCallback, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import apiClient, { hasStoredSession } from '@/lib/api-client'
import { useDialog, apiErrorMessage } from '@/components/DialogProvider'
import ErrorState from '@/components/ErrorState'
import PageHeader from '@/components/PageHeader'
import EmptyState from '@/components/EmptyState'
import { ICONOS } from '@/lib/category-icons'

interface Category {
  id: string
  nombre: string
  tipo: string
  icono?: string
}

type Tipo = 'gasto' | 'ingreso'

// La lista de íconos tiene algunos repetidos: se muestran una sola vez
const ICONOS_UNICOS = Array.from(new Set(ICONOS))
const FORM_VACIO = { nombre: '', tipo: 'gasto' as Tipo, icono: '🛒' }

export default function CategoriesPage() {
  const router = useRouter()
  const [categories, setCategories] = useState<Category[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [formData, setFormData] = useState(FORM_VACIO)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState('')
  const [filterTipo, setFilterTipo] = useState<'todos' | Tipo>('todos')
  const { confirm, notify } = useDialog()

  const fetchCategories = useCallback((isActive: () => boolean = () => true) => {
    return apiClient.get<Category[]>('/api/v1/categorias')
      .then(res => {
        if (!isActive()) return
        setCategories(res.data)
        setLoadError('')
      })
      .catch(err => {
        if (isActive()) setLoadError(apiErrorMessage(err, 'No se pudieron cargar las categorías.'))
      })
      .finally(() => {
        if (isActive()) setLoading(false)
      })
  }, [])

  useEffect(() => {
    if (!hasStoredSession()) { router.push('/auth/login'); return }
    let active = true
    fetchCategories(() => active)
    return () => { active = false }
  }, [fetchCategories, router])

  const openCreate = () => {
    setEditingId(null)
    setFormData({ ...FORM_VACIO, tipo: filterTipo === 'ingreso' ? 'ingreso' : 'gasto' })
    setFormError('')
    setShowForm(true)
  }

  const openEdit = (cat: Category) => {
    setEditingId(cat.id)
    setFormData({ nombre: cat.nombre, tipo: cat.tipo as Tipo, icono: cat.icono || '🛒' })
    setFormError('')
    setShowForm(true)
  }

  const closeForm = () => { setShowForm(false); setEditingId(null); setFormError('') }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setFormError('')
    try {
      const datos = { ...formData, nombre: formData.nombre.trim() }
      if (editingId) await apiClient.put(`/api/v1/categorias/${editingId}`, datos)
      else await apiClient.post('/api/v1/categorias', datos)
      await fetchCategories()
      notify(editingId ? 'Categoría actualizada' : 'Categoría creada', 'success')
      closeForm()
    } catch (err) {
      setFormError(apiErrorMessage(err, 'No se pudo guardar la categoría.'))
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (cat: Category) => {
    const ok = await confirm({
      title: `¿Eliminar «${cat.nombre}»?`,
      description: 'Sus transacciones se conservan y quedan «Sin categoría». Los presupuestos de esta categoría se eliminan.',
      confirmLabel: 'Eliminar',
      danger: true,
    })
    if (!ok) return
    try {
      await apiClient.delete(`/api/v1/categorias/${cat.id}`)
      setCategories(prev => prev.filter(c => c.id !== cat.id))
      if (editingId === cat.id) closeForm()
      notify('Categoría eliminada', 'success')
    } catch (err) {
      notify(apiErrorMessage(err, 'No se pudo eliminar la categoría.'), 'error')
    }
  }

  const displayed = filterTipo === 'todos' ? categories : categories.filter(c => c.tipo === filterTipo)
  const counts = {
    todos: categories.length,
    gasto: categories.filter(c => c.tipo === 'gasto').length,
    ingreso: categories.filter(c => c.tipo === 'ingreso').length,
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Categorías"
        subtitle="Organiza tus ingresos y gastos"
        actions={
          <button type="button" onClick={showForm && !editingId ? closeForm : openCreate} className="btn-primary" aria-expanded={showForm && !editingId}>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            {showForm && !editingId ? 'Cancelar' : 'Nueva categoría'}
          </button>
        }
      />

      {showForm && (
        <form onSubmit={handleSubmit} className="card p-4 sm:p-6 space-y-4 animate-slide-in" aria-labelledby="cat-form-titulo">
          <div className="flex items-center justify-between">
            <h2 id="cat-form-titulo" className="text-sm font-bold text-slate-900">{editingId ? 'Editar categoría' : 'Nueva categoría'}</h2>
            <button type="button" onClick={closeForm} aria-label="Cerrar formulario" className="w-9 h-9 flex items-center justify-center rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 text-xl leading-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">&times;</button>
          </div>
          {formError && <div role="alert" className="p-3 rounded-lg bg-red-50 border border-red-200 text-sm font-medium text-red-700">{formError}</div>}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <fieldset>
              <legend className="label">Tipo</legend>
              <div className="grid grid-cols-2 gap-2">
                {(['gasto', 'ingreso'] as const).map(t => (
                  <label key={t} className={`flex items-center justify-center gap-1.5 p-2.5 rounded-lg border-2 cursor-pointer has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-blue-500 has-[:focus-visible]:ring-offset-2 text-sm font-semibold transition-all ${
                    formData.tipo === t
                      ? t === 'gasto' ? 'border-red-500 bg-red-50 text-red-700' : 'border-emerald-500 bg-emerald-50 text-emerald-700'
                      : 'border-slate-200 text-slate-500 hover:border-slate-300'
                  }`}>
                    <input type="radio" name="cat-tipo" className="sr-only" checked={formData.tipo === t} onChange={() => setFormData(p => ({ ...p, tipo: t }))} />
                    {t === 'gasto' ? '↓ Gasto' : '↑ Ingreso'}
                  </label>
                ))}
              </div>
            </fieldset>
            <div>
              <label htmlFor="cat-nombre" className="label">Nombre</label>
              <input id="cat-nombre" type="text" value={formData.nombre} onChange={e => setFormData(p => ({ ...p, nombre: e.target.value }))}
                placeholder="Ej.: Mercado, Arriendo, Sueldo" required maxLength={40} autoComplete="off" className="input-field" autoFocus />
            </div>
          </div>

          <fieldset>
            <legend className="label">Ícono <span className="text-xl align-middle ml-1" aria-hidden>{formData.icono}</span></legend>
            <div className="grid grid-cols-8 sm:grid-cols-12 gap-1 max-h-40 overflow-y-auto p-2 bg-slate-50 rounded-lg border border-slate-200">
              {ICONOS_UNICOS.map(i => (
                <button key={i} type="button" onClick={() => setFormData(p => ({ ...p, icono: i }))}
                  aria-label={`Ícono ${i}`} aria-pressed={formData.icono === i}
                  className={`text-xl p-1.5 rounded-lg transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${formData.icono === i ? 'bg-blue-100 ring-2 ring-blue-400' : 'hover:bg-slate-200'}`}>
                  {i}
                </button>
              ))}
            </div>
          </fieldset>

          <div className="flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
            <button type="button" onClick={closeForm} className="btn-secondary">Cancelar</button>
            <button type="submit" disabled={saving} className="btn-primary disabled:opacity-50">
              {saving ? 'Guardando…' : editingId ? 'Guardar cambios' : 'Crear categoría'}
            </button>
          </div>
        </form>
      )}

      {/* Filtro por tipo */}
      <div className="flex gap-2" role="group" aria-label="Filtrar por tipo">
        {(['todos', 'gasto', 'ingreso'] as const).map(f => (
          <button key={f} type="button" onClick={() => setFilterTipo(f)} aria-pressed={filterTipo === f}
            className={`text-sm px-3.5 py-1.5 rounded-full font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
              filterTipo === f ? 'bg-slate-900 text-white dark:bg-teal-600' : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50'
            }`}>
            {f === 'todos' ? 'Todas' : f === 'gasto' ? 'Gastos' : 'Ingresos'} <span className="opacity-70 tabular-nums">{counts[f]}</span>
          </button>
        ))}
      </div>

      {loadError ? (
        <ErrorState message={loadError} onRetry={() => { setLoading(true); fetchCategories() }} />
      ) : loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {[1, 2, 3, 4, 5, 6].map(i => <div key={i} className="card h-[4.5rem] animate-pulse bg-slate-100" />)}
        </div>
      ) : displayed.length === 0 ? (
        <EmptyState
          title={filterTipo === 'todos' ? 'Aún no tienes categorías' : `Aún no tienes categorías de ${filterTipo === 'gasto' ? 'gasto' : 'ingreso'}`}
          description="Las categorías te ayudan a ver en qué se va tu dinero."
          actionLabel="Crear la primera"
          onAction={openCreate}
        />
      ) : (
        <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {displayed.map(cat => (
            <li key={cat.id} className="card p-3 sm:p-4 flex items-center gap-3 group">
              <span className={`w-11 h-11 rounded-xl flex items-center justify-center text-2xl flex-shrink-0 ${cat.tipo === 'gasto' ? 'bg-red-50' : 'bg-emerald-50'}`} aria-hidden>
                {cat.icono || '📁'}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-slate-900 truncate">{cat.nombre}</p>
                <span className={cat.tipo === 'gasto' ? 'badge-red' : 'badge-green'}>{cat.tipo === 'gasto' ? '↓ Gasto' : '↑ Ingreso'}</span>
              </div>
              <div className="flex items-center gap-1 reveal-on-hover transition-opacity flex-shrink-0">
                <button type="button" onClick={() => openEdit(cat)} title="Editar" aria-label={`Editar categoría ${cat.nombre}`}
                  className="p-2 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125" />
                  </svg>
                </button>
                <button type="button" onClick={() => handleDelete(cat)} title="Eliminar" aria-label={`Eliminar categoría ${cat.nombre}`}
                  className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
                  </svg>
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
