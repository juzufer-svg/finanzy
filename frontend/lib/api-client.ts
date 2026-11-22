'use client'

import axios from 'axios'
import { CSRF_HEADER, CSRF_VALUE, LEGACY_TOKEN_KEY, STORED_USER_KEY } from '@/lib/session'

// Rutas relativas: el proxy de Next.js (app/api/v1/[...path]/route.ts) las envía al
// backend y añade la sesión desde la cookie HttpOnly. El navegador nunca ve el token.
const apiClient = axios.create({
  baseURL: '',
  headers: {
    'Content-Type': 'application/json',
    [CSRF_HEADER]: CSRF_VALUE,
  },
})

// Sesiones antiguas (token en localStorage): se pasan una sola vez a la cookie HttpOnly
// antes de la primera petición, y el token se borra del navegador.
let legacyMigration: Promise<void> | null = null

function migrateLegacySession(): Promise<void> {
  if (legacyMigration) return legacyMigration
  legacyMigration = (async () => {
    if (typeof window === 'undefined') return
    let legacy: string | null = null
    try { legacy = localStorage.getItem(LEGACY_TOKEN_KEY) } catch { return }
    if (!legacy) return
    let definitivo = true
    try {
      await axios.post('/api/v1/auth/adopt', { token: legacy }, {
        headers: { 'Content-Type': 'application/json', [CSRF_HEADER]: CSRF_VALUE },
      })
    } catch (err: unknown) {
      // 400/401: sesión vencida o inválida (la siguiente petición llevará al login).
      // 5xx o sin red: fallo pasajero; se conserva el token y se reintenta después (INV-016).
      const status = (err as { response?: { status?: number } })?.response?.status
      definitivo = status === 400 || status === 401
    }
    if (definitivo) clearLegacySession()
    else legacyMigration = null
  })()
  return legacyMigration
}

/** Borra el token antiguo del navegador (también al iniciar sesión, para que no reemplace la sesión nueva). */
export function clearLegacySession(): void {
  if (typeof window === 'undefined') return
  try { localStorage.removeItem(LEGACY_TOKEN_KEY) } catch { /* sin almacenamiento */ }
  document.cookie = 'token=; path=/; max-age=0'
}

apiClient.interceptors.request.use(async (config) => {
  if (!config.url?.includes('/api/v1/auth/')) await migrateLegacySession()
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const url: string = error.config?.url || ''
    // Un 401 en login o en un código es un error del formulario, no una sesión vencida
    if (error.response?.status === 401 && !url.includes('/api/v1/auth/') && typeof window !== 'undefined') {
      try { localStorage.removeItem(STORED_USER_KEY) } catch { /* sin almacenamiento */ }
      // Fuera de un componente no hay router de Next: se fuerza una carga
      // completa para limpiar todo el estado de la sesión expirada.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.href = '/auth/login'
    }
    return Promise.reject(error)
  }
)

/** ¿El navegador recuerda una sesión? (solo una pista para la interfaz; la verdad la tiene la cookie). */
export function hasStoredSession(): boolean {
  if (typeof window === 'undefined') return false
  try {
    return !!localStorage.getItem(STORED_USER_KEY) || !!localStorage.getItem(LEGACY_TOKEN_KEY)
  } catch {
    return false
  }
}

export default apiClient
