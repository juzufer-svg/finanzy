/**
 * Recorrido de punta a punta de la exportación a CSV/Excel (CHG-018, UC-015, CT-011). Manual.
 *
 * Requisitos: el frontend corriendo (next start) apuntando a un backend con una cuenta activa que
 * tenga transacciones en el mes actual, y Playwright disponible (no es dependencia del proyecto:
 * `npx -y playwright@1 install chromium` o el Chromium que ya tenga el equipo).
 *
 *   E2E_BASE_URL=http://localhost:3000 E2E_EMAIL=... E2E_PASSWORD=... node e2e/exportar.mjs
 *   (opcional) E2E_SHOTS=/ruta/carpeta para guardar capturas (modo claro/oscuro, PC y celular)
 *
 * Comprueba: descarga real de un CSV y de un .xlsx por el proxy (nombre del archivo desde
 * Content-Disposition, contenido que coincide con la API), rango > 12 meses bloqueado en la
 * interfaz y rechazado por el servidor (422), un error 422 del servidor visible en pantalla,
 * la nota del .xlsx junto al botón y que la cookie de sesión nunca llega al JavaScript.
 * Nunca usar una cuenta real ni datos de producción.
 */
import { chromium, devices } from 'playwright'
import { readFileSync, mkdirSync } from 'node:fs'

const BASE = process.env.E2E_BASE_URL || 'http://localhost:3000'
const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD
const SHOTS = process.env.E2E_SHOTS || ''
if (!EMAIL || !PASSWORD) {
  console.error('Faltan E2E_EMAIL y E2E_PASSWORD')
  process.exit(2)
}
if (SHOTS) mkdirSync(SHOTS, { recursive: true })

let fallos = 0
const comprobar = (ok, texto) => { console.log(`${ok ? '✔' : '✘'} ${texto}`); if (!ok) fallos++ }
const captura = async (page, nombre) => { if (SHOTS) await page.screenshot({ path: `${SHOTS}/${nombre}.png` }) }

const browser = await chromium.launch()
const errores = []

async function iniciarSesion(contexto) {
  const page = await contexto.newPage()
  page.on('pageerror', e => errores.push(e.message))
  await page.goto(`${BASE}/auth/login`)
  await page.fill('input[type=email]', EMAIL)
  await page.fill('input[type=password]', PASSWORD)
  await Promise.all([page.waitForURL('**/dashboard', { timeout: 15000 }), page.click('button[type=submit]')])
  return page
}

const ctx = await browser.newContext({ acceptDownloads: true, viewport: { width: 1280, height: 900 } })
const page = await iniciarSesion(ctx)
await page.goto(`${BASE}/dashboard/transactions`, { waitUntil: 'networkidle' })
const mes = await page.evaluate(() => sessionStorage.getItem('finanzy_periodo')) ||
  new Date().toISOString().slice(0, 7)
const enApi = await page.evaluate(async m => (await fetch(`/api/v1/transacciones?mes=${m}`)).json(), mes)
comprobar(Array.isArray(enApi) && enApi.length > 0, `la cuenta tiene transacciones en ${mes} (${enApi.length})`)

// --- Panel: valores iniciales y notas ---
await page.getByRole('button', { name: 'Descargar', exact: true }).click()
const form = page.getByRole('form', { name: 'Descargar transacciones' })
await form.waitFor()
comprobar(await form.getByLabel('Desde (mes)').inputValue() === mes, '«Desde» arranca en el período que se está viendo')
comprobar(await form.getByLabel('Hasta (mes)').inputValue() === mes, '«Hasta» arranca en el período que se está viendo')
const texto = await form.innerText()
comprobar(texto.includes('Si tu Excel está en inglés y el CSV se ve en una sola columna, descarga el .xlsx.'), 'junto al botón se lee la nota del .xlsx (CSV elegido)')
comprobar(/pesos colombianos \(COP\)/.test(texto), 'se aclara que el archivo va siempre en COP')
await captura(page, 'exportar-pc-claro')

