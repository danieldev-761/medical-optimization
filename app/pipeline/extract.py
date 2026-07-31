"""Extracción heurística de accion, especialidad, fecha_solicitada y preferencia_horario.

Enfoque conservador por regex/diccionarios, sin costo por llamada externa.
Los campos pueden quedar vacíos cuando no se mencionan explícitamente.
"""

import re

from .preprocess import normalize_ascii

# --- Acción -------------------------------------------------------------------

ACCION_PATTERNS: list[tuple[str, list[str]]] = [
    (
        "cancelar",
        [
            r"\bcancel(ar|acion|a|ado|arlo|o)?\b",
            r"\banul(ar|acion|a|ado)?\b",
            r"\bno (podre|voy a poder|puedo) asistir\b",
            r"\bno asistire\b",
            r"\bno (me|voy a) presentar(e)?\b",
            r"\bdar de baja\b",
            r"\bborrar la cita\b",
        ],
    ),
    (
        "reprogramar",
        [
            r"\breprogram(ar|acion|a|ado|arlo)?\b",
            r"\breagend(ar|amiento|a)?\b",
            r"\bcambiar (la fecha|la cita|de fecha|el dia|el horario)\b",
            r"\bmodificar (la fecha|el horario|mi cita|la cita|mi turno)\b",
            r"\bmover (la cita|la fecha|mi cita)\b",
            r"\bposponer\b",
            r"\bposterg(ar|arla|arlo|acion|amiento)\b",
            r"\baplazar\b",
            r"\badelantar (mi turno|mi cita|el turno|la cita|mi consulta|la consulta|mi control)\b",
            r"\bagendar (para|otra vez|de nuevo|nuevamente)\b",
            r"\bfecha alternativa\b",
        ],
    ),
    (
        "confirmar",
        [
            r"\bconfirm(ar|acion|o|a|amos|andola|andolo)?\b",
            r"\breafirm(ar|acion|o)?\b",
            r"\bsi, quiero (mantener|confirmar)\b",
            r"\bconfirmada\b",
        ],
    ),
]

ACCION_COMPILED: list[tuple[str, list[re.Pattern]]] = [
    (accion, [re.compile(pat, re.IGNORECASE) for pat in pats])
    for accion, pats in ACCION_PATTERNS
]

CONFIRM_NEGATIONS = re.compile(r"\bno quiero confirmar\b|\bdesconfirmar\b", re.IGNORECASE)


def _norm(text: str) -> str:
    return normalize_ascii(text).lower()


def extract_accion(text: str) -> str:
    return _extract_accion(_norm(text))


def _extract_accion(t: str) -> str:
    if CONFIRM_NEGATIONS.search(t):
        return ""
    for accion, patterns in ACCION_COMPILED:
        for pat in patterns:
            if pat.search(t):
                return accion
    return ""


# --- Especialidad -------------------------------------------------------------

ESPECIALIDADES: dict[str, list[str]] = {
    "cardiologia": [r"\bcardio\w*"],
    "dermatologia": [r"\bdermatolo\w*", r"\bpiel\b"],
    "ginecologia": [r"\bgineco\w*"],
    "pediatria": [r"\bpediatra\w*", r"\bpedia\w*"],
    "medicina general": [r"\bmedicina general\b", r"\bmedico general\b", r"\bgeneralista\b"],
    "oftalmologia": [r"\boftalmo\w*", r"\bojo\b", r"\bojos\b"],
    "otorrinolaringologia": [r"\boto(rrino|rinola)?\w*"],
    "traumatologia": [r"\btraumat\w*"],
    "neurologia": [r"\bneuro\w*"],
    "psicologia": [r"\bpsicolo\w*", r"\bpsiquiatra\w*", r"\bpsiquiatria\b"],
    "odontologia": [r"\bodonto\w*", r"\bdentista\b", r"\bdental\b"],
    "urologia": [r"\burolog\w*"],
    "endocrinologia": [r"\bendocrin\w*"],
    "gastroenterologia": [r"\bgastro(enterol)?\w*", r"\bgastro\b"],
    "nutricion": [r"\bnutricio\w*", r"\bnutriolog\w*"],
    "fisioterapia": [r"\bfisio\w*"],
    "oncologia": [r"\boncolog\w*"],
    "nefrologia": [r"\bnefrolog\w*"],
    "reumatologia": [r"\breumat\w*"],
    "geriatria": [r"\bgeriatr\w*", r"\bgeronto\w*"],
    "maternidad": [r"\bmatemidad\b", r"\bembarazo\b", r"\bobstetricia\b", r"\bobstetra\b"],
    "laboratorio": [r"\blaboratorio\b", r"\bexamenes?\b", r"\banalisis\b", r"\bprueba de sangre\b"],
    "radiologia": [r"\bradiolog\w*", r"\brayos x\b", r"\bresonancia\b", r"\becografia\b", r"\beco \b"],
    "vacunacion": [r"\bvacun(a|acion|as)\b", r"\bvacuna\b"],
}

