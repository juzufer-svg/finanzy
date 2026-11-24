/**
 * Monitor de consumos del Dueño (CHG-017, UC-014, CT-010): tipos y utilidades puras.
 * Sin dependencias de React ni del navegador, para poder probarlas con `npm test`.
 *
 * Los montos de dinero de las plataformas vienen en USD y se muestran como tales: no pasan por el
 * conversor de moneda de la app. Los textos se arman a mano (sin Intl) para verse igual en todos los navegadores.
 */

export const TEXTO_NO_DISPONIBLE = 'No disponible'

export type NombrePlataforma = 'railway' | 'anthropic' | 'meta' | 'supabase' | 'vercel' | 'brevo'
export type EstadoPlataforma = 'ok' | 'no_disponible'
export type ValorDato = string | number

export interface Plataforma {
  estado: EstadoPlataforma
  datos: Record<string, ValorDato> | null
  actualizado_en: string | null
}

export interface ConteoClaude { llamadas: number; tokens_entrada: number; tokens_salida: number }

export interface DiaContador {
  fecha: string
  claude: { asistente: ConteoClaude; whatsapp: ConteoClaude }
  brevo_correos_enviados: number
  whatsapp_mensajes: { enviados: number; recibidos: number }
}

export interface ResumenMonitor {
  generado_en: string
  contadores: { desde: string | null; dias: DiaContador[] }
  plataformas: Record<NombrePlataforma, Plataforma>
}

type TipoCampo = 'usd' | 'numero' | 'bytes' | 'fecha' | 'plan' | 'moneda'
interface CampoDef {
  clave: string
  etiqueta: string
  tipo: TipoCampo
  /** Etiqueta cuando el dato es oficial (la plataforma lo entrega), no estimado con los contadores propios. */
  etiquetaOficial?: string
}

/** Orden y nombre visible de las seis plataformas. */
export const PLATAFORMAS: { clave: NombrePlataforma; nombre: string }[] = [
  { clave: 'railway', nombre: 'Railway' },
  { clave: 'anthropic', nombre: 'Claude (Anthropic)' },
  { clave: 'meta', nombre: 'Meta / WhatsApp' },
  { clave: 'supabase', nombre: 'Supabase' },
  { clave: 'vercel', nombre: 'Vercel' },
  { clave: 'brevo', nombre: 'Brevo' },
]

/** Lista blanca de campos por plataforma (CT-010): lo que no esté aquí no se muestra. */
const CAMPOS: Record<NombrePlataforma, CampoDef[]> = {
  railway: [
    { clave: 'costo_estimado_mes', etiqueta: 'Gasto del período (US$)', tipo: 'usd' },
    { clave: 'creditos_saldo', etiqueta: 'Créditos prepagados (US$)', tipo: 'usd' },
    { clave: 'uso_cpu_vcpu_horas', etiqueta: 'CPU (vCPU-horas)', tipo: 'numero' },
    { clave: 'uso_memoria_gb_horas', etiqueta: 'Memoria (GB-horas)', tipo: 'numero' },
    { clave: 'periodo_hasta', etiqueta: 'Período hasta', tipo: 'fecha' },
  ],
  // Sin clave de administración el backend estima el mes con los contadores propios (solo el chat) y envía
  // `llamadas_mes`; con ella, los datos son oficiales y se usan las etiquetas «oficiales».
  anthropic: [
    { clave: 'llamadas_mes', etiqueta: 'Llamadas del chat (mes)', tipo: 'numero' },
    { clave: 'tokens_entrada_mes', etiqueta: 'Tokens de entrada (mes)', tipo: 'numero', etiquetaOficial: 'Tokens de entrada del mes' },
    { clave: 'tokens_salida_mes', etiqueta: 'Tokens de salida (mes)', tipo: 'numero', etiquetaOficial: 'Tokens de salida del mes' },
    { clave: 'costo_mes', etiqueta: 'Costo estimado del mes (US$)', tipo: 'usd', etiquetaOficial: 'Costo del mes' },
  ],
  meta: [
    { clave: 'conversaciones_periodo', etiqueta: 'Mensajes facturables del mes', tipo: 'numero' },
    { clave: 'periodo_desde', etiqueta: 'Período desde', tipo: 'fecha' },
    { clave: 'periodo_hasta', etiqueta: 'Período hasta', tipo: 'fecha' },
  ],
  supabase: [
    { clave: 'tamano_bd_bytes', etiqueta: 'Tamaño de la BD', tipo: 'bytes' },
    { clave: 'limite_bd_bytes', etiqueta: 'Límite del plan', tipo: 'bytes' },
  ],
  vercel: [
    { clave: 'plan', etiqueta: 'Plan', tipo: 'plan' },
    { clave: 'ancho_banda_bytes', etiqueta: 'Ancho de banda usado', tipo: 'bytes' },
    { clave: 'limite_ancho_banda_bytes', etiqueta: 'Límite de ancho de banda', tipo: 'bytes' },
  ],
  brevo: [
    { clave: 'creditos_restantes', etiqueta: 'Créditos restantes', tipo: 'numero' },
    { clave: 'enviados_hoy', etiqueta: 'Enviados hoy', tipo: 'numero' },
  ],
}

