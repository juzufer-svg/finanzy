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

  @BDD-WHATSAPP
  Escenario: Corregir solo cambia lo que digo
    Dado un gasto de $85.000 en Hogar con Crédito el 20 de noviembre
    Cuando escribo «no, eran 80 mil»
    Entonces el monto pasa a $80.000 y la categoría, el medio de pago y la fecha se conservan
    # Prueba: backend/tests/test_whatsapp.py::test_h1_corregir_con_campos_vacios_no_borra_lo_que_tenia

  @BDD-WHATSAPP
  Escenario: Un fallo a mitad del registro no deja datos a medias
    Dado que escribo dos gastos y el servidor falla al guardar el segundo
    Entonces no queda ninguno guardado y me avisa que no se registró nada
    # Prueba: backend/tests/test_whatsapp.py::test_h3_si_falla_a_mitad_del_lote_no_queda_nada_y_se_avisa

  @BDD-WHATSAPP @invariante @INV-016
  Escenario: Cambiar la contraseña desconecta WhatsApp
    Dado mi número enlazado
    Cuando cambio o restablezco la contraseña
    Entonces el número queda desconectado y ya no puede registrar
    # Prueba: backend/tests/test_whatsapp.py::test_h2_cambiar_la_contrasena_desconecta_whatsapp
