import re
import unicodedata


# ============================================================
# INTENCIONES
# ============================================================

START_SERVICE = "START_SERVICE"
CLOSE_SERVICE = "CLOSE_SERVICE"


# ============================================================
# NORMALIZACIÓN
# ============================================================

def normalize_text(
    value,
) -> str:

    if value is None:
        return ""

    text = str(
        value
    ).strip().lower()

    text = "".join(
        character
        for character in unicodedata.normalize(
            "NFD",
            text,
        )
        if unicodedata.category(
            character
        ) != "Mn"
    )

    # Convertir signos comunes en espacios.
    # Esto permite entender:
    #
    # cot-37470
    # cot:37470
    # cot / 37470
    #
    text = re.sub(
        r"[_:/\-]+",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ============================================================
# EXTRAER COT
#
# Debe reconocer, entre otros:
#
# COT37470
# cot37470
# COT 37470
# cot 37470
# Cot-37470
# cot:37470
# la cot 37470
# iniciar cot 37470
#
# Siempre devuelve:
#
# COT37470
# ============================================================

def extract_cot(
    text: str,
):

    value = str(
        text
        or ""
    ).strip()

    if not value:
        return None

    match = re.search(
        r"\bcot[\s\-_:/.]*([0-9]{3,})\b",
        value,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    number = match.group(
        1
    )

    return f"COT{number}"


# ============================================================
# DETECTAR INICIO
# ============================================================

def is_start_service_request(
    text: str,
) -> bool:

    value = normalize_text(
        text
    )

    if not value:
        return False

    # ========================================================
    # LEVANTAMIENTO TÉCNICO
    #
    # Estas expresiones pertenecen al Agente Maestro.
    # ========================================================

    maestro_phrases = (
        "levantar servicio",
        "levantar un servicio",
        "quiero levantar servicio",
        "quiero levantar un servicio",
        "quisiera levantar servicio",
        "quisiera levantar un servicio",
        "realizar levantamiento",
        "realizar un levantamiento",
        "hacer levantamiento",
        "hacer un levantamiento",
        "levantamiento tecnico",
        "hacer levantamiento tecnico",
        "realizar levantamiento tecnico",
    )

    if any(
        phrase in value
        for phrase in maestro_phrases
    ):

        return False

    # ========================================================
    # INICIO REAL DE SERVICIO
    #
    # Incluimos expresiones naturales que puede utilizar
    # un técnico en terreno.
    # ========================================================

    start_phrases = (
        "iniciar servicio",
        "iniciar un servicio",
        "iniciar el servicio",

        "quiero iniciar servicio",
        "quiero iniciar un servicio",
        "quiero iniciar el servicio",

        "quisiera iniciar servicio",
        "quisiera iniciar un servicio",

        "necesito iniciar servicio",
        "necesito iniciar un servicio",

        "comenzar servicio",
        "comenzar un servicio",
        "comenzar el servicio",

        "quiero comenzar servicio",
        "quiero comenzar un servicio",

        "dar inicio al servicio",
        "dar inicio a un servicio",

        "inicio de servicio",
        "inicio del servicio",

        "registrar inicio de servicio",
        "registrar el inicio del servicio",

        # Expresiones naturales de terreno
        "partir servicio",
        "partir el servicio",
        "partir un servicio",

        "quiero partir servicio",
        "quiero partir el servicio",
        "quiero partir un servicio",

        "empezar servicio",
        "empezar el servicio",
        "empezar un servicio",

        "quiero empezar servicio",
        "quiero empezar el servicio",
        "quiero empezar un servicio",

        "iniciar pega",
        "comenzar pega",
        "empezar pega",
        "partir pega",
    )

    return any(
        phrase in value
        for phrase in start_phrases
    )


# ============================================================
# DETECTAR CIERRE
# ============================================================

def is_close_service_request(
    text: str,
) -> bool:

    value = normalize_text(
        text
    )

    if not value:
        return False

    phrases = (
        "cerrar servicio",
        "cerrar un servicio",
        "cerrar el servicio",

        "cierre de servicio",
        "cierre del servicio",

        "finalizar servicio",
        "finalizar un servicio",
        "finalizar el servicio",

        "terminar servicio",
        "terminar un servicio",
        "terminar el servicio",

        # Lenguaje más natural
        "terminamos servicio",
        "terminamos el servicio",

        "termine servicio",
        "termine el servicio",

        "servicio terminado",
        "servicio finalizado",

        "cerrar pega",
        "terminar pega",
        "finalizar pega",
    )

    return any(
        phrase in value
        for phrase in phrases
    )


# ============================================================
# RESPUESTA SÍ / NO
# ============================================================

def parse_yes_no(
    text: str,
):

    value = normalize_text(
        text
    )

    if value in (
        "1",
        "si",
        "s",
        "yes",
        "correcto",
        "correcta",
        "confirmo",
        "confirmar",
        "dale",
        "ok",
        "okay",
        "ya",
    ):
        return True

    if value in (
        "2",
        "no",
        "n",
        "incorrecto",
        "incorrecta",
        "cancelar",
    ):
        return False

    return None


# ============================================================
# SELECCIÓN NUMÉRICA
# ============================================================

def parse_selection(
    text: str,
    options: list,
):

    value = str(
        text
        or ""
    ).strip()

    if not re.fullmatch(
        r"\d+",
        value,
    ):
        return None

    try:

        index = int(
            value
        ) - 1

    except Exception:

        return None

    if (
        index < 0
        or index >= len(
            options
        )
    ):

        return None

    return options[
        index
    ]