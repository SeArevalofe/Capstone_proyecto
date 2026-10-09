import base64
import os

from urllib.parse import quote

import requests

from app.config import (
    AIRTABLE_TOKEN,
    AIRTABLE_SERVICE_BASE_ID,
    AIRTABLE_SERVICE_CLOSURE_TABLE_ID,
    AIRTABLE_CLOSURE_SERVICE_LINK_FIELD,
    AIRTABLE_CLOSURE_TECHNICIAN_FIELD,
    AIRTABLE_CLOSURE_HELPER_FIELD,
    AIRTABLE_CLOSURE_OBSERVATIONS_FIELD,
    AIRTABLE_CLOSURE_MITIGATION_CAUSE_FIELD,
    AIRTABLE_CLOSURE_SERVICE_SHEET_FIELD,
    AIRTABLE_CLOSURE_SERVICE_PHOTOS_FIELD,
    AIRTABLE_CLOSURE_INTERNAL_REPORT_FIELD,
    AIRTABLE_CLOSURE_OC_FIELD,
    AIRTABLE_CLOSURE_WORKER_TABLE_ID,
    AIRTABLE_CLOSURE_WORKER_RRHH_FIELD,
)

from app.airtable.client import (
    create_record,
    get_records,
    update_record,
)


# ============================================================
# LIMPIAR TEXTO
# ============================================================

def clean_text(
    value,
) -> str:

    return str(
        value
        or ""
    ).strip()

# ============================================================
# NORMALIZAR RECORD ID
# ============================================================

def normalize_record_id(
    value,
):

    value = clean_text(
        value
    )

    if not value.startswith(
        "rec"
    ):

        return None

    return value

# ============================================================
# NORMALIZAR LISTA DE RECORD IDS
# ============================================================

def normalize_record_ids(
    values,
) -> list:

    if values is None:

        return []

    if not isinstance(
        values,
        list,
    ):

        values = [
            values
        ]

    result = []

    for value in values:

        record_id = normalize_record_id(
            value
        )

        if (
            record_id
            and record_id not in result
        ):

            result.append(
                record_id
            )

    return result


def escape_airtable_formula_text(
    value,
) -> str:

    return clean_text(value).replace(
        "\\",
        "\\\\",
    ).replace(
        "'",
        "\\'",
    )


def find_service_closure_by_service_record_id(
    service_record_id: str,
    service_identifier: str,
) -> dict:

    service_record_id = normalize_record_id(
        service_record_id
    )
    service_identifier = clean_text(
        service_identifier
    )

    if not service_record_id:
        return {
            "found": False,
            "multiple": False,
            "reason": "missing_service_record_id",
        }

    if not service_identifier:
        return {
            "found": False,
            "multiple": False,
            "reason": "missing_service_identifier",
        }

    escaped_identifier = escape_airtable_formula_text(
        service_identifier.upper()
    )
    formula = (
        "UPPER(TRIM("
        f"{{{AIRTABLE_CLOSURE_OC_FIELD}}}"
        "))="
        f"'{escaped_identifier}'"
    )

    try:
        result = get_records(
            base_id=AIRTABLE_SERVICE_BASE_ID,
            table_id=AIRTABLE_SERVICE_CLOSURE_TABLE_ID,
            params={
                "filterByFormula": formula,
                "maxRecords": 1,
                "pageSize": 1,
                "returnFieldsByFieldId": True,
            },
        )
        records = result.get("records") or []
    except Exception as error:
        print(
            "Error buscando cierre para sincronización:",
            type(error).__name__,
        )
        return {
            "found": False,
            "multiple": False,
            "reason": "closure_lookup_error",
        }

    for record in records:
        fields = record.get("fields") or {}
        linked_services = normalize_record_ids(
            fields.get(AIRTABLE_CLOSURE_SERVICE_LINK_FIELD)
        )
        if service_record_id in linked_services:
            return {
                "found": True,
                "multiple": False,
                "reason": None,
                "record_id": record.get("id"),
                "fields": fields,
            }

    return {
        "found": False,
        "multiple": False,
        "reason": "closure_not_found",
    }


