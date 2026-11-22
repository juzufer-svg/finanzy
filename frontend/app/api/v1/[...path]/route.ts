/**
 * Proxy de la API (ADR-005): navegador → Next.js (Vercel) → FastAPI (Railway).
 *
 * - La sesión es una cookie HttpOnly + Secure + SameSite=Lax. El navegador nunca ve el JWT:
 *   al iniciar sesión se quita `access_token` de la respuesta y se guarda en la cookie.
 * - En cada petición se convierte la cookie en `Authorization: Bearer …` hacia el backend.
 *   Un encabezado Authorization que mande el navegador se ignora.
 * - CSRF: toda petición que cambia datos debe traer el encabezado `x-finanzy-csrf` (un sitio
 *   ajeno no puede añadirlo sin permiso CORS) y, si trae Origin, debe ser este mismo sitio.
 * - Rutas propias: `auth/logout` (borra la cookie) y `auth/adopt` (pasa a la cookie una
 *   sesión antigua guardada en localStorage, para que nadie pierda la sesión al desplegar).
 * - Depende de Vercel para la IP real: Vercel reemplaza `x-forwarded-for` con la IP del
 *   visitante y aquí se reenvía tal cual (fuera de Vercel el cliente podría falsificarla).
 * - Del backend solo se reenvía `Content-Type` (la API no usa redirecciones ni descargas).
 */
import { type NextRequest, NextResponse } from 'next/server'
import { CSRF_HEADER, CSRF_VALUE } from '@/lib/session'

const BACKEND_URL = (process.env.BACKEND_URL || 'http://localhost:8000').replace(/\/+$/, '')
const IS_PROD = process.env.NODE_ENV === 'production'
// El prefijo __Host- obliga a Secure, Path=/ y sin Domain (no se comparte con subdominios).
const COOKIE_NAME = IS_PROD ? '__Host-finanzy_session' : 'finanzy_session'
const DEFAULT_MAX_AGE = 7 * 24 * 60 * 60 // 7 días, igual que la sesión del backend
const TOKEN_ROUTES = new Set(['auth/login', 'auth/verify-email'])
const SAFE_METHODS = new Set(['GET', 'HEAD'])
const MAX_BODY_BYTES = 64 * 1024

type Ctx = { params: Promise<{ path: string[] }> }

function json(status: number, detail: string) {
  return NextResponse.json({ detail }, { status, headers: { 'Cache-Control': 'no-store' } })
}

/** Segundos hasta que vence el JWT (según su `exp`), para que la cookie dure lo mismo. */
function maxAgeFromToken(token: string): number {
  try {
    const payload = JSON.parse(Buffer.from(token.split('.')[1] || '', 'base64url').toString('utf8'))
    const seconds = Math.floor(Number(payload.exp) - Date.now() / 1000)
    if (Number.isFinite(seconds) && seconds > 0) return Math.min(seconds, 30 * 24 * 60 * 60)
  } catch {
    // token sin formato JWT: se usa la duración por defecto
  }
  return DEFAULT_MAX_AGE
}

function setSessionCookie(res: NextResponse, token: string) {
  res.cookies.set({
    name: COOKIE_NAME,
    value: token,
    httpOnly: true,
    secure: IS_PROD,
    sameSite: 'lax',
    path: '/',
    maxAge: maxAgeFromToken(token),
  })
}

function clearSessionCookie(res: NextResponse) {
  res.cookies.set({ name: COOKIE_NAME, value: '', httpOnly: true, secure: IS_PROD, sameSite: 'lax', path: '/', maxAge: 0 })
  // Cookie antigua, legible desde JavaScript (antes de ADR-005)
  res.cookies.set({ name: 'token', value: '', path: '/', maxAge: 0 })
}

/** Protección CSRF para métodos que cambian datos. */
function csrfOk(req: NextRequest): boolean {
  if (SAFE_METHODS.has(req.method)) return true
  if (req.headers.get(CSRF_HEADER) !== CSRF_VALUE) return false
  const origin = req.headers.get('origin')
  if (!origin) return true // algunos navegadores no envían Origin en peticiones del mismo sitio
  try {
    return new URL(origin).host === req.headers.get('host')
  } catch {
    return false
  }
}

async function callBackend(req: NextRequest, path: string, token: string | undefined, body?: string) {
  const headers = new Headers({ Accept: 'application/json' })
  const contentType = req.headers.get('content-type')
  if (contentType) headers.set('Content-Type', contentType)
  // IP real del visitante para los límites del backend (Vercel la pone en x-forwarded-for)
  const forwardedFor = req.headers.get('x-forwarded-for')
  if (forwardedFor) headers.set('X-Forwarded-For', forwardedFor)
  if (token) headers.set('Authorization', `Bearer ${token}`)

  return fetch(`${BACKEND_URL}/api/v1/${path}${req.nextUrl.search}`, {
    method: req.method,
    headers,
    body,
    cache: 'no-store',
    redirect: 'manual',
  })
}

