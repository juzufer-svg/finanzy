# language: es
# Trazabilidad: REQ-F-001, REQ-F-002 · UC-001, UC-002 · INV-006, INV-010, INV-011, INV-014, INV-015
# Las pruebas automatizadas que implementan cada escenario se indican con «Prueba:».
Característica: Registro e inicio de sesión

  @BDD-AUTH @happy-path
  Escenario: Registro y verificación de una cuenta nueva
    Dado un correo que no está registrado
    Cuando el visitante se registra
    Entonces se crea una cuenta pendiente y se envía un código
    Y al ingresar el código la cuenta queda activa con sesión iniciada
    # Prueba: backend/tests/test_auth.py::test_registro_crea_cuenta_pendiente_y_envia_codigo, ::test_verificar_codigo_activa_la_cuenta_y_da_sesion

  @BDD-AUTH @invariante @INV-006
  Escenario: Una cuenta pendiente no obtiene sesión
    Dado una cuenta pendiente con contraseña correcta
    Cuando intenta iniciar sesión
    Entonces no recibe sesión y se le pide verificar
    # Prueba: backend/tests/test_auth.py::test_inv006_cuenta_pendiente_no_obtiene_sesion

  @BDD-AUTH @invariante @INV-010
  Escenario: El login se bloquea tras 5 fallos
    Dado un correo
    Cuando se ingresa una contraseña incorrecta 5 veces
    Entonces el siguiente intento se rechaza con 429 durante 15 minutos
    # Prueba: backend/tests/test_auth.py::test_inv010_login_se_bloquea_tras_5_fallos

  @BDD-AUTH @invariante @INV-011
  Escenario: Sesiones manipuladas se rechazan
    Dado un token vencido, sin firma, sin exp o firmado con otra clave
    Cuando se usa para acceder
    Entonces se rechaza
    # Prueba: backend/tests/test_auth.py::test_inv011_tokens_invalidos_se_rechazan

  @BDD-AUTH @invariante @INV-015
  Escenario: Las contraseñas existentes siguen funcionando
    Dado un hash creado con SQL ($2a$) o con passlib (> 72 bytes)
    Cuando el usuario inicia sesión
    Entonces la contraseña se valida
    # Prueba: backend/tests/test_auth.py::test_inv015_valida_hash_2a_creado_con_sql, ::test_inv015_valida_contrasenas_largas_de_passlib