def sync_report_to_closure_record(
    closure_record_id: str,
    report_text: str,
) -> dict:

    closure_record_id = normalize_record_id(
        closure_record_id
    )
    report_text = clean_text(
        report_text
    )

    if not closure_record_id:
        return {"synced": False, "reason": "missing_closure_record_id"}

    if not report_text:
        return {"synced": False, "reason": "empty_report"}

    try:
        result = update_record(
            base_id=AIRTABLE_SERVICE_BASE_ID,
            table_id=AIRTABLE_SERVICE_CLOSURE_TABLE_ID,
            record_id=closure_record_id,
            fields={
                AIRTABLE_CLOSURE_INTERNAL_REPORT_FIELD: report_text,
            },
        )
    except Exception as error:
        print(
            "Error sincronizando informe interno de cierre:",
            type(error).__name__,
            "record_id=", closure_record_id,
        )
        return {
            "synced": False,
            "reason": "closure_report_update_error",
        }

    return {
        "synced": bool(result.get("updated")),
        "reason": None if result.get("updated") else "closure_report_update_failed",
        "record_id": closure_record_id,
    }


def sync_report_to_existing_closure(
    service_record_id: str,
    service_identifier: str,
    report_text: str,
) -> dict:

    lookup = find_service_closure_by_service_record_id(
        service_record_id=service_record_id,
        service_identifier=service_identifier,
    )

    if not lookup.get("found"):
        return {
            "synced": False,
            "reason": lookup.get("reason") or "closure_not_found",
        }

    return sync_report_to_closure_record(
        closure_record_id=lookup.get("record_id"),
        report_text=report_text,
    )


def sync_activity_report_to_closure(
    closure_record_id: str,
    service_record_id: str,
    service_identifier: str,
) -> dict:

    # Import local para mantener los repositorios desacoplados al cargar.
    from app.airtable.activity_repository import (
        get_field_report_from_activity,
    )

    report = get_field_report_from_activity(
        service_record_id=service_record_id,
        service_identifier=service_identifier,
    )

    if not report.get("found"):
        return {
            "synced": False,
            "reason": report.get("reason") or "activity_report_not_found",
        }

    return sync_report_to_closure_record(
        closure_record_id=closure_record_id,
        report_text=report.get("report_text"),
    )

# ============================================================
# OBTENER TODOS LOS REGISTROS DE UNA TABLA
#
# get_records() obtiene una página.
#
# Esta función sigue automáticamente los offset de Airtable
# para que el sistema continúe funcionando aunque la tabla
# de técnicos/supervisores supere los 100 registros.
# ============================================================

def get_all_records(
    base_id: str,
    table_id: str,
    params: dict = None,
) -> list:

    all_records = []

    current_params = dict(
        params
        or {}
    )

    while True:

        result = get_records(
            base_id=base_id,
            table_id=table_id,
            params=(
                current_params
                if current_params
                else None
            ),
        )

        records = result.get(
            "records",
            [],
        )

        if isinstance(
            records,
            list,
        ):

            all_records.extend(
                records
            )

        offset = clean_text(
            result.get(
                "offset"
            )
        )

        if not offset:

            break

        current_params[
            "offset"
        ] = offset

    return all_records

# ============================================================
# CARGAR TABLA DE TÉCNICOS / SUPERVISORES
#
# TABLA DESTINO DEL CAMPO:
#
# "Tecnico que Cierra Servicio"
#
# tblVWWEWk657HJPWv
#
# Esta tabla posee un vínculo llamado RRHH hacia RRHH2.
#
# Un usuario puede llegar a esta función de dos maneras:
#
# 1) Record ID de RRHH2
#    recXXXX de tblWaKSb4JrgeuMRS
#
# 2) Record ID de la propia tabla de técnicos
#    recXXXX de tblVWWEWk657HJPWv
#
# La función siguiente soporta ambos casos.
# ============================================================

def get_closure_workers() -> list:

    try:

        records = get_all_records(
            base_id=(
                AIRTABLE_SERVICE_BASE_ID
            ),
            table_id=(
                AIRTABLE_CLOSURE_WORKER_TABLE_ID
            ),
        )

    except Exception as error:

        print()
        print("=" * 70)
        print("❌ ERROR LEYENDO TABLA DE TÉCNICOS")
        print("=" * 70)

        print(
            type(error).__name__,
            str(error),
        )

        print("=" * 70)

        raise

    return records