const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
const PLANES: Record<string, string> = { gratuito: 'Gratuito', pro: 'Pro', otro: 'Otro' }

const esNumero = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v) && v >= 0
const esObjeto = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)

/** Agrupa miles con punto: 1234567 → «1.234.567». */
function agrupar(entero: string): string {
  return entero.replace(/\B(?=(\d{3})+(?!\d))/g, '.')
}

/** Cantidad entera con separador de miles («1.234»). Valores no válidos → «—». */
export function formatNumero(n: unknown): string {
  if (!esNumero(n)) return '—'
  const redondeado = Math.round(n)
  if (Number.isInteger(n) || Math.abs(n - redondeado) < 0.005) return agrupar(String(redondeado))
  const [ent, dec] = n.toFixed(2).split('.')
  return `${agrupar(ent)},${dec.replace(/0$/, '')}`
}

/** Monto en dólares tal como lo entrega la plataforma, sin conversión de moneda: «US$ 12,50». */
export function formatUsd(n: unknown): string {
  if (!esNumero(n)) return '—'
  const [ent, dec] = n.toFixed(2).split('.')
  return `US$ ${agrupar(ent)},${dec}`
}

/** Bytes legibles (base 1024): 1536 → «1,5 KB». */
export function formatBytes(n: unknown): string {
  if (!esNumero(n)) return '—'
  const unidades = ['B', 'KB', 'MB', 'GB', 'TB']
  let valor = n
  let i = 0
  while (valor >= 1024 && i < unidades.length - 1) { valor /= 1024; i++ }
  if (i === 0) return `${Math.round(valor)} B`
  const texto = valor.toFixed(valor >= 100 ? 0 : 1).replace(/\.0$/, '').replace('.', ',')
  return `${texto} ${unidades[i]}`
}

/** «2026-11-24» → «24 nov 2026». Si no tiene el formato esperado, devuelve «—». */
export function formatFechaDia(fecha: unknown): string {
  const m = typeof fecha === 'string' ? /^(\d{4})-(\d{2})-(\d{2})/.exec(fecha) : null
  const mes = m ? MESES[Number(m[2]) - 1] : undefined
  if (!m || !mes) return '—'
  return `${Number(m[3])} ${mes} ${m[1]}`
}

/** Colombia está en UTC−5 todo el año (sin horario de verano): se resta a mano, sin depender de la zona del navegador. */
const DESFASE_COLOMBIA_MS = -5 * 60 * 60 * 1000

/** Instante UTC ISO-8601 → hora de Colombia: «24 nov 2026, 10:00 a. m.». Si no es válido, devuelve «—». */
export function formatInstante(iso: unknown): string {
  const m = typeof iso === 'string' ? /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso) : null
  if (!m) return '—'
  if (formatFechaDia(`${m[1]}-${m[2]}-${m[3]}`) === '—') return '—'
  const t = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4]), Number(m[5])) + DESFASE_COLOMBIA_MS)
  const dia = formatFechaDia(`${t.getUTCFullYear()}-${String(t.getUTCMonth() + 1).padStart(2, '0')}-${String(t.getUTCDate()).padStart(2, '0')}`)
  const h = t.getUTCHours()
  const hora12 = h % 12 === 0 ? 12 : h % 12
  return `${dia}, ${hora12}:${String(t.getUTCMinutes()).padStart(2, '0')} ${h < 12 ? 'a. m.' : 'p. m.'}`
}

