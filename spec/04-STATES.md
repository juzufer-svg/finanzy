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
| cualquiera | reinicio o despliegue del backend | (se conserva) | Desde CHG-020 el código vive en PostgreSQL, solo como HMAC (INV-037, INV-040); sin Supabase (solo fuera de producción) sigue en memoria (INV-041) |

## Bloqueo de login (CHG-020)

Estados: `libre`, `contando` (1 a 4 fallos en la ventana de 15 min), `bloqueado` (5.º fallo, 15 min)

| Desde | Acción | Hacia | Precondiciones / efecto |
|---|---|---|---|
| libre | fallo de login (o de contraseña actual en el perfil) | contando | Se reserva el intento antes de comprobar la contraseña (INV-038) |
| contando | 5.º fallo dentro de 15 min | bloqueado | 429 durante 15 min desde ese fallo; no se comprueba ninguna contraseña |
| contando | 15 min desde el primer fallo sin llegar a 5 | libre | La ventana caduca |
| contando / bloqueado | inicio de sesión correcto (solo si no está bloqueado), restablecimiento de contraseña | libre | Reinicia el contador |
| bloqueado | pasan 15 min | libre | — |
| cualquiera | reinicio o despliegue del backend | (se conserva) | Persistido en PostgreSQL (INV-037) |
| cualquiera | eliminar la cuenta / pasan 30 días sin actividad | (desaparece) | INV-040 |

## Cuenta de dinero (CHG-019)

Estados: `activa`, `archivada`, `eliminada` (no existe). El saldo es derivado, no un estado (INV-047).

| Desde | Acción | Hacia | Quién | Precondiciones / efecto |
|---|---|---|---|---|
| — | crear | activa | Usuario | Menos de 20 cuentas, nombre único, saldo inicial válido (INV-050, INV-051) |
| activa | archivar | archivada | Usuario | Cualquier saldo; queda congelada (sin altas, cambios ni bajas de movimientos) |
| archivada | desarchivar | activa | Usuario | — |
| activa | eliminar | eliminada | Usuario | Solo sin movimientos ni transferencias; si no, 409 «archívala» |
| activa / archivada | eliminar la cuenta de usuario | eliminada | Usuario | Cascada con todos sus datos (INV-021) |

Una **Transferencia** no tiene estados: se crea y se elimina (no se edita).

## Meta (derivado, no persistido)

Estados: `en progreso` (ahorrado < objetivo), `completada` (ahorrado ≥ objetivo)

| Desde | Acción | Hacia | Precondiciones |
|---|---|---|---|
| en progreso | abonar / editar ahorrado | completada | Ahorrado alcanza el objetivo |
| completada | editar objetivo o ahorrado | en progreso | Ahorrado queda por debajo del objetivo |

> La columna `metas.estado` de la BD no se usa (pregunta abierta 3 en `REQUIREMENTS.md`).

## Monitor y Contador diario (CHG-017)

Sin estados nuevos. El Dueño es un actor derivado del correo de la sesión (no un estado del Usuario) y el Contador
diario solo se incrementa o se purga por antigüedad (INV-036); no tiene ciclo de vida.

**Transiciones no listadas = prohibidas.** El backend debe rechazarlas con error de negocio claro.
