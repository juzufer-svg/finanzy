'use client'

import { useEffect, useState, useSyncExternalStore } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import Link from 'next/link'
import { useAuthStore } from '@/store/auth'
import { useThemeStore } from '@/store/theme'
import { useCurrencyStore } from '@/store/currency'
import { usePeriodStore } from '@/store/period'
import FinanzyLogo from '@/components/FinanzyLogo'
import apiClient from '@/lib/api-client'

// SVG Icon components
const IconDashboard = () => (
  <svg className="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
      d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 0 1 3 19.875v-6.75ZM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V8.625ZM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V4.125Z" />
  </svg>
)

const IconCreditCard = () => (
  <svg className="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
      d="M2.25 8.25h19.5M2.25 9h19.5m-16.5 5.25h6m-6 2.25h3m-3.75 3h15a2.25 2.25 0 0 0 2.25-2.25V6.75A2.25 2.25 0 0 0 19.5 4.5h-15a2.25 2.25 0 0 0-2.25 2.25v10.5A2.25 2.25 0 0 0 4.5 19.5Z" />
  </svg>
)

const IconBudget = () => (
  <svg className="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
      d="M12 6v12m-3-2.818.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
  </svg>
)

const IconGoal = () => (
  <svg className="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
      d="M3 3v1.5M3 21v-6m0 0 2.77-.693a9 9 0 0 1 6.208.682l.108.054a9 9 0 0 0 6.086.71l3.114-.732a48.524 48.524 0 0 1-.005-10.499l-3.11.732a9 9 0 0 1-6.085-.711l-.108-.054a9 9 0 0 0-6.208-.682L3 4.5M3 15V4.5" />
  </svg>
)

const IconReport = () => (
  <svg className="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
      d="M7.5 14.25v2.25m3-4.5v4.5m3-6.75v6.75m3-9v9M6 20.25h12A2.25 2.25 0 0 0 20.25 18V6A2.25 2.25 0 0 0 18 3.75H6A2.25 2.25 0 0 0 3.75 6v12A2.25 2.25 0 0 0 6 20.25Z" />
  </svg>
)

const IconProfile = () => (
  <svg className="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
      d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z" />
  </svg>
)

const IconLogout = () => (
  <svg className="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
      d="M15.75 9V5.25A2.25 2.25 0 0 0 13.5 3h-6a2.25 2.25 0 0 0-2.25 2.25v13.5A2.25 2.25 0 0 0 7.5 21h6a2.25 2.25 0 0 0 2.25-2.25V15m3 0 3-3m0 0-3-3m3 3H9" />
  </svg>
)

const IconSun = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
      d="M12 3v2.25m6.364.386-1.591 1.591M21 12h-2.25m-.386 6.364-1.591-1.591M12 18.75V21m-4.773-4.227-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0Z" />
  </svg>
)

const IconMoon = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
      d="M21.752 15.002A9.72 9.72 0 0 1 18 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 0 0 3 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 0 0 9.002-5.998Z" />
  </svg>
)

const subscribeNoop = () => () => {}

const menuItems = [
  { href: '/dashboard', label: 'Dashboard', Icon: IconDashboard },
  { href: '/dashboard/transactions', label: 'Transacciones', Icon: IconCreditCard },
  { href: '/dashboard/budgets', label: 'Presupuestos', Icon: IconBudget },
  { href: '/dashboard/goals', label: 'Metas', Icon: IconGoal },
  { href: '/dashboard/reports', label: 'Reportes', Icon: IconReport },
  { href: '/dashboard/profile', label: 'Perfil', Icon: IconProfile },
]

