# language: es
# Trazabilidad: REQ-F-017 · UC-013 · CT-009 · INV-029, INV-030
Característica: Registrar por WhatsApp con IA

  @BDD-WHATSAPP @happy-path
  Escenario: Registrar un gasto en lenguaje libre
    Dado mi número enlazado
    Cuando escribo «ayer pagué 85 mil de internet con la tarjeta»
    Entonces se registra un gasto de $85.000 en Hogar con Crédito y me responde con el detalle
    # Prueba: backend/tests/test_whatsapp.py::test_registra_un_gasto_con_categoria_y_medio

  @BDD-WHATSAPP @invariante @INV-029
  Escenario: Un número no enlazado no puede registrar ni gastar IA
    Cuando un número desconocido escribe un gasto
    Entonces no se registra nada, no se llama a la IA y no se responde
    # Prueba: backend/tests/test_whatsapp.py::test_inv029_numero_no_enlazado_se_ignora_sin_llamar_a_la_ia

  @BDD-WHATSAPP @invariante @INV-029
  Escenario: Una petición sin la firma de Meta se rechaza
    Cuando llega al webhook un mensaje sin firma válida
    Entonces se responde 403 y no se procesa
    # Prueba: backend/tests/test_whatsapp.py::test_inv029_firma_invalida_se_rechaza_y_no_procesa

  @BDD-WHATSAPP @invariante @INV-029
  Escenario: Lo que propone la IA se valida
    Cuando la IA propone un monto de 0 o un tipo inválido
    Entonces no se guarda nada y se pide repetir
    # Prueba: backend/tests/test_whatsapp.py::test_inv029_lo_que_propone_la_ia_se_valida_y_no_se_guarda_si_es_invalido

  @BDD-WHATSAPP
  Escenario: Deshacer solo afecta lo registrado por WhatsApp
    Dado un gasto creado desde la app y dos mensajes registrados por WhatsApp
    Cuando escribo «deshacer» tres veces
    Entonces se borran los dos de WhatsApp y el de la app se conserva
    # Prueba: backend/tests/test_whatsapp.py::test_deshacer_borra_solo_lo_ultimo_registrado_por_whatsapp

  @BDD-WHATSAPP @invariante @INV-030
  Escenario: Tope diario
    Dado que ya envié el máximo de mensajes de hoy
    Cuando escribo otro
    Entonces no se llama a la IA y se me avisa una sola vez
    # Prueba: backend/tests/test_whatsapp.py::test_inv030_tope_diario_por_usuario
