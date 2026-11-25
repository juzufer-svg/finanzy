// Pruebas de las utilidades de cuentas de dinero (CHG-019 fase a, UC-016, CT-012). Se ejecutan con `npm test`.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  TIPOS_CUENTA, TOPE_COP, NOMBRE_CUENTA_MAX, tipoLabel, estadoLabel, normalizarCuenta, normalizarCuentas, separarCuentas,
  nombreVisible, opcionesSelector, nombreDeCuenta, cuentaIdParaPut, textoSaldo, notaDeuda, validarCuenta, cambiosCuenta,
  mensajeErrorCuenta,
} from '../lib/cuentas.ts'

const fmt = n => `$${n}`
const err = (status, detail) => ({ response: { status, data: detail === undefined ? {} : { detail } } })

test('los cuatro tipos de CT-012, con etiqueta en español', () => {
  assert.deepEqual(TIPOS_CUENTA.map(t => t.value), ['efectivo', 'ahorros_corriente', 'billetera_digital', 'tarjeta_credito'])
  assert.equal(tipoLabel('tarjeta_credito'), 'Tarjeta de crédito')
  assert.equal(tipoLabel('cripto'), 'Otra')
  assert.equal(tipoLabel(undefined), 'Otra')
})

test('el estado se dice con palabras', () => {
  assert.equal(estadoLabel(true), 'Archivada')
  assert.equal(estadoLabel(false), 'No archivada')
})

test('normalizarCuenta: lista blanca, saldo numérico o texto, archivada solo con true', () => {
  const c = normalizarCuenta({
    id: 'a1', nombre: 'Efectivo', tipo: 'efectivo', saldo_inicial: '1000.50', saldo: 98500.5, archivada: false,
    usuario_id: 'u', secreto: 'x',
  })
  assert.deepEqual(c, { id: 'a1', nombre: 'Efectivo', tipo: 'efectivo', saldo_inicial: 1000.5, saldo: 98500.5, archivada: false })
  assert.equal(normalizarCuenta({ id: 'a', nombre: 'X', archivada: 'true' }).archivada, false)
  assert.equal(normalizarCuenta({ id: 'a', nombre: 'X', archivada: true }).archivada, true)
})

test('normalizarCuenta: tipo desconocido, saldo inválido y datos rotos', () => {
  const c = normalizarCuenta({ id: 'a', nombre: 'X', tipo: 'cripto', saldo: 'abc', saldo_inicial: null })
  assert.equal(c.tipo, null)
  assert.equal(c.saldo, null)
  assert.equal(c.saldo_inicial, 0)
  assert.equal(normalizarCuenta(null), null)
  assert.equal(normalizarCuenta([]), null)
  assert.equal(normalizarCuenta({ nombre: 'sin id' }), null)
  assert.equal(normalizarCuenta({ id: 'a', nombre: 5 }), null)
  assert.equal(normalizarCuenta({ id: '', nombre: 'X' }), null)
  assert.equal(normalizarCuenta({ id: 'a', nombre: 'X', saldo: Infinity }).saldo, null)
})

test('normalizarCuentas: ignora lo roto y ordena por nombre', () => {
  assert.deepEqual(normalizarCuentas('no es lista'), [])
  assert.deepEqual(normalizarCuentas(undefined), [])
  const lista = normalizarCuentas([{ id: '2', nombre: 'Zeta' }, 7, { id: '1', nombre: 'ahorros' }, { nombre: 'sin id' }])
  assert.deepEqual(lista.map(c => c.id), ['1', '2'])
})

test('separarCuentas y nombre visible', () => {
  const l = normalizarCuentas([{ id: '1', nombre: 'A' }, { id: '2', nombre: 'B', archivada: true }])
  const { activas, archivadas } = separarCuentas(l)
  assert.deepEqual(activas.map(c => c.id), ['1'])
  assert.deepEqual(archivadas.map(c => c.id), ['2'])
  assert.equal(nombreVisible(archivadas[0]), 'B (archivada)')
  assert.equal(nombreVisible(activas[0]), 'A')
})

test('el selector solo ofrece las no archivadas, salvo la que ya tiene la transacción', () => {
  const l = normalizarCuentas([{ id: '1', nombre: 'A' }, { id: '2', nombre: 'B', archivada: true }, { id: '3', nombre: 'C', archivada: true }])
  assert.deepEqual(opcionesSelector(l).map(o => o.id), ['1'])
  assert.deepEqual(opcionesSelector(l, null).map(o => o.id), ['1'])
  assert.deepEqual(opcionesSelector(l, '2'), [{ id: '1', label: 'A' }, { id: '2', label: 'B (archivada)' }])
  assert.deepEqual(opcionesSelector([]), [])
})

