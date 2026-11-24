'use client'

import { create } from 'zustand'
import apiClient, { clearLegacySession } from '@/lib/api-client'
import { LEGACY_TOKEN_KEY, STORED_USER_KEY } from '@/lib/session'

interface AuthUser {
  id: string
  email: string
  full_name?: string
}

interface AuthStore {
  user: AuthUser | null
  isAuthenticated: boolean
  // CHG-017 (CT-002): `es_dueno` de GET /users/me. Solo decide si se muestra el enlace «Monitor»;
  // la autorización real la hace el backend. Vive solo en memoria: nunca se guarda en localStorage.
  esDueno: boolean
  setEsDueno: (esDueno: boolean) => void
  setUser: (user: AuthUser) => void
  logout: () => Promise<void>
  loadAuth: () => void
}

// El token vive en una cookie HttpOnly (ADR-005). El navegador solo recuerda datos no
// sensibles del usuario para pintar la interfaz; si la cookie ya no sirve, el backend
// responde 401 y apiClient lleva al login.
function readStoredAuth(): Pick<AuthStore, 'user' | 'isAuthenticated'> {
  if (typeof window === 'undefined') return { user: null, isAuthenticated: false }
  try {
    const user = localStorage.getItem(STORED_USER_KEY)
    if (!user) return { user: null, isAuthenticated: false }
    return { user: JSON.parse(user), isAuthenticated: true }
  } catch {
    return { user: null, isAuthenticated: false }
  }
}

export const useAuthStore = create<AuthStore>((set, get) => ({
  ...readStoredAuth(),
  esDueno: false,

  setEsDueno: (esDueno: boolean) => set({ esDueno: esDueno === true }),

  // Se llama al iniciar sesión: el token antiguo ya no debe migrarse sobre la sesión nueva.
  // Si cambia la persona, se descarta `esDueno` (se recalcula con GET /users/me); si es la misma
  // (p. ej. solo cambió el nombre), se conserva.
  setUser: (user: AuthUser) => {
    clearLegacySession()
    try { localStorage.setItem(STORED_USER_KEY, JSON.stringify(user)) } catch { /* sin almacenamiento */ }
    const mismaPersona = get().user?.id === user.id
    set(mismaPersona ? { user, isAuthenticated: true } : { user, isAuthenticated: true, esDueno: false })
  },

  logout: async () => {
    try {
      localStorage.removeItem(STORED_USER_KEY)
      localStorage.removeItem(LEGACY_TOKEN_KEY)
    } catch { /* sin almacenamiento */ }
    set({ user: null, isAuthenticated: false, esDueno: false })
    try {
      await apiClient.post('/api/v1/auth/logout')
    } catch {
      // Si falla la red, la cookie vence sola; la interfaz ya cerró la sesión
    }
  },

  loadAuth: () => set(readStoredAuth()),
}))
