# CT-NNN — {{MÉTODO /ruta}}

- **Versión:** v1 · **UC / REQ:**
- **Permiso requerido:**

## Entrada
```json
{
  "campo": "tipo — obligatorio/opcional — regla"
}
```

## Condiciones (precondiciones de negocio)
-

## Salida exitosa — `200`
```json
{}
```

## Errores
| HTTP | Código de negocio | Cuándo | Mensaje |
|---|---|---|---|
| 400 | | Validación | |
| 403 | | Sin permiso | |
| 409 | | Transición no permitida / invariante | |

## Efectos secundarios
(Auditoría: actor, fecha; eventos publicados; notificaciones.)

## Compatibilidad
Cambios incompatibles requieren nueva versión y ADR.
