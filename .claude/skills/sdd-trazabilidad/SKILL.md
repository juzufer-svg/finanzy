---
name: sdd-trazabilidad
description: Actualiza spec/TRACEABILITY.md relacionando requerimientos, casos de uso, contratos, implementación y pruebas. Úsalo al terminar cualquier cambio que toque código o spec.
---

# Actualizar la trazabilidad

1. Identifica los REQ afectados por el cambio (`work/changes/CHG-*.md`).
2. Para cada REQ, asegura una fila en `spec/TRACEABILITY.md` con: `REQ | UC | Contrato | Implementación (ruta) | Pruebas (ruta/id BDD) | Estado`.
3. Rutas reales: verifica que los archivos existen (`Glob`) antes de anotarlos.
4. Estado: `Especificado` → `Implementado` → `Verificado` (solo si el validador ejecutó las pruebas con éxito).
5. Si encuentras un REQ sin UC/prueba, o código sin REQ, agrégalo como hallazgo; no inventes el vínculo.
