// Medios de pago (CHG-007, INV-022). El backend guarda el código; la interfaz muestra el nombre.
// Mantener en el mismo orden y con los mismos códigos que backend/app/schemas/plataapp.py (MEDIOS_PAGO).

export const MEDIOS_PAGO = [
  { value: 'debito', label: 'Débito' },
  { value: 'credito', label: 'Crédito' },
  { value: 'efectivo', label: 'Efectivo' },
  { value: 'transferencia', label: 'Transferencia' },
  { value: 'nequi_daviplata', label: 'Nequi / Daviplata' },
] as const

export type MedioPago = (typeof MEDIOS_PAGO)[number]['value']

/** Medio que se propone al registrar un movimiento nuevo. */
export const MEDIO_POR_DEFECTO: MedioPago = 'debito'

/** Nombre para mostrar; `null`/desconocido = "Sin especificar". */
export function medioPagoLabel(value: string | null | undefined): string {
  return MEDIOS_PAGO.find(m => m.value === value)?.label ?? 'Sin especificar'
}
