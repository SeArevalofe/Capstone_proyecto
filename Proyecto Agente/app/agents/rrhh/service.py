import re
import unicodedata

from app.agents.rrhh.conversation_engine import (
    analyze_rrhh_message,
)

from app.agents.rrhh.permissions import (
    is_same_employee,
    can_read_other_employee,
    can_search_employees,
    can_list_employees,
    can_count_employees,
    filter_allowed_fields,
)

from app.airtable.employee_repository import (
    find_employee_by_name,
    count_employees,
    search_employees,
    get_employees,
)


# ============================================================
# NORMALIZAR
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

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ============================================================
# ES CONSULTA SOBRE EL USUARIO ACTUAL
# ============================================================

def requested_employee_is_self(
    employee_name,
    employee: dict,
) -> bool:

    authenticated_name = normalize_text(
        employee.get(
            "nombre"
        )
    )

    requested_name = normalize_text(
        employee_name
    )

    if not authenticated_name:
        return False

    # La IA podría no devolver nombre en alguna ocasión.
    if not requested_name:
        return True

    if requested_name == authenticated_name:
        return True

    # Comparación por palabras.
    authenticated_words = set(
        authenticated_name.split()
    )

    requested_words = set(
        requested_name.split()
    )

    if (
        requested_words
        and requested_words.issubset(
            authenticated_words
        )
    ):
        return True

    return False


# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================