# ============================================================
# RESOLVER PERSONA PARA CIERRE
#
# ACEPTA:
#
# - Record ID de RRHH2
#
# o
#
# - Record ID de tblVWWEWk657HJPWv
#
# DEVUELVE:
#
# SIEMPRE el Record ID válido para el campo
# "Tecnico que Cierra Servicio".
#
# Esto permite utilizar:
#
# - Técnicos
# - Supervisores
#
# siempre que tengan su registro correspondiente en la tabla
# vinculada al campo de cierre.
# ============================================================

def resolve_closure_worker_record_id(
    source_record_id: str,
    workers=None,
) -> dict:

    source_record_id = normalize_record_id(
        source_record_id
    )

    if not source_record_id:

        return {
            "found": False,
            "reason": "invalid_worker_record_id",
            "record_id": None,
        }

    print()
    print("=" * 70)
    print("🔎 RESOLVIENDO PERSONA PARA CIERRE")
    print("=" * 70)

    print(
        "Record ID recibido:",
        source_record_id,
    )

    print(
        "Tabla destino:",
        AIRTABLE_CLOSURE_WORKER_TABLE_ID,
    )

    print("=" * 70)

    # ========================================================
    # OBTENER TABLA DESTINO
    # ========================================================

    try:

        if workers is None:

            workers = get_closure_workers()

    except Exception as error:

        return {
            "found": False,
            "reason": "closure_worker_lookup_error",
            "record_id": None,
            "error": str(
                error
            ),
        }

    if not isinstance(
        workers,
        list,
    ):

        workers = []

    # ========================================================
    # CASO 1:
    #
    # EL ID YA PERTENECE A LA TABLA DESTINO
    # ========================================================

    direct_matches = []

    for record in workers:

        record_id = normalize_record_id(
            record.get(
                "id"
            )
        )

        if record_id == source_record_id:

            direct_matches.append(
                record
            )

    if len(
        direct_matches
    ) == 1:

        record = direct_matches[
            0
        ]

        fields = record.get(
            "fields",
            {},
        )

        print()
        print("=" * 70)
        print("✅ PERSONA YA PERTENECE A TABLA DESTINO")
        print("=" * 70)

        print(
            "Record destino:",
            source_record_id,
        )

        print(
            "Nombre:",
            fields.get(
                "Nombre del Tecnico"
            ),
        )

        print("=" * 70)

        return {
            "found": True,
            "reason": None,
            "record_id": source_record_id,
            "source_record_id": source_record_id,
            "source_type": "closure_worker",
            "record": record,
            "fields": fields,
        }

    # ========================================================
    # CASO 2:
    #
    # EL ID PERTENECE A RRHH2.
    #
    # BUSCARLO DENTRO DEL CAMPO RRHH DE LA TABLA DESTINO.
    # ========================================================

    rrhh_matches = []

    for record in workers:

        fields = record.get(
            "fields",
            {},
        )

        rrhh_links = fields.get(
            AIRTABLE_CLOSURE_WORKER_RRHH_FIELD,
            [],
        )

        rrhh_links = normalize_record_ids(
            rrhh_links
        )

        if source_record_id in rrhh_links:

            rrhh_matches.append(
                record
            )

    # ========================================================
    # NO ENCONTRADO
    # ========================================================

    if not rrhh_matches:

        print()
        print("=" * 70)
        print("❌ PERSONA NO ENCONTRADA PARA CIERRE")
        print("=" * 70)

        print(
            "Record ID recibido:",
            source_record_id,
        )

        print(
            "No existe directamente en:",
            AIRTABLE_CLOSURE_WORKER_TABLE_ID,
        )

        print(
            "Ni fue encontrado mediante campo:",
            AIRTABLE_CLOSURE_WORKER_RRHH_FIELD,
        )

        print("=" * 70)

        return {
            "found": False,
            "reason": "closure_worker_not_found",
            "record_id": None,
            "source_record_id": source_record_id,
        }

    # ========================================================
    # DUPLICADO
    # ========================================================

    if len(
        rrhh_matches
    ) > 1:

        print()
        print("=" * 70)
        print("❌ PERSONA DUPLICADA EN TABLA DE TÉCNICOS")
        print("=" * 70)

        for record in rrhh_matches:

            print(
                record.get(
                    "id"
                ),
                record.get(
                    "fields",
                    {},
                ).get(
                    "Nombre del Tecnico"
                ),
            )

        print("=" * 70)

        return {
            "found": False,
            "reason": "multiple_closure_workers",
            "record_id": None,
            "source_record_id": source_record_id,
            "records": rrhh_matches,
        }

    # ========================================================
    # ENCONTRADO MEDIANTE RRHH
    # ========================================================

    record = rrhh_matches[
        0
    ]

    record_id = normalize_record_id(
        record.get(
            "id"
        )
    )

    fields = record.get(
        "fields",
        {},
    )

    if not record_id:

        return {
            "found": False,
            "reason": "closure_worker_missing_record_id",
            "record_id": None,
            "source_record_id": source_record_id,
        }

    print()
    print("=" * 70)
    print("✅ PERSONA RESUELTA PARA CIERRE")
    print("=" * 70)

    print(
        "Record origen RRHH:",
        source_record_id,
    )

    print(
        "Record destino:",
        record_id,
    )

    print(
        "Nombre:",
        fields.get(
            "Nombre del Tecnico"
        ),
    )

    print("=" * 70)

    return {
        "found": True,
        "reason": None,
        "record_id": record_id,
        "source_record_id": source_record_id,
        "source_type": "rrhh",
        "record": record,
        "fields": fields,
    }


