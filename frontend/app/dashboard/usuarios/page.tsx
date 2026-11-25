'use client'

/**
 * Panel de administración de usuarios (CHG-023, UC-017 · REQ-F-021): solo para el Dueño.
 * La autorización la hace el backend en cada petición: si responde 404 (no es el Dueño, o cualquier fallo al
 * autorizar) se muestra «Página no encontrada», sin pistas de que el panel exista (INV-053), igual que el Monitor.
 * Solo se muestran cantidades y datos básicos (INV-055): nunca montos ni datos financieros de otras personas.
 * La contraseña del Dueño (para eliminar) vive solo en el estado del diálogo mientras está abierto: no se guarda
 * en ningún almacenamiento y se borra al cerrarlo o ante cualquier error.
 */
import React, { useEffect, useId, useRef, useState } from 'react'
import Link from 'next/link'
import apiClient from '@/lib/api-client'
import { apiErrorMessage, useDialog } from '@/components/DialogProvider'
import ErrorState from '@/components/ErrorState'
import PageHeader from '@/components/PageHeader'
import {
  EXITO_ACCION, FILTROS_ESTADO, MAX_BUSQUEDA, busquedaValida, etiquetaAccion, etiquetaEstado, filtrarPorEstado,
  formatCantidad, formatFecha, formatFechaHora, formatUltimoAcceso, mensajeDeError, normalizarAuditoria, normalizarDetalle,
  normalizarLista, validarEliminar,
  type AccionUsuario, type EstadoUsuario, type FiltroEstado, type UsuarioAdmin,
} from '@/lib/usuarios'

const RETARDO_BUSQUEDA_MS = 350

/** Mensaje claro por código HTTP (CT-013); si no tiene propio, el genérico de la app. */
function textoError(err: unknown, accion: AccionUsuario | undefined, fallback: string): string {
  const e = err as { response?: { status?: number; data?: { detail?: unknown } } }
  return mensajeDeError(e?.response?.status, e?.response?.data?.detail, accion) ?? apiErrorMessage(err, fallback)
}

interface Resultado<T> { clave: string; datos: T | null; error: string; noEncontrada: boolean }

/**
 * Consulta GET con guardia de «activo»: una respuesta vieja nunca pisa a una nueva. `url` nulo = no consultar.
 * `version` sube para forzar otra consulta de la misma dirección (Actualizar, tras una acción).
 */
function useConsulta<T>(url: string | null, version: number, normalizar: (raw: unknown) => T | null, errorBase: string) {
  const [res, setRes] = useState<Resultado<T> | null>(null)
  const clave = url === null ? null : `${url}#${version}`
  useEffect(() => {
    if (clave === null || url === null) return
    let activo = true
    apiClient.get(url)
      .then(r => {
        if (!activo) return
        const datos = normalizar(r.data)
        setRes({ clave, datos, error: datos ? '' : 'No se pudo leer la respuesta del servidor.', noEncontrada: false })
      })
      .catch(err => {
        if (!activo) return
        const nf = err?.response?.status === 404
        setRes({ clave, datos: null, error: nf ? '' : textoError(err, undefined, errorBase), noEncontrada: nf })
      })
    return () => { activo = false }
  }, [clave, url, normalizar, errorBase])
  return {
    datos: res?.datos ?? null,
    error: res?.error ?? '',
    noEncontrada: res?.noEncontrada ?? false,
    cargando: clave !== null && res?.clave !== clave,
    consultado: res !== null,
  }
}

const CLASE_ESTADO: Record<EstadoUsuario, string> = { activa: 'badge-green', suspendida: 'badge-red', pendiente: 'badge-amber' }

/** El estado va siempre con texto (no solo color). */
function BadgeEstado({ estado }: { estado: EstadoUsuario }) {
  return <span className={CLASE_ESTADO[estado]}>{etiquetaEstado(estado)}</span>
}

function BadgeTu() {
  return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-700">Tú</span>
}

function Paginacion({ etiqueta, pagina, total, onCambiar, deshabilitado }: {
  etiqueta: string; pagina: number; total: number; onCambiar: (p: number) => void; deshabilitado: boolean
}) {
  return (
    <nav aria-label={etiqueta} className="flex items-center justify-between gap-3">
      <button type="button" className="btn-secondary disabled:opacity-50" disabled={deshabilitado || pagina <= 1} onClick={() => onCambiar(pagina - 1)}>
        <span aria-hidden>←</span> Anterior<span className="sr-only"> página</span>
      </button>
      <p className="text-sm text-slate-600" aria-live="polite">Página {pagina} de {total}</p>
      <button type="button" className="btn-secondary disabled:opacity-50" disabled={deshabilitado || pagina >= total} onClick={() => onCambiar(pagina + 1)}>
        Siguiente<span className="sr-only"> página</span> <span aria-hidden>→</span>
      </button>
    </nav>
  )
}

