# ============================================================
# CAMPOS DISPONIBLES PARA EL AGENTE RRHH
# ============================================================

ALLOWED_EMPLOYEE_FIELDS = {
    "nombre",
    "email",
    "cargo",
    "contrato_vigente",
    "region",
    "cedula",
    "genero",
    "folio_trabajador",
    "fecha_ingreso",
    "fecha_renovacion_contrato",
    "fecha_nacimiento",
    "fecha_curso_altura",
    "telefono",
    "direccion",
    "centro_negocios",
    "fecha_termino_contrato",
    "indefinido",
    "plazo_fijo",
}


# ============================================================
# FILTROS DISPONIBLES
# ============================================================

ALLOWED_FILTER_FIELDS = {
    "nombre",
    "email",
    "cargo",
    "contrato_vigente",
    "region",
    "genero",
    "centro_negocios",
    "fecha_ingreso",
    "fecha_nacimiento",
    "indefinido",
    "plazo_fijo",
}


# ============================================================
# ACCIONES DISPONIBLES
# ============================================================

ALLOWED_ACTIONS = {
    "get_employee",
    "search_employees",
    "count_employees",
    "list_employees",
    "general_rrhh_question",
}


# ============================================================
# VALIDAR ANÁLISIS
# ============================================================

def sanitize_rrhh_analysis(
    analysis: dict,
) -> dict:

    if not isinstance(
        analysis,
        dict,
    ):

        analysis = {}

    action = analysis.get(
        "action",
        "general_rrhh_question",
    )

    if action not in ALLOWED_ACTIONS:

        action = "general_rrhh_question"

    employee_name = analysis.get(
        "employee_name"
    )

    if employee_name is not None:

        employee_name = str(
            employee_name
        ).strip()

        if not employee_name:

            employee_name = None

    requested_fields = analysis.get(
        "requested_fields",
        [],
    )

    if not isinstance(
        requested_fields,
        list,
    ):

        requested_fields = []

    requested_fields = [
        field
        for field in requested_fields
        if field in ALLOWED_EMPLOYEE_FIELDS
    ]

    filters = analysis.get(
        "filters",
        {},
    )

    if not isinstance(
        filters,
        dict,
    ):

        filters = {}

    clean_filters = {}

    for key, value in filters.items():

        if key not in ALLOWED_FILTER_FIELDS:

            continue

        if value is None:

            continue

        clean_filters[
            key
        ] = value

    return {
        "action": action,
        "employee_name": employee_name,
        "requested_fields": requested_fields,
        "filters": clean_filters,
        "summary": str(
            analysis.get(
                "summary",
                "",
            )
            or ""
        ).strip(),
    }