# ============================================================
# RESOLVER VARIAS PERSONAS
#
# Utilizado principalmente para ayudantes.
#
# Cada ID puede venir:
#
# - desde RRHH2
#
# o
#
# - directamente desde tblVWWEWk657HJPWv
# ============================================================

def resolve_closure_worker_record_ids(
    source_record_ids,
) -> dict:

    source_record_ids = normalize_record_ids(
        source_record_ids
    )

    if not source_record_ids:

        return {
            "found": True,
            "record_ids": [],
            "workers": [],
        }

    try:

        workers = get_closure_workers()

    except Exception as error:

        return {
            "found": False,
            "reason": "closure_worker_lookup_error",
            "record_ids": [],
            "error": str(
                error
            ),
        }

    resolved_ids = []
    resolved_workers = []

    for source_record_id in source_record_ids:

        result = resolve_closure_worker_record_id(
            source_record_id=source_record_id,
            workers=workers,
        )

        if not result.get(
            "found"
        ):

            return {
                "found": False,
                "reason": result.get(
                    "reason",
                    "closure_worker_not_found",
                ),
                "record_ids": resolved_ids,
                "failed_record_id":
                    source_record_id,
                "worker_result":
                    result,
            }

        resolved_id = normalize_record_id(
            result.get(
                "record_id"
            )
        )

        if (
            resolved_id
            and resolved_id not in resolved_ids
        ):

            resolved_ids.append(
                resolved_id
            )

            resolved_workers.append(
                result
            )

    return {
        "found": True,
        "reason": None,
        "record_ids": resolved_ids,
        "workers": resolved_workers,
    }


# ============================================================
# CREAR FORMULARIO DE CIERRE
#
# CREA UNA FILA NUEVA EN:
#
# Cierre de Servicios
#
# CAMPOS EDITABLES:
#
# - ID_X
# - Tecnico que Cierra Servicio
# - Ayudante que Cierra Servicio
# - Observaciones
#
# "Servicio que Cierra" NO SE ESCRIBE.
#
# Ese campo es calculado por Airtable.
#
# ID_X enlaza el cierre con Solicitudes de Servicio.
# ============================================================