/** Diálogo de eliminar (INV-058): correo escrito + contraseña del Dueño. Se desmonta al cerrar: el estado se descarta. */
function EliminarDialog({ usuario, onCerrar, onEliminado }: {
  usuario: UsuarioAdmin; onCerrar: () => void; onEliminado: () => void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const refContrasena = useRef<HTMLInputElement>(null)
  const idTitulo = useId()
  const idCorreo = useId()
  const idContrasena = useId()
  const idAyuda = useId()
  const [correo, setCorreo] = useState('')
  const [contrasena, setContrasena] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const el = ref.current
    if (el && !el.open) el.showModal()
    return () => { if (el?.open) el.close() }
  }, [])

  const { valido } = validarEliminar(correo, usuario.correo, contrasena)

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!valido || enviando || !usuario.id) return
    setEnviando(true)
    setError('')
    try {
      await apiClient.delete(`/api/v1/admin/usuarios/${usuario.id}`, {
        data: { confirmar_correo: correo.trim(), contrasena_dueno: contrasena },
      })
      setContrasena('')
      onEliminado()
    } catch (err) {
      setError(textoError(err, 'eliminar', 'No se pudo eliminar la cuenta.'))
      setContrasena('') // la contraseña no se conserva tras un intento
      refContrasena.current?.focus()
    } finally {
      setEnviando(false)
    }
  }

  return (
    <dialog
      ref={ref}
      aria-labelledby={idTitulo}
      aria-describedby={idAyuda}
      onCancel={e => { e.preventDefault(); if (!enviando) onCerrar() }}
      onClick={e => { if (e.target === ref.current && !enviando) onCerrar() }}
      className="overscroll-contain m-auto w-[calc(100%-2rem)] max-w-md rounded-2xl p-0 shadow-2xl bg-white text-slate-900 dark:bg-slate-800 dark:text-slate-100 backdrop:bg-slate-900/60"
    >
      <form onSubmit={enviar} className="p-6 space-y-4" autoComplete="off">
        <h2 id={idTitulo} className="text-lg font-bold">Eliminar la cuenta de {usuario.correo}</h2>
        <p id={idAyuda} className="text-sm text-slate-600">
          Se borran la cuenta y todos sus datos. Esta acción es irreversible. Para confirmar, escribe el correo de la cuenta y tu contraseña.
        </p>
        <div>
          <label htmlFor={idCorreo} className="label">Correo de la cuenta a eliminar</label>
          <input
            id={idCorreo} type="email" value={correo} onChange={e => setCorreo(e.target.value)}
            autoComplete="off" autoFocus maxLength={255} spellCheck={false} placeholder={usuario.correo}
            aria-invalid={correo.length > 0 && !valido} className="input-field"
          />
        </div>
        <div>
          <label htmlFor={idContrasena} className="label">Tu contraseña</label>
          <input
            id={idContrasena} ref={refContrasena} type="password" value={contrasena} onChange={e => setContrasena(e.target.value)}
            autoComplete="current-password" maxLength={128} className="input-field"
          />
        </div>
        <div aria-live="assertive">
          {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-800">{error}</p>}
        </div>
        <div className="flex justify-end gap-3 pt-2">
          <button type="button" className="btn-secondary" onClick={onCerrar} disabled={enviando}>Cancelar</button>
          <button type="submit" className="btn-danger disabled:opacity-50" disabled={!valido || enviando}>
            {enviando ? 'Eliminando…' : 'Eliminar cuenta'}
          </button>
        </div>
      </form>
    </dialog>
  )
}

function Dato({ etiqueta, children }: { etiqueta: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 text-sm py-1.5">
      <dt className="text-slate-500">{etiqueta}</dt>
      <dd className="font-semibold text-slate-900 text-right break-all">{children}</dd>
    </div>
  )
}

