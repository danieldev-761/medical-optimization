"""Compresión por plantillas semánticas para traducción masiva.

Reemplaza entidades variables (fechas, horas, especialidades) por marcadores
de posición genéricos ({DATE}, {TIME}, {SPEC}) para abstraer miles de mensajes
en un número muy reducido de plantillas estructurales.
"""

from __future__ import annotations

import re

# Patrones de coincidencia para abstracción de variables
_DATE_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}(/\d{2,4})?\b|"
    r"\b(el|la|para el|para|en el)\s+\d{1,2}\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\b|"
    r"\b(lunes|martes|miercoles|jueves|viernes|sabado|domingo)\b|\bpasado manana\b|\bmanana\b",
    re.IGNORECASE,
)

_TIME_RE = re.compile(
    r"\b\d{1,2}(:\d{2})?\s*(am|pm)\b|\b(a las|alas|sobre)\s+\d{1,2}(:\d{2})?\b|\b(por la|en la|de la)?\s*(manana|tarde|noche)\b",
    re.IGNORECASE,
)


def extract_template(text: str) -> tuple[str, dict[str, str]]:
    """Convierte un mensaje limpio en una plantilla neutral y extrae sus variables.

    Ejemplo:
    "Quiero agendar cita para el 15 de Octubre a las 10am" ->
    ("Quiero agendar cita para {DATE} {TIME}", {"DATE": "el 15 de Octubre", "TIME": "a las 10am"})
    """
    if not text:
        return "", {}

    vars_found: dict[str, str] = {}

    def replace_date(match: re.Match) -> str:
        vars_found["{DATE}"] = match.group(0)
        return "{DATE}"

    def replace_time(match: re.Match) -> str:
        vars_found["{TIME}"] = match.group(0)
        return "{TIME}"

    template = _DATE_RE.sub(replace_date, text)
    template = _TIME_RE.sub(replace_time, template)
    template = re.sub(r"\s+", " ", template).strip()

    return template, vars_found


def reconstruct_translation(template_translation: str, vars_found: dict[str, str]) -> str:
    """Reinyecta las variables extraídas en la plantilla traducida."""
    result = template_translation
    for placeholder, val in vars_found.items():
        result = result.replace(placeholder, val)
    return result
