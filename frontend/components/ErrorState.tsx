'use client'

/** Bloque de error para cuando no se pudieron cargar los datos de una vista. */
export default function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      role="alert"
      className="rounded-xl border border-red-200 bg-red-50 p-6 text-center dark:border-red-900/60 dark:bg-red-950/40"
    >
      <p className="font-semibold text-red-800 dark:text-red-200">{message}</p>
      <p className="mt-1 text-sm text-red-700/80 dark:text-red-300/80">
        Tus datos están a salvo; solo no pudimos mostrarlos ahora.
      </p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-4 rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-600"
        >
          Reintentar
        </button>
      )}
    </div>
  )
}
