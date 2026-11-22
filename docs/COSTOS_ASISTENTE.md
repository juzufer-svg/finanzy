# Costos del asistente con Claude

> Referencia rápida del costo del chat **Asistente** (CHG-010, ADR-006). Precios consultados en noviembre de 2026;
> si cambian, la fuente oficial es https://platform.claude.com/docs/en/about-claude/pricing

## Resumen

Cuesta casi nada. Cada pregunta gasta menos de una décima de centavo de dólar, así que el saldo de la
Claude Console puede seguir mostrando lo mismo (p. ej. 5,00 US$) después de varias preguntas.

## Precio del modelo (Claude Haiku 5.5, `claude-haiku-5-5`)

| Concepto | Prompts de hasta 100.000 tokens | Prompts de más de 100.000 tokens |
|---|---|---|
| Entrada | 0,10 US$ por millón de tokens | 0,50 US$ por millón de tokens |
| Salida | 0,50 US$ por millón de tokens | 2,50 US$ por millón de tokens |

Las preguntas del asistente usan unos pocos miles de tokens, muy por debajo del límite de 100.000.
Fuente: [precios oficiales de Anthropic](https://platform.claude.com/docs/en/about-claude/pricing)
(sección *Model pricing*, filas de Claude Haiku 5.5).

## Cómo calcular el costo exacto de una pregunta

Debajo de cada respuesta del chat aparece algo como
*"Última respuesta: 4.800 tokens de entrada y 250 de salida"*. Con esos números:

```
costo (US$) = entrada × 0,10 / 1.000.000  +  salida × 0,50 / 1.000.000
```

Ejemplo con 4.800 de entrada y 250 de salida: 0,00048 + 0,000125 ≈ **0,0006 US$** (unos 2 o 3 pesos colombianos).

## Qué esperar

- Una pregunta normal gasta entre **0,0004 y 0,001 US$**. La mayor parte es entrada, porque en cada llamada
  van las instrucciones y la descripción de las herramientas.
- Con **5 US$** de saldo alcanza para unas **5.000 a 10.000 preguntas**.
- Con el tope de **30 preguntas diarias por usuario** (`ASISTENTE_PREGUNTAS_POR_USUARIO_DIA`), un usuario no
  puede gastar más de unos **3 centavos de dólar al día**. El tope global es de 300 preguntas al día
  (`ASISTENTE_PREGUNTAS_TOTALES_DIA`). Ver INV-024 en `spec/05-INVARIANTS.md`.

## Ver el gasto real

En la Claude Console (https://platform.claude.com), menú **Uso** (o **Costos**): tokens y costo por día y por
clave. Puede tardar unos minutos en actualizarse.

## Control del gasto

- El saldo es **prepagado** y la **recarga automática está desactivada**: cuando se agota, la API deja de
  responder y el asistente muestra "El asistente no tiene saldo disponible en este momento". El resto de la
  app sigue funcionando.
- La clave `ANTHROPIC_API_KEY` vive solo en Railway (nunca en Vercel ni en el repositorio).
- Para cambiar de modelo o los topes diarios: variables `ANTHROPIC_MODEL`, `ASISTENTE_PREGUNTAS_POR_USUARIO_DIA`
  y `ASISTENTE_PREGUNTAS_TOTALES_DIA` en Railway (ver `backend/.env.example`).
