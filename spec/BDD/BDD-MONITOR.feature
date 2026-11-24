# language: es
# Trazabilidad: REQ-F-018 · UC-014 · CT-010 · CT-002 (es_dueno) · INV-031 a INV-036
# Pruebas: backend/tests/test_monitor.py (INV-031 a INV-035), backend/tests/test_contadores.py (INV-036) y backend/sql/pruebas/06_comprobar_monitor.sql (RLS, clave única, atomicidad).
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
    Y es idéntico (cuerpo y cabeceras, salvo "Date") al de "GET /api/v1/no-existe"

  @BDD-MONITOR @invariante @INV-031
  # Prueba: tests/test_monitor.py::test_inv031_sin_owner_email_responde_404
  Escenario: Sin OWNER_EMAIL se niega a todos
    Dado que OWNER_EMAIL está vacía o no existe
    Cuando cualquier usuario con sesión, incluido el Dueño habitual, pide el resumen
    Entonces recibe 404

  @BDD-MONITOR @invariante @INV-031
  # Prueba: tests/test_monitor.py::test_inv031_sin_owner_email_ni_se_mira_la_sesion
  Escenario: Sin OWNER_EMAIL ni siquiera se consulta la sesión
    Dado que OWNER_EMAIL está vacía
    Cuando el Dueño habitual pide el resumen
    Entonces recibe 404 sin que se lea al usuario en la BD

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

  @BDD-MONITOR @invariante @INV-031
  # Prueba: tests/test_monitor.py::test_inv031_users_me_es_dueno_solo_informa_sobre_si_mismo
  Escenario: La interfaz sabe si mostrar «Monitor» sin conocer el correo del Dueño
    Cuando el Dueño pide "GET /api/v1/users/me"
    Entonces "es_dueno" es true
    Pero para cualquier otro usuario "es_dueno" es false y la respuesta no contiene el correo del Dueño
    Y si OWNER_EMAIL está vacía o la comprobación falla, "es_dueno" es false y "/users/me" sigue respondiendo 200

  @BDD-MONITOR @invariante @INV-033
  # Prueba: tests/test_monitor.py::test_inv033_dueno_con_metodo_no_get_recibe_405
  Escenario: Solo lectura para el Dueño
    Cuando el Dueño intenta POST, PUT, PATCH, DELETE o HEAD sobre "/api/v1/monitor/resumen"
    Entonces recibe 405 con "Cache-Control: no-store"
    Y no se ejecuta ninguna acción ni se escribe nada en ninguna plataforma

  @BDD-MONITOR @invariante @INV-033
  # Prueba: tests/test_monitor.py::test_inv033_no_dueno_con_post_recibe_404_identico (parametrizada: POST y HEAD)
  Escenario: Un no-Dueño con un método distinto de GET recibe el mismo 404 que con GET
    Dado un usuario con sesión válida que no es el Dueño
    Cuando envía POST o HEAD a "/api/v1/monitor/resumen"
    Entonces recibe 404 byte a byte idéntico al de una ruta inexistente, sin "Cache-Control: no-store"
    Y no recibe 405, que revelaría que la ruta existe

  @BDD-MONITOR @invariante @INV-033
  # Prueba: tests/test_monitor.py::test_inv033_no_se_escribe_en_plataformas
  Escenario: El Monitor nunca escribe en las plataformas
    Dado que las seis plataformas están simuladas y se registran todas las peticiones salientes
    Cuando el Dueño pide el resumen y también intenta POST, PUT, PATCH y DELETE
    Entonces todas las peticiones salientes son de lectura (GET o equivalente)
    Y no se escribe nada en ninguna plataforma ni en la tabla de contadores desde "/monitor/*"

  @BDD-MONITOR @invariante @INV-033
  # Prueba: tests/test_monitor.py::test_inv033_metodos_raros_no_dueno_recibe_404_identico_byte_a_byte y ::test_inv033_metodos_raros_dueno_recibe_405_con_no_store
  Escenario: Cualquier método raro, incluido OPTIONS sin preflight, se trata igual
    Cuando se envía TRACE, PROPFIND, un método inventado u OPTIONS sin "Origin" a "/api/v1/monitor/resumen"
    Entonces un no-Dueño recibe 404 byte a byte idéntico al de "/api/v1/no-existe" con el mismo método
    Pero el Dueño recibe 405 con "Allow: GET" y "Cache-Control: no-store"

  @BDD-MONITOR @invariante @INV-031
  # Prueba: tests/test_monitor.py::test_inv031_barra_final_es_404_como_cualquier_ruta_inexistente
  Escenario: La barra final no delata la ruta
    Cuando cualquier persona pide "/api/v1/monitor/resumen/" (con barra final)
    Entonces recibe el mismo 404 que "/api/v1/no-existe/" y ninguna redirección

  @BDD-MONITOR @invariante @INV-033
  # Prueba: tests/test_monitor.py::test_inv033_subruta_inexistente_responde_404_normal
  Escenario: Una subruta inexistente bajo /monitor da el 404 normal
    Cuando cualquier usuario, incluido el Dueño, pide "/api/v1/monitor/no-existe" con GET, POST o DELETE
    Entonces recibe el 404 normal de la API, no 405 ni 429, y sin "Cache-Control: no-store"
    Y la comparación con "GET /api/v1/no-existe" se hace sin sesión y con sesión de un no-Dueño

  @BDD-MONITOR @invariante @INV-033
  # Prueba: tests/test_monitor.py::test_inv033_options_responde_igual_en_cualquier_ruta
  Escenario: El preflight CORS queda fuera de la regla de 404
    Cuando se envía OPTIONS (preflight CORS) a "/api/v1/monitor/resumen" y a "/api/v1/no-existe"
    Entonces ambas respuestas son las del middleware CORS y son iguales (solo el preflight real, con "Origin" y "Access-Control-Request-Method")
    Y no revelan nada sobre el Monitor

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
    Dado que una plataforma responde con campos extra (un correo, un teléfono, un texto libre y un token), valores booleanos, negativos o anidados
    Cuando el Dueño pide el resumen
    Entonces "datos" solo contiene las claves de la lista blanca de esa plataforma
    Y sus valores son solo int o float no negativos (nunca bool), fechas ISO (instantes UTC con "Z") o cadenas de la lista blanca
    Y si no queda ningún campo válido la plataforma aparece "no_disponible"
    Y Anthropic aparece "no_disponible" o solo con los campos de su lista

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
  # Prueba: tests/test_monitor.py::test_inv034_nada_del_cliente_llega_a_la_url
  Escenario: Nada de lo que envía el cliente llega a una URL de plataforma
    Dado que el cliente envía parámetros de consulta, cabeceras y rutas con direcciones, ids y "../"
    Cuando el Dueño pide el resumen
    Entonces las URLs salientes son solo las fijas del código con los ids de configuración
    Y ningún valor de la petición del cliente aparece en ellas

  @BDD-MONITOR @invariante @INV-034
  # Prueba: tests/test_monitor.py::test_inv034_timeout_de_5s_marca_no_disponible
  Escenario: Una plataforma que tarda más de 5 segundos queda no disponible
    Dado que una plataforma no responde antes de 5 segundos en total (aunque cada fase de la conexión sea rápida)
    Cuando el Dueño pide el resumen
    Entonces esa plataforma aparece "no_disponible" y la respuesta no espera más de ese plazo total (asyncio.wait_for) por ella
    Y las demás se muestran con normalidad

  @BDD-MONITOR @invariante @INV-034
  # Prueba: tests/test_monitor.py::test_inv034_resumen_responde_en_menos_de_6s_en_el_peor_caso
  Escenario: El resumen responde en menos de 6 segundos aunque todas las plataformas sean lentas
    Dado que las seis plataformas tardan más de 5 segundos y la lectura de contadores es normal
    Cuando el Dueño pide el resumen
    Entonces recibe 200 en menos de 6 segundos con las seis plataformas "no_disponible"
    Y los contadores y las plataformas se consultaron en paralelo

  @BDD-MONITOR @invariante @INV-034
  # Prueba: tests/test_monitor.py::test_inv034_cuerpo_de_plataforma_mayor_de_1mb_es_no_disponible y ::test_inv034_lectura_de_contadores_con_plazo_total_503_solo_al_dueno
  Escenario: Cuerpos enormes y lecturas colgadas no tumban el Monitor
    Dado que una plataforma responde con más de 1 MB
    Entonces esa plataforma aparece "no_disponible"
    Y si la lectura de contadores no responde en 5 s, el Dueño recibe 503 con "Cache-Control: no-store" y un no-Dueño recibe 404

  @BDD-MONITOR @invariante @INV-035
  # Prueba: tests/test_monitor.py::test_inv035_cache_60s_no_reconsulta y ::test_inv035_limite_20_por_minuto_responde_429
  Escenario: Caché de 60 s y límite de 20 peticiones por minuto
    Cuando el Dueño pide el resumen varias veces seguidas
    Entonces las plataformas no se consultan de nuevo mientras la caché de 60 s vale
    Y a la petición 21 dentro de un minuto recibe 429 con "Cache-Control: no-store"

  @BDD-MONITOR @invariante @INV-035
  # Prueba: tests/test_monitor.py::test_inv035_fallos_se_cachean_15s
  Escenario: Los fallos de plataforma se cachean 15 segundos
    Dado que una plataforma falla
    Cuando el Dueño pide el resumen dos veces con menos de 15 segundos de diferencia
    Entonces la plataforma solo se consulta una vez
    Y pasados los 15 segundos se vuelve a consultar

  @BDD-MONITOR @invariante @INV-035
  # Prueba: tests/test_monitor.py::test_inv035_405_del_dueno_cuenta_para_el_limite
  Escenario: Los 405 del Dueño cuentan para el límite
    Dado que el Dueño ya envió 20 peticiones POST en un minuto y recibió 405
    Cuando pide el resumen con GET
    Entonces recibe 429 con "Cache-Control: no-store"

  @BDD-MONITOR @invariante @INV-035
  # Prueba: tests/test_monitor.py::test_inv035_no_dueno_sobre_el_limite_recibe_404_nunca_429
  Escenario: Un no-Dueño que supera el límite recibe 404, nunca 429
    Dado un usuario con sesión válida que no es el Dueño
    Cuando envía 25 peticiones en un minuto a "/api/v1/monitor/resumen"
    Entonces todas reciben el mismo 404 idéntico al de una ruta inexistente
    Y ninguna recibe 429

  @BDD-MONITOR @invariante @INV-035
  # Prueba: tests/test_monitor.py::test_inv035_no_store_solo_en_respuestas_del_dueno
  Escenario: "no-store" solo en las respuestas al Dueño confirmado
    Cuando el Dueño recibe 200, 405, 429 o 503
    Entonces cada una lleva "Cache-Control: no-store"
    Pero ningún 404 (no-Dueño, sin sesión, BD caída al autorizar, sin OWNER_EMAIL o ruta inexistente) lo lleva

  @BDD-MONITOR @invariante @INV-036
  # Prueba: tests/test_contadores.py::test_inv036_fallo_al_contar_no_rompe_el_flujo
  Escenario: Los contadores guardan solo agregados y no rompen el flujo
    Dado que la tabla de contadores falla al escribir
    Cuando un usuario hace una pregunta al asistente
    Entonces recibe su respuesta normalmente y se registra un aviso sin datos personales

  @BDD-MONITOR @invariante @INV-036
  # Prueba: tests/test_contadores.py::test_inv036_solo_cuentan_correos_exitosos
  Escenario: Solo cuentan los correos enviados con éxito
    Dado que Brevo rechaza un envío
    Cuando se pide un código por correo
    Entonces el contador de correos enviados no aumenta

  @BDD-MONITOR @invariante @INV-036
  # Prueba: tests/test_contadores.py::test_inv036_recibidos_solo_de_numeros_enlazados y ::test_inv036_firma_invalida_no_incrementa_whatsapp_recibidos
  Escenario: Los mensajes de números desconocidos o con firma inválida no se cuentan
    Dado un mensaje de WhatsApp de un número desconocido y otro con firma inválida
    Cuando el webhook los recibe
    Entonces el contador de mensajes recibidos no aumenta
    Pero un mensaje de un número enlazado con firma válida sí lo aumenta en 1

  @BDD-MONITOR @invariante @INV-036
  # Prueba: tests/test_contadores.py::test_inv036_purga_a_90_dias_una_vez_al_dia
  Escenario: La purga de 90 días ocurre al escribir, como mucho una vez al día
    Dado contadores con fecha anterior a hoy menos 90 días y otros posteriores
    Cuando se escribe un contador por primera vez en el día
    Entonces se borran solo las filas con fecha menor que hoy menos 90 días
    Y se registra la marca de última purga en la propia tabla (fila "purga"/"general" del día)
    Y una segunda escritura el mismo día, aunque sea de otra instancia, no vuelve a purgar
    Y la misma instancia no vuelve ni a intentarlo ese día (prueba: ::test_inv036_la_purga_se_intenta_una_sola_vez_al_dia_por_instancia)

  @BDD-MONITOR @invariante @INV-036
  # Prueba: backend/sql/pruebas/06_comprobar_monitor.sql
  Escenario: La tabla de contadores tiene RLS, clave única e incremento atómico
    Dada la migración de contadores aplicada en una base de pruebas
    Entonces la tabla tiene RLS activado y sin políticas para los roles de la API pública
    Y rechaza una segunda fila con la misma fecha, métrica y origen
    Y no tiene columnas de correo, teléfono, texto ni id de usuario
    Y con el contador de hoy en 10, dos incrementos simultáneos de 1 y de 2 lo dejan en 13
