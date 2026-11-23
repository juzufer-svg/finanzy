// Pruebas de CHG-012: recurrentes (textos y fechas) y alertas de presupuesto. `npm test`.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { localDate, frecuenciaTexto, diasHasta, cuandoTexto, totalMensualEstimado } from '../lib/recurrentes.ts'
import { estadoPresupuesto, budgetAlerts, topSpending } from '../lib/month-stats.ts'

test('fecha local YYYY-MM-DD (no UTC)', () => {
  assert.equal(localDate(new Date(2026, 0, 5, 23, 59)), '2026-01-05')
})

test('texto de la frecuencia', () => {
  assert.equal(frecuenciaTexto('mensual', 5), 'Mensual, el día 5')
  assert.equal(frecuenciaTexto('mensual', 31), 'Mensual, el día 31 (o el último del mes)')
  assert.equal(frecuenciaTexto('quincenal', 15), 'Quincenal, días 15 y 30')
  assert.equal(frecuenciaTexto('quincenal', 20), 'Quincenal, días 5 y 20')
  assert.equal(frecuenciaTexto('semanal', 3), 'Semanal')
})

test('días hasta una fecha y su texto', () => {
  assert.equal(diasHasta('2026-12-01', '2026-11-23'), 8)
  assert.equal(diasHasta('2027-01-01', '2026-12-31'), 1)
  assert.equal(cuandoTexto('2026-11-23', '2026-11-23'), 'Hoy')
  assert.equal(cuandoTexto('2026-11-24', '2026-11-23'), 'Mañana')
  assert.equal(cuandoTexto('2026-11-22', '2026-11-23'), 'Ayer')
  assert.equal(cuandoTexto('2026-11-20', '2026-11-23'), 'Hace 3 días')
  assert.equal(cuandoTexto('2026-11-30', '2026-11-23'), 'En 7 días')
})

test('total mensual estimado solo con las activas del tipo', () => {
  const r = (frecuencia, monto, tipo = 'gasto', activa = true) => ({ id: 'x', categoria_id: null, tipo, monto, frecuencia, dia_ancla: 1, proxima_fecha: '2026-12-01', activa })
  const items = [r('mensual', 1000), r('quincenal', 500), r('semanal', 120), r('mensual', 999, 'gasto', false), r('mensual', 5000, 'ingreso')]
  assert.equal(Math.round(totalMensualEstimado(items, 'gasto')), 1000 + 1000 + 520)
  assert.equal(totalMensualEstimado(items, 'ingreso'), 5000)
})

test('estado del presupuesto: 75 % aviso, 100 % excedido', () => {
  assert.equal(estadoPresupuesto(74.9, 100), 'ok')
  assert.equal(estadoPresupuesto(75, 100), 'aviso')
  assert.equal(estadoPresupuesto(100, 100), 'excedido')
  assert.equal(estadoPresupuesto(10, 0), 'ok')
})

test('alertas: solo las que pasan del 75 %, de mayor a menor', () => {
  const cats = [{ id: 'c1', nombre: 'Comida', tipo: 'gasto' }, { id: 'c2', nombre: 'Ocio', tipo: 'gasto' }, { id: 'c3', nombre: 'Casa', tipo: 'gasto' }]
  const pres = [{ categoria_id: 'c1', limite_mensual: 100 }, { categoria_id: 'c2', limite_mensual: 100 }, { categoria_id: 'c3', limite_mensual: 100 }]
  const tx = (categoria_id, monto, tipo = 'gasto') => ({ id: 'x', categoria_id, monto, tipo, fecha: '2026-11-01' })
  const movs = [tx('c1', 80), tx('c2', 130), tx('c3', 50), tx('c3', 500, 'ingreso')]
  const alertas = budgetAlerts(pres, movs, cats)
  assert.deepEqual(alertas.map(a => [a.nombre, a.estado, Math.round(a.porcentaje)]), [['Ocio', 'excedido', 130], ['Comida', 'aviso', 80]])
})

test('top de gasto agrupa el resto en "Otras"', () => {
  const cats = [1, 2, 3, 4].map(i => ({ id: `c${i}`, nombre: `Cat ${i}`, tipo: 'gasto' }))
  const tx = (categoria_id, monto) => ({ id: 'x', categoria_id, monto, tipo: 'gasto', fecha: '2026-11-01' })
  const movs = [tx('c1', 40), tx('c2', 30), tx('c3', 20), tx('c4', 10), tx(null, 5)]
  assert.deepEqual(topSpending(movs, cats, 3), [{ nombre: 'Cat 1', total: 40 }, { nombre: 'Cat 2', total: 30 }, { nombre: 'Otras', total: 35 }])
  assert.deepEqual(topSpending(movs.slice(4), cats), [{ nombre: 'Sin categoría', total: 5 }])
})