test('nombre de la cuenta de una transacción', () => {
  const l = normalizarCuentas([{ id: '1', nombre: 'Efectivo' }])
  assert.equal(nombreDeCuenta(l, '1'), 'Efectivo')
  assert.equal(nombreDeCuenta(l, null), null)
  assert.equal(nombreDeCuenta(l, ''), null)
  assert.equal(nombreDeCuenta(l, 'desconocida'), null)
  assert.equal(nombreDeCuenta(l, 5), null)
})

test('cuenta_id en PUT: sin cambio no se envía, vacío quita, valor reemplaza', () => {
  assert.deepEqual(cuentaIdParaPut('a', 'a'), {})
  assert.deepEqual(cuentaIdParaPut(null, ''), {})
  assert.deepEqual(cuentaIdParaPut(undefined, ''), {})
  assert.deepEqual(cuentaIdParaPut('a', ''), { cuenta_id: null })
  assert.deepEqual(cuentaIdParaPut(null, 'b'), { cuenta_id: 'b' })
  assert.deepEqual(cuentaIdParaPut('a', 'b'), { cuenta_id: 'b' })
})

test('saldos con signo y aviso de deuda en tarjetas', () => {
  assert.equal(textoSaldo(1500, fmt), '$1500')
  assert.equal(textoSaldo(-1500, fmt), '-$1500')
  assert.equal(textoSaldo(0, fmt), '$0')
  assert.equal(textoSaldo(null, fmt), '—')
  assert.equal(notaDeuda({ tipo: 'tarjeta_credito', saldo: -10 }), 'Deuda')
  assert.equal(notaDeuda({ tipo: 'tarjeta_credito', saldo: 10 }), null)
  assert.equal(notaDeuda({ tipo: 'efectivo', saldo: -10 }), null)
  assert.equal(notaDeuda({ tipo: 'tarjeta_credito', saldo: null }), null)
})

test('validarCuenta: nombre, tipo y saldo (INV-051)', () => {
  const ok = { nombre: ' Efectivo ', tipo: 'efectivo', saldoInicial: 100000 }
  assert.equal(validarCuenta(ok), null)
  assert.equal(validarCuenta({ ...ok, saldoInicial: 0 }), null)
  assert.equal(validarCuenta({ ...ok, saldoInicial: TOPE_COP }), null)
  assert.match(validarCuenta({ ...ok, nombre: '   ' }), /nombre/)
  assert.equal(validarCuenta({ ...ok, nombre: 'x'.repeat(NOMBRE_CUENTA_MAX) }), null)
  assert.match(validarCuenta({ ...ok, nombre: 'x'.repeat(NOMBRE_CUENTA_MAX + 1) }), /100/)
  assert.match(validarCuenta({ ...ok, tipo: 'cripto' }), /tipo/)
  assert.match(validarCuenta({ ...ok, saldoInicial: NaN }), /saldo inicial válido/)
  assert.match(validarCuenta({ ...ok, saldoInicial: TOPE_COP + 0.01 }), /máximo/)
  assert.match(validarCuenta({ ...ok, saldoInicial: -1 }), /tarjetas de crédito/)
  assert.equal(validarCuenta({ ...ok, tipo: 'tarjeta_credito', saldoInicial: -5000 }), null)
  assert.match(validarCuenta({ ...ok, tipo: 'tarjeta_credito', saldoInicial: -(TOPE_COP + 1) }), /máximo/)
})

test('cambiosCuenta: solo envía lo que cambió y recorta el nombre', () => {
  const orig = { nombre: 'Efectivo', saldo_inicial: 1000 }
  assert.deepEqual(cambiosCuenta(orig, { nombre: ' Efectivo ', saldoInicial: 1000 }), {})
  assert.deepEqual(cambiosCuenta(orig, { nombre: ' Billetera ', saldoInicial: 1000 }), { nombre: 'Billetera' })
  assert.deepEqual(cambiosCuenta(orig, { nombre: 'Efectivo', saldoInicial: 2000 }), { saldo_inicial: 2000 })
  assert.deepEqual(cambiosCuenta(orig, { nombre: 'B', saldoInicial: 0 }), { nombre: 'B', saldo_inicial: 0 })
})

