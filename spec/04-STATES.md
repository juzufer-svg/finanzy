# Estados y transiciones

## Usuario

Estados: `pendiente` (is_active = false), `activa` (is_active = true), `suspendida` (CHG-023: `suspendida = true` sobre una cuenta activa; la limpieza de cuentas sin verificar no la toca), `eliminada` (no existe)

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
| activa | suspender (CHG-023) | suspendida | Dueño (panel) | No es su propia cuenta; no ya suspendida (409) | `suspendida = true`, sube la versión de sesión, se desconecta WhatsApp, queda en el registro de acciones |
| suspendida | reactivar (CHG-023) | activa | Dueño (panel) | Está suspendida (409 si no) | `suspendida = false`; las sesiones anteriores no reviven; queda en el registro |
| suspendida | eliminar (panel) | eliminada | Dueño (panel) | Escribe el correo de la cuenta | Baja completa y registro |
| activa / suspendida / pendiente | cerrar sesiones (CHG-023) | (mismo estado) | Dueño (panel) | No es su propia cuenta | Sube la versión de sesión; WhatsApp se desconecta |
| pendiente | eliminar (panel) | eliminada | Dueño (panel) | Escribe el correo de la cuenta | Baja completa y registro (suspender una pendiente → 409) |
| suspendida | iniciar sesión / verificar correo | suspendida | Visitante | — | 403 genérico solo con contraseña correcta; sin sesión ni código (INV-056) |

## Código de verificación

Estados: `vigente`, `usado`, `invalidado`, `vencido`

| Desde | Acción | Hacia | Precondiciones / efecto |
|---|---|---|---|
| — | emitir | vigente | Respeta límites (INV-010): el espacio de 60 s y los topes se comprueban y el código se guarda en una sola operación atómica (INV-038); reemplaza al código anterior del mismo propósito |
| vigente | verificar con el valor correcto | usado | Un solo uso (INV-007) |
| vigente | 5.º intento fallido | invalidado | Hay que pedir otro |
| vigente | pasan 10 minutos | vencido | — |
| cualquiera | reinicio o despliegue del backend | (se conserva) | Desde CHG-020 el código vive en PostgreSQL, solo como HMAC (INV-037, INV-040); sin Supabase (solo fuera de producción) sigue en memoria (INV-041) |

## Bloqueo de login (CHG-020)

Estados: `libre`, `contando` (1 a 4 fallos dentro de la ventana de **24 h** contada desde el primer fallo), `bloqueado` (5.º fallo, 15 min)

| Desde | Acción | Hacia | Precondiciones / efecto |
|---|---|---|---|
| libre | intento de login (o de contraseña actual en el perfil) | contando | Se **reserva** el intento antes de comprobar la contraseña (INV-038); si era incorrecta, el fallo ya está contado |
| contando | 5.ª reserva dentro de las 24 h | bloqueado | 429 durante 15 min desde esa reserva; no se comprueba ninguna contraseña más. Si la 5.ª reserva acierta, se le devuelve el intento y se levanta el bloqueo (inicia sesión) |
| contando | pasan 24 h desde el primer fallo sin llegar a 5 | libre | La serie caduca (INV-010) |
| contando | contraseña correcta | contando o libre | Se **devuelve** el intento reservado (sin borrar los fallos de otras peticiones en vuelo); la serie se borra solo cuando ya no queda ninguna reserva en vuelo |
| contando / bloqueado | restablecimiento de contraseña | libre | Borra la serie (también desbloquea a quien otra persona bloqueó, riesgo aceptado M-6) |
| bloqueado | pasan 15 min | libre | La serie nueva empieza de cero |
| cualquiera | reinicio o despliegue del backend | (se conserva) | Persistido en PostgreSQL (INV-037) |
| cualquiera | eliminar la cuenta / pasan 30 días sin actividad | (desaparece) | INV-040 |

## Cuenta de dinero (CHG-019)

Estados: `no archivada`, `archivada`, `eliminada` (no existe). El saldo es derivado, no un estado (INV-047). (La «cuenta» de usuario sí es `activa`/`pendiente`: no mezclar.)

| Desde | Acción | Hacia | Quién | Precondiciones / efecto |
|---|---|---|---|---|
| — | crear | no archivada | Usuario | Menos de 20 cuentas de dinero, nombre único, saldo inicial válido (INV-050, INV-051) |
| no archivada | archivar | archivada | Usuario | Cualquier saldo, con o sin transacciones; queda congelada (sin transacciones nuevas, cambios ni bajas de transacciones o transferencias; `FZ002` bajo el mismo bloqueo del saldo) |
| archivada | desarchivar | no archivada | Usuario | — |
| no archivada | eliminar | eliminada | Usuario | Solo sin transacciones ni transferencias; si no, 409 «archívala» |
| no archivada / archivada | eliminar la cuenta de usuario | eliminada | Usuario | Cascada con todos sus datos (INV-021) |

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
