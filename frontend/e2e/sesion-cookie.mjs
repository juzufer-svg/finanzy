/**
 * Prueba de punta a punta de la sesión en cookie HttpOnly (ADR-005, INV-020). Manual.
 *
 * Requisitos: el frontend corriendo (next start) apuntando a un backend con una cuenta activa,
 * y Playwright disponible (no es dependencia del proyecto: `npx -y playwright@1 install chromium`
 * o el Chromium que ya tenga el equipo).
 *
 *   E2E_BASE_URL=http://localhost:3000 E2E_EMAIL=... E2E_PASSWORD=... node e2e/sesion-cookie.mjs
 *   (opcional) E2E_LEGACY_TOKEN=<JWT válido> para probar la migración desde localStorage
 *
 * Nunca usar una cuenta real ni datos de producción.
 */
import { chromium } from 'playwright'

const BASE = process.env.E2E_BASE_URL || 'http://localhost:3000'
const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD
const LEGACY = process.env.E2E_LEGACY_TOKEN
if (!EMAIL || !PASSWORD) {
  console.error('Faltan E2E_EMAIL y E2E_PASSWORD')
  process.exit(2)
}

let fallos = 0
const comprobar = (ok, texto) => { console.log(`${ok ? '✔' : '✘'} ${texto}`); if (!ok) fallos++ }

const browser = await chromium.launch()
const errores = []

if (LEGACY) {
  const ctx = await browser.newContext()
  const page = await ctx.newPage()
  page.on('pageerror', e => errores.push(e.message))
  await page.goto(BASE)
  await page.evaluate(([t, email]) => {
    localStorage.setItem('token', t)
    localStorage.setItem('user', JSON.stringify({ id: 'x', email }))
  }, [LEGACY, EMAIL])
  await page.goto(`${BASE}/dashboard`)
  await page.waitForTimeout(2500)
  comprobar(page.url().endsWith('/dashboard'), 'una sesión antigua sigue abierta tras la migración')
  comprobar(await page.evaluate(() => localStorage.getItem('token')) === null, 'el token antiguo se borró de localStorage')
  comprobar((await ctx.cookies()).some(c => c.httpOnly && c.name.includes('finanzy_session')), 'la sesión pasó a una cookie HttpOnly')
  await ctx.close()
}

const ctx = await browser.newContext()
const page = await ctx.newPage()
page.on('pageerror', e => errores.push(e.message))
await page.goto(`${BASE}/auth/login`)
await page.fill('input[type=email]', EMAIL)
await page.fill('input[type=password]', PASSWORD)
const [resp] = await Promise.all([
  page.waitForResponse(r => r.url().includes('/api/v1/auth/login')),
  page.click('button[type=submit]'),
])
comprobar(!(await resp.text()).includes('access_token'), 'la respuesta de login no trae el token')
await page.waitForURL('**/dashboard', { timeout: 10000 })
comprobar(true, 'login lleva al dashboard')
comprobar(!(await page.evaluate(() => document.cookie)).includes('eyJ'), 'JavaScript no puede leer el token')
comprobar(!JSON.stringify(await page.evaluate(() => ({ ...localStorage }))).includes('eyJ'), 'localStorage no guarda el token')

const sinCsrf = await page.evaluate(async () => (await fetch('/api/v1/categorias', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ nombre: 'csrf', icono: 'x', tipo: 'gasto' }),
})).status)
comprobar(sinCsrf === 403, 'una petición sin encabezado CSRF se rechaza (403)')

await page.goto(`${BASE}/dashboard/profile`)
await page.waitForTimeout(1500)
comprobar((await page.content()).includes(EMAIL), 'el perfil carga los datos con la cookie')

await page.getByRole('button', { name: /cerrar sesi/i }).first().click()
await page.waitForTimeout(1500)
comprobar(!(await ctx.cookies()).some(c => c.name.includes('finanzy_session')), 'cerrar sesión borra la cookie')
await page.goto(`${BASE}/dashboard`)
await page.waitForTimeout(1500)
comprobar(page.url().includes('/auth/login'), 'sin sesión el dashboard lleva al login')

comprobar(errores.length === 0, `sin errores de JavaScript ${errores.length ? JSON.stringify(errores) : ''}`)
await browser.close()
process.exit(fallos ? 1 : 0)
