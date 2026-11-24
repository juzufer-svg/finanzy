# UC-016 — Gestionar cuentas de dinero y transferencias

- **REQ:** REQ-F-020 · **Contrato:** CT-012 (y CT-003 v1.2, CT-006 v1.1, CT-008 v1.1, CT-009 v1.1, CT-007 v1.1, CT-011 v1.1) · **Invariantes:** INV-046 a INV-052 (y INV-001, INV-003, INV-008, INV-021, INV-023, INV-026, INV-029) · **CHG:** CHG-019 · **ADR:** ADR-009
- **Actor principal:** Usuario con sesión activa · **Secundarios:** IA de WhatsApp (propone, no decide)
- **Disparador:** Abre «Cuentas» en el menú, elige una cuenta al registrar un movimiento, o pulsa «Transferir»
- **Precondiciones:** Sesión vigente.
- **Postcondiciones:** Los saldos reflejan los movimientos con cuenta; nada queda a medias.

## Flujo principal (fase a: cuentas y saldos)
1. La persona crea una cuenta de dinero: nombre, tipo y **saldo inicial** (lo que tiene hoy; lo escribe a mano).
2. Al registrar o editar una transacción (ingreso o gasto) puede elegir «Cuenta (opcional)». El medio de pago es otro campo y se conserva (coexisten).
3. El backend valida que la cuenta es suya (404 si no) y que el movimiento no deja una cuenta que no sea tarjeta de crédito en negativo (409 atómico, INV-048).
4. «Cuentas» muestra cada cuenta con su **saldo actual** (derivado, en la moneda de visualización), con las archivadas en una sección aparte.
5. La persona puede renombrar, corregir el saldo inicial, **archivar** o, si no tiene movimientos, **eliminar** una cuenta.

## Flujo (fase b: transferencias)
1. La persona pulsa «Transferir», elige cuenta de origen, cuenta de destino, monto, fecha y descripción opcional.
2. El backend valida que ambas son suyas y distintas, activas y que el origen conserva saldo (salvo tarjeta). Se guarda **una** transferencia y los dos saldos cambian juntos.
3. La transferencia aparece en la lista de movimientos («Efectivo → Ahorros»), pero **no** suma a ingresos ni gastos del resumen, presupuestos ni reportes.
4. Puede eliminarla (restablece los saldos si ninguno queda en negativo indebido); no se edita. Pagar una tarjeta de crédito = transferir hacia ella.

## Flujo (fase c: integraciones)
- **Abono a meta:** puede indicar la cuenta de origen; con saldo insuficiente no se registra el gasto ni se suma a la meta (INV-008).
- **Recurrente:** puede tener cuenta; al confirmar, la transacción se crea con ella; si la cuenta está archivada o sin saldo, falla y la fecha **no** avanza (INV-026).
- **WhatsApp:** si el mensaje nombra una cuenta («pagué 20 mil con Nequi desde mi cuenta Ahorros») el backend la busca entre las activas del usuario; si no se nombra, el movimiento queda sin cuenta (INV-029).
- **Asistente:** puede consultar cuentas y saldos (solo lectura, INV-023).
- **Exportación:** el archivo añade la columna «Cuenta» al final.

## Flujos alternativos / excepciones
- 1a. Nombre repetido (sin distinguir mayúsculas ni espacios) → 409. Más de 20 cuentas → 409 (INV-050).
- 1b. Saldo inicial negativo en una cuenta que no es tarjeta, o con más de 2 decimales, o por encima de 9 999 999 999,99 → 422 (INV-051).
- 3a. Gasto, baja de un ingreso, edición de monto/cuenta o cambio del saldo inicial que dejaría el saldo negativo → 409 «Saldo insuficiente…»; no se guarda nada.
- 3b. Cuenta archivada → 409 «Desarchívala para registrar movimientos»; cuenta ajena o inexistente → 404.
- 5a. Eliminar una cuenta con movimientos o transferencias → 409 «Archívala».
- 2c. Origen y destino iguales → 422; cuenta ajena → 404 (sin decir cuál de las dos).
- Dos operaciones simultáneas sobre la misma cuenta: una puede recibir 409 si ya no alcanza el saldo; nunca queda un saldo indebido (INV-048).
- BD caída → 503; no se guarda nada.

## Reglas de negocio
- Saldo = saldo inicial + ingresos − gastos + transferencias recibidas − enviadas; solo actual; en COP; **incluye todos los movimientos registrados con esa cuenta, aunque su fecha sea futura**.
- Los movimientos anteriores quedan «sin cuenta» y no mueven ningún saldo; asignarles una cuenta al editarlos es una decisión de la persona y sí lo mueve.
- Medio de pago y cuenta son independientes. «Transferencia» como medio de pago no es una transferencia entre cuentas.
- Cuentas bancarias conectadas: fuera de alcance; todo es manual.

## Contrato asociado
`CONTRACTS/CT-012` · **BDD:** `BDD/BDD-CUENTAS.feature`
