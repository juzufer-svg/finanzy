import { monthTitle, shiftMonth } from '@/lib/month-stats'

/** Botones de mes anterior / siguiente. En el celular se muestran solo las flechas. */
export default function MonthNavigator({ mes, onChange }: { mes: string; onChange: (mes: string) => void }) {
  return (
    <div className="flex items-center gap-2" role="group" aria-label="Cambiar de mes">
      <button
        type="button"
        onClick={() => onChange(shiftMonth(mes, -1))}
        className="btn-secondary px-3"
        aria-label={`Mes anterior: ${monthTitle(shiftMonth(mes, -1))}`}
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.75 19.5 8.25 12l7.5-7.5" />
        </svg>
        <span className="hidden sm:inline">Anterior</span>
      </button>
      <button
        type="button"
        onClick={() => onChange(shiftMonth(mes, 1))}
        className="btn-secondary px-3"
        aria-label={`Mes siguiente: ${monthTitle(shiftMonth(mes, 1))}`}
      >
        <span className="hidden sm:inline">Siguiente</span>
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="m8.25 4.5 7.5 7.5-7.5 7.5" />
        </svg>
      </button>
    </div>
  )
}
