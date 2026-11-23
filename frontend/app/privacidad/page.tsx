import type { Metadata } from 'next'
import Link from 'next/link'
import FinanzyLogo from '@/components/FinanzyLogo'

// Política de privacidad pública (CHG-014): la exige Meta para publicar la app de WhatsApp.
// También sirve como «instrucciones de eliminación de datos» (sección 6). Solo describe lo que la
// app hace de verdad; si cambia el tratamiento de datos, hay que actualizar este texto.

export const metadata: Metadata = {
  title: 'Política de privacidad · Finanzy',
  description: 'Qué datos guarda Finanzy, para qué los usa y cómo eliminarlos.',
}

const ACTUALIZADA = '23 de noviembre de 2026'

function Seccion({ id, titulo, children }: { id: string; titulo: string; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-titulo`} className="space-y-3">
      <h2 id={`${id}-titulo`} className="text-lg sm:text-xl font-bold text-slate-900 dark:text-white">{titulo}</h2>
      <div className="space-y-3 text-slate-700 dark:text-slate-300 leading-relaxed">{children}</div>
    </section>
  )
}

export default function Privacidad() {
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
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900 dark:text-white">Política de privacidad</h1>
            <p className="text-sm text-slate-500 mt-2">Última actualización: {ACTUALIZADA}</p>
            <p className="mt-4 text-slate-700 dark:text-slate-300 leading-relaxed">
              Finanzy es una aplicación de finanzas personales para registrar ingresos, gastos, presupuestos y metas de ahorro.
              Esta página explica qué datos guarda, para qué los usa, con qué servicios se procesan y cómo eliminarlos.
              Finanzy no vende tus datos ni los usa para publicidad.
            </p>
          </div>

          <Seccion id="datos" titulo="1. Qué datos guardamos">
            <ul className="list-disc pl-5 space-y-1.5">
              <li><strong>Cuenta:</strong> tu nombre, tu correo electrónico, tu moneda preferida y tu contraseña (guardada solo como un código cifrado irreversible, nunca en texto).</li>
              <li><strong>Tus finanzas:</strong> las transacciones (monto, fecha, tipo, categoría, medio de pago y descripción), categorías, presupuestos, metas de ahorro y transacciones recurrentes que registres.</li>
              <li><strong>WhatsApp (solo si lo conectas):</strong> el número de teléfono que enlazas, los identificadores de los mensajes ya procesados (para no registrarlos dos veces, se borran a los 7 días) y qué transacciones se crearon por WhatsApp (para poder deshacerlas).</li>
              <li><strong>En tu navegador:</strong> una cookie de sesión segura para mantenerte conectado y preferencias como el tema claro u oscuro, la moneda y el mes que estás viendo.</li>
            </ul>
          </Seccion>

          <Seccion id="uso" titulo="2. Para qué los usamos">
            <ul className="list-disc pl-5 space-y-1.5">
              <li>Mostrarte tu información financiera, reportes y avisos de presupuesto.</li>
              <li>Enviarte por correo los códigos para verificar tu cuenta y restablecer tu contraseña.</li>
              <li>Registrar los movimientos que nos escribas por WhatsApp y responderte con la confirmación.</li>
              <li>Responder las preguntas que hagas al Asistente IA dentro de la app.</li>
              <li>Proteger tu cuenta: límites de intentos, cierre de sesiones al cambiar la contraseña y detección de abusos.</li>
            </ul>
          </Seccion>

          <Seccion id="whatsapp" titulo="3. WhatsApp e inteligencia artificial">
            <p>
              Si conectas tu WhatsApp, los mensajes que envíes al número de Finanzy llegan a través de la plataforma
              WhatsApp Business de Meta. Solo se procesan los mensajes de texto del número que tú enlazaste; los de
              cualquier otro número se ignoran.
            </p>
            <p>
              Para entender lo que escribes (por ejemplo, «almorcé por 18 mil con débito»), el texto del mensaje y los
              nombres de tus categorías se envían a la API de Claude, de Anthropic. No se envían tu teléfono, tu correo
              ni tu identificador de usuario. Lo mismo aplica a las preguntas del Asistente IA, que solo consulta tus
              datos y nunca los modifica.
            </p>
            <p>Puedes desconectar WhatsApp cuando quieras en <strong>Perfil → WhatsApp → Desconectar</strong>. También se desconecta si cambias o restableces tu contraseña.</p>
          </Seccion>

          <Seccion id="servicios" titulo="4. Servicios que usamos">
            <p>Para funcionar, Finanzy usa estos proveedores, que procesan los datos solo para prestar su servicio:</p>
            <ul className="list-disc pl-5 space-y-1.5">
              <li><strong>Supabase:</strong> base de datos donde se guarda tu información.</li>
              <li><strong>Vercel</strong> y <strong>Railway:</strong> alojamiento de la aplicación web y del servidor.</li>
              <li><strong>Brevo:</strong> envío de los correos con códigos.</li>
              <li><strong>Anthropic (Claude):</strong> interpretación de mensajes de WhatsApp y respuestas del Asistente IA.</li>
              <li><strong>Meta (WhatsApp Business):</strong> envío y recepción de mensajes de WhatsApp, solo si lo conectas.</li>
              <li><strong>open.er-api.com:</strong> tasas de cambio de monedas (tu navegador las consulta; no se envían tus datos).</li>
            </ul>
          </Seccion>

          <Seccion id="seguridad" titulo="5. Cómo protegemos tus datos">
            <p>
              Toda la comunicación viaja cifrada (HTTPS). Cada persona solo puede ver y modificar sus propios datos.
              Las contraseñas se guardan cifradas, la sesión vive en una cookie que el código de la página no puede
              leer, y los mensajes de WhatsApp solo se aceptan si llevan la firma de Meta.
            </p>
          </Seccion>

          <Seccion id="eliminar" titulo="6. Cómo eliminar tus datos">
            <p>Puedes borrar toda tu información en cualquier momento, sin pedírselo a nadie:</p>
            <ol className="list-decimal pl-5 space-y-1.5">
              <li>Inicia sesión en Finanzy.</li>
              <li>Ve a <strong>Perfil → Zona de peligro → Eliminar cuenta</strong>.</li>
              <li>Escribe tu correo para confirmar.</li>
            </ol>
            <p>
              Se eliminan de inmediato tu cuenta y todos sus datos: transacciones, categorías, presupuestos, metas,
              recurrentes y el enlace de WhatsApp. Esta acción no se puede deshacer. Si solo quieres dejar de usar
              WhatsApp, basta con desconectarlo en Perfil.
            </p>
          </Seccion>

          <Seccion id="cambios" titulo="7. Cambios a esta política">
            <p>Si cambia la forma en que tratamos tus datos, actualizaremos esta página y su fecha de actualización.</p>
          </Seccion>

          <p className="pt-4 border-t border-slate-200 dark:border-slate-700 text-sm">
            <Link href="/" className="font-semibold text-blue-600 hover:underline">← Volver a Finanzy</Link>
          </p>
        </article>
      </main>
    </div>
  )
}
