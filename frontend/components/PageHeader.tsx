import React from 'react'

/**
 * Encabezado común de las vistas del dashboard: título, subtítulo y acciones.
 * En el celular las acciones bajan a su propia línea solo si no caben al lado del título.
 */
export default function PageHeader({ title, subtitle, actions }: {
  title: string
  subtitle?: React.ReactNode
  actions?: React.ReactNode
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-3">
      <div className="min-w-0">
        <h1 className="page-title">{title}</h1>
        {subtitle && <p className="page-subtitle">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}
