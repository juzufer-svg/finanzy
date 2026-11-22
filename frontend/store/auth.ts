'use client'

import { create } from 'zustand'

interface AuthUser {
  id: string
  email: string
  full_name?: string
}

interface AuthStore {
  token: string | null
  user: AuthUser | null
  isAuthenticated: boolean
  setToken: (token: string) => void
  setUser: (user: AuthUser) => void
  logout: () => void
  loadAuth: () => void
}

// Sesión guardada en el navegador (en el servidor no existe localStorage)
function readStoredAuth(): Pick<AuthStore, 'token' | 'user' | 'isAuthenticated'> {
  if (typeof window === 'undefined') return { token: null, user: null, isAuthenticated: false }
  const token = localStorage.getItem('token')
  const user = localStorage.getItem('user')
  if (!token || !user) return { token: null, user: null, isAuthenticated: false }
  try {
    return { token, user: JSON.parse(user), isAuthenticated: true }
  } catch {
    return { token: null, user: null, isAuthenticated: false }
  }
}

export const useAuthStore = create<AuthStore>((set) => ({
    ...readStoredAuth(),

    setToken: (token: string) => {
      localStorage.setItem('token', token)
      document.cookie = `token=${token}; path=/; max-age=86400; SameSite=Lax`
      set({ token, isAuthenticated: true })
    },
    
    setUser: (user: any) => {
      localStorage.setItem('user', JSON.stringify(user))
      set({ user })
    },
    
    logout: () => {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      document.cookie = 'token=; path=/; max-age=0'
      set({ token: null, user: null, isAuthenticated: false })
    },
    
    loadAuth: () => set(readStoredAuth()),
}))
