'use client'

import { create } from 'zustand'
import { fetchRates, convertAmount, formatAmount, FALLBACK_RATES, toInputValue, fromInputValue, currencySymbol } from '@/lib/currency'

interface CurrencyStore {
  currency: string        // display currency (what user selected)
  baseCurrency: string    // the currency data is stored in (set once)
  rates: Record<string, number>
  ratesLoaded: boolean
  setCurrency: (currency: string) => void
  loadRates: () => Promise<void>
  fmt: (amount: number) => string
  convert: (amount: number) => number
  /** Monto base → texto para un campo de monto en la moneda elegida (CHG-013). */
  toInput: (base: number) => string
  /** Texto de un campo (moneda elegida) → monto base; `original` conserva el valor si no se tocó. */
  toBase: (text: string, original?: { base: number; text: string }) => number
  /** Símbolo para el prefijo de los campos de monto. */
  symbol: string
}

type CurrencySnapshot = Pick<CurrencyStore, 'currency' | 'baseCurrency' | 'rates'>

function readStorage(key: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback
  return localStorage.getItem(key) ?? fallback
}

function getInitialBaseCurrency(): string {
  if (typeof window === 'undefined') return 'COP'

  const migrated = localStorage.getItem('base_currency_migrated_v2') === '1'

  // Force one-time migration to COP for existing persisted amounts.
  if (!migrated) {
    localStorage.setItem('base_currency', 'COP')
    localStorage.setItem('base_currency_migrated_v2', '1')
    return 'COP'
  }

  return localStorage.getItem('base_currency') ?? 'COP'
}

function buildConverter(snapshot: CurrencySnapshot) {
  const r = Object.keys(snapshot.rates).length ? snapshot.rates : FALLBACK_RATES
  return (amount: number) => convertAmount(amount, snapshot.baseCurrency, snapshot.currency, r)
}

function buildInputHelpers(snapshot: CurrencySnapshot) {
  const r = Object.keys(snapshot.rates).length ? snapshot.rates : FALLBACK_RATES
  return {
    toInput: (base: number) => toInputValue(base, snapshot.baseCurrency, snapshot.currency, r),
    toBase: (text: string, original?: { base: number; text: string }) =>
      fromInputValue(text, snapshot.baseCurrency, snapshot.currency, r, original),
    symbol: currencySymbol(snapshot.currency),
  }
}

function buildFormatter(snapshot: CurrencySnapshot) {
  const convert = buildConverter(snapshot)
  return (amount: number) => formatAmount(convert(amount), snapshot.currency)
}

export const useCurrencyStore = create<CurrencyStore>((set, get) => ({
  currency: readStorage('currency', 'USD'),
  baseCurrency: getInitialBaseCurrency(),
  rates: {},
  ratesLoaded: false,

  setCurrency: (currency: string) => {
    if (typeof window !== 'undefined') localStorage.setItem('currency', currency)
    const state = get()
    const snapshot: CurrencySnapshot = {
      currency,
      baseCurrency: state.baseCurrency,
      rates: state.rates,
    }
    set({
      currency,
      convert: buildConverter(snapshot),
      fmt: buildFormatter(snapshot),
      ...buildInputHelpers(snapshot),
    })
  },

  loadRates: async () => {
    if (get().ratesLoaded) return
    const rates = await fetchRates()
    const state = get()
    const snapshot: CurrencySnapshot = {
      currency: state.currency,
      baseCurrency: state.baseCurrency,
      rates,
    }
    set({
      rates,
      ratesLoaded: true,
      convert: buildConverter(snapshot),
      fmt: buildFormatter(snapshot),
      ...buildInputHelpers(snapshot),
    })
  },

  ...buildInputHelpers({
    currency: readStorage('currency', 'USD'),
    baseCurrency: getInitialBaseCurrency(),
    rates: {},
  }),

  convert: buildConverter({
    currency: readStorage('currency', 'USD'),
    baseCurrency: getInitialBaseCurrency(),
    rates: {},
  }),

  fmt: buildFormatter({
    currency: readStorage('currency', 'USD'),
    baseCurrency: getInitialBaseCurrency(),
    rates: {},
  }),
}))

// Available currencies
export const AVAILABLE_CURRENCIES = [
  { code: 'USD', name: 'Dólar Estadounidense', symbol: 'US$' },
  { code: 'EUR', name: 'Euro', symbol: '€' },
  { code: 'MXN', name: 'Peso Mexicano', symbol: 'MX$' },
  { code: 'ARS', name: 'Peso Argentino', symbol: 'AR$' },
  { code: 'COP', name: 'Peso Colombiano', symbol: '$' },
  { code: 'CLP', name: 'Peso Chileno', symbol: '$' },
]

