// Pruebas de CHG-018: exportación a CSV/Excel (rango, nombre, errores como Blob y cabeceras del proxy). `npm test`.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  rangoValido, mesesDelRango, nombreDeArchivo, nombreDesdeContentDisposition, errorDeBlob, cabecerasDeDescarga,
  MENSAJE_413,
} from '../lib/exportar.ts'

// Mismo contrato que apiErrorMessage (components/DialogProvider.tsx), sin importar React
const mensaje = (err, fallback) => {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  return fallback
}
const errorBlob = (status, cuerpo, tipo = 'application/json') =>
  ({ response: { status, data: new Blob([cuerpo], { type: tipo }) } })
const cabeceras = obj => ({ get: n => obj[n.toLowerCase()] ?? null })

test('rangoValido: hasta 12 meses se acepta y 13 no (INV-044)', () => {
  assert.deepEqual(rangoValido('2026-11', '2026-11'), { ok: true })
  assert.deepEqual(rangoValido('2025-12', '2026-11'), { ok: true })
  assert.equal(mesesDelRango('2025-12', '2026-11'), 12)
  const r = rangoValido('2025-11', '2026-11')
  assert.equal(r.ok, false)
  assert.match(r.motivo, /hasta 12 meses/)
  assert.equal(mesesDelRango('2025-01', '2026-02'), 14)
})

test('rangoValido: inicio posterior al final y meses inválidos se rechazan', () => {
  const a = rangoValido('2026-11', '2026-10')
  assert.equal(a.ok, false)
  assert.match(a.motivo, /no puede ser posterior/)
  for (const [d, h] of [['2026-13', '2026-12'], ['', '2026-01'], ['2026-1', '2026-02'], ['1999-12', '2000-01'], ['2026-01', 'abc']]) {
    assert.equal(rangoValido(d, h).ok, false, `${d} - ${h}`)
  }
})

test('nombreDeArchivo: un mes o un rango, sin datos personales', () => {
  assert.equal(nombreDeArchivo('2026-11', '2026-11', 'csv'), 'finanzy-transacciones-2026-11.csv')
  assert.equal(nombreDeArchivo('2026-11', undefined, 'csv'), 'finanzy-transacciones-2026-11.csv')
  assert.equal(nombreDeArchivo('2026-09', '2026-11', 'xlsx'), 'finanzy-transacciones-2026-09_a_2026-11.xlsx')
})

test('nombreDesdeContentDisposition: usa el nombre del servidor solo si es seguro', () => {
  const respaldo = 'finanzy-transacciones-2026-11.csv'
  assert.equal(nombreDesdeContentDisposition('attachment; filename="finanzy-transacciones-2026-01_a_2026-11.xlsx"', respaldo),
    'finanzy-transacciones-2026-01_a_2026-11.xlsx')
  assert.equal(nombreDesdeContentDisposition(null, respaldo), respaldo)
  assert.equal(nombreDesdeContentDisposition('attachment; filename="../../etc/passwd"', respaldo), respaldo)
  assert.equal(nombreDesdeContentDisposition('attachment; filename="a/b.csv"', respaldo), respaldo)
})

test('errorDeBlob: 422, 429 y 503 llegan como Blob y se lee su detail', async () => {
  for (const [status, detail, codigo] of [
    [422, 'El archivo superaría los 4 MB. Elige menos meses.', 'exportacion_demasiado_grande'],
    [422, 'Hay más de 10 000 transacciones en ese rango. Elige menos meses.', 'exportacion_demasiadas_filas'],
    [429, 'Demasiadas descargas. Espera un momento e intenta de nuevo.', undefined],
    [503, 'La exportación tardó demasiado. Elige menos meses.', undefined],
  ]) {
    const err = await errorDeBlob(errorBlob(status, JSON.stringify({ detail, ...(codigo ? { codigo } : {}) })))
    assert.equal(mensaje(err, 'x'), detail)
    assert.equal(err.response.data.codigo, codigo)
    assert.ok(!String(mensaje(err, 'x')).includes('Blob'))
  }
})

test('errorDeBlob: un Blob que no es JSON usa el mensaje por defecto', async () => {
  const err = await errorDeBlob(errorBlob(503, '<html>Bad gateway</html>', 'text/html'))
  assert.equal(mensaje(err, 'por defecto'), 'por defecto')
  const vacio = await errorDeBlob(errorBlob(500, ''))
  assert.equal(mensaje(vacio, 'por defecto'), 'por defecto')
})

test('errorDeBlob: un 413 opaco de Vercel se traduce a un mensaje claro', async () => {
  const err = await errorDeBlob(errorBlob(413, 'Request Entity Too Large', 'text/plain'))
  assert.equal(mensaje(err, 'x'), MENSAJE_413)
  assert.equal(MENSAJE_413, 'El archivo es demasiado grande. Elige menos meses.')
})

test('errorDeBlob: sin respuesta (sin red) o con datos ya en objeto no cambia el error', async () => {
  const sinRed = { message: 'Network Error' }
  assert.equal(await errorDeBlob(sinRed), sinRed)
  const conObjeto = { response: { status: 422, data: { detail: 'Formato no válido: usa csv o xlsx' } } }
  assert.equal(mensaje(await errorDeBlob(conObjeto), 'x'), 'Formato no válido: usa csv o xlsx')
})

test('cabecerasDeDescarga: reenvía Content-Disposition y Content-Type solo en exportaciones/*', () => {
  const up = cabeceras({
    'content-type': 'text/csv; charset=utf-8',
    'content-disposition': 'attachment; filename="finanzy-transacciones-2026-11.csv"',
  })
  assert.deepEqual(cabecerasDeDescarga('exportaciones/transacciones', up), {
    'Content-Type': 'text/csv; charset=utf-8',
    'Content-Disposition': 'attachment; filename="finanzy-transacciones-2026-11.csv"',
  })
})

test('cabecerasDeDescarga: ignora Content-Disposition en cualquier otra ruta', () => {
  const up = cabeceras({ 'content-type': 'application/json', 'content-disposition': 'attachment; filename="x.csv"' })
  for (const ruta of ['transacciones', 'users/me', 'auth/login', 'transacciones/exportaciones', 'exportaciones-falsas/x']) {
    assert.deepEqual(cabecerasDeDescarga(ruta, up), { 'Content-Type': 'application/json' }, ruta)
  }
})

test('cabecerasDeDescarga: sin Content-Type o con una disposición que no es adjunto no añade nada', () => {
  assert.deepEqual(cabecerasDeDescarga('exportaciones/transacciones', cabeceras({})), {})
  assert.deepEqual(cabecerasDeDescarga('exportaciones/transacciones', cabeceras({ 'content-disposition': 'inline' })), {})
})
