import React, { useEffect, useRef, useState } from 'react'
import apiClient from '@/lib/api-client'
import { apiErrorMessage } from '@/components/DialogProvider'
import { MEDIOS_PAGO, MEDIO_POR_DEFECTO } from '@/lib/payment-methods'
import { useCurrencyStore } from '@/store/currency'
import MoneyPrefix from '@/components/MoneyPrefix'

interface TransactionFormProps {
  categories: any[]
  onSuccess?: () => void
}

export default function TransactionForm({ categories, onSuccess }: TransactionFormProps) {
  const toBase = useCurrencyStore(s => s.toBase)
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState('')
  const today = new Date()
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
  const [formData, setFormData] = useState({
    categoria_id: '',
    monto: '',
    descripcion: '',
    fecha: todayStr,
    tipo: 'gasto',
    medio_pago: MEDIO_POR_DEFECTO as string,
  })

  // Botón flotante «+» del celular (CHG-012): llega con ?nueva=1, se muestra el formulario y se
  // enfoca el monto. Solo toca el DOM (sin cambiar estado) y quita el parámetro para que recargar no repita.
  const cardRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get('nueva') !== '1') return
    cardRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    document.getElementById('txf-monto')?.focus({ preventScroll: true })
    params.delete('nueva')
    const query = params.toString()
    window.history.replaceState(window.history.state, '', window.location.pathname + (query ? `?${query}` : ''))
  }, [])

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      await apiClient.post('/api/v1/transacciones', {
        ...formData,
        monto: toBase(formData.monto), // escrito en la moneda elegida, se guarda en la base (CHG-013)
        medio_pago: formData.medio_pago || null,
      })
      const t2 = new Date()
      const t2str = `${t2.getFullYear()}-${String(t2.getMonth() + 1).padStart(2, '0')}-${String(t2.getDate()).padStart(2, '0')}`
      // Se conservan el tipo y el medio de pago para registrar varios seguidos más rápido
      setFormData(prev => ({ ...prev, categoria_id: '', monto: '', descripcion: '', fecha: t2str }))
      setSuccess(true)
      setTimeout(() => setSuccess(false), 2000)
      if (onSuccess) onSuccess()
    } catch (err) {
      setError(apiErrorMessage(err, 'No se pudo guardar la transacción.'))
    } finally {
      setLoading(false)
    }
  }

  const filteredCategories = categories.filter(cat => cat.tipo === formData.tipo)

  return (
    <div ref={cardRef} className="card p-5 scroll-mt-20">
      <div className="flex items-center gap-3 mb-5 pb-4 border-b border-slate-100">
        <div className="w-9 h-9 bg-blue-100 rounded-lg flex items-center justify-center">
          <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
        </div>
        <div>
          <h2 className="text-sm font-bold text-slate-900">Nueva Transacción</h2>
          <p className="text-xs text-slate-500">Registra un ingreso o gasto</p>
        </div>
      </div>

      {error && (
        <div role="alert" className="mb-4 p-3 rounded-lg bg-red-50 border border-red-200 text-sm font-medium text-red-700 dark:bg-red-950/40 dark:border-red-900/60 dark:text-red-200">
          {error}
        </div>
      )}
      {success && (
        <div className="mb-4 flex items-center gap-2 p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-emerald-700 text-sm font-medium animate-slide-in">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="m4.5 12.75 6 6 9-13.5" />
          </svg>
          Transacción registrada
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Tipo */}
        <div>
          <span className="label">Tipo</span>
          <div className="grid grid-cols-2 gap-2">
            {['gasto', 'ingreso'].map(tipo => (
              <label key={tipo} className={`flex items-center justify-center gap-2 p-2.5 rounded-lg border-2 cursor-pointer has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-blue-500 has-[:focus-visible]:ring-offset-2 transition-all text-sm font-semibold ${
                formData.tipo === tipo
                  ? tipo === 'gasto'
                    ? 'border-red-500 bg-red-50 text-red-700'
                    : 'border-emerald-500 bg-emerald-50 text-emerald-700'
                  : 'border-slate-200 text-slate-500 hover:border-slate-300'
              }`}>
                <input type="radio" name="tipo" value={tipo} checked={formData.tipo === tipo}
                  onChange={handleChange} className="sr-only" />
                {tipo === 'gasto' ? (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.25 6 9 12.75l4.286-4.286a11.948 11.948 0 0 1 4.306 6.43l.776 2.898m0 0 3.182-5.511m-3.182 5.51-5.511-3.181" />
                  </svg>
                ) : (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.25 18 9 11.25l4.306 4.306a11.95 11.95 0 0 1 5.814-5.519l2.74-1.22m0 0-5.94-2.281m5.94 2.28-2.28 5.941" />
                  </svg>
                )}
                {tipo.charAt(0).toUpperCase() + tipo.slice(1)}
              </label>
            ))}
          </div>
        </div>

        {/* Categoría */}
        <div>
          <label htmlFor="txf-categoria" className="label">Categoría</label>
          <select id="txf-categoria" name="categoria_id" value={formData.categoria_id} onChange={handleChange} required className="input-field">
            <option value="">Selecciona una categoría</option>
            {filteredCategories.map(cat => (
              <option key={cat.id} value={cat.id}>{cat.icono ? `${cat.icono} ${cat.nombre}` : cat.nombre}</option>
            ))}
          </select>
          {filteredCategories.length === 0 && (
            <p className="text-xs text-slate-500 mt-1">Aún no tienes categorías de este tipo. Créalas en el menú «Categorías».</p>
          )}
        </div>

        {/* Medio de pago (CHG-007) */}
        <div>
          <label htmlFor="txf-medio" className="label">Medio de pago</label>
          <select id="txf-medio" name="medio_pago" value={formData.medio_pago} onChange={handleChange} className="input-field">
            {MEDIOS_PAGO.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
            <option value="">Sin especificar</option>
          </select>
        </div>

        {/* Monto */}
        <div>
          <label htmlFor="txf-monto" className="label">Monto</label>
          <div className="relative">
            <MoneyPrefix />
            <input id="txf-monto" type="number" name="monto" value={formData.monto} onChange={handleChange}
              required step="0.01" min="0.01" placeholder="0.00"
              className="input-field !pl-12" />
          </div>
        </div>

        {/* Fecha */}
        <div>
          <label htmlFor="txf-fecha" className="label">Fecha</label>
          <input id="txf-fecha" type="date" name="fecha" value={formData.fecha} onChange={handleChange} className="input-field" />
        </div>

        {/* Descripción */}
        <div>
          <label htmlFor="txf-descripcion" className="label">Descripción <span className="text-slate-400 font-normal">(opcional)</span></label>
          <textarea id="txf-descripcion" name="descripcion" value={formData.descripcion} onChange={handleChange}
            className="input-field resize-none" rows={2} placeholder="Añade una nota..." />
        </div>

        <button type="submit" disabled={loading}
          className={`w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg font-semibold text-sm transition-all ${
            loading ? 'bg-slate-200 text-slate-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700 text-white shadow-sm hover:shadow'
          }`}>
          {loading ? (
            <>
              <div className="w-4 h-4 border-2 border-slate-400 border-t-transparent rounded-full animate-spin" />
              Guardando...
            </>
          ) : (
            <>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
              Registrar Transacción
            </>
          )}
        </button>
      </form>
    </div>
  )
}
