# UC-012 — Gestionar y confirmar transacciones recurrentes

- **REQ:** F-016 · **Contrato:** CT-008 · **Invariantes:** INV-001, INV-002, INV-025, INV-026 · **CHG:** CHG-012
- **Actor:** Usuario con sesión.

## Flujo principal
1. En «Recurrentes» pulsa «Nueva recurrente» e indica tipo, nombre, monto, categoría, frecuencia, primera fecha y medio de pago.
2. El sistema la guarda con su día ancla. **No registra ninguna transacción** (INV-025).
3. Cuando llega la fecha, el Inicio y la página de Recurrentes muestran «Pendientes por confirmar» con el monto propuesto.
4. El usuario ajusta el monto si cambió (p. ej. la factura de la luz) y pulsa «Registrar».
5. El sistema crea la transacción con la fecha de la ocurrencia y mueve la recurrente a su próxima fecha.

## Flujos alternos
- **Omitir:** el usuario pulsa «Omitir» y confirma; no se registra nada y avanza a la próxima fecha.
- **Atrasadas:** si pasaron varias fechas, se confirman una por una (cada confirmación deja pendiente la siguiente si también llegó).
- **Doble toque / otra pestaña:** la segunda confirmación de la misma fecha recibe 409 y la lista se actualiza (INV-026).
- **Pausar / activar / editar / eliminar:** desde la lista. Una pausada no aparece en pendientes. Eliminar conserva las transacciones ya registradas.
- **Categoría borrada:** la recurrente queda «Sin categoría».