// --- CSV real por el proxy ---
const [dlCsv] = await Promise.all([
  page.waitForEvent('download'),
  form.getByRole('button', { name: 'Descargar CSV' }).click(),
])
comprobar(dlCsv.suggestedFilename() === `finanzy-transacciones-${mes}.csv`, `el CSV se llama ${dlCsv.suggestedFilename()}`)
const rutaCsv = await dlCsv.path()
const bytesCsv = readFileSync(rutaCsv)
comprobar(bytesCsv.subarray(0, 3).equals(Buffer.from([0xef, 0xbb, 0xbf])), 'el CSV empieza con BOM UTF-8')
const lineas = bytesCsv.toString('utf8').replace(/^﻿/, '').split('\r\n').filter(Boolean)
comprobar(lineas[0] === 'Fecha;Tipo;Categoría;Descripción;Medio de pago;Monto (COP);Origen', 'el CSV trae los 7 encabezados de CT-011')
comprobar(lineas.length - 1 === enApi.length, `el CSV tiene ${lineas.length - 1} filas y la API ${enApi.length}`)
const sumaCsv = lineas.slice(1).reduce((s, l) => { const c = l.split(';'); return s + Number(c[5].replace(',', '.')) * (c[1] === 'Gasto' ? -1 : 1) }, 0)
const sumaApi = enApi.reduce((s, t) => s + (t.tipo === 'gasto' ? -t.monto : t.monto), 0)
comprobar(Math.abs(sumaCsv - sumaApi) < 0.01, `el balance del CSV (${sumaCsv}) coincide con el de la API (${sumaApi})`)
await page.getByText(/Descarga lista/).first().waitFor()
comprobar(true, 'se avisa «Descarga lista» al terminar')

// --- xlsx real por el proxy ---
await form.getByText('Excel (.xlsx)').click()
const [dlXlsx] = await Promise.all([
  page.waitForEvent('download'),
  form.getByRole('button', { name: 'Descargar Excel' }).click(),
])
comprobar(dlXlsx.suggestedFilename() === `finanzy-transacciones-${mes}.xlsx`, `el Excel se llama ${dlXlsx.suggestedFilename()}`)
const bytesXlsx = readFileSync(await dlXlsx.path())
comprobar(bytesXlsx.subarray(0, 2).toString() === 'PK', 'el .xlsx es un zip válido (PK)')
comprobar(bytesXlsx.includes('xl/worksheets/sheet1.xml'), 'el .xlsx trae la hoja de cálculo')

// --- Rango > 12 meses: la interfaz lo bloquea ---
const [a, m] = mes.split('-').map(Number)
const hace13 = new Date(a, m - 1 - 12, 1)
const inicio13 = `${hace13.getFullYear()}-${String(hace13.getMonth() + 1).padStart(2, '0')}`
await form.getByLabel('Desde (mes)').fill(inicio13)
const alerta = form.getByRole('alert')
await alerta.waitFor()
comprobar(/hasta 12 meses/.test(await alerta.innerText()), `un rango de 13 meses (${inicio13} a ${mes}) muestra «${(await alerta.innerText()).trim()}»`)
comprobar(await form.getByRole('button', { name: /^Descargar/ }).isDisabled(), 'con un rango inválido el botón de descarga queda desactivado')
await captura(page, 'exportar-pc-rango-invalido')

// --- Y el servidor también lo rechaza (422), con las cabeceras de seguridad ---
const respuesta = await page.evaluate(async ([d, h]) => {
  const r = await fetch(`/api/v1/exportaciones/transacciones?desde=${d}&hasta=${h}&formato=csv`)
  return { status: r.status, cache: r.headers.get('cache-control'), cuerpo: await r.json() }
}, [inicio13, mes])
comprobar(respuesta.status === 422 && /12 meses/.test(respuesta.cuerpo.detail), `el servidor responde 422: «${respuesta.cuerpo.detail}»`)
comprobar(respuesta.cache === 'no-store', 'la respuesta del proxy lleva Cache-Control: no-store')
const ok = await page.evaluate(async m => {
  const r = await fetch(`/api/v1/exportaciones/transacciones?desde=${m}&formato=xlsx`)
  return { tipo: r.headers.get('content-type'), disp: r.headers.get('content-disposition'), nosniff: r.headers.get('x-content-type-options') }
}, mes)
comprobar(/attachment; filename="finanzy-transacciones-.*\.xlsx"/.test(ok.disp || ''), `el proxy reenvía Content-Disposition (${ok.disp})`)
comprobar(/spreadsheetml/.test(ok.tipo || ''), 'el proxy conserva el Content-Type del xlsx')
const otra = await page.evaluate(async () => (await fetch('/api/v1/categorias')).headers.get('content-disposition'))
comprobar(otra === null, 'en otras rutas el proxy no reenvía Content-Disposition')

