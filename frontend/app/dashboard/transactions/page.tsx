'use client'

import React, { useCallback, useEffect, useState } from 'react'
import apiClient, { hasStoredSession } from '@/lib/api-client'
import TransactionForm from '@/components/TransactionForm'
import { useDialog, apiErrorMessage } from '@/components/DialogProvider'
import ErrorState from '@/components/ErrorState'
import { useRouter } from 'next/navigation'
import { useCurrencyStore } from '@/store/currency'
import { filterTransactions, shortDate } from '@/lib/month-stats'
import PageHeader from '@/components/PageHeader'
import PeriodPicker from '@/components/PeriodPicker'
import { usePeriodStore } from '@/store/period'
import { MEDIOS_PAGO, medioPagoLabel } from '@/lib/payment-methods'
import MoneyPrefix from '@/components/MoneyPrefix'
import ExportarDescarga from '@/components/ExportarDescarga'
import { normalizarCuentas, opcionesSelector, nombreDeCuenta, cuentaIdParaPut, mensajeErrorCuenta, type Cuenta } from '@/lib/cuentas'

interface Transaction {
  id: string
  categoria_id: string
  tipo: 'ingreso' | 'gasto'
  monto: number
  descripcion: string
  fecha: string
  medio_pago?: string | null
  cuenta_id?: string | null
}

interface Category {
  id: string
  nombre: string
  tipo: string
  icono?: string
}