export default function UsuariosPage() {
  const { confirm, notify } = useDialog()
  const idBuscar = useId()
  const idEstado = useId()
  const [q, setQ] = useState('')
  const [qAplicada, setQAplicada] = useState('')
  const [pagina, setPagina] = useState(1)
  const [filtro, setFiltro] = useState<FiltroEstado>('todos')
  const [versionLista, setVersionLista] = useState(0)
  const [paginaAud, setPaginaAud] = useState(1)
  const [versionAud, setVersionAud] = useState(0)
  const [detalleId, setDetalleId] = useState<string | null>(null)
  const [versionDetalle, setVersionDetalle] = useState(0)
  const [accionando, setAccionando] = useState(false)
  const [errorAccion, setErrorAccion] = useState('')
  const [eliminando, setEliminando] = useState<UsuarioAdmin | null>(null)
  const tituloDetalle = useRef<HTMLHeadingElement>(null)

  // Búsqueda con retardo corto: solo se aplica si es válida (1 a 60 caracteres, sin control)
  useEffect(() => {
    const t = setTimeout(() => { if (busquedaValida(q)) setQAplicada(q.trim()) }, RETARDO_BUSQUEDA_MS)
    return () => clearTimeout(t)
  }, [q])

  const urlLista = `/api/v1/admin/usuarios?pagina=${pagina}${qAplicada ? `&q=${encodeURIComponent(qAplicada)}` : ''}`
  const lista = useConsulta(urlLista, versionLista, normalizarLista, 'No se pudo cargar la lista de usuarios.')
  const urlDetalle = detalleId ? `/api/v1/admin/usuarios/${detalleId}` : null
  const detalle = useConsulta(urlDetalle, versionDetalle, normalizarDetalle, 'No se pudo cargar el detalle del usuario.')
  // La auditoría solo se pide cuando ya se confirmó al Dueño con la lista
  const urlAud = lista.datos ? `/api/v1/admin/auditoria?pagina=${paginaAud}` : null
  const auditoria = useConsulta(urlAud, versionAud, normalizarAuditoria, 'No se pudo cargar el registro de acciones.')

  useEffect(() => { if (detalleId) tituloDetalle.current?.focus() }, [detalleId])

  const recargarTodo = () => {
    setVersionLista(v => v + 1)
    setVersionAud(v => v + 1)
    if (detalleId) setVersionDetalle(v => v + 1)
  }

  const abrirDetalle = (id: string) => {
    setErrorAccion('')
    setDetalleId(id)
    setVersionDetalle(v => v + 1)
  }

  const ejecutar = async (accion: Exclude<AccionUsuario, 'eliminar'>, u: UsuarioAdmin) => {
    if (!u.id || accionando) return
    const textos = {
      suspender: { title: `¿Suspender la cuenta de ${u.correo}?`, description: 'La persona pierde el acceso al instante (también sus sesiones abiertas) y no podrá iniciar sesión hasta que la reactives. Se desconecta su WhatsApp.', confirmLabel: 'Suspender', danger: true },
      reactivar: { title: `¿Reactivar la cuenta de ${u.correo}?`, description: 'Podrá iniciar sesión de nuevo con una sesión nueva. Las sesiones anteriores no se recuperan.', confirmLabel: 'Reactivar', danger: false },
      'cerrar-sesiones': { title: `¿Cerrar las sesiones de ${u.correo}?`, description: 'Tendrá que iniciar sesión de nuevo en todos sus dispositivos. Se desconecta su WhatsApp.', confirmLabel: 'Cerrar sesiones', danger: true },
    }[accion]
    if (!(await confirm(textos))) return
    setAccionando(true)
    setErrorAccion('')
    try {
      await apiClient.post(`/api/v1/admin/usuarios/${u.id}/${accion}`)
      notify(EXITO_ACCION[accion], 'success')
      recargarTodo()
    } catch (err) {
      const msg = textoError(err, accion, 'No se pudo completar la acción.')
      setErrorAccion(msg)
      notify(msg, 'error')
      recargarTodo() // el estado pudo cambiar (409) o la cuenta desaparecer (404)
    } finally {
      setAccionando(false)
    }
  }

  const trasEliminar = () => {
    setEliminando(null)
    setDetalleId(null)
    notify(EXITO_ACCION.eliminar, 'success')
    recargarTodo()
  }

  if (lista.noEncontrada) {
    return (
      <div className="py-16 text-center">
        <h1 className="page-title">Página no encontrada</h1>
        <p className="page-subtitle">La página que buscas no existe.</p>
        <Link href="/dashboard" className="btn-primary mt-6">Ir al inicio</Link>
      </div>
    )
  }

  // Hasta confirmar la respuesta no se muestra nada del panel (ni el título): a quien no es el Dueño le llega 404
  if (!lista.datos) {
    return lista.cargando ? (
      <div className="flex justify-center py-16" role="status" aria-label="Cargando">
        <div className="w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
      </div>
    ) : (
      <ErrorState message={lista.error || 'No se pudo cargar la página.'} onRetry={() => setVersionLista(v => v + 1)} />
    )
  }

  const datos = lista.datos
  const visibles = filtrarPorEstado(datos.usuarios, filtro)
  const busquedaInvalida = !busquedaValida(q)
  const d = detalle.datos
  const detalleEsDueno = d?.es_dueno === true

  const actualizar = (
    <button type="button" onClick={recargarTodo} disabled={lista.cargando} className="btn-secondary disabled:opacity-60">
      {lista.cargando ? 'Actualizando…' : 'Actualizar'}
    </button>
  )

  return (
    <div className="space-y-6">
      <PageHeader
        title="Usuarios"
        subtitle={<>Administración de cuentas · Actualizado: <span aria-live="polite">{formatFechaHora(datos.generado_en)}</span></>}
        actions={actualizar}
      />

      {detalleId && (
        <section aria-labelledby="usuarios-detalle" className="card p-4 sm:p-5 space-y-3">
          <div className="flex items-start justify-between gap-3">
            <h2 id="usuarios-detalle" ref={tituloDetalle} tabIndex={-1} className="text-base font-bold text-slate-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded">
              Detalle del usuario
            </h2>
            <button type="button" className="btn-secondary" onClick={() => { setDetalleId(null); setErrorAccion('') }}>Cerrar detalle</button>
          </div>
          {detalle.error ? (
            <ErrorState message={detalle.error} onRetry={() => setVersionDetalle(v => v + 1)} />
          ) : detalle.noEncontrada || (!d && !detalle.cargando) ? (
            <p role="alert" className="text-sm font-medium text-red-700">Esa cuenta ya no existe. Actualiza la lista.</p>
          ) : !d ? (
            <div className="flex justify-center py-6" role="status" aria-label="Cargando detalle">
              <div className="w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : (
            <>
              <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 divide-y sm:divide-y-0 divide-slate-100">
                <Dato etiqueta="Correo">{d.correo}</Dato>
                <Dato etiqueta="Nombre">{d.nombre || '—'}</Dato>
                <Dato etiqueta="Estado"><BadgeEstado estado={d.estado} /></Dato>
                <Dato etiqueta="Moneda">{d.moneda || '—'}</Dato>
                <Dato etiqueta="Registrado">{formatFechaHora(d.registrado_en)}</Dato>
                <Dato etiqueta="Último acceso">{formatUltimoAcceso(d.ultimo_acceso)}</Dato>
                <Dato etiqueta="WhatsApp conectado">{d.uso.whatsapp_conectado === null ? '—' : d.uso.whatsapp_conectado ? 'Sí' : 'No'}</Dato>
                <Dato etiqueta="Transacciones">{formatCantidad(d.uso.transacciones)}</Dato>
                <Dato etiqueta="Categorías">{formatCantidad(d.uso.categorias)}</Dato>
                <Dato etiqueta="Presupuestos">{formatCantidad(d.uso.presupuestos)}</Dato>
                <Dato etiqueta="Metas">{formatCantidad(d.uso.metas)}</Dato>
                <Dato etiqueta="Recurrentes">{formatCantidad(d.uso.recurrentes)}</Dato>
              </dl>
              <p className="text-xs text-slate-500">Solo se muestran cantidades; los montos y movimientos de las personas no son visibles desde este panel.</p>
              {errorAccion && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-800">{errorAccion}</p>}
              {detalleEsDueno ? (
                <p className="text-sm text-slate-600">Es tu cuenta: no tiene acciones disponibles desde el panel.</p>
              ) : (
                <div className="flex flex-wrap gap-2 pt-1">
                  {d.estado === 'activa' && (
                    <button type="button" className="btn-secondary" disabled={accionando} onClick={() => ejecutar('suspender', d)}>Suspender</button>
                  )}
                  {d.estado === 'suspendida' && (
                    <button type="button" className="btn-primary" disabled={accionando} onClick={() => ejecutar('reactivar', d)}>Reactivar</button>
                  )}
                  <button type="button" className="btn-secondary" disabled={accionando} onClick={() => ejecutar('cerrar-sesiones', d)}>Cerrar sesiones</button>
                  <button type="button" className="btn-danger" disabled={accionando} onClick={() => { setErrorAccion(''); setEliminando(d) }}>Eliminar cuenta</button>
                </div>
              )}
            </>
          )}
        </section>
      )}

      <section aria-labelledby="usuarios-lista" className="space-y-3">
        <div>
          <h2 id="usuarios-lista" className="text-base font-bold text-slate-900">Cuentas registradas</h2>
          <p className="text-sm text-slate-500" aria-live="polite">
            {datos.total === 0 ? 'Sin resultados.' : `${formatCantidad(datos.total)} ${datos.total === 1 ? 'cuenta' : 'cuentas'} · 25 por página`}
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-[1fr_14rem] gap-3">
          <div>
            <label htmlFor={idBuscar} className="label">Buscar por correo o nombre</label>
            <input
              id={idBuscar} type="search" value={q} maxLength={MAX_BUSQUEDA} autoComplete="off" spellCheck={false}
              onChange={e => { setQ(e.target.value); setPagina(1) }}
              aria-invalid={busquedaInvalida} className="input-field" placeholder="Ej.: ana@ejemplo.com"
            />
            {busquedaInvalida && <p role="alert" className="mt-1 text-xs font-medium text-red-700">La búsqueda no puede tener caracteres de control.</p>}
          </div>
          <div>
            <label htmlFor={idEstado} className="label">Estado (esta página)</label>
            <select id={idEstado} value={filtro} onChange={e => setFiltro(e.target.value as FiltroEstado)} className="input-field">
              {FILTROS_ESTADO.map(f => <option key={f.valor} value={f.valor}>{f.etiqueta}</option>)}
            </select>
          </div>
        </div>

        <div aria-busy={lista.cargando} className={lista.cargando ? 'opacity-60 transition-opacity' : 'transition-opacity'}>
          {visibles.length === 0 ? (
            <div className="card p-6 text-center text-sm text-slate-600" role="status">
              {datos.usuarios.length === 0
                ? (qAplicada ? 'Ninguna cuenta coincide con la búsqueda.' : 'Aún no hay cuentas registradas.')
                : 'Ninguna cuenta de esta página tiene ese estado.'}
            </div>
          ) : (
            <>
              {/* Escritorio: tabla */}
              <div className="card hidden md:block overflow-x-auto">
                <table className="w-full text-sm">
                  <caption className="sr-only">Cuentas registradas, página {datos.pagina} de {datos.total_paginas}</caption>
                  <thead>
                    <tr className="text-left text-xs text-slate-500 border-b border-slate-200">
                      <th scope="col" className="py-3 pl-4 pr-3 font-semibold">Correo</th>
                      <th scope="col" className="py-3 px-2 font-semibold">Nombre</th>
                      <th scope="col" className="py-3 px-2 font-semibold">Registro</th>
                      <th scope="col" className="py-3 px-2 font-semibold">Estado</th>
                      <th scope="col" className="py-3 px-2 font-semibold">Moneda</th>
                      <th scope="col" className="py-3 px-2 font-semibold">Último acceso</th>
                      <th scope="col" className="py-3 px-2 font-semibold text-right">Transacciones</th>
                      <th scope="col" className="py-3 pl-2 pr-4 font-semibold text-right"><span className="sr-only">Acciones</span></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {visibles.map(u => (
                      <tr key={u.id ?? 'dueno'} className="text-slate-800">
                        <th scope="row" className="py-3 pl-4 pr-3 font-medium text-left break-all">
                          {u.correo} {u.es_dueno && <BadgeTu />}
                        </th>
                        <td className="py-3 px-2">{u.nombre || '—'}</td>
                        <td className="py-3 px-2 whitespace-nowrap">{formatFecha(u.registrado_en)}</td>
                        <td className="py-3 px-2"><BadgeEstado estado={u.estado} /></td>
                        <td className="py-3 px-2">{u.moneda || '—'}</td>
                        <td className="py-3 px-2 whitespace-nowrap">{formatUltimoAcceso(u.ultimo_acceso)}</td>
                        <td className="py-3 px-2 text-right">{formatCantidad(u.uso.transacciones)}</td>
                        <td className="py-3 pl-2 pr-4 text-right">
                          {u.id && (
                            <button type="button" className="btn-secondary" onClick={() => abrirDetalle(u.id as string)}>
                              Ver detalle<span className="sr-only"> de {u.correo}</span>
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Celular: tarjetas */}
              <ul className="md:hidden space-y-3">
                {visibles.map(u => (
                  <li key={u.id ?? 'dueno'} className="card p-4 space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <p className="font-semibold text-slate-900 break-all">{u.correo}</p>
                      {u.es_dueno ? <BadgeTu /> : <BadgeEstado estado={u.estado} />}
                    </div>
                    <dl className="text-sm space-y-1">
                      <div className="flex justify-between gap-3"><dt className="text-slate-500">Nombre</dt><dd className="text-slate-900 text-right">{u.nombre || '—'}</dd></div>
                      {u.es_dueno && <div className="flex justify-between gap-3"><dt className="text-slate-500">Estado</dt><dd><BadgeEstado estado={u.estado} /></dd></div>}
                      <div className="flex justify-between gap-3"><dt className="text-slate-500">Registro</dt><dd className="text-slate-900 text-right">{formatFecha(u.registrado_en)}</dd></div>
                      <div className="flex justify-between gap-3"><dt className="text-slate-500">Moneda</dt><dd className="text-slate-900 text-right">{u.moneda || '—'}</dd></div>
                      <div className="flex justify-between gap-3"><dt className="text-slate-500">Último acceso</dt><dd className="text-slate-900 text-right">{formatUltimoAcceso(u.ultimo_acceso)}</dd></div>
                      <div className="flex justify-between gap-3"><dt className="text-slate-500">Transacciones</dt><dd className="text-slate-900 text-right">{formatCantidad(u.uso.transacciones)}</dd></div>
                    </dl>
                    {u.id && (
                      <button type="button" className="btn-secondary w-full" onClick={() => abrirDetalle(u.id as string)}>
                        Ver detalle<span className="sr-only"> de {u.correo}</span>
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>

        <Paginacion etiqueta="Paginación de cuentas" pagina={datos.pagina} total={datos.total_paginas} deshabilitado={lista.cargando} onCambiar={setPagina} />
      </section>

      <section aria-labelledby="usuarios-registro" className="space-y-3">
        <div>
          <h2 id="usuarios-registro" className="text-base font-bold text-slate-900">Registro de acciones</h2>
          <p className="text-sm text-slate-500">Lo que has hecho como administrador. Se conserva hasta 365 días.</p>
        </div>
        {auditoria.error ? (
          <ErrorState message={auditoria.error} onRetry={() => setVersionAud(v => v + 1)} />
        ) : !auditoria.datos ? (
          <div className="flex justify-center py-6" role="status" aria-label="Cargando registro de acciones">
            <div className="w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : auditoria.datos.registros.length === 0 ? (
          <div className="card p-6 text-center text-sm text-slate-600" role="status">Aún no has hecho ninguna acción.</div>
        ) : (
          <>
            <div className="card overflow-x-auto" aria-busy={auditoria.cargando}>
              <table className="w-full text-sm">
                <caption className="sr-only">Registro de acciones del administrador, página {auditoria.datos.pagina} de {auditoria.datos.total_paginas}</caption>
                <thead>
                  <tr className="text-left text-xs text-slate-500 border-b border-slate-200">
                    <th scope="col" className="py-3 pl-4 pr-3 font-semibold">Fecha</th>
                    <th scope="col" className="py-3 px-2 font-semibold">Acción</th>
                    <th scope="col" className="py-3 pl-2 pr-4 font-semibold">Usuario afectado</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {auditoria.datos.registros.map(r => (
                    <tr key={r.id} className="text-slate-800">
                      <th scope="row" className="py-3 pl-4 pr-3 font-medium text-left whitespace-nowrap">{formatFechaHora(r.fecha)}</th>
                      <td className="py-3 px-2">{etiquetaAccion(r.accion)}</td>
                      <td className="py-3 pl-2 pr-4 break-all">{r.usuario_correo ?? 'Cuenta eliminada'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Paginacion etiqueta="Paginación del registro de acciones" pagina={auditoria.datos.pagina} total={auditoria.datos.total_paginas} deshabilitado={auditoria.cargando} onCambiar={setPaginaAud} />
          </>
        )}
      </section>

      {eliminando && (
        <EliminarDialog usuario={eliminando} onCerrar={() => setEliminando(null)} onEliminado={trasEliminar} />
      )}
    </div>
  )
}
