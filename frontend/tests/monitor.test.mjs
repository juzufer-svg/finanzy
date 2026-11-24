// Pruebas de las utilidades del Monitor de consumos (CHG-017, UC-014). Se ejecutan con `npm test`.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  TEXTO_NO_DISPONIBLE, PLATAFORMAS, formatBytes, formatNumero, formatUsd, formatFechaDia, formatInstante,
  camposVisibles, notaPlataforma, NOTA_ESTIMADO_CONTADORES, estadoPlataforma, porcentajeUso, normalizarResumen, sumarDias, serieDias, diaDeInstante,
  total, alturasApiladas,
} from '../lib/monitor.ts'

test('texto de no disponible, sin motivo', () => {
  assert.equal(TEXTO_NO_DISPONIBLE, 'No disponible')
})

test('las seis plataformas, en orden', () => {
  assert.deepEqual(PLATAFORMAS.map(p => p.clave), ['railway', 'anthropic', 'meta', 'supabase', 'vercel', 'brevo'])
})

test('bytes legibles', () => {
  assert.equal(formatBytes(0), '0 B')
  assert.equal(formatBytes(512), '512 B')
  assert.equal(formatBytes(1024), '1 KB')
  assert.equal(formatBytes(1536), '1,5 KB')
  assert.equal(formatBytes(500 * 1024 * 1024), '500 MB')
  assert.equal(formatBytes(1024 ** 3 * 100), '100 GB')
  assert.equal(formatBytes(-1), '—')
  assert.equal(formatBytes(NaN), '—')
  assert.equal(formatBytes('12'), '—')
})

test('números y dólares con separadores', () => {
  assert.equal(formatNumero(1234567), '1.234.567')
  assert.equal(formatNumero(0), '0')
  assert.equal(formatNumero(12.5), '12,5')
  assert.equal(formatNumero(null), '—')
  assert.equal(formatUsd(12.5), 'US$ 12,50')
  assert.equal(formatUsd(1234.567), 'US$ 1.234,57')
  assert.equal(formatUsd(undefined), '—')
})

test('fechas de día y hora de Colombia', () => {
  assert.equal(formatFechaDia('2026-11-24'), '24 nov 2026')
  assert.equal(formatFechaDia('2026-13-01'), '—')
  assert.equal(formatFechaDia('hola'), '—')
  assert.equal(formatInstante('2026-11-24T15:00:00Z'), '24 nov 2026, 10:00 a. m.')   // Colombia = UTC−5
  assert.equal(formatInstante('2026-11-24T11:42:00Z'), '24 nov 2026, 6:42 a. m.')
  assert.equal(formatInstante('2026-11-24T23:30:00Z'), '24 nov 2026, 6:30 p. m.')
  assert.equal(formatInstante('2026-11-25T03:00:00Z'), '24 nov 2026, 10:00 p. m.')     // cruza el día hacia atrás
  assert.equal(formatInstante('2026-12-01T02:00:00Z'), '30 nov 2026, 9:00 p. m.')      // cruza el mes
  assert.equal(formatInstante('2026-11-24T05:00:00Z'), '24 nov 2026, 12:00 a. m.')     // medianoche
  assert.equal(formatInstante('2026-11-24T17:00:00Z'), '24 nov 2026, 12:00 p. m.')     // mediodía
  assert.equal(formatInstante(null), '—')
  assert.equal(diaDeInstante('2026-11-24T15:00:00Z'), '2026-11-24')
  assert.equal(diaDeInstante('2026-11-25T03:00:00Z'), '2026-11-24')   // Colombia = UTC−5: aún es el 24
  assert.equal(diaDeInstante('2026-11-24T05:00:00Z'), '2026-11-24')
  assert.equal(diaDeInstante('2026-11-24T04:59:00Z'), '2026-11-23')
  assert.equal(diaDeInstante('2026-12-01T02:00:00Z'), '2026-11-30')   // cruza de mes
  assert.equal(diaDeInstante('x'), null)
})

