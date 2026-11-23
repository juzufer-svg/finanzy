# Registrar movimientos por WhatsApp con IA (CHG-014)

Escribes a un número de WhatsApp en lenguaje libre («almorcé por 18 mil con débito», «me llegó el sueldo,
2 millones cien») y Finanzy registra el ingreso o gasto en tu cuenta. Responde con lo que guardó; si algo quedó
mal escribes «deshacer» o lo corriges («no, eran 80 mil»).

## Costo
- **WhatsApp (Meta):** $0. Los mensajes que tú envías no se cobran y Meta regala **1.000 respuestas al mes por
  número**. Sin tarjeta registrada Meta nunca cobra: si algún mes se pasara de 1.000, solo dejaría de responder.
- **IA (Claude Haiku, de tu saldo de Anthropic):** unos 0,0003 US$ por mensaje (~0,18 US$ con 600 mensajes al mes).
  Tope: 50 mensajes por día (`WHATSAPP_MENSAJES_POR_DIA`). Ver `docs/COSTOS_ASISTENTE.md`.

## Paso a paso (una sola vez, ~30-45 minutos)

### 1. Ejecutar el SQL en Supabase
Supabase → SQL Editor → New query → pegar `backend/sql/2026-11-23_whatsapp.sql` → Run. Debe mostrar 3 tablas con
`rowsecurity = true`.

### 2. Crear la app en Meta
1. Entra a https://developers.facebook.com/apps con tu cuenta de Facebook y pulsa **Create App**.
2. Nombre (p. ej. «Finanzy») y tu correo.
3. Caso de uso: **Connect with customers through WhatsApp** → Next.
4. Crea un *business portfolio* (gratis; tu nombre basta) o elige uno existente → **Create app**.

### 3. Número de prueba y tu número
1. En el panel de la app: **WhatsApp → API Setup** (o «Start using the API»).
2. Meta te asigna un **número de prueba** («From»). Copia el **Phone number ID** (es un número largo, no el teléfono).
3. En **To**, agrega **tu número personal** de WhatsApp. Te llega un código por WhatsApp para verificarlo.
4. Pulsa **Send message**: te llega un mensaje de prueba de Meta. **Respóndele cualquier cosa** (así se abre el chat).

### 4. Token permanente
El token que aparece en API Setup vence rápido. Para uno permanente:
1. https://business.facebook.com/latest/settings → **System users** → **Add+** → nombre «finanzy-bot», rol **Admin**.
2. Selecciónalo → **Assign assets** → tu app → permiso **Manage app** (control total). Asígnale también tu cuenta de WhatsApp.
3. **Generate token** → elige tu app → vencimiento **Never** → permisos `whatsapp_business_messaging` y
   `whatsapp_business_management` → copia el token (solo se muestra una vez).

### 5. App Secret
Panel de la app → **App settings → Basic** → **App secret** → Show → cópialo.

### 6. Variables en Railway
Railway → tu servicio del backend → **Variables** → agrega:

| Variable | Valor |
|---|---|
| `WHATSAPP_TOKEN` | El token permanente del paso 4 |
| `WHATSAPP_APP_SECRET` | El App secret del paso 5 |
| `WHATSAPP_PHONE_NUMBER_ID` | El Phone number ID del paso 3 |
| `WHATSAPP_VERIFY_TOKEN` | Una palabra secreta que inventes (p. ej. 30 letras y números al azar) |

`ANTHROPIC_API_KEY` ya existe (la usa el Asistente). Railway se reinicia solo al guardar.

### 7. Webhook
Panel de la app → **WhatsApp → Configuration** → **Webhook** → Edit:
- **Callback URL:** `https://<URL-de-tu-backend-en-Railway>/api/v1/whatsapp/webhook`
  (la URL pública de Railway, la misma que tiene `BACKEND_URL` en Vercel; **no** la de Vercel).
- **Verify token:** la palabra secreta de `WHATSAPP_VERIFY_TOKEN`.
- **Verify and save**. Luego, en **Webhook fields**, suscríbete a **messages**.

### 8. Conectar tu número a tu cuenta
Finanzy → **Perfil → WhatsApp → Conectar WhatsApp** → envía el código `FZ-…` al número de prueba → te responde
«✅ ¡Listo!». Desde ahí ya puedes escribir tus movimientos.

## Cómo usarlo
- «hoy almorcé por 18 mil con débito» · «me llegó el sueldo, 2 millones cien» · «ayer 85 mil de internet y 6 de taxi».
- Montos siempre en **pesos colombianos**. Si no dices la fecha, es hoy. Si no dices el medio de pago, queda sin especificar.
- La categoría la elige la IA entre **tus** categorías; si ninguna encaja queda «Sin categoría».
- Si falta el monto, te pregunta. «deshacer» borra lo último registrado por WhatsApp; «no, eran 80 mil» lo corrige.
- «ayuda» muestra ejemplos (sin gastar IA).

## Problemas comunes
| Síntoma | Causa probable |
|---|---|
| Meta no verifica el webhook | `WHATSAPP_VERIFY_TOKEN` distinto al escrito en Meta, o la URL no es la de Railway |
| No responde nada | Falta suscribirse a **messages**, falta alguna variable en Railway, o tu número no está enlazado |
| «El código no es válido» | Venció (10 min) o ya se usó: genera otro en Perfil |
| «No pude procesar tu mensaje» | Sin saldo en la Claude Console o la IA no respondió: no se registró nada |
| Dejó de responder tras un tiempo | El token no era permanente (paso 4) |
