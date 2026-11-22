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

