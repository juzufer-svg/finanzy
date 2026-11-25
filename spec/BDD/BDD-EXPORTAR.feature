# language: es
# Trazabilidad: REQ-F-019 · UC-015 · CT-011 · INV-042 a INV-045 · ADR-011 · REQ-N-019 a REQ-N-021 y REQ-N-026
# Pruebas: backend/tests/test_exportar.py y frontend/tests/exportar.test.mjs (npm test, incluye la prueba del proxy: cabecerasDeDescarga y errorDeBlob). Recorrido de punta a punta con el proxy real: frontend/e2e/exportar.mjs (manual, Playwright).
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

  @BDD-EXPORTAR @borde @INV-045
  # Prueba: tests/test_exportar.py::test_inv045_origen_solo_app_o_whatsapp_las_recurrentes_y_abonos_salen_como_app
  Escenario: Una recurrente confirmada y un abono salen como App
    Dado una transacción creada al confirmar una recurrente y otra creada por un abono a meta
    Cuando exporta
    Entonces ambas dicen Origen "App" (decisión del dueño: solo App o WhatsApp)

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
  # Prueba: tests/test_exportar.py::test_h4_csv_todo_el_texto_va_entre_comillas_y_el_monto_no, ::test_h4_csv_al_releer_con_punto_y_coma_los_valores_coinciden_y_las_comillas_protegen_comas_y_saltos
  Escenario: Una coma o un punto y coma dentro del texto no parte la celda del CSV
    Dado transacciones con descripción "x,=1+1", "x;=1+1", "dijo ""hola"", =1+1" y una con salto de línea
    Cuando se exporta en CSV
    Entonces todas las celdas de texto salen entre comillas dobles y el monto sin comillas y con coma decimal
    Y al releer con «;» las descripciones coinciden con las del archivo (con un apóstrofo antes de cada fragmento peligroso)

  @BDD-EXPORTAR @invariante @INV-043
  # Prueba: tests/test_exportar.py::test_inv043_neutralizar_csv_fragmentos_tras_coma_o_punto_y_coma, ::test_inv043_csv_texto_normal_con_comas_no_cambia_y_montos_y_xlsx_no_se_tocan, ::test_h4_csv_al_releer_con_punto_y_coma_los_valores_coinciden_y_las_comillas_protegen_comas_y_saltos
  Escenario: Un lector con coma como delimitador no obtiene celdas que empiecen como fórmula
    Dado descripciones "x,=1+1", "x;=1+1", "a, =cmd", "a,@SUM(1)", "a,-1" y "pan, leche, huevos"
    Cuando se exporta en CSV
    Entonces salen "x,'=1+1", "x;'=1+1", "a,' =cmd", "a,'@SUM(1)", "a,'-1" y "pan, leche, huevos" (el CSV altera mínimamente esos textos; el monto y el xlsx no se tocan)
    Y al leer con delimitador «,» o «;» ninguna celda empieza por = + - @ tabulación o retorno de carro (también con `x,"=2+3`, `x\n"=1`, `a\r\n=1+1`; prueba de propiedad: `::test_inv043_propiedad_ninguna_celda_empieza_por_caracter_peligroso_con_ambos_delimitadores`)

  @BDD-EXPORTAR @invariante @INV-042 @INV-044
  # Prueba: tests/test_exportar.py::test_h1_supabase_* (cliente de Supabase falso), ::test_h2_*, ::test_h3_*, ::test_h5_*, ::test_c3_*
  Escenario: Lectura de Supabase, tope de simultaneidad, temporales y año acotado
    Dado la consulta a Supabase filtra por el usuario de la sesión, ordena por fecha, created_at e id y pagina de 1000 en 1000 sin saltar ni duplicar
    Y ya hay 2 exportaciones en curso
    Cuando llega una tercera
    Entonces responde 503 al instante sin encolar y /health sigue respondiendo
    Y un xlsx cortado por plazo no deja archivos temporales
    Y un usuario con una exportación en curso recibe 429 «Ya tienes una exportación en curso» en la segunda y otro usuario no se ve afectado
    Y si el cliente se desconecta el hilo se detiene y se liberan la ranura y el usuario
    Y un fallo al borrar tras guardar el libro no convierte el archivo generado en 503
    Y un mes con año fuera de 2000 a 2100 responde 422 sin consumir el límite de 10 por minuto

  @BDD-EXPORTAR @invariante @INV-043
  # Prueba: tests/test_exportar.py::test_inv043_xlsx_neutraliza_formulas_y_no_hay_celdas_de_formula
  Escenario: Lo mismo en Excel, sin apóstrofo visible
    Dado las mismas descripciones y una categoría llamada "=1+1"
    Cuando se exporta en xlsx
    Entonces ninguna celda tiene tipo fórmula (ni hay elementos de fórmula en el XML de la hoja)
    Y cada texto peligroso es una cadena explícita con quotePrefix y su valor es el texto original, sin apóstrofo antepuesto

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
    Entonces sale idéntica, sin apóstrofo ni quotePrefix

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
    Entonces recibe 422 "Hay más de 10 000 transacciones…" con codigo "exportacion_demasiadas_filas" y no se entrega ningún archivo; con exactamente 10 000 (de tamaño normal) sí

  @BDD-EXPORTAR @invariante @INV-044
  # Prueba: tests/test_exportar.py::test_inv044_mas_de_4mb_responde_422_exportacion_demasiado_grande
  Escenario: Un archivo de más de 4 MB no se entrega ni se trunca
    Dado transacciones cuyo archivo, en CSV o en xlsx, pasaría de 4 000 000 bytes
    Cuando exporta
    Entonces recibe 422 "El archivo superaría los 4 MB…" con codigo "exportacion_demasiado_grande" y no se entrega ningún archivo

  @BDD-EXPORTAR @invariante @INV-044
  # Prueba: tests/test_exportar.py::test_inv044_el_tope_de_bytes_corta_la_generacion_sin_acumular_todo
  Escenario: El servidor comprueba el tamaño mientras genera
    Dado un cliente de BD que cuenta las páginas pedidas y filas muy grandes
    Cuando se supera el tope de 4 MB a mitad del rango
    Entonces deja de pedir páginas, responde 422 y no llega a construir el archivo completo en memoria

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

  @BDD-EXPORTAR @invariante @INV-044
  # Prueba: tests/test_exportar.py::test_inv044_plazo_total_de_8s_responde_503_sin_archivo_parcial
  Escenario: Una exportación demasiado lenta se corta antes del límite del proxy
    Dado una BD que tarda 3 s por página
    Cuando se exportan 10 000 filas
    Entonces responde 503 "La exportación tardó demasiado…" a los 8 s como máximo y no entrega archivo

  @BDD-EXPORTAR @borde @INV-044
  # Prueba: tests/test_exportar.py::test_inv044_limite_de_10_descargas_por_minuto_responde_429
  Escenario: Límite de descargas
    Cuando un usuario pide 11 descargas en un minuto
    Entonces la 11.ª recibe 429 y otro usuario no se ve afectado

  @BDD-EXPORTAR @borde @REQ-N-020
  # Prueba: tests/test_exportar.py::test_req_n020_peor_caso_real_con_comillas_multibyte_y_cuenta_responde_422
  Escenario: Peor caso real de tamaño
    Dado 10 000 transacciones con descripción de 255 caracteres con comillas y caracteres de varios bytes, y la columna Cuenta
    Cuando se exporta en CSV y en xlsx
    Entonces el servidor responde 422 "exportacion_demasiado_grande" (no entrega un archivo de más de 4 000 000 bytes ni lo trunca)

  @BDD-EXPORTAR @borde @REQ-N-020
  # Prueba: tests/test_exportar.py::test_req_n020_descripciones_ascii_de_255_caracteres_caben_en_4mb
  Escenario: Descripciones largas pero normales caben
    Dado 10 000 transacciones con descripción ASCII de 255 caracteres
    Cuando se exporta en CSV y en xlsx
    Entonces cada archivo pesa menos de 4 000 000 bytes y tiene las 10 000 filas

  @BDD-EXPORTAR @invariante @REQ-N-020
  # Prueba: tests/test_exportar.py::test_req_n020_ningun_archivo_entregado_supera_4_000_000_bytes
  Escenario: Nunca se entrega un archivo de más de 4 MB
    Dado distintas combinaciones de filas, tamaños de descripción y formatos
    Cuando se exporta
    Entonces toda respuesta 200 pesa como máximo 4 000 000 bytes; el resto son 422

  @BDD-EXPORTAR @borde @REQ-N-019
  # Prueba: tests/test_exportar.py::test_req_n019_10000_filas_en_menos_de_3s_csv_y_6s_xlsx
  Escenario: Tiempo de generación
    Dado 10 000 transacciones de tamaño normal
    Cuando se exporta
    Entonces el CSV se genera en menos de 3 s y el xlsx en menos de 6 s (sin red)

  @BDD-EXPORTAR @borde @REQ-N-026
  # Prueba: tests/test_exportar.py::test_req_n026_la_generacion_no_bloquea_el_bucle_de_eventos
  Escenario: Generar el archivo no congela el servidor
    Dado una exportación de 10 000 filas en curso
    Cuando otra petición llega mientras se genera
    Entonces el bucle de eventos nunca queda bloqueado más de 0,5 s

  @BDD-EXPORTAR @borde @INV-045
  # Prueba: frontend/tests/exportar.test.mjs (rangoValido, nombreDeArchivo)
  Escenario: La interfaz no deja pedir un rango inválido
    Dado el diálogo de descarga
    Cuando se elige un rango de más de 12 meses o con inicio posterior al final
    Entonces el botón «Descargar» queda desactivado y se explica por qué

  @BDD-EXPORTAR @borde @INV-044
  # Prueba: frontend/tests/exportar.test.mjs ("errorDeBlob: 422, 429 y 503 llegan como Blob y se lee su detail", "errorDeBlob: un Blob que no es JSON usa el mensaje por defecto", "errorDeBlob: un 413 opaco de Vercel se traduce a un mensaje claro")
  Escenario: Los errores de una descarga se leen aunque lleguen como Blob
    Dado una descarga con responseType blob que recibe 422, 429, 503 o un 413 sin JSON
    Cuando la interfaz procesa el error
    Entonces el usuario ve el mensaje de detail (o el mensaje claro por defecto) con apiErrorMessage y useDialog, nunca "[object Blob]" ni un mensaje genérico

  @BDD-EXPORTAR @borde @INV-042
  # Prueba: frontend/tests/exportar.test.mjs ("cabecerasDeDescarga: reenvía Content-Disposition y Content-Type solo en exportaciones/*", "cabecerasDeDescarga: ignora Content-Disposition en cualquier otra ruta")
  # Prueba de punta a punta (manual): frontend/e2e/exportar.mjs (descarga real por el proxy, nombre del archivo, 422 visible, la cookie de sesión nunca llega al JavaScript)
  Escenario: El proxy entrega el archivo con su nombre y solo para exportaciones
    Dado una respuesta del backend con Content-Disposition
    Cuando pasa por el proxy en la ruta exportaciones/transacciones y en otra ruta
    Entonces en la primera el navegador recibe Content-Disposition y Content-Type, y en la otra solo Content-Type

  @BDD-EXPORTAR @borde @INV-045
  # Prueba: frontend/e2e/exportar.mjs (manual; comprueba que junto al botón se lee la nota del .xlsx para Excel en inglés)
  Escenario: La nota del formato seguro está junto al botón
    Dado el diálogo de descarga
    Cuando se elige CSV
    Entonces se lee «Si tu Excel está en inglés y el CSV se ve en una sola columna, descarga el .xlsx.»