def process_rrhh_message(
    phone: str,
    text: str,
    employee: dict,
) -> str:

    text_clean = str(
        text
        or ""
    ).strip()

    print()
    print("=" * 70)
    print("👥 AGENTE RRHH JCF")
    print("=" * 70)

    print(
        "Teléfono:",
        phone
    )

    print(
        "Usuario autenticado:",
        employee.get(
            "nombre"
        )
        or "No identificado"
    )

    print(
        "Cargo:",
        employee.get(
            "cargo"
        )
        or "No informado"
    )

    print(
        "Consulta:",
        text_clean
    )

    print("=" * 70)

    if not text_clean:

        return (
            "👥 *Agente RRHH JCF*\n\n"
            "No recibí una consulta para procesar."
        )

    # ========================================================
    # 1. IA INTERPRETA LA PREGUNTA
    # ========================================================

    analysis = analyze_rrhh_message(
        message=text_clean,
        employee=employee,
    )

    action = analysis.get(
        "action"
    )

    employee_name = analysis.get(
        "employee_name"
    )

    requested_fields = analysis.get(
        "requested_fields",
        [],
    )

    filters = analysis.get(
        "filters",
        {},
    )

    print()
    print("=" * 70)
    print("📋 PLAN RRHH")
    print("=" * 70)

    print(
        "Acción:",
        action
    )

    print(
        "Persona:",
        employee_name
    )

    print(
        "Campos:",
        requested_fields
    )

    print(
        "Filtros:",
        filters
    )

    print("=" * 70)

    # ========================================================
    # 2. CONSULTAR PERSONA
    # ========================================================

    if action == "get_employee":

        # ====================================================
        # CONSULTA SOBRE MÍ MISMO
        #
        # IMPORTANTE:
        # NO CONSULTAMOS AIRTABLE NUEVAMENTE.
        #
        # El webhook ya identificó al empleado.
        # ====================================================

        if requested_employee_is_self(
            employee_name=employee_name,
            employee=employee,
        ):

            print()
            print("=" * 70)
            print("⚡ RRHH FAST PATH")
            print("=" * 70)
            print(
                "Usando trabajador autenticado."
            )
            print(
                "No se realizará búsqueda adicional "
                "de trabajadores."
            )
            print("=" * 70)

            allowed_fields = filter_allowed_fields(
                requester=employee,
                target=employee,
                requested_fields=requested_fields,
            )

            if (
                requested_fields
                and not allowed_fields
            ):

                return (
                    "👥 *Agente RRHH JCF*\n\n"
                    "No tengo autorización para mostrar "
                    "ese tipo de información."
                )

            return format_employee_response(
                employee_data=employee,
                requested_fields=allowed_fields,
            )

        # ====================================================
        # CONSULTA SOBRE OTRA PERSONA
        #
        # VERIFICAMOS PERMISO ANTES DE BUSCAR EN AIRTABLE.
        #
        # Esto es importante tanto por privacidad
        # como por rendimiento.
        # ====================================================

        if not can_read_other_employee(
            employee
        ):

            print()
            print("=" * 70)
            print("🔒 CONSULTA DE TERCERO BLOQUEADA")
            print("=" * 70)

            print(
                "Solicitante:",
                employee.get(
                    "nombre"
                )
            )

            print(
                "Persona solicitada:",
                employee_name
            )

            print("=" * 70)

            return (
                "👥 *Agente RRHH JCF*\n\n"
                "Por privacidad, solo puedo mostrarte "
                "tus propios datos personales.\n\n"
                "Puedes preguntarme, por ejemplo:\n"
                "• cuál es mi correo\n"
                "• cuál es mi dirección\n"
                "• cuándo ingresé\n"
                "• cuál es mi fecha de nacimiento"
            )

        # ====================================================
        # USUARIO RRHH AUTORIZADO:
        # AHORA SÍ BUSCAMOS AL TERCERO
        # ====================================================

        if not employee_name:

            return (
                "👥 *Agente RRHH JCF*\n\n"
                "Necesito saber de qué trabajador "
                "quieres consultar información."
            )

        result = find_employee_by_name(
            employee_name
        )

        if result.get(
            "multiple"
        ):

            records = result.get(
                "records",
                [],
            )

            names = []

            for record in records:

                name = record.get(
                    "nombre"
                )

                if name:

                    names.append(
                        f"• {name}"
                    )

            return (
                "👥 *Agente RRHH JCF*\n\n"
                "Encontré más de un trabajador "
                "que coincide con ese nombre.\n\n"
                + "\n".join(
                    names
                )
                + "\n\nIndícame cuál necesitas."
            )

        if not result.get(
            "found"
        ):

            return (
                "👥 *Agente RRHH JCF*\n\n"
                f"No encontré un trabajador "
                f"asociado a *{employee_name}*."
            )

        allowed_fields = filter_allowed_fields(
            requester=employee,
            target=result,
            requested_fields=requested_fields,
        )

        return format_employee_response(
            employee_data=result,
            requested_fields=allowed_fields,
        )

    # ========================================================
    # 3. CONTAR
    # ========================================================
    #
    # Los conteos no revelan datos personales individuales.
    # ========================================================

    if action == "count_employees":

        if not can_count_employees(
            employee
        ):

            return (
                "👥 *Agente RRHH JCF*\n\n"
                "No tienes permisos para realizar "
                "esa consulta."
            )

        result = count_employees(
            filters=filters
        )

        count = result.get(
            "count",
            0,
        )

        description = build_filter_description(
            filters
        )

        if description:

            return (
                "👥 *Agente RRHH JCF*\n\n"
                f"Hay *{count} trabajadores* "
                f"{description}."
            )

        return (
            "👥 *Agente RRHH JCF*\n\n"
            f"Actualmente hay *{count} trabajadores* "
            "registrados en RRHH."
        )

    # ========================================================
    # 4. BUSCAR TRABAJADORES
    # ========================================================

    if action == "search_employees":

        if not can_search_employees(
            employee
        ):

            return (
                "👥 *Agente RRHH JCF*\n\n"
                "Por privacidad, no tienes acceso "
                "al listado de otros trabajadores."
            )

        result = search_employees(
            filters=filters,
            max_records=30,
        )

        if not result.get(
            "found"
        ):

            return (
                "👥 *Agente RRHH JCF*\n\n"
                "No encontré trabajadores "
                "que coincidan con los criterios indicados."
            )

        return format_employee_list(
            result=result,
            requested_fields=requested_fields,
        )

    # ========================================================
    # 5. LISTAR TODOS
    # ========================================================

    if action == "list_employees":

        if not can_list_employees(
            employee
        ):

            return (
                "👥 *Agente RRHH JCF*\n\n"
                "Por privacidad, no tienes acceso "
                "al listado completo de trabajadores."
            )

        result = get_employees(
            max_records=30
        )

        if not result.get(
            "found"
        ):

            return (
                "👥 *Agente RRHH JCF*\n\n"
                "No encontré trabajadores registrados."
            )

        return format_employee_list(
            result=result,
            requested_fields=(
                requested_fields
                or [
                    "nombre",
                    "cargo",
                ]
            ),
        )

    # ========================================================
    # 6. PREGUNTA GENERAL
    # ========================================================

    return (
        "👥 *Agente RRHH JCF*\n\n"
        "Puedo ayudarte con tus datos registrados "
        "en RRHH, como correo, teléfono, dirección, "
        "cargo, fecha de ingreso o información "
        "contractual disponible."
    )


# ============================================================
# FORMATEAR PERSONA
# ============================================================

