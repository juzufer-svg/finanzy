# language: es
# Trazabilidad: REQ-F-018 · UC-014 · CT-010 · INV-031 a INV-036
# Las pruebas se escribirán en la implementación (backend/tests/test_monitor.py); aún no existen.
Característica: Monitor de consumos solo para el dueño

  @BDD-MONITOR @happy-path
  Escenario: El dueño ve el Monitor
    Dado que OWNER_EMAIL es "dueno@ejemplo.com" y inicio sesión con "  Dueno@Ejemplo.com "
    Cuando pido el resumen del Monitor
    Entonces recibo 200 con los contadores y las seis plataformas
    Y la respuesta lleva "Cache-Control: no-store"

  @BDD-MONITOR @invariante @INV-031
  Escenario: Otro usuario recibe 404 sin pistas
    Dado un usuario con sesión válida que no es el dueño
    Cuando pide el resumen del Monitor
    Entonces recibe 404 igual que una ruta inexistente
    Y la respuesta no menciona el Monitor ni el correo del dueño

  @BDD-MONITOR @invariante @INV-031
  Escenario: Sin sesión también recibe 404
    Cuando una persona sin sesión pide el resumen del Monitor
    Entonces recibe 404 y no 401

  @BDD-MONITOR @invariante @INV-031
  Escenario: Sin OWNER_EMAIL se niega a todos
    Dado que OWNER_EMAIL está vacía o no existe
    Cuando cualquier usuario con sesión, incluido el dueño habitual, pide el resumen
    Entonces recibe 404

  @BDD-MONITOR @invariante @INV-033
  Escenario: Solo lectura
    Cuando el dueño intenta POST, PUT, PATCH o DELETE sobre una ruta del Monitor
    Entonces no se ejecuta ninguna acción y no se escribe nada en ninguna plataforma

  @BDD-MONITOR
  Escenario: Una plataforma caída no rompe las demás
    Dado que la consulta a Railway falla y falta el token de Anthropic
    Cuando el dueño pide el resumen
    Entonces Railway y Anthropic aparecen con estado "no_disponible" y datos nulos
    Y Meta, Supabase, Vercel y Brevo aparecen con su información
    Y la respuesta no incluye el motivo del fallo

  @BDD-MONITOR @invariante @INV-032
  Escenario: No se filtran tokens ni datos personales
    Dado que los seis tokens MONITOR_* están configurados y una plataforma responde con error que incluye el token
    Cuando el dueño pide el resumen
    Entonces ni la respuesta, ni los logs, ni los errores contienen ningún token, el correo del dueño, correos, teléfonos, textos ni ids de usuario

  @BDD-MONITOR @invariante @INV-034
  Escenario: Las URLs son fijas y no se siguen redirecciones
    Dado que una plataforma responde con una redirección a otro servidor
    Cuando el dueño pide el resumen
    Entonces no se sigue la redirección y esa plataforma aparece "no_disponible"

  @BDD-MONITOR @invariante @INV-035
  Escenario: Caché corta y límite de frecuencia
    Cuando el dueño pide el resumen varias veces seguidas
    Entonces las plataformas no se consultan de nuevo mientras la caché vale
    Y al pasar el límite de frecuencia recibe 429 con "Cache-Control: no-store"

  @BDD-MONITOR @invariante @INV-036
  Escenario: Los contadores guardan solo agregados y no rompen el flujo
    Dado que la tabla de contadores falla al escribir
    Cuando un usuario hace una pregunta al asistente
    Entonces recibe su respuesta normalmente y se registra un aviso sin datos personales

  @BDD-MONITOR @invariante @INV-036
  Escenario: Solo cuentan los correos enviados con éxito
    Dado que Brevo rechaza un envío
    Cuando se pide un código por correo
    Entonces el contador de correos enviados no aumenta
