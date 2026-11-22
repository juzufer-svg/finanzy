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
