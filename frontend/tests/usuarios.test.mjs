// Pruebas de las utilidades del panel de usuarios del Dueño (CHG-023, UC-017, CT-013). Se ejecutan con `npm test`.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  POR_PAGINA, formatFechaHora, formatFecha, formatUltimoAcceso, formatCantidad, etiquetaEstado, filtrarPorEstado,
  etiquetaAccion, busquedaValida, paginasTotales, normalizarLista, normalizarDetalle, normalizarAuditoria,
  correoCoincide, validarEliminar, mensajeDeError, FILTROS_ESTADO,
} from '../lib/usuarios.ts'

const ID = '11111111-1111-4111-8111-111111111111'
const usuario = (extra = {}) => ({
  id: ID, correo: 'ana@ejemplo.com', nombre: 'Ana Pérez', estado: 'activa', moneda: 'COP',
  registrado_en: '2026-11-20T10:00:00Z', ultimo_acceso: '2026-11-25T09:00:00Z', es_dueno: false, uso: { transacciones: 42 }, ...extra,
})

test('la página es de 25', () => assert.equal(POR_PAGINA, 25))

test('fecha en hora de Colombia (UTC-5) sin Intl', () => {
  assert.equal(formatFechaHora('2026-11-25T15:00:00Z'), '25 nov 2026, 10:00 a. m.')
  assert.equal(formatFechaHora('2026-11-25T03:30:00Z'), '24 nov 2026, 10:30 p. m.')
  assert.equal(formatFechaHora('2026-01-01T05:00:00Z'), '1 ene 2026, 12:00 a. m.')
  assert.equal(formatFechaHora('2026-11-25T17:05:00Z'), '25 nov 2026, 12:05 p. m.')
  assert.equal(formatFechaHora('basura'), '—')
  assert.equal(formatFechaHora(null), '—')
  assert.equal(formatFecha('2026-11-25T03:30:00Z'), '24 nov 2026')
  assert.equal(formatFecha(undefined), '—')
})

test('último acceso nulo se muestra «Nunca»', () => {
  assert.equal(formatUltimoAcceso(null), 'Nunca')
  assert.equal(formatUltimoAcceso('2026-11-25T15:00:00Z'), '25 nov 2026, 10:00 a. m.')
})

test('cantidades con separador de miles y valores inválidos', () => {
  assert.equal(formatCantidad(0), '0')
  assert.equal(formatCantidad(12345), '12.345')
  assert.equal(formatCantidad(-1), '—')
  assert.equal(formatCantidad('3'), '—')
  assert.equal(formatCantidad(1.5), '—')
})

test('etiqueta de estado con texto', () => {
  assert.equal(etiquetaEstado('activa'), 'Activa')
  assert.equal(etiquetaEstado('suspendida'), 'Suspendida')
  assert.equal(etiquetaEstado('pendiente'), 'Pendiente')
  assert.equal(etiquetaEstado('otro'), '—')
  assert.deepEqual(FILTROS_ESTADO.map(f => f.valor), ['todos', 'activa', 'suspendida', 'pendiente'])
})

test('filtro por estado sobre la página cargada', () => {
  const us = [usuario(), usuario({ estado: 'suspendida' }), usuario({ estado: 'pendiente' })]
  assert.equal(filtrarPorEstado(us, 'todos').length, 3)
  assert.deepEqual(filtrarPorEstado(us, 'suspendida').map(u => u.estado), ['suspendida'])
})

test('nombre de las acciones de auditoría', () => {
  assert.equal(etiquetaAccion('suspender'), 'Suspendió una cuenta')
  assert.equal(etiquetaAccion('eliminar'), 'Eliminó una cuenta')
  assert.equal(etiquetaAccion('x'), '—')
})

test('búsqueda: 1 a 60, sin control; vacía es válida', () => {
  assert.equal(busquedaValida(''), true)
  assert.equal(busquedaValida('   '), true)
  assert.equal(busquedaValida('ana'), true)
  assert.equal(busquedaValida('a'.repeat(60)), true)
  assert.equal(busquedaValida('a'.repeat(61)), false)
  assert.equal(busquedaValida('a\u0000b'), false)
  assert.equal(busquedaValida('50%_\\'), true)
})

test('páginas totales: mínimo 1 y tope 400', () => {
  assert.equal(paginasTotales(0), 1)
  assert.equal(paginasTotales(25), 1)
  assert.equal(paginasTotales(26), 2)
  assert.equal(paginasTotales(99999), 400)
  assert.equal(paginasTotales('x'), 1)
})

