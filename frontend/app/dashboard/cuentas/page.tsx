'use client'

/**
 * Cuentas de dinero (CHG-019 fase a, UC-016, CT-012): dónde está tu dinero. Crear, renombrar, corregir el saldo
 * inicial, archivar / restaurar y eliminar (solo si no tiene movimientos). El saldo lo calcula el servidor en COP;
 * aquí se muestra en la moneda elegida. Las reglas (saldo no negativo, tope de 20, nombre único) viven en el backend.
 */
import React, { useCallback, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import apiClient, { hasStoredSession } from '@/lib/api-client'
import { useDialog } from '@/components/DialogProvider'
import ErrorState from '@/components/ErrorState'
import PageHeader from '@/components/PageHeader'
import EmptyState from '@/components/EmptyState'
import MoneyPrefix from '@/components/MoneyPrefix'
import { useCurrencyStore } from '@/store/currency'
import {
  TIPOS_CUENTA, NOMBRE_CUENTA_MAX, normalizarCuentas, separarCuentas, tipoLabel, estadoLabel, esTarjeta,
  textoSaldo, notaDeuda, validarCuenta, cambiosCuenta, mensajeErrorCuenta, type Cuenta, type TipoCuenta,
} from '@/lib/cuentas'

type Formulario = { id: string | null; nombre: string; tipo: TipoCuenta; saldo: string }
const FORM_VACIO: Formulario = { id: null, nombre: '', tipo: 'efectivo', saldo: '' }

export default function CuentasPage() {
  const router = useRouter()
  const fmt = useCurrencyStore(s => s.fmt)
  const toInput = useCurrencyStore(s => s.toInput)
  const toBase = useCurrencyStore(s => s.toBase)
  const { confirm, notify } = useDialog()

  const [cuentas, setCuentas] = useState<Cuenta[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [form, setForm] = useState<Formulario | null>(null)
  // Saldo inicial tal como se mostró al abrir la edición: si no se toca, se conserva el valor exacto (CHG-013)
  const [saldoOriginal, setSaldoOriginal] = useState('')
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState('')
  const [trabajando, setTrabajando] = useState<string | null>(null)

  const fetchCuentas = useCallback((isActive: () => boolean = () => true) => {
    return apiClient.get('/api/v1/cuentas?incluir_archivadas=true')
      .then(res => {
        if (!isActive()) return
        setCuentas(normalizarCuentas(res.data))
        setLoadError('')
      })
      .catch(err => {
        if (isActive()) setLoadError(mensajeErrorCuenta(err, 'No se pudieron cargar tus cuentas.'))
      })
      .finally(() => {
        if (isActive()) setLoading(false)
      })
  }, [])

  useEffect(() => {
    if (!hasStoredSession()) { router.push('/auth/login'); return }
    let active = true
    fetchCuentas(() => active)
    return () => { active = false }
  }, [fetchCuentas, router])

  const openCreate = () => { setForm({ ...FORM_VACIO }); setSaldoOriginal(''); setFormError('') }
  const openEdit = (c: Cuenta) => {
    const texto = toInput(c.saldo_inicial)
    setForm({ id: c.id, nombre: c.nombre, tipo: c.tipo ?? 'efectivo', saldo: texto })
    setSaldoOriginal(texto)
    setFormError('')
  }
  const closeForm = () => { setForm(null); setFormError('') }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form) return
    const editando = cuentas.find(c => c.id === form.id) ?? null
    // El monto se escribe en la moneda elegida y se guarda en COP; sin tocar, se conserva el valor exacto
    const saldoBase = toBase(form.saldo, editando ? { base: editando.saldo_inicial, text: saldoOriginal } : undefined)
    const tipo = editando ? (editando.tipo ?? form.tipo) : form.tipo
    const problema = validarCuenta({ nombre: form.nombre, tipo, saldoInicial: saldoBase })
    if (problema) { setFormError(problema); return }
    setSaving(true)
    setFormError('')
    try {
      if (editando) {
        const cambios = cambiosCuenta(editando, { nombre: form.nombre, saldoInicial: saldoBase })
        if (Object.keys(cambios).length > 0) await apiClient.put(`/api/v1/cuentas/${editando.id}`, cambios)
      } else {
        await apiClient.post('/api/v1/cuentas', { nombre: form.nombre.trim(), tipo: form.tipo, saldo_inicial: saldoBase })
      }
      await fetchCuentas()
      notify(editando ? 'Cuenta actualizada' : 'Cuenta creada', 'success')
      closeForm()
    } catch (err) {
      setFormError(mensajeErrorCuenta(err, 'No se pudo guardar la cuenta.'))
    } finally {
      setSaving(false)
    }
  }

  const toggleArchivada = async (c: Cuenta) => {
    const archivar = !c.archivada
    const ok = await confirm({
      title: archivar ? `¿Archivar «${c.nombre}»?` : `¿Restaurar «${c.nombre}»?`,
      description: archivar
        ? 'Quedará congelada: no podrás registrar, editar ni eliminar transacciones con ella hasta restaurarla. Su saldo y su historial se conservan.'
        : 'Volverá a estar disponible para registrar transacciones.',
      confirmLabel: archivar ? 'Archivar' : 'Restaurar',
    })
    if (!ok) return
    setTrabajando(c.id)
    try {
      await apiClient.put(`/api/v1/cuentas/${c.id}`, { archivada: archivar })
      await fetchCuentas()
      notify(archivar ? 'Cuenta archivada' : 'Cuenta restaurada', 'success')
    } catch (err) {
      notify(mensajeErrorCuenta(err, archivar ? 'No se pudo archivar la cuenta.' : 'No se pudo restaurar la cuenta.'), 'error')
    } finally {
      setTrabajando(null)
    }
  }

  const handleDelete = async (c: Cuenta) => {
    const ok = await confirm({
      title: `¿Eliminar «${c.nombre}»?`,
      description: 'Solo se puede eliminar una cuenta sin transacciones. Esta acción no se puede deshacer; si tiene movimientos, archívala.',
      confirmLabel: 'Eliminar',
      danger: true,
    })
    if (!ok) return
    setTrabajando(c.id)
    try {
      await apiClient.delete(`/api/v1/cuentas/${c.id}`)
      setCuentas(prev => prev.filter(x => x.id !== c.id))
      if (form?.id === c.id) closeForm()
      notify('Cuenta eliminada', 'success')
    } catch (err) {
      notify(mensajeErrorCuenta(err, 'No se pudo eliminar la cuenta.'), 'error')
    } finally {
      setTrabajando(null)
    }
  }

  const { activas, archivadas } = separarCuentas(cuentas)
  const creando = form !== null && form.id === null
  const editandoCuenta = form?.id ? cuentas.find(c => c.id === form.id) ?? null : null
  const tipoFormulario = editandoCuenta ? (editandoCuenta.tipo ?? form!.tipo) : form?.tipo

  const tarjeta = (c: Cuenta) => {
    const deuda = notaDeuda(c)
    const ocupada = trabajando === c.id
    return (
      <li key={c.id} className={`card p-4 flex flex-col gap-3 ${c.archivada ? 'opacity-90' : ''}`}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-slate-900 truncate" title={c.nombre}>{c.nombre}</p>
            <div className="mt-1 flex flex-wrap items-center gap-1.5">
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-600">{tipoLabel(c.tipo)}</span>
              {c.archivada && <span className="badge-amber">{estadoLabel(true)}</span>}
            </div>
          </div>
          <div className="text-right flex-shrink-0">
            <p className="text-xs text-slate-500">{deuda ? 'Deuda' : 'Saldo'}</p>
            <p className={`text-base sm:text-lg font-bold tabular-nums whitespace-nowrap ${c.saldo !== null && c.saldo < 0 ? 'text-red-600' : 'text-slate-900'}`}>
              {textoSaldo(c.saldo, fmt)}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-3">
          <button type="button" onClick={() => openEdit(c)} disabled={ocupada} aria-label={`Editar cuenta ${c.nombre}`} className="btn-secondary !py-1.5 !px-3 text-xs disabled:opacity-50">Editar</button>
          <button type="button" onClick={() => toggleArchivada(c)} disabled={ocupada} aria-label={`${c.archivada ? 'Restaurar' : 'Archivar'} cuenta ${c.nombre}`} className="btn-secondary !py-1.5 !px-3 text-xs disabled:opacity-50">
            {c.archivada ? 'Restaurar' : 'Archivar'}
          </button>
          <button type="button" onClick={() => handleDelete(c)} disabled={ocupada} aria-label={`Eliminar cuenta ${c.nombre}`} className="btn-secondary !py-1.5 !px-3 text-xs !text-red-600 dark:!text-red-400 disabled:opacity-50">Eliminar</button>
        </div>
      </li>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Cuentas"
        subtitle="Dónde está tu dinero: efectivo, bancos, billeteras y tarjetas"
        actions={
          <button type="button" onClick={creando ? closeForm : openCreate} className="btn-primary" aria-expanded={creando}>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            {creando ? 'Cancelar' : 'Nueva cuenta'}
          </button>
        }
      />

      {form && (
        <form onSubmit={handleSubmit} className="card p-4 sm:p-6 space-y-4 animate-slide-in" aria-labelledby="cta-form-titulo" noValidate>
          <div className="flex items-center justify-between">
            <h2 id="cta-form-titulo" className="text-sm font-bold text-slate-900">{form.id ? 'Editar cuenta' : 'Nueva cuenta'}</h2>
            <button type="button" onClick={closeForm} aria-label="Cerrar formulario" className="w-9 h-9 flex items-center justify-center rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 text-xl leading-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">&times;</button>
          </div>
          {formError && <div role="alert" className="p-3 rounded-lg bg-red-50 border border-red-200 text-sm font-medium text-red-700">{formError}</div>}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label htmlFor="cta-nombre" className="label">Nombre</label>
              <input id="cta-nombre" type="text" value={form.nombre} onChange={e => setForm(p => p && ({ ...p, nombre: e.target.value }))}
                placeholder="Ej.: Efectivo, Bancolombia, Nequi" required maxLength={NOMBRE_CUENTA_MAX} autoComplete="off" className="input-field" autoFocus />
            </div>
            <div>
              <label htmlFor="cta-tipo" className="label">Tipo</label>
              {form.id ? (
                <>
                  <input id="cta-tipo" type="text" value={tipoLabel(tipoFormulario)} readOnly aria-describedby="cta-tipo-ayuda" className="input-field opacity-80" />
                  <p id="cta-tipo-ayuda" className="text-xs text-slate-500 mt-1">El tipo no se puede cambiar.</p>
                </>
              ) : (
                <select id="cta-tipo" value={form.tipo} onChange={e => setForm(p => p && ({ ...p, tipo: e.target.value as TipoCuenta }))} className="input-field">
                  {TIPOS_CUENTA.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
              )}
            </div>
          </div>

          <div>
            <label htmlFor="cta-saldo" className="label">Saldo inicial</label>
            <div className="relative">
              <MoneyPrefix />
              <input id="cta-saldo" type="number" inputMode="decimal" step="0.01" value={form.saldo} onChange={e => setForm(p => p && ({ ...p, saldo: e.target.value }))}
                min={tipoFormulario && esTarjeta(tipoFormulario) ? undefined : 0} placeholder="0" aria-describedby="cta-saldo-ayuda" className="input-field !pl-12" />
            </div>
            <p id="cta-saldo-ayuda" className="text-xs text-slate-500 mt-1">
              {tipoFormulario && esTarjeta(tipoFormulario)
                ? 'Lo que tienes hoy en esta cuenta. En una tarjeta de crédito, escribe la deuda con signo negativo (puede ser 0).'
                : 'Lo que tienes hoy en esta cuenta (puede ser 0). El saldo actual se calcula solo con tus transacciones.'}
            </p>
          </div>

          <div className="flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
            <button type="button" onClick={closeForm} className="btn-secondary">Cancelar</button>
            <button type="submit" disabled={saving} className="btn-primary disabled:opacity-50">
              {saving ? 'Guardando…' : form.id ? 'Guardar cambios' : 'Crear cuenta'}
            </button>
          </div>
        </form>
      )}

      {loadError ? (
        <ErrorState message={loadError} onRetry={() => { setLoading(true); fetchCuentas() }} />
      ) : loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3" role="status" aria-label="Cargando cuentas">
          {[1, 2, 3].map(i => <div key={i} className="card h-28 animate-pulse bg-slate-100" />)}
        </div>
      ) : cuentas.length === 0 ? (
        <EmptyState
          title="Aún no tienes cuentas"
          description="Crea tu primera cuenta (por ejemplo, tu efectivo o tu banco) con el saldo que tienes hoy y elígela al registrar transacciones."
          actionLabel="Crear mi primera cuenta"
          onAction={openCreate}
        />
      ) : (
        <>
          {activas.length > 0 ? (
            <section aria-labelledby="cta-activas">
              <h2 id="cta-activas" className="text-sm font-bold text-slate-900 mb-3">Mis cuentas <span className="text-slate-500 font-normal tabular-nums">({activas.length})</span></h2>
              <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">{activas.map(tarjeta)}</ul>
            </section>
          ) : (
            <p className="text-sm text-slate-500">No tienes cuentas sin archivar. Crea una nueva o restaura una archivada.</p>
          )}
          {archivadas.length > 0 && (
            <section aria-labelledby="cta-archivadas">
              <h2 id="cta-archivadas" className="text-sm font-bold text-slate-900 mb-1">Archivadas <span className="text-slate-500 font-normal tabular-nums">({archivadas.length})</span></h2>
              <p className="text-xs text-slate-500 mb-3">Están congeladas: no admiten transacciones nuevas hasta que las restaures.</p>
              <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">{archivadas.map(tarjeta)}</ul>
            </section>
          )}
        </>
      )}
    </div>
  )
}
