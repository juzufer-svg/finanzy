'use client'

import axios from 'axios'

// Usar siempre rutas relativas - Next.js las proxea al backend internamente (sin CORS)
const apiClient = axios.create({
  baseURL: '',
  headers: {
    'Content-Type': 'application/json',
  },
})

// Add interceptor for JWT token
apiClient.interceptors.request.use((config) => {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null
  
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  
  return config
})

// Response interceptor
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Clear token and redirect to login
      if (typeof window !== 'undefined') {
        localStorage.removeItem('token')
        // Fuera de un componente no hay router de Next: se fuerza una carga
        // completa para limpiar todo el estado de la sesión expirada.
        // eslint-disable-next-line @next/next/no-location-assign-relative-destination
        window.location.href = '/auth/login'
      }
    }
    return Promise.reject(error)
  }
)

export default apiClient
