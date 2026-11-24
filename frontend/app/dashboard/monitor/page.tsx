'use client'

/**
 * Monitor de consumos (CHG-017, UC-014 · REQ-F-018): solo lectura y solo para el Dueño.
 * La autorización la hace el backend en cada petición: si responde 404 (no es el Dueño, o cualquier
 * fallo al autorizar) se muestra «Página no encontrada», sin pistas de que el Monitor exista (INV-031).
 * Los montos de las plataformas vienen en USD y se muestran tal cual (no pasan por el conversor de moneda).
 * Nunca se muestran ni se guardan tokens: la respuesta del backend no los incluye.
 */
import React, { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import apiClient from '@/lib/api-client'
import { apiErrorMessage } from '@/components/DialogProvider'
import ErrorState from '@/components/ErrorState'
import PageHeader from '@/components/PageHeader'
import {
  PLATAFORMAS, TEXTO_NO_DISPONIBLE, alturasApiladas, camposVisibles, diaDeInstante, estadoPlataforma,
  formatFechaDia, formatInstante, formatNumero, normalizarResumen, notaPlataforma, porcentajeUso, serieDias, total,
  type NombrePlataforma, type Plataforma, type PuntoDia, type ResumenMonitor,
} from '@/lib/monitor'

const COLOR_A = '#2563eb' // azul primario
const COLOR_B = '#00B89C' // verde azulado de marca

interface SerieDef { nombre: string; color: string; valor: (p: PuntoDia) => number }
interface GraficoDef { id: string; titulo: string; unidad: string; series: SerieDef[] }

const GRAFICOS: GraficoDef[] = [
  {
    id: 'claude-llamadas', titulo: 'Llamadas a Claude por origen', unidad: 'llamadas',
    series: [
      { nombre: 'Asistente', color: COLOR_A, valor: p => p.claude_llamadas_asistente },
      { nombre: 'WhatsApp', color: COLOR_B, valor: p => p.claude_llamadas_whatsapp },
    ],
  },
  {
    id: 'claude-tokens', titulo: 'Tokens de Claude por origen', unidad: 'tokens',
    series: [
      { nombre: 'Asistente', color: COLOR_A, valor: p => p.claude_tokens_asistente },
      { nombre: 'WhatsApp', color: COLOR_B, valor: p => p.claude_tokens_whatsapp },
    ],
  },
  {
    id: 'brevo-correos', titulo: 'Correos enviados con Brevo', unidad: 'correos',
    series: [{ nombre: 'Correos', color: COLOR_A, valor: p => p.correos }],
  },
  {
    id: 'whatsapp-mensajes', titulo: 'Mensajes de WhatsApp', unidad: 'mensajes',
    series: [
      { nombre: 'Enviados', color: COLOR_A, valor: p => p.wa_enviados },
      { nombre: 'Recibidos', color: COLOR_B, valor: p => p.wa_recibidos },
    ],
  },
]

/** Gráfico de barras apiladas en SVG propio, con resumen para lector de pantalla (la tabla es la alternativa completa). */
function GraficoBarras({ def, serie }: { def: GraficoDef; serie: PuntoDia[] }) {
  const W = 300
  const H = 110
  const paso = W / Math.max(serie.length, 1)
  const ancho = Math.max(paso - 2, 1)
  const maximo = Math.max(0, ...serie.map(p => total(def.series.map(s => s.valor(p)))))
  const totales = def.series.map(s => ({ nombre: s.nombre, suma: total(serie.map(s.valor)) }))
  const resumen = `${def.titulo}, últimos ${serie.length} días: ${totales.map(t => `${t.nombre} ${formatNumero(t.suma)}`).join(', ')} ${def.unidad}.`
  return (
    <figure className="card p-4">
      <figcaption className="text-sm font-bold text-slate-900">{def.titulo}</figcaption>
      <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
        {def.series.map((s, i) => (
          <li key={s.nombre} className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 rounded-sm" style={{ backgroundColor: s.color }} aria-hidden />
            {s.nombre}: <strong className="text-slate-800">{formatNumero(totales[i].suma)}</strong>
          </li>
        ))}
      </ul>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={resumen} className="mt-3 w-full h-28" preserveAspectRatio="none">
        <line x1="0" y1={H - 0.5} x2={W} y2={H - 0.5} stroke="currentColor" className="text-slate-300" strokeWidth="1" />
        {serie.map((p, i) => {
          const alturas = alturasApiladas(def.series.map(s => s.valor(p)), maximo)
          let base = H
          return (
            <g key={p.fecha}>
              {alturas.map((a, j) => {
                const h = (a / 100) * (H - 4)
                base -= h
                return h > 0 ? <rect key={def.series[j].nombre} x={i * paso + 1} y={base} width={ancho} height={h} fill={def.series[j].color} /> : null
              })}
            </g>
          )
        })}
      </svg>
      <div className="mt-1 flex justify-between text-[11px] text-slate-500" aria-hidden>
        <span>{formatFechaDia(serie[0]?.fecha)}</span>
        <span>{formatFechaDia(serie[serie.length - 1]?.fecha)}</span>
      </div>
    </figure>
  )
}

function TarjetaPlataforma({ clave, nombre, plataforma }: { clave: NombrePlataforma; nombre: string; plataforma: Plataforma }) {
  const ok = estadoPlataforma(clave, plataforma) === 'ok'
  const campos = ok ? camposVisibles(clave, plataforma.datos) : []
  const usoBd = clave === 'supabase' ? porcentajeUso(plataforma.datos?.tamano_bd_bytes, plataforma.datos?.limite_bd_bytes) : null
  const usoVercel = clave === 'vercel' ? porcentajeUso(plataforma.datos?.ancho_banda_bytes, plataforma.datos?.limite_ancho_banda_bytes) : null
  const uso = usoBd ?? usoVercel
  const idTitulo = `plat-${clave}`
  return (
    <section className="card p-4 sm:p-5" aria-labelledby={idTitulo}>
      <div className="flex items-start justify-between gap-2">
        <h3 id={idTitulo} className="text-sm font-bold text-slate-900">{nombre}</h3>
        {ok
          ? <span className="badge-green">Disponible</span>
          : <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-600">{TEXTO_NO_DISPONIBLE}</span>}
      </div>
      {ok ? (
        <>
          <dl className="mt-3 space-y-2">
            {campos.map(c => (
              <div key={c.clave} className="flex items-baseline justify-between gap-3 text-sm">
                <dt className="text-slate-500">{c.etiqueta}</dt>
                <dd className="font-semibold text-slate-900 text-right">{c.valor}</dd>
              </div>
            ))}
          </dl>
          {uso !== null && (
            <div className="mt-3">
              <div
                role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={uso}
                aria-label={`Uso del límite en ${nombre}`} className="h-2 rounded-full bg-slate-200 overflow-hidden"
              >
                <div className={`h-full rounded-full ${uso >= 90 ? 'bg-red-500' : uso >= 75 ? 'bg-amber-500' : 'bg-teal-500'}`} style={{ width: `${uso}%` }} />
              </div>
              <p className="mt-1 text-xs text-slate-500">{uso} % del límite</p>
            </div>
          )}
          {notaPlataforma(clave, plataforma.datos) && (
            <p className="mt-3 text-xs text-slate-500">{notaPlataforma(clave, plataforma.datos)}</p>
          )}
          <p className="mt-3 text-xs text-slate-500">Dato de {formatInstante(plataforma.actualizado_en)}</p>
        </>
      ) : (
        <p className="mt-3 text-sm text-slate-500">{TEXTO_NO_DISPONIBLE}</p>
      )}
    </section>
  )
}

function TablaDias({ serie }: { serie: PuntoDia[] }) {
  // Solo los días con algún dato (la tabla es la alternativa textual al gráfico)
  const filas = serie.filter(p => Object.entries(p).some(([k, v]) => k !== 'fecha' && Number(v) > 0))
  return (
    <details className="card p-4">
      <summary className="cursor-pointer text-sm font-bold text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded">
        Ver los datos en una tabla
      </summary>
      {filas.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">Aún sin datos desde la activación.</p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Contadores propios por día (UTC), últimos 30 días</caption>
            <thead>
              <tr className="text-left text-xs text-slate-500 border-b border-slate-200">
                <th scope="col" className="py-2 pr-3 font-semibold">Día (UTC)</th>
                <th scope="col" className="py-2 px-2 font-semibold text-right">Llamadas asistente</th>
                <th scope="col" className="py-2 px-2 font-semibold text-right">Llamadas WhatsApp</th>
                <th scope="col" className="py-2 px-2 font-semibold text-right">Tokens asistente</th>
                <th scope="col" className="py-2 px-2 font-semibold text-right">Tokens WhatsApp</th>
                <th scope="col" className="py-2 px-2 font-semibold text-right">Correos</th>
                <th scope="col" className="py-2 px-2 font-semibold text-right">WhatsApp enviados</th>
                <th scope="col" className="py-2 pl-2 font-semibold text-right">WhatsApp recibidos</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {[...filas].reverse().map(p => (
                <tr key={p.fecha} className="text-slate-800">
                  <th scope="row" className="py-2 pr-3 font-medium text-left whitespace-nowrap">{formatFechaDia(p.fecha)}</th>
                  <td className="py-2 px-2 text-right">{formatNumero(p.claude_llamadas_asistente)}</td>
                  <td className="py-2 px-2 text-right">{formatNumero(p.claude_llamadas_whatsapp)}</td>
                  <td className="py-2 px-2 text-right">{formatNumero(p.claude_tokens_asistente)}</td>
                  <td className="py-2 px-2 text-right">{formatNumero(p.claude_tokens_whatsapp)}</td>
                  <td className="py-2 px-2 text-right">{formatNumero(p.correos)}</td>
                  <td className="py-2 px-2 text-right">{formatNumero(p.wa_enviados)}</td>
                  <td className="py-2 pl-2 text-right">{formatNumero(p.wa_recibidos)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </details>
  )
}

export default function MonitorPage() {
  const [resumen, setResumen] = useState<ResumenMonitor | null>(null)
  const [loading, setLoading] = useState(true)
  const [actualizando, setActualizando] = useState(false)
  const [error, setError] = useState('')
  const [noEncontrada, setNoEncontrada] = useState(false)

  const cargar = useCallback((isActive: () => boolean = () => true) =>
    apiClient.get('/api/v1/monitor/resumen')
      .then(res => {
        if (!isActive()) return
        const normalizado = normalizarResumen(res.data)
        if (!normalizado) {
          setError('No se pudo leer la respuesta del Monitor.')
          return
        }
        setResumen(normalizado)
        setError('')
      })
      .catch(err => {
        if (!isActive()) return
        // 404: no es el Dueño (o falló la autorización). Sin pistas de que el Monitor exista.
        if (err?.response?.status === 404) {
          setResumen(null)
          setError('')
          setNoEncontrada(true)
          return
        }
        setError(apiErrorMessage(err, 'No se pudo cargar el Monitor.'))
      })
      .finally(() => {
        if (!isActive()) return
        setLoading(false)
        setActualizando(false)
      }), [])

  useEffect(() => {
    let active = true
    cargar(() => active)
    return () => { active = false }
  }, [cargar])

  const reintentar = () => {
    setError('')
    if (resumen) setActualizando(true)
    else setLoading(true)
    cargar()
  }

  if (noEncontrada) {
    return (
      <div className="py-16 text-center">
        <h1 className="page-title">Página no encontrada</h1>
        <p className="page-subtitle">La página que buscas no existe.</p>
        <Link href="/dashboard" className="btn-primary mt-6">Ir al inicio</Link>
      </div>
    )
  }

  const botonActualizar = (
    <button type="button" onClick={reintentar} disabled={actualizando} className="btn-secondary disabled:opacity-60">
      {actualizando ? 'Actualizando…' : 'Actualizar'}
    </button>
  )

  // Hasta confirmar la respuesta no se muestra nada del Monitor (ni el título): a quien no es el Dueño
  // le llega un 404 y solo debe ver «Página no encontrada».
  if (!resumen) {
    return loading ? (
      <div className="flex justify-center py-16" role="status" aria-label="Cargando">
        <div className="w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
      </div>
    ) : (
      <ErrorState message={error || 'No se pudo cargar la página.'} onRetry={reintentar} />
    )
  }

  const hoy = diaDeInstante(resumen.generado_en)
  const serie = hoy ? serieDias(resumen.contadores.dias, hoy, 30) : []

  return (
    <div className="space-y-6">
      <PageHeader
        title="Monitor"
        subtitle={<>Consumos de las plataformas · Actualizado: <span aria-live="polite">{formatInstante(resumen.generado_en)}</span></>}
        actions={botonActualizar}
      />

      {error && <ErrorState message={error} onRetry={reintentar} />}

      <>
          <section aria-labelledby="monitor-plataformas" className="space-y-3">
            <div>
              <h2 id="monitor-plataformas" className="text-base font-bold text-slate-900">Plataformas</h2>
              <p className="text-sm text-slate-500">Los montos de dinero están en dólares (USD), tal como los entrega cada plataforma.</p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
              {PLATAFORMAS.map(({ clave, nombre }) => (
                <TarjetaPlataforma key={clave} clave={clave} nombre={nombre} plataforma={resumen.plataformas[clave]} />
              ))}
            </div>
          </section>

          <section aria-labelledby="monitor-contadores" className="space-y-3">
            <div>
              <h2 id="monitor-contadores" className="text-base font-bold text-slate-900">Contadores propios · últimos 30 días</h2>
              <p className="text-sm text-slate-500">
                {resumen.contadores.desde
                  ? `Registrados desde el ${formatFechaDia(resumen.contadores.desde)} (días en UTC).`
                  : 'Aún sin datos desde la activación.'}
              </p>
            </div>
            {serie.length > 0 && resumen.contadores.dias.length > 0 && (
              <>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  {GRAFICOS.map(def => <GraficoBarras key={def.id} def={def} serie={serie} />)}
                </div>
                <TablaDias serie={serie} />
              </>
            )}
          </section>
      </>
    </div>
  )
}
