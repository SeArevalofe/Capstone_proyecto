import math

from app.config import (
    AIRTABLE_SERVICE_BASE_ID,
    AIRTABLE_ACTIVITY_TABLE_ID,
    AIRTABLE_ACTIVITY_FIELD_ID_CUADRO,
    AIRTABLE_ACTIVITY_FIELD_START_LOCATION,
    AIRTABLE_ACTIVITY_FIELD_TECHNICIAN,
    AIRTABLE_ACTIVITY_FIELD_HELPER,
    AIRTABLE_ACTIVITY_FIELD_RECORD_IDENTIFIER,
    AIRTABLE_ACTIVITY_REPORT_FIELD,
)

from app.airtable.client import (
    create_record,
    get_records,
    update_record,
)

from app.geolocation.reverse_geocoder import (
    geocode_address_google,
)


# ============================================================
# CAMPO AIRTABLE - DISTANCIA INICIO
#
# Distancia en kilómetros.
# ============================================================

AIRTABLE_ACTIVITY_FIELD_START_DISTANCE = (
    "fldnLc685RkqhaBuW"
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
# NORMALIZAR COORDENADA
# ============================================================

def normalize_coordinate(
    value,
):

    if value is None:
        return None

    try:

        return float(
            value
        )

    except (
        TypeError,
        ValueError,
    ):

        return None


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


# ============================================================
# ESCAPAR TEXTO AIRTABLE
# ============================================================

def escape_airtable_formula_text(
    value,
) -> str:

    value = clean_text(
        value
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
# DISTANCIA HAVERSINE
#
# Devuelve distancia geográfica en kilómetros.
#
# No consume API.
# ============================================================

def calculate_distance_km(
    latitude_1,
    longitude_1,
    latitude_2,
    longitude_2,
):

    latitude_1 = normalize_coordinate(
        latitude_1
    )

    longitude_1 = normalize_coordinate(
        longitude_1
    )

    latitude_2 = normalize_coordinate(
        latitude_2
    )

    longitude_2 = normalize_coordinate(
        longitude_2
    )

    if (
        latitude_1 is None
        or longitude_1 is None
        or latitude_2 is None
        or longitude_2 is None
    ):

        return None

    earth_radius_km = 6371.0088

    lat1 = math.radians(
        latitude_1
    )

    lon1 = math.radians(
        longitude_1
    )

    lat2 = math.radians(
        latitude_2
    )

    lon2 = math.radians(
        longitude_2
    )

    delta_lat = (
        lat2
        - lat1
    )

    delta_lon = (
        lon2
        - lon1
    )

    a = (
        math.sin(
            delta_lat / 2
        ) ** 2
        +
        math.cos(
            lat1
        )
        *
        math.cos(
            lat2
        )
        *
        math.sin(
            delta_lon / 2
        ) ** 2
    )

    # Protección contra errores mínimos
    # de punto flotante.
    a = min(
        1.0,
        max(
            0.0,
            a,
        ),
    )

    c = (
        2
        * math.atan2(
            math.sqrt(
                a
            ),
            math.sqrt(
                1 - a
            ),
        )
    )

    distance_km = (
        earth_radius_km
        * c
    )

    return round(
        distance_km,
        2,
    )


# ============================================================
# RESOLVER DISTANCIA DE INICIO
#
# GPS WHATSAPP
#       ↓
# Dirección oficial
#       ↓
# Google Geocoding
#       ↓
# Coordenadas servicio
#       ↓
# Haversine
#       ↓
# Distancia KM
# ============================================================

def resolve_start_distance(
    service_address: str,
    start_latitude=None,
    start_longitude=None,
) -> dict:

    service_address = clean_text(
        service_address
    )

    start_latitude = normalize_coordinate(
        start_latitude
    )

    start_longitude = normalize_coordinate(
        start_longitude
    )

    print()
    print("=" * 70)
    print("📏 CALCULANDO DISTANCIA DE INICIO")
    print("=" * 70)

    print(
        "Dirección servicio:",
        service_address,
    )

    print(
        "Latitud inicio:",
        start_latitude,
    )

    print(
        "Longitud inicio:",
        start_longitude,
    )

    print("=" * 70)

    # ========================================================
    # DIRECCIÓN FALTANTE
    # ========================================================

    if not service_address:

        return {
            "calculated": False,
            "reason": "missing_service_address",
            "distance_km": None,
        }

    # ========================================================
    # GPS FALTANTE
    # ========================================================

    if (
        start_latitude is None
        or start_longitude is None
    ):

        return {
            "calculated": False,
            "reason": "missing_start_coordinates",
            "distance_km": None,
        }

    # ========================================================
    # GEOCODIFICAR DIRECCIÓN DEL SERVICIO
    # ========================================================

    service_location = geocode_address_google(
        service_address
    )

    if not service_location.get(
        "resolved"
    ):

        return {
            "calculated": False,

            "reason": (
                service_location.get(
                    "reason"
                )
                or "service_geocoding_failed"
            ),

            "distance_km": None,

            "geocoding_result": (
                service_location
            ),
        }

    service_latitude = normalize_coordinate(
        service_location.get(
            "latitude"
        )
    )

    service_longitude = normalize_coordinate(
        service_location.get(
            "longitude"
        )
    )

    # ========================================================
    # CALCULAR DISTANCIA
    # ========================================================

    distance_km = calculate_distance_km(
        latitude_1=start_latitude,
        longitude_1=start_longitude,
        latitude_2=service_latitude,
        longitude_2=service_longitude,
    )

    if distance_km is None:

        return {
            "calculated": False,
            "reason": "distance_calculation_failed",
            "distance_km": None,
        }

    print()
    print("=" * 70)
    print("✅ DISTANCIA DE INICIO CALCULADA")
    print("=" * 70)

    print(
        "Ubicación trabajador:",
        f"{start_latitude}, "
        f"{start_longitude}",
    )

    print(
        "Ubicación servicio:",
        f"{service_latitude}, "
        f"{service_longitude}",
    )

    print(
        "Dirección Google:",
        service_location.get(
            "formatted_address"
        ),
    )

    print(
        "Distancia:",
        distance_km,
        "km",
    )

    print("=" * 70)

    return {
        "calculated": True,

        "reason": None,

        "distance_km": (
            distance_km
        ),

        "start_latitude": (
            start_latitude
        ),

        "start_longitude": (
            start_longitude
        ),

        "service_latitude": (
            service_latitude
        ),

        "service_longitude": (
            service_longitude
        ),

        "service_address": (
            service_address
        ),

        "google_address": (
            service_location.get(
                "formatted_address"
            )
        ),

        "matched_variant": (
            service_location.get(
                "matched_variant"
            )
        ),
    }


# ============================================================
# BUSCAR REGISTRO DE INICIO POR SERVICIO
#
# REGLA:
#
# UNA COT = UNA FILA
#
# IMPORTANTE:
#
# La búsqueda se realiza directamente en Airtable
# utilizando la COT visible en ID Cuadro.
# ============================================================

def find_activity_start_by_service(
    service_record_id: str,
    cot: str = None,
) -> dict:

    service_record_id = normalize_record_id(
        service_record_id
    )

    cot = clean_text(
        cot
    )

    if not service_record_id:

        return {
            "found": False,
            "multiple": False,
            "reason": "missing_service_record_id",
            "records": [],
        }

    if not cot:

        return {
            "found": False,
            "multiple": False,
            "reason": "missing_cot",
            "records": [],
        }

    cot_upper = (
        cot.upper()
    )

    escaped_cot = escape_airtable_formula_text(
        cot_upper
    )

    # ========================================================
    # FILTRO EXACTO POR ID REGISTRO
    # ========================================================

    formula = (
        "UPPER(TRIM("
        f"{{{AIRTABLE_ACTIVITY_FIELD_RECORD_IDENTIFIER}}}"
        "))="
        f"'{escaped_cot}'"
    )

    print()
    print("=" * 70)
    print("🔎 BUSCANDO INICIO DE ACTIVIDAD EXISTENTE")
    print("=" * 70)

    print(
        "Tabla:",
        AIRTABLE_ACTIVITY_TABLE_ID,
    )

    print(
        "COT:",
        cot,
    )

    print(
        "Servicio Record ID:",
        service_record_id,
    )

    print(
        "Fórmula:",
        formula,
    )

    print("=" * 70)

    try:

        result = get_records(
            base_id=AIRTABLE_SERVICE_BASE_ID,
            table_id=AIRTABLE_ACTIVITY_TABLE_ID,
            params={
                "filterByFormula": formula,
                "maxRecords": 2,
                "pageSize": 2,
            },
        )

    except Exception as error:

        print()
        print("=" * 70)
        print("❌ ERROR BUSCANDO INICIO EXISTENTE")
        print("=" * 70)

        print(
            type(error).__name__,
            str(error),
        )

        print("=" * 70)

        return {
            "found": False,
            "multiple": False,
            "reason": "airtable_lookup_error",
            "error": str(
                error
            ),
            "records": [],
        }

    records = result.get(
        "records",
        [],
    )

    if not isinstance(
        records,
        list,
    ):

        records = []

    # ========================================================
    # MUY IMPORTANTE
    #
    # Además del ID Registro exacto, comprobamos el vínculo al
    # record de Solicitudes. Así no confundimos variantes de COT.
    # ========================================================

    matches = []

    for record in records:

        fields = record.get("fields", {})
        linked_services = normalize_record_ids(
            fields.get(AIRTABLE_ACTIVITY_FIELD_ID_CUADRO)
        )

        if service_record_id in linked_services:
            matches.append(record)

    print()
    print("=" * 70)
    print("📋 RESULTADO BÚSQUEDA INICIO")
    print("=" * 70)

    print(
        "COT:",
        cot,
    )

    print(
        "Registros Airtable:",
        len(
            records
        ),
    )

    print(
        "Coincidencias:",
        len(
            matches
        ),
    )

    for record in matches:

        print(
            "• Activity Record ID:",
            record.get(
                "id"
            ),
        )

    print("=" * 70)

    # ========================================================
    # NO EXISTE
    # ========================================================

    if not matches:

        return {
            "found": False,
            "multiple": False,
            "reason": "not_found",
            "records": [],
        }

    # ========================================================
    # DUPLICADOS
    # ========================================================

    if len(
        matches
    ) > 1:

        return {
            "found": False,

            "multiple": True,

            "count": len(
                matches
            ),

            "reason": (
                "duplicate_activity_records"
            ),

            "records": matches,
        }

    # ========================================================
    # EXACTAMENTE UNO
    # ========================================================

    record = matches[
        0
    ]

    return {
        "found": True,

        "multiple": False,

        "reason": None,

        "record": record,

        "record_id": record.get(
            "id"
        ),

        "fields": record.get(
            "fields",
            {},
        ),
    }


# ============================================================
# CREAR / ACTUALIZAR INICIO DE ACTIVIDAD
#
# REGLA:
#
# 0 registros = CREATE
# 1 registro  = UPDATE
# 2+          = ERROR
# ============================================================

def create_activity_start(
    cot: str,
    service_record_id: str,
    technician_name: str,
    technician_record_id: str,
    helper_names: list,
    helper_record_ids: list,
    location: str,
    service_address: str = None,
    start_latitude=None,
    start_longitude=None,
) -> dict:

    # ========================================================
    # NORMALIZAR
    # ========================================================

    cot = clean_text(
        cot
    )

    service_record_id = normalize_record_id(
        service_record_id
    )

    technician_name = clean_text(
        technician_name
    )

    technician_record_id = normalize_record_id(
        technician_record_id
    )

    helper_names = (
        helper_names
        if isinstance(
            helper_names,
            list,
        )
        else []
    )

    helper_record_ids = normalize_record_ids(
        helper_record_ids
    )

    location = clean_text(
        location
    )

    service_address = clean_text(
        service_address
    )

    start_latitude = normalize_coordinate(
        start_latitude
    )

    start_longitude = normalize_coordinate(
        start_longitude
    )

    # ========================================================
    # VALIDACIONES
    # ========================================================

    if not cot:

        return {
            "created": False,
            "updated": False,
            "saved": False,
            "reason": "missing_cot",
        }

    if not service_record_id:

        return {
            "created": False,
            "updated": False,
            "saved": False,
            "reason": "missing_service_record_id",
        }

    if not technician_record_id:

        return {
            "created": False,
            "updated": False,
            "saved": False,
            "reason": "missing_technician_record_id",
        }

    if not location:

        return {
            "created": False,
            "updated": False,
            "saved": False,
            "reason": "missing_location",
        }

    # ========================================================
    # BUSCAR REGISTRO EXISTENTE
    # ========================================================

    existing = find_activity_start_by_service(
        service_record_id=service_record_id,
        cot=cot,
    )

    # ========================================================
    # ERROR LOOKUP
    # ========================================================

    if (
        existing.get(
            "reason"
        )
        == "airtable_lookup_error"
    ):

        return {
            "created": False,
            "updated": False,
            "saved": False,
            "reason": "airtable_lookup_error",
            "error": existing.get(
                "error"
            ),
        }

    # ========================================================
    # DUPLICADOS
    # ========================================================

    if existing.get(
        "multiple"
    ):

        print()
        print("=" * 70)
        print("🚨 DUPLICADO DETECTADO")
        print("=" * 70)

        print(
            "COT:",
            cot,
        )

        print(
            "Cantidad:",
            existing.get(
                "count"
            ),
        )

        print("=" * 70)

        return {
            "created": False,

            "updated": False,

            "saved": False,

            "reason": (
                "duplicate_activity_records"
            ),

            "cot": cot,

            "service_record_id": (
                service_record_id
            ),

            "count": existing.get(
                "count"
            ),
        }

    # ========================================================
    # DISTANCIA
    #
    # Si Google no puede resolver la dirección,
    # NO bloqueamos el inicio.
    # ========================================================

    distance_result = resolve_start_distance(
        service_address=service_address,
        start_latitude=start_latitude,
        start_longitude=start_longitude,
    )

    distance_km = (
        distance_result.get(
            "distance_km"
        )
        if distance_result.get(
            "calculated"
        )
        else None
    )

    # ========================================================
    # PAYLOAD AIRTABLE
    # ========================================================

    fields = {
        AIRTABLE_ACTIVITY_FIELD_ID_CUADRO: [
            service_record_id
        ],

        AIRTABLE_ACTIVITY_FIELD_TECHNICIAN: [
            technician_record_id
        ],

        AIRTABLE_ACTIVITY_FIELD_START_LOCATION:
            location,
    }

    # ========================================================
    # AYUDANTES
    # ========================================================

    if helper_record_ids:

        fields[
            AIRTABLE_ACTIVITY_FIELD_HELPER
        ] = helper_record_ids

    # ========================================================
    # DISTANCIA
    # ========================================================

    if distance_km is not None:

        fields[
            AIRTABLE_ACTIVITY_FIELD_START_DISTANCE
        ] = distance_km

    # ========================================================
    # DEBUG
    # ========================================================

    print()
    print("=" * 70)

    if existing.get(
        "found"
    ):

        print(
            "♻️ ACTUALIZANDO INICIO DE SERVICIO"
        )

    else:

        print(
            "🚀 CREANDO INICIO DE SERVICIO"
        )

    print("=" * 70)

    print(
        "COT:",
        cot,
    )

    print(
        "Servicio Record ID:",
        service_record_id,
    )

    print(
        "Técnico:",
        technician_name,
    )

    print(
        "Técnico Record ID:",
        technician_record_id,
    )

    print(
        "Ayudantes:",
        helper_names,
    )

    print(
        "Ayudantes Record IDs:",
        helper_record_ids,
    )

    print(
        "Ubicación inicio:",
        location,
    )

    print(
        "Latitud inicio:",
        start_latitude,
    )

    print(
        "Longitud inicio:",
        start_longitude,
    )

    print(
        "Dirección oficial servicio:",
        service_address,
    )

    print(
        "Distancia inicio:",
        (
            f"{distance_km} km"
            if distance_km is not None
            else "No calculada"
        ),
    )

    if distance_km is None:

        print(
            "Motivo distancia:",
            distance_result.get(
                "reason"
            ),
        )

    print(
        "Payload:",
        fields,
    )

    if existing.get(
        "found"
    ):

        print(
            "Activity Record ID existente:",
            existing.get(
                "record_id"
            ),
        )

    print("=" * 70)

    # ========================================================
    # UPDATE
    # ========================================================

    if existing.get(
        "found"
    ):

        activity_record_id = existing.get(
            "record_id"
        )

        if not activity_record_id:

            return {
                "created": False,
                "updated": False,
                "saved": False,
                "reason": "existing_record_missing_id",
            }

        try:

            result = update_record(
                base_id=AIRTABLE_SERVICE_BASE_ID,
                table_id=AIRTABLE_ACTIVITY_TABLE_ID,
                record_id=activity_record_id,
                fields=fields,
            )

        except Exception as error:

            print()
            print("=" * 70)
            print("❌ ERROR ACTUALIZANDO INICIO")
            print("=" * 70)

            print(
                type(error).__name__,
                str(error),
            )

            print("=" * 70)

            return {
                "created": False,
                "updated": False,
                "saved": False,
                "reason": "airtable_update_error",
                "error": str(
                    error
                ),
                "record_id": activity_record_id,
            }

        updated = bool(
            result.get(
                "updated"
            )
        )

        print()
        print("=" * 70)

        if updated:

            print(
                "✅ INICIO ACTUALIZADO CORRECTAMENTE"
            )

        else:

            print(
                "❌ AIRTABLE NO CONFIRMÓ ACTUALIZACIÓN"
            )

            print(
                "Resultado:",
                result,
            )

        print("=" * 70)

        return {
            # Compatibilidad con operaciones/service.py
            "created": updated,

            "updated": updated,

            "new_record": False,

            "saved": updated,

            "reason": (
                None
                if updated
                else "airtable_update_failed"
            ),

            "record_id": (
                activity_record_id
            ),

            "cot": cot,

            "service_record_id": (
                service_record_id
            ),

            "distance_km": (
                distance_km
            ),

            "distance_calculated": (
                distance_result.get(
                    "calculated",
                    False,
                )
            ),

            "distance_reason": (
                distance_result.get(
                    "reason"
                )
            ),

            "fields": result.get(
                "fields",
                {},
            ),
        }

    # ========================================================
    # CREATE
    # ========================================================

    try:

        result = create_record(
            base_id=AIRTABLE_SERVICE_BASE_ID,
            table_id=AIRTABLE_ACTIVITY_TABLE_ID,
            fields=fields,
        )

    except Exception as error:

        print()
        print("=" * 70)
        print("❌ ERROR CREANDO INICIO")
        print("=" * 70)

        print(
            type(error).__name__,
            str(error),
        )

        print("=" * 70)

        return {
            "created": False,

            "updated": False,

            "new_record": False,

            "saved": False,

            "reason": (
                "airtable_create_error"
            ),

            "error": str(
                error
            ),
        }

    created = bool(
        result.get(
            "created"
        )
    )

    print()
    print("=" * 70)

    if created:

        print(
            "✅ INICIO CREADO CORRECTAMENTE"
        )

    else:

        print(
            "❌ AIRTABLE NO CONFIRMÓ CREACIÓN"
        )

        print(
            "Resultado:",
            result,
        )

    print("=" * 70)

    return {
        "created": created,

        "updated": False,

        "new_record": created,

        "saved": created,

        "reason": (
            None
            if created
            else "airtable_create_failed"
        ),

        "record_id": result.get(
            "record_id"
        ),

        "cot": cot,

        "service_record_id": (
            service_record_id
        ),

        "distance_km": (
            distance_km
        ),

        "distance_calculated": (
            distance_result.get(
                "calculated",
                False,
            )
        ),

        "distance_reason": (
            distance_result.get(
                "reason"
            )
        ),

        "fields": result.get(
            "fields",
            {},
        ),
    }


# ============================================================
# GUARDAR INFORME DE LEVANTAMIENTO EN INICIO DE ACTIVIDADES
# ============================================================

def save_field_report_to_activity(
    report_text: str,
    activity_record_id: str = None,
    service_record_id: str = None,
    service_identifier: str = None,
) -> dict:

    report_text = clean_text(report_text)
    activity_record_id = normalize_record_id(activity_record_id)
    service_record_id = normalize_record_id(service_record_id)
    service_identifier = clean_text(service_identifier)

    if not report_text:
        return {"saved": False, "reason": "empty_report"}

    lookup_used = False

    if not activity_record_id:

        lookup_used = True
        lookup = find_activity_start_by_service(
            service_record_id=service_record_id,
            cot=service_identifier,
        )

        if lookup.get("multiple"):
            return {
                "saved": False,
                "reason": "duplicate_activity_records",
                "count": lookup.get("count"),
            }

        if not lookup.get("found"):
            return {
                "saved": False,
                "reason": lookup.get("reason") or "activity_not_found",
            }

        activity_record_id = normalize_record_id(
            lookup.get("record_id")
        )

    if not activity_record_id:
        return {
            "saved": False,
            "reason": "missing_activity_record_id",
        }

    try:
        result = update_record(
            base_id=AIRTABLE_SERVICE_BASE_ID,
            table_id=AIRTABLE_ACTIVITY_TABLE_ID,
            record_id=activity_record_id,
            fields={
                AIRTABLE_ACTIVITY_REPORT_FIELD: report_text,
            },
        )
    except Exception as error:
        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None)

        print(
            "Error guardando levantamiento:",
            "status=", status_code,
            "field=", AIRTABLE_ACTIVITY_REPORT_FIELD,
            "record_id=", activity_record_id,
            "reason=", type(error).__name__,
        )

        return {
            "saved": False,
            "reason": "airtable_update_exception",
            "status_code": status_code,
            "record_id": activity_record_id,
            "field": AIRTABLE_ACTIVITY_REPORT_FIELD,
        }

    saved = bool(result.get("updated"))

    return {
        "saved": saved,
        "reason": None if saved else "airtable_update_failed",
        "record_id": activity_record_id,
        "activity_record_id": activity_record_id,
        "service_record_id": service_record_id,
        "service_identifier": service_identifier,
        "table_id": AIRTABLE_ACTIVITY_TABLE_ID,
        "field": AIRTABLE_ACTIVITY_REPORT_FIELD,
        "lookup_used": lookup_used,
        "save_mode": "replace",
    }


def get_field_report_from_activity(
    service_record_id: str,
    service_identifier: str,
    technician_record_id: str = None,
) -> dict:

    technician_record_id = normalize_record_id(
        technician_record_id
    )

    lookup = find_activity_start_by_service(
        service_record_id=service_record_id,
        cot=service_identifier,
    )

    if lookup.get("multiple"):
        return {
            "found": False,
            "reason": "duplicate_activity_records",
        }

    if not lookup.get("found"):
        return {
            "found": False,
            "reason": lookup.get("reason") or "activity_not_found",
        }

    fields = lookup.get("fields") or {}

    if technician_record_id:
        activity_technician_ids = normalize_record_ids(
            fields.get(AIRTABLE_ACTIVITY_FIELD_TECHNICIAN)
        )

        if technician_record_id not in activity_technician_ids:
            return {
                "found": False,
                "reason": "activity_technician_mismatch",
                "record_id": lookup.get("record_id"),
            }

    report_text = clean_text(
        fields.get(AIRTABLE_ACTIVITY_REPORT_FIELD)
    )

    if not report_text:
        return {
            "found": False,
            "reason": "empty_activity_report",
            "record_id": lookup.get("record_id"),
        }

    return {
        "found": True,
        "reason": None,
        "record_id": lookup.get("record_id"),
        "report_text": report_text,
    }
