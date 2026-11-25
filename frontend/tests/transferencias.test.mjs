// Pruebas de las utilidades de transferencias (CHG-024, UC-016, CT-012). Se ejecutan con `npm test`.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  normalizarTransferencias, desplazarMes, mesDe, fechaLocal, cuentasParaTransferir, validarTransferencia, cuerpoTransferencia,
} from '../lib/transferencias.ts'

const base = { origen: 'a', destino: 'b', monto: 1000, fecha: '2026-11-25', descripcion: '' }

test('normaliza, descarta lo inválido y ordena por fecha descendente', () => {
  const l = normalizarTransferencias([
    { id: '1', cuenta_origen_id: 'a', cuenta_destino_id: 'b', monto: '500.50', fecha: '2026-11-01', descripcion: null },
    { id: '2', cuenta_origen_id: 'a', cuenta_destino_id: 'b', monto: 10, fecha: '2026-11-20', descripcion: 'x' },
    { id: '3' }, null,
  ])
  assert.deepEqual(l.map(t => t.id), ['2', '1'])
  assert.equal(l[1].monto, 500.5)
  assert.equal(l[1].descripcion, '')
  assert.deepEqual(normalizarTransferencias('x'), [])
})

test('solo cuentas no archivadas en los selectores', () => {
  const r = cuentasParaTransferir([{ id: 'a', archivada: false }, { id: 'b', archivada: true }])
  assert.deepEqual(r.map(c => c.id), ['a'])
})

test('validación: cuentas iguales, monto y fecha', () => {
  assert.equal(validarTransferencia(base), null)
  assert.equal(validarTransferencia({ ...base, destino: 'a' }), 'Elige dos cuentas distintas.')
  assert.match(validarTransferencia({ ...base, origen: '' }), /origen/)
  assert.match(validarTransferencia({ ...base, destino: '' }), /destino/)
  assert.match(validarTransferencia({ ...base, monto: 0 }), /mayor que 0/)
  assert.match(validarTransferencia({ ...base, monto: NaN }), /mayor que 0/)
  assert.match(validarTransferencia({ ...base, monto: 1e10 }), /máximo/)
  assert.match(validarTransferencia({ ...base, fecha: '' }), /fecha/)
  assert.match(validarTransferencia({ ...base, descripcion: 'x'.repeat(256) }), /255/)
})

test('cuerpo: la nota vacía no se envía', () => {
  assert.deepEqual(cuerpoTransferencia(base), { cuenta_origen_id: 'a', cuenta_destino_id: 'b', monto: 1000, fecha: '2026-11-25' })
  assert.equal(cuerpoTransferencia({ ...base, descripcion: ' hola ' }).descripcion, 'hola')
})

test('meses y fecha local', () => {
  assert.equal(desplazarMes('2026-01', -1), '2025-12')
  assert.equal(desplazarMes('2026-12', 1), '2027-01')
  assert.equal(fechaLocal(new Date(2026, 10, 5)), '2026-11-05')
  assert.equal(mesDe(new Date(2026, 10, 5)), '2026-11')
})
