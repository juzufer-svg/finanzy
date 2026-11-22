import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import ThemeProvider from '@/components/ThemeProvider'
import DialogProvider from '@/components/DialogProvider'

// Fuente auto-alojada por Next.js (sin peticiones a Google en tiempo de ejecución)
const inter = Inter({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700', '800'],
  display: 'swap',
  variable: '--font-inter',
})

export const metadata: Metadata = {
  title: 'Finanzy - Control a tu medida',
  description: 'Tu solución completa para gestionar tus finanzas personales',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="es" className={inter.variable}>
      <body className="antialiased font-inter bg-gradient-to-br from-slate-50 via-blue-50 to-slate-50 dark:bg-slate-900 dark:from-slate-900 dark:via-slate-900 dark:to-slate-900">
        <ThemeProvider>
          <DialogProvider>
            {children}
          </DialogProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}
