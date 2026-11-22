# Objetos de valor

Valores sin identidad propia, con validación incluida (implementada en `backend/app/schemas/`).

| Value Object | Composición | Validaciones | Igualdad | Ejemplo válido / inválido |
|---|---|---|---|---|
| Email | texto | Formato de correo válido (`EmailStr`); se normaliza a minúsculas | por valor, sin distinguir mayúsculas | `ana@gmail.com` / `ana@` |
| Contraseña | texto | Registro y restablecimiento 8-128 caracteres (INV-018). Solo cuentan los primeros 72 bytes (límite de bcrypt) | — (se compara con su hash) | `Clave123` / `abc` |
| Monto | decimal | > 0 y ≤ 1 000 000 000 000; acepta texto numérico (`"12.5"`) | por valor | `42.5` / `0`, `-5` |
| Monto ahorrado | decimal | ≥ 0 y ≤ 1 000 000 000 000 | por valor | `0` / `-1` |
| Tipo de transacción | enumeración | `ingreso` o `gasto` | por valor | `gasto` / `otro` |
| Fecha | texto | Empieza con `YYYY-MM-DD` válido (mes 01-12, día 01-31) | por valor | `2026-11-22` / `hoy` |
| Mes | texto | `YYYY-MM` con mes 01-12 | por valor | `2026-11` / `2026-13`, `abc` |
| Código | texto | Exactamente 6 dígitos | por valor | `482913` / `12a456` |
| Moneda | enumeración | USD, EUR, MXN, ARS, COP, CLP | por valor | `COP` / `BTC` |
