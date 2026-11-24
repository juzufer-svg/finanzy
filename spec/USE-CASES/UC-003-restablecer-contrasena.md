# UC-003 — Restablecer contraseña

- **REQ:** REQ-F-003
- **Actor principal:** Visitante
- **Disparador:** Pulsa «¿Olvidaste tu contraseña?»
- **Precondiciones:** —
- **Postcondiciones:** Contraseña nueva; cuenta activa; sesiones abiertas cerradas; WhatsApp desconectado (CHG-014)
- **Invariantes involucrados:** INV-007, INV-009, INV-010, INV-016, INV-037 a INV-041 (CHG-020)

## Flujo principal
1. El visitante ingresa su correo.
2. El sistema responde siempre lo mismo y, si la cuenta existe, envía un código de restablecimiento.
3. El visitante ingresa el código y la contraseña nueva (≥ 8, confirmada).
4. El sistema desconecta WhatsApp (si falla, responde 503 y no cambia nada; CHG-014), cambia la contraseña, cierra todas las sesiones abiertas de la cuenta (en cualquier dispositivo)
   y lo invita a iniciar sesión.

## Flujos alternativos / excepciones
- 2a. Límite por destinatario o global alcanzado → no se envía, pero la respuesta es la misma (200). Para una cuenta inexistente se ejecuta y cuenta exactamente igual (código señuelo que no se envía ni puede verificarse).
- 4a. Código inválido → 400.
- 2b. (CHG-020) El código vigente y los límites de envío viven en PostgreSQL (solo como HMAC, INV-040) y sobreviven a un despliegue; el espacio de 60 s y los topes se comprueban en una sola operación atómica (INV-038); la respuesta de la acción 2 y las llamadas a la BD son las mismas exista o no la cuenta (INV-009, INV-039).
- 2c. (CHG-020) Si la BD de estado o la lectura de la tabla de usuarios falla, o tarda más de 5 s → 503 «Servicio no disponible…», idéntico exista o no la cuenta; no se envía ni se guarda ningún código y, al restablecer, el código no se consume.
- 4b. (CHG-020) Restablecer la contraseña también desbloquea el login del correo (aunque otra persona lo hubiera bloqueado, riesgo aceptado M-6).

## Reglas de negocio
- El código de restablecimiento no sirve para verificar la cuenta y viceversa.

## Contrato asociado
`CONTRACTS/CT-001` · **BDD:** BDD-RECUPERACION, BDD-AUTH-PERSISTENTE
