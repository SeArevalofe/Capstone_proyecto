import re
import unicodedata


# ============================================================
# NORMALIZAR TEXTO
# ============================================================

def normalize_text(value) -> str:

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
# CARGO
# ============================================================

def get_employee_position(
    employee: dict,
) -> str:

    if not isinstance(
        employee,
        dict,
    ):
        return ""

    cargo = employee.get(
        "cargo"
    )

    if isinstance(
        cargo,
        list,
    ):

        if not cargo:
            return ""

        cargo = cargo[0]

    return normalize_text(
        cargo
    )


# ============================================================
# TIPOS DE CARGO
# ============================================================

def is_supervisor(
    employee: dict,
) -> bool:

    cargo = get_employee_position(
        employee
    )

    return (
        "supervisor" in cargo
    )


def is_technician(
    employee: dict,
) -> bool:

    cargo = get_employee_position(
        employee
    )

    return (
        "tecnico" in cargo
        or "tecnica" in cargo
    )


def is_helper(
    employee: dict,
) -> bool:

    cargo = get_employee_position(
        employee
    )

    return (
        "ayudante" in cargo
    )


# ============================================================
# CAMPO DE ASIGNACIÓN
# ============================================================

def get_assignment_field_for_employee(
    employee: dict,
):

    if is_supervisor(
        employee
    ):
        return "Supervisor Asignado"

    if is_technician(
        employee
    ):
        return "Tecnico Asignado"

    if is_helper(
        employee
    ):
        return "Ayudante Asignado"

    return None


# ============================================================
# PERMISOS
# ============================================================

def get_maestro_permissions(
    employee: dict,
) -> dict:

    assignment_field = (
        get_assignment_field_for_employee(
            employee
        )
    )

    supervisor = is_supervisor(
        employee
    )

    return {
        "can_access_maestro": (
            assignment_field is not None
        ),

        "can_view_services": (
            assignment_field is not None
        ),

        "can_create_report": supervisor,

        "can_edit_report": supervisor,

        "can_save_report": supervisor,

        "assignment_field": assignment_field,

        "position": get_employee_position(
            employee
        ),
    }


def can_access_maestro(
    employee: dict,
) -> bool:

    return bool(
        get_maestro_permissions(
            employee
        ).get(
            "can_access_maestro"
        )
    )


def can_view_services(
    employee: dict,
) -> bool:

    return bool(
        get_maestro_permissions(
            employee
        ).get(
            "can_view_services"
        )
    )


def can_create_field_report(
    employee: dict,
) -> bool:

    return bool(
        get_maestro_permissions(
            employee
        ).get(
            "can_create_report"
        )
    )


def can_edit_field_report(
    employee: dict,
) -> bool:

    return bool(
        get_maestro_permissions(
            employee
        ).get(
            "can_edit_report"
        )
    )


def can_save_field_report(
    employee: dict,
) -> bool:

    return bool(
        get_maestro_permissions(
            employee
        ).get(
            "can_save_report"
        )
    )