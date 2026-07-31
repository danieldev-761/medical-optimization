"""Genera datos de ejemplo .xlsx para validación end-to-end de la pipeline."""

import argparse
import random
import shutil
from pathlib import Path

import pandas as pd

TEMPLATES = [
    ("Quiero confirmar mi cita de cardiologia para el lunes.", "confirmar", "cardiologia", "lunes", ""),
    ("Buenos días, necesito cancelar la cita de dermatologia por favor.", "cancelar", "dermatologia", "", ""),
    ("Hola, quiero reprogramar mi cita, preferiblemente por la tarde.", "reprogramar", "", "", "por la tarde"),
    ("Confirmo mi cita con el oftalmologo el 15 de mayo a las 9 am.", "confirmar", "oftalmologia", "15 de mayo", "a las 9 am"),
    ("No voy a poder asistir, por favor anule mi cita de neurologia.", "cancelar", "neurologia", "", ""),
    ("Necesito cambiar la fecha de mi cita de odontologia para la proxima semana.", "reprogramar", "odontologia", "proxima semana", ""),
    ("Gracias, confirmo asistencia a pediatria el martes en la manana.", "confirmar", "pediatria", "martes", "en la manana"),
    ("Quiero agendar de nuevo mi cita de fisioterapia para el viernes a las 3 pm.", "reprogramar", "fisioterapia", "viernes", "a las 3 pm"),
    ("Por favor cancelar mi cita de ginecologia, no podre asistir.", "cancelar", "ginecologia", "", ""),
    ("Confirmo la cita de psicologia para manana por la manana.", "confirmar", "psicologia", "manana", "por la manana"),
]

SIN_ACCION = [
    ("", "", "", ""),
    ("hola", "", "", ""),
    ("gracias", "", "", ""),
]

ACCION_VARIANTES = {
    "confirmar": ["confirmar", "confirmo", "reafirmar", "confirmacion", "confirmada"],
    "cancelar": ["cancelar", "cancelacion", "anular", "anulacion", "no asistire"],
    "reprogramar": ["reprogramar", "reagendar", "cambiar la fecha", "mover la cita", "posponer"],
}

ESPECIALIDADES = {
    "cardiologia": ["cardiologia", "con el cardiologo"],
    "dermatologia": ["dermatologia", "con el dermatologo"],
    "ginecologia": ["ginecologia", "con la ginecologa"],
    "pediatria": ["pediatria", "con el pediatra"],
    "oftalmologia": ["oftalmologia", "con el oftalmologo"],
    "neurologia": ["neurologia", "con el neurologo"],
    "psicologia": ["psicologia", "con la psicologa"],
    "fisioterapia": ["fisioterapia", "con el fisioterapeuta"],
    "odontologia": ["odontologia", "con el odontologo"],
    "medicina general": ["medicina general", "con el medico general"],
}

FECHAS = ["el lunes", "el martes", "el viernes", "la proxima semana", "para manana", "el 15 de mayo", "el 3 de julio", "la semana que viene"]
HORARIOS = ["por la manana", "en la tarde", "a las 9 am", "a las 3 pm", "al mediodia", "por la noche", ""]


def generate(n: int, seed: int = 42) -> pd.DataFrame:
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        accion, verbos = rng.choice(list(ACCION_VARIANTES.items()))
        esp_name, esp_form = rng.choice(list(ESPECIALIDADES.items()))
        esp = rng.choice(esp_form)
        fecha = rng.choice(FECHAS)
        horario = rng.choice(HORARIOS)
        partes = [f"{verbo} mi cita de {esp}", fecha]
        if horario:
            partes.append(horario)
        msg = ", ".join(partes) + "."
        msg = msg.replace(" mi cita de ", " de ") if verbo == "no asistire" else msg
        rows.append(
            {
                "paciente_id": f"P-{1000 + i}",
                "mensaje_texto": msg,
            }
        )
    return pd.DataFrame(rows)


def generate(n: int, seed: int = 42) -> pd.DataFrame:
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        accion, verbos = rng.choice(list(ACCION_VARIANTES.items()))
        verbo = rng.choice(verbos)
        esp_name, esp_form = rng.choice(list(ESPECIALIDADES.items()))
        esp = rng.choice(esp_form)
        fecha = rng.choice(FECHAS)
        horario = rng.choice(HORARIOS)
        partes = [f"{verbo} mi cita de {esp}", fecha]
        if horario:
            partes.append(horario)
        msg = ", ".join(partes) + "."
        msg = msg.replace(" mi cita de ", " de ") if verbo == "no asistire" else msg
        rows.append(
            {
                "paciente_id": f"P-{1000 + i}",
                "mensaje_texto": msg,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera datos .xlsx de ejemplo")
    parser.add_argument("--n", type=int, default=200, help="filas por archivo")
    parser.add_argument("--files", type=int, default=2, help="cantidad de archivos")
    parser.add_argument("--out", type=str, default="sample")
    args = parser.parse_args()

    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    for f in range(args.files):
        df = generate(args.n, seed=42 + f)
        extra = [{"mensaje_texto": t[0]} for t in TEMPLATES]
        extra += [{"mensaje_texto": m} for m in ("", "hola", "gracias", "   ")]
        base = pd.DataFrame(extra, columns=["mensaje_texto"])
        base.insert(0, "paciente_id", [f"X-{f}-{i}" for i in range(len(base))])
        df = pd.concat([df, base], ignore_index=True)
        df = df.drop_duplicates(subset="mensaje_texto", keep="first")
        df.to_excel(out / f"citas_{f + 1}.xlsx", index=False)
        print(f"Generado: {out / f'citas_{f + 1}.xlsx'} ({len(df)} filas)")


if __name__ == "__main__":
    main()
