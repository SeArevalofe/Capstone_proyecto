import os

from pathlib import Path

from dotenv import load_dotenv


# ============================================================
# RUTAS
# ============================================================

BASE_DIR = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

ENV_PATH = (
    BASE_DIR
    / ".env"
)

MEDIA_DIR = (
    BASE_DIR
    / "storage"
    / "media"
)

MEDIA_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# VARIABLES DE ENTORNO
# ============================================================

load_dotenv(
    ENV_PATH,
    override=True,
)


# ============================================================
# OPENAI
# ============================================================

OPENAI_API_KEY = os.getenv(
    "OPENAI_API_KEY",
    "",
).strip()

OPENAI_MODEL = os.getenv(
    "OPENAI_MODEL",
    "gpt-5.4-mini",
).strip()

OPENAI_TRANSCRIPTION_MODEL = os.getenv(
    "OPENAI_TRANSCRIPTION_MODEL",
    "gpt-4o-mini-transcribe",
).strip()

if not OPENAI_API_KEY:

    raise RuntimeError(
        "No se encontró OPENAI_API_KEY."
    )


# ============================================================
# AIRTABLE - TOKEN
# ============================================================

AIRTABLE_TOKEN = os.getenv(
    "AIRTABLE_TOKEN",
    "",
).strip()

if not AIRTABLE_TOKEN:

    raise RuntimeError(
        "No se encontró AIRTABLE_TOKEN."
    )


# ============================================================
# AIRTABLE - REGISTRO INICIO DE ACTIVIDADES
#
# CONFIGURACIÓN HISTÓRICA.
#
# IMPORTANTE:
# Más abajo existen las constantes utilizadas actualmente
# por activity_repository.py.
#
# No eliminamos este bloque todavía para evitar romper
# funcionalidades existentes.
# ============================================================

AIRTABLE_ACTIVITY_TABLE_ID = (
    "tblmf8w7NywpOTd6N"
)

AIRTABLE_ACTIVITY_FIELD_TOOL_RENTAL = (
    "fldafr8AgygKt75Vx"
)

AIRTABLE_ACTIVITY_FIELD_START_LOCATION = (
    "fldTByiEXJy1z8Itc"
)

AIRTABLE_ACTIVITY_FIELD_END_LOCATION = (
    "fldbnq23hAEpaKLyz"
)

AIRTABLE_ACTIVITY_FIELD_ID_CUADRO = (
    "fldo62Uh9Rt0ESdMa"
)

AIRTABLE_ACTIVITY_FIELD_TECHNICIAN = (
    "fldwWl0d61jJZiBJy"
)

AIRTABLE_ACTIVITY_FIELD_HELPER = (
    "fldB6cVbSPB0IdHfc"
)


# ============================================================
# AIRTABLE - RRHH2
# ============================================================

AIRTABLE_EMPLOYEE_BASE_ID = os.getenv(
    "AIRTABLE_EMPLOYEE_BASE_ID",
    "",
).strip()

AIRTABLE_EMPLOYEE_TABLE_ID = os.getenv(
    "AIRTABLE_EMPLOYEE_TABLE_ID",
    "",
).strip()

AIRTABLE_EMPLOYEE_PHONE_FIELD = os.getenv(
    "AIRTABLE_EMPLOYEE_PHONE_FIELD",
    "Telefono - Trabajador",
).strip()

AIRTABLE_EMPLOYEE_NAME_FIELD = os.getenv(
    "AIRTABLE_EMPLOYEE_NAME_FIELD",
    "Nombre Trabajador",
).strip()

AIRTABLE_EMPLOYEE_POSITION_FIELD = os.getenv(
    "AIRTABLE_EMPLOYEE_POSITION_FIELD",
    "Cargo",
).strip()

if not AIRTABLE_EMPLOYEE_BASE_ID:

    raise RuntimeError(
        "No se encontró AIRTABLE_EMPLOYEE_BASE_ID."
    )

if not AIRTABLE_EMPLOYEE_TABLE_ID:

    raise RuntimeError(
        "No se encontró AIRTABLE_EMPLOYEE_TABLE_ID."
    )


# ============================================================
# AIRTABLE - TABLA DE CARGOS
# ============================================================

AIRTABLE_POSITION_BASE_ID = os.getenv(
    "AIRTABLE_POSITION_BASE_ID",
    AIRTABLE_EMPLOYEE_BASE_ID,
).strip()

AIRTABLE_POSITION_TABLE_ID = os.getenv(
    "AIRTABLE_POSITION_TABLE_ID",
    "",
).strip()

