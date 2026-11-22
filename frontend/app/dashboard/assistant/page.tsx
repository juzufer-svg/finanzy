'use client'

import React, { useEffect, useRef, useState } from 'react'
import apiClient from '@/lib/api-client'
import PageHeader from '@/components/PageHeader'
import { apiErrorMessage } from '@/components/DialogProvider'
import { usePeriodStore } from '@/store/period'
import { monthTitle } from '@/lib/month-stats'

/**
 * Asistente con Claude (CHG-010, CT-007): preguntas en lenguaje natural sobre las finanzas propias.
 * La conversación vive solo en esta pantalla (no se guarda); al backend se envían las últimas
 * preguntas y respuestas para que entienda preguntas de seguimiento.
 */

type Rol = 'usuario' | 'asistente'
interface Mensaje { rol: Rol; texto: string }
interface Respuesta { respuesta: string; modelo: string; uso: { input_tokens: number; output_tokens: number } }

const MAX_PREGUNTA = 500
const MAX_HISTORIAL = 10 // igual que el backend (CT-007)
const MAX_TEXTO_HISTORIAL = 2000

export default function AssistantPage() {
  const mes = usePeriodStore(s => s.mes)
  const nombreMes = monthTitle(mes).toLowerCase()
  const [mensajes, setMensajes] = useState<Mensaje[]>([])
  const [pregunta, setPregunta] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState('')
  const [ultimoUso, setUltimoUso] = useState<Respuesta['uso'] | null>(null)
  const finRef = useRef<HTMLDivElement>(null)
  const campoRef = useRef<HTMLTextAreaElement>(null)

  const sugerencias = [
    `¿Cuáles fueron mis 5 gastos más altos de ${nombreMes}?`,
    `¿En qué categoría gasté más en ${nombreMes}?`,
    `¿Cómo voy con mis presupuestos de ${nombreMes}?`,
    '¿Cuánto llevo ahorrado en mis metas?',
  ]

  // Bajar al último mensaje cuando llega uno nuevo
  useEffect(() => {
    finRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [mensajes, enviando])

  const enviar = async (texto: string) => {
    const limpio = texto.trim()
    if (!limpio || enviando) return
    // Solo se envían intercambios completos (las preguntas que fallaron no van al historial)
    const historial = mensajes.slice(-MAX_HISTORIAL).map(m => ({ ...m, texto: m.texto.slice(0, MAX_TEXTO_HISTORIAL) }))
    setMensajes(prev => [...prev, { rol: 'usuario', texto: limpio }])
    setPregunta('')
    setError('')
    setEnviando(true)
    try {
      const { data } = await apiClient.post<Respuesta>('/api/v1/asistente/chat', { pregunta: limpio, historial })
      setMensajes(prev => [...prev, { rol: 'asistente', texto: data.respuesta }])
      setUltimoUso(data.uso)
    } catch (err: unknown) {
      // Se quita la pregunta fallida y se devuelve al campo para reintentar
      setMensajes(prev => prev.slice(0, -1))
      setPregunta(limpio)
      setError(apiErrorMessage(err, 'El asistente no pudo responder. Intenta de nuevo.'))
    } finally {
      setEnviando(false)
      campoRef.current?.focus()
    }
  }

  const onSubmit = (e: React.FormEvent) => { e.preventDefault(); void enviar(pregunta) }
  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter envía; Shift+Enter hace salto de línea
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      void enviar(pregunta)
    }
  }

  const nuevaConversacion = () => { setMensajes([]); setError(''); setUltimoUso(null); campoRef.current?.focus() }

  return (
    <div className="space-y-4 sm:space-y-6">
      <PageHeader
        title="Asistente IA"
        subtitle="Pregunta en tus palabras por tus gastos, ingresos, presupuestos y metas"
        actions={mensajes.length > 0 && (
          <button type="button" className="btn-secondary" onClick={nuevaConversacion} disabled={enviando}>
            Nueva conversación
          </button>
        )}
      />

      <section className="card flex flex-col min-h-[60dvh]" aria-label="Conversación con el asistente">
        <div className="flex-1 p-3 sm:p-5 space-y-3 overflow-y-auto" aria-live="polite" aria-busy={enviando}>
          {mensajes.length === 0 && (
            <div className="py-6 sm:py-10 text-center">
              <p className="text-sm text-slate-500 mb-4">Prueba con alguna de estas preguntas:</p>
              <div className="flex flex-wrap justify-center gap-2">
                {sugerencias.map(s => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => void enviar(s)}
                    disabled={enviando}
                    className="text-left text-sm px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-slate-700 hover:border-blue-400 hover:text-blue-700 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {mensajes.map((m, i) => (
            <div key={i} className={`flex ${m.rol === 'usuario' ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-[85%] sm:max-w-[75%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap break-words ${
                  m.rol === 'usuario'
                    ? 'bg-blue-600 text-white rounded-br-md'
                    : 'bg-slate-100 text-slate-800 rounded-bl-md'
                }`}
              >
                <span className="sr-only">{m.rol === 'usuario' ? 'Tú: ' : 'Asistente: '}</span>
                {m.texto}
              </div>
            </div>
          ))}

          {enviando && (
            <div className="flex justify-start">
              <div className="rounded-2xl rounded-bl-md px-4 py-3 bg-slate-100 text-slate-500 text-sm">
                <span className="inline-flex gap-1" aria-hidden>
                  <span className="w-1.5 h-1.5 rounded-full bg-current animate-bounce [animation-delay:-0.3s]" />
                  <span className="w-1.5 h-1.5 rounded-full bg-current animate-bounce [animation-delay:-0.15s]" />
                  <span className="w-1.5 h-1.5 rounded-full bg-current animate-bounce" />
                </span>
                <span className="sr-only">El asistente está consultando tus datos…</span>
              </div>
            </div>
          )}
          <div ref={finRef} />
        </div>

        <form onSubmit={onSubmit} className="border-t border-slate-200 p-3 sm:p-4 space-y-2">
          {error && (
            <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>
          )}
          <div className="flex items-end gap-2">
            <label htmlFor="pregunta-asistente" className="sr-only">Escribe tu pregunta</label>
            <textarea
              id="pregunta-asistente"
              ref={campoRef}
              rows={1}
              maxLength={MAX_PREGUNTA}
              autoComplete="off"
              value={pregunta}
              onChange={e => setPregunta(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Escribe tu pregunta…"
              className="input-field resize-none max-h-40"
            />
            <button type="submit" className="btn-primary flex-shrink-0" disabled={enviando || !pregunta.trim()}>
              {enviando ? 'Pensando…' : 'Enviar'}
            </button>
          </div>
          <p className="text-xs text-slate-500">
            Responde con Claude usando solo tus datos y no puede modificarlos. Montos en pesos colombianos.
            {ultimoUso && ` · Última respuesta: ${ultimoUso.input_tokens.toLocaleString('es-CO')} tokens de entrada y ${ultimoUso.output_tokens.toLocaleString('es-CO')} de salida.`}
          </p>
        </form>
      </section>
    </div>
  )
}
