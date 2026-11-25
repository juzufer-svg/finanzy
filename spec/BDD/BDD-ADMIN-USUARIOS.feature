# language: es
# Trazabilidad: REQ-F-021 · UC-017 · CT-013 · CT-001 (login 403) · INV-053 a INV-062 · CHG-023 (provisional)
# Pruebas: backend/tests/test_admin_usuarios.py, backend/tests/test_admin_suspension.py, backend/sql/pruebas/11_comprobar_admin_usuarios.sql
# y frontend/tests/admin-usuarios.test.mjs. Los nombres completos de cada grupo de pruebas están en INV-053 a INV-062 (fuente única).
Característica: Administración de usuarios solo para el Dueño

  @BDD-ADMIN @happy-path @INV-059
  # Prueba: tests/test_admin_usuarios.py::test_inv059_cada_accion_exitosa_deja_un_registro
  Escenario: El Dueño ve la lista y sus acciones quedan registradas
    Dado un Dueño con sesión y tres usuarios registrados
    Cuando pide "GET /api/v1/admin/usuarios"
    Entonces recibe 200 con "Cache-Control: no-store", los tres usuarios, 25 por página y el total
    Y al suspender, reactivar, cerrar sesiones y eliminar a un usuario cada acción deja un registro en la auditoría

  @BDD-ADMIN @invariante @INV-053
  # Prueba: tests/test_admin_usuarios.py::test_inv053_no_dueno_recibe_404_identico_a_ruta_inexistente
  Escenario: Otro usuario recibe 404 sin pistas en todas las rutas
    Dado un usuario con sesión válida que no es el Dueño
    Cuando pide cualquiera de las siete rutas de "/api/v1/admin" con su método
    Entonces recibe 404 byte a byte idéntico (cuerpo y cabeceras, salvo "Date") al de "GET /api/v1/no-existe"
    Y ninguno lleva "Cache-Control: no-store"

  @BDD-ADMIN @invariante @INV-053
  # Prueba: tests/test_admin_usuarios.py::test_inv053_sin_sesion_recibe_404
  Escenario: Sin sesión también recibe 404
    Cuando una persona sin sesión pide "GET /api/v1/admin/usuarios"
    Entonces recibe 404 y no 401, idéntico al de una ruta inexistente

  @BDD-ADMIN @invariante @INV-053
  # Prueba: tests/test_admin_usuarios.py::test_inv053_sin_owner_email_responde_404_y_no_mira_la_sesion
  Escenario: Sin OWNER_EMAIL se niega a todos
    Dado que OWNER_EMAIL está vacía o no existe
    Cuando el Dueño habitual pide la lista
    Entonces recibe 404 sin que se lea al usuario en la BD

  @BDD-ADMIN @invariante @INV-053
  # Prueba: tests/test_admin_usuarios.py::test_inv053_bd_caida_al_autorizar_responde_404
  Escenario: Si la BD falla al autorizar, se niega con 404 y no con 503
    Dado que la base de datos falla al verificar la sesión
    Cuando cualquier persona, incluido el Dueño habitual, pide la lista
    Entonces recibe 404 idéntico al de una ruta inexistente y no 503

  @BDD-ADMIN @invariante @INV-053
  # Prueba: tests/test_admin_usuarios.py::test_inv053_no_dueno_con_parametros_invalidos_recibe_404_y_no_422
  Escenario: Un no-Dueño con parámetros inválidos no recibe 422
    Dado un usuario que no es el Dueño
    Cuando pide "/api/v1/admin/usuarios?q=<61 caracteres>", "?pagina=abc", "/api/v1/admin/usuarios/no-es-uuid" o un DELETE sin cuerpo
    Entonces recibe siempre el mismo 404 y nunca 422

  @BDD-ADMIN @invariante @INV-053
  # Prueba: tests/test_admin_usuarios.py::test_inv053_no_dueno_con_cualquier_metodo_recibe_404 y ::test_inv053_dueno_con_metodo_no_permitido_recibe_405_con_allow_y_no_store
  Escenario: Solo GET, POST y DELETE; el resto no revela nada
    Cuando un no-Dueño envía PUT, PATCH, HEAD, TRACE, PROPFIND u OPTIONS sin "Origin" a una ruta de administración
    Entonces recibe el 404 idéntico al de una ruta inexistente
    Pero el Dueño recibe 405 con "Allow" y "Cache-Control: no-store"

  @BDD-ADMIN @invariante @INV-053
  # Prueba: tests/test_admin_usuarios.py::test_inv053_429_y_503_solo_despues_de_confirmar_al_dueno
  Escenario: El 429 y el 503 solo existen para el Dueño ya confirmado
    Dado que la BD falla al leer la lista y el límite está superado
    Cuando el Dueño pide la lista recibe 429 o 503 con "Cache-Control: no-store"
    Pero un no-Dueño, en la misma situación, recibe el 404

  @BDD-ADMIN @invariante @INV-054
  # Prueba: tests/test_admin_usuarios.py::test_inv054_el_dueno_no_puede_suspenderse y ::test_inv054_el_dueno_no_puede_eliminarse
  Escenario: El Dueño no puede suspenderse ni eliminarse a sí mismo
    Dado el Dueño con sesión
    Cuando intenta suspender, eliminar o cerrar las sesiones de su propia cuenta
    Entonces recibe 409 y no se cambia ni se audita nada

  @BDD-ADMIN @invariante @INV-054
  # Prueba: tests/test_admin_usuarios.py::test_inv054_la_lista_no_expone_el_id_de_la_cuenta_del_dueno
  Escenario: La lista no expone el id del administrador
    Cuando el Dueño pide la lista
    Entonces su propia fila trae "id" nulo, "es_dueno" verdadero y ninguna acción disponible

  @BDD-ADMIN @invariante @INV-055
  # Prueba: tests/test_admin_usuarios.py::test_inv055_ninguna_respuesta_incluye_hashed_password y ::test_inv055_no_se_exponen_montos_descripciones_ni_categorias
  Escenario: Ninguna respuesta trae la contraseña ni datos financieros
    Dado un usuario con transacciones, categorías y metas con textos y montos reconocibles
    Cuando el Dueño pide la lista, el detalle, una acción y la auditoría
    Entonces ninguna respuesta incluye "hashed_password", "session_version", montos, descripciones ni nombres de categorías
    Y del uso solo salen conteos enteros y si tiene WhatsApp conectado

  @BDD-ADMIN @invariante @INV-055
  # Prueba: tests/test_admin_usuarios.py::test_inv055_respuestas_solo_con_claves_de_lista_blanca
  Escenario: Lo que entregue la BD de más se descarta
    Dado una BD simulada que devuelve claves y tipos extra
    Cuando el Dueño pide la lista
    Entonces la respuesta solo contiene las claves de la lista blanca de CT-013

  @BDD-ADMIN @invariante @INV-056
  # Prueba: tests/test_admin_suspension.py::test_inv056_login_de_suspendida_con_contrasena_correcta_responde_403_generico
  Escenario: La persona suspendida no puede iniciar sesión
    Dado un usuario suspendido
    Cuando inicia sesión con su contraseña correcta
    Entonces recibe 403 con un mensaje genérico, sin token ni código

  @BDD-ADMIN @invariante @INV-056
  # Prueba: tests/test_admin_suspension.py::test_inv056_login_de_suspendida_con_contrasena_incorrecta_responde_401_igual_que_siempre
  Escenario: Con la contraseña incorrecta no se revela el estado
    Dado un usuario suspendido
    Cuando inicia sesión con una contraseña incorrecta
    Entonces recibe el 401 «Credenciales inválidas» de siempre y cuenta como fallo

  @BDD-ADMIN @invariante @INV-056
  # Prueba: tests/test_admin_suspension.py::test_inv056_sesion_abierta_de_suspendida_recibe_401 y ::test_inv056_suspender_marca_suspendida_y_sube_session_version_juntas
  Escenario: Las sesiones abiertas dejan de valer al suspender
    Dado un usuario con una sesión abierta
    Cuando el Dueño lo suspende
    Entonces su siguiente petición recibe 401 «Tu sesión ya no es válida»
    Y la versión de sesión subió y "suspendida" quedó marcada en la misma operación

  @BDD-ADMIN @invariante @INV-056
  # Prueba: tests/test_admin_suspension.py::test_inv056_reactivar_permite_login_pero_no_revive_tokens_viejos y ::test_inv056_reset_password_no_reactiva_a_la_suspendida
  Escenario: Reactivar no revive sesiones y restablecer la contraseña no reactiva
    Dado un usuario suspendido con un token anterior
    Cuando restablece su contraseña sigue suspendido
    Y cuando el Dueño lo reactiva puede iniciar sesión, pero el token anterior sigue dando 401

  @BDD-ADMIN @invariante @INV-056
  # Prueba: tests/test_admin_suspension.py::test_inv056_la_limpieza_de_cuentas_sin_verificar_no_toca_a_las_suspendidas
  Escenario: La limpieza de cuentas sin verificar no borra a los suspendidos
    Dado un usuario activo y suspendido creado hace más de una hora
    Cuando corre la limpieza de cuentas sin verificar
    Entonces el usuario sigue existiendo

  @BDD-ADMIN @invariante @INV-056
  # Prueba: tests/test_admin_suspension.py::test_inv056_suspender_dos_veces_responde_409_y_audita_una_sola_vez
  Escenario: Suspender dos veces
    Dado un usuario ya suspendido
    Cuando el Dueño lo suspende otra vez
    Entonces recibe 409 y no se crea un segundo registro de auditoría

  @BDD-ADMIN @invariante @INV-057
  # Prueba: tests/test_admin_suspension.py::test_inv057_cerrar_sesiones_sube_session_version_en_uno y ::test_inv057_el_token_anterior_recibe_401_y_el_login_nuevo_funciona
  Escenario: Cerrar sesiones
    Dado un usuario con la versión de sesión 3 y un token vigente
    Cuando el Dueño cierra sus sesiones
    Entonces la versión es 4, el token anterior recibe 401 y un inicio de sesión nuevo funciona

  @BDD-ADMIN @invariante @INV-058
  # Prueba: tests/test_admin_usuarios.py::test_inv058_eliminar_sin_confirmar_correo_responde_422_y_no_borra y ::test_inv058_correo_distinto_responde_422
  Escenario: Eliminar exige escribir el correo
    Dado un usuario con datos
    Cuando el Dueño envía DELETE sin "confirmar_correo" o con otro correo
    Entonces recibe 422 y no se borra nada

  @BDD-ADMIN @invariante @INV-058
  # Prueba: tests/test_admin_usuarios.py::test_inv058_eliminar_borra_la_cuenta_con_cascada_y_llama_a_borrar_de_cuenta
  Escenario: Eliminar reutiliza la baja de la cuenta
    Dado un usuario con datos y WhatsApp conectado
    Cuando el Dueño lo elimina escribiendo su correo (con mayúsculas y espacios)
    Entonces recibe 204, la cuenta y todos sus datos desaparecen y se limpian sus intentos y códigos
    Y queda un registro "eliminar" con su id y sin datos personales

  @BDD-ADMIN @invariante @INV-058
  # Prueba: tests/test_admin_usuarios.py::test_inv058_si_falla_la_limpieza_de_autenticacion_la_baja_no_se_revierte y ::test_inv058_si_falla_el_borrado_no_queda_auditoria_ni_limpieza
  Escenario: Orden seguro de la baja
    Cuando falla la limpieza de intentos y códigos tras el borrado, la baja queda hecha y solo hay un aviso sin datos
    Pero cuando falla el borrado, responde 503 y no queda ni baja parcial ni registro de auditoría

  @BDD-ADMIN @invariante @INV-059
  # Prueba: tests/test_admin_usuarios.py::test_inv059_el_registro_sobrevive_a_la_baja_del_usuario y ::test_inv059_el_registro_solo_tiene_usuario_id_accion_y_fecha
  Escenario: La auditoría sobrevive a la baja y no tiene datos personales
    Dado un usuario eliminado por el Dueño
    Cuando el Dueño pide la auditoría
    Entonces el registro sigue con acción, fecha e id, y su "usuario_correo" es nulo

  @BDD-ADMIN @invariante @INV-059
  # Prueba: tests/test_admin_usuarios.py::test_inv059_acciones_rechazadas_o_fallidas_no_dejan_registro
  Escenario: Lo rechazado no se audita
    Cuando una acción responde 404, 409, 422 o 503
    Entonces no se crea ningún registro de auditoría

  @BDD-ADMIN @invariante @INV-060
  # Prueba: tests/test_admin_usuarios.py::test_inv060_limite_60_por_minuto_responde_429_con_no_store y ::test_inv060_limite_20_escrituras_por_minuto_responde_429
  Escenario: Límites de frecuencia del Dueño
    Cuando el Dueño hace 61 peticiones en un minuto, o 21 acciones POST/DELETE
    Entonces la petición excedida recibe 429 con "Cache-Control: no-store"
    Pero un no-Dueño con 100 peticiones recibe siempre el 404

  @BDD-ADMIN @invariante @INV-060
  # Prueba: tests/test_admin_usuarios.py::test_inv060_pagina_de_25_y_tope_de_400_paginas y ::test_inv060_pagina_invalida_responde_422
  Escenario: Paginación acotada
    Dado 60 usuarios
    Cuando el Dueño pide la página 1, la 3, la 0 y la 401
    Entonces recibe 25 usuarios, 10 usuarios, 422 y 422, con "total" 60 y "total_paginas" 3

  @BDD-ADMIN @invariante @INV-060
  # Prueba: tests/test_admin_usuarios.py::test_inv060_busqueda_escapa_comodines y ::test_inv060_busqueda_con_comillas_y_sql_se_trata_como_texto
  Escenario: La búsqueda es texto literal
    Dado usuarios con correos y nombres distintos
    Cuando el Dueño busca "%", "_", "\\" o "' or 1=1 --"
    Entonces no coincide con todos los usuarios, no rompe la consulta y no ejecuta SQL
    Pero buscar "ANA" encuentra "ana@ejemplo.com" y "Ana Pérez" sin distinguir mayúsculas

  @BDD-ADMIN @invariante @INV-060
  # Prueba: tests/test_admin_usuarios.py::test_inv060_bd_lenta_responde_503_en_5s
  Escenario: Una BD lenta no cuelga el panel
    Dado que la lectura de la lista tarda más de 5 segundos
    Cuando el Dueño pide la lista
    Entonces recibe 503 con "Cache-Control: no-store" en como mucho 5 segundos

  @BDD-ADMIN @invariante @INV-061
  # Prueba: tests/test_admin_suspension.py::test_inv061_login_registra_ultimo_acceso y ::test_inv061_como_maximo_una_vez_por_hora
  Escenario: El último acceso se guarda como mucho una vez por hora
    Dado un usuario que nunca ha iniciado sesión
    Cuando inicia sesión dos veces en menos de una hora
    Entonces "ultimo_acceso" se escribe una sola vez y se actualiza al iniciar sesión pasada la hora

  @BDD-ADMIN @invariante @INV-061
  # Prueba: tests/test_admin_suspension.py::test_inv061_un_fallo_al_registrar_no_rompe_el_login
  Escenario: Si falla el último acceso, el inicio de sesión continúa
    Dado que "registrar_acceso" falla o tarda más de 2 segundos
    Cuando la persona inicia sesión con credenciales correctas
    Entonces recibe su sesión igual y solo se registra un aviso sin datos personales

  @BDD-ADMIN @invariante @INV-062
  # Prueba: backend/sql/pruebas/11_comprobar_admin_usuarios.sql
  Escenario: Los datos del panel están protegidos en la base
    Dada la migración aplicada dos veces en una base de pruebas
    Entonces "auditoria_admin" tiene RLS sin políticas y sin permisos para "anon" y "authenticated"
    Y las funciones "admin_*" y "registrar_acceso" solo las puede ejecutar "service_role"
    Y ninguna fila existente de "users" cambió y ninguna función devuelve "hashed_password"
    Y con 1 000 usuarios "admin_listar_usuarios" responde en menos de 2 segundos
    Y dos suspensiones simultáneas dan una sola "ok" y una sola fila de auditoría, y 20 "registrar_acceso" simultáneos escriben una vez

  @BDD-ADMIN @interfaz
  # Prueba: frontend/tests/admin-usuarios.test.mjs (helpers) · revisión manual de la página
  Escenario: La interfaz solo ofrece el panel al Dueño y confirma lo destructivo
    Dado que "es_dueno" es falso
    Entonces no aparece el enlace «Usuarios» y, por la dirección, la página muestra «no encontrada» al recibir 404
    Pero con "es_dueno" verdadero el diálogo de eliminar solo habilita el botón cuando se escribe el correo exacto
