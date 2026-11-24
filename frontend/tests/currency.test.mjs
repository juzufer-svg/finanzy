// Montos en la moneda elegida (CHG-013, BL-030). `npm test`.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { toInputValue, fromInputValue, currencySymbol, FALLBACK_RATES } from '../lib/currency.ts'

const R = { ...FALLBACK_RATES, COP: 4000 } // 1 US$ = 4.000 COP

test('el campo muestra el monto base en la moneda elegida', () => {
  assert.equal(toInputValue(85000, 'COP', 'USD', R), '21.25')
  assert.equal(toInputValue(85000, 'COP', 'COP', R), '85000')
  assert.equal(toInputValue(100000, 'COP', 'USD', R), '25')
})

test('lo escrito se guarda en la moneda base, redondeado a centavos', () => {
  assert.equal(fromInputValue('25', 'COP', 'USD', R), 100000)
  assert.equal(fromInputValue('10,5', 'COP', 'USD', R), 42000)
  assert.equal(fromInputValue('85000', 'COP', 'COP', R), 85000)
  assert.equal(fromInputValue('0.333', 'COP', 'USD', { ...R, COP: 3 }), 1)
  assert.ok(Number.isNaN(fromInputValue('abc', 'COP', 'USD', R)))
})

test('si no se tocó el campo se conserva el valor original exacto', () => {
  const R2 = { ...FALLBACK_RATES, COP: 3626 }
  const texto = toInputValue(85000, 'COP', 'USD', R2) // "23.44"
  assert.equal(fromInputValue(texto, 'COP', 'USD', R2), 84993.44) // ida y vuelta pierde precisión...
  assert.equal(fromInputValue(texto, 'COP', 'USD', R2, { base: 85000, text: texto }), 85000) // ...pero se conserva
  assert.equal(fromInputValue('30', 'COP', 'USD', R2, { base: 85000, text: texto }), 108780)
})

test('símbolo del prefijo', () => {
  assert.equal(currencySymbol('USD'), 'US$')
  assert.equal(currencySymbol('COP'), '$')
  assert.equal(currencySymbol('XYZ'), '$')
})

test('solo se aceptan las monedas que la app conoce (lo que llega del servidor o del navegador)', async () => {
  const { isSupportedCurrency } = await import('../lib/currency.ts')
  for (const c of ['USD', 'EUR', 'MXN', 'ARS', 'COP', 'CLP']) assert.equal(isSupportedCurrency(c), true, c)
  for (const c of ['BTC', 'usd', '', null, undefined, 5, {}]) assert.equal(isSupportedCurrency(c), false, String(c))
})