function formatCampo(def: CampoDef, valor: ValorDato): string | null {
  switch (def.tipo) {
    case 'usd': return esNumero(valor) ? formatUsd(valor) : null
    case 'numero': return esNumero(valor) ? formatNumero(valor) : null
    case 'bytes': return esNumero(valor) ? formatBytes(valor) : null
    case 'fecha': { const t = formatFechaDia(valor); return t === '—' ? null : t }
    case 'plan': return typeof valor === 'string' && PLANES[valor] ? PLANES[valor] : null
    default: return null
  }
}

export interface CampoVisible { clave: string; etiqueta: string; valor: string }

/** Campos de una plataforma listos para mostrar: solo los de la lista blanca y con valor válido. */
export function camposVisibles(nombre: NombrePlataforma, datos: Plataforma['datos']): CampoVisible[] {
  if (!datos || !esObjeto(datos)) return []
  const salida: CampoVisible[] = []
  for (const def of CAMPOS[nombre] ?? []) {
    if (!(def.clave in datos)) continue
    const valor = formatCampo(def, datos[def.clave])
    if (valor === null) continue
    const oficial = nombre === 'anthropic' && !('llamadas_mes' in datos) && def.etiquetaOficial
    salida.push({ clave: def.clave, etiqueta: oficial || def.etiqueta, valor })
  }
  return salida
}

/** Nota de la tarjeta cuando los datos son una estimación con los contadores propios (no oficiales). */
export const NOTA_ESTIMADO_CONTADORES = 'Estimado a partir de los contadores propios (solo el chat; WhatsApp aparte)'

export function notaPlataforma(nombre: NombrePlataforma, datos: Plataforma['datos']): string | null {
  return nombre === 'anthropic' && esObjeto(datos) && 'llamadas_mes' in datos ? NOTA_ESTIMADO_CONTADORES : null
}

/** Estado efectivo: «ok» solo si el backend lo dice y queda al menos un campo mostrable. */
export function estadoPlataforma(nombre: NombrePlataforma, p: Plataforma | null | undefined): EstadoPlataforma {
  if (!p || p.estado !== 'ok') return 'no_disponible'
  return camposVisibles(nombre, p.datos).length > 0 ? 'ok' : 'no_disponible'
}

/** Porcentaje (0-100, entero) de `usado` sobre `limite`; `null` si no se puede calcular. */
export function porcentajeUso(usado: unknown, limite: unknown): number | null {
  if (!esNumero(usado) || !esNumero(limite) || limite <= 0) return null
  return Math.min(100, Math.round((usado / limite) * 100))
}

const CERO_CLAUDE: ConteoClaude = { llamadas: 0, tokens_entrada: 0, tokens_salida: 0 }

function conteoClaude(v: unknown): ConteoClaude {
  const o = esObjeto(v) ? v : {}
  const n = (x: unknown) => (esNumero(x) ? x : 0)
  return { llamadas: n(o.llamadas), tokens_entrada: n(o.tokens_entrada), tokens_salida: n(o.tokens_salida) }
}

/** Valida y normaliza la respuesta de `GET /monitor/resumen`; `null` si no tiene la forma esperada. */
export function normalizarResumen(raw: unknown): ResumenMonitor | null {
  if (!esObjeto(raw) || !esObjeto(raw.contadores) || !esObjeto(raw.plataformas)) return null
  const n = (x: unknown) => (esNumero(x) ? x : 0)
  const diasRaw = Array.isArray(raw.contadores.dias) ? raw.contadores.dias : []
  const dias: DiaContador[] = []
  for (const d of diasRaw) {
    if (!esObjeto(d) || typeof d.fecha !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(d.fecha)) continue
    const claude = esObjeto(d.claude) ? d.claude : {}
    const wa = esObjeto(d.whatsapp_mensajes) ? d.whatsapp_mensajes : {}
    dias.push({
      fecha: d.fecha,
      claude: { asistente: conteoClaude(claude.asistente), whatsapp: conteoClaude(claude.whatsapp) },
      brevo_correos_enviados: n(d.brevo_correos_enviados),
      whatsapp_mensajes: { enviados: n(wa.enviados), recibidos: n(wa.recibidos) },
    })
  }
  const plataformas = {} as Record<NombrePlataforma, Plataforma>
  for (const { clave } of PLATAFORMAS) {
    const p = (raw.plataformas as Record<string, unknown>)[clave]
    if (esObjeto(p) && p.estado === 'ok' && esObjeto(p.datos)) {
      const datos: Record<string, ValorDato> = {}
      for (const [k, v] of Object.entries(p.datos)) if (typeof v === 'string' || typeof v === 'number') datos[k] = v
      plataformas[clave] = { estado: 'ok', datos, actualizado_en: typeof p.actualizado_en === 'string' ? p.actualizado_en : null }
    } else {
      plataformas[clave] = { estado: 'no_disponible', datos: null, actualizado_en: null }
    }
  }
  const desde = raw.contadores.desde
  return {
    generado_en: typeof raw.generado_en === 'string' ? raw.generado_en : '',
    contadores: { desde: typeof desde === 'string' ? desde : null, dias },
    plataformas,
  }
}