test('campos visibles: solo lista blanca y valores válidos', () => {
  const campos = camposVisibles('supabase', {
    tamano_bd_bytes: 1024 * 1024, limite_bd_bytes: 500 * 1024 * 1024, token: 'secreto', otro: 5,
  })
  assert.deepEqual(campos.map(c => c.clave), ['tamano_bd_bytes', 'limite_bd_bytes'])
  assert.deepEqual(campos.map(c => c.valor), ['1 MB', '500 MB'])
  assert.ok(!JSON.stringify(campos).includes('secreto'))
  const r = camposVisibles('railway', { costo_estimado_mes: 3.2, moneda: 'USD', periodo_hasta: '2026-11-30' })
  assert.deepEqual(r.map(c => c.valor), ['US$ 3,20', '30 nov 2026'])
  const g = camposVisibles('railway', { costo_estimado_mes: 0.0379, creditos_saldo: 0, moneda: 'USD', periodo_hasta: '2026-12-22' })
  assert.deepEqual(g.map(c => [c.etiqueta, c.valor]), [
    ['Gasto del período (US$)', 'US$ 0,04'], ['Créditos prepagados (US$)', 'US$ 0,00'], ['Período hasta', '22 dic 2026']])
  assert.deepEqual(camposVisibles('railway', { costo_estimado_mes: -1, creditos_saldo: 'x' }), [])
  assert.deepEqual(camposVisibles('vercel', { plan: 'gratuito', ancho_banda_bytes: -4 }).map(c => c.valor), ['Gratuito'])
  assert.deepEqual(camposVisibles('vercel', { plan: 'inventado' }), [])
  assert.deepEqual(camposVisibles('brevo', null), [])
})

test('Supabase: etiquetas de tamaño y límite en MB/GB', () => {
  const c = camposVisibles('supabase', { tamano_bd_bytes: 52428800, limite_bd_bytes: 524288000 })
  assert.deepEqual(c.map(x => [x.etiqueta, x.valor]), [['Tamaño de la BD', '50 MB'], ['Límite del plan', '500 MB']])
  assert.equal(camposVisibles('supabase', { tamano_bd_bytes: 2 * 1024 ** 3 })[0].valor, '2 GB')
  assert.equal(porcentajeUso(52428800, 524288000), 10)
})

test('Anthropic estimado con contadores propios: etiquetas, US$ sin conversor y nota', () => {
  const datos = { llamadas_mes: 1200, tokens_entrada_mes: 3500000, tokens_salida_mes: 40000, costo_mes: 0.37, moneda: 'USD', cuenta: 'x' }
  assert.deepEqual(camposVisibles('anthropic', datos).map(c => [c.etiqueta, c.valor]), [
    ['Llamadas del chat (mes)', '1.200'], ['Tokens de entrada (mes)', '3.500.000'],
    ['Tokens de salida (mes)', '40.000'], ['Costo estimado del mes (US$)', 'US$ 0,37']])
  assert.equal(notaPlataforma('anthropic', datos), 'Estimado a partir de los contadores propios (solo el chat; WhatsApp aparte)')
  assert.equal(NOTA_ESTIMADO_CONTADORES, notaPlataforma('anthropic', datos))
  // modelo desconocido: sin costo
  assert.deepEqual(camposVisibles('anthropic', { llamadas_mes: 1, tokens_entrada_mes: 2, tokens_salida_mes: 3 }).map(c => c.clave),
    ['llamadas_mes', 'tokens_entrada_mes', 'tokens_salida_mes'])
  // datos oficiales (clave de administración): sin nota y con las etiquetas oficiales
  const oficial = { costo_mes: 2.5, moneda: 'USD', tokens_entrada_mes: 10 }
  assert.equal(notaPlataforma('anthropic', oficial), null)
  assert.deepEqual(camposVisibles('anthropic', oficial).map(c => c.etiqueta), ['Tokens de entrada del mes', 'Costo del mes'])
  assert.equal(notaPlataforma('brevo', datos), null)
})

test('estado de plataforma: ok solo con algún campo mostrable', () => {
  assert.equal(estadoPlataforma('brevo', { estado: 'ok', datos: { enviados_hoy: 3 }, actualizado_en: null }), 'ok')
  assert.equal(estadoPlataforma('brevo', { estado: 'ok', datos: { raro: 3 }, actualizado_en: null }), 'no_disponible')
  assert.equal(estadoPlataforma('brevo', { estado: 'no_disponible', datos: null, actualizado_en: null }), 'no_disponible')
  assert.equal(estadoPlataforma('brevo', undefined), 'no_disponible')
})

