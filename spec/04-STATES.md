# Estados y transiciones

## Usuario

Estados: `pendiente` (is_active = false), `activa` (is_active = true), `eliminada` (no existe)

```
(registro) ──▶ pendiente ──verificar código──▶ activa ──eliminar cuenta──▶ eliminada
                   │   └──restablecer contraseña──▶ activa
                   └──1 hora sin verificar──▶ eliminada (limpieza automática)
```

| Desde | Acción | Hacia | Quién puede | Precondiciones | Efectos |
|---|---|---|---|---|---|
| — | registrarse | pendiente | Visitante | Correo no registrado como activa | Se envía código (con límites) |
| pendiente | verificar código | activa | Visitante | Código válido, no vencido | Se emite sesión |
| pendiente | restablecer contraseña | activa | Visitante | Código de reset válido | El código prueba la propiedad del correo |
| pendiente | iniciar sesión | pendiente | Visitante | Credenciales válidas | No hay sesión; se envía código (INV-006) |
| pendiente | limpieza | eliminada | Sistema | Creada hace > 1 hora | Borrado definitivo |
| activa | eliminar cuenta | eliminada | Usuario | Confirma escribiendo su correo | Se borran todos sus datos (cascada) |

## Código de verificación

Estados: `vigente`, `usado`, `invalidado`, `vencido`

| Desde | Acción | Hacia | Precondiciones / efecto |
|---|---|---|---|
| — | emitir | vigente | Respeta límites (INV-010); reemplaza al código anterior del mismo propósito |
| vigente | verificar con el valor correcto | usado | Un solo uso (INV-007) |
| vigente | 5.º intento fallido | invalidado | Hay que pedir otro |
| vigente | pasan 10 minutos | vencido | — |
| cualquiera | reinicio del backend | (desaparece) | Se guardan en memoria |

## Meta (derivado, no persistido)

Estados: `en progreso` (ahorrado < objetivo), `completada` (ahorrado ≥ objetivo)

| Desde | Acción | Hacia | Precondiciones |
|---|---|---|---|
| en progreso | abonar / editar ahorrado | completada | Ahorrado alcanza el objetivo |
| completada | editar objetivo o ahorrado | en progreso | Ahorrado queda por debajo del objetivo |

> La columna `metas.estado` de la BD no se usa (pregunta abierta 3 en `REQUIREMENTS.md`).

**Transiciones no listadas = prohibidas.** El backend debe rechazarlas con error de negocio claro.
