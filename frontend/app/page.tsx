import Link from 'next/link'
import FinanzyLogo from '@/components/FinanzyLogo'

// Página pública (CHG-012, B3): íconos SVG coherentes con la app (antes emojis) y textos que
// describen lo que la app hace de verdad. La vista previa es una maqueta ilustrativa, sin datos reales.

const FEATURES = [
  {
    title: 'Ingresos y gastos en segundos',
    text: 'Anota cada movimiento con su categoría y medio de pago, y encuéntralo después con el buscador.',
    icon: 'M2.25 8.25h19.5M2.25 9h19.5m-16.5 5.25h6m-6 2.25h3m-3.75 3h15a2.25 2.25 0 0 0 2.25-2.25V6.75A2.25 2.25 0 0 0 19.5 4.5h-15a2.25 2.25 0 0 0-2.25 2.25v10.5A2.25 2.25 0 0 0 4.5 19.5Z',
  },
  {
    title: 'Gastos fijos sin repetir trabajo',
    text: 'Guarda tu arriendo, sueldo o suscripciones una vez. Cuando llega la fecha, los confirmas con un toque.',
    icon: 'M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99',
  },
  {
    title: 'Presupuestos con avisos',
    text: 'Pon un límite por categoría y mira cuánto te queda. Te avisamos al llegar al 75 % y al pasarte.',
    icon: 'M12 6v12m-3-2.818.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
  },
  {
    title: 'Metas de ahorro',
    text: 'Define cuánto quieres juntar y para cuándo. Cada abono suma a tu meta y queda registrado.',
    icon: 'M3 3v1.5M3 21v-6m0 0 2.77-.693a9 9 0 0 1 6.208.682l.108.054a9 9 0 0 0 6.086.71l3.114-.732a48.524 48.524 0 0 1-.005-10.499l-3.11.732a9 9 0 0 1-6.085-.711l-.108-.054a9 9 0 0 0-6.208-.682L3 4.5M3 15V4.5',
  },
  {
    title: 'Reportes del mes',
    text: 'Compara con el mes anterior, mira tu gasto diario promedio y una proyección al cierre del mes.',
    icon: 'M7.5 14.25v2.25m3-4.5v4.5m3-6.75v6.75m3-9v9M6 20.25h12A2.25 2.25 0 0 0 20.25 18V6A2.25 2.25 0 0 0 18 3.75H6A2.25 2.25 0 0 0 3.75 6v12A2.25 2.25 0 0 0 6 20.25Z',
  },
  {
    title: 'Asistente con IA',
    text: 'Pregunta en tus palabras: «¿cuánto gasté en comida este mes?». Solo consulta, nunca cambia tus datos.',
    icon: 'M8.625 9.75a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H8.25m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H12m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0h-.375m-13.5 3.01c0 1.6 1.123 2.994 2.707 3.227 1.087.16 2.185.283 3.293.369V21l4.184-4.183a1.14 1.14 0 0 1 .778-.332 48.294 48.294 0 0 0 5.83-.498c1.585-.233 2.708-1.626 2.708-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z',
  },
]

