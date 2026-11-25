/**
 * Panel de administración de usuarios del Dueño (CHG-023, UC-017, CT-013): tipos y utilidades puras.
 * Sin dependencias de React ni del navegador, para poder probarlas con `npm test`.
 *
 * Privacidad (INV-055): solo se leen cantidades y datos básicos; cualquier clave que no esté en la lista
 * blanca de aquí se descarta. Nunca hay montos ni datos financieros de otras personas.
 */

export const POR_PAGINA = 25
export const MAX_PAGINA = 400
export const MAX_BUSQUEDA = 60

export type EstadoUsuario = 'activa' | 'pendiente' | 'suspendida'
export type AccionAuditoria = 'suspender' | 'reactivar' | 'cerrar_sesiones' | 'eliminar'
export type FiltroEstado = 'todos' | EstadoUsuario

export interface UsoUsuario {
  transacciones: number | null
  categorias: number | null
  presupuestos: number | null
  metas: number | null
  recurrentes: number | null
  whatsapp_conectado: boolean | null
}

export interface UsuarioAdmin {
  /** `null` en la cuenta del Dueño (el backend no expone su id). */
  id: string | null
  correo: string
  nombre: string
  estado: EstadoUsuario
  moneda: string
  registrado_en: string | null
  ultimo_acceso: string | null
  es_dueno: boolean
  uso: UsoUsuario
}

export interface ListaUsuarios {
  generado_en: string
  pagina: number
  total: number
  total_paginas: number
  usuarios: UsuarioAdmin[]
}

export interface RegistroAuditoria {
  id: number
  fecha: string | null
  accion: AccionAuditoria
  usuario_id: string
  usuario_correo: string | null
}

export interface ListaAuditoria {
  generado_en: string
  pagina: number
  total: number
  total_paginas: number
  registros: RegistroAuditoria[]
}

const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
const ESTADOS: EstadoUsuario[] = ['activa', 'pendiente', 'suspendida']
const ACCIONES: AccionAuditoria[] = ['suspender', 'reactivar', 'cerrar_sesiones', 'eliminar']
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

const esObjeto = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)
const esEntero = (v: unknown): v is number => typeof v === 'number' && Number.isInteger(v) && v >= 0
const texto = (v: unknown, max = 255): string => (typeof v === 'string' ? v.slice(0, max) : '')

/** Colombia está en UTC−5 todo el año: se resta a mano, sin depender de la zona del navegador ni de Intl. */
const DESFASE_COLOMBIA_MS = -5 * 60 * 60 * 1000

/** Instante UTC ISO-8601 → hora de Colombia: «24 nov 2026, 10:00 a. m.». Si no es válido, «—». */
export function formatFechaHora(iso: unknown): string {
  const m = typeof iso === 'string' ? /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso) : null
  if (!m) return '—'
  const t = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4]), Number(m[5])) + DESFASE_COLOMBIA_MS)
  if (Number.isNaN(t.getTime())) return '—'
  const h = t.getUTCHours()
  const hora12 = h % 12 === 0 ? 12 : h % 12
  return `${t.getUTCDate()} ${MESES[t.getUTCMonth()]} ${t.getUTCFullYear()}, ${hora12}:${String(t.getUTCMinutes()).padStart(2, '0')} ${h < 12 ? 'a. m.' : 'p. m.'}`
}

/** Solo la fecha (día de Colombia): «24 nov 2026». */
export function formatFecha(iso: unknown): string {
  const completo = formatFechaHora(iso)
  return completo === '—' ? '—' : completo.split(',')[0]
}

/** Último acceso: «Nunca» si no hay (significa «último inicio de sesión», no actividad). */
export function formatUltimoAcceso(iso: unknown): string {
  return iso === null || iso === undefined ? 'Nunca' : formatFechaHora(iso)
}

/** Cantidad entera con punto de miles; no válida → «—». */
export function formatCantidad(n: unknown): string {
  return esEntero(n) ? String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '.') : '—'
}

/** Texto del estado (el badge no depende solo del color). */
export function etiquetaEstado(estado: unknown): string {
  return estado === 'activa' ? 'Activa' : estado === 'suspendida' ? 'Suspendida' : estado === 'pendiente' ? 'Pendiente' : '—'
}