test('normalizar la lista descarta claves desconocidas y datos sensibles', () => {
  const raw = {
    generado_en: '2026-11-25T15:00:00Z', pagina: 1, por_pagina: 25, total: 2, total_paginas: 1,
    usuarios: [
      usuario({ hashed_password: 'x', session_version: 3, monto: 5000, uso: { transacciones: 42, monto_total: 9 } }),
      usuario({ id: null, correo: 'dueno@ejemplo.com', es_dueno: true }),
      usuario({ estado: 'rara' }),
      'no es objeto',
    ],
  }
  const l = normalizarLista(raw)
  assert.ok(l)
  assert.equal(l.usuarios.length, 2)
  const u = l.usuarios[0]
  assert.deepEqual(Object.keys(u).sort(), ['correo', 'es_dueno', 'estado', 'id', 'moneda', 'nombre', 'registrado_en', 'ultimo_acceso', 'uso'])
  assert.deepEqual(Object.keys(u.uso).sort(), ['categorias', 'metas', 'presupuestos', 'recurrentes', 'transacciones', 'whatsapp_conectado'])
  assert.equal(u.uso.transacciones, 42)
  assert.equal(u.uso.categorias, null)
  assert.equal(JSON.stringify(l).includes('hashed_password'), false)
  assert.equal(l.usuarios[1].id, null)
  assert.equal(l.usuarios[1].es_dueno, true)
})

test('normalizar rechaza respuestas con forma inesperada', () => {
  assert.equal(normalizarLista(null), null)
  assert.equal(normalizarLista({ usuarios: 'x' }), null)
  assert.equal(normalizarDetalle({ correo: 'a@b.co', estado: 'activa', id: 'no-uuid' }), null)
  assert.equal(normalizarAuditoria({}), null)
})

test('detalle con conteos y WhatsApp', () => {
  const d = normalizarDetalle(usuario({ uso: { transacciones: 1, categorias: 2, presupuestos: 3, metas: 4, recurrentes: 5, whatsapp_conectado: true } }))
  assert.deepEqual(d.uso, { transacciones: 1, categorias: 2, presupuestos: 3, metas: 4, recurrentes: 5, whatsapp_conectado: true })
})

test('normalizar la auditoría', () => {
  const a = normalizarAuditoria({
    generado_en: '2026-11-25T15:00:00Z', pagina: 2, total: 30, total_paginas: 2,
    registros: [
      { id: 7, fecha: '2026-11-25T15:01:00Z', accion: 'suspender', usuario_id: ID, usuario_correo: 'ana@ejemplo.com', ip: '1.1.1.1' },
      { id: 8, fecha: '2026-11-25T15:02:00Z', accion: 'eliminar', usuario_id: ID, usuario_correo: null },
      { id: 9, fecha: 'x', accion: 'hackear', usuario_id: ID, usuario_correo: null },
    ],
  })
  assert.equal(a.registros.length, 2)
  assert.equal(a.pagina, 2)
  assert.equal(a.registros[1].usuario_correo, null)
  assert.equal('ip' in a.registros[0], false)
})

test('el correo de confirmación coincide sin importar mayúsculas ni espacios', () => {
  assert.equal(correoCoincide('  ANA@Ejemplo.com ', 'ana@ejemplo.com'), true)
  assert.equal(correoCoincide('ana@ejemplo.co', 'ana@ejemplo.com'), false)
  assert.equal(correoCoincide('', ''), false)
})

test('validar eliminar exige correo exacto y contraseña', () => {
  assert.equal(validarEliminar('ana@ejemplo.com', 'ana@ejemplo.com', 'Clave').valido, true)
  const r1 = validarEliminar('otra@ejemplo.com', 'ana@ejemplo.com', 'Clave')
  assert.equal(r1.valido, false)
  assert.ok(r1.errores.correo)
  const r2 = validarEliminar('ana@ejemplo.com', 'ana@ejemplo.com', '')
  assert.equal(r2.valido, false)
  assert.ok(r2.errores.contrasena)
  assert.equal(validarEliminar('ana@ejemplo.com', 'ana@ejemplo.com', 'x'.repeat(129)).valido, false)
})

test('mensajes de error de 403, 404, 409, 422, 429 y 503', () => {
  assert.equal(mensajeDeError(403, 'Contraseña incorrecta', 'eliminar'), 'La contraseña es incorrecta.')
  assert.match(mensajeDeError(404, 'Usuario no encontrado'), /ya no existe/)
  assert.equal(mensajeDeError(409, 'La cuenta ya está suspendida'), 'La cuenta ya está suspendida')
  assert.match(mensajeDeError(409, undefined), /Actualiza/)
  assert.equal(mensajeDeError(422, 'El correo escrito no coincide con el de la cuenta'), 'El correo escrito no coincide con el de la cuenta')
  assert.match(mensajeDeError(429, undefined), /Demasiados/)
  assert.match(mensajeDeError(503, undefined), /Revisa el estado/)
  assert.equal(mensajeDeError(500, 'x'), null)
})
