# language: es
# Trazabilidad: REQ-N-002 · UC-001..UC-003 · INV-010
# Las pruebas automatizadas que implementan cada escenario se indican con «Prueba:».
Característica: Límites contra abuso

  @BDD-LIMITES @invariante @INV-010
  Escenario: Máximo 10 pedidos de código por IP por hora
    Dado una misma IP
    Cuando pide 11 códigos en una hora
    Entonces el 11.º se rechaza con 429
    # Prueba: backend/tests/test_limites.py::test_ip_maximo_10_pedidos_de_codigo_por_hora

  @BDD-LIMITES @invariante @INV-010
  Escenario: No se reenvía antes de 60 segundos
    Dado un código recién enviado
    Cuando se vuelve a pedir
    Entonces no se envía otro correo
    # Prueba: backend/tests/test_limites.py::test_no_se_reenvia_codigo_antes_de_60_segundos

  @BDD-LIMITES @invariante @INV-010
  Escenario: Topes diarios por destinatario y global
    Dado 10 correos enviados hoy a un destinatario, o 250 en total
    Cuando se pide otro código
    Entonces no se envía
    # Prueba: backend/tests/test_limites.py::test_maximo_10_correos_por_dia_al_mismo_destinatario, ::test_tope_global_de_250_correos_por_dia
