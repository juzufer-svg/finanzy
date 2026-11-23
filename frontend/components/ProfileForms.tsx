'use client'

/**
 * Formularios del perfil (CHG-012, A4): cambiar el nombre y cambiar la contraseña.
 * Cambiar la contraseña cierra las sesiones de los otros dispositivos; esta sigue abierta porque
 * el proxy guarda en la cookie el token nuevo que entrega el backend (INV-027).
 */
import React, { useState } from 'react'
import apiClient from '@/lib/api-client'
import { apiErrorMessage, useDialog } from '@/components/DialogProvider'

export function EditNameForm({ current, onSaved, onCancel }: {
  current: string
  onSaved: (fullName: string) => void
  onCancel: () => void
}) {
  const [nombre, setNombre] = useState(current)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      const { data } = await apiClient.put('/api/v1/users/me', { full_name: nombre })
      onSaved(data.full_name)
    } catch (err) {
      setError(apiErrorMessage(err, 'No se pudo guardar el nombre.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-2">
      <label htmlFor="perfil-nombre" className="text-xs text-slate-500 font-medium">Nombre completo</label>
      <input id="perfil-nombre" type="text" value={nombre} onChange={e => setNombre(e.target.value)}
        required minLength={2} maxLength={100} autoComplete="name" autoFocus className="input-field" />
      {error && <p role="alert" className="text-xs font-medium text-red-600 dark:text-red-400">{error}</p>}
      <div className="flex gap-2">
        <button type="submit" disabled={saving || nombre.trim().length < 2} className="btn-primary !min-h-[2.25rem] !py-1.5 disabled:opacity-50">
          {saving ? 'Guardando…' : 'Guardar'}
        </button>
        <button type="button" onClick={onCancel} className="btn-secondary !min-h-[2.25rem] !py-1.5">Cancelar</button>
      </div>
    </form>
  )
}

export function ChangePasswordCard() {
  const { notify } = useDialog()
  const [actual, setActual] = useState('')
  const [nueva, setNueva] = useState('')
  const [repetir, setRepetir] = useState('')
  const [show, setShow] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const largoOk = nueva.length >= 8 && nueva.length <= 128
  const coinciden = nueva === repetir
  const distinta = nueva !== actual

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (!largoOk) { setError('La nueva contraseña debe tener entre 8 y 128 caracteres.'); return }
    if (!coinciden) { setError('Las contraseñas nuevas no coinciden.'); return }
    if (!distinta) { setError('La nueva contraseña debe ser distinta de la actual.'); return }
    setSaving(true)
    try {
      await apiClient.post('/api/v1/users/me/password', { actual, nueva })
      setActual(''); setNueva(''); setRepetir('')
      notify('Contraseña actualizada. Cerramos tu sesión en los demás dispositivos.', 'success')
    } catch (err) {
      setError(apiErrorMessage(err, 'No se pudo cambiar la contraseña.'))
    } finally {
      setSaving(false)
    }
  }

  const tipo = show ? 'text' : 'password'

  return (
    <div className="card p-5">
      <h2 className="text-sm font-bold text-slate-900 mb-1 flex items-center gap-2">
        <span className="w-6 h-6 bg-amber-100 rounded flex items-center justify-center" aria-hidden>
          <svg className="w-3.5 h-3.5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z" />
          </svg>
        </span>
        Seguridad
      </h2>
      <p className="text-xs text-slate-500 mb-4 pb-3 border-b border-slate-100">
        Al cambiar la contraseña se cierra tu sesión en los demás dispositivos. En este sigues conectado.
      </p>
      <form onSubmit={submit} className="grid grid-cols-1 md:grid-cols-3 gap-4 items-start" noValidate>
        <div>
          <label htmlFor="pw-actual" className="label">Contraseña actual</label>
          <input id="pw-actual" type={tipo} value={actual} onChange={e => setActual(e.target.value)}
            required maxLength={128} autoComplete="current-password" className="input-field" />
        </div>
        <div>
          <label htmlFor="pw-nueva" className="label">Nueva contraseña</label>
          <input id="pw-nueva" type={tipo} value={nueva} onChange={e => setNueva(e.target.value)}
            required minLength={8} maxLength={128} autoComplete="new-password" className="input-field" aria-describedby="pw-nueva-ayuda" />
          <p id="pw-nueva-ayuda" className={`text-xs mt-1 ${nueva && !largoOk ? 'text-red-600 dark:text-red-400' : 'text-slate-500'}`}>Mínimo 8 caracteres.</p>
        </div>
        <div>
          <label htmlFor="pw-repetir" className="label">Repite la nueva</label>
          <input id="pw-repetir" type={tipo} value={repetir} onChange={e => setRepetir(e.target.value)}
            required maxLength={128} autoComplete="new-password" className="input-field" aria-invalid={!!repetir && !coinciden} />
          {repetir && !coinciden && <p className="text-xs mt-1 text-red-600 dark:text-red-400">No coincide.</p>}
        </div>
        {error && <p role="alert" className="md:col-span-3 p-3 rounded-lg bg-red-50 border border-red-200 text-sm font-medium text-red-700">{error}</p>}
        <div className="md:col-span-3 flex flex-col-reverse sm:flex-row sm:items-center sm:justify-between gap-3">
          <label className="inline-flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
            <input type="checkbox" checked={show} onChange={e => setShow(e.target.checked)} className="w-4 h-4 rounded border-slate-300 text-blue-600 focus-visible:ring-2 focus-visible:ring-blue-500" />
            Mostrar contraseñas
          </label>
          <button type="submit" disabled={saving || !actual || !nueva || !repetir} className="btn-primary disabled:opacity-50">
            {saving ? 'Cambiando…' : 'Cambiar contraseña'}
          </button>
        </div>
      </form>
    </div>
  )
}
