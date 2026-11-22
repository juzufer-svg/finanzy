# language: es
# Trazabilidad: REQ-F-NNN · UC-NNN · INV-NNN
Característica: {{Gestión de incidencias}}

  @BDD-UC-NNN @happy-path
  Escenario: {{Un técnico resuelve una incidencia}}
    Dado una incidencia en estado "en_progreso"
    Y existe un técnico asignado
    Cuando el técnico registra una descripción de resolución
    Entonces el estado cambia a "resuelta"
    Y se guarda quién realizó la acción y cuándo

  @BDD-UC-NNN @invariante @INV-001
  Escenario: {{No se puede resolver sin técnico asignado}}
    Dado una incidencia en estado "en_progreso"
    Y no existe técnico asignado
    Cuando se intenta registrar la resolución
    Entonces el sistema rechaza la acción con un error de negocio claro
    Y el estado sigue siendo "en_progreso"
