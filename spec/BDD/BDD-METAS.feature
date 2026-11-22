# language: es
# Trazabilidad: REQ-F-008, REQ-F-009 · UC-007 · INV-008
# Las pruebas automatizadas que implementan cada escenario se indican con «Prueba:».
Característica: Metas de ahorro

  @BDD-METAS @happy-path
  Escenario: Abonar a una meta
    Dado una meta de 1000
    Cuando se abonan 50
    Entonces la meta tiene 50 (5 %) y hay un gasto de 50 en «Ahorro»
    # Prueba: backend/tests/test_metas.py::test_abono_suma_a_la_meta_y_registra_gasto_en_ahorro

  @BDD-METAS @invariante @INV-008
  Escenario: Abono a una meta inexistente
    Dado un id de meta que no existe
    Cuando se intenta abonar
    Entonces se responde 404 y no se crea ningún gasto
    # Prueba: backend/tests/test_metas.py::test_inv008_abono_a_meta_inexistente_no_crea_gasto

  @BDD-METAS @invariante @INV-008
  Escenario: Se revierte el gasto si falla la meta
    Dado que actualizar la meta falla
    Cuando se abona
    Entonces se responde 500 y el gasto creado se elimina
    # Prueba: backend/tests/test_metas.py::test_inv008_si_falla_actualizar_la_meta_se_revierte_el_gasto
