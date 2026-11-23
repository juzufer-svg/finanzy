import React from 'react'
import Link from 'next/link'

/**
 * Estado vacío con guía (CHG-012, B6): explica qué falta y ofrece el siguiente paso.
 * La acción puede ser un botón (`onAction`) o un enlace (`actionHref`).
 */
export default function EmptyState({ title, description, actionLabel, onAction, actionHref, icon, compact = false }: {
  title: string
  description?: string
  actionLabel?: string
  onAction?: () => void
  actionHref?: string
  icon?: React.ReactNode
  /** Sin tarjeta y con menos espacio (para usar dentro de otra tarjeta). */
  compact?: boolean
}) {
  const action = actionLabel && (actionHref
    ? <Link href={actionHref} className="btn-primary mt-4">{actionLabel}</Link>
    : onAction ? <button type="button" onClick={onAction} className="btn-primary mt-4">{actionLabel}</button> : null)

  return (
    <div className={`flex flex-col items-center text-center ${compact ? 'py-8 px-4' : 'card px-6 py-12 sm:p-16'}`}>
      <div className="w-14 h-14 bg-slate-100 rounded-2xl flex items-center justify-center mb-4 text-slate-400" aria-hidden>
        {icon ?? (
          <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
        )}
      </div>
      <h3 className="text-base font-semibold text-slate-700">{title}</h3>
      {description && <p className="text-sm text-slate-500 mt-1 max-w-sm">{description}</p>}
      {action}
    </div>
  )
}
