# language: es
# Trazabilidad: REQ-F-019 · UC-015 · CT-011 · INV-042 a INV-045 · ADR-011 · REQ-N-019 a REQ-N-021
# Pruebas: backend/tests/test_exportar.py y frontend/tests/exportar.test.mjs (npm test). Recorrido de punta a punta con el proxy: frontend/e2e/exportar.mjs (manual, Playwright).
Característica: Exportar transacciones a CSV o Excel

  @BDD-EXPORTAR @happy-path @INV-045
  # Prueba: tests/test_exportar.py::test_inv045_csv_utf8_con_bom_separador_punto_y_coma_y_columnas
  Escenario: Descargar el mes en CSV
    Dado un usuario con 3 transacciones en 2026-11 y 2 en 2026-10
    Cuando pide "desde=2026-11&formato=csv"
    Entonces recibe 200 con un CSV UTF-8 con BOM, separador ";" y las columnas Fecha, Tipo, Categoría, Descripción, Medio de pago, Monto (COP), Origen
    Y el archivo tiene 3 filas de datos ordenadas por fecha ascendente
    Y "Content-Disposition" es attachment con filename "finanzy-transacciones-2026-11.csv"

  @BDD-EXPORTAR @happy-path @INV-045
  # Prueba: tests/test_exportar.py::test_inv045_xlsx_se_abre_con_openpyxl_y_tiene_hoja_transacciones
  Escenario: Descargar un rango en Excel
    Dado un usuario con transacciones de 2026-09 a 2026-11
    Cuando pide "desde=2026-09&hasta=2026-11&formato=xlsx"
    Entonces recibe 200 con un .xlsx con una hoja "Transacciones", fecha como fecha real y monto como número
    Y el nombre es "finanzy-transacciones-2026-09_a_2026-11.xlsx"

  @BDD-EXPORTAR @invariante @INV-045
  # Prueba: tests/test_exportar.py::test_inv045_montos_en_cop_tal_como_se_guardan
  Escenario: Los montos no cambian con la moneda de visualización
    Dado un usuario cuya moneda es USD y una transacción de 42000.50 guardada
    Cuando exporta
    Entonces el monto del archivo es 42000,50 (CSV) o 42000.5 (xlsx), en COP

  @BDD-EXPORTAR @borde @INV-045
  # Prueba: tests/test_exportar.py::test_inv045_sin_filas_exporta_solo_encabezados
  Escenario: Un mes sin transacciones
    Dado un usuario sin transacciones en el rango
    Cuando exporta
    Entonces recibe 200 con solo la fila de encabezados

  @BDD-EXPORTAR @borde @INV-045
  # Prueba: tests/test_exportar.py::test_inv045_origen_whatsapp_y_app_y_medio_de_pago_en_espanol
  Escenario: Origen y medio de pago legibles
    Dado una transacción creada por WhatsApp con débito y otra creada en la app sin medio de pago
    Cuando exporta
    Entonces la primera dice Origen "WhatsApp" y Medio de pago "Débito", y la segunda "App" y vacío

  @BDD-EXPORTAR @invariante @INV-042
  # Prueba: tests/test_exportar.py::test_inv042_exporta_solo_las_transacciones_del_usuario_de_la_sesion
  Escenario: No se mezclan datos de otras personas
    Dado dos usuarios A y B con transacciones en el mismo mes
    Cuando A exporta
    Entonces el archivo contiene solo las de A

  @BDD-EXPORTAR @invariante @INV-042
  # Prueba: tests/test_exportar.py::test_inv042_no_acepta_usuario_en_la_peticion
  Escenario: Un parámetro de usuario se ignora
    Cuando A pide "desde=2026-11&usuario_id=<id de B>" o con un encabezado de usuario ajeno
    Entonces el archivo es el de A

  @BDD-EXPORTAR @invariante @INV-042
  # Prueba: tests/test_exportar.py::test_inv042_sin_sesion_responde_401
  Escenario: Sin sesión no hay descarga
    Cuando una persona sin sesión pide la exportación
    Entonces recibe 401 y ningún dato

  @BDD-EXPORTAR @invariante @INV-042
  # Prueba: tests/test_exportar.py::test_inv042_cabeceras_no_store_y_nombre_sin_datos_personales
  Escenario: El archivo no se guarda en cachés ni delata a su dueño
    Cuando se exporta
    Entonces la respuesta lleva "Cache-Control: no-store" y "X-Content-Type-Options: nosniff"
    Y el nombre del archivo no contiene nombre, correo ni ids

  @BDD-EXPORTAR @invariante @INV-042
  # Prueba: tests/test_exportar.py::test_inv042_el_archivo_no_contiene_ids_ni_correo
  Escenario: Sin identificadores internos
    Cuando se exporta
    Entonces ninguna celda contiene el id del usuario, de la transacción o de la categoría ni el correo

  @BDD-EXPORTAR @invariante @INV-042
  # Prueba: tests/test_exportar.py::test_inv042_la_categoria_ajena_no_se_filtra
  Escenario: Una categoría ajena no aparece
    Dado una transacción cuya categoría pertenece a otro usuario (dato corrupto)
    Cuando se exporta
    Entonces la categoría sale como "Sin categoría" y nunca el nombre ajeno

  @BDD-EXPORTAR @invariante @INV-043
  # Prueba: tests/test_exportar.py::test_inv043_csv_neutraliza_formulas
  Escenario: Una descripción maliciosa no ejecuta fórmulas en CSV
    Dado transacciones con descripción "=HYPERLINK(""http://x"")", "+1+1", "-2+3", "@SUM(A1)", "\t=1" y "\r=1"
    Cuando se exporta en CSV
    Entonces cada una empieza con un apóstrofo y ninguna celda de texto empieza por = + - @ tabulación o retorno de carro

  @BDD-EXPORTAR @invariante @INV-043
  # Prueba: tests/test_exportar.py::test_inv043_xlsx_neutraliza_formulas_y_no_hay_celdas_de_formula
  Escenario: Lo mismo en Excel
    Dado las mismas descripciones y una categoría llamada "=1+1"
    Cuando se exporta en xlsx
    Entonces ninguna celda tiene tipo fórmula, y los textos peligrosos llevan el apóstrofo

  @BDD-EXPORTAR @borde @INV-043
  # Prueba: tests/test_exportar.py::test_inv043_montos_y_fechas_no_se_prefijan
  Escenario: Los números no se alteran
    Dado un gasto de 0.5 y una fecha 2026-11-01
    Cuando se exporta
    Entonces el monto y la fecha salen sin apóstrofo (son numéricos o ISO)

  @BDD-EXPORTAR @borde @INV-043
  # Prueba: tests/test_exportar.py::test_inv043_texto_normal_no_se_modifica
  Escenario: Un texto normal queda igual
    Dado una descripción "Almuerzo - menú del día"
    Cuando se exporta
    Entonces sale idéntica, sin apóstrofo

  @BDD-EXPORTAR @invariante @INV-044
  # Prueba: tests/test_exportar.py::test_inv044_rango_mayor_de_12_meses_responde_422
  Escenario: Más de 12 meses se rechaza
    Cuando pide "desde=2025-01&hasta=2026-02"
    Entonces recibe 422 "Puedes exportar hasta 12 meses por archivo" y 12 meses exactos se aceptan

  @BDD-EXPORTAR @invariante @INV-044
  # Prueba: tests/test_exportar.py::test_inv044_mas_de_10000_filas_responde_422_sin_truncar
  Escenario: Demasiadas filas no se truncan en silencio
    Dado un usuario con 10 001 transacciones en el rango
    Cuando exporta
    Entonces recibe 422 "Hay más de 10 000 transacciones…" y no se entrega ningún archivo; con exactamente 10 000 sí

  @BDD-EXPORTAR @invariante @INV-044
  # Prueba: tests/test_exportar.py::test_inv044_pagina_todas_las_filas_mas_alla_de_1000
  Escenario: PostgREST no recorta el archivo a 1000 filas
    Dado un usuario con 2 500 transacciones en el mes y un cliente que devuelve como máximo 1000 por consulta
    Cuando exporta
    Entonces el archivo tiene las 2 500 filas, sin duplicadas ni faltantes

  @BDD-EXPORTAR @invariante @INV-044
  # Prueba: tests/test_exportar.py::test_inv044_parametros_invalidos_responden_422
  Escenario: Parámetros inválidos
    Cuando pide mes "2026-13", desde posterior a hasta, o formato "pdf"
    Entonces recibe 422 con un mensaje claro y no se consulta la BD

  @BDD-EXPORTAR @invariante @INV-044
  # Prueba: tests/test_exportar.py::test_inv044_error_de_la_bd_responde_503_sin_archivo_parcial
  Escenario: Si la BD falla a mitad de la paginación
    Dado que la segunda página de la consulta falla
    Cuando exporta
    Entonces responde 503 y no entrega un archivo parcial (INV-013)

  @BDD-EXPORTAR @borde @REQ-N-019
  # Prueba: tests/test_exportar.py::test_inv044_limite_de_10_descargas_por_minuto_responde_429
  Escenario: Límite de descargas
    Cuando un usuario pide 11 descargas en un minuto
    Entonces la 11.ª recibe 429 y otro usuario no se ve afectado

  @BDD-EXPORTAR @borde @REQ-N-020
  # Prueba: tests/test_exportar.py::test_req_n020_peor_caso_10000_filas_cabe_en_4mb
  Escenario: Peor caso de tamaño
    Dado 10 000 transacciones con descripción de 255 caracteres
    Cuando se exporta en CSV y en xlsx
    Entonces cada archivo pesa menos de 4 MB

  @BDD-EXPORTAR @borde @REQ-N-019
  # Prueba: tests/test_exportar.py::test_req_n019_10000_filas_en_menos_de_3s_csv_y_8s_xlsx
  Escenario: Tiempo de generación
    Dado 10 000 transacciones
    Cuando se exporta
    Entonces el CSV se genera en menos de 3 s y el xlsx en menos de 8 s (sin red)

  @BDD-EXPORTAR @borde @INV-045
  # Prueba: frontend/tests/exportar.test.mjs (rangoValido, nombreDeArchivo)
  Escenario: La interfaz no deja pedir un rango inválido
    Dado el diálogo de descarga
    Cuando se elige un rango de más de 12 meses o con inicio posterior al final
    Entonces el botón «Descargar» queda desactivado y se explica por qué