async function readBody(req: NextRequest): Promise<string | undefined | null> {
  if (SAFE_METHODS.has(req.method)) return undefined
  const text = await req.text()
  if (new TextEncoder().encode(text).length > MAX_BODY_BYTES) return null
  return text || undefined
}

/**
 * Pasa a la cookie HttpOnly una sesión antigua (token en localStorage), si sigue siendo válida.
 * Nunca reemplaza ni borra una sesión que ya está en la cookie (p. ej. un login reciente).
 */
async function adoptLegacySession(req: NextRequest, body: string | undefined) {
  if (req.cookies.get(COOKIE_NAME)?.value) return new NextResponse(null, { status: 204 })
  let token = ''
  try {
    token = String(JSON.parse(body || '{}').token || '')
  } catch {
    // cuerpo inválido
  }
  if (!token || token.length > 4096) return json(400, 'Sesión inválida')

  let check: Response
  let user: unknown
  try {
    check = await fetch(`${BACKEND_URL}/api/v1/users/me`, {
      headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
      cache: 'no-store',
    })
    user = check.ok ? await check.json() : null
  } catch {
    return json(502, 'No se pudo conectar con el servidor. Intenta de nuevo en unos minutos.')
  }
  if (check.status === 401 || check.status === 404 || check.status === 422) {
    return json(401, 'Tu sesión ya no es válida. Inicia sesión de nuevo.')
  }
  if (!check.ok) return json(503, 'Servicio no disponible. Intenta de nuevo en unos minutos.')
  const res = NextResponse.json(user, { headers: { 'Cache-Control': 'no-store' } })
  setSessionCookie(res, token)
  return res
}

async function handle(req: NextRequest, ctx: Ctx) {
  const { path: parts } = await ctx.params
  if (parts.some(p => p === '..' || p === '.' || p.includes('/') || p.includes('\\'))) {
    return json(400, 'Ruta inválida')
  }
  const path = parts.map(encodeURIComponent).join('/')

  if (!csrfOk(req)) return json(403, 'Solicitud rechazada por seguridad. Recarga la página e intenta de nuevo.')

  const body = await readBody(req)
  if (body === null) return json(413, 'La solicitud es demasiado grande.')

  if (req.method === 'POST' && path === 'auth/logout') {
    const res = new NextResponse(null, { status: 204 })
    clearSessionCookie(res)
    return res
  }
  if (req.method === 'POST' && path === 'auth/adopt') {
    return adoptLegacySession(req, body)
  }

  const token = req.cookies.get(COOKIE_NAME)?.value
  // Sin cookie no hay sesión: 401 (el backend respondería 422 por falta del encabezado)
  if (!token && !path.startsWith('auth/')) {
    return json(401, 'Tu sesión ya no es válida. Inicia sesión de nuevo.')
  }
  let upstream: Response
  try {
    upstream = await callBackend(req, path, token, body)
  } catch {
    return json(502, 'No se pudo conectar con el servidor. Intenta de nuevo en unos minutos.')
  }

  const upstreamType = upstream.headers.get('content-type') || ''
  const headers = { 'Cache-Control': 'no-store' }

  // Inicio de sesión: el token va a la cookie y se quita de la respuesta
  if (req.method === 'POST' && TOKEN_ROUTES.has(path) && upstream.ok && upstreamType.includes('application/json')) {
    const data = await upstream.json()
    if (data && typeof data.access_token === 'string') {
      const visible = { ...data }
      delete visible.access_token
      delete visible.token_type
      const res = NextResponse.json(visible, { status: upstream.status, headers })
      setSessionCookie(res, data.access_token)
      return res
    }
    return NextResponse.json(data, { status: upstream.status, headers })
  }

  const res = new NextResponse(upstream.status === 204 ? null : await upstream.arrayBuffer(), {
    status: upstream.status,
    headers: upstreamType ? { ...headers, 'Content-Type': upstreamType } : headers,
  })
  // Sesión vencida, cerrada o cuenta eliminada: se borra la cookie (un 503 no la toca, INV-016).
  // Un 401 de auth/* (p. ej. contraseña mala en el login) no es una sesión vencida.
  const sesionVencida = upstream.status === 401 && !path.startsWith('auth/')
  if (token && (sesionVencida || (req.method === 'DELETE' && path === 'users/me' && upstream.ok))) {
    clearSessionCookie(res)
  }
  return res
}

export const GET = handle
export const POST = handle
export const PUT = handle
export const DELETE = handle
