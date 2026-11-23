import React from 'react'
import Link from 'next/link'
import FinanzyLogo from '@/components/FinanzyLogo'

/** Diseño común de las páginas legales públicas (/privacidad y /terminos, CHG-014). */
export function LegalPage({ titulo, actualizada, intro, children }: {
  titulo: string
  actualizada: string
  intro: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div className="min-h-screen bg-[#fff] dark:bg-slate-900">
      <header className="border-b border-slate-200 dark:border-slate-700 px-4 md:px-8 py-4 pt-[max(1rem,env(safe-area-inset-top))]">
        <div className="max-w-3xl mx-auto flex items-center justify-between gap-4">
          <Link href="/" aria-label="Finanzy, ir al inicio" className="rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
            <FinanzyLogo variant="horizontal" size={28} />
          </Link>
          <Link href="/auth/login" className="text-sm font-semibold text-blue-600 hover:underline">Iniciar sesión</Link>
        </div>
      </header>

      <main className="px-4 md:px-8 py-8 md:py-12 pb-[max(2rem,env(safe-area-inset-bottom))]">
        <article className="max-w-3xl mx-auto space-y-8">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900 dark:text-white">{titulo}</h1>
            <p className="text-sm text-slate-500 mt-2">Última actualización: {actualizada}</p>
            <div className="mt-4 text-slate-700 dark:text-slate-300 leading-relaxed">{intro}</div>
          </div>
          {children}
          <p className="pt-4 border-t border-slate-200 dark:border-slate-700 text-sm flex flex-wrap gap-x-4 gap-y-2">
            <Link href="/" className="font-semibold text-blue-600 hover:underline">← Volver a Finanzy</Link>
            <Link href="/privacidad" className="text-blue-600 hover:underline">Política de privacidad</Link>
            <Link href="/terminos" className="text-blue-600 hover:underline">Condiciones del servicio</Link>
          </p>
        </article>
      </main>
    </div>
  )
}

export function Seccion({ id, titulo, children }: { id: string; titulo: string; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-titulo`} className="space-y-3 scroll-mt-6">
      <h2 id={`${id}-titulo`} className="text-lg sm:text-xl font-bold text-slate-900 dark:text-white">{titulo}</h2>
      <div className="space-y-3 text-slate-700 dark:text-slate-300 leading-relaxed">{children}</div>
    </section>
  )
}