AIRTABLE_POSITION_NAME_FIELD = os.getenv(
    "AIRTABLE_POSITION_NAME_FIELD",
    "Cargo",
).strip()


# ============================================================
# AIRTABLE - SOLICITUDES DE SERVICIO
# ============================================================

AIRTABLE_SERVICE_BASE_ID = os.getenv(
    "AIRTABLE_SERVICE_BASE_ID",
    "",
).strip()

AIRTABLE_SERVICE_REQUEST_TABLE_ID = os.getenv(
    "AIRTABLE_SERVICE_REQUEST_TABLE_ID",
    "",
).strip()


# ------------------------------------------------------------
# DIRECCIÓN DEL SERVICIO
# ------------------------------------------------------------

AIRTABLE_SERVICE_ADDRESS_FIELD = os.getenv(
    "AIRTABLE_SERVICE_ADDRESS_FIELD",
    "Direccion (from Ubicacion de Trabajo - Creacion de Servicio)",
).strip()

AIRTABLE_SERVICE_DESCRIPTION_FIELD = os.getenv(
    "AIRTABLE_SERVICE_DESCRIPTION_FIELD",
    "Descripcion del Servicio",
).strip()


# ------------------------------------------------------------
# ID PRINCIPAL DEL SERVICIO
#
# Ejemplos:
#
# COT37470
# COT37392 - OC
# COT20894 - COTIZACION
# ------------------------------------------------------------

AIRTABLE_SERVICE_QUOTE_FIELD = os.getenv(
    "AIRTABLE_SERVICE_QUOTE_FIELD",
    "ID Solicitud de Servicio",
).strip()


# ------------------------------------------------------------
# OC DEL SERVICIO
# ------------------------------------------------------------

AIRTABLE_SERVICE_OC_FIELD = os.getenv(
    "AIRTABLE_SERVICE_OC_FIELD",
    "OC",
).strip()


# ------------------------------------------------------------
# ESTADO DEL SERVICIO
# ------------------------------------------------------------

AIRTABLE_SERVICE_STATUS_FIELD = os.getenv(
    "AIRTABLE_SERVICE_STATUS_FIELD",
    "Estado del Servicio",
).strip()

# Record vinculado que representa el estado lógico ACTIVO.
AIRTABLE_SERVICE_STATUS_ACTIVE_RECORD_ID = os.getenv(
    "AIRTABLE_SERVICE_STATUS_ACTIVE_RECORD_ID",
    "recNAjJDSZ4xVfxMm",
).strip()

# Record vinculado que representa el estado lógico PAUSADO.
AIRTABLE_SERVICE_STATUS_PAUSED_RECORD_ID = os.getenv(
    "AIRTABLE_SERVICE_STATUS_PAUSED_RECORD_ID",
    "rec7BtzNpCP0JwHWH",
).strip()


# ------------------------------------------------------------
# TIPO DE SERVICIO
# ------------------------------------------------------------

AIRTABLE_SERVICE_TYPE_FIELD = os.getenv(
    "AIRTABLE_SERVICE_TYPE_FIELD",
    "Tipo de Servicio",
).strip()


# ------------------------------------------------------------
# ASIGNACIONES
# ------------------------------------------------------------

AIRTABLE_SERVICE_TECHNICIAN_FIELD = os.getenv(
    "AIRTABLE_SERVICE_TECHNICIAN_FIELD",
    "Tecnico Asignado",
).strip()

AIRTABLE_SERVICE_HELPER_FIELD = os.getenv(
    "AIRTABLE_SERVICE_HELPER_FIELD",
    "Ayudante Asignado",
).strip()

AIRTABLE_SERVICE_SUPERVISOR_FIELD = os.getenv(
    "AIRTABLE_SERVICE_SUPERVISOR_FIELD",
    "Supervisor Asignado",
).strip()


# ------------------------------------------------------------
# IMÁGENES ASOCIADAS A LA SOLICITUD
# ------------------------------------------------------------

AIRTABLE_SERVICE_IMAGES_FIELD = os.getenv(
    "AIRTABLE_SERVICE_IMAGES_FIELD",
    "Fotografías Levantamiento",
).strip()


# ------------------------------------------------------------
# VALIDACIÓN
# ------------------------------------------------------------

if not AIRTABLE_SERVICE_BASE_ID:

    raise RuntimeError(
        "No se encontró AIRTABLE_SERVICE_BASE_ID."
    )

if not AIRTABLE_SERVICE_REQUEST_TABLE_ID:

    raise RuntimeError(
        "No se encontró AIRTABLE_SERVICE_REQUEST_TABLE_ID."
    )