// --- Un 422 del servidor (demasiado grande) se ve en pantalla, leído desde el Blob ---
await form.getByLabel('Desde (mes)').fill(mes)
await page.route('**/api/v1/exportaciones/transacciones*', route => route.fulfill({
  status: 422, contentType: 'application/json',
  body: JSON.stringify({ detail: 'El archivo superaría los 4 MB. Elige menos meses.', codigo: 'exportacion_demasiado_grande' }),
}))
await form.getByRole('button', { name: /^Descargar/ }).click()
const aviso = page.getByRole('alert').filter({ hasText: 'El archivo superaría los 4 MB. Elige menos meses.' }).first()
await aviso.waitFor({ timeout: 5000 })
comprobar(true, 'un 422 «exportacion_demasiado_grande» se ve en pantalla con su mensaje (no «[object Blob]»)')
await captura(page, 'exportar-pc-error-422')
await page.route('**/api/v1/exportaciones/transacciones*', route => route.fulfill({
  status: 429, contentType: 'application/json', body: JSON.stringify({ detail: 'Demasiadas descargas. Espera un momento e intenta de nuevo.' }),
}))
await form.getByRole('button', { name: /^Descargar/ }).click()
await page.getByRole('alert').filter({ hasText: 'Demasiadas descargas' }).first().waitFor({ timeout: 5000 })
comprobar(true, 'un 429 se ve en pantalla con su mensaje')
await page.route('**/api/v1/exportaciones/transacciones*', route => route.fulfill({ status: 413, contentType: 'text/plain', body: 'Request Entity Too Large' }))
await form.getByRole('button', { name: /^Descargar/ }).click()
await page.getByRole('alert').filter({ hasText: 'El archivo es demasiado grande. Elige menos meses.' }).first().waitFor({ timeout: 5000 })
comprobar(true, 'un 413 opaco (sin JSON) muestra el mensaje claro por defecto')
await page.unroute('**/api/v1/exportaciones/transacciones*')

comprobar(!(await page.evaluate(() => document.cookie)).includes('eyJ'), 'JavaScript no puede leer el token de sesión')

// --- Reportes y celular / modo oscuro ---
await page.goto(`${BASE}/dashboard/reports`, { waitUntil: 'networkidle' })
comprobar(await page.getByRole('button', { name: 'Descargar', exact: true }).isVisible(), 'Reportes también tiene el botón «Descargar»')
await ctx.close()

for (const [nombre, opciones] of [['pc-oscuro', { viewport: { width: 1280, height: 900 }, colorScheme: 'dark' }], ['celular-claro', { ...devices['iPhone 13'], colorScheme: 'light' }], ['celular-oscuro', { ...devices['iPhone 13'], colorScheme: 'dark' }]]) {
  const c = await browser.newContext(opciones)
  const p = await iniciarSesion(c)
  await p.goto(`${BASE}/dashboard/reports`, { waitUntil: 'networkidle' })
  await p.getByRole('button', { name: 'Descargar', exact: true }).click()
  await p.getByRole('form', { name: 'Descargar transacciones' }).waitFor()
  const desborde = await p.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)
  comprobar(!desborde, `${nombre}: sin desborde horizontal`)
  await captura(p, `exportar-${nombre}`)
  await c.close()
}

comprobar(errores.length === 0, `sin errores de JavaScript ${errores.length ? JSON.stringify(errores) : ''}`)
await browser.close()
process.exit(fallos ? 1 : 0)
