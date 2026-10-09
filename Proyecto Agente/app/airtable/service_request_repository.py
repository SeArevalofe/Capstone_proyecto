import re
import unicodedata

from functools import lru_cache

from app.airtable.client import (
    get_records,
    get_record,
    update_record,
    upload_attachment,
)

from app.config import (
    AIRTABLE_SERVICE_BASE_ID,
    AIRTABLE_SERVICE_REQUEST_TABLE_ID,
    AIRTABLE_SERVICE_QUOTE_FIELD,
    AIRTABLE_SERVICE_OC_FIELD,
    AIRTABLE_SERVICE_STATUS_FIELD,
    AIRTABLE_SERVICE_STATUS_ACTIVE_RECORD_ID,
    AIRTABLE_SERVICE_STATUS_PAUSED_RECORD_ID,
    AIRTABLE_SERVICE_TYPE_FIELD,
    AIRTABLE_SERVICE_TECHNICIAN_FIELD,
    AIRTABLE_SERVICE_HELPER_FIELD,
    AIRTABLE_SERVICE_SUPERVISOR_FIELD,
    AIRTABLE_SERVICE_ADDRESS_FIELD,
    AIRTABLE_SERVICE_DESCRIPTION_FIELD,
    AIRTABLE_SERVICE_IMAGES_FIELD,
    AIRTABLE_SERVICE_CLOSURE_TABLE_ID,
    AIRTABLE_CLOSURE_OC_FIELD,
    AIRTABLE_EMPLOYEE_BASE_ID,
    AIRTABLE_EMPLOYEE_TABLE_ID,
    AIRTABLE_EMPLOYEE_NAME_FIELD,
)

from app.agents.maestro.permissions import (
    get_assignment_field_for_employee,
)


# ============================================================
# ESTADOS OPERATIVOS
# ============================================================

ALLOWED_OPERATIONAL_STATUSES = {
    "programado",
    "activo",
    "pausado",
}

OPERATIONAL_STATUS_ORDER = {
    "programado": 1,
    "activo": 2,
    "pausado": 3,
}


def update_service_status_by_record_id(
    service_record_id: str,
    status: str,
) -> dict:

    service_record_id = str(
        service_record_id
        or ""
    ).strip()

    status = str(
        status
        or ""
    ).strip().upper()

    if not service_record_id:
        return {
            "updated": False,
            "reason": "missing_service_record_id",
        }

    if not status:
        return {
            "updated": False,
            "reason": "missing_service_status",
        }

    status_record_ids = {
        "ACTIVO": AIRTABLE_SERVICE_STATUS_ACTIVE_RECORD_ID,
        "PAUSADO": AIRTABLE_SERVICE_STATUS_PAUSED_RECORD_ID,
    }

    if status not in status_record_ids:
        return {
            "updated": False,
            "reason": "unsupported_service_status",
        }

    status_record_id = status_record_ids[status]

    if not status_record_id:
        return {
            "updated": False,
            "reason": "missing_service_status_record_id",
        }

    try:
        result = update_record(
            base_id=AIRTABLE_SERVICE_BASE_ID,
            table_id=AIRTABLE_SERVICE_REQUEST_TABLE_ID,
            record_id=service_record_id,
            fields={
                AIRTABLE_SERVICE_STATUS_FIELD: [
                    status_record_id,
                ],
            },
        )
    except Exception as error:
        print(
            "Error actualizando estado del servicio:",
            type(error).__name__,
            str(error),
        )
        return {
            "updated": False,
            "reason": "service_status_update_failed",
        }

    return {
        "updated": bool(
            result.get("updated")
        ),
        "record_id": service_record_id,
        "status": status,
    }


# ============================================================
# NORMALIZAR TEXTO
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
# NORMALIZAR ID DE SERVICIO
# ============================================================

