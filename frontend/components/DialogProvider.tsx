'use client'

/**
 * Diálogos de confirmación y avisos (toasts) propios de la app.
 * Reemplazan window.confirm() / alert(): respetan el tema, funcionan con teclado
 * (Esc cancela, el foco queda atrapado en el diálogo) y se anuncian a lectores de pantalla.
 *
 * Uso:
 *   const { confirm, notify } = useDialog()
 *   if (!(await confirm({ title: '¿Eliminar meta?', confirmLabel: 'Eliminar', danger: true }))) return
 *   notify('No se pudo eliminar', 'error')
 */
import { createContext, useCallback, useContext, useEffect, useId, useRef, useState } from 'react'

type ConfirmOptions = {
  title: string
  description?: string
  confirmLabel?: string
  cancelLabel?: string
  danger?: boolean
}

type ToastType = 'success' | 'error' | 'info'
type Toast = { id: number; message: string; type: ToastType }

type DialogApi = {
  confirm: (opts: ConfirmOptions) => Promise<boolean>
  notify: (message: string, type?: ToastType) => void
}

const DialogContext = createContext<DialogApi | null>(null)

export function useDialog(): DialogApi {
  const ctx = useContext(DialogContext)
  if (!ctx) throw new Error('useDialog debe usarse dentro de <DialogProvider>')
  return ctx
}

const TOAST_MS = 5000

export default function DialogProvider({ children }: { children: React.ReactNode }) {
  const [pending, setPending] = useState<(ConfirmOptions & { resolve: (v: boolean) => void }) | null>(null)
  const [toasts, setToasts] = useState<Toast[]>([])
  const dialogRef = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  const descId = useId()

  const confirm = useCallback((opts: ConfirmOptions) => {
    return new Promise<boolean>(resolve => setPending({ ...opts, resolve }))
  }, [])

  const notify = useCallback((message: string, type: ToastType = 'info') => {
    const id = Date.now() + Math.random()
    setToasts(t => [...t, { id, message, type }])
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), TOAST_MS)
  }, [])

  // Abrir el <dialog> nativo en modo modal (gestiona foco y tecla Esc)
  useEffect(() => {
    const el = dialogRef.current
    if (pending && el && !el.open) el.showModal()
  }, [pending])

  const close = (result: boolean) => {
    pending?.resolve(result)
    dialogRef.current?.close()
    setPending(null)
  }

  const toastStyles: Record<ToastType, string> = {
    success: 'border-emerald-500 bg-white text-slate-800 dark:bg-slate-800 dark:text-slate-100',
    error: 'border-red-500 bg-white text-slate-800 dark:bg-slate-800 dark:text-slate-100',
    info: 'border-blue-500 bg-white text-slate-800 dark:bg-slate-800 dark:text-slate-100',
  }
  const toastIcon: Record<ToastType, string> = { success: '✓', error: '!', info: 'i' }
  const toastIconBg: Record<ToastType, string> = {
    success: 'bg-emerald-500', error: 'bg-red-500', info: 'bg-blue-500',
  }

  return (
    <DialogContext.Provider value={{ confirm, notify }}>
      {children}

      {pending && (
        <dialog
          ref={dialogRef}
          aria-labelledby={titleId}
          aria-describedby={pending.description ? descId : undefined}
          onCancel={e => { e.preventDefault(); close(false) }}
          onClick={e => { if (e.target === dialogRef.current) close(false) }}
          className="finanzy-dialog overscroll-contain m-auto w-[calc(100%-2rem)] max-w-sm rounded-2xl p-0 shadow-2xl bg-white text-slate-900 dark:bg-slate-800 dark:text-slate-100 backdrop:bg-slate-900/60"
        >
          <div className="p-6">
            <h2 id={titleId} className="text-lg font-bold">{pending.title}</h2>
            {pending.description && (
              <p id={descId} className="mt-2 text-sm text-slate-600 dark:text-slate-300">{pending.description}</p>
            )}
            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                autoFocus
                onClick={() => close(false)}
                className="px-4 py-2 rounded-lg text-sm font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 dark:text-slate-200 dark:bg-slate-700 dark:hover:bg-slate-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500"
              >
                {pending.cancelLabel ?? 'Cancelar'}
              </button>
              <button
                type="button"
                onClick={() => close(true)}
                className={`px-4 py-2 rounded-lg text-sm font-semibold text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 ${
                  pending.danger
                    ? 'bg-red-600 hover:bg-red-700 focus-visible:outline-red-600'
                    : 'bg-blue-600 hover:bg-blue-700 focus-visible:outline-blue-600'
                }`}
              >
                {pending.confirmLabel ?? 'Aceptar'}
              </button>
            </div>
          </div>
        </dialog>
      )}

      {/* Avisos: aria-live para que los lectores de pantalla los anuncien */}
      <div
        aria-live="polite"
        className="fixed bottom-4 right-4 left-4 sm:left-auto z-[100] flex flex-col gap-2 sm:w-96 pointer-events-none"
      >
        {toasts.map(t => (
          <div
            key={t.id}
            role={t.type === 'error' ? 'alert' : 'status'}
            className={`finanzy-toast pointer-events-auto flex items-start gap-3 rounded-xl border-l-4 px-4 py-3 shadow-lg ${toastStyles[t.type]}`}
          >
            <span aria-hidden="true" className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-bold text-white ${toastIconBg[t.type]}`}>
              {toastIcon[t.type]}
            </span>
            <p className="flex-1 text-sm font-medium">{t.message}</p>
            <button
              type="button"
              onClick={() => setToasts(ts => ts.filter(x => x.id !== t.id))}
              aria-label="Cerrar aviso"
              className="rounded text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500"
            >
              <span aria-hidden="true">×</span>
            </button>
          </div>
        ))}
      </div>

      <style>{`
        .finanzy-dialog[open] { animation: finanzy-dialog-in 160ms cubic-bezier(0.2, 0, 0, 1); }
        .finanzy-toast { animation: finanzy-toast-in 200ms cubic-bezier(0.2, 0, 0, 1); }
        @keyframes finanzy-dialog-in { from { opacity: 0; transform: scale(0.96); } to { opacity: 1; transform: scale(1); } }
        @keyframes finanzy-toast-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
        @media (prefers-reduced-motion: reduce) {
          .finanzy-dialog[open], .finanzy-toast { animation: none; }
        }
      `}</style>
    </DialogContext.Provider>
  )
}

/** Extrae un mensaje legible de un error de axios/FastAPI. */
export function apiErrorMessage(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail[0]?.msg) return 'Revisa los datos ingresados.'
  if (err?.response?.status === 429) return 'Demasiados intentos. Espera unos minutos.'
  if (!err?.response) return 'No hay conexión con el servidor. Revisa tu internet e intenta de nuevo.'
  return fallback
}
