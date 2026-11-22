# language: es
# Trazabilidad: REQ-F-003 · UC-003 · INV-007, INV-009
# Las pruebas automatizadas que implementan cada escenario se indican con «Prueba:».
Característica: Recuperar contraseña

  @BDD-RECUPERACION @happy-path
  Escenario: Restablecer la contraseña con el código
    Dado una cuenta existente
    Cuando pide restablecer y usa el código con una contraseña nueva válida
    Entonces puede iniciar sesión con la nueva y no con la anterior
    # Prueba: backend/tests/test_codigos.py::test_restablecer_contrasena_flujo_completo

  @BDD-RECUPERACION @invariante @INV-009
  Escenario: No se revela si un correo está registrado
    Dado un correo registrado y otro no registrado
    Cuando se pide restablecer para ambos
    Entonces la respuesta es idéntica
    # Prueba: backend/tests/test_codigos.py::test_inv009_forgot_password_responde_igual_exista_o_no

  @BDD-RECUPERACION @invariante @INV-007
  Escenario: El código es de un solo uso
    Dado un código de restablecimiento ya usado
    Cuando se intenta usar de nuevo
    Entonces se rechaza
    # Prueba: backend/tests/test_codigos.py::test_inv007_codigo_de_un_solo_uso