/** Un punto de la serie diaria (todos los días de la ventana, con ceros donde no hubo datos). */
export interface PuntoDia {
  fecha: string
  claude_llamadas_asistente: number
  claude_llamadas_whatsapp: number
  claude_tokens_asistente: number
  claude_tokens_whatsapp: number
  correos: number
  wa_enviados: number
  wa_recibidos: number
}

/** Suma `n` días a una fecha `YYYY-MM-DD` (calendario UTC, sin depender de la zona horaria). */
export function sumarDias(fecha: string, n: number): string {
  const [a, m, d] = fecha.split('-').map(Number)
  const t = new Date(Date.UTC(a, m - 1, d + n))
  return `${t.getUTCFullYear()}-${String(t.getUTCMonth() + 1).padStart(2, '0')}-${String(t.getUTCDate()).padStart(2, '0')}`
}

/**
 * Serie continua de `n` días terminando en `hasta` (`YYYY-MM-DD`, hoy de Colombia). El backend solo envía los días con
 * datos; aquí se rellenan con ceros para que el gráfico muestre la ventana completa.
 */
export function serieDias(dias: DiaContador[], hasta: string, n = 30): PuntoDia[] {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(hasta)) return []
  const porFecha = new Map(dias.map(d => [d.fecha, d]))
  const serie: PuntoDia[] = []
  for (let i = n - 1; i >= 0; i--) {
    const fecha = sumarDias(hasta, -i)
    const d = porFecha.get(fecha)
    const a = d?.claude.asistente ?? CERO_CLAUDE
    const w = d?.claude.whatsapp ?? CERO_CLAUDE
    serie.push({
      fecha,
      claude_llamadas_asistente: a.llamadas,
      claude_llamadas_whatsapp: w.llamadas,
      claude_tokens_asistente: a.tokens_entrada + a.tokens_salida,
      claude_tokens_whatsapp: w.tokens_entrada + w.tokens_salida,
      correos: d?.brevo_correos_enviados ?? 0,
      wa_enviados: d?.whatsapp_mensajes.enviados ?? 0,
      wa_recibidos: d?.whatsapp_mensajes.recibidos ?? 0,
    })
  }
  return serie
}

/**
 * Día de Colombia (`YYYY-MM-DD`, UTC−5) de un instante UTC ISO-8601 con «Z»; si no es válido, `null`. Los días de
 * los contadores son días de Colombia: ni el día UTC ni el del navegador. Es el «hoy» con que termina la serie.
 */
export function diaDeInstante(iso: unknown): string | null {
  const m = typeof iso === 'string' ? /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso) : null
  if (!m) return null
  const t = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4]), Number(m[5])) + DESFASE_COLOMBIA_MS)
  if (Number.isNaN(t.getTime())) return null
  return `${t.getUTCFullYear()}-${String(t.getUTCMonth() + 1).padStart(2, '0')}-${String(t.getUTCDate()).padStart(2, '0')}`
}

/** Suma de una serie de valores. */
export const total = (valores: number[]): number => valores.reduce((a, b) => a + b, 0)

/** Alturas (0-100) de las barras apiladas de un día respecto al máximo de la serie. */
export function alturasApiladas(partes: number[], maximo: number): number[] {
  if (!(maximo > 0)) return partes.map(() => 0)
  return partes.map(p => (p > 0 ? Math.max(1, (p / maximo) * 100) : 0))
}
