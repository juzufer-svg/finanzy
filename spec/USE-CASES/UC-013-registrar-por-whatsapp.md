# UC-013 — Registrar ingresos y gastos por WhatsApp con IA

- **REQ:** F-017 · **Contrato:** CT-009 · **Invariantes:** INV-001, INV-002, INV-029, INV-030 · **CHG:** CHG-014 · **ADR:** ADR-007
- **Actor:** Usuario con su número enlazado.

## Precondiciones
WhatsApp configurado en el servidor (docs/WHATSAPP.md) y el número enlazado con un código de Perfil.

## Flujo principal
1. El usuario escribe en lenguaje libre: «almorcé por 18 mil y 6 de taxi».
2. Meta envía el mensaje al webhook; el backend verifica la firma, el número enlazado y los topes.
3. La IA interpreta montos (COP), tipo, fecha, categoría (de las suyas) y medio de pago y propone registrarlos.
4. El backend valida y crea las transacciones (sin pedir confirmación) y responde con el detalle.

## Flujos alternos
- Falta el monto o no se sabe si es ingreso o gasto → la IA pregunta y no registra nada.
- «deshacer» → borra lo registrado por el último mensaje. «no, eran 80 mil» → corrige el último (o el N-ésimo).
- IA sin saldo o caída → aviso; no se registra nada.
- Número no enlazado → se ignora (sin costo).
