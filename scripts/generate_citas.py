import random
import pandas as pd
from datetime import datetime, timedelta
from faker import Faker


def generar_citas_excel(
    nombre_archivo="citas_medicas_solicitudes.xlsx", num_filas=10000
):
    print(f"Generando {num_filas} solicitudes de citas médicas en español...")

    # Inicializar Faker en español
    fake = Faker("es_ES")

    # Especialidades médicas habituales en el centro de salud
    especialidades = [
        "Cardiología",
        "Dermatología",
        "Ginecología y Obstetricia",
        "Neurología",
        "Oftalmología",
        "Ortopedia y Traumatología",
        "Pediatría",
        "Otorrinolaringología",
        "Gastroenterología",
        "Urología",
        "Medicina General",
        "Endocrinología",
    ]

    # Plantillas con vocabulario formal/médico propio del caso de uso
    plantillas_mensajes = [
        "Deseo solicitar la reprogramación de mi cita médica con el cardiólogo para la próxima semana en el horario de la mañana.",
        "Solicito modificar la fecha de mi consulta médica asignada debido a inconvenientes laborales imprevistos.",
        "Requiero cancelar la cita programada e identificar la disponibilidad de agenda para el turno de la tarde.",
        "Agradezco de antemano la gestión para reagendar mi control periódico para el próximo mes.",
        "Necesito cambiar el horario de mi turno médico, de preferencia en las primeras horas del día.",
        "Favor confirmar si es posible postergar mi atención especializada para el día viernes por la mañana.",
        "Por motivos personales me resulta imposible asistir a la cita asignada. Deseo postergarla para la siguiente semana.",
        "Quisiera saber si hay posibilidad de adelantar mi turno médico por motivos de urgencia no vital.",
    ]

    data = []

    # Generación eficiente de datos
    for _ in range(num_filas):
        id_paciente = fake.uuid4()[:8].upper()
        paciente = fake.name()
        ciudad = fake.city()
        especialidad = random.choice(especialidades)

        # Fecha futura deseada para la reasignación
        fecha_deseada = (datetime.now() + timedelta(days=random.randint(2, 30))).strftime("%Y-%m-%d")

        # Probabilidad del 10% de que el mensaje venga vacío o con datos incompletos
        if random.random() < 0.10:
            mensaje_texto = ""
        else:
            # Combina una plantilla formal con contexto adicional dinámico
            mensaje_texto = (
                f"{random.choice(plantillas_mensajes)} {fake.sentence(nb_words=8)}"
            )

        data.append(
            {
                "id_paciente": id_paciente,
                "paciente": paciente,
                "ciudad": ciudad,
                "especialidad_medica": especialidad,
                "fecha_solicitada": fecha_deseada,
                "mensaje_texto": mensaje_texto,
            }
        )

    print("Creando DataFrame de Pandas...")
    df = pd.DataFrame(data)

    print(f"Guardando archivo Excel: {nombre_archivo}...")
    # Exportar a Excel (requiere openpyxl)
    df.to_excel(nombre_archivo, index=False, engine="openpyxl")

    print(f"¡Proceso completado con éxito! Archivo creado: {nombre_archivo}")


if __name__ == "__main__":
    # Permite ejecutarlo directo o importar la función
    generar_citas_excel()
