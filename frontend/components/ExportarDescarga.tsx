'use client'

import { useId, useRef, useState } from 'react'
import apiClient from '@/lib/api-client'
import { apiErrorMessage, useDialog } from '@/components/DialogProvider'
import { usePeriodStore } from '@/store/period'
import { monthTitle } from '@/lib/month-stats'
import {
  type FormatoExportacion, MAX_MESES_EXPORTAR, MENSAJE_ERROR_DEFECTO,
  errorDeBlob, nombreDeArchivo, nombreDesdeContentDisposition, rangoValido,
} from '@/lib/exportar'

const FORMATOS: { valor: FormatoExportacion; titulo: string; detalle: string }[] = [
  { valor: 'csv', titulo: 'CSV', detalle: 'Texto separado por «;»' },
  { valor: 'xlsx', titulo: 'Excel (.xlsx)', detalle: 'Formato más seguro' },
]

/**
 * Botón «Descargar» (CHG-018, UC-015): exporta las transacciones del período que se está viendo
 * (o de un rango de hasta 12 meses) a CSV o Excel. Los montos van siempre en COP.
 * El servidor valida todo otra vez; aquí solo se evita pedir un rango que se sabe inválido.
 */
export default function ExportarDescarga() {
  const mesActual = usePeriodStore(s => s.mes)
  const { notify } = useDialog()
  const [abierto, setAbierto] = useState(false)
  const [formato, setFormato] = useState<FormatoExportacion>('csv')
  const [desde, setDesde] = useState(mesActual)
  const [hasta, setHasta] = useState(mesActual)
  const [cargando, setCargando] = useState(false)
  const [errorDescarga, setErrorDescarga] = useState('')
  const botonRef = useRef<HTMLButtonElement>(null)
  const panelId = useId()
  const idDesde = useId()
  const idHasta = useId()
  const idMotivo = useId()

  const rango = rangoValido(desde, hasta)

  const alternar = () => {
    if (!abierto) {
      // El período que ya se está viendo es el valor inicial
      setDesde(mesActual)
      setHasta(mesActual)
      setErrorDescarga('')
    }
    setAbierto(a => !a)
  }

  const cerrar = () => {
    setAbierto(false)
    botonRef.current?.focus()
  }

  const descargar = async () => {
    if (!rango.ok || cargando) return
    setCargando(true)
    setErrorDescarga('')
    try {
      const res = await apiClient.get('/api/v1/exportaciones/transacciones', {
        params: { desde, hasta, formato },
        responseType: 'blob',
      })
      const nombre = nombreDesdeContentDisposition(
        res.headers?.['content-disposition'] as string | undefined,
        nombreDeArchivo(desde, hasta, formato),
      )
      const url = URL.createObjectURL(res.data as Blob)
      const enlace = document.createElement('a')
      enlace.href = url
      enlace.download = nombre
      document.body.appendChild(enlace)
      enlace.click()
      enlace.remove()
      setTimeout(() => URL.revokeObjectURL(url), 10000)
      notify(`Descarga lista: ${nombre}`, 'success')
    } catch (err) {
      // Con responseType 'blob' el error llega como Blob: se lee su JSON antes de mostrarlo
      const mensaje = apiErrorMessage(await errorDeBlob(err), MENSAJE_ERROR_DEFECTO)
      setErrorDescarga(mensaje)
      notify(mensaje, 'error')
    } finally {
      setCargando(false)
    }
  }

  const periodo = desde === hasta ? monthTitle(desde) : `${monthTitle(desde)} a ${monthTitle(hasta)}`

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <button
          ref={botonRef}
          type="button"
          onClick={alternar}
          aria-expanded={abierto}
          aria-controls={abierto ? panelId : undefined}
          className="btn-secondary inline-flex items-center gap-2"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
          </svg>
          Descargar
        </button>
      </div>

      {abierto && (
        <form
          id={panelId}
          aria-label="Descargar transacciones"
          className="card p-4 sm:p-5 space-y-4"
          onSubmit={e => { e.preventDefault(); void descargar() }}
          onKeyDown={e => { if (e.key === 'Escape') cerrar() }}
        >
          <div>
            <h2 className="text-sm font-bold text-slate-900 dark:text-white">Descargar transacciones</h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              Los ingresos y gastos del período, en un archivo para abrir en Excel u otra hoja de cálculo.
            </p>
          </div>

          <fieldset>
            <legend className="label">Formato</legend>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {FORMATOS.map(f => (
                <label
                  key={f.valor}
                  className={`flex flex-col p-3 rounded-lg border-2 cursor-pointer text-sm has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-blue-500 has-[:focus-visible]:ring-offset-2 dark:has-[:focus-visible]:ring-offset-slate-900 transition-colors ${
                    formato === f.valor
                      ? 'border-blue-600 bg-blue-50 text-blue-900 dark:bg-blue-900/30 dark:text-blue-100 dark:border-blue-400'
                      : 'border-slate-200 text-slate-700 hover:border-slate-300 dark:border-slate-700 dark:text-slate-200 dark:hover:border-slate-500'
                  }`}
                >
                  <input type="radio" name="formato-exportacion" className="sr-only" value={f.valor}
                    checked={formato === f.valor} onChange={() => setFormato(f.valor)} />
                  <span className="font-semibold">{f.titulo}</span>
                  <span className="text-xs text-slate-500 dark:text-slate-400">{f.detalle}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label htmlFor={idDesde} className="label">Desde (mes)</label>
              <input id={idDesde} type="month" value={desde} onChange={e => setDesde(e.target.value)}
                min="2000-01" max="2100-12" required autoComplete="off" placeholder="AAAA-MM"
                aria-invalid={!rango.ok} aria-describedby={!rango.ok ? idMotivo : undefined} className="input-field" />
            </div>
            <div>
              <label htmlFor={idHasta} className="label">Hasta (mes)</label>
              <input id={idHasta} type="month" value={hasta} onChange={e => setHasta(e.target.value)}
                min="2000-01" max="2100-12" required autoComplete="off" placeholder="AAAA-MM"
                aria-invalid={!rango.ok} aria-describedby={!rango.ok ? idMotivo : undefined} className="input-field" />
            </div>
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 -mt-2">
            Puedes elegir hasta {MAX_MESES_EXPORTAR} meses por archivo.
          </p>

          {!rango.ok && (
            <p id={idMotivo} role="alert" className="text-sm text-red-700 dark:text-red-400">{rango.motivo}</p>
          )}
          {errorDescarga && rango.ok && (
            <p role="alert" className="text-sm text-red-700 dark:text-red-400">{errorDescarga}</p>
          )}

          <ul className="text-xs text-slate-600 dark:text-slate-300 space-y-1 list-disc pl-4">
            <li>El archivo siempre va en pesos colombianos (COP), tal como se guardan, aunque veas otra moneda en la app.</li>
            {formato === 'csv'
              ? <li>El CSV usa «;» y coma decimal. Si tu Excel está en inglés y el CSV se ve en una sola columna, descarga el .xlsx.</li>
              : <li>El .xlsx guarda fechas y montos como datos reales y es el formato que conviene si tu Excel está en inglés.</li>}
          </ul>

          <div className="flex flex-wrap items-center justify-end gap-2">
            <button type="button" onClick={cerrar} className="btn-secondary">Cerrar</button>
            <button type="submit" disabled={!rango.ok || cargando} aria-busy={cargando}
              aria-describedby={!rango.ok ? idMotivo : undefined} className="btn-primary">
              {cargando ? 'Descargando…' : `Descargar ${formato === 'xlsx' ? 'Excel' : 'CSV'}`}
            </button>
          </div>
          <span className="sr-only" aria-live="polite">{rango.ok ? `Período a descargar: ${periodo}` : ''}</span>
        </form>
      )}
    </div>
  )
}