ESPECIALIDADES_COMPILED: dict[str, list[re.Pattern]] = {
    esp: [re.compile(pat, re.IGNORECASE) for pat in pats]
    for esp, pats in ESPECIALIDADES.items()
}


def extract_especialidad(text: str) -> str:
    return _extract_especialidad(_norm(text))


def _extract_especialidad(t: str) -> str:
    for especialidad, patterns in ESPECIALIDADES_COMPILED.items():
        for pat in patterns:
            if pat.search(t):
                return especialidad
    return ""


# --- Fecha solicitada ---------------------------------------------------------

DIA_SEMANA = r"(lunes|martes|miercoles|jueves|viernes|sabado|domingo)"

FECHA_PATTERNS = [
    r"\b(el|la|para el|para|en el)\s+\d{1,2}\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\b",
    r"\bdia\s+\d{1,2}\b",
    r"\b\d{4}-\d{2}-\d{2}\b",
    r"\b\d{1,2}/\d{1,2}(/\d{2,4})?\b",
    r"\bpasado manana\b",
    r"\bproxima semana\b",
    r"\bproximo mes\b",
    r"\bsemana (que viene|siguiente|entrante)\b",
    r"\bla (proxima|siguiente) semana\b",
    r"\beste\s+(lunes|martes|miercoles|jueves|viernes|sabado|domingo)\b",
    rf"\b{ DIA_SEMANA }\b",
    r"\bmanana\b",
]

FECHA_COMPILED = [re.compile(pat, re.IGNORECASE) for pat in FECHA_PATTERNS]


def extract_fecha_solicitada(text: str) -> str:
    return _extract_fecha_solicitada(_norm(text))


def _extract_fecha_solicitada(t: str) -> str:
    for pat in FECHA_COMPILED:
        m = pat.search(t)
        if m:
            return m.group(0).strip()
    return ""


# --- Preferencia horaria ------------------------------------------------------

HORARIO_PATTERNS = [
    r"\b(por|en|para|durante)\s+(la\s+)?manana\b",
    r"\b(por|en|para|durante)\s+(la\s+)?tarde\b",
    r"\b(por|en|para|durante)\s+(la\s+)?noche\b",
    r"\b(horario|turno|agenda) de la (manana|tarde|noche)\b",
    r"\bprimeras horas del dia\b",
    r"\bprimera hora\b",
    r"\bmediodia\b",
    r"\bmedio dia\b",
    r"\b(a las|alas|a eso de|sobre)\s+\d{1,2}(:\d{2})?\s*(am|pm)?\b",
    r"\b\d{1,2}(:\d{2})?\s*(am|pm)\b",
    r"\ben la manana\b",
    r"\ben la tarde\b",
    r"\bmanana temprano\b",
    r"\bde la (manana|tarde|noche)\b",
    r"\bpor la mananita\b",
]

HORARIO_COMPILED = [re.compile(pat, re.IGNORECASE) for pat in HORARIO_PATTERNS]


def extract_preferencia_horario(text: str) -> str:
    return _extract_preferencia_horario(_norm(text))


def _extract_preferencia_horario(t: str) -> str:
    for pat in HORARIO_COMPILED:
        m = pat.search(t)
        if m:
            return m.group(0).strip()
    return ""


def extract_fields(text: str, fields: list[str] | None = None) -> dict:
    """Extrae los campos estructurados de un mensaje normalizando el texto una sola vez.

    fields: subconjunto de ("accion", "especialidad", "fecha_solicitada",
    "preferencia_horario"). None extrae los 4.
    """
    t = _norm(text)
    result = {}
    if fields is None or "accion" in fields:
        result["accion"] = _extract_accion(t)
    if fields is None or "especialidad" in fields:
        result["especialidad"] = _extract_especialidad(t)
    if fields is None or "fecha_solicitada" in fields:
        result["fecha_solicitada"] = _extract_fecha_solicitada(t)
    if fields is None or "preferencia_horario" in fields:
        result["preferencia_horario"] = _extract_preferencia_horario(t)
    return result