test('mensajes de error: 409 y 422 con texto del servidor, 404, 503 y sin conexión', () => {
  const saldo = 'Saldo insuficiente: esto dejaría la cuenta «Efectivo» en negativo. Solo las tarjetas de crédito pueden quedar en negativo.'
  assert.equal(mensajeErrorCuenta(err(409, saldo), 'x'), saldo)
  assert.equal(mensajeErrorCuenta(err(409, 'Ya tienes una cuenta con ese nombre'), 'x'), 'Ya tienes una cuenta con ese nombre')
  assert.equal(mensajeErrorCuenta(err(409, 'Llegaste al máximo de 20 cuentas'), 'x'), 'Llegaste al máximo de 20 cuentas')
  assert.equal(mensajeErrorCuenta(err(404, 'Cuenta no encontrada'), 'x'), 'Cuenta no encontrada')
  assert.match(mensajeErrorCuenta(err(404), 'x'), /ya no existe/)
  assert.equal(mensajeErrorCuenta(err(422, 'Elige un tipo válido'), 'x'), 'Elige un tipo válido')
  assert.equal(mensajeErrorCuenta(err(422, [{ msg: 'raro' }]), 'x'), 'Revisa los datos ingresados.')
  assert.match(mensajeErrorCuenta(err(503, 'texto interno'), 'x'), /^El servicio no está disponible/)
  assert.doesNotMatch(mensajeErrorCuenta(err(503, 'texto interno'), 'x'), /interno|cuentas/)   // genérico: sirve a TransactionForm
  // todo lo que no es 404/409/422 se delega en apiErrorMessage: un 401 conserva su texto y uno sin texto cae al respaldo
  assert.equal(mensajeErrorCuenta(err(401, 'No autenticado'), 'x'), 'No autenticado')
  assert.equal(mensajeErrorCuenta(err(401), 'No se pudo'), 'No se pudo')
  assert.equal(mensajeErrorCuenta(err(403, 'Prohibido'), 'x'), 'Prohibido')
  assert.match(mensajeErrorCuenta(err(429), 'x'), /Demasiados/)
  assert.match(mensajeErrorCuenta(new Error('red'), 'x'), /conexión/)
  assert.match(mensajeErrorCuenta(undefined, 'x'), /conexión/)
  assert.equal(mensajeErrorCuenta(err(500), 'No se pudo'), 'No se pudo')
})

// ---- Fase (c) · CHG-025 T10: abono con cuenta, recurrentes y confirmación ----
import { cuerpoAbono, cuerpoConfirmar, avisoSaldo } from '../lib/cuentas.ts'

test('abono: sin cuenta no se envía cuenta_id; con cuenta sí', () => {
  const base = { monto: 50, descripcion: 'Abono', fecha: '2026-11-25' }
  assert.deepEqual(cuerpoAbono({ ...base, cuentaId: '' }), base)
  assert.ok(!('cuenta_id' in cuerpoAbono({ ...base, cuentaId: '' })))
  assert.deepEqual(cuerpoAbono({ ...base, cuentaId: 'c1' }), { ...base, cuenta_id: 'c1' })
})

test('confirmar: cuenta_id solo si la persona la tocó; null = quitar', () => {
  const b = { ocurrencia: '2026-11-25', cuentaOriginal: 'c1' }
  assert.deepEqual(cuerpoConfirmar({ ...b, cuentaElegida: 'c1' }), { ocurrencia: '2026-11-25' })
  assert.deepEqual(cuerpoConfirmar({ ...b, cuentaElegida: 'c2' }), { ocurrencia: '2026-11-25', cuenta_id: 'c2' })
  assert.deepEqual(cuerpoConfirmar({ ...b, cuentaElegida: '' }), { ocurrencia: '2026-11-25', cuenta_id: null })
  assert.deepEqual(cuerpoConfirmar({ ocurrencia: 'x', cuentaOriginal: null, cuentaElegida: '', monto: 9 }), { ocurrencia: 'x', monto: 9 })
  assert.deepEqual(cuerpoConfirmar({ ocurrencia: 'x', cuentaOriginal: undefined, cuentaElegida: 'c3' }), { ocurrencia: 'x', cuenta_id: 'c3' })
})

test('aviso de saldo: solo si el monto supera el saldo y no es tarjeta; no bloquea', () => {
  const ahorros = { nombre: 'Ahorros', tipo: 'ahorros_corriente', saldo: 100 }
  assert.equal(avisoSaldo(ahorros, 100, fmt), null)
  assert.equal(avisoSaldo(ahorros, 0, fmt), null)
  assert.equal(avisoSaldo(undefined, 500, fmt), null)
  assert.equal(avisoSaldo({ ...ahorros, saldo: null }, 500, fmt), null)
  assert.equal(avisoSaldo({ ...ahorros, tipo: 'tarjeta_credito' }, 500, fmt), null)
  assert.match(avisoSaldo(ahorros, 100.01, fmt), /supera el saldo de «Ahorros» \(\$100\)/)
})

test('abono/confirmar: mensajes de 409, 404, 422 y 503 con mensajeErrorCuenta', () => {
  assert.equal(mensajeErrorCuenta(err(409, 'Saldo insuficiente'), 'x'), 'Saldo insuficiente')
  assert.equal(mensajeErrorCuenta(err(409, 'La cuenta está archivada'), 'x'), 'La cuenta está archivada')
  assert.equal(mensajeErrorCuenta(err(404, 'Cuenta no encontrada'), 'x'), 'Cuenta no encontrada')
  assert.equal(mensajeErrorCuenta(err(422, 'Monto inválido'), 'x'), 'Monto inválido')
  assert.match(mensajeErrorCuenta(err(503, 'texto interno'), 'x'), /no está disponible/)
  assert.doesNotMatch(mensajeErrorCuenta(err(503, 'texto interno'), 'x'), /interno/)
})
