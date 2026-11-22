'use client'

import { create } from 'zustand'
import apiClient from '@/lib/api-client'
import { LEGACY_TOKEN_KEY, STORED_USER_KEY } from '@/lib/session'

interface AuthUser {
  id: string
  email: string
  full_name?: string
}

interface AuthStore {
  user: AuthUser | null
  isAuthenticated: boolean
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

export const useAuthStore = create<AuthStore>((set) => ({
  ...readStoredAuth(),

  setUser: (user: AuthUser) => {
    try { localStorage.setItem(STORED_USER_KEY, JSON.stringify(user)) } catch { /* sin almacenamiento */ }
    set({ user, isAuthenticated: true })
  },

  logout: async () => {
    try {
      localStorage.removeItem(STORED_USER_KEY)
      localStorage.removeItem(LEGACY_TOKEN_KEY)
    } catch { /* sin almacenamiento */ }
    set({ user: null, isAuthenticated: false })
    try {
      await apiClient.post('/api/v1/auth/logout')
    } catch {
      // Si falla la red, la cookie vence sola; la interfaz ya cerró la sesión
    }
  },

  loadAuth: () => set(readStoredAuth()),
}))