export const FILTROS_ESTADO: { valor: FiltroEstado; etiqueta: string }[] = [
  { valor: 'todos', etiqueta: 'Todos' },
  { valor: 'activa', etiqueta: 'Activos' },
  { valor: 'suspendida', etiqueta: 'Suspendidos' },
  { valor: 'pendiente', etiqueta: 'Pendientes' },
]

/** El backend no filtra por estado (CT-013): se filtra lo que ya llegó en la página. */
export function filtrarPorEstado(usuarios: UsuarioAdmin[], filtro: FiltroEstado): UsuarioAdmin[] {
  return filtro === 'todos' ? usuarios : usuarios.filter(u => u.estado === filtro)
}

export const NOMBRE_ACCION: Record<AccionAuditoria, string> = {
  suspender: 'Suspendió una cuenta',
  reactivar: 'Reactivó una cuenta',
  cerrar_sesiones: 'Cerró las sesiones de una cuenta',
  eliminar: 'Eliminó una cuenta',
}

export function etiquetaAccion(accion: unknown): string {
  return typeof accion === 'string' && (ACCIONES as string[]).includes(accion) ? NOMBRE_ACCION[accion as AccionAuditoria] : '—'
}

/** Búsqueda válida: 1 a 60 caracteres (ya recortada) y sin caracteres de control. Vacía = sin filtro (válida). */
export function busquedaValida(q: string): boolean {
  const t = q.trim()
  if (t.length === 0) return true
  return t.length <= MAX_BUSQUEDA && !/[\u0000-\u001f\u007f]/.test(t)
}

export function paginasTotales(total: unknown, porPagina: number = POR_PAGINA): number {
  if (!esEntero(total) || total <= 0) return 1
  return Math.min(MAX_PAGINA, Math.max(1, Math.ceil(total / porPagina)))
}

function normalizarUso(raw: unknown): UsoUsuario {
  const o = esObjeto(raw) ? raw : {}
  const n = (v: unknown) => (esEntero(v) ? v : null)
  return {
    transacciones: n(o.transacciones),
    categorias: n(o.categorias),
    presupuestos: n(o.presupuestos),
    metas: n(o.metas),
    recurrentes: n(o.recurrentes),
    whatsapp_conectado: typeof o.whatsapp_conectado === 'boolean' ? o.whatsapp_conectado : null,
  }
}

/** Un usuario de la respuesta: lista blanca de claves; `null` si falta lo esencial (correo o estado válido). */
export function normalizarUsuario(raw: unknown): UsuarioAdmin | null {
  if (!esObjeto(raw)) return null
  const correo = texto(raw.correo)
  if (!correo || typeof raw.estado !== 'string' || !(ESTADOS as string[]).includes(raw.estado)) return null
  const esDueno = raw.es_dueno === true
  const id = typeof raw.id === 'string' && UUID.test(raw.id) ? raw.id : null
  if (!esDueno && !id) return null
  return {
    id: esDueno ? null : id,
    correo,
    nombre: texto(raw.nombre, 100),
    estado: raw.estado as EstadoUsuario,
    moneda: texto(raw.moneda, 8),
    registrado_en: typeof raw.registrado_en === 'string' ? raw.registrado_en : null,
    ultimo_acceso: typeof raw.ultimo_acceso === 'string' ? raw.ultimo_acceso : null,
    es_dueno: esDueno,
    uso: normalizarUso(raw.uso),
  }
}

function cabecera(raw: Record<string, unknown>) {
  const pagina = esEntero(raw.pagina) && raw.pagina >= 1 ? Math.min(raw.pagina, MAX_PAGINA) : 1
  const total = esEntero(raw.total) ? raw.total : 0
  const totalPaginas = esEntero(raw.total_paginas) && raw.total_paginas >= 1 ? Math.min(raw.total_paginas, MAX_PAGINA) : paginasTotales(total)
  return { generado_en: texto(raw.generado_en, 40), pagina, total, total_paginas: totalPaginas }
}