/** Inicial del nombre (o del correo) para el avatar. */
const initialOf = (user: { full_name?: string; email?: string } | null) =>
  (user?.full_name || user?.email || 'U').trim().charAt(0).toUpperCase()

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const [sidebarOpen, setSidebarOpen] = useState(true)
  // El menú móvil queda abierto solo para la ruta donde se abrió:
  // al navegar se cierra solo, sin un efecto que haga setState.
  const [mobileMenuPath, setMobileMenuPath] = useState<string | null>(null)
  const mobileMenuOpen = mobileMenuPath === pathname
  const setMobileMenuOpen = (open: boolean) => setMobileMenuPath(open ? pathname : null)
  // false en el servidor y durante la hidratación, true después en el cliente
  const hydrated = useSyncExternalStore(subscribeNoop, () => true, () => false)
  const { isAuthenticated, logout, user, loadAuth, setUser } = useAuthStore()
  const { dark, toggle: toggleTheme } = useThemeStore()
  const { loadRates } = useCurrencyStore()
  const resetPeriod = usePeriodStore(s => s.resetMes)

  useEffect(() => {
    loadAuth()
    loadRates()
  }, [loadAuth, loadRates])

  // Si el usuario ya tiene sesión pero no tiene full_name (sesión antigua), lo carga desde la API
  useEffect(() => {
    if (!user || user.full_name) return
    apiClient.get('/api/v1/users/me')
      .then(res => {
        if (res.data?.full_name) {
          setUser({ ...user, full_name: res.data.full_name })
        }
      })
      .catch(() => {})
  }, [user, setUser])

  useEffect(() => {
    if (hydrated && !isAuthenticated) router.push('/auth/login')
  }, [hydrated, isAuthenticated, router])

  // Esc cierra el menú móvil
  useEffect(() => {
    if (!mobileMenuOpen) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setMobileMenuPath(null) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [mobileMenuOpen])

  if (!hydrated) return null
  if (!isAuthenticated) return null

  const isActive = (href: string) =>
    href === '/dashboard' ? pathname === '/dashboard' : pathname.startsWith(href)
  const currentSection = menuItems.find(item => isActive(item.href))?.label ?? 'Dashboard'
  const displayName = user?.full_name || user?.email || 'Usuario'
  // Al cerrar sesión el período vuelve al mes actual (la siguiente persona no hereda el filtro)
  const handleLogout = async () => { resetPeriod(); await logout(); router.push('/') }

  const themeButton = (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={dark ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro'}
      title={dark ? 'Modo claro' : 'Modo oscuro'}
      className={`w-10 h-10 flex items-center justify-center rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${dark ? 'text-slate-300 hover:bg-slate-700' : 'text-slate-500 hover:bg-slate-100'}`}
    >
      {dark ? <IconSun /> : <IconMoon />}
    </button>
  )

  const userCard = (
    <div className="flex items-center gap-3 px-2 py-2 rounded-lg bg-slate-800">
      <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0" aria-hidden>
        {initialOf(user)}
      </div>
      <div className="min-w-0">
        <p className="text-xs font-semibold text-white truncate">{displayName}</p>
        {user?.email && user.email !== displayName && <p className="text-xs text-slate-400 truncate">{user.email}</p>}
      </div>
    </div>
  )

  const navLinkClass = (active: boolean) =>
    `flex items-center gap-3 px-3 rounded-lg transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 ${
      active
        ? 'bg-blue-600 text-white shadow-md shadow-blue-900/30'
        : 'text-slate-400 hover:bg-slate-800 hover:text-white'
    }`

  return (
    <div className={`min-h-viewport ${dark ? 'bg-slate-900' : 'bg-slate-100'}`}>
      {/* ── Barra lateral de escritorio (oculta en móvil) ── */}
      <aside
        aria-label="Menú principal"
        className={`hidden md:flex flex-col ${sidebarOpen ? 'w-60' : 'w-16'} bg-slate-900 text-white transition-[width] duration-300 fixed h-screen left-0 top-0 z-40 border-r border-slate-800`}
      >
        {/* Logo: el único de la vista en escritorio */}
        <Link
          href="/dashboard"
          aria-label="Finanzy, ir al inicio"
          className={`flex items-center h-16 border-b border-slate-700/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-teal-400 ${sidebarOpen ? 'px-5' : 'justify-center'}`}
        >
          {sidebarOpen ? (
            <FinanzyLogo variant="horizontal" size={30} lightText />
          ) : (
            <FinanzyLogo variant="icon" size={30} />
          )}
        </Link>

        <nav className="flex-1 px-2 py-4 space-y-1 overflow-y-auto">
          {menuItems.map(({ href, label, Icon }) => {
            const active = isActive(href)
            return (
              <Link
                key={href}
                href={href}
                title={!sidebarOpen ? label : undefined}
                aria-label={!sidebarOpen ? label : undefined}
                aria-current={active ? 'page' : undefined}
                className={`${navLinkClass(active)} py-2.5 ${sidebarOpen ? '' : 'justify-center'}`}
              >
                <Icon />
                {sidebarOpen && <span className="text-sm font-medium">{label}</span>}
              </Link>
            )
          })}
        </nav>

        {/* Usuario + cerrar sesión */}
        <div className="border-t border-slate-700/60 p-3 space-y-2">
          {sidebarOpen && userCard}
          <button
            type="button"
            onClick={handleLogout}
            title={!sidebarOpen ? 'Cerrar sesión' : undefined}
            aria-label={!sidebarOpen ? 'Cerrar sesión' : undefined}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-400 hover:bg-red-600/20 hover:text-red-400 transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400 ${sidebarOpen ? '' : 'justify-center'}`}
          >
            <IconLogout />
            {sidebarOpen && <span className="text-sm font-medium">Cerrar sesión</span>}
          </button>
        </div>

        {/* Contraer / expandir */}
        <button
          type="button"
          onClick={() => setSidebarOpen(!sidebarOpen)}
          aria-label={sidebarOpen ? 'Contraer menú' : 'Expandir menú'}
          aria-expanded={sidebarOpen}
          className="absolute -right-3 top-5 w-6 h-6 bg-slate-700 hover:bg-blue-600 text-white rounded-full flex items-center justify-center shadow-md ring-2 ring-slate-900 transition-colors duration-150 focus-visible:outline-none focus-visible:ring-teal-400"
        >
          <svg className={`w-3.5 h-3.5 transition-transform ${sidebarOpen ? '' : 'rotate-180'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M15.75 19.5 8.25 12l7.5-7.5" />
          </svg>
        </button>
      </aside>

      {/* ── Menú lateral móvil ── */}
      {mobileMenuOpen && (
        <div
          className="md:hidden fixed inset-0 bg-black/60 z-50 animate-fade-in"
          onClick={() => setMobileMenuOpen(false)}
        >
          <aside
            aria-label="Menú"
            className="absolute left-0 top-0 h-full w-72 max-w-[85vw] bg-slate-900 text-white flex flex-col shadow-2xl animate-slide-in pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)] pl-[env(safe-area-inset-left)]"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-4 h-16 border-b border-slate-700/60">
              <FinanzyLogo variant="horizontal" size={28} lightText />
              <button
                type="button"
                onClick={() => setMobileMenuOpen(false)}
                aria-label="Cerrar menú"
                autoFocus
                className="w-10 h-10 flex items-center justify-center rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18 18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <nav className="flex-1 px-2 py-4 space-y-1 overflow-y-auto">
              {menuItems.map(({ href, label, Icon }) => {
                const active = isActive(href)
                return (
                  <Link key={href} href={href} aria-current={active ? 'page' : undefined} className={`${navLinkClass(active)} py-3`}>
                    <Icon />
                    <span className="text-sm font-medium">{label}</span>
                  </Link>
                )
              })}
            </nav>

            <div className="border-t border-slate-700/60 p-3 space-y-2">
              {userCard}
              <button
                type="button"
                onClick={handleLogout}
                className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-400 hover:bg-red-600/20 hover:text-red-400 transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400"
              >
                <IconLogout />
                <span className="text-sm font-medium">Cerrar sesión</span>
              </button>
            </div>
          </aside>
        </div>
      )}

      {/* ── Contenido ── */}
      <div className={`min-w-0 flex flex-col min-h-viewport transition-[margin] duration-300 ${sidebarOpen ? 'md:ml-60' : 'md:ml-16'}`}>
        {/* Barra superior: en móvil lleva el logo (no hay barra lateral); en escritorio, la sección actual */}
        <header className={`sticky top-0 z-30 border-b pt-[env(safe-area-inset-top)] backdrop-blur ${dark ? 'bg-slate-800/95 border-slate-700' : 'bg-white/95 border-slate-200'}`}>
          <div className="h-14 md:h-16 px-3 md:px-6 flex items-center justify-between gap-3 pl-[max(0.75rem,env(safe-area-inset-left))] pr-[max(0.75rem,env(safe-area-inset-right))] md:pl-6 md:pr-6">
            <div className="flex items-center gap-1 min-w-0">
              <button
                type="button"
                className={`md:hidden w-10 h-10 flex items-center justify-center rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${dark ? 'text-slate-300 hover:bg-slate-700' : 'text-slate-600 hover:bg-slate-100'}`}
                onClick={() => setMobileMenuOpen(true)}
                aria-label="Abrir menú"
                aria-expanded={mobileMenuOpen}
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
                </svg>
              </button>
              <Link href="/dashboard" aria-label="Finanzy, ir al inicio" className="md:hidden rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
                <FinanzyLogo variant="horizontal" size={26} lightText={dark} />
              </Link>
              <div className="hidden md:flex items-baseline gap-2 min-w-0">
                <span className={`text-base font-semibold truncate ${dark ? 'text-white' : 'text-slate-900'}`}>{currentSection}</span>
                <span className={`text-sm ${dark ? 'text-slate-500' : 'text-slate-400'}`}>·</span>
                <span className={`text-sm truncate ${dark ? 'text-slate-400' : 'text-slate-500'}`}>Control financiero total</span>
              </div>
            </div>
            <div className="flex items-center gap-1 sm:gap-2 flex-shrink-0">
              {themeButton}
              <Link
                href="/dashboard/profile"
                aria-label={`Bienvenido, ${displayName}: ir a tu perfil`}
                className={`flex items-center gap-2 rounded-full sm:rounded-lg p-1 sm:pl-1.5 sm:pr-3 sm:py-1.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${dark ? 'sm:bg-slate-700/60 hover:bg-slate-700 text-slate-100' : 'sm:bg-slate-100 hover:bg-slate-200 text-slate-800'}`}
              >
                <span className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0 ${dark ? 'bg-teal-600' : 'bg-blue-600'}`} aria-hidden>
                  {initialOf(user)}
                </span>
                <span className="hidden sm:flex flex-col leading-tight text-left">
                  <span className={`text-[11px] ${dark ? 'text-slate-400' : 'text-slate-500'}`}>Bienvenido,</span>
                  <span className="text-xs font-semibold truncate max-w-[160px]">{displayName}</span>
                </span>
              </Link>
            </div>
          </div>
        </header>

        {/* Contenido de la página (desplaza la ventana: así Safari en iPhone oculta sus barras al bajar) */}
        <main className="flex-1 px-3 py-4 sm:px-4 md:p-6 lg:p-8 pb-[calc(5.5rem+env(safe-area-inset-bottom))] md:pb-8 pl-[max(0.75rem,env(safe-area-inset-left))] pr-[max(0.75rem,env(safe-area-inset-right))] sm:pl-4 sm:pr-4 md:pl-6 md:pr-6 lg:pl-8 lg:pr-8">
          <div className="animate-fade-in max-w-7xl mx-auto">{children}</div>
        </main>
      </div>

      {/* ── Navegación inferior móvil ── */}
      <nav
        aria-label="Navegación principal"
        className={`md:hidden fixed bottom-0 inset-x-0 border-t z-40 pb-[env(safe-area-inset-bottom)] backdrop-blur ${dark ? 'bg-slate-800/95 border-slate-700' : 'bg-white/95 border-slate-200'}`}
      >
        {/* Perfil no va aquí: se abre desde el avatar de la barra superior (5 botones caben sin cortar textos) */}
        <div className="grid grid-cols-5 h-16 px-[env(safe-area-inset-left)]">
          {menuItems.filter(item => item.href !== '/dashboard/profile').map(({ href, label, Icon }) => {
            const active = isActive(href)
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? 'page' : undefined}
                className={`relative flex flex-col items-center justify-center gap-1 transition-colors focus-visible:outline-none focus-visible:bg-blue-500/10 ${
                  active
                    ? (dark ? 'text-teal-300' : 'text-blue-600')
                    : (dark ? 'text-slate-400 hover:text-slate-200' : 'text-slate-500 hover:text-slate-700')
                }`}
              >
                {active && <span className={`absolute top-0 h-0.5 w-8 rounded-full ${dark ? 'bg-teal-300' : 'bg-blue-600'}`} aria-hidden />}
                <Icon />
                <span className="text-[10px] font-medium leading-none max-w-full truncate px-0.5">{label}</span>
              </Link>
            )
          })}
        </div>
      </nav>
    </div>
  )
}
