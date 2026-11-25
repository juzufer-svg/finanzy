# language: es
# Trazabilidad: REQ-F-004, REQ-F-005 · UC-004, UC-008 · INV-003, INV-004, INV-005
# Las pruebas automatizadas que implementan cada escenario se indican con «Prueba:».
Característica: Transacciones y resumen

  @BDD-TRANSACCIONES @invariante @INV-003
  Escenario: Montos inválidos se rechazan
    Dado un monto 0, negativo o mayor a 1e12
    Cuando se registra la transacción
    Entonces se rechaza con 422
    # Prueba: backend/tests/test_validaciones.py::test_inv003_montos_fuera_de_rango_se_rechazan

  @BDD-TRANSACCIONES @invariante @INV-004 @INV-005
  Escenario: Tipo y fecha deben ser válidos
    Dado un tipo distinto de ingreso/gasto o una fecha mal formada
    Cuando se registra
    Entonces se rechaza con 422
    # Prueba: backend/tests/test_validaciones.py::test_inv004_tipo_debe_ser_ingreso_o_gasto, ::test_inv005_fechas_invalidas_se_rechazan

  @BDD-TRANSACCIONES @happy-path
  Escenario: Resumen del mes
    Dado un ingreso de 100 y un gasto de 30 en noviembre y un gasto en octubre
    Cuando se pide el resumen de noviembre
    Entonces ingresos 100, gastos 30, balance 70 y 2 transacciones
    # Prueba: backend/tests/test_validaciones.py::test_resumen_del_mes

  @BDD-TRANSACCIONES @CHG-006
  Escenario: Promedio diario con los días reales y proyección al cierre
    Dado que hoy es 22 de noviembre y llevo 220.000 gastados en noviembre
    Cuando abro Reportes de noviembre
    Entonces el gasto diario promedio es 10.000 ("en 22 de 30 días")
    Y la proyección al cierre es 300.000
    Y en octubre (31 días) un gasto de 310.000 da un promedio de 10.000 y no hay proyección
    # Prueba: frontend/tests/month-stats.test.mjs (promedio diario real, proyección al cierre)

  @BDD-TRANSACCIONES @CHG-006
  Escenario: Comparación con el mes anterior por categoría
    Dado 100 en "a" y 300 en "b" este mes, y 200 en "a" y 70 en "z" el mes anterior
    Cuando veo la tabla de gastos por categoría
    Entonces aparecen b, a, z en ese orden, "a" con ▼ 50 % y "b" como nueva
    # Prueba: frontend/tests/month-stats.test.mjs (comparación por categoría)

  @BDD-TRANSACCIONES @CHG-006
  Escenario: Buscar y filtrar transacciones
    Dado un gasto "Mercado D1" en la categoría "Alimentación"
    Cuando busco "ALIMENTACION" o filtro por esa categoría
    Entonces solo aparece ese gasto
    # Prueba: frontend/tests/month-stats.test.mjs (buscador)

  @BDD-TRANSACCIONES @CHG-007 @invariante @INV-022
  Escenario: Medio de pago de una transacción
    Dado que registro un gasto con medio de pago "efectivo"
    Cuando lo edito sin enviar el medio de pago
    Entonces conserva "efectivo"; si envío null queda sin especificar; y un valor como "bitcoin" se rechaza con 422
    # Prueba: backend/tests/test_medio_pago.py


  @BDD-TRANSACCIONES @CHG-027 @invariante @INV-063
  Escenario: Fecha anterior al 1 de enero de 2026
    Dado que hoy en Colombia es el 25/11/2026
    Cuando registro una transacción con fecha 2025-12-31
    Entonces responde 422 «La fecha debe estar entre el 1 de enero de 2026 y el 25/11/2027» y no se guarda nada
    # Prueba: backend/tests/test_rango_fechas.py::test_inv063_crear_transaccion_2025_12_31_se_rechaza_con_mensaje

  @BDD-TRANSACCIONES @CHG-027 @invariante @INV-063
  Escenario: Fecha mínima permitida
    Dado que hoy en Colombia es el 25/11/2026
    Cuando registro una transacción con fecha 2026-01-01
    Entonces se guarda
    # Prueba: backend/tests/test_rango_fechas.py::test_inv063_crear_transaccion_2026_01_01_se_acepta

  @BDD-TRANSACCIONES @CHG-027 @invariante @INV-063
  Escenario: Fecha máxima permitida (hoy más 365 días)
    Dado que hoy en Colombia es el 25/11/2026
    Cuando registro una transacción con fecha 2027-11-25
    Entonces se guarda
    # Prueba: backend/tests/test_rango_fechas.py::test_inv063_crear_transaccion_hoy_mas_365_se_acepta

  @BDD-TRANSACCIONES @CHG-027 @invariante @INV-063
  Escenario: Fecha posterior a hoy más 365 días
    Dado que hoy en Colombia es el 25/11/2026
    Cuando registro una transacción con fecha 2027-11-26
    Entonces responde 422 «La fecha debe estar entre el 1 de enero de 2026 y el 25/11/2027» y no se guarda nada
    # Prueba: backend/tests/test_rango_fechas.py::test_inv063_crear_transaccion_hoy_mas_366_se_rechaza

  @BDD-TRANSACCIONES @CHG-027 @invariante @INV-063
  Escenario: Año absurdo
    Cuando registro una transacción con fecha 9999-12-31 o 0001-01-01
    Entonces responde 422 «La fecha debe estar entre el 1 de enero de 2026 y el 25/11/2027» y no se guarda nada
    # Prueba: backend/tests/test_rango_fechas.py::test_inv063_crear_transaccion_fechas_absurdas_se_rechazan

  @BDD-TRANSACCIONES @CHG-027 @invariante @INV-063
  Escenario: El día de Colombia decide el borde, no el día UTC
    Dado que son las 22:30 del 25/11/2026 en Colombia (ya es 26/11 en UTC)
    Cuando registro una transacción con fecha 2027-11-26
    Entonces se rechaza con 422, y con fecha 2027-11-25 se guarda
    # Prueba: backend/tests/test_rango_fechas.py::test_inv063_el_borde_depende_del_dia_de_colombia_y_no_del_dia_utc

  @BDD-TRANSACCIONES @CHG-027 @invariante @INV-063
  Escenario: Editar sin cambiar la fecha no se rechaza por el rango
    Dado una transacción guardada con fecha 2025-06-01
    Cuando la edito cambiando solo el monto
    Entonces se guarda; pero si cambio su fecha a una fuera de rango, responde 422
    # Prueba: backend/tests/test_rango_fechas.py::test_inv063_editar_sin_cambiar_la_fecha_no_se_rechaza_aunque_este_fuera_de_rango
