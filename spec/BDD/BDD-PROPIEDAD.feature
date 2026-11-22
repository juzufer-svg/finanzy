# language: es
# Trazabilidad: REQ-N-001 · UC-004..UC-007 · INV-001, INV-002
# Las pruebas automatizadas que implementan cada escenario se indican con «Prueba:».
Característica: Aislamiento de datos entre usuarios

  @BDD-PROPIEDAD @invariante @INV-001
  Escenario: Un usuario no puede tocar datos de otro
    Dado una transacción, categoría, presupuesto o meta del usuario A
    Cuando el usuario B intenta verla, editarla, borrarla o abonar
    Entonces recibe 404 y el registro de A no cambia
    # Prueba: backend/tests/test_propiedad.py::test_inv001_otro_usuario_no_ve_edita_ni_borra_transacciones, ::test_inv001_otro_usuario_no_modifica_categorias_presupuestos_ni_metas

  @BDD-PROPIEDAD @invariante @INV-002
  Escenario: No se puede usar una categoría ajena
    Dado una categoría del usuario A
    Cuando el usuario B la usa en una transacción o presupuesto
    Entonces recibe 404
    # Prueba: backend/tests/test_propiedad.py::test_inv002_no_se_puede_usar_una_categoria_ajena
