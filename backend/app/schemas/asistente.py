"""
Validaciones del asistente con Claude (CHG-010, CT-007).
"""
from typing import Literal

from pydantic import BaseModel, Field

MAX_PREGUNTA = 500
MAX_TEXTO_HISTORIAL = 2000
MAX_MENSAJES_HISTORIAL = 10


class MensajeHistorial(BaseModel):
    rol: Literal["usuario", "asistente"]
    texto: str = Field(..., min_length=1, max_length=MAX_TEXTO_HISTORIAL)


class PreguntaAsistente(BaseModel):
    pregunta: str = Field(..., min_length=1, max_length=MAX_PREGUNTA)
    # Conversación previa (solo texto). El cliente envía las últimas preguntas y respuestas
    # para que Claude entienda preguntas de seguimiento ("¿y el mes pasado?").
    historial: list[MensajeHistorial] = Field(default_factory=list, max_length=MAX_MENSAJES_HISTORIAL)


class UsoAsistente(BaseModel):
    input_tokens: int
    output_tokens: int


class RespuestaAsistente(BaseModel):
    respuesta: str
    modelo: str
    uso: UsoAsistente