test('porcentaje de uso', () => {
  assert.equal(porcentajeUso(50, 200), 25)
  assert.equal(porcentajeUso(300, 200), 100)
  assert.equal(porcentajeUso(1, 0), null)
  assert.equal(porcentajeUso(undefined, 10), null)
})

test('sumar días cruza meses y años', () => {
  assert.equal(sumarDias('2026-11-24', -29), '2026-10-26')
  assert.equal(sumarDias('2026-01-01', -1), '2025-12-31')
  assert.equal(sumarDias('2028-02-28', 1), '2028-02-29')
})

const dia = (fecha, extra = {}) => ({
  fecha,
  claude: {
    asistente: { llamadas: 4, tokens_entrada: 5200, tokens_salida: 900 },
    whatsapp: { llamadas: 2, tokens_entrada: 1800, tokens_salida: 300 },
  },
  brevo_correos_enviados: 3,
  whatsapp_mensajes: { enviados: 6, recibidos: 7 },
  ...extra,
})

test('serie de 30 días con ceros donde no hay datos', () => {
  const serie = serieDias([dia('2026-11-24'), dia('2026-11-20')], '2026-11-24')
  assert.equal(serie.length, 30)
  assert.equal(serie[0].fecha, '2026-10-26')
  assert.equal(serie[29].fecha, '2026-11-24')
  assert.equal(serie[29].claude_llamadas_asistente, 4)
  assert.equal(serie[29].claude_tokens_asistente, 6100)
  assert.equal(serie[29].claude_tokens_whatsapp, 2100)
  assert.equal(serie[29].wa_recibidos, 7)
  assert.equal(serie[28].correos, 0)
  assert.equal(serie[25].correos, 3) // 20 de noviembre
  assert.deepEqual(serieDias([], 'mal'), [])
  assert.equal(total(serie.map(p => p.correos)), 6)
})

test('alturas apiladas', () => {
  assert.deepEqual(alturasApiladas([5, 0], 10), [50, 0])
  assert.deepEqual(alturasApiladas([1], 1000), [1]) // mínimo visible
  assert.deepEqual(alturasApiladas([3, 4], 0), [0, 0])
})

test('normalizar el resumen: forma inválida, plataformas faltantes y datos sucios', () => {
  assert.equal(normalizarResumen(null), null)
  assert.equal(normalizarResumen({ contadores: {} }), null)
  const r = normalizarResumen({
    generado_en: '2026-11-24T15:00:00Z',
    contadores: { desde: '2026-11-24', dias: [dia('2026-11-24'), { fecha: 'mala' }, 7] },
    plataformas: {
      railway: { estado: 'ok', datos: { costo_estimado_mes: 2, anidado: { a: 1 } }, actualizado_en: '2026-11-24T14:59:30Z' },
      anthropic: { estado: 'no_disponible', datos: null, actualizado_en: null },
    },
  })
  assert.equal(r.contadores.dias.length, 1)
  assert.equal(r.contadores.desde, '2026-11-24')
  assert.equal(r.plataformas.railway.estado, 'ok')
  assert.deepEqual(Object.keys(r.plataformas.railway.datos), ['costo_estimado_mes'])
  for (const { clave } of PLATAFORMAS) assert.ok(r.plataformas[clave])
  assert.equal(r.plataformas.vercel.estado, 'no_disponible')
  const vacio = normalizarResumen({ generado_en: 'x', contadores: { desde: null, dias: [] }, plataformas: {} })
  assert.deepEqual(vacio.contadores.dias, [])
})

test('la serie de 30 días termina en el hoy de Colombia, no en el día UTC', () => {
  const hoy = diaDeInstante('2026-11-25T03:00:00Z')   // en UTC ya es el 25; en Colombia sigue el 24
  const serie = serieDias([], hoy, 30)
  assert.equal(serie[29].fecha, '2026-11-24')
  assert.equal(serie[0].fecha, '2026-10-26')
})