def format_employee_response(
    employee_data: dict,
    requested_fields: list,
) -> str:

    name = (
        employee_data.get(
            "nombre"
        )
        or "Trabajador"
    )

    if not requested_fields:

        requested_fields = [
            "nombre",
            "cargo",
            "email",
            "telefono",
            "region",
            "centro_negocios",
            "fecha_ingreso",
            "contrato_vigente",
        ]

    labels = {

        "nombre": "Nombre",

        "email": "Correo",

        "cargo": "Cargo",

        "contrato_vigente": (
            "Contrato vigente"
        ),

        "region": "Región",

        "cedula": "Cédula",

        "genero": "Género",

        "folio_trabajador": (
            "Folio trabajador"
        ),

        "fecha_ingreso": (
            "Fecha de ingreso"
        ),

        "fecha_renovacion_contrato": (
            "Fecha renovación contrato"
        ),

        "fecha_nacimiento": (
            "Fecha de nacimiento"
        ),

        "fecha_curso_altura": (
            "Fecha curso de altura"
        ),

        "telefono": "Teléfono",

        "direccion": "Dirección",

        "centro_negocios": (
            "Centro de negocios"
        ),

        "fecha_termino_contrato": (
            "Fecha término de contrato"
        ),

        "indefinido": (
            "Contrato indefinido"
        ),

        "plazo_fijo": (
            "Contrato a plazo fijo"
        ),

        "sueldo": "Sueldo",

        "vacaciones": "Vacaciones",

        "dias_vacaciones": (
            "Días de vacaciones"
        ),
    }

    lines = [
        "👥 *Agente RRHH JCF*",
        "",
    ]

    # Si pidió un único campo, evitamos una respuesta
    # demasiado grande.
    if len(
        requested_fields
    ) <= 1:

        for field in requested_fields:

            value = employee_data.get(
                field
            )

            label = labels.get(
                field,
                field,
            )

            if value in (
                None,
                "",
            ):

                return (
                    "👥 *Agente RRHH JCF*\n\n"
                    f"No tengo registrado tu dato de "
                    f"*{label.lower()}*."
                )

            if isinstance(
                value,
                bool,
            ):

                value = (
                    "Sí"
                    if value
                    else "No"
                )

            return (
                "👥 *Agente RRHH JCF*\n\n"
                f"{label}: *{value}*"
            )

    # ========================================================
    # RESPUESTA DE VARIOS CAMPOS
    # ========================================================

    lines.extend(
        [
            f"*{name}*",
            "",
        ]
    )

    for field in requested_fields:

        if field == "nombre":
            continue

        value = employee_data.get(
            field
        )

        if value in (
            None,
            "",
        ):
            continue

        if isinstance(
            value,
            bool,
        ):

            value = (
                "Sí"
                if value
                else "No"
            )

        label = labels.get(
            field,
            field,
        )

        lines.append(
            f"• {label}: {value}"
        )

    if len(
        lines
    ) == 4:

        lines.append(
            "No hay información disponible "
            "para los campos solicitados."
        )

    return "\n".join(
        lines
    )


# ============================================================
# FORMATEAR LISTA
# ============================================================

def format_employee_list(
    result: dict,
    requested_fields: list,
) -> str:

    records = result.get(
        "records",
        [],
    )

    total = result.get(
        "count",
        len(
            records
        ),
    )

    if not requested_fields:

        requested_fields = [
            "nombre",
            "cargo",
        ]

    lines = [
        "👥 *Agente RRHH JCF*",
        "",
        f"Encontré *{total} trabajadores*.",
        "",
    ]

    for employee in records:

        name = (
            employee.get(
                "nombre"
            )
            or "Sin nombre"
        )

        details = []

        for field in requested_fields:

            if field == "nombre":
                continue

            value = employee.get(
                field
            )

            if value in (
                None,
                "",
            ):
                continue

            if isinstance(
                value,
                bool,
            ):

                value = (
                    "Sí"
                    if value
                    else "No"
                )

            details.append(
                str(
                    value
                )
            )

        if details:

            lines.append(
                f"• {name} — "
                + " | ".join(
                    details
                )
            )

        else:

            lines.append(
                f"• {name}"
            )

    if total > len(
        records
    ):

        lines.extend(
            [
                "",
                (
                    f"Mostrando los primeros "
                    f"{len(records)} registros."
                ),
            ]
        )

    return "\n".join(
        lines
    )


# ============================================================
# DESCRIBIR FILTROS
# ============================================================

def build_filter_description(
    filters: dict,
) -> str:

    if not filters:

        return ""

    parts = []

    for field, value in filters.items():

        if field == "contrato_vigente":

            if value is True:

                parts.append(
                    "con contrato vigente"
                )

            elif value is False:

                parts.append(
                    "sin contrato vigente"
                )

        elif field == "cargo":

            parts.append(
                f"con cargo {value}"
            )

        elif field == "region":

            parts.append(
                f"en la región {value}"
            )

        elif field == "genero":

            parts.append(
                f"con género {value}"
            )

        elif field == "centro_negocios":

            parts.append(
                f"del centro de negocios {value}"
            )

        elif field == "indefinido":

            if value:

                parts.append(
                    "con contrato indefinido"
                )

        elif field == "plazo_fijo":

            if value:

                parts.append(
                    "con contrato a plazo fijo"
                )

    if not parts:

        return ""

    return " ".join(
        parts
    )