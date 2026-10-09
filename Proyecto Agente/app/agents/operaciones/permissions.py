import re
import unicodedata


# ============================================================
# CARGOS AUTORIZADOS
# ============================================================

OPERATIONAL_ROLES = {
    "supervisor",
    "tecnico",
    "ayudante",
}

FIELD_SURVEY_ROLES = {
    "supervisor",
}


# ============================================================
# NORMALIZAR
# ============================================================

def normalize_role(
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

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ============================================================
# CARGO DEL TRABAJADOR
# ============================================================

def get_employee_role(
    employee: dict,
) -> str:

    if not isinstance(
        employee,
        dict,
    ):
        return ""

    return normalize_role(
        employee.get(
            "cargo"
        )
    )


def is_supervisor(
    employee: dict,
) -> bool:

    return "supervisor" in get_employee_role(
        employee
    )


def is_technician(
    employee: dict,
) -> bool:

    role = get_employee_role(
        employee
    )

    return (
        "tecnico" in role
        or "tecnica" in role
    )


def is_helper(
    employee: dict,
) -> bool:

    return "ayudante" in get_employee_role(
        employee
    )


def uses_technician_operations_flow(
    employee: dict,
) -> bool:

    return (
        is_technician(employee)
        or is_helper(employee)
    )


def is_service_type_allowed(
    employee: dict,
    service_type,
) -> bool:

    normalized_type = normalize_role(
        service_type
    )

    if is_supervisor(
        employee
    ):

        return normalized_type == "cotizacion"

    if uses_technician_operations_flow(
        employee
    ):

        return normalized_type != "cotizacion"

    # No cambiamos el comportamiento histórico de otros cargos.
    return True


# ============================================================
# PUEDE USAR OPERACIONES
# ============================================================

def can_use_operations(
    employee: dict,
) -> bool:

    role = get_employee_role(
        employee
    )

    return any(
        allowed_role in role
        for allowed_role in OPERATIONAL_ROLES
    )


# ============================================================
# PUEDE REALIZAR LEVANTAMIENTO TÉCNICO
# ============================================================

def can_perform_field_survey(
    employee: dict,
) -> bool:

    role = get_employee_role(
        employee
    )

    return any(
        allowed_role in role
        for allowed_role in FIELD_SURVEY_ROLES
    )