# ============================================================
# AIRTABLE - CIERRE DE SERVICIOS
# ============================================================
#
# FLUJO OPERACIONAL:
#
# Al completar el formulario por WhatsApp:
#
# - COT
# - Técnico
# - Técnico ayudante, si existe
# - Observaciones
#
# se CREA una nueva fila en:
#
# Cierre de Servicios
#
# Las fotografías se agregan después sobre el Record ID
# recién creado.
# ============================================================

AIRTABLE_SERVICE_CLOSURE_TABLE_ID = os.getenv(
    "AIRTABLE_SERVICE_CLOSURE_TABLE_ID",
    "",
).strip()


# ============================================================
# CIERRE - COT
# ============================================================
#
# Este es el campo que relaciona el cierre con la COT.
# ============================================================

AIRTABLE_CLOSURE_SERVICE_LINK_FIELD = (
    "fldzA9Zub8a9ihoZe"
)


# ============================================================
# CIERRE - TÉCNICO
# ============================================================
#
# Field ID:
# fldQG6cMIncxuXrJD
# ============================================================

AIRTABLE_CLOSURE_TECHNICIAN_FIELD = (
    "fldQG6cMIncxuXrJD"
)

# ============================================================
# CIERRE - TABLA TÉCNICOS / SUPERVISORES
#
# El campo "Tecnico que Cierra Servicio" de Cierre de Servicios
# vincula contra esta tabla.
#
# Tanto técnicos como supervisores pueden ser utilizados
# como persona que realiza el cierre.
# ============================================================

AIRTABLE_CLOSURE_WORKER_TABLE_ID = (
    "tblVWWEWk657HJPWv"
)

AIRTABLE_CLOSURE_WORKER_RRHH_FIELD = (
    "RRHH"
)

AIRTABLE_CLOSURE_WORKER_NAME_FIELD = (
    "Nombre del Tecnico"
)

# ============================================================
# CIERRE - TÉCNICO AYUDANTE
# ============================================================
#
# Field ID:
# fldSBDxIiD8RrOjyq
#
# Si el servicio NO tiene ayudante,
# este campo simplemente NO se envía.
# ============================================================

AIRTABLE_CLOSURE_HELPER_FIELD = (
    "fldSBDxIiD8RrOjyq"
)


# ============================================================
# CIERRE - OBSERVACIONES
# ============================================================
#
# Field ID:
# fldcMshJnHoaiscmz
# ============================================================

AIRTABLE_CLOSURE_OBSERVATIONS_FIELD = (
    "fldcMshJnHoaiscmz"
)

# Selección única usada por cierres técnicos no satisfactorios.
AIRTABLE_CLOSURE_MITIGATION_CAUSE_FIELD = (
    "Causas de mitigacion"
)


# ============================================================
# CIERRE - FOTO HOJA DE SERVICIO
# ============================================================
#
# Field ID:
# fldmtrWvo7TFHVtmP
# ============================================================

AIRTABLE_CLOSURE_SERVICE_SHEET_FIELD = (
    "fldmtrWvo7TFHVtmP"
)


# ============================================================
# CIERRE - FOTOS DEL SERVICIO
# ============================================================
#
# Field ID:
# fldRsiW6sUyYUaAsz
# ============================================================

AIRTABLE_CLOSURE_SERVICE_PHOTOS_FIELD = (
    "fldRsiW6sUyYUaAsz"
)


# ============================================================
# CIERRE - CAMPO HISTÓRICO
#
# Se conserva para compatibilidad con otros flujos,
# principalmente Agente Maestro.
# ============================================================

AIRTABLE_CLOSURE_OC_FIELD = os.getenv(
    "AIRTABLE_CLOSURE_OC_FIELD",
    "Servicio que Cierra",
).strip()


# ============================================================
# CIERRE - LEVANTAMIENTO WHATSAPP (LOOKUP)
#
# Airtable refleja aquí el valor original de Inicio Actividades.
# Python no escribe el informe directamente en este campo.
# ============================================================

AIRTABLE_CLOSURE_REPORT_FIELD = os.getenv(
    "AIRTABLE_CLOSURE_REPORT_FIELD",
    "Levantamientos WSP",
).strip()

# Copia interna editable del informe. Es distinta del Lookup histórico.
AIRTABLE_CLOSURE_INTERNAL_REPORT_FIELD = os.getenv(
    "AIRTABLE_CLOSURE_INTERNAL_REPORT_FIELD",
    "Informe Levantamientos WSP",
).strip()


# ============================================================
# CIERRE - FOTOGRAFÍAS DE LEVANTAMIENTO
#
# Utilizado por Agente Maestro.
# ============================================================

