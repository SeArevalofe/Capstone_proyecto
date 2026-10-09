import re
import unicodedata


# ============================================================
# CAMPOS QUE UN TRABAJADOR PUEDE CONSULTAR SOBRE SÍ MISMO
# ============================================================

SELF_FIELDS = {
    "nombre",
    "email",
    "cargo",
    "telefono",
    "region",
    "centro_negocios",
    "fecha_ingreso",
    "contrato_vigente",
    "fecha_nacimiento",
    "direccion",
    "cedula",
    "genero",
    "fecha_renovacion_contrato",
    "fecha_termino_contrato",
    "indefinido",
    "plazo_fijo",
    "fecha_curso_altura",

    # Preparado para cuando agreguemos estos datos.
    "sueldo",
    "vacaciones",
    "dias_vacaciones",
}


# ============================================================
# CARGOS AUTORIZADOS PARA CONSULTAR TERCEROS
# ============================================================
#
# IMPORTANTE:
# Supervisor NO obtiene acceso RRHH automáticamente.
#
# El permiso de hacer levantamientos es independiente
# del permiso de consultar información personal.
# ============================================================

HR_PRIVILEGED_POSITIONS = {
    "rrhh",
    "recursos humanos",
    "jefe rrhh",
    "jefa rrhh",
    "jefe de rrhh",
    "jefa de rrhh",
    "encargado rrhh",
    "encargada rrhh",
    "encargado de rrhh",
    "encargada de rrhh",
    "gerente rrhh",
    "gerenta rrhh",
    "gerente de rrhh",
    "gerenta de rrhh",
}


# ============================================================
# NORMALIZAR
# ============================================================

def normalize_text(
    value,
) -> str:

    if value is None:
        return ""

    if isinstance(
        value,
        list,
    ):

        value = " ".join(
            str(item)
            for item in value
        )

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

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ============================================================
# NORMALIZAR CARGO
# ============================================================

def normalize_position(
    value,
) -> str:

    return normalize_text(
        value
    )


# ============================================================
# ES USUARIO RRHH PRIVILEGIADO
# ============================================================

def is_hr_user(
    employee: dict,
) -> bool:

    if not isinstance(
        employee,
        dict,
    ):
        return False

    position = normalize_position(
        employee.get(
            "cargo"
        )
    )

    if not position:
        return False

    for allowed in HR_PRIVILEGED_POSITIONS:

        allowed_normalized = normalize_text(
            allowed
        )

        if (
            position == allowed_normalized
            or allowed_normalized in position
        ):

            return True

    return False


# ============================================================
# COMPARAR IDENTIDAD
# ============================================================

def is_same_employee(
    requester: dict,
    target: dict,
) -> bool:

    if not isinstance(
        requester,
        dict,
    ):

        return False

    if not isinstance(
        target,
        dict,
    ):

        return False

    requester_record_id = str(
        requester.get(
            "record_id"
        )
        or ""
    ).strip()

    target_record_id = str(
        target.get(
            "record_id"
        )
        or ""
    ).strip()

    # ========================================================
    # PRIMERA OPCIÓN: RECORD ID AIRTABLE
    # ========================================================

    if (
        requester_record_id
        and target_record_id
    ):

        return (
            requester_record_id
            == target_record_id
        )

    # ========================================================
    # FALLBACK: NOMBRE
    # ========================================================

    requester_name = normalize_text(
        requester.get(
            "nombre"
        )
    )

    target_name = normalize_text(
        target.get(
            "nombre"
        )
    )

    return bool(
        requester_name
        and target_name
        and requester_name == target_name
    )


# ============================================================
# PUEDE CONSULTAR OTRO TRABAJADOR
# ============================================================

def can_read_other_employee(
    requester: dict,
) -> bool:

    return is_hr_user(
        requester
    )


# ============================================================
# PUEDE LISTAR TRABAJADORES
# ============================================================

def can_list_employees(
    requester: dict,
) -> bool:

    return is_hr_user(
        requester
    )


# ============================================================
# PUEDE BUSCAR GRUPOS DE TRABAJADORES
# ============================================================

def can_search_employees(
    requester: dict,
) -> bool:

    return is_hr_user(
        requester
    )


# ============================================================
# CONTEOS AGREGADOS
# ============================================================
#
# "¿Cuántos trabajadores somos?"
# "¿Cuántos técnicos hay?"
#
# No revela información personal individual.
# ============================================================

def can_count_employees(
    requester: dict,
) -> bool:

    return bool(
        requester
        and requester.get(
            "found",
            True,
        )
    )


# ============================================================
# PUEDE LEER CAMPO
# ============================================================

def can_read_field(
    requester: dict,
    target: dict,
    field: str,
) -> bool:

    field = str(
        field
        or ""
    ).strip()

    if not field:

        return False

    # ========================================================
    # MIS PROPIOS DATOS
    # ========================================================

    if is_same_employee(
        requester=requester,
        target=target,
    ):

        return (
            field in SELF_FIELDS
        )

    # ========================================================
    # TERCEROS
    # ========================================================

    if can_read_other_employee(
        requester
    ):

        return True

    return False


# ============================================================
# FILTRAR CAMPOS SOLICITADOS
# ============================================================

def filter_allowed_fields(
    requester: dict,
    target: dict,
    requested_fields: list,
) -> list:

    if not isinstance(
        requested_fields,
        list,
    ):

        return []

    return [
        field
        for field in requested_fields
        if can_read_field(
            requester=requester,
            target=target,
            field=field,
        )
    ]