/** Valida y normaliza `GET /admin/usuarios`; `null` si no tiene la forma esperada. */
export function normalizarLista(raw: unknown): ListaUsuarios | null {
  if (!esObjeto(raw) || !Array.isArray(raw.usuarios)) return null
  const usuarios = raw.usuarios.map(normalizarUsuario).filter((u): u is UsuarioAdmin => u !== null)
  return { ...cabecera(raw), usuarios }
}

/** Valida y normaliza el detalle (y la respuesta de las acciones); `null` si no es válido. */
export function normalizarDetalle(raw: unknown): UsuarioAdmin | null {
  return normalizarUsuario(raw)
}

/** Valida y normaliza `GET /admin/auditoria`; `null` si no tiene la forma esperada. */
export function normalizarAuditoria(raw: unknown): ListaAuditoria | null {
  if (!esObjeto(raw) || !Array.isArray(raw.registros)) return null
  const registros: RegistroAuditoria[] = []
  for (const r of raw.registros) {
    if (!esObjeto(r) || !esEntero(r.id) || typeof r.accion !== 'string' || !(ACCIONES as string[]).includes(r.accion)) continue
    if (typeof r.usuario_id !== 'string' || !UUID.test(r.usuario_id)) continue
    registros.push({
      id: r.id,
      fecha: typeof r.fecha === 'string' ? r.fecha : null,
      accion: r.accion as AccionAuditoria,
      usuario_id: r.usuario_id,
      usuario_correo: typeof r.usuario_correo === 'string' ? r.usuario_correo.slice(0, 255) : null,
    })
  }
  return { ...cabecera(raw), registros }
}

// ---------------------------------------------------------------------------------------------------------------
// Eliminar: formulario (INV-058)
// ---------------------------------------------------------------------------------------------------------------

/** Mismo criterio del backend: `strip().lower()`. */
export const normalizarCorreo = (s: string): string => s.trim().toLowerCase()

export function correoCoincide(escrito: string, correoUsuario: string): boolean {
  const e = normalizarCorreo(escrito)
  return e.length >= 3 && e === normalizarCorreo(correoUsuario)
}

export interface ErroresEliminar { correo?: string; contrasena?: string }

/** Valida el formulario de eliminar. El botón solo se habilita con `valido`. */
export function validarEliminar(correoEscrito: string, correoUsuario: string, contrasena: string): { valido: boolean; errores: ErroresEliminar } {
  const errores: ErroresEliminar = {}
  if (!correoCoincide(correoEscrito, correoUsuario)) errores.correo = 'El correo escrito no coincide con el de la cuenta.'
  if (contrasena.length < 1 || contrasena.length > 128) errores.contrasena = 'Escribe tu contraseña (hasta 128 caracteres).'
  return { valido: Object.keys(errores).length === 0, errores }
}

export type AccionUsuario = 'suspender' | 'reactivar' | 'cerrar-sesiones' | 'eliminar'

/** Mensaje claro por código de error de CT-013; `null` si el código no tiene mensaje propio. */
export function mensajeDeError(status: unknown, detail: unknown, accion?: AccionUsuario): string | null {
  const d = typeof detail === 'string' && detail.trim() ? detail : null
  switch (status) {
    case 403: return accion === 'eliminar' ? 'La contraseña es incorrecta.' : 'No tienes permiso para hacerlo.'
    case 404: return 'Esa cuenta ya no existe. Actualiza la lista.'
    case 409: return d ?? 'La cuenta no está en un estado que permita esta acción. Actualiza la lista.'
    case 413: return 'La solicitud es demasiado grande.'
    case 422: return d ?? 'Revisa los datos escritos.'
    case 429: return d ?? 'Demasiados intentos. Espera un momento antes de volver a intentar.'
    case 503: return d ?? 'No se pudo completar la operación. Revisa el estado del usuario antes de reintentar.'
    default: return null
  }
}

/** Texto para el aviso de éxito de cada acción. */
export const EXITO_ACCION: Record<AccionUsuario, string> = {
  suspender: 'Cuenta suspendida.',
  reactivar: 'Cuenta reactivada.',
  'cerrar-sesiones': 'Sesiones cerradas.',
  eliminar: 'Cuenta eliminada con todos sus datos.',
}
