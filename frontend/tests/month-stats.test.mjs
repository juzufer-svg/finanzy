// Pruebas de los cálculos del mes (CHG-006). Se ejecutan con `npm test` (node --test), sin librerías nuevas.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  monthOf, shiftMonth, daysInMonth, elapsedDays, sumByTipo, dailyAverage, projectMonthEnd,
  pctChange, totalsByCategory, compareByCategory, cumulativeByDay, totalBudget, normalizeText,
  filterTransactions, totalsByPaymentMethod, comparablePrevious,
} from '../lib/month-stats.ts'

const hoy = new Date(2026, 10, 22) // 22 de noviembre de 2026 (hora local)
const tx = (id, fecha, monto, tipo = 'gasto', categoria_id = 'c1', descripcion = '', medio_pago = null) =>
  ({ id, fecha, monto, tipo, categoria_id, descripcion, medio_pago })

test('meses: anterior, siguiente y cambio de año', () => {
  assert.equal(monthOf(hoy), '2026-11')
  assert.equal(shiftMonth('2026-01', -1), '2025-12')
  assert.equal(shiftMonth('2026-12', 1), '2027-01')
})

test('días reales del mes, incluido febrero bisiesto', () => {
  assert.equal(daysInMonth('2026-11'), 30)
  assert.equal(daysInMonth('2026-12'), 31)
  assert.equal(daysInMonth('2026-02'), 28)
  assert.equal(daysInMonth('2028-02'), 29)
})

test('días transcurridos: mes cerrado, en curso y futuro', () => {
  assert.equal(elapsedDays('2026-10', hoy), 31)
  assert.equal(elapsedDays('2026-11', hoy), 22)
  assert.equal(elapsedDays('2026-12', hoy), 0)
})

test('promedio diario real (BL-007): ya no divide siempre entre 30', () => {
  assert.equal(dailyAverage(310000, '2026-10', hoy), 10000) // octubre tiene 31 días
  assert.equal(dailyAverage(220000, '2026-11', hoy), 10000) // van 22 días de noviembre
  assert.equal(dailyAverage(100, '2026-12', hoy), null)     // diciembre no ha empezado
})

test('proyección al cierre solo en el mes en curso', () => {
  assert.equal(projectMonthEnd(220000, '2026-11', hoy), 300000) // 10.000 diarios × 30 días
  assert.equal(projectMonthEnd(220000, '2026-10', hoy), null)
  assert.equal(projectMonthEnd(0, '2026-11', new Date(2026, 10, 1)), 0)
})

test('variación porcentual frente al mes anterior', () => {
  assert.equal(pctChange(120, 100), 20)
  assert.equal(pctChange(80, 100), -20)
  assert.equal(pctChange(50, 0), null) // sin base para comparar
})

test('totales por tipo y por categoría (lo sin categoría va aparte)', () => {
  const items = [tx('1', '2026-11-01', 100), tx('2', '2026-11-02', 50, 'ingreso'), tx('3', '2026-11-03', 30, 'gasto', null)]
  assert.equal(sumByTipo(items, 'gasto'), 130)
  assert.equal(sumByTipo(items, 'ingreso'), 50)
  assert.deepEqual(totalsByCategory(items, 'gasto'), { c1: 100, '': 30 })
})

test('comparación por categoría ordenada por gasto actual', () => {
  const actual = [tx('1', '2026-11-01', 100, 'gasto', 'a'), tx('2', '2026-11-02', 300, 'gasto', 'b')]
  const anterior = [tx('3', '2026-10-01', 200, 'gasto', 'a'), tx('4', '2026-10-05', 70, 'gasto', 'z')]
  const filas = compareByCategory(actual, anterior)
  assert.deepEqual(filas.map(f => f.categoriaId), ['b', 'a', 'z'])
  assert.equal(filas[1].variacion, -50)
  assert.equal(filas[0].variacion, null) // categoría nueva este mes
  assert.equal(filas[2].actual, 0)
})

test('gasto acumulado día a día, cortado en hoy', () => {
  const items = [tx('1', '2026-11-01', 10), tx('2', '2026-11-03', 5), tx('3', '2026-11-03', 5, 'ingreso'), tx('4', '2026-10-31', 99)]
  const serie = cumulativeByDay(items, '2026-11')
  assert.equal(serie.length, 30)
  assert.deepEqual(serie.slice(0, 4), [10, 10, 15, 15])
  assert.equal(serie[29], 15)
  assert.deepEqual(cumulativeByDay(items, '2026-11', 'gasto', 2), [10, 10])
})

test('presupuesto total: solo categorías de gasto', () => {
  const cats = [{ id: 'g', nombre: 'Comida', tipo: 'gasto' }, { id: 'i', nombre: 'Sueldo', tipo: 'ingreso' }]
  assert.equal(totalBudget([{ categoria_id: 'g', limite_mensual: 500 }, { categoria_id: 'i', limite_mensual: 900 }], cats), 500)
})

test('buscador: sin tildes ni mayúsculas, por descripción o categoría', () => {
  const cats = [{ id: 'c1', nombre: 'Alimentación', tipo: 'gasto' }, { id: 'c2', nombre: 'Transporte', tipo: 'gasto' }]
  const items = [
    tx('1', '2026-11-01', 10, 'gasto', 'c1', 'Mercado D1', 'debito'),
    tx('2', '2026-11-02', 20, 'gasto', 'c2', 'Gasolina', 'credito'),
    tx('3', '2026-11-03', 30, 'gasto', null, 'Regalo cumpleaños', null),
  ]
  assert.equal(normalizeText('  Cumpleaños '), 'cumpleanos')
  assert.deepEqual(filterTransactions(items, { texto: 'ALIMENTACION' }, cats).map(t => t.id), ['1'])
  assert.deepEqual(filterTransactions(items, { texto: 'cumpleanos' }, cats).map(t => t.id), ['3'])
  assert.deepEqual(filterTransactions(items, { categoriaId: 'c2' }, cats).map(t => t.id), ['2'])
  assert.deepEqual(filterTransactions(items, { categoriaId: '__sin__' }, cats).map(t => t.id), ['3'])
  assert.deepEqual(filterTransactions(items, { medioPago: 'debito' }, cats).map(t => t.id), ['1'])
  assert.deepEqual(filterTransactions(items, { medioPago: '__sin__' }, cats).map(t => t.id), ['3'])
  assert.equal(filterTransactions(items, {}, cats).length, 3)
})

test('gasto por medio de pago, de mayor a menor (CHG-007)', () => {
  const items = [
    tx('1', '2026-11-01', 10, 'gasto', 'c1', '', 'debito'),
    tx('2', '2026-11-02', 50, 'gasto', 'c1', '', 'efectivo'),
    tx('3', '2026-11-03', 15, 'gasto', 'c1', '', 'debito'),
    tx('4', '2026-11-04', 5, 'gasto', 'c1', '', null),
    tx('5', '2026-11-05', 999, 'ingreso', 'c1', '', 'transferencia'),
  ]
  assert.deepEqual(totalsByPaymentMethod(items), [
    { medio: 'efectivo', total: 50 }, { medio: 'debito', total: 25 }, { medio: '', total: 5 },
  ])
})

test('en el mes en curso se compara con el mes anterior hasta el mismo día', () => {
  const octubre = [tx('1', '2026-10-05', 10), tx('2', '2026-10-22', 20), tx('3', '2026-10-28', 40)]
  assert.deepEqual(comparablePrevious(octubre, '2026-11', hoy).map(t => t.id), ['1', '2'])
  assert.equal(comparablePrevious(octubre, '2026-10', hoy).length, 3) // mes cerrado: completo
})