def create_service_closure_form(
    service_record_id: str,
    quote_number: str = None,
    technician_record_id: str = None,
    helper_record_ids=None,
    observations: str = None,
    oc=None,
    no_helper=None,
    mitigation_cause: str = None,
) -> dict:

    # ========================================================
    # NORMALIZAR SERVICIO
    # ========================================================

    service_record_id = normalize_record_id(
        service_record_id
    )

    quote_number = clean_text(
        quote_number
    )

    observations = clean_text(
        observations
    )

    oc = clean_text(
        oc
    )

    mitigation_cause = clean_text(
        mitigation_cause
    )

    # ========================================================
    # VALIDAR SERVICIO
    # ========================================================

    if not service_record_id:

        return {
            "created": False,
            "saved": False,
            "reason": "missing_service_record_id",
        }

    # ========================================================
    # VALIDAR TÉCNICO ORIGINAL
    # ========================================================

    technician_source_record_id = normalize_record_id(
        technician_record_id
    )

    if not technician_source_record_id:

        return {
            "created": False,
            "saved": False,
            "reason": "missing_technician_record_id",
        }

    # ========================================================
    # RESOLVER TÉCNICO / SUPERVISOR
    #
    # Convierte el Record ID de RRHH2 al Record ID válido
    # para "Tecnico que Cierra Servicio".
    #
    # Si ya viene de la tabla destino, lo conserva.
    # ========================================================

    technician_result = (
        resolve_closure_worker_record_id(
            technician_source_record_id
        )
    )

    if not technician_result.get(
        "found"
    ):

        return {
            "created": False,
            "saved": False,
            "reason": technician_result.get(
                "reason",
                "closure_worker_not_found",
            ),
            "technician_source_record_id":
                technician_source_record_id,
            "technician_result":
                technician_result,
        }

    technician_record_id = normalize_record_id(
        technician_result.get(
            "record_id"
        )
    )

    if not technician_record_id:

        return {
            "created": False,
            "saved": False,
            "reason": "missing_resolved_technician_record_id",
        }

    # ========================================================
    # AYUDANTES
    #
    # Si no_helper=True, ignoramos cualquier ID de ayudante.
    #
    # Esto mantiene compatibilidad con operaciones/service.py.
    # ========================================================

    helper_source_record_ids = normalize_record_ids(
        helper_record_ids
    )

    if no_helper is True:

        helper_source_record_ids = []

    helper_record_ids = []

    if helper_source_record_ids:

        helpers_result = (
            resolve_closure_worker_record_ids(
                helper_source_record_ids
            )
        )

        if not helpers_result.get(
            "found"
        ):

            return {
                "created": False,
                "saved": False,
                "reason": helpers_result.get(
                    "reason",
                    "closure_helper_not_found",
                ),
                "helper_source_record_ids":
                    helper_source_record_ids,
                "helpers_result":
                    helpers_result,
            }

        helper_record_ids = normalize_record_ids(
            helpers_result.get(
                "record_ids"
            )
        )

    # ========================================================
    # CONSTRUIR PAYLOAD
    #
    # IMPORTANTE:
    #
    # AIRTABLE_CLOSURE_SERVICE_LINK_FIELD debe ser ID_X:
    #
    # fldzA9Zub8a9ihoZe
    #
    # NO:
    #
    # fldEtm438uASwVl46
    #
    # porque "Servicio que Cierra" es fórmula.
    # ========================================================

    fields = {
        AIRTABLE_CLOSURE_SERVICE_LINK_FIELD: [
            service_record_id
        ],

        AIRTABLE_CLOSURE_TECHNICIAN_FIELD: [
            technician_record_id
        ],

        AIRTABLE_CLOSURE_OBSERVATIONS_FIELD:
            observations,
    }

    # ========================================================
    # AYUDANTE
    #
    # Si no existe, NO se envía el campo.
    # ========================================================

    if helper_record_ids:

        fields[
            AIRTABLE_CLOSURE_HELPER_FIELD
        ] = helper_record_ids

    if mitigation_cause:
        fields[
            AIRTABLE_CLOSURE_MITIGATION_CAUSE_FIELD
        ] = mitigation_cause

    # ========================================================
    # DEBUG
    # ========================================================

    print()
    print("=" * 70)
    print("🧾 CREANDO CIERRE DE SERVICIO")
    print("=" * 70)

    print(
        "Tabla cierre:",
        AIRTABLE_SERVICE_CLOSURE_TABLE_ID,
    )

    print(
        "COT:",
        quote_number
        or "NO INFORMADA",
    )

    print(
        "OC:",
        oc
        or "SIN OC",
    )

    print(
        "Solicitud Record ID:",
        service_record_id,
    )

    print()
    print(
        "Técnico origen:",
        technician_source_record_id,
    )

    print(
        "Técnico destino:",
        technician_record_id,
    )

    print(
        "Técnico nombre:",
        technician_result.get(
            "fields",
            {},
        ).get(
            "Nombre del Tecnico"
        ),
    )

    print()
    print(
        "Ayudantes origen:",
        helper_source_record_ids,
    )

    print(
        "Ayudantes destino:",
        helper_record_ids,
    )

    print(
        "No helper:",
        no_helper,
    )

    print()
    print(
        "Observaciones:",
        observations
        or "VACÍO",
    )

    print()
    print(
        "Payload enviado a Airtable:"
    )

    print(
        fields
    )

    print("=" * 70)

    # ========================================================
    # CREAR REGISTRO
    # ========================================================

    try:

        result = create_record(
            base_id=(
                AIRTABLE_SERVICE_BASE_ID
            ),
            table_id=(
                AIRTABLE_SERVICE_CLOSURE_TABLE_ID
            ),
            fields=fields,
        )

    except Exception as error:

        print()
        print("=" * 70)
        print("❌ ERROR CREANDO CIERRE")
        print("=" * 70)

        print(
            type(error).__name__,
            str(error),
        )

        print("=" * 70)

        return {
            "created": False,
            "saved": False,
            "reason": "airtable_create_error",
            "error": str(
                error
            ),
            "quote_number": quote_number,
            "service_record_id":
                service_record_id,
            "technician_source_record_id":
                technician_source_record_id,
            "technician_record_id":
                technician_record_id,
            "helper_source_record_ids":
                helper_source_record_ids,
            "helper_record_ids":
                helper_record_ids,
        }

    # ========================================================
    # VALIDAR RESPUESTA
    # ========================================================

    created = bool(
        result.get(
            "created"
        )
    )

    closure_record_id = normalize_record_id(
        result.get(
            "record_id"
        )
    )

    # ========================================================
    # DEBUG FINAL
    # ========================================================

    print()
    print("=" * 70)

    if created:

        print(
            "✅ CIERRE DE SERVICIO CREADO"
        )

        print(
            "COT:",
            quote_number,
        )

        print(
            "Solicitud Record ID:",
            service_record_id,
        )

        print(
            "Técnico Record ID:",
            technician_record_id,
        )

        print(
            "Ayudantes Record IDs:",
            helper_record_ids,
        )

        print(
            "Nuevo cierre Record ID:",
            closure_record_id,
        )

    else:

        print(
            "❌ AIRTABLE NO CONFIRMÓ CREACIÓN"
        )

        print(
            "Respuesta:",
            result,
        )

    print("=" * 70)

    return {
        "created": created,
        "saved": created,
        "updated": False,
        "new_record": created,

        "reason": (
            None
            if created
            else "airtable_create_failed"
        ),

        "record_id":
            closure_record_id,

        "closure_record_id":
            closure_record_id,

        "quote_number":
            quote_number,

        "oc": (
            oc
            or None
        ),

        "service_record_id":
            service_record_id,

        "technician_source_record_id":
            technician_source_record_id,

        "technician_record_id":
            technician_record_id,

        "helper_source_record_ids":
            helper_source_record_ids,

        "helper_record_ids":
            helper_record_ids,

        "observations":
            observations,

        "fields": result.get(
            "fields",
            {},
        ),
    }


