# language: es
# Trazabilidad: REQ-F-020 · UC-016 · CT-012 (y CT-003 v1.2, CT-006, CT-007, CT-008, CT-009, CT-011) · INV-046 a INV-052 · ADR-009 · REQ-N-022 a REQ-N-025
# Vocabulario: «cuenta de dinero» = la entidad nueva; «cuenta» sola = cuenta de usuario; «archivada / no archivada»; «transacción» = un ingreso o gasto; «movimientos» = transacciones y transferencias juntas.
# Pruebas: fase (a) backend/tests/test_cuentas.py + backend/sql/pruebas/08_comprobar_cuentas.sql; fase (b) backend/tests/test_transferencias.py + 09_comprobar_transferencias.sql; fase (c) backend/tests/test_cuentas_integracion.py + 10_comprobar_cuentas_integracion.sql; concurrencia real en backend/sql/pruebas/probar.sh.
Característica: Cuentas de dinero con saldo y transferencias

  # ───────────── Fase (a): cuentas de dinero y saldos ─────────────

  @BDD-CUENTAS @happy-path @INV-047
  # Prueba: tests/test_cuentas.py::test_inv047_saldo_es_inicial_mas_ingresos_menos_gastos
  Escenario: El saldo se deriva de las transacciones
    Dado una cuenta de dinero "Efectivo" con saldo inicial 100000
    Cuando registro un ingreso de 50000 y un gasto de 30000 con esa cuenta de dinero
    Entonces el saldo de "Efectivo" es 120000

  @BDD-CUENTAS @invariante @INV-047
  # Prueba: tests/test_cuentas.py::test_inv047_las_transacciones_sin_cuenta_no_mueven_ningun_saldo
  Escenario: Las transacciones anteriores quedan sin cuenta de dinero
    Dado transacciones existentes sin cuenta de dinero y una cuenta de dinero nueva con saldo inicial 100000
    Entonces todas siguen con cuenta_id nulo y el saldo de la cuenta de dinero es 100000

  @BDD-CUENTAS @invariante @INV-047
  # Prueba: tests/test_cuentas.py::test_inv047_editar_y_eliminar_transaccion_recalcula
  Escenario: Editar o borrar una transacción recalcula el saldo
    Dado un gasto de 30000 en "Efectivo" (saldo 70000)
    Cuando cambio su monto a 10000, luego cambio su cuenta de dinero a "Ahorros" y luego lo elimino
    Entonces los saldos de las dos cuentas de dinero siguen la fórmula en cada paso

  @BDD-CUENTAS @invariante @INV-047
  # Prueba: tests/test_cuentas.py::test_inv047_saldo_siempre_en_cop_sin_conversion
  Escenario: El saldo se guarda en COP
    Dado un usuario con moneda de visualización USD
    Cuando consulta GET /cuentas
    Entonces los saldos vienen en COP, sin convertir

  @BDD-CUENTAS @invariante @INV-047
  # Prueba real: backend/sql/pruebas/08_comprobar_cuentas.sql (test_inv047_no_existe_columna_de_saldo_guardado)
  Escenario: No hay saldo guardado
    Cuando se revisa la tabla `cuentas` en PostgreSQL
    Entonces no tiene ninguna columna de saldo actual (solo saldo_inicial) y la función cuentas_con_saldo calcula el saldo

  @BDD-CUENTAS @invariante @INV-047
  # Prueba: tests/test_cuentas.py::test_inv047_transacciones_de_fecha_futura_cuentan_en_el_saldo
  Escenario: Una transacción con fecha futura cuenta de dinero
    Dado un gasto de 10000 con fecha del mes que viene en "Efectivo" (saldo inicial 50000)
    Entonces el saldo es 40000

  @BDD-CUENTAS @happy-path @INV-050
  # Prueba: tests/test_cuentas.py::test_cuenta_se_crea_edita_y_lista_con_saldo
  Escenario: Crear, renombrar y listar cuentas de dinero
    Cuando creo "Efectivo" (efectivo, 100000), la renombro a "Billetera" y listo las cuentas de dinero
    Entonces veo "Billetera" con su saldo y su tipo, y el tipo no se puede editar

  @BDD-CUENTAS @invariante @INV-046
  # Prueba: tests/test_cuentas.py::test_inv046_cuenta_ajena_responde_404
  Escenario: Una cuenta de dinero ajena no existe para mí
    Dado una cuenta de dinero del usuario B
    Cuando el usuario A hace GET, PUT o DELETE sobre ella
    Entonces recibe 404 "Cuenta no encontrada", idéntico al de un id inexistente

  @BDD-CUENTAS @invariante @INV-046
  # Prueba: tests/test_cuentas.py::test_inv046_transaccion_con_cuenta_ajena_404_crear_y_editar
  Escenario: No puedo registrar transacciones en la cuenta de dinero de otra persona
    Cuando A crea o edita una transacción con la cuenta de dinero de B
    Entonces recibe 404 y no se guarda ni se modifica nada

  @BDD-CUENTAS @invariante @INV-046
  # Prueba real: backend/sql/pruebas/08_comprobar_cuentas.sql
  Escenario: La BD también impide cuentas de dinero ajenas
    Cuando se inserta directamente en PostgreSQL una transacción del usuario A con la cuenta de dinero del usuario B
    Entonces falla por la llave foránea compuesta (cuenta_id, usuario_id)

  @BDD-CUENTAS @invariante @INV-048
  # Prueba: tests/test_cuentas.py::test_inv048_gasto_que_deja_saldo_negativo_se_rechaza_con_409
  Escenario: Un gasto sin saldo se rechaza
    Dado una cuenta de dinero "Efectivo" con saldo 20000
    Cuando registro un gasto de 30000 en ella
    Entonces recibe 409 "Saldo insuficiente…" y no se guarda la transacción

  @BDD-CUENTAS @invariante @INV-048
  # Prueba: tests/test_cuentas.py::test_inv048_tarjeta_de_credito_si_puede_quedar_negativa
  Escenario: La tarjeta de crédito sí puede quedar en negativo
    Dado una tarjeta de crédito con saldo 0
    Cuando registro un gasto de 30000 en ella
    Entonces se guarda y el saldo es -30000

  @BDD-CUENTAS @invariante @INV-048
  # Prueba: tests/test_cuentas.py::test_inv048_eliminar_ingreso_que_dejaria_negativo_se_rechaza
  Escenario: Borrar un ingreso ya gastado se rechaza
    Dado un ingreso de 50000 y un gasto de 40000 en "Efectivo" (saldo inicial 0)
    Cuando elimino el ingreso
    Entonces recibe 409 y el ingreso sigue existiendo

  @BDD-CUENTAS @invariante @INV-048
  # Prueba: tests/test_cuentas.py::test_inv048_editar_monto_o_cuenta_que_deja_negativo_se_rechaza
  Escenario: Editar una transacción no puede dejar un saldo negativo
    Cuando subo el monto de un gasto o paso un ingreso a otra cuenta de dinero dejando la original en negativo
    Entonces recibe 409 y la transacción queda como estaba

  @BDD-CUENTAS @invariante @INV-048
  # Prueba: tests/test_cuentas.py::test_inv048_cambiar_saldo_inicial_que_deja_negativo_se_rechaza
  Escenario: Corregir el saldo inicial tampoco puede dejar un saldo negativo
    Dado "Efectivo" con saldo inicial 100000 y gastos por 80000
    Cuando bajo el saldo inicial a 50000
    Entonces recibe 409

  @BDD-CUENTAS @invariante @INV-048
  # Prueba: tests/test_cuentas.py::test_inv048_el_rechazo_no_guarda_nada_y_traduce_el_error_de_la_bd
  Escenario: El error de la BD se traduce a 409 y no deja nada a medias
    Dado que la BD responde con el error de saldo negativo (FZ001)
    Cuando se crea una transacción
    Entonces la respuesta es 409 con mensaje legible (nunca 500 ni el texto crudo de la BD)

  @BDD-CUENTAS @invariante @INV-048
  # Prueba real: backend/sql/pruebas/probar.sh (30 INSERT simultáneos de 100 sobre una cuenta de dinero con saldo inicial 1000, con el disparador real fz001_saldo_transacciones) y 08_comprobar_cuentas.sql
  Escenario: Gastos simultáneos no pasan del saldo ni se interbloquean
    Dado una cuenta de dinero de tipo efectivo con saldo inicial 1000 y los disparadores fz001_* instalados
    Cuando llegan 30 INSERT simultáneos de una transacción de gasto de 100 (30 conexiones a la vez)
    Entonces exactamente 10 se guardan, 20 se rechazan con SQLSTATE FZ001, 0 fallan con deadlock detected (40P01) y el saldo final es 0

  @BDD-CUENTAS @invariante @INV-048
  # Prueba real: backend/sql/pruebas/08_comprobar_cuentas.sql (test_inv048_los_disparadores_fz001_son_before)
  Escenario: El disparador de saldo se dispara antes que las llaves foráneas
    Cuando se consulta pg_trigger por fz001_saldo_transacciones, fz001_saldo_transferencias y fz001_saldo_cuentas
    Entonces los tres son BEFORE (no AFTER); un disparador AFTER daría interbloqueos: el prototipo del validador con 30 INSERT simultáneos produjo 27 deadlock detected

  @BDD-CUENTAS @invariante @INV-050
  # Prueba real: backend/sql/pruebas/08_comprobar_cuentas.sql (archivar mientras otra petición registra una transacción)
  Escenario: Archivar y registrar a la vez no deja una transacción en una cuenta de dinero archivada
    Dado una cuenta de dinero no archivada y dos sesiones de PostgreSQL
    Cuando una archiva la cuenta de dinero y la otra inserta una transacción en ella al mismo tiempo
    Entonces la que llegó segunda bajo el bloqueo ve el estado ya confirmado: o la transacción se guarda y luego se archiva, o se rechaza con FZ002; nunca queda una transacción creada después del archivado

  @BDD-CUENTAS @invariante @INV-048
  # Prueba real: backend/sql/pruebas/08_comprobar_cuentas.sql
  Escenario: La regla cubre cualquier camino de escritura
    Cuando se inserta, edita o borra directamente en PostgreSQL una transacción o transferencia que dejaría una cuenta de dinero de ahorros en negativo
    Entonces la BD lo rechaza (disparador), también si viene de abonar_meta o de WhatsApp

  @BDD-CUENTAS @invariante @INV-050
  # Prueba: tests/test_cuentas.py::test_inv050_cuenta_con_transacciones_no_se_elimina_409
  Escenario: Una cuenta de dinero con transacciones se archiva, no se elimina
    Dado una cuenta de dinero con una transacción
    Cuando intento eliminarla
    Entonces recibe 409 "Archívala en lugar de eliminarla" y la cuenta de dinero sigue ahí

  @BDD-CUENTAS @invariante @INV-050
  # Prueba: tests/test_cuentas.py::test_inv050_cuenta_sin_transacciones_se_elimina
  Escenario: Una cuenta de dinero vacía sí se elimina
    Dado una cuenta de dinero sin transacciones ni transferencias
    Cuando la elimino
    Entonces recibe 200 y ya no aparece

  @BDD-CUENTAS @invariante @INV-050
  # Prueba: tests/test_cuentas.py::test_inv050_cuenta_archivada_esta_congelada
  Escenario: Una cuenta de dinero archivada no admite transacciones
    Dado una cuenta de dinero archivada
    Cuando registro, edito el monto o elimino una transacción de esa cuenta de dinero
    Entonces recibe 409 «está archivada» y tras desarchivarla funciona

  @BDD-CUENTAS @invariante @INV-050
  # Prueba: tests/test_cuentas.py::test_inv050_archivar_y_desarchivar_con_saldo_distinto_de_cero
  Escenario: Archivar y desarchivar
    Dado una cuenta de dinero con saldo 5000
    Cuando la archivo y la desarchivo
    Entonces el saldo no cambia y aparece solo con "incluir_archivadas=true" mientras esté archivada

  @BDD-CUENTAS @invariante @INV-050
  # Prueba: tests/test_cuentas.py::test_inv050_tope_de_20_cuentas
  Escenario: Máximo 20 cuentas de dinero por usuario
    Dado un usuario con 20 cuentas de dinero (no archivadas y archivadas)
    Cuando crea otra
    Entonces recibe 409 "Llegaste al máximo de 20 cuentas de dinero" y otro usuario no se ve afectado

  @BDD-CUENTAS @invariante @INV-050
  # Prueba: tests/test_cuentas.py::test_inv050_nombre_unico_por_usuario
  Escenario: Nombre repetido
    Dado una cuenta de dinero "Efectivo"
    Cuando creo " efectivo " o la renombro igual que otra
    Entonces recibe 409; otro usuario sí puede usar ese nombre

  @BDD-CUENTAS @invariante @INV-050
  # Prueba real: backend/sql/pruebas/08_comprobar_cuentas.sql (borrar un usuario con cuentas de dinero, transacciones y transferencias; 21 cuentas de dinero simultáneas)
  Escenario: Eliminar la cuenta de usuario sigue funcionando
    Dado un usuario con cuentas de dinero y transacciones con cuenta de dinero (incluida una tarjeta con saldo negativo y una cuenta de dinero con ingresos)
    Cuando se elimina el usuario
    Entonces se borran todos sus datos sin error y el disparador no bloquea la cascada (REQ-F-013, INV-021)

  @BDD-CUENTAS @invariante @INV-051
  # Prueba: tests/test_cuentas.py::test_inv051_saldo_inicial_y_montos_respetan_tope_y_dos_decimales
  Escenario: Montos de cuentas de dinero acotados
    Cuando creo una cuenta de dinero con saldo inicial 10000000000, 12.345 o -1 (que no es tarjeta)
    Entonces recibe 422; y 9999999999.99 se acepta

  @BDD-CUENTAS @invariante @INV-051
  # Prueba: tests/test_cuentas.py::test_inv051_los_montos_se_leen_con_decimal_y_rechazan_mas_de_dos_decimales
  Escenario: Los decimales se leen con precisión
    Cuando envío un monto 0.001, 12.345 o 1e-3, y luego 0.10 y 100.5
    Entonces los tres primeros reciben 422 y los dos últimos se aceptan sin error de redondeo

  @BDD-CUENTAS @invariante @INV-051
  # Prueba: tests/test_cuentas.py::test_inv051_put_solo_con_cuenta_id_valida_el_monto_guardado
  Escenario: Asignar una cuenta de dinero a una transacción vieja valida su monto guardado
    Dado una transacción guardada sin cuenta de dinero cuyo monto no cumple el tope ni los 2 decimales de INV-051 (dato anterior a CHG-019)
    Cuando hago PUT enviando solo cuenta_id
    Entonces recibe 422 «El monto de esta transacción no cumple el máximo permitido con cuenta de dinero» y no se modifica nada; con un monto válido se asigna

  @BDD-CUENTAS @borde @INV-051
  # Prueba: tests/test_cuentas.py::test_inv051_saldo_inicial_negativo_solo_en_tarjeta_de_credito
  Escenario: Deuda inicial en la tarjeta
    Cuando creo una tarjeta de crédito con saldo inicial -250000
    Entonces se acepta y el saldo es -250000

  @BDD-CUENTAS @borde @INV-051
  # Prueba: tests/test_cuentas.py::test_inv051_tipo_invalido_422
  Escenario: Tipo desconocido
    Cuando creo una cuenta de dinero de tipo "cripto"
    Entonces recibe 422

  @BDD-CUENTAS @borde @INV-004
  # Prueba: tests/test_cuentas.py::test_medio_de_pago_y_cuenta_coexisten
  Escenario: Medio de pago y cuenta de dinero conviven
    Cuando registro un gasto con medio_pago "debito" y cuenta de dinero "Ahorros"
    Entonces ambos se guardan, y quitar la cuenta de dinero no cambia el medio de pago ni al revés

  @BDD-CUENTAS @borde @INV-022
  # Prueba: tests/test_cuentas.py::test_put_conserva_quita_o_reemplaza_cuenta_como_medio_pago
  Escenario: Editar sin tocar la cuenta de dinero
    Dado un gasto con cuenta de dinero
    Cuando lo edito sin enviar cuenta_id, luego con null y luego con otra cuenta de dinero
    Entonces la conserva, la quita y la reemplaza respectivamente

  @BDD-CUENTAS @borde @REQ-N-022
  # Prueba: tests/test_cuentas.py::test_req_n022_listar_cuentas_hace_pocas_consultas
  # Prueba real: backend/sql/pruebas/08_comprobar_cuentas.sql (20 cuentas de dinero y 50 000 transacciones, plan con índice)
  Escenario: Listar cuentas de dinero es rápido
    Dado 20 cuentas de dinero y 50 000 transacciones
    Cuando se pide GET /cuentas
    Entonces se resuelve con una sola consulta SQL agregada que usa los índices por cuenta de dinero

  @BDD-CUENTAS @borde @REQ-N-025
  # Prueba real: backend/sql/pruebas/08_comprobar_cuentas.sql
  Escenario: La migración no toca los datos existentes y se puede repetir
    Dado una base con transacciones y recurrentes
    Cuando se ejecuta dos veces 2026-11-25_cuentas.sql
    Entonces el número de filas no cambia, todas tienen cuenta_id nulo y no hay errores

  @BDD-CUENTAS @invariante @INV-021
  # Prueba real: backend/sql/pruebas/08_comprobar_cuentas.sql
  Escenario: Las tablas nuevas no son accesibles desde fuera del backend
    Cuando se revisan las tablas `cuentas` (y `transferencias` en la fase b) en PostgreSQL
    Entonces tienen RLS activado, ninguna política y sin permisos para anon ni authenticated

  # ───────────── Fase (b): transferencias ─────────────

  @BDD-CUENTAS @happy-path @INV-049
  # Prueba: tests/test_transferencias.py::test_inv049_transferencia_mueve_ambos_saldos_juntos
  Escenario: Transferir entre mis cuentas de dinero
    Dado "Efectivo" con 100000 y "Ahorros" con 0
    Cuando transfiero 40000 de "Efectivo" a "Ahorros"
    Entonces "Efectivo" queda en 60000 y "Ahorros" en 40000

  @BDD-CUENTAS @invariante @INV-049
  # Prueba: tests/test_transferencias.py::test_inv049_no_cuenta_como_ingreso_ni_gasto_en_resumen_presupuestos_reportes_asistente
  Escenario: Una transferencia no es ingreso ni gasto
    Dado una transferencia de 40000 en el mes
    Cuando consulto el resumen del mes, el gasto de un presupuesto, GET /transacciones, las herramientas del asistente y la exportación
    Entonces ninguna la cuenta de dinero ni la muestra como transacción

  @BDD-CUENTAS @invariante @INV-049
  # Prueba: tests/test_transferencias.py::test_inv049_aparece_en_la_lista_de_movimientos
  Escenario: Se ve en la lista de movimientos
    Cuando listo GET /transferencias?mes=2026-11
    Entonces veo la transferencia con origen, destino, monto y fecha

  @BDD-CUENTAS @invariante @INV-049
  # Prueba: tests/test_transferencias.py::test_inv049_origen_y_destino_deben_ser_distintos_422
  Escenario: Origen y destino distintos
    Cuando transfiero de "Efectivo" a "Efectivo"
    Entonces recibe 422 "Elige dos cuentas de dinero distintas"

  @BDD-CUENTAS @invariante @INV-049
  # Prueba: tests/test_transferencias.py::test_inv049_saldo_insuficiente_en_origen_409_y_no_mueve_nada
  Escenario: Sin saldo en el origen
    Dado "Efectivo" con 10000
    Cuando transfiero 40000 a "Ahorros"
    Entonces recibe 409 y ningún saldo cambia

  @BDD-CUENTAS @invariante @INV-049
  # Prueba: tests/test_transferencias.py::test_inv049_desde_una_tarjeta_de_credito_se_permite_quedar_negativa
  Escenario: Adelanto de la tarjeta
    Cuando transfiero 30000 desde una tarjeta de crédito con saldo 0 a "Efectivo"
    Entonces se guarda y la tarjeta queda en -30000

  @BDD-CUENTAS @invariante @INV-049
  # Prueba: tests/test_transferencias.py::test_inv049_pagar_la_tarjeta_sube_su_saldo
  Escenario: Pagar la tarjeta
    Dado una tarjeta con saldo -30000 y "Ahorros" con 100000
    Cuando transfiero 30000 de "Ahorros" a la tarjeta
    Entonces la tarjeta queda en 0 y "Ahorros" en 70000

  @BDD-CUENTAS @invariante @INV-049
  # Prueba: tests/test_transferencias.py::test_inv049_eliminar_transferencia_restablece_saldos
  Escenario: Eliminar una transferencia
    Cuando elimino una transferencia
    Entonces los saldos vuelven a los de antes; si dejara el destino en negativo (y no es tarjeta) recibe 409

  @BDD-CUENTAS @invariante @INV-049
  # Prueba: tests/test_transferencias.py::test_inv049_cuenta_archivada_no_puede_ser_origen_ni_destino
  Escenario: Cuentas archivadas no participan
    Cuando transfiero desde o hacia una cuenta de dinero archivada
    Entonces recibe 409

  @BDD-CUENTAS @invariante @INV-046
  # Prueba: tests/test_transferencias.py::test_inv046_transferencia_con_cuenta_ajena_404
  Escenario: Transferir con la cuenta de dinero de otro
    Cuando A transfiere usando una cuenta de dinero de B como origen o como destino
    Entonces recibe 404 sin decir cuál de las dos falló, y A no puede ver ni borrar transferencias de B

  @BDD-CUENTAS @invariante @INV-049
  # Prueba: tests/test_transferencias.py::test_inv051_transferencia_monto_cero_negativo_o_sobre_el_tope_422
  Escenario: Monto de transferencia inválido
    Cuando transfiero 0, -5, 12.345 o 10000000000
    Entonces recibe 422

  @BDD-CUENTAS @invariante @INV-049
  # Prueba real: backend/sql/pruebas/probar.sh (20 transferencias simultáneas desde una cuenta de dinero con 1000) y 09_comprobar_transferencias.sql
  Escenario: Transferencias simultáneas no pasan del saldo y son atómicas
    Dado una cuenta de dinero de tipo efectivo con saldo 1000
    Cuando llegan 20 transferencias simultáneas de 100 hacia otra cuenta de dinero
    Entonces exactamente 10 se guardan, la suma de los dos saldos no cambia y el origen termina en 0

  @BDD-CUENTAS @invariante @INV-049
  # Prueba real: backend/sql/pruebas/probar.sh (20 transferencias A→B y 20 B→A simultáneas, disparador fz001_saldo_transferencias)
  Escenario: Transferencias cruzadas simultáneas no se interbloquean
    Dado dos cuentas de dinero A y B de tipo efectivo con saldo 1000 cada una
    Cuando llegan 20 transferencias de 100 de A a B y 20 de 100 de B a A al mismo tiempo
    Entonces 0 fallan con deadlock detected (40P01), ninguna cuenta de dinero queda en negativo y la suma de los dos saldos sigue siendo 2000

  @BDD-CUENTAS @invariante @INV-049
  # Prueba real: backend/sql/pruebas/09_comprobar_transferencias.sql
  Escenario: La BD impide transferencias inconsistentes
    Cuando se inserta directamente una transferencia con origen = destino, con monto <= 0 o con cuentas de dinero de distinto usuario
    Entonces PostgreSQL la rechaza (CHECK y llaves compuestas)

  @BDD-CUENTAS @invariante @INV-047
  # Prueba: tests/test_transferencias.py::test_inv047_saldo_incluye_transferencias
  Escenario: El saldo incluye transferencias
    Cuando consulto GET /cuentas tras una transferencia
    Entonces el saldo de cada cuenta de dinero suma las recibidas y resta las enviadas

  # ───────────── Fase (c): integraciones ─────────────

  @BDD-CUENTAS @happy-path @INV-052
  # Prueba: tests/test_cuentas_integracion.py::test_inv052_abono_a_meta_con_cuenta_descuenta_el_saldo
  Escenario: Abonar a una meta desde una cuenta de dinero
    Dado "Ahorros" con 100000 y una meta
    Cuando abono 30000 indicando "Ahorros"
    Entonces la meta sube 30000, se registra el gasto "Ahorro" con esa cuenta de dinero y "Ahorros" queda en 70000

  @BDD-CUENTAS @invariante @INV-052
  # Prueba: tests/test_cuentas_integracion.py::test_inv052_abono_con_saldo_insuficiente_no_suma_a_la_meta_ni_registra_gasto
  # Prueba real: backend/sql/pruebas/10_comprobar_cuentas_integracion.sql
  Escenario: Abono sin saldo
    Dado "Efectivo" con 10000
    Cuando abono 30000 desde "Efectivo"
    Entonces recibe 409 y ni la meta ni la categoría "Ahorro" ni el saldo cambian (INV-008)

  @BDD-CUENTAS @invariante @INV-052
  # Prueba: tests/test_cuentas_integracion.py::test_inv052_abono_con_cuenta_ajena_404_y_sin_funcion_sql_responde_503
  Escenario: Abono con cuenta de dinero ajena o sin la función nueva
    Cuando abono con la cuenta de dinero de otro usuario, o con cuenta de dinero y sin la función SQL actualizada
    Entonces recibe 404 en el primer caso y 503 en el segundo, sin usar el método no atómico

  @BDD-CUENTAS @invariante @INV-046
  # Prueba: tests/test_cuentas_integracion.py::test_inv046_recurrente_con_cuenta_ajena_404_crear_editar_y_confirmar
  Escenario: Una recurrente no puede usar la cuenta de dinero de otra persona
    Cuando A crea o edita una recurrente con la cuenta de dinero de B, o confirma una propia con cuenta_id de B
    Entonces recibe 404 «Cuenta no encontrada» en los tres casos, no se guarda ni se modifica nada y la próxima fecha no avanza

  @BDD-CUENTAS @happy-path @INV-052
  # Prueba: tests/test_cuentas_integracion.py::test_inv052_recurrente_con_cuenta_crea_la_transaccion_en_esa_cuenta
  Escenario: Confirmar una recurrente con cuenta de dinero
    Dado una recurrente de gasto con cuenta de dinero "Efectivo"
    Cuando la confirmo
    Entonces la transacción se crea con esa cuenta de dinero y la fecha avanza

  @BDD-CUENTAS @invariante @INV-052
  # Prueba: tests/test_cuentas_integracion.py::test_inv052_recurrente_con_cuenta_archivada_o_sin_saldo_no_avanza
  Escenario: Confirmar una recurrente que no se puede registrar
    Dado una recurrente cuya cuenta de dinero está archivada o sin saldo
    Cuando la confirmo
    Entonces recibe 409, no se crea la transacción y la próxima fecha no avanza (INV-025, INV-026)

  @BDD-CUENTAS @invariante @INV-052
  # Prueba: tests/test_cuentas_integracion.py::test_inv052_confirmar_recurrente_es_una_sola_operacion_atomica_y_no_avanza_si_falla
  # Prueba real: backend/sql/pruebas/10_comprobar_cuentas_integracion.sql (función confirmar_recurrente)
  Escenario: Confirmar una recurrente es todo o nada
    Dado una recurrente cuya confirmación falla en la BD (saldo insuficiente, cuenta de dinero archivada o error al insertar)
    Cuando la confirmo
    Entonces el backend llama a UNA sola función SQL (no avanza la fecha y luego intenta revertirla), la transacción no existe y proxima_fecha sigue siendo la que vio la persona

  @BDD-CUENTAS @invariante @INV-052
  # Prueba: tests/test_cuentas_integracion.py::test_inv052_doble_confirmacion_solo_crea_una_transaccion
  # Prueba real: backend/sql/pruebas/probar.sh (2 confirmaciones simultáneas de la misma ocurrencia)
  Escenario: Dos confirmaciones a la vez crean una sola transacción
    Dado una recurrente con una ocurrencia pendiente
    Cuando llegan dos confirmaciones simultáneas de esa ocurrencia
    Entonces una crea la transacción y avanza la fecha, la otra recibe 409 y no se crea una segunda transacción

  @BDD-CUENTAS @invariante @INV-052
  # Prueba: tests/test_cuentas_integracion.py::test_inv052_confirmar_sin_la_funcion_sql_responde_503_y_no_usa_el_metodo_anterior
  Escenario: Sin la función SQL nueva no se confirma
    Dado que la función confirmar_recurrente no existe en la BD (migración sin aplicar)
    Cuando se confirma una recurrente
    Entonces recibe 503 y no se usa el flujo anterior (avanzar y luego crear)

  @BDD-CUENTAS @happy-path @INV-052
  # Prueba: tests/test_cuentas_integracion.py::test_inv052_whatsapp_cuenta_solo_si_el_usuario_la_nombra
  Escenario: WhatsApp con cuenta de dinero nombrada
    Cuando el mensaje dice "almorcé 18 mil con débito desde Ahorros" y la IA propone la cuenta de dinero "Ahorros"
    Entonces el backend la busca entre las cuentas de dinero no archivadas del usuario y registra el gasto con esa cuenta de dinero

  @BDD-CUENTAS @invariante @INV-052
  # Prueba: tests/test_cuentas_integracion.py::test_inv052_whatsapp_sin_cuenta_nombrada_registra_sin_cuenta
  Escenario: WhatsApp sin nombrar cuenta de dinero
    Cuando el mensaje no nombra ninguna cuenta de dinero aunque la IA proponga una
    Entonces la transacción se registra sin cuenta de dinero

  @BDD-CUENTAS @invariante @INV-052
  # Prueba: tests/test_cuentas_integracion.py::test_inv052_whatsapp_cuenta_inexistente_o_sin_saldo_no_registra
  Escenario: WhatsApp con cuenta de dinero que no existe o sin saldo
    Cuando el mensaje nombra una cuenta de dinero inexistente, archivada o sin saldo suficiente
    Entonces no se registra nada y la respuesta lo explica sin revelar datos de otros

  @BDD-CUENTAS @invariante @INV-052
  # Prueba: tests/test_cuentas_integracion.py::test_inv052_whatsapp_no_envia_saldos_ni_ids_a_claude
  Escenario: Claude solo ve nombres
    Cuando se arma la petición a Claude
    Entonces incluye los nombres de las cuentas de dinero no archivadas pero ningún saldo, id ni correo (INV-029)

  @BDD-CUENTAS @invariante @INV-052
  # Prueba: tests/test_cuentas_integracion.py::test_inv052_whatsapp_no_crea_transferencias
  Escenario: WhatsApp no mueve dinero entre cuentas de dinero
    Cuando el usuario pide por WhatsApp transferir entre cuentas de dinero
    Entonces no se crea ninguna transferencia

  @BDD-CUENTAS @invariante @INV-052
  # Prueba: tests/test_cuentas_integracion.py::test_inv052_asistente_cuentas_y_saldos_es_solo_lectura
  Escenario: El asistente consulta saldos sin poder cambiarlos
    Cuando el asistente usa cuentas_y_saldos
    Entonces solo lee las cuentas de dinero del usuario del token, sin ids hacia Claude, y no existe herramienta que cree o cambie cuentas de dinero (INV-023)

  @BDD-CUENTAS @invariante @INV-052
  # Prueba: tests/test_cuentas_integracion.py::test_inv052_exportar_incluye_columna_cuenta_al_final_y_no_incluye_transferencias
  Escenario: La exportación gana la columna Cuenta
    Cuando exporto transacciones con y sin cuenta de dinero
    Entonces la columna 8 «Cuenta» trae el nombre o queda vacía, las columnas 1 a 7 no cambian y no hay transferencias