AIRTABLE_CLOSURE_IMAGES_FIELD = os.getenv(
    "AIRTABLE_CLOSURE_IMAGES_FIELD",
    "Fotografías Levantamiento",
).strip()


# ============================================================
# VALIDACIÓN
# ============================================================

if not AIRTABLE_SERVICE_CLOSURE_TABLE_ID:

    raise RuntimeError(
        "No se encontró AIRTABLE_SERVICE_CLOSURE_TABLE_ID."
    )

# ============================================================
# WHATSAPP
# ============================================================

WHATSAPP_ACCESS_TOKEN = os.getenv(
    "WHATSAPP_ACCESS_TOKEN",
    "",
).strip()

WHATSAPP_PHONE_NUMBER_ID = os.getenv(
    "WHATSAPP_PHONE_NUMBER_ID",
    "",
).strip()

WHATSAPP_VERIFY_TOKEN = os.getenv(
    "WHATSAPP_VERIFY_TOKEN",
    "",
).strip()

WHATSAPP_API_VERSION = os.getenv(
    "WHATSAPP_API_VERSION",
    "v25.0",
).strip()

if not WHATSAPP_ACCESS_TOKEN:

    raise RuntimeError(
        "No se encontró WHATSAPP_ACCESS_TOKEN."
    )

if not WHATSAPP_PHONE_NUMBER_ID:

    raise RuntimeError(
        "No se encontró WHATSAPP_PHONE_NUMBER_ID."
    )

if not WHATSAPP_VERIFY_TOKEN:

    raise RuntimeError(
        "No se encontró WHATSAPP_VERIFY_TOKEN."
    )


# ============================================================
# DESARROLLO
# ============================================================

DEVELOPMENT_MODE = (
    os.getenv(
        "DEVELOPMENT_MODE",
        "false",
    )
    .strip()
    .lower()
    == "true"
)


# ============================================================
# TELÉFONO GENERAL DE PRUEBA
# ============================================================

TEST_PHONE = os.getenv(
    "TEST_PHONE",
    "",
).strip()


# ============================================================
# USUARIO DE PRUEBA
# ============================================================

TEST_EMPLOYEE_NAME = os.getenv(
    "TEST_EMPLOYEE_NAME",
    "Usuario de Pruebas",
).strip()

TEST_EMPLOYEE_EMAIL = os.getenv(
    "TEST_EMPLOYEE_EMAIL",
    "",
).strip()

TEST_EMPLOYEE_POSITION = os.getenv(
    "TEST_EMPLOYEE_POSITION",
    "Supervisor",
).strip()


# ============================================================
# IMPERSONACIÓN
# ============================================================

TEST_IMPERSONATE_PHONE = os.getenv(
    "TEST_IMPERSONATE_PHONE",
    "",
).strip()


# ============================================================
# REGISTROS - INICIO ACTIVIDADES
#
# IMPORTANTE:
#
# Estas constantes son las que actualmente utiliza
# activity_repository.py.
#
# Se conservan exactamente para NO romper el inicio
# de servicios que ya está funcionando.
# ============================================================

AIRTABLE_ACTIVITY_TABLE_ID = (
    "tblmf8w7NywpOTd6N"
)

AIRTABLE_ACTIVITY_FIELD_ID_CUADRO = (
    "ID Cuadro"
)

AIRTABLE_ACTIVITY_FIELD_TOOL_RENTAL = (
    "Arriendo Herramientas"
)

AIRTABLE_ACTIVITY_FIELD_START_LOCATION = (
    "Inicio - Geolocalizacion Whatsapp"
)

AIRTABLE_ACTIVITY_FIELD_TECHNICIAN = (
    "Tecnico"
)

AIRTABLE_ACTIVITY_FIELD_HELPER = (
    "Tecnico - Ayudante"
)

AIRTABLE_ACTIVITY_FIELD_START_DISTANCE = (
    "fldnLc685RkqhaBuW"
)

AIRTABLE_ACTIVITY_FIELD_RECORD_IDENTIFIER = os.getenv(
    "AIRTABLE_ACTIVITY_FIELD_RECORD_IDENTIFIER",
    "ID Registro",
).strip()

AIRTABLE_ACTIVITY_REPORT_FIELD = os.getenv(
    "AIRTABLE_ACTIVITY_REPORT_FIELD",
    "Levantamientos WSP",
).strip()


# ============================================================
# GOOGLE MAPS API GEOCODING
# ============================================================

GOOGLE_MAPS_API_KEY = os.getenv(
    "GOOGLE_MAPS_API_KEY",
    "",
).strip()