# ============================================================
# COMPATIBILIDAD CON OPERACIONES/SERVICE.PY
#
# Se mantiene el nombre save_service_closure_form.
#
# También acepta no_helper para compatibilidad con versiones
# anteriores/nuevas de operaciones/service.py.
# ============================================================

def save_service_closure_form(
    service_record_id: str,
    quote_number: str = None,
    technician_record_id: str = None,
    helper_record_ids=None,
    observations: str = None,
    oc=None,
    no_helper=None,
    mitigation_cause: str = None,
    append_observations: bool = False,
) -> dict:

    if append_observations:
        existing = find_service_closure_by_service_record_id(
            service_record_id=service_record_id,
            service_identifier=quote_number,
        )

        if existing.get("reason") == "closure_lookup_error":
            return {
                "saved": False,
                "reason": "closure_lookup_error",
            }

        if existing.get("found"):
            closure_record_id = normalize_record_id(
                existing.get("record_id")
            )
            existing_fields = existing.get("fields") or {}
            previous_observations = clean_text(
                existing_fields.get(
                    AIRTABLE_CLOSURE_OBSERVATIONS_FIELD
                )
            )
            new_observations = clean_text(observations)

            if not new_observations:
                combined_observations = previous_observations
            elif (
                previous_observations == new_observations
                or previous_observations.endswith(
                    "\n" + new_observations
                )
            ):
                combined_observations = previous_observations
            elif previous_observations:
                combined_observations = (
                    previous_observations
                    + "\n"
                    + new_observations
                )
            else:
                combined_observations = new_observations

            fields = {
                AIRTABLE_CLOSURE_OBSERVATIONS_FIELD:
                    combined_observations,
            }
            mitigation_cause = clean_text(mitigation_cause)
            if mitigation_cause:
                fields[
                    AIRTABLE_CLOSURE_MITIGATION_CAUSE_FIELD
                ] = mitigation_cause

            try:
                result = update_record(
                    base_id=AIRTABLE_SERVICE_BASE_ID,
                    table_id=AIRTABLE_SERVICE_CLOSURE_TABLE_ID,
                    record_id=closure_record_id,
                    fields=fields,
                )
            except Exception as error:
                return {
                    "saved": False,
                    "updated": False,
                    "reason": "airtable_update_error",
                    "error": str(error),
                }

            return {
                "saved": bool(result.get("updated")),
                "created": False,
                "updated": bool(result.get("updated")),
                "new_record": False,
                "reason": (
                    None
                    if result.get("updated")
                    else "airtable_update_failed"
                ),
                "record_id": closure_record_id,
                "closure_record_id": closure_record_id,
                "observations": combined_observations,
            }

    return create_service_closure_form(
        service_record_id=(
            service_record_id
        ),

        quote_number=(
            quote_number
        ),

        technician_record_id=(
            technician_record_id
        ),

        helper_record_ids=(
            helper_record_ids
        ),

        observations=(
            observations
        ),

        oc=(
            oc
        ),

        no_helper=(
            no_helper
        ),

        mitigation_cause=(
            mitigation_cause
        ),
    )


