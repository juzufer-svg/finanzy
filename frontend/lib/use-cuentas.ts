'use client'

/**
 * Carga las cuentas de dinero (CT-012) para los selectores «Cuenta (opcional)» (CHG-025). Incluye las archivadas para
 * poder mostrar su nombre; el selector filtra con `opcionesSelector`. Con guardia `isActive` y sin setState síncrono.
 */
import { useCallback, useEffect, useState } from 'react'
import apiClient from '@/lib/api-client'
import { normalizarCuentas, mensajeErrorCuenta, type Cuenta } from '@/lib/cuentas'

export function useCuentas() {
  const [estado, setEstado] = useState<{ cuentas: Cuenta[]; cargando: boolean; error: string }>({ cuentas: [], cargando: true, error: '' })
  const [intento, setIntento] = useState(0)

  useEffect(() => {
    let active = true
    apiClient.get('/api/v1/cuentas?incluir_archivadas=true')
      .then(r => { if (active) setEstado({ cuentas: normalizarCuentas(r.data), cargando: false, error: '' }) })
      .catch(err => { if (active) setEstado({ cuentas: [], cargando: false, error: mensajeErrorCuenta(err, 'No se pudieron cargar tus cuentas.') }) })
    return () => { active = false }
  }, [intento])

  const reintentar = useCallback(() => {
    setEstado(s => ({ ...s, cargando: true, error: '' }))
    setIntento(i => i + 1)
  }, [])

  return { ...estado, reintentar }
}
