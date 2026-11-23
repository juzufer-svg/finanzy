const CACHE_KEY = 'fx_rates_v2'
const CACHE_TTL = 4 * 60 * 60 * 1000 // 4 hours

// Fallback rates relative to USD (used if API fails)
export const FALLBACK_RATES: Record<string, number> = {
  USD: 1,
  EUR: 0.92,
  MXN: 17.5,
  ARS: 1200,
  COP: 3626,
  CLP: 950,
}

export async function fetchRates(): Promise<Record<string, number>> {
  if (typeof window !== 'undefined') {
    try {
      const cached = localStorage.getItem(CACHE_KEY)
      if (cached) {
        const { rates, ts } = JSON.parse(cached)
        if (Date.now() - ts < CACHE_TTL) return rates
      }
    } catch {}
  }
  try {
    const res = await fetch('https://open.er-api.com/v6/latest/USD')
    if (!res.ok) throw new Error(`FX API error ${res.status}`)
    const data = await res.json()
    if (data?.result !== 'success' || !data?.rates) throw new Error('Invalid FX payload')
    const rates: Record<string, number> = {
      USD: 1,
      EUR: data.rates.EUR,
      MXN: data.rates.MXN,
      ARS: data.rates.ARS,
      COP: data.rates.COP,
      CLP: data.rates.CLP,
    }
    if (typeof window !== 'undefined') {
      localStorage.setItem(CACHE_KEY, JSON.stringify({ rates, ts: Date.now() }))
    }
    return rates
  } catch {
    return { ...FALLBACK_RATES }
  }
}

export function convertAmount(
  amount: number,
  from: string,
  to: string,
  rates: Record<string, number>
): number {
  if (from === to || amount === 0) return amount
  const r = Object.keys(rates).length ? rates : FALLBACK_RATES
  const rFrom = r[from] ?? FALLBACK_RATES[from] ?? 1
  const rTo = r[to] ?? FALLBACK_RATES[to] ?? 1
  return amount * (rTo / rFrom)
}

const CURRENCY_DISPLAY: Record<string, { symbol: string; locale: string; decimals: number }> = {
  USD: { symbol: 'US$', locale: 'en-US', decimals: 2 },
  EUR: { symbol: '€',   locale: 'de-DE', decimals: 2 },
  MXN: { symbol: 'MX$', locale: 'es-MX', decimals: 0 },
  ARS: { symbol: 'AR$', locale: 'es-AR', decimals: 0 },
  COP: { symbol: '$',   locale: 'es-CO', decimals: 0 },
  CLP: { symbol: '$',   locale: 'es-CL', decimals: 0 },
}

export function formatAmount(amount: number, currency: string): string {
  const cfg = CURRENCY_DISPLAY[currency] ?? { symbol: '$', locale: 'es-MX', decimals: 0 }
  return `${cfg.symbol}${amount.toLocaleString(cfg.locale, {
    maximumFractionDigits: cfg.decimals,
    minimumFractionDigits: 0,
  })}`
}

// ── Montos en formularios (CHG-013, BL-030) ──
// Los montos se guardan en la moneda base (COP). Los formularios los muestran y los reciben en la
// moneda elegida; al guardar se convierten a la base. Si la persona no tocó el campo, se conserva el
// valor original exacto: una conversión de ida y vuelta (85.000 → US$23,44 → 84.988) no lo altera.

/** Símbolo de la moneda para el prefijo de los campos de monto. */
export function currencySymbol(currency: string): string {
  return CURRENCY_DISPLAY[currency]?.symbol ?? '$'
}

/** Valor para un campo de monto: el monto base convertido a la moneda elegida, con hasta 2 decimales. */
export function toInputValue(base: number, baseCurrency: string, currency: string, rates: Record<string, number>): string {
  const v = convertAmount(Number(base), baseCurrency, currency, rates)
  return String(Math.round(v * 100) / 100)
}

/**
 * Monto en la moneda base a partir de lo que escribió la persona (en la moneda elegida).
 * Con `original` (al editar): si el texto no cambió respecto de `originalText`, devuelve `original` tal cual.
 * Redondea a 2 decimales (la columna es NUMERIC(12,2)). Devuelve NaN si el texto no es un número.
 */
export function fromInputValue(
  text: string, baseCurrency: string, currency: string, rates: Record<string, number>,
  original?: { base: number; text: string },
): number {
  if (original && text.trim() === original.text) return Number(original.base)
  const n = Number(String(text).replace(',', '.'))
  if (!Number.isFinite(n)) return NaN
  return Math.round(convertAmount(n, currency, baseCurrency, rates) * 100) / 100
}
