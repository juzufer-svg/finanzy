# language: es
# Trazabilidad: REQ-F-002 · REQ-F-003 · REQ-N-002 · REQ-N-016 a REQ-N-018 · UC-002 · UC-003 · CT-001 · INV-037 a INV-041 (y INV-007, INV-009, INV-010, INV-013 aclaradas) · ADR-010
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
  # Prueba: tests/test_auth_persistente.py::test_inv037_cinco_fallos_repartidos_en_menos_de_24_horas_bloquean
  Escenario: Cinco fallos repartidos en el día sí bloquean
    Dado un correo con un fallo a las 08:00, otros a las 12:00, 16:00 y 20:00 (todos dentro de 24 horas desde el primero)
    Cuando falla un quinto intento a las 23:00
    Entonces el correo queda bloqueado 15 minutos contados desde ese quinto intento

  @BDD-AUTH-PERSISTENTE @invariante @INV-037
  # Prueba: tests/test_auth_persistente.py::test_inv037_fallos_de_mas_de_24_horas_no_acumulan_con_uno_nuevo
  Escenario: Cuatro fallos de hace más de 24 horas no acumulan con uno nuevo
    Dado 4 fallos de login hace más de 24 horas
    Cuando falla un quinto intento hoy
    Entonces no hay bloqueo y la serie vuelve a empezar en 1 (precisión de INV-010: la serie caduca a las 24 horas del primer fallo)

  @BDD-AUTH-PERSISTENTE @invariante @INV-038
  # Prueba: tests/test_auth_persistente.py::test_inv038_login_paralelo_no_comprueba_mas_de_5_contrasenas
  # Prueba real: backend/sql/pruebas/probar.sh (6 reservas simultáneas → 5 permitidas) y 07_comprobar_auth_persistente.sql
  Escenario: 50 intentos simultáneos no esquivan el bloqueo
    Dado un correo sin fallos previos
    Cuando llegan 50 inicios de sesión simultáneos con contraseña incorrecta, cada uno desde una IP distinta (para que el límite por IP no pueda ser el origen de ningún 429)
    Entonces como mucho 5 llegan a comprobar la contraseña (401) y los otros 45 reciben 429 «Demasiados intentos fallidos» por el bloqueo del correo
    Y el correo queda bloqueado 15 minutos

  @BDD-AUTH-PERSISTENTE @invariante @INV-038
  # Prueba: tests/test_auth_persistente.py::test_inv038_login_paralelo_desde_una_ip_distingue_el_429_por_ip_y_por_correo
  Escenario: Desde una sola IP cada 429 dice de qué límite viene
    Dado un correo sin fallos previos y 50 inicios de sesión simultáneos con contraseña incorrecta desde la misma IP
    Cuando se cuentan las respuestas
    Entonces 30 pasan el límite por IP (5 reciben 401 y 25 reciben 429 «Demasiados intentos fallidos» del correo) y los 20 restantes reciben 429 «Demasiadas solicitudes» del límite por IP

  @BDD-AUTH-PERSISTENTE @invariante @INV-038
  # Prueba: tests/test_auth_persistente.py::test_inv038_la_quinta_reserva_que_acierta_inicia_sesion_y_no_deja_bloqueado
  # Prueba real: backend/sql/pruebas/probar.sh (la 5.ª reserva con contraseña correcta)
  Escenario: Si la 5.ª reserva acierta, la persona entra
    Dado un correo con 4 intentos reservados que ya fallaron
    Cuando la 5.ª reserva comprueba una contraseña correcta
    Entonces recibe sesión (200), el intento se le devuelve y el bloqueo que fijó su propia reserva se levanta
    Y, si no hay otras reservas en vuelo, la serie se borra (comportamiento real: el desbloqueo visible es el mismo, la persona puede volver a entrar y la serie empieza de cero); si hay otras reservas en vuelo, el correo queda con 4 fallos, no bloqueado, y la serie se conserva

  @BDD-AUTH-PERSISTENTE @invariante @INV-038
  # Prueba: tests/test_auth_persistente.py::test_inv038_devolver_el_intento_no_borra_los_fallos_en_vuelo
  # Prueba real: backend/sql/pruebas/07_comprobar_auth_persistente.sql
  Escenario: Un login correcto no borra los fallos de peticiones en vuelo
    Dado 3 peticiones con contraseña incorrecta ya reservadas y todavía comprobándose, y una cuarta con la contraseña correcta
    Cuando la cuarta se resuelve con acierto
    Entonces se le devuelve solo su intento: los 3 fallos en vuelo siguen contados y la serie no se borra

  @BDD-AUTH-PERSISTENTE @invariante @INV-038
  # Prueba: tests/test_auth_persistente.py::test_inv038_login_correcto_sin_reservas_en_vuelo_borra_la_serie
  Escenario: Un login correcto sin nada en vuelo reinicia la serie
    Dado un correo con 3 fallos ya resueltos y ninguna reserva en vuelo
    Cuando la persona inicia sesión correctamente
    Entonces el contador vuelve a 0

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
  # Prueba real: backend/sql/pruebas/probar.sh (15 emisiones simultáneas con p_espacio_seg = 0 a un destinatario con 5 eventos → 5 enviadas y 10 limitadas)
  Escenario: Pedidos de código simultáneos respetan el tope diario por destinatario
    Dado 9 correos ya enviados hoy a un destinatario (hace más de 60 segundos)
    Cuando llegan 5 pedidos simultáneos para ese destinatario
    Entonces solo 1 se envía y los otros 4 reciben «reciente» (60 s) o el rechazo silencioso o 429 según el endpoint (INV-009, INV-010)

  @BDD-AUTH-PERSISTENTE @invariante @INV-038
  # Prueba: tests/test_auth_persistente.py::test_inv038_emitir_codigo_es_una_sola_operacion_atomica_y_respeta_los_60s_en_paralelo
  # Prueba real: backend/sql/pruebas/probar.sh (10 emisiones simultáneas al mismo correo → 1 enviado y 9 reciente)
  Escenario: Los 60 segundos y los topes se comprueban en una sola operación
    Dado un correo sin códigos recientes
    Cuando llegan 10 pedidos simultáneos para ese correo
    Entonces el backend hace UNA llamada a la BD por pedido (no «comprobar» y luego «guardar»), exactamente 1 se envía y los otros 9 reciben «reciente»

  @BDD-AUTH-PERSISTENTE @invariante @INV-038
  # Prueba: tests/test_auth_persistente.py::test_inv038_las_ventanas_usan_el_reloj_de_la_bd_y_el_backend_nunca_envia_la_hora
  Escenario: Las ventanas usan el reloj de la BD
    Dado dos instancias del backend con relojes distintos
    Cuando cada una registra intentos, códigos y eventos
    Entonces el backend nunca envía una hora a las funciones SQL y las ventanas se miden con now() de la BD

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
  # Prueba: tests/test_auth_persistente.py::test_inv039_falla_solo_la_tabla_de_usuarios_responde_503
  Escenario: Si falla solo la tabla de usuarios tampoco se deja pasar ni se confunde con «no existe»
    Dado que el estado de autenticación funciona pero la lectura de la tabla de usuarios falla (get_by_email_estricto lanza)
    Cuando se llama a login (con contraseña correcta), forgot-password, resend-code, register, verify-email (con el código correcto) y reset-password (con el código correcto)
    Entonces cada una responde 503, nunca 401, 200 ni 404, no se crea ninguna cuenta y los códigos correctos no se consumen

  @BDD-AUTH-PERSISTENTE @invariante @INV-039
  # Prueba: tests/test_auth_persistente.py::test_inv039_operacion_de_estado_lenta_responde_503_en_5s
  Escenario: Una BD de estado lenta no cuelga el login
    Dado que la BD de estado tarda más de 5 segundos
    Cuando se inicia sesión
    Entonces responde 503 en menos de 6 segundos

  @BDD-AUTH-PERSISTENTE @invariante @INV-039
  # Prueba: tests/test_auth_persistente.py::test_inv039_el_plazo_se_impone_en_cada_llamada_al_cliente_de_la_bd
  Escenario: El plazo se impone en el cliente, no solo alrededor del hilo
    Dado que una llamada a la BD de estado se queda colgada
    Cuando se agota su plazo
    Entonces el cliente de la BD de estado fue creado con un plazo de 4 segundos o menos, la llamada termina por el plazo del propio cliente y su hilo queda libre (no se acumulan hilos colgados)

  @BDD-AUTH-PERSISTENTE @invariante @INV-039
  # Prueba: tests/test_auth_persistente.py::test_inv039_ejecutor_de_estado_agotado_responde_503_sin_encolar
  Escenario: Si no hay hilos libres para el estado, se responde 503 enseguida
    Dado que los 8 hilos del ejecutor de estado están ocupados con llamadas lentas
    Cuando llega otra petición de login
    Entonces responde 503 de inmediato sin esperar en cola

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
    Cuando se pide forgot-password para cada uno
    Entonces la respuesta es idéntica y la secuencia de llamadas a la BD de estado es la misma (el código de la cuenta inexistente es un señuelo que no se envía)

  @BDD-AUTH-PERSISTENTE @invariante @INV-009
  # Prueba: tests/test_auth_persistente.py::test_inv009_resend_code_responde_y_cuenta_igual_en_pendiente_activa_e_inexistente
  Escenario: Reenviar un código no revela qué cuentas están pendientes
    Dado un correo con cuenta pendiente, otro con cuenta activa y otro inexistente
    Cuando se pide resend-code para cada uno, antes y después de alcanzar el tope diario de 10 correos del destinatario y el global de 250
    Entonces las tres respuestas son idénticas (200 antes del tope y el mismo 429 «Ya enviamos varios códigos…» al alcanzarlo), la secuencia de llamadas a la BD es la misma y solo la cuenta pendiente recibe un correo; el señuelo también consume el espacio de 60 s y los topes

  @BDD-AUTH-PERSISTENTE @invariante @INV-009
  # Prueba: tests/test_auth_persistente.py::test_inv009_login_con_correo_inexistente_verifica_contra_un_hash_senuelo
  Escenario: El login tarda lo mismo exista o no el correo
    Dado un correo inexistente y otro registrado
    Cuando se inicia sesión con una contraseña incorrecta en cada uno
    Entonces en ambos casos se ejecuta una comprobación bcrypt (contra el hash real o contra un hash señuelo del mismo costo), ambos responden 401 «Credenciales inválidas» y ambos cuentan como fallo

  @BDD-AUTH-PERSISTENTE @invariante @INV-039
  # Prueba: tests/test_auth_persistente.py::test_inv039_el_codigo_senuelo_no_puede_verificarse
  Escenario: Un código señuelo nunca abre una sesión
    Dado un correo de una cuenta ya activa al que se pidió resend-code (se guardó un código señuelo)
    Cuando se prueban en verify-email los 1 000 000 de valores de 6 dígitos posibles (o una muestra amplia en la prueba)
    Entonces ninguno es aceptado y no se emite ninguna sesión

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
    Entonces los diccionarios y limitadores de memoria de autenticación están vacíos (INV-013, solo en su alcance: login, registro, verificación y recuperación; el asistente, WhatsApp y el Monitor siguen en memoria, BL-040)

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
    Entonces no queda ninguna fila de intentos ni de códigos de su correo (REQ-F-013 CA-2) y las huellas de límites expiran con su purga (hasta 2 días)

  @BDD-AUTH-PERSISTENTE @invariante @INV-040
  # Prueba: tests/test_auth_persistente.py::test_inv040_si_falla_la_limpieza_la_baja_no_se_revierte
  Escenario: Un fallo al limpiar no deshace la baja
    Dado que la limpieza del estado de autenticación falla
    Cuando el usuario elimina su cuenta
    Entonces la baja se completa y solo se registra un aviso sin datos personales

  @BDD-AUTH-PERSISTENTE @invariante @INV-040
  # Prueba: tests/test_auth_persistente.py::test_inv040_purga_30_dias_intentos_y_codigos_y_2_dias_eventos_una_vez_al_dia
  # Prueba real: backend/sql/pruebas/07_comprobar_auth_persistente.sql
  Escenario: Se purga lo viejo, una vez al día
    Dado filas de intentos y códigos de hace 31 y 29 días, y eventos de límites de hace 3 días y de hace 1 día
    Cuando se emite un código nuevo
    Entonces se borran los intentos y códigos de 31 días y los eventos de 3 días, se conservan los demás, la marca de última purga es la fila «purga» de auth_limites_eventos y no se vuelve a purgar el mismo día aunque haya varias instancias

  @BDD-AUTH-PERSISTENTE @invariante @INV-040
  # Prueba: tests/test_auth_persistente.py::test_inv040_tope_de_filas_de_eventos_con_ip_falsificada_responde_429
  # Prueba real: backend/sql/pruebas/07_comprobar_auth_persistente.sql
  Escenario: Una IP falsificada no hace crecer la tabla sin límite
    Dado un atacante que llama directo al backend con una X-Forwarded-For distinta en cada petición
    Cuando la tabla de eventos llega a 500 000 filas
    Entonces los límites por IP responden 429 «Demasiadas solicitudes», se registra un aviso sin datos personales y no se insertan más filas hasta que expiren las existentes

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
  Escenario: Iniciar sesión bien o restablecer la contraseña reinicia el contador, también si otra persona bloqueó el correo
    Dado 4 fallos de login (o 5: correo bloqueado por otra persona)
    Cuando la persona inicia sesión correctamente (4 fallos) o restablece su contraseña con el código del correo (bloqueado)
    Entonces el contador vuelve a 0 y el correo queda desbloqueado (riesgo aceptado M-6: cualquiera puede bloquear un correo 15 min; restablecer lo desbloquea)

  @BDD-AUTH-PERSISTENTE @borde @INV-027
  # Prueba: tests/test_auth_persistente.py::test_inv027_change_password_usa_el_bloqueo_persistente
  Escenario: La contraseña actual mala en el perfil cuenta en el bloqueo persistente
    Dado 4 fallos de login del correo
    Cuando la persona se equivoca de contraseña actual en el perfil
    Entonces el correo queda bloqueado 15 minutos también tras un reinicio

  @BDD-AUTH-PERSISTENTE @borde @REQ-N-017
  # Prueba: tests/test_auth_persistente.py::test_req_n017_llamadas_a_la_bd_por_operacion
  Escenario: Pocas llamadas por operación
    Cuando se hace un inicio de sesión (con cuenta activa, con cuenta pendiente, con contraseña incorrecta y bloqueado), una verificación de código, un restablecimiento y un pedido de código
    Entonces el login usa como mucho 3 llamadas a la BD de estado (4 si la cuenta está pendiente y emite código; 2 si el correo está bloqueado), la verificación 2, el restablecimiento 3 y el pedido de código 2
