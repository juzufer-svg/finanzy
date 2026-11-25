// Pruebas del rango de fechas de transacciones y transferencias (CHG-027, INV-063). Se ejecutan con `npm test`.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { FECHA_MINIMA, hoyColombia, rangoFechas, mensajeFueraDeRango, validarRangoFecha } from '../lib/rango-fechas.ts'
import { apiErrorMessage } from '../lib/api-error.ts'
import { mensajeErrorCuenta } from '../lib/cuentas.ts'

const AHORA = new Date('2026-11-25T15:00:00Z') // 25 nov en Colombia; max = 2027-11-25

test('min fijo y max = hoy + 365 días en formato YYYY-MM-DD', () => {
  assert.deepEqual(rangoFechas(AHORA), { min: '2026-01-01', max: '2027-11-25' })
  assert.equal(FECHA_MINIMA, '2026-01-01')
})

test('el día de Colombia (UTC−5), no el UTC, decide el borde', () => {
  // 02:00 UTC del 26 nov = 21:00 del 25 nov en Colombia
  assert.equal(hoyColombia(new Date('2026-11-26T02:00:00Z')), '2026-11-25')
  assert.equal(rangoFechas(new Date('2026-11-26T02:00:00Z')).max, '2027-11-25')
  // 05:00 UTC ya es el 26 en Colombia
  assert.equal(hoyColombia(new Date('2026-11-26T05:00:00Z')), '2026-11-26')
  assert.equal(rangoFechas(new Date('2026-11-26T05:00:00Z')).max, '2027-11-26')
})

test('bordes: 2025-12-31 rechaza, 2026-01-01 acepta, hoy+365 acepta, hoy+366 rechaza, año 9999 rechaza', () => {
  assert.equal(validarRangoFecha('2025-12-31', AHORA), 'La fecha debe estar entre el 1 de enero de 2026 y el 25/11/2027')
  assert.equal(validarRangoFecha('2026-01-01', AHORA), null)
  assert.equal(validarRangoFecha('2027-11-25', AHORA), null)
  assert.equal(validarRangoFecha('2027-11-26', AHORA), mensajeFueraDeRango(AHORA))
  assert.equal(validarRangoFecha('9999-12-31', AHORA), mensajeFueraDeRango(AHORA))
})

test('año bisiesto: hoy 2027-03-01 + 365 = 2028-02-29', () => {
  assert.equal(rangoFechas(new Date('2027-03-01T12:00:00Z')).max, '2028-02-29')
})

test('un texto que no es fecha YYYY-MM-DD no se juzga aquí', () => {
  assert.equal(validarRangoFecha('', AHORA), null)
  assert.equal(validarRangoFecha('hola', AHORA), null)
})

test('422 de fecha: texto y lista de Pydantic (sin «Value error, ») se muestran bien', () => {
  const msg = 'La fecha debe estar entre el 1 de enero de 2026 y el 25/11/2027'
  const texto = { response: { status: 422, data: { detail: msg } } }
  const lista = { response: { status: 422, data: { detail: [{ type: 'value_error', loc: ['body', 'fecha'], msg: `Value error, ${msg}` }] } } }
  for (const e of [texto, lista]) {
    assert.equal(apiErrorMessage(e, 'x'), msg)
    assert.equal(mensajeErrorCuenta(e, 'x'), msg)
  }
})

test('422 de lista con otro mensaje sigue siendo genérico', () => {
  const e = { response: { status: 422, data: { detail: [{ msg: 'Value error, algo interno' }] } } }
  assert.equal(apiErrorMessage(e, 'x'), 'Revisa los datos ingresados.')
})