def normalize_service_id(
    value,
) -> str:

    if value is None:
        return ""

    value = str(
        value
    ).strip()

    value = re.sub(
        r"\s*-\s*",
        " - ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.upper().strip()


# ============================================================
# EXTRAER COT BASE
#
# Ejemplos:
#
# COT37470
# COT37470 - OC
# COT37470 - GARANTIA
#
# -> COT37470
# ============================================================

def extract_base_quote(
    value,
) -> str:

    if value is None:
        return ""

    text = normalize_service_id(
        value
    )

    match = re.search(
        r"\bCOT\s*(\d{3,})\b",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return ""

    return (
        f"COT{match.group(1)}"
    )


# ============================================================
# ESCAPAR TEXTO PARA AIRTABLE
# ============================================================

def escape_airtable_string(
    value,
) -> str:

    value = str(
        value
        or ""
    )

    value = value.replace(
        "\\",
        "\\\\",
    )

    value = value.replace(
        "'",
        "\\'",
    )

    return value


# ============================================================
# NORMALIZAR CAMPOS VINCULADOS
# ============================================================

def normalize_assignment_values(
    value,
) -> list:

    if value is None:
        return []

    if isinstance(
        value,
        list,
    ):

        values = value

    else:

        values = [
            value
        ]

    result = []

    for item in values:

        if item is None:
            continue

        if isinstance(
            item,
            dict,
        ):

            raw_value = (
                item.get("id")
                or item.get("record_id")
                or item.get("name")
                or item.get("nombre")
                or item.get("value")
            )

        else:

            raw_value = item

        text = str(
            raw_value
            or ""
        ).strip()

        if (
            text
            and text not in result
        ):

            result.append(
                text
            )

    return result


# ============================================================
# NORMALIZAR DIRECCIÓN DEL SERVICIO
#
# El campo de Airtable puede venir:
#
# ["Av. Apoquindo 4501, Las Condes"]
#
# o:
#
# "Av. Apoquindo 4501, Las Condes"
# ============================================================

# ============================================================
# OBTENER DIRECCIÓN DEL SERVICIO DESDE AIRTABLE
#
# Airtable normalmente devuelve los fields usando el NOMBRE
# del campo, aunque en config tengamos guardado el Field ID.
#
# Por eso intentamos:
#
# 1. Valor configurado.
# 2. Nombre exacto conocido.
# 3. Detección flexible por nombre.
# ============================================================

# ============================================================
# NORMALIZAR DIRECCIÓN DEL SERVICIO
#
# Airtable puede devolver la dirección como:
#
# "Pedro Lagos 980, Santiago"
#
# o como Lookup:
#
# ["Pedro Lagos 980, Santiago"]
#
# o incluso como diccionario.
#
# Siempre devolvemos un texto limpio.
# ============================================================

def normalize_service_address(
    value,
) -> str:

    if value is None:

        return ""

    # ========================================================
    # LISTA / LOOKUP DE AIRTABLE
    # ========================================================

    if isinstance(
        value,
        list,
    ):

        addresses = []

        for item in value:

            # ------------------------------------------------
            # ITEM COMO DICCIONARIO
            # ------------------------------------------------

            if isinstance(
                item,
                dict,
            ):

                raw_value = (
                    item.get(
                        "address"
                    )
                    or item.get(
                        "name"
                    )
                    or item.get(
                        "value"
                    )
                    or item.get(
                        "text"
                    )
                    or ""
                )

            else:

                raw_value = item

            text = str(
                raw_value
                or ""
            ).strip()

            text = re.sub(
                r"\s+",
                " ",
                text,
            )

            if (
                text
                and text not in addresses
            ):

                addresses.append(
                    text
                )

        if not addresses:

            return ""

        return ", ".join(
            addresses
        )

    # ========================================================
    # DICCIONARIO DIRECTO
    # ========================================================

    if isinstance(
        value,
        dict,
    ):

        raw_value = (
            value.get(
                "address"
            )
            or value.get(
                "name"
            )
            or value.get(
                "value"
            )
            or value.get(
                "text"
            )
            or ""
        )

        text = str(
            raw_value
            or ""
        ).strip()

        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        return text

    # ========================================================
    # TEXTO NORMAL
    # ========================================================

    text = str(
        value
        or ""
    ).strip()

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text

# ============================================================
# PAGINACIÓN GENÉRICA
# ============================================================

def get_all_records(
    table_id: str,
) -> list:

    records = []
    offset = None

    while True:

        params = {
            "pageSize": 100,
        }

        if offset:

            params[
                "offset"
            ] = offset

        result = get_records(
            base_id=AIRTABLE_SERVICE_BASE_ID,
            table_id=table_id,
            params=params,
        )

        records.extend(
            result.get(
                "records",
                [],
            )
        )

        offset = result.get(
            "offset"
        )

        if not offset:
            break

    return records

# ============================================================
# OBTENER DIRECCIÓN DEL SERVICIO DESDE LOS CAMPOS
#
# Primero intenta con el campo configurado:
#
# AIRTABLE_SERVICE_ADDRESS_FIELD
#
# Si por alguna razón no viene ahí, intenta encontrar
# automáticamente campos cuyo nombre contenga "direccion".
# ============================================================

def get_service_address_from_fields(
    fields: dict,
) -> str:

    if not isinstance(
        fields,
        dict,
    ):

        return ""

    # ========================================================
    # 1. CAMPO CONFIGURADO
    # ========================================================

    configured_value = fields.get(
        AIRTABLE_SERVICE_ADDRESS_FIELD
    )

    configured_address = normalize_service_address(
        configured_value
    )

    if configured_address:

        return configured_address

    # ========================================================
    # 2. BUSCAR CAMPOS QUE CONTENGAN "DIRECCION"
    #
    # Esto sirve como respaldo si Airtable devuelve el campo
    # utilizando su nombre en lugar del Field ID configurado.
    # ========================================================

    for field_name, field_value in fields.items():

        normalized_field_name = normalize_text(
            field_name
        )

        if "direccion" not in normalized_field_name:

            continue

        address = normalize_service_address(
            field_value
        )

        if address:

            print()
            print("=" * 70)
            print("📍 DIRECCIÓN ENCONTRADA POR FALLBACK")
            print("=" * 70)

            print(
                "Campo:",
                field_name,
            )

            print(
                "Valor:",
                address,
            )

            print("=" * 70)

            return address

    # ========================================================
    # 3. NO ENCONTRADA
    # ========================================================

    return ""

def normalize_service_type_value(
    value,
) -> str:

    if isinstance(
        value,
        list,
    ):
        return next(
            (
                str(item).strip()
                for item in value
                if str(item).strip()
            ),
            "",
        )

    return str(
        value
        or ""
    ).strip()


# ============================================================
# CONVERTIR REGISTRO DE SERVICIO
# ============================================================

def build_service_result(
    record: dict,
    status_label: str = None,
) -> dict:

    fields = record.get(
        "fields",
        {},
    )

    if not isinstance(
        fields,
        dict,
    ):

        fields = {}

    raw_status = fields.get(
        AIRTABLE_SERVICE_STATUS_FIELD
    )

    normalized_label = normalize_text(
        status_label
    )

    if (
        normalized_label
        not in ALLOWED_OPERATIONAL_STATUSES
    ):

        normalized_label = ""

    # ========================================================
    # DIRECCIÓN
    # ========================================================

    service_address = get_service_address_from_fields(
        fields
    )

    service_description = normalize_service_address(
        fields.get(
            AIRTABLE_SERVICE_DESCRIPTION_FIELD
        )
    )

    return {
        "record_id": record.get(
            "id"
        ),

        "quote_number": fields.get(
            AIRTABLE_SERVICE_QUOTE_FIELD
        ),

        "oc": fields.get(
            AIRTABLE_SERVICE_OC_FIELD
        ),

        "service_address": (
            service_address
        ),

        "service_description": (
            service_description
        ),

        "status": raw_status,

        "status_label": (
            normalized_label.upper()
            if normalized_label
            else None
        ),

        "service_type": normalize_service_type_value(
            fields.get(
                AIRTABLE_SERVICE_TYPE_FIELD
            )
        ),

        "record": record,

        "fields": fields,
    }


# ============================================================
# FÓRMULA DE ASIGNACIÓN
# ============================================================

def build_assignment_formula(
    employee_name: str,
    assignment_field: str,
) -> str:

    escaped_name = escape_airtable_string(
        employee_name.lower()
    )

    # Los delimitadores evitan coincidencias parciales entre nombres.
    return (
        "FIND("
        f"',{escaped_name},',"
        "','&LOWER("
        "ARRAYJOIN("
        f"{{{assignment_field}}},"
        "','"
        ")"
        ")&','"
        ")"
    )


@lru_cache(maxsize=512)
def linked_assignment_is_employee_record(record_id: str):

    record_id = str(record_id or "").strip()

    if not record_id.startswith("rec"):
        return False

    try:
        record = get_record(
            base_id=AIRTABLE_EMPLOYEE_BASE_ID,
            table_id=AIRTABLE_EMPLOYEE_TABLE_ID,
            record_id=record_id,
        )
    except Exception as error:
        response = getattr(error, "response", None)

        if getattr(response, "status_code", None) == 404:
            return False

        # Los errores transitorios no se cachean; la siguiente consulta
        # podrá volver a comprobar el origen del vínculo.
        raise

    if not isinstance(record, dict):
        return None

    if record.get("found") is False:
        return False

    fields = record.get("fields") or (
        record.get("record") or {}
    ).get("fields") or {}
    returned_record_id = (
        record.get("record_id")
        or record.get("id")
        or (record.get("record") or {}).get("id")
    )

    if str(returned_record_id or "").strip() != record_id:
        return None

    linked_employee_name = normalize_text(
        fields.get(AIRTABLE_EMPLOYEE_NAME_FIELD)
        or fields.get("Nombre del Tecnico")
        or fields.get("Nombre + ID")
    )
    raw_rrhh_ids = fields.get("RRHH")
    if not isinstance(raw_rrhh_ids, list):
        raw_rrhh_ids = [raw_rrhh_ids]

    return {
        "record_id": record_id,
        "employee_record_ids": {
            str(value).strip()
            for value in raw_rrhh_ids
            if str(value or "").strip().startswith("rec")
        },
        "employee_name": linked_employee_name,
    }


def record_matches_employee_assignment(
    record: dict,
    assignment_field: str,
    employee: dict,
) -> bool:

    fields = (
        record.get("fields", {})
        if isinstance(record, dict)
        else {}
    )
    raw_assignments = fields.get(assignment_field)
    if not isinstance(raw_assignments, list):
        raw_assignments = [raw_assignments]

    linked_record_ids = {
        str(value).strip()
        for value in raw_assignments
        if str(value or "").strip().startswith("rec")
    }
    employee_record_id = str(
        employee.get("record_id") or ""
    ).strip()

    # Si coinciden, no hace falta consultar el origen del vínculo.
    if employee_record_id.startswith("rec") and linked_record_ids:
        if employee_record_id in linked_record_ids:
            return True

        # El caso de IDs RRHH2 duplicados se confirmó únicamente en
        # Supervisor Asignado. Técnico y Ayudante conservan su validación
        # histórica por Record ID exacto.
        if assignment_field != AIRTABLE_SERVICE_SUPERVISOR_FIELD:
            return False

        try:
            comparable_ids = [
                linked_assignment_is_employee_record(record_id)
                for record_id in linked_record_ids
            ]
        except Exception:
            # Si no se puede comprobar el origen, no se relaja la
            # asignación: falla cerrado para evitar falsos positivos.
            return False

        employee_name = normalize_text(
            employee.get("nombre")
        )
        comparable_records = [
            value
            for value in comparable_ids
            if isinstance(value, dict)
        ]
        comparable_names = {
            value.get("employee_name")
            for value in comparable_records
            if value.get("employee_name")
        }

        if employee_record_id and any(
            employee_record_id in value.get(
                "employee_record_ids",
                set(),
            )
            for value in comparable_records
        ):
            return True

        if employee_name and employee_name in comparable_names:
            return True

        if comparable_records:
            return False

        if not all(value is False for value in comparable_ids):
            return False

        # Para vínculos a otra tabla, se conserva la coincidencia exacta
        # por nombre que Airtable ya aplicó en build_assignment_formula().
        return True

    # Compatibilidad con respuestas antiguas/mocks que solo traen nombres.
    return True

# ============================================================
# FÓRMULA DE ESTADO
# ============================================================

def build_status_formula(
    status: str,
) -> str:

    normalized_status = normalize_text(
        status
    )

    if (
        normalized_status
        not in ALLOWED_OPERATIONAL_STATUSES
    ):

        raise ValueError(
            f"Estado operativo inválido: {status}"
        )

    escaped_status = escape_airtable_string(
        normalized_status
    )

    return (
        "LOWER("
        f"{{{AIRTABLE_SERVICE_STATUS_FIELD}}}"
        f")='{escaped_status}'"
    )


# ============================================================
# SERVICIOS DEL TRABAJADOR POR ESTADO
# ============================================================

def get_services_for_employee_by_status(
    employee: dict,
    status: str,
) -> dict:

    if not isinstance(
        employee,
        dict,
    ):

        return {
            "found": False,
            "count": 0,
            "records": [],
            "reason": "invalid_employee",
        }

    employee_name = str(
        employee.get(
            "nombre"
        )
        or ""
    ).strip()

    if not employee_name:

        return {
            "found": False,
            "count": 0,
            "records": [],
            "reason": "missing_employee_name",
        }

    normalized_status = normalize_text(
        status
    )

    if (
        normalized_status
        not in ALLOWED_OPERATIONAL_STATUSES
    ):

        return {
            "found": False,
            "count": 0,
            "records": [],
            "reason": "invalid_status",
        }

    assignment_field = (
        get_assignment_field_for_employee(
            employee
        )
    )

    print()
    print("=" * 70)
    print("🔎 CONSULTA DE SERVICIOS DEL TRABAJADOR")
    print("=" * 70)
    print("Trabajador:", employee_name)
    print("Cargo:", employee.get("cargo"))
    print("Campo asignación:", assignment_field)
    print("Estado:", normalized_status.upper())
    print("=" * 70)

    if not assignment_field:

        return {
            "found": False,
            "count": 0,
            "records": [],
            "reason": "no_assignment_field",
        }

    status_formula = build_status_formula(
        normalized_status
    )

    assignment_formula = build_assignment_formula(
        employee_name=employee_name,
        assignment_field=assignment_field,
    )

    formula = (
        "AND("
        f"{status_formula},"
        f"{assignment_formula}"
        ")"
    )

    print()
    print("=" * 70)
    print("⚡ AIRTABLE - CONSULTA FILTRADA")
    print("=" * 70)
    print(
        "Tabla:",
        AIRTABLE_SERVICE_REQUEST_TABLE_ID,
    )
    print(
        "Fórmula:",
        formula,
    )
    print("=" * 70)

    records = []
    offset = None

    while True:

        params = {
            "filterByFormula": formula,
            "pageSize": 100,
        }

        if offset:

            params[
                "offset"
            ] = offset

        result = get_records(
            base_id=AIRTABLE_SERVICE_BASE_ID,
            table_id=AIRTABLE_SERVICE_REQUEST_TABLE_ID,
            params=params,
        )

        records.extend(
            result.get(
                "records",
                [],
            )
        )

        offset = result.get(
            "offset"
        )

        if not offset:
            break

    records = [
        record
        for record in records
        if record_matches_employee_assignment(
            record=record,
            assignment_field=assignment_field,
            employee=employee,
        )
    ]

    services = [
        build_service_result(
            record=record,
            status_label=normalized_status,
        )
        for record in records
    ]

    services.sort(
        key=lambda service: (
            normalize_text(
                service.get(
                    "quote_number"
                )
            ),
            normalize_text(
                service.get(
                    "oc"
                )
            ),
        )
    )

    print()
    print("=" * 70)
    print("📋 SERVICIOS ENCONTRADOS")
    print("=" * 70)

    print(
        "Cantidad:",
        len(
            services
        ),
    )

    for service in services:

        print(
            "•",
            service.get(
                "quote_number"
            ),
            "| Dirección:",
            service.get(
                "service_address"
            ),
            "| Estado:",
            service.get(
                "status_label"
            ),
        )

    print("=" * 70)

    return {
        "found": bool(
            services
        ),

        "count": len(
            services
        ),

        "records": services,

        "statuses": [
            normalized_status.upper()
        ],

        "assignment_field": (
            assignment_field
        ),
    }


# ============================================================
# SERVICIOS DEL TRABAJADOR EN VARIOS ESTADOS
# ============================================================

def get_services_for_employee(
    employee: dict,
    statuses=None,
) -> dict:

    if statuses is None:

        statuses = [
            "PROGRAMADO",
            "ACTIVO",
            "PAUSADO",
        ]

    if isinstance(
        statuses,
        str,
    ):

        statuses = [
            statuses
        ]

    normalized_statuses = []

    for status in statuses:

        normalized = normalize_text(
            status
        )

        if (
            normalized
            in ALLOWED_OPERATIONAL_STATUSES
            and normalized
            not in normalized_statuses
        ):

            normalized_statuses.append(
                normalized
            )

    if not normalized_statuses:

        return {
            "found": False,
            "count": 0,
            "records": [],
            "reason": "invalid_status",
        }

    all_services = []
    assignment_field = None

    for status in normalized_statuses:

        result = get_services_for_employee_by_status(
            employee=employee,
            status=status,
        )

        if (
            result.get(
                "reason"
            )
            in (
                "invalid_employee",
                "missing_employee_name",
                "no_assignment_field",
            )
        ):

            return result

        if not assignment_field:

            assignment_field = result.get(
                "assignment_field"
            )

        all_services.extend(
            result.get(
                "records",
                [],
            )
        )

    # ========================================================
    # ELIMINAR DUPLICADOS
    # ========================================================

    unique_services = []
    seen = set()

    for service in all_services:

        record_id = str(
            service.get(
                "record_id"
            )
            or ""
        ).strip()

        if record_id:

            key = record_id

        else:

            key = (
                normalize_text(
                    service.get(
                        "quote_number"
                    )
                ),
                normalize_text(
                    service.get(
                        "oc"
                    )
                ),
                normalize_text(
                    service.get(
                        "status_label"
                    )
                ),
            )

        if key in seen:
            continue

        seen.add(
            key
        )

        unique_services.append(
            service
        )

    unique_services.sort(
        key=lambda service: (
            OPERATIONAL_STATUS_ORDER.get(
                normalize_text(
                    service.get(
                        "status_label"
                    )
                ),
                99,
            ),
            normalize_text(
                service.get(
                    "quote_number"
                )
            ),
        )
    )

    return {
        "found": bool(
            unique_services
        ),

        "count": len(
            unique_services
        ),

        "records": unique_services,

        "statuses": [
            status.upper()
            for status in normalized_statuses
        ],

        "assignment_field": (
            assignment_field
        ),
    }


# ============================================================
# PROGRAMADOS
# ============================================================

def get_programmed_services_for_employee(
    employee: dict,
) -> dict:

    return get_services_for_employee_by_status(
        employee=employee,
        status="PROGRAMADO",
    )


# ============================================================
# ACTIVOS
# ============================================================

def get_active_services_for_employee(
    employee: dict,
) -> dict:

    return get_services_for_employee_by_status(
        employee=employee,
        status="ACTIVO",
    )


# ============================================================
# PAUSADOS
# ============================================================

def get_paused_services_for_employee(
    employee: dict,
) -> dict:

    return get_services_for_employee_by_status(
        employee=employee,
        status="PAUSADO",
    )


# ============================================================
# TODOS LOS OPERATIVOS
# ============================================================

def get_operational_services_for_employee(
    employee: dict,
) -> dict:

    return get_services_for_employee(
        employee=employee,
        statuses=[
            "PROGRAMADO",
            "ACTIVO",
            "PAUSADO",
        ],
    )


# ============================================================
# BUSCAR SERVICIO ASIGNADO
# ============================================================

def get_assigned_service(
    identifier: str,
    employee: dict,
    statuses=None,
) -> dict:

    wanted = normalize_text(
        identifier
    )

    wanted_base = normalize_text(
        extract_base_quote(
            identifier
        )
    )

    if not wanted:

        return {
            "found": False,
            "reason": "empty_identifier",
        }

    result = get_services_for_employee(
        employee=employee,
        statuses=(
            statuses
            or [
                "PROGRAMADO",
                "ACTIVO",
                "PAUSADO",
            ]
        ),
    )

    services = result.get(
        "records",
        [],
    )

    matches = []

    for service in services:

        quote_value = service.get(
            "quote_number"
        )

        quote = normalize_text(
            quote_value
        )

        quote_base = normalize_text(
            extract_base_quote(
                quote_value
            )
        )

        oc = normalize_text(
            service.get(
                "oc"
            )
        )

        quote_match = (
            wanted == quote
            or (
                wanted_base
                and quote_base
                and wanted_base == quote_base
            )
        )

        oc_match = (
            wanted == oc
            if oc
            else False
        )

        if (
            quote_match
            or oc_match
        ):

            matches.append(
                service
            )

    if not matches:

        return {
            "found": False,
            "reason": "not_assigned",
        }

    if len(
        matches
    ) > 1:

        return {
            "found": False,
            "multiple": True,
            "count": len(
                matches
            ),
            "records": matches,
        }

    service = dict(
        matches[
            0
        ]
    )

    service[
        "found"
    ] = True

    service[
        "multiple"
    ] = False

    return service


def get_assigned_service_by_record_id(
    record_id: str,
    employee: dict,
    statuses=None,
) -> dict:

    wanted_record_id = str(
        record_id
        or ""
    ).strip()

    if not wanted_record_id:

        return {
            "found": False,
            "reason": "empty_record_id",
        }

    result = get_services_for_employee(
        employee=employee,
        statuses=(
            statuses
            or [
                "PROGRAMADO",
                "ACTIVO",
                "PAUSADO",
            ]
        ),
    )

    for service in result.get(
        "records",
        [],
    ):

        if str(
            service.get(
                "record_id"
            )
            or ""
        ).strip() != wanted_record_id:

            continue

        matched_service = dict(
            service
        )

        matched_service[
            "found"
        ] = True

        matched_service[
            "multiple"
        ] = False

        return matched_service

    return {
        "found": False,
        "reason": "not_assigned",
    }


# ============================================================
# BUSCAR SOLICITUD EXACTA
# ============================================================

def get_quote(
    quote_number: str,
) -> dict:

    requested = normalize_service_id(
        quote_number
    )

    if not requested:

        return {
            "found": False,
            "multiple": False,
            "reason": "invalid_quote",
        }

    escaped = escape_airtable_string(
        requested
    )

    formula = (
        "UPPER("
        "TRIM("
        f"{{{AIRTABLE_SERVICE_QUOTE_FIELD}}}"
        ")"
        ")="
        f"'{escaped}'"
    )

    result = get_records(
        base_id=AIRTABLE_SERVICE_BASE_ID,
        table_id=AIRTABLE_SERVICE_REQUEST_TABLE_ID,
        params={
            "filterByFormula": formula,
            "pageSize": 10,
        },
    )

    matches = result.get(
        "records",
        [],
    )

    if not matches:

        return {
            "found": False,
            "multiple": False,
            "reason": "quote_not_found",
        }

    if len(
        matches
    ) > 1:

        return {
            "found": True,
            "multiple": True,
            "count": len(
                matches
            ),
            "records": matches,
        }

    record = matches[
        0
    ]

    fields = record.get(
        "fields",
        {},
    )

    return {
        "found": True,
        "multiple": False,
        "record": record,
        "record_id": record.get(
            "id"
        ),
        "fields": fields,
        "service_id": fields.get(
            AIRTABLE_SERVICE_QUOTE_FIELD
        ),
        "quote_number": fields.get(
            AIRTABLE_SERVICE_QUOTE_FIELD
        ),
        "service_address": normalize_service_address(
            fields.get(
                AIRTABLE_SERVICE_ADDRESS_FIELD
            )
        ),
    }


# ============================================================
# OBTENER REGISTRO POR RECORD ID
# ============================================================

def get_record_by_id(
    record_id: str,
) -> dict:

    return get_record(
        base_id=AIRTABLE_SERVICE_BASE_ID,
        table_id=AIRTABLE_SERVICE_REQUEST_TABLE_ID,
        record_id=record_id,
    )


# ============================================================
# CONTEXTO OPERACIONAL DE UNA COT
# ============================================================

def get_operational_service_context(
    cot: str,
    employee: dict,
    statuses=None,
    record_id: str = None,
) -> dict:

    requested_cot = str(
        cot
        or ""
    ).strip()

    record_id = str(
        record_id
        or ""
    ).strip()

    cot = extract_base_quote(
        requested_cot
    )

    if not cot and not record_id:

        return {
            "found": False,
            "reason": "invalid_cot",
        }

    if statuses is None:

        statuses = [
            "PROGRAMADO",
            "ACTIVO",
            "PAUSADO",
        ]

    # ========================================================
    # VALIDAR ASIGNACIÓN
    # ========================================================

    if record_id:

        service = get_assigned_service_by_record_id(
            record_id=record_id,
            employee=employee,
            statuses=statuses,
        )

    else:

        service = get_assigned_service(
            identifier=requested_cot,
            employee=employee,
            statuses=statuses,
        )

    if not service.get(
        "found"
    ):

        return service

    service_record_id = str(
        service.get(
            "record_id"
        )
        or ""
    ).strip()

    fields = service.get(
        "fields",
        {},
    )

    if not isinstance(
        fields,
        dict,
    ):

        fields = {}

    fresh_record = None

    # ========================================================
    # RELEER SERVICIO EXACTO
    # ========================================================

    if service_record_id:

        try:

            fresh_result = get_record_by_id(
                service_record_id
            )

            if fresh_result.get(
                "found"
            ):

                fresh_record = fresh_result.get(
                    "record"
                )

                if isinstance(
                    fresh_record,
                    dict,
                ):

                    fresh_fields = fresh_record.get(
                        "fields",
                        {},
                    )

                    if isinstance(
                        fresh_fields,
                        dict,
                    ):

                        fields = fresh_fields

        except Exception as error:

            print()
            print("=" * 70)
            print("⚠️ ERROR RELEYENDO SERVICIO")
            print("=" * 70)
            print(
                type(error).__name__,
                str(error),
            )
            print("=" * 70)

    # ========================================================
    # ASIGNACIONES
    # ========================================================

    raw_technicians = fields.get(
        AIRTABLE_SERVICE_TECHNICIAN_FIELD
    )

    raw_helpers = fields.get(
        AIRTABLE_SERVICE_HELPER_FIELD
    )

    raw_supervisors = fields.get(
        AIRTABLE_SERVICE_SUPERVISOR_FIELD
    )

    technicians = normalize_assignment_values(
        raw_technicians
    )

    helpers = normalize_assignment_values(
        raw_helpers
    )

    supervisors = normalize_assignment_values(
        raw_supervisors
    )

    # ========================================================
    # DIRECCIÓN DEL SERVICIO
    # ========================================================

    raw_service_address = fields.get(
    AIRTABLE_SERVICE_ADDRESS_FIELD
    )

    service_address = get_service_address_from_fields(
        fields
    )

    service_description = normalize_service_address(
        fields.get(
            AIRTABLE_SERVICE_DESCRIPTION_FIELD
        )
    )

    # ========================================================
    # COT / OC / ESTADO
    # ========================================================

    quote_number = (
        fields.get(
            AIRTABLE_SERVICE_QUOTE_FIELD
        )
        or service.get(
            "quote_number"
        )
    )

    oc = (
        fields.get(
            AIRTABLE_SERVICE_OC_FIELD
        )
        or service.get(
            "oc"
        )
    )

    raw_status = (
        fields.get(
            AIRTABLE_SERVICE_STATUS_FIELD
        )
        or service.get(
            "status"
        )
    )

    status_label = (
        service.get(
            "status_label"
        )
        or raw_status
    )

    # ========================================================
    # TIPO DE SERVICIO
    # ========================================================

    raw_service_type = fields.get(
        AIRTABLE_SERVICE_TYPE_FIELD
    )

    if isinstance(
        raw_service_type,
        list,
    ):

        service_type = next(
            (
                str(value).strip()
                for value in raw_service_type
                if str(value).strip()
            ),
            "",
        )

    else:

        service_type = str(
            raw_service_type
            or ""
        ).strip()

    # ========================================================
    # DEBUG
    # ========================================================

    print()
    print("=" * 70)
    print("📦 CONTEXTO OPERACIONAL")
    print("=" * 70)

    print(
        "COT:",
        quote_number,
    )

    print(
        "Record ID:",
        service_record_id,
    )

    print(
        "Dirección oficial:",
        service_address
        or "NO INFORMADA",
    )

    print(
        "Ayudantes:",
        helpers,
    )

    print(
        "Técnicos:",
        technicians,
    )

    print(
        "Supervisores:",
        supervisors,
    )

    print("=" * 70)

    return {
        "found": True,

        "record_id": service_record_id,

        "cot": (
            extract_base_quote(
                quote_number
            )
            or cot
        ),

        "quote_number": (
            quote_number
        ),

        "oc": oc,

        "status": (
            status_label
        ),

        "service_type": (
            service_type
        ),

        "service_address": (
            service_address
        ),

        "service_description": (
            service_description
        ),

        "technicians": (
            technicians
        ),

        "helpers": (
            helpers
        ),

        "supervisors": (
            supervisors
        ),

        "fields": fields,

        "record": (
            fresh_record
            or service.get(
                "record"
            )
        ),
    }


# ============================================================
# VARIANTES DEL IDENTIFICADOR
# ============================================================

def build_identifier_variants(
    value,
) -> list:

    original = normalize_service_id(
        value
    )

    if not original:

        return []

    variants = [
        original
    ]

    base_quote = extract_base_quote(
        original
    )

    if (
        base_quote
        and base_quote not in variants
    ):

        variants.append(
            base_quote
        )

    without_oc = re.sub(
        r"\s*-\s*OC\s*$",
        "",
        original,
        flags=re.IGNORECASE,
    ).strip()

    if (
        without_oc
        and without_oc not in variants
    ):

        variants.append(
            without_oc
        )

    if base_quote:

        with_oc = (
            f"{base_quote} - OC"
        )

        if with_oc not in variants:

            variants.append(
                with_oc
            )

    return variants


# ============================================================
# BUSCAR CIERRE EXACTO
# ============================================================

def find_closure_record_exact(
    identifier,
) -> dict:

    variants = build_identifier_variants(
        identifier
    )

    if not variants:

        return {
            "found": False,
            "multiple": False,
            "reason": "missing_identifier",
        }

    attempted_variants = []

    for variant in variants:

        escaped = escape_airtable_string(
            variant
        )

        formula = (
            "UPPER("
            "TRIM("
            f"{{{AIRTABLE_CLOSURE_OC_FIELD}}}"
            ")"
            ")"
            f"='{escaped}'"
        )

        attempted_variants.append(
            variant
        )

        result = get_records(
            base_id=AIRTABLE_SERVICE_BASE_ID,
            table_id=AIRTABLE_SERVICE_CLOSURE_TABLE_ID,
            params={
                "filterByFormula": formula,
                "pageSize": 20,
            },
        )

        matches = result.get(
            "records",
            [],
        )

        if not matches:
            continue

        if len(
            matches
        ) > 1:

            return {
                "found": False,
                "multiple": True,
                "count": len(
                    matches
                ),
                "records": matches,
                "reason": (
                    "multiple_exact_closure_records"
                ),
                "identifier": identifier,
                "matched_variant": variant,
                "attempted_variants": (
                    attempted_variants
                ),
            }

        record = matches[
            0
        ]

        return {
            "found": True,
            "multiple": False,
            "record": record,
            "record_id": record.get(
                "id"
            ),
            "fields": record.get(
                "fields",
                {},
            ),
            "matched_identifier": identifier,
            "matched_variant": variant,
            "attempted_variants": (
                attempted_variants
            ),
            "match_mode": "exact",
        }

    return {
        "found": False,
        "multiple": False,
        "reason": "closure_record_not_found",
        "identifier": identifier,
        "variants": variants,
        "attempted_variants": (
            attempted_variants
        ),
    }


# ============================================================
# BUSCAR CIERRE POR COT BASE
# ============================================================

def find_closure_record_by_base_quote(
    identifier,
) -> dict:

    base_quote = extract_base_quote(
        identifier
    )

    if not base_quote:

        return {
            "found": False,
            "multiple": False,
            "reason": "missing_base_quote",
        }

    escaped = escape_airtable_string(
        base_quote
    )

    formula = (
        "FIND("
        f"'{escaped}',"
        "UPPER("
        f"{{{AIRTABLE_CLOSURE_OC_FIELD}}}"
        ")"
        ")"
    )

    result = get_records(
        base_id=AIRTABLE_SERVICE_BASE_ID,
        table_id=AIRTABLE_SERVICE_CLOSURE_TABLE_ID,
        params={
            "filterByFormula": formula,
            "pageSize": 20,
        },
    )

    matches = result.get(
        "records",
        [],
    )

    if not matches:

        return {
            "found": False,
            "multiple": False,
            "reason": "closure_record_not_found",
            "identifier": identifier,
            "base_quote": base_quote,
        }

    if len(
        matches
    ) > 1:

        return {
            "found": False,
            "multiple": True,
            "count": len(
                matches
            ),
            "records": matches,
            "reason": "multiple_closure_records",
            "identifier": identifier,
            "base_quote": base_quote,
        }

    record = matches[
        0
    ]

    return {
        "found": True,
        "multiple": False,
        "record": record,
        "record_id": record.get(
            "id"
        ),
        "fields": record.get(
            "fields",
            {},
        ),
        "matched_identifier": (
            base_quote
        ),
        "match_mode": "base_quote",
    }


# ============================================================
# BUSCAR CIERRE
# ============================================================

def find_closure_record(
    identifier,
) -> dict:

    exact_result = find_closure_record_exact(
        identifier
    )

    if (
        exact_result.get(
            "found"
        )
        or exact_result.get(
            "multiple"
        )
    ):

        return exact_result

    base_result = (
        find_closure_record_by_base_quote(
            identifier
        )
    )

    if (
        base_result.get(
            "found"
        )
        or base_result.get(
            "multiple"
        )
    ):

        return base_result

    return {
        "found": False,
        "multiple": False,
        "reason": "closure_record_not_found",
        "identifier": identifier,
    }


# ============================================================
# COMPATIBILIDAD
# ============================================================

def find_closure_record_by_oc(
    oc,
) -> dict:

    return find_closure_record(
        oc
    )


# ============================================================
# BUSCAR CIERRE PARA SERVICIO
# ============================================================

def find_closure_for_service(
    quote_number=None,
    oc=None,
) -> dict:

    tried = []

    # ========================================================
    # COT
    # ========================================================

    if quote_number:

        quote_text = str(
            quote_number
        ).strip()

        if quote_text:

            tried.append(
                {
                    "type": "quote",
                    "value": quote_text,
                }
            )

            result = find_closure_record(
                quote_text
            )

            if (
                result.get(
                    "found"
                )
                or result.get(
                    "multiple"
                )
            ):

                result[
                    "lookup_type"
                ] = "quote"

                result[
                    "lookup_value"
                ] = quote_text

                result[
                    "tried"
                ] = tried

                return result

    # ========================================================
    # OC FALLBACK
    # ========================================================

    if oc:

        oc_text = str(
            oc
        ).strip()

        if oc_text:

            already_tried = any(
                normalize_service_id(
                    item.get(
                        "value"
                    )
                )
                == normalize_service_id(
                    oc_text
                )
                for item in tried
            )

            if not already_tried:

                tried.append(
                    {
                        "type": "oc",
                        "value": oc_text,
                    }
                )

                result = find_closure_record(
                    oc_text
                )

                if (
                    result.get(
                        "found"
                    )
                    or result.get(
                        "multiple"
                    )
                ):

                    result[
                        "lookup_type"
                    ] = "oc"

                    result[
                        "lookup_value"
                    ] = oc_text

                    result[
                        "tried"
                    ] = tried

                    return result

    return {
        "found": False,
        "multiple": False,
        "reason": "closure_record_not_found",
        "tried": tried,
    }


def upload_field_image(
    quote_number: str,
    record_id: str = None,
    file_path: str = None,
    filename: str = None,
    mime_type: str = "image/jpeg",
    **_compatibility,
) -> dict:

    result = None

    if record_id:
        try:
            result = get_record_by_id(record_id)
        except Exception as error:
            return {
                "uploaded": False,
                "reason": "service_lookup_error",
                "error": str(error),
            }

    if not result or not result.get("found"):
        try:
            result = get_quote(quote_number)
        except Exception as error:
            return {
                "uploaded": False,
                "reason": "service_lookup_error",
                "error": str(error),
            }

    if not result.get("found"):
        return {"uploaded": False, "reason": "service_not_found"}

    if result.get("multiple"):
        return {"uploaded": False, "reason": "duplicate_service"}

    service_record = result.get("record") or {}
    service_record_id = (
        result.get("record_id")
        or service_record.get("id")
    )

    upload_result = upload_attachment(
        base_id=AIRTABLE_SERVICE_BASE_ID,
        record_id=service_record_id,
        field_id=AIRTABLE_SERVICE_IMAGES_FIELD,
        file_path=file_path,
        filename=filename,
        mime_type=mime_type,
    )

    if upload_result.get("uploaded"):
        upload_result["service_record_id"] = service_record_id

    return upload_result