# ============================================================
# LEER ARCHIVO
# ============================================================

def read_file_as_base64(
    file_path: str,
) -> dict:

    file_path = clean_text(
        file_path
    )

    if not file_path:

        return {
            "ok": False,
            "reason": "missing_file_path",
        }

    if not os.path.isfile(
        file_path
    ):

        return {
            "ok": False,
            "reason": "file_not_found",
        }

    try:

        with open(
            file_path,
            "rb",
        ) as file:

            file_bytes = file.read()

    except OSError as error:

        return {
            "ok": False,
            "reason": "file_read_error",
            "error": str(
                error
            ),
        }

    if not file_bytes:

        return {
            "ok": False,
            "reason": "empty_file",
        }

    encoded_file = (
        base64.b64encode(
            file_bytes
        )
        .decode(
            "utf-8"
        )
    )

    return {
        "ok": True,
        "file_bytes":
            file_bytes,
        "encoded_file":
            encoded_file,
    }


# ============================================================
# SUBIR ARCHIVO A CAMPO ATTACHMENT
#
# Utiliza directamente el Record ID del cierre.
# ============================================================

def upload_attachment_to_closure(
    closure_record_id: str,
    field_id: str,
    file_path: str,
    filename: str = None,
    mime_type: str = "image/jpeg",
) -> dict:

    closure_record_id = normalize_record_id(
        closure_record_id
    )

    field_id = clean_text(
        field_id
    )

    file_path = clean_text(
        file_path
    )

    filename = clean_text(
        filename
        or (
            os.path.basename(
                file_path
            )
            if file_path
            else ""
        )
    )

    mime_type = clean_text(
        mime_type
        or "image/jpeg"
    )

    # ========================================================
    # VALIDACIONES
    # ========================================================

    if not closure_record_id:

        return {
            "uploaded": False,
            "reason": "missing_closure_record_id",
        }

    if not field_id:

        return {
            "uploaded": False,
            "reason": "missing_field_id",
        }

    file_result = read_file_as_base64(
        file_path
    )

    if not file_result.get(
        "ok"
    ):

        return {
            "uploaded": False,
            "reason": file_result.get(
                "reason"
            ),
            "error": file_result.get(
                "error"
            ),
        }

    encoded_file = file_result.get(
        "encoded_file"
    )

    file_bytes = file_result.get(
        "file_bytes",
        b"",
    )

    # ========================================================
    # URL AIRTABLE CONTENT API
    # ========================================================

    field_path = quote(
        field_id,
        safe="",
    )

    url = (
        "https://content.airtable.com/v0/"
        f"{AIRTABLE_SERVICE_BASE_ID}/"
        f"{closure_record_id}/"
        f"{field_path}/"
        "uploadAttachment"
    )

    headers = {
        "Authorization":
            f"Bearer {AIRTABLE_TOKEN}",

        "Content-Type":
            "application/json",
    }

    payload = {
        "contentType":
            mime_type,
        "filename":
            filename,
        "file":
            encoded_file,
    }

    # ========================================================
    # DEBUG
    # ========================================================

    print()
    print("=" * 70)
    print("📷 SUBIENDO ARCHIVO A CIERRE")
    print("=" * 70)

    print(
        "Record cierre:",
        closure_record_id,
    )

    print(
        "Campo:",
        field_id,
    )

    print(
        "Archivo:",
        filename,
    )

    print(
        "Tipo:",
        mime_type,
    )

    print(
        "Tamaño:",
        len(
            file_bytes
        ),
        "bytes",
    )

    print("=" * 70)

    # ========================================================
    # SUBIR
    # ========================================================

    try:

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=60,
        )

    except requests.RequestException as error:

        return {
            "uploaded": False,
            "reason": "airtable_connection_error",
            "error": str(
                error
            ),
        }

    print(
        "Status Airtable:",
        response.status_code,
    )

    if not response.ok:

        print()
        print("=" * 70)
        print("❌ ERROR SUBIENDO ARCHIVO")
        print("=" * 70)

        print(
            response.text
        )

        print("=" * 70)

        return {
            "uploaded": False,
            "reason": "airtable_upload_failed",
            "status_code":
                response.status_code,
            "response":
                response.text,
        }

    try:

        result = response.json()

    except ValueError:

        result = {}

    attachment_id = None

    result_fields = result.get(
        "fields",
        {},
    )

    if not isinstance(
        result_fields,
        dict,
    ):

        result_fields = {}

    attachments = result_fields.get(
        field_id,
        [],
    )

    if (
        isinstance(
            attachments,
            list,
        )
        and attachments
    ):

        last_attachment = attachments[
            -1
        ]

        if isinstance(
            last_attachment,
            dict,
        ):

            attachment_id = (
                last_attachment.get(
                    "id"
                )
            )

    print()
    print("=" * 70)
    print("✅ ARCHIVO SUBIDO")
    print("=" * 70)

    print(
        "Record cierre:",
        closure_record_id,
    )

    print(
        "Attachment ID:",
        attachment_id,
    )

    print("=" * 70)

    return {
        "uploaded": True,
        "closure_record_id":
            closure_record_id,
        "attachment_id":
            attachment_id,
        "filename":
            filename,
        "mime_type":
            mime_type,
        "field_id":
            field_id,
    }


# ============================================================
# SUBIR FOTO HOJA DE SERVICIO
# ============================================================

def upload_service_sheet_photo(
    closure_record_id: str,
    file_path: str,
    filename: str = None,
    mime_type: str = "image/jpeg",
) -> dict:

    return upload_attachment_to_closure(
        closure_record_id=(
            closure_record_id
        ),

        field_id=(
            AIRTABLE_CLOSURE_SERVICE_SHEET_FIELD
        ),

        file_path=(
            file_path
        ),

        filename=(
            filename
        ),

        mime_type=(
            mime_type
        ),
    )


# ============================================================
# SUBIR FOTO DEL SERVICIO
# ============================================================

def upload_service_photo(
    closure_record_id: str,
    file_path: str,
    filename: str = None,
    mime_type: str = "image/jpeg",
) -> dict:

    return upload_attachment_to_closure(
        closure_record_id=(
            closure_record_id
        ),

        field_id=(
            AIRTABLE_CLOSURE_SERVICE_PHOTOS_FIELD
        ),

        file_path=(
            file_path
        ),

        filename=(
            filename
        ),

        mime_type=(
            mime_type
        ),
    )