function EditTransactionModal({ transaction, categories, cuentas, onClose, onSaved }: {
  transaction: Transaction
  categories: Category[]
  cuentas: Cuenta[]
  onClose: () => void
  onSaved: () => void
}) {
  const toInput = useCurrencyStore(s => s.toInput)
  const toBase = useCurrencyStore(s => s.toBase)
  // Monto en la moneda elegida; si no se toca, se conserva el valor exacto (CHG-013)
  const [montoInicial] = useState(() => toInput(transaction.monto))
  const [formData, setFormData] = useState({
    categoria_id: transaction.categoria_id || '',
    monto: montoInicial,
    descripcion: transaction.descripcion || '',
    fecha: transaction.fecha,
    tipo: transaction.tipo as 'gasto' | 'ingreso',
    medio_pago: transaction.medio_pago || '',
    cuenta_id: transaction.cuenta_id || '',
  })
  // Solo las no archivadas, más la cuenta que la transacción ya tiene (se conserva al editar)
  const opcionesCuenta = opcionesSelector(cuentas, transaction.cuenta_id)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const filteredCats = categories.filter(c => c.tipo === formData.tipo)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const { cuenta_id, ...resto } = formData
      await apiClient.put(`/api/v1/transacciones/${transaction.id}`, {
        ...resto,
        monto: toBase(formData.monto, { base: transaction.monto, text: montoInicial }),
        medio_pago: formData.medio_pago || null,
        // Sin cambio no se envía: conserva la cuenta y no revalida el monto (CT-003 v1.2)
        ...cuentaIdParaPut(transaction.cuenta_id, cuenta_id),
      })
      onSaved()
      onClose()
    } catch (err) {
      setError(mensajeErrorCuenta(err, 'Error al actualizar la transacción'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4 pt-[max(1rem,env(safe-area-inset-top))] pb-[max(1rem,env(safe-area-inset-bottom))]" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-5 sm:p-6 max-h-[calc(100dvh-2rem)] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-base font-bold text-slate-900">Editar Transacción</h3>
          <button type="button" onClick={onClose} aria-label="Cerrar" className="w-9 h-9 flex items-center justify-center rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 text-xl leading-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">&times;</button>
        </div>
        {error && <div role="alert" className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">{error}</div>}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <span className="block text-xs font-semibold text-slate-700 mb-2">Tipo</span>
            <div className="grid grid-cols-2 gap-2">
              {(['gasto', 'ingreso'] as const).map(t => (
                <label key={t} className={`flex items-center justify-center gap-1.5 p-2.5 rounded-lg border-2 cursor-pointer has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-blue-500 has-[:focus-visible]:ring-offset-2 text-sm font-semibold transition-all ${
                  formData.tipo === t
                    ? t === 'gasto' ? 'border-red-500 bg-red-50 text-red-700' : 'border-emerald-500 bg-emerald-50 text-emerald-700'
                    : 'border-slate-200 text-slate-500 hover:border-slate-300'
                }`}>
                  <input type="radio" className="sr-only" checked={formData.tipo === t} onChange={() => setFormData(p => ({...p, tipo: t, categoria_id: ''}))} />
                  {t === 'gasto' ? '↓' : '↑'} {t.charAt(0).toUpperCase() + t.slice(1)}
                </label>
              ))}
            </div>
          </div>
          <div>
            <label htmlFor="txe-categoria" className="block text-xs font-semibold text-slate-700 mb-1.5">Categoría</label>
            <select id="txe-categoria" value={formData.categoria_id} onChange={e => setFormData(p => ({...p, categoria_id: e.target.value}))} required
              className="w-full px-3 py-2.5 text-sm border-2 border-slate-200 rounded-lg focus:border-blue-500 focus:outline-none bg-slate-50 focus:bg-white">
              <option value="">Selecciona una categoría</option>
              {filteredCats.map(c => <option key={c.id} value={c.id}>{c.icono} {c.nombre}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="txe-medio" className="block text-xs font-semibold text-slate-700 mb-1.5">Medio de pago</label>
            <select id="txe-medio" value={formData.medio_pago} onChange={e => setFormData(p => ({...p, medio_pago: e.target.value}))}
              className="w-full px-3 py-2.5 text-sm border-2 border-slate-200 rounded-lg focus:border-blue-500 focus:outline-none bg-slate-50 focus:bg-white">
              {MEDIOS_PAGO.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
              <option value="">Sin especificar</option>
            </select>
          </div>
          <div>
            <label htmlFor="txe-cuenta" className="block text-xs font-semibold text-slate-700 mb-1.5">Cuenta <span className="text-slate-400 font-normal">(opcional)</span></label>
            <select id="txe-cuenta" value={formData.cuenta_id} onChange={e => setFormData(p => ({...p, cuenta_id: e.target.value}))}
              className="w-full px-3 py-2.5 text-sm border-2 border-slate-200 rounded-lg focus:border-blue-500 focus:outline-none bg-slate-50 focus:bg-white">
              <option value="">Sin cuenta</option>
              {opcionesCuenta.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="txe-monto" className="block text-xs font-semibold text-slate-700 mb-1.5">Monto</label>
            <div className="relative">
              <MoneyPrefix />
              <input id="txe-monto" type="number" value={formData.monto} onChange={e => setFormData(p => ({...p, monto: e.target.value}))}
                required step="0.01" min="0.01"
                className="w-full !pl-12 pr-3 py-2.5 text-sm border-2 border-slate-200 rounded-lg focus:border-blue-500 focus:outline-none bg-slate-50 focus:bg-white" />
            </div>
          </div>
          <div>
            <label htmlFor="txe-fecha" className="block text-xs font-semibold text-slate-700 mb-1.5">Fecha</label>
            <input id="txe-fecha" type="date" value={formData.fecha} onChange={e => setFormData(p => ({...p, fecha: e.target.value}))}
              required className="w-full px-3 py-2.5 text-sm border-2 border-slate-200 rounded-lg focus:border-blue-500 focus:outline-none bg-slate-50 focus:bg-white" />
          </div>
          <div>
            <label htmlFor="txe-descripcion" className="block text-xs font-semibold text-slate-700 mb-1.5">Descripción <span className="text-slate-400 font-normal">(opcional)</span></label>
            <textarea id="txe-descripcion" value={formData.descripcion} onChange={e => setFormData(p => ({...p, descripcion: e.target.value}))}
              rows={2} className="w-full px-3 py-2.5 text-sm border-2 border-slate-200 rounded-lg focus:border-blue-500 focus:outline-none bg-slate-50 focus:bg-white resize-none" />
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

function CategorizedView({
  transactions,
  categories,
  cuentas,
  loading,
  onDelete,
  onEdit,
  fmt,
}: {
  transactions: Transaction[]
  categories: Category[]
  cuentas: Cuenta[]
  loading: boolean
  onDelete: (id: string) => void
  onEdit: (t: Transaction) => void
  fmt: (n: number) => string
}) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [activeTab, setActiveTab] = useState<'todos' | 'gasto' | 'ingreso'>('todos')
  // Buscador y filtros (CHG-006): texto en descripción o categoría, sin importar tildes ni mayúsculas
  const [texto, setTexto] = useState('')
  const [categoriaFiltro, setCategoriaFiltro] = useState('')
  const [medioFiltro, setMedioFiltro] = useState('')
  const filtrando = texto.trim() !== '' || categoriaFiltro !== '' || medioFiltro !== ''

  // Con un filtro activo los grupos se muestran abiertos, salvo que el usuario cierre alguno
  const isOpen = (id: string) => (filtrando ? expanded[id] !== false : !!expanded[id])
  const toggle = (id: string) => setExpanded(p => ({ ...p, [id]: !isOpen(id) }))

  const porTipo = activeTab === 'todos' ? transactions : transactions.filter(t => t.tipo === activeTab)
  const filteredTxs = filterTransactions(porTipo, { texto, categoriaId: categoriaFiltro, medioPago: medioFiltro }, categories)
  const categoriasDelTab = categories.filter(c => activeTab === 'todos' || c.tipo === activeTab)
  const netoFiltrado = filteredTxs.reduce((s, t) => s + (t.tipo === 'gasto' ? -t.monto : t.monto), 0)
  const limpiarFiltros = () => { setTexto(''); setCategoriaFiltro(''); setMedioFiltro('') }

  // Cuenta de dinero de la transacción, discreta al final de la línea (CHG-019)
  const cuentaTexto = (tx: Transaction) => {
    const nombre = nombreDeCuenta(cuentas, tx.cuenta_id)
    return nombre ? ` · ${nombre}` : ''
  }

  // Group by category
  const groups = categories
    .map(cat => {
      const txs = filteredTxs.filter(t => t.categoria_id === cat.id)
      if (txs.length === 0) return null
      const total = txs.reduce((s, t) => s + t.monto, 0)
      return { cat, txs, total }
    })
    .filter(Boolean) as { cat: Category; txs: Transaction[]; total: number }[]

  // Transactions with no matching category
  const uncategorized = filteredTxs.filter(t => !categories.find(c => c.id === t.categoria_id))

  return (
    <div className="space-y-4">
      {/* Buscador y filtro por categoría */}
      <div className="card p-3 sm:p-4 flex flex-wrap gap-3 items-end">
        <div className="basis-full min-w-0">
          <label htmlFor="tx-buscar" className="label">Buscar</label>
          <input id="tx-buscar" type="search" value={texto} onChange={e => setTexto(e.target.value)}
            placeholder="Descripción o categoría…" autoComplete="off" className="input-field" />
        </div>
        <div className="flex-1 min-w-[10rem]">
          <label htmlFor="tx-filtro-categoria" className="label">Categoría</label>
          <select id="tx-filtro-categoria" value={categoriaFiltro} onChange={e => setCategoriaFiltro(e.target.value)} className="input-field">
            <option value="">Todas</option>
            {categoriasDelTab.map(c => <option key={c.id} value={c.id}>{c.icono ? `${c.icono} ${c.nombre}` : c.nombre}</option>)}
            <option value="__sin__">Sin categoría</option>
          </select>
        </div>
        <div className="flex-1 min-w-[10rem]">
          <label htmlFor="tx-filtro-medio" className="label">Medio de pago</label>
          <select id="tx-filtro-medio" value={medioFiltro} onChange={e => setMedioFiltro(e.target.value)} className="input-field">
            <option value="">Todos</option>
            {MEDIOS_PAGO.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
            <option value="__sin__">Sin especificar</option>
          </select>
        </div>
        {filtrando && (
          <button type="button" onClick={limpiarFiltros} className="btn-secondary whitespace-nowrap">Limpiar filtros</button>
        )}
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap items-center gap-1.5">
        {(['todos', 'gasto', 'ingreso'] as const).map(tab => (
          <button
            key={tab}
            type="button"
            onClick={() => { setActiveTab(tab); setCategoriaFiltro('') }}
            aria-pressed={activeTab === tab}
            className={`text-xs px-4 py-2 rounded-full font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
              activeTab === tab ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-900' : 'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600'
            }`}
          >
            {tab === 'todos' ? 'Todos' : tab === 'gasto' ? '↓ Gastos' : '↑ Ingresos'}
          </button>
        ))}
        <span className="ml-auto text-xs text-slate-500 tabular-nums" aria-live="polite">
          {filteredTxs.length} {filteredTxs.length === 1 ? 'registro' : 'registros'}{filtrando ? ` · neto ${netoFiltrado < 0 ? '-' : '+'}${fmt(Math.abs(netoFiltrado))}` : ''}
        </span>
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <div className="w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : groups.length === 0 && uncategorized.length === 0 ? (
        <div className="card flex flex-col items-center justify-center py-16 text-center">
          <div className="w-16 h-16 bg-slate-100 rounded-2xl flex items-center justify-center mb-4">
            <svg className="w-8 h-8 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M2.25 8.25h19.5M2.25 9h19.5m-16.5 5.25h6m-6 2.25h3m-3.75 3h15a2.25 2.25 0 0 0 2.25-2.25V6.75A2.25 2.25 0 0 0 19.5 4.5h-15a2.25 2.25 0 0 0-2.25 2.25v10.5A2.25 2.25 0 0 0 4.5 19.5Z" />
            </svg>
          </div>
          <h3 className="text-base font-semibold text-slate-700">{filtrando ? 'Ningún movimiento coincide' : 'Sin transacciones'}</h3>
          <p className="text-sm text-slate-500 mt-1">{filtrando ? 'Prueba con otra palabra u otra categoría.' : 'No hay registros en este período'}</p>
          {filtrando && <button type="button" onClick={limpiarFiltros} className="btn-secondary mt-4">Limpiar filtros</button>}
        </div>
      ) : (
        <div className="space-y-3">
          {groups.map(({ cat, txs, total }) => {
            const abierto = isOpen(cat.id)
            const isGasto = cat.tipo === 'gasto'
            return (
              <div
                key={cat.id}
                className={`card overflow-hidden border-l-4 transition-all ${
                  isGasto ? 'border-red-400' : 'border-emerald-400'
                }`}
              >
                {/* Card header — clickable to expand */}
                <button
                  className="w-full flex items-center gap-3 p-3 sm:p-4 hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500"
                  onClick={() => toggle(cat.id)}
                  aria-expanded={abierto}
                >
                  <span className="text-2xl flex-shrink-0">{cat.icono || '📁'}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-bold text-slate-900 truncate">{cat.nombre}</p>
                    <p className="text-xs text-slate-400 mt-0.5">
                      {txs.length} {txs.length === 1 ? 'transacción' : 'transacciones'}
                    </p>
                  </div>
                  <div className="flex items-center gap-3 flex-shrink-0">
                    <span
                      className={`text-sm sm:text-base font-bold tabular-nums whitespace-nowrap ${isGasto ? 'text-red-600' : 'text-emerald-600'}`}
                    >
                      {isGasto ? '-' : '+'}{fmt(total)}
                    </span>
                    <svg
                      className={`w-4 h-4 text-slate-400 transition-transform ${abierto ? 'rotate-180' : ''}`}
                      fill="none" stroke="currentColor" viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="m19.5 8.25-7.5 7.5-7.5-7.5" />
                    </svg>
                  </div>
                </button>

                {/* Expanded transactions */}
                {abierto && (
                  <div className="border-t border-slate-100 divide-y divide-slate-50">
                    {txs
                      .sort((a, b) => b.fecha.localeCompare(a.fecha))
                      .map(tx => (
                        <div key={tx.id} className="flex items-center gap-3 px-4 py-3 bg-slate-50/50 dark:bg-slate-700/30 group">
                          <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${isGasto ? 'bg-red-400' : 'bg-emerald-400'}`} />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-slate-700 truncate">
                              {tx.descripcion || cat.nombre}
                            </p>
                            <p className="text-xs text-slate-500">{shortDate(tx.fecha)}{tx.medio_pago ? ` · ${medioPagoLabel(tx.medio_pago)}` : ''}{cuentaTexto(tx)}</p>
                          </div>
                          <div className="flex items-center gap-1 flex-shrink-0">
                            <span className={`text-sm font-semibold tabular-nums whitespace-nowrap ${isGasto ? 'text-red-600' : 'text-emerald-600'}`}>
                              {isGasto ? '-' : '+'}{fmt(tx.monto)}
                            </span>
                            <button
                              onClick={() => onEdit(tx)}
                              className="p-2 hover:bg-blue-100 dark:hover:bg-blue-900/40 rounded-lg text-slate-400 hover:text-blue-500 dark:hover:text-blue-400 reveal-on-hover transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                              title="Editar"
                              aria-label={`Editar ${tx.descripcion || cat.nombre} del ${shortDate(tx.fecha)}`}
                            >
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125" />
                              </svg>
                            </button>
                            <button
                              onClick={() => onDelete(tx.id)}
                              className="p-2 hover:bg-red-100 dark:hover:bg-red-900/40 rounded-lg text-slate-400 hover:text-red-500 dark:hover:text-red-400 reveal-on-hover transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
                              title="Eliminar"
                              aria-label={`Eliminar ${tx.descripcion || cat.nombre} del ${shortDate(tx.fecha)}`}
                            >
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
                              </svg>
                            </button>
                          </div>
                        </div>
                      ))}
                  </div>
                )}
              </div>
            )
          })}

          {/* Uncategorized fallback */}
          {uncategorized.length > 0 && (
            <div className="card overflow-hidden border-l-4 border-slate-300">
              <button
                className="w-full flex items-center gap-3 p-3 sm:p-4 hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500"
                onClick={() => toggle('__uncategorized__')}
                aria-expanded={isOpen('__uncategorized__')}
              >
                <span className="text-2xl flex-shrink-0" aria-hidden>📁</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-bold text-slate-900">Sin categoría</p>
                  <p className="text-xs text-slate-400 mt-0.5">{uncategorized.length} {uncategorized.length === 1 ? 'transacción' : 'transacciones'}</p>
                </div>
                <svg
                  className={`w-4 h-4 text-slate-400 transition-transform ${isOpen('__uncategorized__') ? 'rotate-180' : ''}`}
                  fill="none" stroke="currentColor" viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="m19.5 8.25-7.5 7.5-7.5-7.5" />
                </svg>
              </button>
              {isOpen('__uncategorized__') && (
                <div className="border-t border-slate-100 divide-y divide-slate-50">
                  {uncategorized.map(tx => (
                    <div key={tx.id} className="flex items-center gap-3 px-4 py-3 bg-slate-50/50 dark:bg-slate-700/30 group">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-slate-700 truncate">{tx.descripcion || '—'}</p>
                        <p className="text-xs text-slate-500">{shortDate(tx.fecha)}{tx.medio_pago ? ` · ${medioPagoLabel(tx.medio_pago)}` : ''}{cuentaTexto(tx)}</p>
                      </div>
                      <div className="flex items-center gap-1 flex-shrink-0">
                        <span className={`text-sm font-semibold tabular-nums whitespace-nowrap ${tx.tipo === 'gasto' ? 'text-red-600' : 'text-emerald-600'}`}>
                          {tx.tipo === 'gasto' ? '-' : '+'}{fmt(tx.monto)}
                        </span>
                        {/* Permite asignarles una categoría (p. ej. tras borrar la que tenían) */}
                        <button onClick={() => onEdit(tx)} title="Editar" aria-label="Editar transacción"
                          className="p-2 hover:bg-blue-100 dark:hover:bg-blue-900/40 rounded-lg text-slate-400 hover:text-blue-500 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125" />
                          </svg>
                        </button>
                        <button onClick={() => onDelete(tx.id)} title="Eliminar" aria-label="Eliminar transacción"
                          className="p-2 hover:bg-red-100 dark:hover:bg-red-900/40 rounded-lg text-slate-400 hover:text-red-500 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500">
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18 18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function TransactionsPage() {
  const router = useRouter()
  const fmt = useCurrencyStore(s => s.fmt)
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [cuentas, setCuentas] = useState<Cuenta[]>([])
  const [loading, setLoading] = useState(true)
  // Período compartido por todas las vistas (CHG-009)
  const currentMonth = usePeriodStore(s => s.mes)
  // Mes de los datos en pantalla: si no coincide con el período, se está cargando el nuevo
  const [loadedMonth, setLoadedMonth] = useState<string | null>(null)
  const stale = loadedMonth !== null && loadedMonth !== currentMonth
  const [editingTransaction, setEditingTransaction] = useState<Transaction | null>(null)
  const [loadError, setLoadError] = useState('')
  const { confirm, notify } = useDialog()

  // isActive permite ignorar respuestas que llegan tarde (cambio de mes o vista cerrada)
  const fetchData = useCallback((isActive: () => boolean = () => true) => {
    return Promise.all([
      apiClient.get(`/api/v1/transacciones?mes=${currentMonth}`),
      apiClient.get('/api/v1/categorias'),
      // Las cuentas son un extra: si fallan, las transacciones se siguen viendo y registrando sin cuenta
      apiClient.get('/api/v1/cuentas?incluir_archivadas=true').then(r => normalizarCuentas(r.data)).catch(() => [] as Cuenta[]),
    ])
      .then(([transRes, catRes, cuentasRes]) => {
        if (!isActive()) return
        setTransactions(transRes.data)
        setCategories(catRes.data)
        setCuentas(cuentasRes)
        setLoadError('')
      })
      .catch(err => {
        if (isActive()) setLoadError(apiErrorMessage(err, 'No se pudieron cargar tus transacciones.'))
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

  const handleDelete = async (id: string) => {
    const ok = await confirm({
      title: '¿Eliminar esta transacción?',
      description: 'Esta acción no se puede deshacer.',
      confirmLabel: 'Eliminar',
      danger: true,
    })
    if (!ok) return
    try {
      await apiClient.delete(`/api/v1/transacciones/${id}`)
      setTransactions(prev => prev.filter(t => t.id !== id))
      notify('Transacción eliminada', 'success')
    } catch (err) {
      notify(apiErrorMessage(err, 'No se pudo eliminar la transacción.'), 'error')
    }
  }

  const income = transactions.filter(t => t.tipo === 'ingreso').reduce((s, t) => s + t.monto, 0)
  const expenses = transactions.filter(t => t.tipo === 'gasto').reduce((s, t) => s + t.monto, 0)

  return (
    <div className="space-y-6">
      {editingTransaction && (
        <EditTransactionModal
          transaction={editingTransaction}
          categories={categories}
          cuentas={cuentas}
          onClose={() => setEditingTransaction(null)}
          onSaved={fetchData}
        />
      )}

      <PageHeader
        wideActions
        title="Transacciones"
        subtitle="Ingresos y gastos del período"
        actions={<PeriodPicker />}
      />

      <ExportarDescarga />

      {/* Mini stats */}
      <div className={`grid grid-cols-2 sm:grid-cols-3 gap-3 sm:gap-4 transition-opacity ${stale ? 'opacity-50' : ''}`} aria-busy={stale}>
        <div className="card p-3 sm:p-4 border-l-4 border-emerald-400 min-w-0">
          <p className="text-xs text-slate-500">Ingresos</p>
          <p className="text-base sm:text-xl font-bold text-emerald-600 mt-0.5 tabular-nums break-words">{fmt(income)}</p>
        </div>
        <div className="card p-3 sm:p-4 border-l-4 border-red-400 min-w-0">
          <p className="text-xs text-slate-500">Gastos</p>
          <p className="text-base sm:text-xl font-bold text-red-600 mt-0.5 tabular-nums break-words">{fmt(expenses)}</p>
        </div>
        <div className="card p-3 sm:p-4 border-l-4 border-blue-400 min-w-0 col-span-2 sm:col-span-1">
          <p className="text-xs text-slate-500">Balance</p>
          <p className={`text-base sm:text-xl font-bold mt-0.5 tabular-nums break-words ${(income - expenses) >= 0 ? 'text-blue-600' : 'text-red-600'}`}>
            {fmt(income - expenses)}
          </p>
        </div>
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1">
          <TransactionForm categories={categories} cuentas={cuentas} onSuccess={fetchData} />
        </div>
        <div className="lg:col-span-2">
          {loadError ? (
            <ErrorState message={loadError} onRetry={() => { setLoading(true); fetchData() }} />
          ) : (
          <CategorizedView
            transactions={transactions}
            categories={categories}
            cuentas={cuentas}
            loading={loading || stale}
            onDelete={handleDelete}
            onEdit={setEditingTransaction}
            fmt={fmt}
          />
          )}
        </div>
      </div>
    </div>
  )
}
