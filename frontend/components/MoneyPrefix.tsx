'use client'

import { useCurrencyStore } from '@/store/currency'

/**
 * Prefijo de los campos de monto con el símbolo de la moneda elegida (CHG-013): «US$», «€», «$».
 * El campo que lo acompaña usa `!pl-12` para dejarle espacio.
 */
export default function MoneyPrefix() {
  const symbol = useCurrencyStore(s => s.symbol)
  return (
    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 font-semibold text-sm pointer-events-none" aria-hidden>
      {symbol}
    </span>
  )
}
