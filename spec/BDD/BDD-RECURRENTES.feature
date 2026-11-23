# language: es
# Trazabilidad: REQ-F-016 · UC-012 · CT-008 · INV-025, INV-026
# Las pruebas automatizadas que implementan cada escenario se indican con «Prueba:».
Característica: Transacciones recurrentes

  @BDD-RECURRENTES @invariante @INV-025
  Escenario: Crear una recurrente no registra nada
    Dado que creo el arriendo mensual con primera fecha ya pasada
    Entonces no existe ninguna transacción nueva
    Y el arriendo aparece en pendientes
    # Prueba: backend/tests/test_recurrentes.py::test_inv025_crear_no_registra_ninguna_transaccion

  @BDD-RECURRENTES @happy-path
  Escenario: Confirmar una pendiente con el monto ajustado
    Dado la recurrente «Luz» de 90.000 pendiente el 5 de noviembre
    Cuando la registro con 104.350,50 el 7 de noviembre
    Entonces se crea un gasto de 104.350,50 el 7 de noviembre
    Y la plantilla sigue proponiendo 90.000 y su próxima fecha es el 5 de diciembre
    # Prueba: backend/tests/test_recurrentes.py::test_confirmar_con_monto_y_fecha_ajustados

  @BDD-RECURRENTES @invariante @INV-026
  Escenario: Doble toque en «Registrar»
    Dado una recurrente pendiente
    Cuando confirmo la misma fecha dos veces
    Entonces la segunda vez recibo 409 y hay una sola transacción
    # Prueba: backend/tests/test_recurrentes.py::test_inv026_doble_confirmacion_registra_una_sola_vez

  @BDD-RECURRENTES @invariante @INV-026
  Escenario: El día 31 no se pierde tras febrero
    Dado una recurrente mensual del 31 de enero
    Entonces la siguiente es el 28 de febrero y la otra el 31 de marzo
    # Prueba: backend/tests/test_recurrentes.py::test_inv026_mensual_respeta_el_dia_ancla

  @BDD-RECURRENTES @invariante @INV-001
  Escenario: Otra persona no puede ver ni confirmar mis recurrentes
    Dado una recurrente mía
    Cuando otro usuario intenta verla, editarla, confirmarla u omitirla
    Entonces recibe 404 y no se registra nada
    # Prueba: backend/tests/test_recurrentes.py::test_inv001_otro_usuario_no_ve_ni_toca_mis_recurrentes

  @BDD-RECURRENTES @invariante @INV-026
  Escenario: Editar o pausar con datos viejos no hace retroceder la fecha
    Dado una recurrente que registré desde pendientes y ahora tiene próxima fecha el 5 de diciembre
    Cuando otra pantalla con datos viejos intenta guardarla con el 5 de noviembre
    Entonces recibe 409 y la fecha sigue en el 5 de diciembre
    Y pausar o editar el monto sin enviar fecha la conserva
    # Prueba: backend/tests/test_recurrentes.py::test_inv026_editar_con_la_fecha_vieja_no_la_hace_retroceder
