# language: es
# Trazabilidad: REQ-F-018 · UC-014 · CT-010 · INV-031 a INV-036
# Las pruebas se escribirán en la implementación: backend/tests/test_monitor.py y backend/sql/pruebas/06_comprobar_monitor.sql; aún no existen.
Característica: Monitor de consumos solo para el Dueño

  @BDD-MONITOR @happy-path @INV-031
  # Prueba: tests/test_monitor.py::test_inv031_correo_con_mayusculas_y_espacios
  Escenario: El Dueño ve el Monitor aunque OWNER_EMAIL tenga mayúsculas y espacios
    Dado que OWNER_EMAIL es "  DUENO@Ejemplo.com " y inicio sesión con "dueno@ejemplo.com"
    Cuando pido el resumen del Monitor
    Entonces recibo 200 con los contadores y las seis plataformas
    Y la respuesta lleva "Cache-Control: no-store"

  @BDD-MONITOR @invariante @INV-031
  # Prueba: tests/test_monitor.py::test_inv031_no_dueno_recibe_404_identico_a_ruta_inexistente
  Escenario: Otro usuario recibe 404 sin pistas
    Dado un usuario con sesión válida que no es el Dueño
    Cuando pide el resumen del Monitor
    Entonces recibe 404 byte a byte idéntico (cuerpo y cabeceras, salvo "Date") al de "GET /api/v1/no-existe" y al de "GET /api/v1/monitor/no-existe"
    Y ninguno de esos 404 lleva "Cache-Control: no-store"
    Y la respuesta no menciona el Monitor ni el correo del Dueño

  @BDD-MONITOR @invariante @INV-031
  # Prueba: tests/test_monitor.py::test_inv031_sin_sesion_recibe_404
  Escenario: Sin sesión también recibe 404
    Cuando una persona sin sesión pide el resumen del Monitor
    Entonces recibe 404 y no 401

  @BDD-MONITOR @invariante @INV-031
  # Prueba: tests/test_monitor.py::test_inv031_sin_owner_email_responde_404
  Escenario: Sin OWNER_EMAIL se niega a todos
    Dado que OWNER_EMAIL está vacía o no existe
    Cuando cualquier usuario con sesión, incluido el Dueño habitual, pide el resumen
    Entonces recibe 404

  @BDD-MONITOR @invariante @INV-031
  # Prueba: tests/test_monitor.py::test_inv031_bd_caida_al_autorizar_responde_404
  Escenario: Si la BD falla al autorizar, se niega con 404 y no con 503
    Dado que la base de datos falla al verificar la sesión
    Cuando cualquier persona, incluido el Dueño habitual, pide el resumen
    Entonces recibe 404 byte a byte idéntico al de una ruta inexistente (sin "Cache-Control: no-store") y no 503

  @BDD-MONITOR @invariante @INV-031
  # Prueba: tests/test_monitor.py::test_inv031_bd_caida_al_leer_contadores_responde_503_solo_al_dueno
  Escenario: El 503 solo existe para el Dueño ya confirmado
    Dado que la sesión es la del Dueño y la lectura de contadores falla
    Cuando pide el resumen
    Entonces recibe 503 con "Cache-Control: no-store"
    Pero un usuario que no es el Dueño, en la misma situación, recibe 404

  @BDD-MONITOR @invariante @INV-031
  # Prueba: tests/test_monitor.py::test_inv031_usa_compare_digest
  Escenario: El correo se compara en tiempo constante
    Cuando el servidor compara el correo de la sesión con OWNER_EMAIL
    Entonces usa "hmac.compare_digest" sobre los bytes de ambos correos normalizados

  @BDD-MONITOR @invariante @INV-033
  # Prueba: tests/test_monitor.py::test_inv033_dueno_con_metodo_no_get_recibe_405
  Escenario: Solo lectura para el Dueño
    Cuando el Dueño intenta POST, PUT, PATCH o DELETE sobre una ruta del Monitor
    Entonces recibe 405 y no se ejecuta ninguna acción ni se escribe nada en ninguna plataforma

  @BDD-MONITOR @invariante @INV-033
  # Prueba: tests/test_monitor.py::test_inv033_no_dueno_con_post_recibe_404_identico
  Escenario: Un no-Dueño con POST recibe el mismo 404 que con GET
    Dado un usuario con sesión válida que no es el Dueño
    Cuando envía POST a "/api/v1/monitor/resumen"
    Entonces recibe 404 byte a byte idéntico al de una ruta inexistente, sin "Cache-Control: no-store"
    Y no recibe 405, que revelaría que la ruta existe

  @BDD-MONITOR
  # Prueba: tests/test_monitor.py::test_plataforma_caida_no_rompe_las_demas
  Escenario: Una plataforma caída no rompe las demás
    Dado que la consulta a Railway falla y falta el token de Anthropic
    Cuando el Dueño pide el resumen
    Entonces Railway y Anthropic aparecen con estado "no_disponible" y datos nulos
    Y Meta, Supabase, Vercel y Brevo aparecen con su información
    Y la respuesta no incluye el motivo del fallo

  @BDD-MONITOR @invariante @INV-032
  # Prueba: tests/test_monitor.py::test_inv032_no_se_filtran_tokens_en_respuesta_ni_logs
  Escenario: No se filtran tokens ni datos personales
    Dado que los seis tokens MONITOR_* están configurados y una plataforma responde con error que incluye el token
    Cuando el Dueño pide el resumen
    Entonces ni la respuesta, ni los logs, ni los errores contienen ningún token, el correo del Dueño, correos, teléfonos, textos ni ids de usuario

  @BDD-MONITOR @invariante @INV-032
  # Prueba: tests/test_monitor.py::test_inv032_datos_solo_lista_blanca
  Escenario: Los datos de cada plataforma solo contienen campos de la lista blanca
    Dado que una plataforma responde con campos extra (un correo, un teléfono, un texto libre y un token)
    Cuando el Dueño pide el resumen
    Entonces "datos" solo contiene las claves de la lista blanca de esa plataforma
    Y sus valores son solo números, fechas ISO o cadenas de la lista blanca
    Y si no queda ningún campo válido la plataforma aparece "no_disponible"

  @BDD-MONITOR @invariante @INV-034
  # Prueba: tests/test_monitor.py::test_inv034_no_sigue_redirecciones
  Escenario: Las URLs son fijas y no se siguen redirecciones
    Dado que una plataforma responde con una redirección a otro servidor
    Cuando el Dueño pide el resumen
    Entonces no se sigue la redirección y esa plataforma aparece "no_disponible"

  @BDD-MONITOR @invariante @INV-034
  # Prueba: tests/test_monitor.py::test_inv034_id_invalido_deja_la_plataforma_no_disponible_sin_consultar
  Escenario: Un id de configuración con formato inválido no llega a ninguna URL
    Dado que el id de proyecto configurado para una plataforma contiene "../" o "?"
    Cuando el Dueño pide el resumen
    Entonces esa plataforma aparece "no_disponible" sin haberse consultado
    Y las demás se muestran con normalidad

  @BDD-MONITOR @invariante @INV-034
  # Prueba: tests/test_monitor.py::test_inv034_timeout_de_5s_marca_no_disponible
  Escenario: Una plataforma que tarda más de 5 segundos queda no disponible
    Dado que una plataforma no responde antes de 5 segundos
    Cuando el Dueño pide el resumen
    Entonces esa plataforma aparece "no_disponible" y la respuesta no espera más de ese tiempo por ella
    Y las demás se muestran con normalidad

  @BDD-MONITOR @invariante @INV-035
  # Prueba: tests/test_monitor.py::test_inv035_cache_60s_no_reconsulta y ::test_inv035_limite_20_por_minuto_responde_429
  Escenario: Caché de 60 s y límite de 20 peticiones por minuto
    Cuando el Dueño pide el resumen varias veces seguidas
    Entonces las plataformas no se consultan de nuevo mientras la caché de 60 s vale
    Y a la petición 21 dentro de un minuto recibe 429 con "Cache-Control: no-store"

  @BDD-MONITOR @invariante @INV-036
  # Prueba: tests/test_monitor.py::test_inv036_fallo_al_contar_no_rompe_el_flujo
  Escenario: Los contadores guardan solo agregados y no rompen el flujo
    Dado que la tabla de contadores falla al escribir
    Cuando un usuario hace una pregunta al asistente
    Entonces recibe su respuesta normalmente y se registra un aviso sin datos personales

  @BDD-MONITOR @invariante @INV-036
  # Prueba: tests/test_monitor.py::test_inv036_solo_cuentan_correos_exitosos
  Escenario: Solo cuentan los correos enviados con éxito
    Dado que Brevo rechaza un envío
    Cuando se pide un código por correo
    Entonces el contador de correos enviados no aumenta

  @BDD-MONITOR @invariante @INV-036
  # Prueba: tests/test_monitor.py::test_inv036_recibidos_solo_de_numeros_enlazados
  Escenario: Los mensajes de números desconocidos o con firma inválida no se cuentan
    Dado un mensaje de WhatsApp de un número desconocido y otro con firma inválida
    Cuando el webhook los recibe
    Entonces el contador de mensajes recibidos no aumenta
    Pero un mensaje de un número enlazado con firma válida sí lo aumenta en 1

  @BDD-MONITOR @invariante @INV-036
  # Prueba: tests/test_monitor.py::test_inv036_purga_a_90_dias_una_vez_al_dia
  Escenario: La purga de 90 días ocurre al escribir, como mucho una vez al día
    Dado contadores de hace más de 90 días y de hace menos de 90 días
    Cuando se escribe un contador por primera vez en el día
    Entonces se borran solo los de más de 90 días
    Y una segunda escritura el mismo día no vuelve a purgar

  @BDD-MONITOR @invariante @INV-036
  # Prueba: backend/sql/pruebas/06_comprobar_monitor.sql
  Escenario: La tabla de contadores tiene RLS y clave única
    Dada la migración de contadores aplicada en una base de pruebas
    Entonces la tabla tiene RLS activado y sin políticas para los roles de la API pública
    Y rechaza una segunda fila con la misma fecha, métrica y origen
    Y no tiene columnas de correo, teléfono, texto ni id de usuario

  @BDD-MONITOR @invariante @INV-036
  # Prueba: tests/test_monitor.py::test_inv036_incremento_atomico
  Escenario: Dos incrementos simultáneos no pierden cuenta
    Dado el contador de hoy en 10
    Cuando se incrementan a la vez en 1 y en 2
    Entonces el contador queda en 13