/** Maqueta de la app (ilustrativa): resumen, presupuesto y gasto por categoría. */
function AppPreview() {
  const barras = [
    { nombre: 'Mercado', pct: 82 },
    { nombre: 'Transporte', pct: 48 },
    { nombre: 'Ocio', pct: 31 },
  ]
  return (
    <div className="relative mx-auto w-full max-w-md" aria-hidden>
      <div className="absolute -inset-6 bg-gradient-to-tr from-[#00B89C]/30 via-blue-500/20 to-indigo-500/30 blur-3xl rounded-[3rem]" />
      <div className="relative rounded-2xl border border-white/10 bg-slate-900/80 backdrop-blur p-4 sm:p-5 shadow-2xl text-left">
        <div className="flex items-center justify-between mb-4">
          <p className="text-sm font-semibold text-white">Noviembre</p>
          <span className="text-[11px] px-2 py-0.5 rounded-full bg-amber-400/15 text-amber-300 font-semibold">1 pendiente</span>
        </div>
        <div className="grid grid-cols-3 gap-2 mb-4">
          {[
            { l: 'Ingresos', v: '$ 4,2 M', c: 'text-emerald-300' },
            { l: 'Gastos', v: '$ 2,9 M', c: 'text-rose-300' },
            { l: 'Balance', v: '$ 1,3 M', c: 'text-sky-300' },
          ].map(k => (
            <div key={k.l} className="rounded-xl bg-white/5 border border-white/5 p-2.5">
              <p className="text-[10px] text-slate-400">{k.l}</p>
              <p className={`text-sm font-bold ${k.c}`}>{k.v}</p>
            </div>
          ))}
        </div>
        <div className="rounded-xl bg-white/5 border border-white/5 p-3 mb-3">
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-200 font-semibold">Presupuesto · Mercado</span>
            <span className="text-amber-300 font-bold">82 %</span>
          </div>
          <div className="mt-2 h-2 rounded-full bg-white/10 overflow-hidden"><div className="h-2 w-[82%] rounded-full bg-amber-400" /></div>
        </div>
        <div className="rounded-xl bg-white/5 border border-white/5 p-3 space-y-2.5">
          <p className="text-xs text-slate-200 font-semibold">En qué gastaste</p>
          {barras.map(b => (
            <div key={b.nombre}>
              <div className="flex justify-between text-[11px] text-slate-400"><span>{b.nombre}</span><span>{b.pct} %</span></div>
              <div className="mt-1 h-1.5 rounded-full bg-white/10 overflow-hidden">
                <div className="h-1.5 rounded-full bg-gradient-to-r from-blue-400 to-[#00B89C]" style={{ width: `${b.pct}%` }} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function Home() {
  return (
    <div className="min-h-screen bg-[#0D1B4B] bg-gradient-to-br from-slate-950 via-[#0D1B4B] to-slate-900 flex flex-col text-white">
      {/* Navegación */}
      <nav className="flex justify-between items-center px-4 md:px-12 py-4 md:py-6 pt-[max(1rem,env(safe-area-inset-top))]" aria-label="Principal">
        <div className="flex items-center shrink-0">
          <FinanzyLogo variant="horizontal" size={36} lightText className="hidden md:flex" />
          <FinanzyLogo variant="horizontal" size={28} lightText className="flex md:hidden" />
        </div>
        <div className="flex items-center gap-2 md:gap-4 shrink-0">
          <Link href="/auth/login" className="px-3 md:px-5 py-2 text-sm md:text-base text-white/90 hover:text-white rounded-lg transition font-medium whitespace-nowrap focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-300">
            Iniciar sesión
          </Link>
          <Link href="/auth/register" className="px-3 md:px-5 py-2 text-sm md:text-base bg-[#00B89C] hover:bg-[#00a68c] text-white rounded-lg transition font-semibold whitespace-nowrap shadow-lg shadow-teal-900/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-300 focus-visible:ring-offset-2 focus-visible:ring-offset-[#0D1B4B]">
            Crear cuenta
          </Link>
        </div>
      </nav>

      <main className="flex-1">
        {/* Portada */}
        <section className="px-4 md:px-12 pt-8 md:pt-16 pb-16 md:pb-24">
          <div className="max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-16 items-center">
            <div className="text-center lg:text-left">
              <p className="inline-flex items-center gap-2 text-xs font-semibold text-teal-200 bg-white/5 border border-white/10 rounded-full px-3 py-1 mb-5">
                <span className="w-1.5 h-1.5 rounded-full bg-[#00B89C]" aria-hidden /> Gratis · en el navegador y el celular
              </p>
              <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold leading-tight tracking-tight mb-5">
                Toma el control de <span className="bg-gradient-to-r from-sky-300 to-[#00B89C] bg-clip-text text-transparent">tu dinero</span>, mes a mes
              </h1>
              <p className="text-base sm:text-lg text-slate-300 leading-relaxed mb-8 max-w-xl mx-auto lg:mx-0">
                Registra tus ingresos y gastos, ponles límite por categoría y avanza hacia tus metas de ahorro. Todo en un solo lugar, en español.
              </p>
              <div className="flex flex-col sm:flex-row gap-3 justify-center lg:justify-start">
                <Link href="/auth/register" className="px-6 py-3.5 bg-[#00B89C] hover:bg-[#00a68c] text-white rounded-xl font-semibold text-base shadow-xl shadow-teal-900/40 transition text-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-300 focus-visible:ring-offset-2 focus-visible:ring-offset-[#0D1B4B]">
                  Empieza gratis
                </Link>
                <Link href="/auth/login" className="px-6 py-3.5 bg-white/5 hover:bg-white/10 border border-white/15 text-white rounded-xl font-semibold text-base transition text-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-300">
                  Ya tengo cuenta
                </Link>
              </div>
            </div>
            <AppPreview />
          </div>
        </section>

        {/* Funciones */}
        <section className="px-4 md:px-12 pb-16 md:pb-24" aria-labelledby="funciones-titulo">
          <div className="max-w-6xl mx-auto">
            <h2 id="funciones-titulo" className="text-2xl md:text-3xl font-bold text-center mb-3">Todo lo que necesitas para tus finanzas personales</h2>
            <p className="text-slate-400 text-center mb-10 max-w-2xl mx-auto">Sin hojas de cálculo ni fórmulas: tú anotas, Finanzy organiza.</p>
            <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-5">
              {FEATURES.map(f => (
                <li key={f.title} className="rounded-2xl border border-white/10 bg-white/[0.04] p-5 md:p-6 hover:bg-white/[0.07] transition">
                  <span className="w-11 h-11 rounded-xl bg-[#00B89C]/15 text-[#5eead4] flex items-center justify-center mb-4" aria-hidden>
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d={f.icon} />
                    </svg>
                  </span>
                  <h3 className="text-base md:text-lg font-semibold mb-1.5">{f.title}</h3>
                  <p className="text-sm text-slate-400 leading-relaxed">{f.text}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* Llamado final */}
        <section className="px-4 md:px-12 pb-16 md:pb-24">
          <div className="max-w-4xl mx-auto rounded-3xl border border-white/10 bg-gradient-to-r from-blue-600/30 to-[#00B89C]/25 p-8 md:p-12 text-center">
            <h2 className="text-2xl md:text-3xl font-bold mb-3">Empieza hoy, en menos de un minuto</h2>
            <p className="text-slate-200 mb-6">Crea tu cuenta con tu correo y registra tu primer movimiento.</p>
            <Link href="/auth/register" className="inline-flex px-6 py-3.5 bg-white text-[#0D1B4B] hover:bg-slate-100 rounded-xl font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-300 focus-visible:ring-offset-2 focus-visible:ring-offset-[#0D1B4B]">
              Crear mi cuenta gratis
            </Link>
          </div>
        </section>
      </main>

      <footer className="border-t border-white/10 px-6 md:px-12 py-6 pb-[max(1.5rem,env(safe-area-inset-bottom))] text-center text-sm text-slate-400">
        <p>© {new Date().getFullYear()} Finanzy · Hecho por Julian Zuñiga · <Link href="/privacidad" className="underline hover:text-white">Privacidad</Link> · <Link href="/terminos" className="underline hover:text-white">Condiciones</Link></p>
      </footer>
    </div>
  )
}
