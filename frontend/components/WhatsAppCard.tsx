'use client'

/**
 * Conectar WhatsApp (CHG-014): genera un código de un solo uso para enlazar el número y muestra el estado.
 * El registro con IA ocurre en el backend (webhook de Meta); aquí solo se enlaza y desenlaza.
 */
import React, { useCallback, useEffect, useState } from 'react'
import apiClient from '@/lib/api-client'
import { apiErrorMessage, useDialog } from '@/components/DialogProvider'
import ErrorState from '@/components/ErrorState'

interface Estado { configurado: boolean; enlazado: boolean; telefono: string | null }

export default function WhatsAppCard() {
  const { confirm, notify } = useDialog()
  const [estado, setEstado] = useState<Estado | null>(null)
  const [error, setError] = useState('')
  const [codigo, setCodigo] = useState<{ codigo: string; minutos: number } | null>(null)
  const [busy, setBusy] = useState(false)

  const cargar = useCallback((isActive: () => boolean = () => true) => {
    return apiClient.get<Estado>('/api/v1/whatsapp/enlace')
      .then(res => {
        if (!isActive()) return null
        setEstado(res.data)
        setError('')
        if (res.data.enlazado) setCodigo(null)
        return res.data
      })
      .catch(err => {
        if (isActive()) setError(apiErrorMessage(err, 'No se pudo cargar el estado de WhatsApp.'))
      })
  }, [])

  useEffect(() => {
    let active = true
    cargar(() => active)
    return () => { active = false }
  }, [cargar])

  const conectar = async () => {
    setBusy(true)
    try {
      const { data } = await apiClient.post('/api/v1/whatsapp/enlace')
      setCodigo({ codigo: data.codigo, minutos: data.vence_en_minutos })
    } catch (err) {
      notify(apiErrorMessage(err, 'No se pudo generar el código.'), 'error')
    } finally {
      setBusy(false)
    }
  }

  const comprobar = async () => {
    setBusy(true)
    const actual = await cargar()
    setBusy(false)
    if (actual?.enlazado) notify('¡WhatsApp conectado!', 'success')
    else if (actual) notify('Aún no llega el código. Espera unos segundos y vuelve a intentarlo.', 'info')
  }

  const desconectar = async () => {
    const ok = await confirm({
      title: '¿Desconectar WhatsApp?',
      description: 'Dejarás de poder registrar movimientos por WhatsApp hasta que lo conectes de nuevo. Lo ya registrado se conserva.',
      confirmLabel: 'Desconectar',
      danger: true,
    })
    if (!ok) return
    try {
      await apiClient.delete('/api/v1/whatsapp/enlace')
      notify('WhatsApp desconectado', 'success')
      await cargar()
    } catch (err) {
      notify(apiErrorMessage(err, 'No se pudo desconectar.'), 'error')
    }
  }

  return (
    <div className="card p-5">
      <h2 className="text-sm font-bold text-slate-900 mb-1 flex items-center gap-2">
        <span className="w-6 h-6 bg-emerald-100 rounded flex items-center justify-center" aria-hidden>
          <svg className="w-3.5 h-3.5 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.625 12a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H8.25m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H12m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 0 1-2.555-.337A5.972 5.972 0 0 1 5.41 20.97a5.969 5.969 0 0 1-.474-.065 4.48 4.48 0 0 0 .978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25Z" />
          </svg>
        </span>
        WhatsApp
      </h2>
      <p className="text-xs text-slate-500 mb-4 pb-3 border-b border-slate-100">
        Registra ingresos y gastos escribiendo por WhatsApp como hablas: «almorcé por 18 mil con débito». La IA los anota en tu cuenta.
      </p>

      {error ? (
        <ErrorState message={error} onRetry={() => { setError(''); cargar() }} />
      ) : !estado ? (
        <div className="h-16 rounded-lg bg-slate-100 animate-pulse" aria-busy="true" aria-label="Cargando el estado de WhatsApp" role="status" />
      ) : !estado.configurado ? (
        <p className="text-sm text-slate-600">Aún no está activado en el servidor. Cuando se configure (ver la guía de WhatsApp), aquí podrás conectarlo.</p>
      ) : estado.enlazado ? (
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <p className="text-sm text-slate-700">
            <span className="badge-green mr-2">Conectado</span>
            Número terminado en <span className="font-semibold tabular-nums">{estado.telefono?.replace('•••• ', '')}</span>
          </p>
          <button type="button" onClick={desconectar} className="btn-secondary">Desconectar</button>
        </div>
      ) : codigo ? (
        <div className="space-y-3">
          <p className="text-sm text-slate-700">Envía este código por WhatsApp al número de Finanzy (el número de prueba de Meta):</p>
          <p className="text-3xl font-bold tracking-widest text-slate-900 tabular-nums select-all" aria-live="polite">{codigo.codigo}</p>
          <p className="text-xs text-slate-500">Vence en {codigo.minutos} minutos y sirve una sola vez. Te llegará una respuesta de confirmación.</p>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={comprobar} disabled={busy} className="btn-primary disabled:opacity-50">
              {busy ? 'Comprobando…' : 'Ya lo envié'}
            </button>
            <button type="button" onClick={conectar} disabled={busy} className="btn-secondary disabled:opacity-50">Generar otro código</button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <p className="text-sm text-slate-600">Tu WhatsApp no está conectado.</p>
          <button type="button" onClick={conectar} disabled={busy} className="btn-primary disabled:opacity-50">
            {busy ? 'Generando…' : 'Conectar WhatsApp'}
          </button>
        </div>
      )}
    </div>
  )
}
