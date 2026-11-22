# language: es
# Trazabilidad: REQ-F-003 · UC-003 · INV-007, INV-009, INV-016
# Las pruebas automatizadas que implementan cada escenario se indican con «Prueba:».
Característica: Recuperar contraseña

  @BDD-RECUPERACION @happy-path
  Escenario: Restablecer la contraseña con el código
    Dado una cuenta existente
    Cuando pide restablecer y usa el código con una contraseña nueva válida
    Entonces puede iniciar sesión con la nueva y no con la anterior
    # Prueba: backend/tests/test_codigos.py::test_restablecer_contrasena_flujo_completo

  @BDD-RECUPERACION @invariante @INV-009
  Escenario: No se revela si un correo está registrado
    Dado un correo registrado y otro no registrado
    Cuando se pide restablecer para ambos
    Entonces la respuesta es idéntica
    # Prueba: backend/tests/test_codigos.py::test_inv009_forgot_password_responde_igual_exista_o_no

  @BDD-RECUPERACION @invariante @INV-007
  Escenario: El código es de un solo uso
    Dado un código de restablecimiento ya usado
    Cuando se intenta usar de nuevo
    Entonces se rechaza
    # Prueba: backend/tests/test_codigos.py::test_inv007_codigo_de_un_solo_uso

  @BDD-RECUPERACION @invariante @INV-016
  Escenario: Restablecer la contraseña cierra las sesiones abiertas
    Dado una cuenta con una sesión abierta en otro dispositivo
    Cuando restablece la contraseña con el código
    Entonces la sesión anterior responde 401 "Tu sesión ya no es válida. Inicia sesión de nuevo."
    Y una sesión nueva con la contraseña nueva sí funciona
    # Prueba: backend/tests/test_sesiones.py::test_inv016_restablecer_contrasena_cierra_las_sesiones_abiertas

  @BDD-RECUPERACION @invariante @INV-016
  Escenario: Desplegar el cambio no cierra las sesiones existentes
    Dado un token emitido antes de existir la versión de sesión
    Cuando se usa y la cuenta no ha restablecido la contraseña
    Entonces sigue funcionando
    # Prueba: backend/tests/test_sesiones.py::test_inv016_tokens_anteriores_al_cambio_sin_sv_siguen_validos_hasta_un_restablecimiento

  @BDD-RECUPERACION @invariante @INV-016
  Escenario: Una falla de la base de datos no cierra la sesión
    Dado que Supabase no responde
    Cuando se usa una sesión válida
    Entonces se responde 503 y no 401
    # Prueba: backend/tests/test_sesiones.py::test_inv016_si_la_bd_falla_se_responde_503_y_no_se_cierra_la_sesion
