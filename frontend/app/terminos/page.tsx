import type { Metadata } from 'next'
import Link from 'next/link'
import { LegalPage, Seccion } from '@/components/LegalPage'

// Condiciones del servicio públicas (CHG-014): Meta las pide al configurar la app de WhatsApp.
// Describen el uso real de Finanzy (app personal y gratuita); si cambia el servicio, actualizar el texto.

export const metadata: Metadata = {
  title: 'Condiciones del servicio · Finanzy',
  description: 'Condiciones de uso de Finanzy, la app de finanzas personales.',
}

const ACTUALIZADA = '23 de noviembre de 2026'

export default function Terminos() {
  return (
    <LegalPage
      titulo="Condiciones del servicio"
      actualizada={ACTUALIZADA}
      intro={<p>
        Estas condiciones explican cómo puedes usar Finanzy, una aplicación gratuita de finanzas personales. Al crear una
        cuenta o usar la app aceptas estas condiciones y la{' '}
        <Link href="/privacidad" className="text-blue-600 hover:underline">política de privacidad</Link>.
      </p>}
    >
      <Seccion id="servicio" titulo="1. Qué es Finanzy">
        <p>
          Finanzy te permite registrar tus ingresos y gastos, organizarlos por categorías, definir presupuestos y metas de
          ahorro, ver reportes y, si lo activas, registrar movimientos escribiendo por WhatsApp y consultar un Asistente IA.
          Es una herramienta de organización personal: <strong>no es un banco, no mueve dinero, no se conecta a tus cuentas
          bancarias y no ofrece asesoría financiera, contable ni tributaria</strong>.
        </p>
      </Seccion>

      <Seccion id="cuenta" titulo="2. Tu cuenta">
        <ul className="list-disc pl-5 space-y-1.5">
          <li>Necesitas un correo válido, que verificamos con un código.</li>
          <li>Eres responsable de mantener tu contraseña en secreto y de lo que se haga con tu cuenta. Si crees que alguien
            más tiene acceso, cambia tu contraseña: se cerrarán tus demás sesiones y se desconectará WhatsApp.</li>
          <li>La cuenta es personal: úsala solo para tus propias finanzas.</li>
        </ul>
      </Seccion>

      <Seccion id="ia" titulo="3. WhatsApp y el Asistente IA">
        <ul className="list-disc pl-5 space-y-1.5">
          <li>Los mensajes que envías por WhatsApp los interpreta una inteligencia artificial, que <strong>puede
            equivocarse</strong> en el monto, la fecha, la categoría o el tipo de movimiento. Revisa la confirmación y usa
            «deshacer» o corrige el movimiento si algo quedó mal.</li>
          <li>Las respuestas del Asistente IA son orientativas y se basan en los datos que registraste; verifica la
            información importante en la app.</li>
          <li>Hay límites de uso diarios para mantener el servicio gratuito.</li>
          <li>El servicio de WhatsApp depende de Meta y puede no estar disponible en algún momento.</li>
        </ul>
      </Seccion>

      <Seccion id="uso" titulo="4. Uso permitido">
        <p>No está permitido usar Finanzy para:</p>
        <ul className="list-disc pl-5 space-y-1.5">
          <li>Intentar acceder a cuentas o datos de otras personas.</li>
          <li>Enviar mensajes automatizados o masivos, o abusar de los códigos por correo o de la IA.</li>
          <li>Interferir con el funcionamiento o la seguridad del servicio.</li>
          <li>Registrar actividades ilegales.</li>
        </ul>
        <p>Podemos suspender o eliminar las cuentas que incumplan estas reglas.</p>
      </Seccion>

      <Seccion id="datos" titulo="5. Tus datos">
        <p>
          La información que registras es tuya. Cómo la guardamos y protegemos está en la{' '}
          <Link href="/privacidad" className="text-blue-600 hover:underline">política de privacidad</Link>. Puedes eliminar
          tu cuenta y todos tus datos en cualquier momento desde <strong>Perfil → Eliminar cuenta</strong>.
        </p>
        <p>
          Hacemos copias de seguridad periódicas, pero te recomendamos no usar Finanzy como único registro de información
          que necesites conservar por obligación legal o tributaria.
        </p>
      </Seccion>

      <Seccion id="garantia" titulo="6. Disponibilidad y responsabilidad">
        <p>
          Finanzy se ofrece gratis y «tal como está». Hacemos lo posible para que funcione bien y de forma segura, pero no
          garantizamos que esté siempre disponible ni libre de errores. Las decisiones financieras que tomes son tuyas;
          Finanzy no se hace responsable de pérdidas derivadas de datos mal registrados, interpretaciones de la IA o
          interrupciones del servicio, en la medida en que la ley lo permita.
        </p>
      </Seccion>

      <Seccion id="cambios" titulo="7. Cambios en el servicio y en estas condiciones">
        <p>
          Podemos mejorar, cambiar o dejar de ofrecer funciones. Si cambian estas condiciones, actualizaremos esta página y
          su fecha de actualización; seguir usando la app después del cambio significa que aceptas la nueva versión.
        </p>
      </Seccion>

      <Seccion id="ley" titulo="8. Ley aplicable">
        <p>Estas condiciones se rigen por las leyes de la República de Colombia.</p>
      </Seccion>
    </LegalPage>
  )
}
