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
  // Sin clave de administración el backend estima el mes con los contadores propios (Asistente IA + WhatsApp) y envía
  // `llamadas_mes`; con ella, los datos son oficiales y se usan las etiquetas «oficiales».
  anthropic: [
    { clave: 'llamadas_mes', etiqueta: 'Llamadas (total)', tipo: 'numero' },
    { clave: 'llamadas_asistente_mes', etiqueta: 'Asistente IA (llamadas del mes)', tipo: 'numero' },
    { clave: 'llamadas_whatsapp_mes', etiqueta: 'WhatsApp (llamadas del mes)', tipo: 'numero' },
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
export const NOTA_ESTIMADO_CONTADORES = 'Estimado a partir de los contadores propios'

export function notaPlataforma(nombre: NombrePlataforma, datos: Plataforma['datos']): string | null {
  return nombre === 'anthropic' && esObjeto(datos) && 'llamadas_mes' in datos ? NOTA_ESTIMADO_CONTADORES : null
}

/** Estado efectivo: «ok» solo si el backend lo dice y queda al menos un campo mostrable. */
export function estadoPlataforma(nombre: NombrePlataforma, p: Plataforma | null | undefined): EstadoPlataforma {
  if (!p || p.estado !== 'ok') return 'no_disponible'
  return camposVisibles(nombre, p.datos).length > 0 ? 'ok' : 'no_disponible'
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

// ---------------------------------------------------------------------------------------------------------------
// Plan, límite y uso de cada plataforma (CHG-017, REQ-F-018 CA-6)
// ---------------------------------------------------------------------------------------------------------------

/**
 * Límites de referencia al 24 nov 2026 según la documentación de cada proveedor; si cambian los planes, actualizar aquí.
 * Son constantes del frontend: el backend no los envía y el Monitor no los verifica contra la plataforma.
 */
export const LIMITES_PLAN = {
  railway: { plan: 'Hobby (US$5 al mes)', limiteTexto: 'US$5 de uso incluido al mes', limiteUsd: 5 },
  vercel: {
    planes: { gratuito: 'Hobby (gratuito)', pro: 'Pro' } as Record<string, string>,
    limiteTexto: '100 GB de transferencia, 1 millón de solicitudes y 1 millón de invocaciones al mes',
    limiteOtroPlan: 'Según el plan contratado (ver el panel de Vercel)',
  },
  supabase: {
    plan: 'Free (gratuito)', limiteBytes: 500 * 1024 * 1024,
    nota: 'El proyecto se pausa tras 1 semana sin actividad',
  },
  brevo: { plan: 'Gratuito', limiteTexto: '300 correos al día', limiteCorreosDia: 300 },
  meta: {
    plan: 'Cuenta de prueba (gratis hasta 1.000 mensajes de servicio al mes)',
    limiteTexto: '1.000 mensajes de servicio al mes por número', limiteMensajes: 1000,
  },
  anthropic: {
    plan: 'API de Anthropic · pago por uso (no es una suscripción Pro)',
    limiteTexto: 'Frecuencia: 4.000 solicitudes por minuto en el nivel inicial; tope de gasto mensual US$500',
    alcance: 'Solo el uso de Haiku que hace Finanzy: Asistente IA + WhatsApp. No incluye Claude Code, la consola ni otras claves',
  },
} as const

export const TEXTO_ATENCION = 'Atención: cerca del límite'
export const TEXTO_CRITICO = 'Límite superado'
export const TEXTO_SIN_MEDIDA = 'Sin medida'
export const UMBRAL_ATENCION = 80
export const UMBRAL_CRITICO = 100

export type NivelUso = 'normal' | 'atencion' | 'critico' | 'sin_medida'

export interface ResumenPlan {
  plan: string
  limiteTexto: string
  usoTexto: string
  /** Porcentaje del límite usado, sin redondear ni topar (puede pasar de 100); `null` si no se puede medir. */
  porcentaje: number | null
  nivel: NivelUso
  /** Etiqueta de la fila de uso («Uso actual» salvo en WhatsApp). */
  etiquetaUso: string
  /** Nota extra de la tarjeta (p. ej. la pausa de Supabase); `null` si no hay. */
  nota: string | null
  /** Línea de alcance bien visible de la tarjeta (solo Claude); ausente si no aplica. */
  alcance?: string
}

/** Texto de un porcentaje: un decimal si es < 10 % («5,3 %»), entero si no; se trunca para no aparentar 80 % antes de tiempo. */
export function formatPorcentaje(p: number): string {
  if (!Number.isFinite(p) || p < 0) return '—'
  if (p < 10) return `${(Math.floor(p * 10 + 1e-9) / 10).toFixed(1).replace('.', ',').replace(/,0$/, '')} %`
  return `${formatNumero(Math.floor(p + 1e-9))} %`
}

/** Nivel según el porcentaje: atención desde 80 %, crítico desde 100 %. */
export function nivelDePorcentaje(p: number | null): NivelUso {
  if (p === null) return 'sin_medida'
  if (p >= UMBRAL_CRITICO) return 'critico'
  if (p >= UMBRAL_ATENCION) return 'atencion'
  return 'normal'
}

/** Texto del nivel (además del color): vacío si es normal o no hay medida. */
export function textoNivel(n: NivelUso): string {
  return n === 'critico' ? TEXTO_CRITICO : n === 'atencion' ? TEXTO_ATENCION : ''
}

/** Mes de Colombia (`YYYY-MM`) de un día `YYYY-MM-DD`; `null` si no es válido. */
const mesDe = (dia: unknown): string | null => (typeof dia === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(dia) ? dia.slice(0, 7) : null)

/** Mensajes de WhatsApp enviados en el mes en curso de Colombia (días de los contadores propios hasta `hoy`). */
function enviadosWhatsappMes(dias: DiaContador[], hoy: string): number {
  const mes = mesDe(hoy)
  if (!mes) return 0
  return total(dias.filter(d => mesDe(d.fecha) === mes && d.fecha <= hoy).map(d => d.whatsapp_mensajes.enviados))
}

/** Arma el resumen cuando hay un valor usado y un límite numérico. */
function conBarra(base: Omit<ResumenPlan, 'usoTexto' | 'porcentaje' | 'nivel'>, usoTexto: string, usado: number, limite: number): ResumenPlan {
  const porcentaje = (usado * 100) / limite
  return { ...base, usoTexto, porcentaje, nivel: nivelDePorcentaje(porcentaje) }
}

/**
 * Plan, límite, uso y porcentaje de una plataforma. Función pura: el uso sale de lo que ya devuelve `/monitor/resumen`
 * (`datos`, `contadores`) y los límites de `LIMITES_PLAN`. `hoyColombia` es el día de Colombia (`YYYY-MM-DD`, ver
 * `diaDeInstante`); solo se usa para el mes en curso de WhatsApp. `contadores` admite la lista de días o el objeto
 * `{ dias }` de la respuesta.
 */
export function resumenPlan(
  plataforma: NombrePlataforma,
  datos: Plataforma['datos'] | undefined,
  contadores: DiaContador[] | { dias: DiaContador[] } | null | undefined,
  hoyColombia: string | null | undefined,
): ResumenPlan {
  const d: Record<string, unknown> = esObjeto(datos) ? datos : {}
  const dias = Array.isArray(contadores) ? contadores : Array.isArray(contadores?.dias) ? contadores.dias : []
  const sinMedida = (base: Omit<ResumenPlan, 'usoTexto' | 'porcentaje' | 'nivel'>, usoTexto = TEXTO_SIN_MEDIDA): ResumenPlan =>
    ({ ...base, usoTexto, porcentaje: null, nivel: 'sin_medida' })

  switch (plataforma) {
    case 'railway': {
      const L = LIMITES_PLAN.railway
      const base = { plan: L.plan, limiteTexto: L.limiteTexto, etiquetaUso: 'Uso actual', nota: null }
      const costo = d.costo_estimado_mes
      return esNumero(costo) ? conBarra(base, formatUsd(costo), costo, L.limiteUsd) : sinMedida(base)
    }
    case 'vercel': {
      const L = LIMITES_PLAN.vercel
      const plan = typeof d.plan === 'string' ? L.planes[d.plan] : undefined
      const base = {
        plan: plan ?? 'No informado',
        limiteTexto: d.plan === 'gratuito' ? L.limiteTexto : L.limiteOtroPlan,
        etiquetaUso: 'Uso actual', nota: null,
      }
      return sinMedida(base, 'No medido por el Monitor')
    }
    case 'supabase': {
      const L = LIMITES_PLAN.supabase
      const limite = esNumero(d.limite_bd_bytes) && d.limite_bd_bytes > 0 ? d.limite_bd_bytes : L.limiteBytes
      const base = { plan: L.plan, limiteTexto: formatBytes(limite), etiquetaUso: 'Uso actual', nota: L.nota }
      const usado = d.tamano_bd_bytes
      return esNumero(usado) ? conBarra(base, formatBytes(usado), usado, limite) : sinMedida(base)
    }
    case 'brevo': {
      const L = LIMITES_PLAN.brevo
      const base = { plan: L.plan, limiteTexto: L.limiteTexto, etiquetaUso: 'Uso actual', nota: null }
      const usado = d.enviados_hoy
      return esNumero(usado) ? conBarra(base, `${formatNumero(usado)} correos hoy`, usado, L.limiteCorreosDia) : sinMedida(base)
    }
    case 'meta': {
      const L = LIMITES_PLAN.meta
      const base = { plan: L.plan, limiteTexto: L.limiteTexto, etiquetaUso: 'Mensajes enviados este mes (contadores propios)', nota: null }
      if (!hoyColombia || mesDe(hoyColombia) === null) return sinMedida(base)
      const enviados = enviadosWhatsappMes(dias, hoyColombia)
      return conBarra(base, formatNumero(enviados), enviados, L.limiteMensajes)
    }
    case 'anthropic': {
      const L = LIMITES_PLAN.anthropic
      const base = { plan: L.plan, limiteTexto: L.limiteTexto, etiquetaUso: 'Uso actual', nota: null, alcance: L.alcance }
      return esNumero(d.costo_mes) ? sinMedida(base, `${formatUsd(d.costo_mes)} (costo del mes)`) : sinMedida(base)
    }
  }
}
