# UC-015 — Exportar transacciones a CSV o Excel

- **REQ:** REQ-F-019 · **Contrato:** CT-011 · **Invariantes:** INV-042 a INV-045 (y INV-001, INV-005, INV-013) · **CHG:** CHG-018 · **ADR:** ADR-011
- **Actor principal:** Usuario con sesión activa
- **Disparador:** Pulsa «Descargar» en Transacciones o en Reportes
- **Precondiciones:** Sesión vigente.
- **Postcondiciones:** El navegador guarda un archivo con **solo** las transacciones de ese usuario del rango pedido. No se modifica ningún dato.

## Flujo principal
1. En Transacciones o Reportes, la persona pulsa «Descargar». Se abre un diálogo con el **formato** (CSV o Excel) y el **rango** de meses (por defecto, el mes que está viendo; hasta 12 meses).
2. La interfaz pide `GET /api/v1/exportaciones/transacciones?desde=…&hasta=…&formato=…` con `apiClient` (por el proxy, con la cookie).
3. El backend valida mes, rango y formato (422), aplica el límite de 10 descargas/min (429), lee **solo las transacciones del usuario de la sesión** paginando de 1000 en 1000 y, si supera 10 000 filas, responde 422 sin truncar.
4. Construye el archivo (columnas de CT-011, montos en COP tal como se guardan, textos neutralizados contra fórmulas) y lo devuelve con `Cache-Control: no-store` y `Content-Disposition` genérico.
5. El navegador guarda `finanzy-transacciones-AAAA-MM.csv` (o `.xlsx`); la interfaz anuncia «Descarga lista».

## Flujos alternativos / excepciones
- 3a. Mes o rango inválido, o más de 12 meses → 422 con mensaje claro; la interfaz lo muestra (`apiErrorMessage` + `useDialog`) y no descarga nada.
- 3b. Más de 10 000 transacciones → 422 «Elige menos meses»; no se entrega un archivo parcial.
- 3c. Sin transacciones en el rango → se descarga un archivo con solo los encabezados.
- 3d. BD caída → 503; la interfaz muestra el error con opción de reintentar.
- 3e. Más de 10 descargas en un minuto → 429.
- 3f. Sin sesión → 401 (la interfaz cierra la sesión como en el resto de la app).

## Reglas de negocio
- Los montos se exportan en **COP**, sin convertir a la moneda de visualización (REQ-F-011): el archivo no cambia según la moneda elegida.
- Se exportan solo transacciones; no se recalculan reportes, presupuestos ni metas (ADR-011).
- Origen «WhatsApp» o «App»; «Recurrente» no se distingue (CHG-018 §4, pregunta 12).
- Un texto que empiece por `= + - @` o tabulación/retorno de carro se neutraliza con `'` (INV-043).
- Con cuentas de dinero (CHG-019) se añade la columna «Cuenta» al final; las transferencias no se exportan.

## Contrato asociado
`CONTRACTS/CT-011` · **BDD:** `BDD/BDD-EXPORTAR.feature`
