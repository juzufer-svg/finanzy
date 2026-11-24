# language: es
# Trazabilidad: REQ-F-002 · REQ-F-003 · REQ-N-002 · UC-002 · UC-003 · CT-001 · INV-037 a INV-041 (y INV-007, INV-009, INV-010, INV-013 aclaradas) · ADR-010
# Pruebas: backend/tests/test_auth_persistente.py (el almacén de pruebas imita las funciones SQL) y backend/sql/pruebas/07_comprobar_auth_persistente.sql + probar.sh (atomicidad y concurrencia reales en PostgreSQL).
Característica: Bloqueos, códigos y límites de login persistentes

  @BDD-AUTH-PERSISTENTE @happy-path @INV-037
  # Prueba: tests/test_auth_persistente.py::test_inv037_bloqueo_de_login_sobrevive_a_un_reinicio
  Escenario: Un despliegue no desbloquea un correo
    Dado un correo con 5 fallos de login y bloqueado 15 minutos
    Cuando el backend se reinicia (se descarta todo el estado en memoria)
    Y se intenta iniciar sesión con ese correo con la contraseña correcta
    Entonces recibe 429 "Demasiados intentos fallidos"
    Y pasados los 15 minutos el inicio de sesión correcto funciona

  @BDD-AUTH-PERSISTENTE @invariante @INV-037
  # Prueba: tests/test_auth_persistente.py::test_inv037_codigo_vigente_sobrevive_a_un_reinicio
  Escenario: Un código vigente se puede usar después de un reinicio
    Dado un código de verificación emitido hace 2 minutos
    Cuando el backend se reinicia
    Y la persona ingresa el código correcto
    Entonces la cuenta se activa y el código queda usado

  @BDD-AUTH-PERSISTENTE @invariante @INV-037
  # Prueba: tests/test_auth_persistente.py::test_inv037_ventanas_de_envio_sobreviven_a_un_reinicio
  Escenario: Los topes de envío y de intentos no se reinician con el backend
    Dado 10 correos enviados hoy a un destinatario, 250 en total, 10 pedidos de código de una IP en la hora y 30 intentos de una IP en 10 minutos
    Cuando el backend se reinicia y se pide otro
    Entonces se rechaza igual que antes del reinicio (INV-010)

  @BDD-AUTH-PERSISTENTE @invariante @INV-037
  # Prueba: tests/test_auth_persistente.py::test_inv037_las_ventanas_siguen_siendo_deslizantes_con_los_mismos_numeros
  Escenario: Los números de INV-010 no cambian
    Cuando se agotan, uno por uno, los seis límites de INV-010
    Entonces cada uno rechaza exactamente en el mismo número que antes (5 fallos, 60 s, 10/día, 10/hora por IP, 250/día, 30 por 10 min)

  @BDD-AUTH-PERSISTENTE @invariante @INV-037
  # Prueba: tests/test_auth_persistente.py::test_inv037_los_5_fallos_se_cuentan_en_una_ventana_de_15_minutos
  Escenario: Cuatro fallos viejos no acumulan con uno nuevo
    Dado 4 fallos de login hace más de 15 minutos
    Cuando falla un quinto intento hoy
    Entonces no hay bloqueo y el contador vuelve a empezar en 1

  @BDD-AUTH-PERSISTENTE @invariante @INV-038
  # Prueba: tests/test_auth_persistente.py::test_inv038_login_paralelo_no_comprueba_mas_de_5_contrasenas
  # Prueba real: backend/sql/pruebas/probar.sh (6 reservas simultáneas → 5 permitidas) y 07_comprobar_auth_persistente.sql
  Escenario: 50 intentos simultáneos no esquivan el bloqueo
    Dado un correo sin fallos previos
    Cuando llegan 50 inicios de sesión simultáneos con contraseña incorrecta
    Entonces como mucho 5 llegan a comprobar la contraseña (401) y el resto recibe 429
    Y el correo queda bloqueado 15 minutos

  @BDD-AUTH-PERSISTENTE @invariante @INV-038
  # Prueba: tests/test_auth_persistente.py::test_inv038_codigo_paralelo_se_consume_una_sola_vez
  # Prueba real: backend/sql/pruebas/probar.sh (dos sesiones verifican el mismo código)
  Escenario: Un código no se puede usar dos veces a la vez
    Dado un código vigente
    Cuando dos peticiones simultáneas envían el código correcto
    Entonces solo una lo consume (200) y la otra recibe 400 "Código inválido o expirado" (INV-007)

  @BDD-AUTH-PERSISTENTE @invariante @INV-038
  # Prueba: tests/test_auth_persistente.py::test_inv038_intentos_de_codigo_paralelos_no_pasan_de_5
  Escenario: Adivinar un código en paralelo no da más de 5 intentos
    Dado un código vigente
    Cuando llegan 40 verificaciones simultáneas con códigos incorrectos
    Entonces se evalúan como mucho 5, el código queda invalidado y ni siquiera el valor correcto lo activa después (INV-007)

  @BDD-AUTH-PERSISTENTE @invariante @INV-038
  # Prueba: tests/test_auth_persistente.py::test_inv038_limite_de_correos_paralelo_no_pasa_del_tope
  Escenario: Pedidos de código simultáneos respetan el tope diario por destinatario
    Dado 9 correos ya enviados hoy a un destinatario
    Cuando llegan 5 pedidos simultáneos para ese destinatario
    Entonces solo 1 se envía y los otros 4 reciben el rechazo silencioso o 429 según el endpoint (INV-009, INV-010)

  @BDD-AUTH-PERSISTENTE @invariante @INV-039
  # Prueba: tests/test_auth_persistente.py::test_inv039_bd_caida_responde_503_en_todas_las_rutas_de_autenticacion
  Escenario: Si la BD de estado falla, el login responde error (fail-closed)
    Dado que la BD de estado no responde
    Cuando se llama a login, register, verify-email, resend-code, forgot-password, reset-password o change-password
    Entonces cada una responde 503 "Servicio no disponible. Intenta de nuevo en unos minutos."
    Y nunca 200, 401, 400 ni 404, y no se concede ninguna sesión

  @BDD-AUTH-PERSISTENTE @invariante @INV-039
  # Prueba: tests/test_auth_persistente.py::test_inv039_fallo_del_limite_por_ip_responde_503_no_deja_pasar
  Escenario: Si falla el límite por IP tampoco se deja pasar
    Dado que la BD de estado falla solo al contar los intentos por IP
    Cuando se inicia sesión con credenciales correctas
    Entonces la respuesta es 503 y no hay sesión

  @BDD-AUTH-PERSISTENTE @invariante @INV-039
  # Prueba: tests/test_auth_persistente.py::test_inv039_operacion_de_estado_lenta_responde_503_en_5s
  Escenario: Una BD de estado lenta no cuelga el login
    Dado que la BD de estado tarda más de 5 segundos
    Cuando se inicia sesión
    Entonces responde 503 en menos de 6 segundos

  @BDD-AUTH-PERSISTENTE @invariante @INV-039
  # Prueba: tests/test_auth_persistente.py::test_inv039_el_503_no_depende_de_si_la_cuenta_existe
  Escenario: El fallo no permite saber qué correos existen
    Dado que la BD de estado falla
    Cuando se pide forgot-password o resend-code para un correo registrado y para uno que no lo está
    Entonces ambas respuestas son idénticas (503, mismo cuerpo)

  @BDD-AUTH-PERSISTENTE @invariante @INV-009
  # Prueba: tests/test_auth_persistente.py::test_inv009_forgot_password_hace_las_mismas_llamadas_a_la_bd_exista_o_no
  Escenario: Pedir un código no revela si la cuenta existe
    Dado un correo registrado y otro que no lo está
    Cuando se pide forgot-password y resend-code para cada uno
    Entonces la respuesta es idéntica y la secuencia de llamadas a la BD de estado es la misma (el código de la cuenta inexistente es un señuelo que no se envía)

  @BDD-AUTH-PERSISTENTE @invariante @INV-041
  # Prueba: tests/test_auth_persistente.py::test_inv041_en_produccion_sin_supabase_no_se_usa_memoria
  Escenario: En producción sin Supabase no se guarda estado en memoria
    Dado ENVIRONMENT=production y sin Supabase configurado
    Cuando se inicia sesión o se pide un código
    Entonces responde 503 y no queda ningún bloqueo ni código en memoria

  @BDD-AUTH-PERSISTENTE @invariante @INV-041
  # Prueba: tests/test_auth_persistente.py::test_inv041_con_supabase_configurado_no_queda_estado_en_memoria
  Escenario: Con Supabase configurado no hay copia en memoria
    Dado Supabase configurado
    Cuando fallan 5 inicios de sesión y se emite un código
    Entonces los diccionarios y limitadores de memoria de autenticación están vacíos (INV-013)

  @BDD-AUTH-PERSISTENTE @invariante @INV-041
  # Prueba: tests/test_auth_persistente.py::test_inv041_modo_demo_fuera_de_produccion_sigue_funcionando
  Escenario: El modo demo local sigue funcionando
    Dado ENVIRONMENT=development y sin Supabase
    Cuando se usa el registro, el login y los códigos
    Entonces funcionan en memoria como hoy (las pruebas existentes de test_auth.py y test_codigos.py siguen pasando)

  @BDD-AUTH-PERSISTENTE @invariante @INV-040
  # Prueba: tests/test_auth_persistente.py::test_inv040_las_claves_son_huellas_hmac_no_el_correo_ni_la_ip
  Escenario: Correo e IP no se guardan en claro
    Cuando se registran fallos, códigos y eventos de límite para "ana@correo.com" desde la IP "203.0.113.7"
    Entonces ningún valor enviado a la BD contiene ese correo ni esa IP, solo huellas HMAC de 64 caracteres hexadecimales

  @BDD-AUTH-PERSISTENTE @invariante @INV-040
  # Prueba: tests/test_auth_persistente.py::test_inv040_el_codigo_se_guarda_solo_como_hmac
  Escenario: El código no se guarda en claro
    Cuando se emite el código "482913"
    Entonces lo enviado a la BD no contiene "482913" y la verificación sigue funcionando

  @BDD-AUTH-PERSISTENTE @invariante @INV-040
  # Prueba: tests/test_auth_persistente.py::test_inv040_nada_sensible_en_logs_ni_en_errores
  Escenario: Los fallos no filtran datos
    Dado que la BD de estado falla con un mensaje que incluye el correo
    Cuando se inicia sesión
    Entonces ni la respuesta ni los logs contienen el correo, la IP ni el código

  @BDD-AUTH-PERSISTENTE @invariante @INV-040
  # Prueba: tests/test_auth_persistente.py::test_inv040_eliminar_cuenta_borra_intentos_y_codigos
  Escenario: Al eliminar la cuenta se borran sus intentos y códigos
    Dado un usuario con fallos de login y un código pendiente
    Cuando elimina su cuenta
    Entonces no queda ninguna fila de intentos ni de códigos de su correo (REQ-F-013 CA-2)

  @BDD-AUTH-PERSISTENTE @invariante @INV-040
  # Prueba: tests/test_auth_persistente.py::test_inv040_si_falla_la_limpieza_la_baja_no_se_revierte
  Escenario: Un fallo al limpiar no deshace la baja
    Dado que la limpieza del estado de autenticación falla
    Cuando el usuario elimina su cuenta
    Entonces la baja se completa y solo se registra un aviso sin datos personales

  @BDD-AUTH-PERSISTENTE @invariante @INV-040
  # Prueba: tests/test_auth_persistente.py::test_inv040_purga_a_30_dias_una_vez_al_dia
  # Prueba real: backend/sql/pruebas/07_comprobar_auth_persistente.sql
  Escenario: Las filas de más de 30 días se purgan
    Dado filas de intentos, códigos y eventos de hace 31 días y de hace 29 días
    Cuando se escribe un código nuevo
    Entonces se borran las de 31 días y se conservan las de 29, y no se vuelve a purgar el mismo día aunque haya varias instancias

  @BDD-AUTH-PERSISTENTE @invariante @INV-040
  # Prueba real: backend/sql/pruebas/07_comprobar_auth_persistente.sql
  Escenario: Las tablas no son accesibles desde fuera del backend
    Cuando se revisan las tres tablas y las funciones en PostgreSQL
    Entonces tienen RLS activado, ninguna política, sin permisos para anon ni authenticated, y las funciones solo se ejecutan con service_role

  @BDD-AUTH-PERSISTENTE @borde @INV-007
  # Prueba: tests/test_auth_persistente.py::test_inv007_codigos_de_verificacion_y_reset_siguen_sin_ser_intercambiables
  Escenario: Verificación y restablecimiento siguen separados
    Dado un código de restablecimiento vigente para un correo
    Cuando se usa como código de verificación de ese mismo correo
    Entonces se rechaza con 400

  @BDD-AUTH-PERSISTENTE @borde @INV-010
  # Prueba: tests/test_auth_persistente.py::test_inv010_el_login_correcto_reinicia_los_fallos_y_el_restablecimiento_desbloquea
  Escenario: Iniciar sesión bien o cambiar la contraseña reinicia el contador
    Dado 4 fallos de login
    Cuando la persona inicia sesión correctamente
    Entonces el contador vuelve a 0

  @BDD-AUTH-PERSISTENTE @borde @INV-027
  # Prueba: tests/test_auth_persistente.py::test_inv027_change_password_usa_el_bloqueo_persistente
  Escenario: La contraseña actual mala en el perfil cuenta en el bloqueo persistente
    Dado 4 fallos de login del correo
    Cuando la persona se equivoca de contraseña actual en el perfil
    Entonces el correo queda bloqueado 15 minutos también tras un reinicio

  @BDD-AUTH-PERSISTENTE @borde @REQ-N-017
  # Prueba: tests/test_auth_persistente.py::test_req_n017_llamadas_a_la_bd_por_operacion
  Escenario: Pocas llamadas extra por operación
    Cuando se hace un inicio de sesión, una verificación de código y un pedido de código
    Entonces el login usa como mucho 3 llamadas a la BD de estado, la verificación 2 y el pedido de código 6
