// Pruebas de las utilidades del Monitor de consumos (CHG-017, UC-014). Se ejecutan con `npm test`.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  TEXTO_NO_DISPONIBLE, PLATAFORMAS, formatBytes, formatNumero, formatUsd, formatFechaDia, formatInstante,
  camposVisibles, notaPlataforma, NOTA_ESTIMADO_CONTADORES, estadoPlataforma, normalizarResumen, sumarDias, serieDias, diaDeInstante,
  total, alturasApiladas, resumenPlan, formatPorcentaje, LIMITES_PLAN,
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
})

test('Anthropic estimado con contadores propios: etiquetas, US$ sin conversor y nota', () => {
  const datos = { llamadas_mes: 1200, llamadas_asistente_mes: 1000, llamadas_whatsapp_mes: 200,
    tokens_entrada_mes: 3500000, tokens_salida_mes: 40000, costo_mes: 0.37, moneda: 'USD', cuenta: 'x' }
  assert.deepEqual(camposVisibles('anthropic', datos).map(c => [c.etiqueta, c.valor]), [
    ['Llamadas (total)', '1.200'], ['Asistente IA (llamadas del mes)', '1.000'], ['WhatsApp (llamadas del mes)', '200'],
    ['Tokens de entrada (mes)', '3.500.000'],
    ['Tokens de salida (mes)', '40.000'], ['Costo estimado del mes (US$)', 'US$ 0,37']])
  assert.equal(notaPlataforma('anthropic', datos), 'Estimado a partir de los contadores propios')
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

// ---- Plan, límite y uso (REQ-F-018 CA-6) ----
const diaWa = (fecha, enviados) => ({
  fecha, claude: { asistente: { llamadas: 0, tokens_entrada: 0, tokens_salida: 0 }, whatsapp: { llamadas: 0, tokens_entrada: 0, tokens_salida: 0 } },
  brevo_correos_enviados: 0, whatsapp_mensajes: { enviados, recibidos: 99 },
})

test('porcentaje en texto: un decimal si es menor de 10 %, truncado', () => {
  assert.equal(formatPorcentaje(0), '0 %')
  assert.equal(formatPorcentaje(5.26), '5,2 %')
  assert.equal(formatPorcentaje(7.1), '7,1 %')
  assert.equal(formatPorcentaje(10), '10 %')
  assert.equal(formatPorcentaje(79.96), '79 %')
  assert.equal(formatPorcentaje(100), '100 %')
  assert.equal(formatPorcentaje(NaN), '—')
})

test('resumenPlan Railway: uso en US$ sobre US$5 y niveles 79,9 / 80 / 100 %', () => {
  const r = resumenPlan('railway', { costo_estimado_mes: 1 }, [], '2026-11-24')
  assert.equal(r.plan, 'Hobby (US$5 al mes)')
  assert.equal(r.limiteTexto, 'US$5 de uso incluido al mes')
  assert.equal(r.usoTexto, 'US$ 1,00')
  assert.equal(r.porcentaje, 20)
  assert.equal(r.nivel, 'normal')
  assert.equal(resumenPlan('railway', { costo_estimado_mes: 3.995 }, [], null).nivel, 'normal') // 79,9 %
  assert.equal(resumenPlan('railway', { costo_estimado_mes: 4 }, [], null).nivel, 'atencion')   // 80 %
  assert.equal(resumenPlan('railway', { costo_estimado_mes: 4.5 }, [], null).nivel, 'atencion')
  assert.equal(resumenPlan('railway', { costo_estimado_mes: 5 }, [], null).nivel, 'critico')    // 100 %
  assert.equal(resumenPlan('railway', { costo_estimado_mes: 7.5 }, [], null).porcentaje, 150)
})

test('resumenPlan Railway sin dato: sin medida', () => {
  for (const datos of [null, {}, { costo_estimado_mes: 'x' }, { costo_estimado_mes: -1 }]) {
    const r = resumenPlan('railway', datos, [], null)
    assert.equal(r.porcentaje, null)
    assert.equal(r.nivel, 'sin_medida')
    assert.equal(r.usoTexto, 'Sin medida')
    assert.equal(r.plan, 'Hobby (US$5 al mes)')
  }
})

test('resumenPlan Brevo: 300 correos al día', () => {
  const r = resumenPlan('brevo', { enviados_hoy: 30, creditos_restantes: 270 }, [], null)
  assert.equal(r.plan, 'Gratuito')
  assert.equal(r.limiteTexto, '300 correos al día')
  assert.equal(r.porcentaje, 10)
  assert.equal(r.nivel, 'normal')
  assert.equal(resumenPlan('brevo', { enviados_hoy: 239 }, [], null).nivel, 'normal')   // 79,67 %
  assert.equal(resumenPlan('brevo', { enviados_hoy: 240 }, [], null).nivel, 'atencion') // 80 %
  assert.equal(resumenPlan('brevo', { enviados_hoy: 300 }, [], null).nivel, 'critico')
  assert.equal(resumenPlan('brevo', {}, [], null).nivel, 'sin_medida')
})

test('resumenPlan Supabase: tamaño sobre el límite de la BD y nota de pausa', () => {
  const MB = 1024 * 1024
  const r = resumenPlan('supabase', { tamano_bd_bytes: 50 * MB, limite_bd_bytes: 500 * MB }, [], null)
  assert.equal(r.plan, 'Free (gratuito)')
  assert.equal(r.limiteTexto, '500 MB')
  assert.equal(r.usoTexto, '50 MB')
  assert.equal(r.porcentaje, 10)
  assert.match(r.nota, /se pausa tras 1 semana sin actividad/i)
  assert.equal(resumenPlan('supabase', { tamano_bd_bytes: 399 * MB, limite_bd_bytes: 500 * MB }, [], null).nivel, 'normal')   // 79,8 %
  assert.equal(resumenPlan('supabase', { tamano_bd_bytes: 400 * MB, limite_bd_bytes: 500 * MB }, [], null).nivel, 'atencion')
  assert.equal(resumenPlan('supabase', { tamano_bd_bytes: 500 * MB, limite_bd_bytes: 500 * MB }, [], null).nivel, 'critico')
  // sin límite en los datos se usa la constante de referencia de 500 MB
  assert.equal(resumenPlan('supabase', { tamano_bd_bytes: 250 * MB }, [], null).porcentaje, 50)
  assert.equal(resumenPlan('supabase', {}, [], null).nivel, 'sin_medida')
})

test('resumenPlan Vercel: plan desde los datos, sin barra', () => {
  const g = resumenPlan('vercel', { plan: 'gratuito' }, [], null)
  assert.equal(g.plan, 'Hobby (gratuito)')
  assert.equal(g.limiteTexto, '100 GB de transferencia, 1 millón de solicitudes y 1 millón de invocaciones al mes')
  assert.equal(g.usoTexto, 'No medido por el Monitor')
  assert.equal(g.porcentaje, null)
  assert.equal(g.nivel, 'sin_medida')
  assert.equal(resumenPlan('vercel', { plan: 'pro' }, [], null).plan, 'Pro')
  assert.equal(resumenPlan('vercel', { plan: 'inventado' }, [], null).plan, 'No informado')
  assert.equal(resumenPlan('vercel', null, [], null).porcentaje, null)
})

test('resumenPlan Claude: plan de pago por uso, costo sin barra', () => {
  const r = resumenPlan('anthropic', { costo_mes: 1.5 }, [], null)
  assert.equal(r.plan, 'API de Anthropic · pago por uso (no es una suscripción Pro)')
  assert.equal(r.alcance, 'Solo el uso de Haiku que hace Finanzy: Asistente IA + WhatsApp. No incluye Claude Code, la consola ni otras claves')
  assert.equal(resumenPlan('brevo', {}, [], null).alcance, undefined)
  assert.equal(r.limiteTexto, 'Frecuencia: 4.000 solicitudes por minuto en el nivel inicial; tope de gasto mensual US$500')
  assert.equal(r.usoTexto, 'US$ 1,50 (costo del mes)')
  assert.equal(r.porcentaje, null)
  assert.equal(r.nivel, 'sin_medida')
  assert.equal(resumenPlan('anthropic', {}, [], null).usoTexto, 'Sin medida')
})

test('resumenPlan WhatsApp: solo el mes en curso de Colombia, con días de dos meses', () => {
  const dias = [diaWa('2026-10-30', 400), diaWa('2026-10-31', 400), diaWa('2026-11-01', 100), diaWa('2026-11-20', 50), diaWa('2026-11-24', 10)]
  const r = resumenPlan('meta', { conversaciones_periodo: 9999 }, dias, '2026-11-24')
  assert.equal(r.plan, 'Cuenta de prueba (gratis hasta 1.000 mensajes de servicio al mes)')
  assert.equal(r.limiteTexto, '1.000 mensajes de servicio al mes por número')
  assert.equal(r.etiquetaUso, 'Mensajes enviados este mes (contadores propios)')
  assert.equal(r.usoTexto, '160') // 100 + 50 + 10; no suma los recibidos ni octubre
  assert.equal(r.porcentaje, 16)
  assert.equal(r.nivel, 'normal')
  // el objeto { dias } de la respuesta también sirve
  assert.equal(resumenPlan('meta', null, { dias }, '2026-11-24').porcentaje, 16)
})

test('resumenPlan WhatsApp: niveles y cruce de mes a medianoche de Colombia', () => {
  assert.equal(resumenPlan('meta', null, [diaWa('2026-11-02', 799)], '2026-11-24').nivel, 'normal')
  assert.equal(resumenPlan('meta', null, [diaWa('2026-11-02', 800)], '2026-11-24').nivel, 'atencion')
  assert.equal(resumenPlan('meta', null, [diaWa('2026-11-02', 1000)], '2026-11-24').nivel, 'critico')
  // 2026-12-01T04:59Z todavía es 30 nov en Colombia; 05:00Z ya es 1 dic y el mes en curso se reinicia
  const dias = [diaWa('2026-11-30', 900), diaWa('2026-12-01', 5)]
  const antes = resumenPlan('meta', null, dias, diaDeInstante('2026-12-01T04:59:00Z'))
  assert.equal(antes.usoTexto, '900')
  assert.equal(antes.nivel, 'atencion')
  const despues = resumenPlan('meta', null, dias, diaDeInstante('2026-12-01T05:00:00Z'))
  assert.equal(despues.usoTexto, '5')
  assert.equal(despues.porcentaje, 0.5)
  assert.equal(despues.nivel, 'normal')
})

test('resumenPlan WhatsApp: sin días en el mes es 0 %; sin «hoy» válido, sin medida', () => {
  const vacio = resumenPlan('meta', null, [], '2026-11-24')
  assert.equal(vacio.usoTexto, '0')
  assert.equal(vacio.porcentaje, 0)
  assert.equal(vacio.nivel, 'normal')
  for (const hoy of [null, undefined, '', 'ayer']) {
    const r = resumenPlan('meta', null, [diaWa('2026-11-02', 5)], hoy)
    assert.equal(r.porcentaje, null)
    assert.equal(r.nivel, 'sin_medida')
  }
  assert.equal(resumenPlan('meta', null, undefined, '2026-11-24').porcentaje, 0)
})

test('los límites de referencia están declarados', () => {
  assert.equal(LIMITES_PLAN.brevo.limiteCorreosDia, 300)
  assert.equal(LIMITES_PLAN.supabase.limiteBytes, 500 * 1024 * 1024)
  assert.equal(LIMITES_PLAN.meta.limiteMensajes, 1000)
  assert.equal(LIMITES_PLAN.railway.limiteUsd, 5)
})
