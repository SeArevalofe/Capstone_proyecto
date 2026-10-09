import json
import re
import unicodedata

from app.airtable.client import (
    get_records,
    get_record,
)

from app.config import (
    AIRTABLE_EMPLOYEE_BASE_ID,
    AIRTABLE_EMPLOYEE_TABLE_ID,
    AIRTABLE_EMPLOYEE_PHONE_FIELD,
    AIRTABLE_EMPLOYEE_NAME_FIELD,
    AIRTABLE_EMPLOYEE_POSITION_FIELD,
    AIRTABLE_POSITION_BASE_ID,
    AIRTABLE_POSITION_TABLE_ID,
    AIRTABLE_POSITION_NAME_FIELD,
)


FIELD_NAME = AIRTABLE_EMPLOYEE_NAME_FIELD
FIELD_PHONE = AIRTABLE_EMPLOYEE_PHONE_FIELD
FIELD_POSITION = AIRTABLE_EMPLOYEE_POSITION_FIELD

FIELD_EMAIL = "Correo Electronico Trabajador"
FIELD_ACTIVE_CONTRACT = "¿Contrato Vigente?"
FIELD_REGION = "Region"
FIELD_ID_DOCUMENT = "Cedula"
FIELD_GENDER = "Género"
FIELD_BIRTH_DATE = "Fecha de Nacimiento"
FIELD_HIRE_DATE = "Fecha de Ingreso - Contrato Trabajador"
FIELD_ADDRESS = "Dirección"
FIELD_BUSINESS_CENTER = "Centro de Negocios"

# ============================================================
# CACHE DE CARGOS
# ============================================================

_POSITION_CACHE = None

# ============================================================
# CACHE DE TRABAJADORES POR RECORD ID
# ============================================================

_EMPLOYEE_RECORD_CACHE = None

# ============================================================
# NORMALIZAR
# ============================================================

def normalize_phone(
    phone,
) -> str:

    if phone is None:
        return ""

    return "".join(
        char
        for char in str(phone)
        if char.isdigit()
    )


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
# PAGINACIÓN RRHH
# ============================================================

def get_all_employee_records() -> list:

    records = []
    offset = None

    while True:

        params = {}

        if offset:
            params[
                "offset"
            ] = offset

        result = get_records(
            base_id=AIRTABLE_EMPLOYEE_BASE_ID,
            table_id=AIRTABLE_EMPLOYEE_TABLE_ID,
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
# PAGINACIÓN CARGOS
# ============================================================

def get_all_position_records() -> list:

    if not AIRTABLE_POSITION_TABLE_ID:
        return []

    records = []
    offset = None

    while True:

        params = {}

        if offset:
            params["offset"] = offset

        result = get_records(
            base_id=AIRTABLE_POSITION_BASE_ID,
            table_id=AIRTABLE_POSITION_TABLE_ID,
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
# OBTENER NOMBRE DEL CARGO DESDE FIELDS
# ============================================================

def extract_position_name(
    fields: dict,
):

    if not fields:
        return None

    # Campo real actual en Airtable
    position_name = fields.get(
        "RRHH - Cargo"
    )

    # Campo configurado
    if not position_name:

        position_name = fields.get(
            AIRTABLE_POSITION_NAME_FIELD
        )

    # Fallbacks
    if not position_name:

        for candidate in (
            "Cargo",
            "Nombre Cargo",
            "Nombre",
            "Puesto",
        ):

            candidate_value = fields.get(
                candidate
            )

            if candidate_value:

                position_name = candidate_value
                break

    return position_name


# ============================================================
# CARGAR CACHE DE CARGOS
# ============================================================

def get_position_cache() -> dict:

    global _POSITION_CACHE

    # Ya fue cargado:
    # no volver a consultar Airtable.
    if _POSITION_CACHE is not None:

        return _POSITION_CACHE

    print()
    print("=" * 70)
    print("⚡ CARGANDO CACHE DE CARGOS")
    print("=" * 70)

    _POSITION_CACHE = {}

    try:

        records = get_all_position_records()

    except Exception as error:

        print(
            "⚠️ No se pudo cargar "
            "la tabla de cargos:",
            type(error).__name__,
            str(error),
        )

        return _POSITION_CACHE

    for record in records:

        record_id = record.get(
            "id"
        )

        if not record_id:
            continue

        fields = record.get(
            "fields",
            {},
        )

        position_name = extract_position_name(
            fields
        )

        if not position_name:
            continue

        if isinstance(
            position_name,
            list,
        ):

            cleaned = [
                str(item)
                for item in position_name
                if item
            ]

            if len(cleaned) == 1:

                _POSITION_CACHE[
                    record_id
                ] = cleaned[0]

            elif cleaned:

                _POSITION_CACHE[
                    record_id
                ] = cleaned

        else:

            _POSITION_CACHE[
                record_id
            ] = str(
                position_name
            )

    print(
        "✅ Cargos cargados en cache:",
        len(_POSITION_CACHE),
    )

    print("=" * 70)

    return _POSITION_CACHE

# ============================================================
# RESOLVER CARGO VINCULADO
# ============================================================

# ============================================================
# RESOLVER CARGO VINCULADO
# ============================================================

def resolve_position(
    value,
):

    if value is None:
        return None

    # ========================================================
    # DETERMINAR IDS / VALORES
    # ========================================================

    if isinstance(
        value,
        str,
    ):

        # Si ya viene como texto,
        # no necesitamos resolver nada.
        if not value.startswith(
            "rec"
        ):
            return value

        linked_ids = [
            value
        ]

    elif isinstance(
        value,
        list,
    ):

        linked_ids = value

    else:

        return value

    # ========================================================
    # SI NO HAY TABLA DE CARGOS
    # ========================================================

    if not AIRTABLE_POSITION_TABLE_ID:

        return value

    # ========================================================
    # CARGAR CACHE UNA SOLA VEZ
    # ========================================================

    position_cache = get_position_cache()

    positions = []

    # ========================================================
    # RESOLVER DESDE MEMORIA
    # ========================================================

    for record_id in linked_ids:

        if not isinstance(
            record_id,
            str,
        ):
            continue

        # Ya viene como texto
        if not record_id.startswith(
            "rec"
        ):

            positions.append(
                str(
                    record_id
                )
            )

            continue

        # ====================================================
        # BUSCAR PRIMERO EN CACHE
        # ====================================================

        position_name = position_cache.get(
            record_id
        )

        if position_name:

            if isinstance(
                position_name,
                list,
            ):

                positions.extend(
                    str(item)
                    for item in position_name
                    if item
                )

            else:

                positions.append(
                    str(
                        position_name
                    )
                )

            continue

        # ====================================================
        # FALLBACK:
        # Si por alguna razón el cargo no estaba en cache,
        # consultarlo individualmente UNA VEZ.
        # ====================================================

        try:

            result = get_record(
                base_id=AIRTABLE_POSITION_BASE_ID,
                table_id=AIRTABLE_POSITION_TABLE_ID,
                record_id=record_id,
            )

        except Exception as error:

            print(
                "⚠️ No se pudo resolver cargo:",
                record_id,
                type(error).__name__,
                str(error),
            )

            continue

        if not result.get(
            "found"
        ):

            print(
                "⚠️ Cargo no encontrado:",
                record_id,
            )

            continue

        fields = result.get(
            "fields",
            {},
        )

        position_name = extract_position_name(
            fields
        )

        if not position_name:
            continue

        # Guardarlo para que no vuelva
        # a consultar Airtable.
        position_cache[
            record_id
        ] = position_name

        if isinstance(
            position_name,
            list,
        ):

            positions.extend(
                str(item)
                for item in position_name
                if item
            )

        else:

            positions.append(
                str(
                    position_name
                )
            )

    # ========================================================
    # RESULTADO
    # ========================================================

    if not positions:

        print(
            "⚠️ No fue posible resolver "
            "el nombre del cargo:",
            value,
        )

        return value

    # Eliminar duplicados manteniendo orden
    positions = list(
        dict.fromkeys(
            positions
        )
    )

    if len(
        positions
    ) == 1:

        return positions[
            0
        ]

    return positions
# ============================================================
# CONVERTIR RECORD
# ============================================================

def build_employee_result(
    record: dict,
) -> dict:

    fields = record.get(
        "fields",
        {},
    )

    raw_position = fields.get(
        FIELD_POSITION
    )

    position = resolve_position(
        raw_position
    )

    return {
        "found": True,

        "record_id": record.get(
            "id"
        ),

        "nombre": fields.get(
            FIELD_NAME
        ),

        "telefono": fields.get(
            FIELD_PHONE
        ),

        "cargo": position,

        "cargo_raw": raw_position,

        "email": fields.get(
            FIELD_EMAIL
        ),

        "contrato_vigente": fields.get(
            FIELD_ACTIVE_CONTRACT
        ),

        "region": fields.get(
            FIELD_REGION
        ),

        "cedula": fields.get(
            FIELD_ID_DOCUMENT
        ),

        "genero": fields.get(
            FIELD_GENDER
        ),

        "fecha_nacimiento": fields.get(
            FIELD_BIRTH_DATE
        ),

        "fecha_ingreso": fields.get(
            FIELD_HIRE_DATE
        ),

        "direccion": fields.get(
            FIELD_ADDRESS
        ),

        "centro_negocios": fields.get(
            FIELD_BUSINESS_CENTER
        ),
    }


# ============================================================
# BUSCAR POR CELULAR
# ============================================================

def get_employee_by_phone(
    phone: str,
) -> dict:

    wanted_phone = normalize_phone(
        phone
    )

    if not wanted_phone:

        return {
            "found": False,
            "message": (
                "Número de teléfono inválido."
            ),
        }

    print()
    print("=" * 70)
    print("📱 IDENTIFICANDO TRABAJADOR EN RRHH2")
    print("=" * 70)
    print(
        "Teléfono recibido:",
        wanted_phone
    )
    print("=" * 70)

    records = get_all_employee_records()

    for record in records:

        fields = record.get(
            "fields",
            {},
        )

        stored_phone = normalize_phone(
            fields.get(
                FIELD_PHONE
            )
        )

        if not stored_phone:
            continue

        # Coincidencia exacta
        if stored_phone == wanted_phone:

            employee = build_employee_result(
                record
            )

            print(
                "✅ Trabajador:",
                employee.get(
                    "nombre"
                )
            )

            print(
                "Cargo:",
                employee.get(
                    "cargo"
                )
            )

            return employee

        # Compatibilidad:
        # +56912345678
        # 56912345678
        # 912345678
        if (
            stored_phone.endswith(
                wanted_phone
            )
            or wanted_phone.endswith(
                stored_phone
            )
        ):

            employee = build_employee_result(
                record
            )

            print(
                "✅ Trabajador:",
                employee.get(
                    "nombre"
                )
            )

            print(
                "Cargo:",
                employee.get(
                    "cargo"
                )
            )

            return employee

    return {
        "found": False,
        "message": (
            "No se encontró un trabajador "
            "asociado a este número."
        ),
    }


# ============================================================
# BUSCAR POR NOMBRE
# ============================================================

def find_employee_by_name(
    name: str,
) -> dict:

    wanted = normalize_text(
        name
    )

    if not wanted:

        return {
            "found": False,
            "multiple": False,
        }

    wanted_words = set(
        wanted.split()
    )

    matches = []

    for record in get_all_employee_records():

        employee = build_employee_result(
            record
        )

        employee_name = normalize_text(
            employee.get(
                "nombre"
            )
        )

        employee_words = set(
            employee_name.split()
        )

        if wanted_words.issubset(
            employee_words
        ):

            matches.append(
                employee
            )

    if not matches:

        return {
            "found": False,
            "multiple": False,
            "message": (
                f"No encontré un trabajador "
                f"asociado a {name}."
            ),
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

    return matches[
        0
    ]


# ============================================================
# COMPATIBILIDAD
# ============================================================

def get_employee_by_name(
    name: str,
) -> dict:

    return find_employee_by_name(
        name
    )


def search_employees_by_name(
    name: str,
    max_records: int = 10,
) -> dict:

    wanted = normalize_text(
        name
    )

    matches = []

    for record in get_all_employee_records():

        employee = build_employee_result(
            record
        )

        employee_name = normalize_text(
            employee.get(
                "nombre"
            )
        )

        if all(
            word in employee_name
            for word in wanted.split()
        ):

            matches.append(
                employee
            )

    return {
        "found": bool(
            matches
        ),
        "count": len(
            matches
        ),
        "records": matches[
            :max_records
        ],
    }


# ============================================================
# CONTAR
# ============================================================

def count_employees(
    filters: dict = None,
) -> dict:

    filters = filters or {}

    employees = [
        build_employee_result(
            record
        )
        for record in get_all_employee_records()
    ]

    if not filters:

        return {
            "success": True,
            "count": len(
                employees
            ),
            "filters": {},
        }

    filtered = []

    for employee in employees:

        matches = True

        for field, expected in filters.items():

            actual = employee.get(
                field
            )

            if isinstance(
                expected,
                bool,
            ):

                if bool(
                    actual
                ) != expected:

                    matches = False
                    break

                continue

            expected_text = normalize_text(
                expected
            )

            if isinstance(
                actual,
                list,
            ):

                actual_text = " ".join(
                    str(item)
                    for item in actual
                )

            else:

                actual_text = actual

            actual_text = normalize_text(
                actual_text
            )

            if expected_text not in actual_text:

                matches = False
                break

        if matches:
            filtered.append(
                employee
            )

    return {
        "success": True,
        "count": len(
            filtered
        ),
        "filters": filters,
    }


def search_employees(
    filters: dict = None,
    max_records: int = 50,
) -> dict:

    filters = filters or {}

    employees = [
        build_employee_result(
            record
        )
        for record in get_all_employee_records()
    ]

    result = []

    for employee in employees:

        matches = True

        for field, expected in filters.items():

            actual = employee.get(
                field
            )

            expected_text = normalize_text(
                expected
            )

            if isinstance(
                actual,
                list,
            ):

                actual = " ".join(
                    str(item)
                    for item in actual
                )

            actual_text = normalize_text(
                actual
            )

            if expected_text not in actual_text:

                matches = False
                break

        if matches:
            result.append(
                employee
            )

    return {
        "found": bool(
            result
        ),
        "count": len(
            result
        ),
        "records": result[
            :max_records
        ],
    }


def get_employees(
    max_records: int = 50,
) -> dict:

    records = get_all_employee_records()

    employees = [
        build_employee_result(
            record
        )
        for record in records[
            :max_records
        ]
    ]

    return {
        "found": bool(
            employees
        ),
        "count": len(
            records
        ),
        "records": employees,
    }


def get_employee_by_email(
    email: str,
) -> dict:

    wanted = normalize_text(
        email
    )

    for record in get_all_employee_records():

        employee = build_employee_result(
            record
        )

        if normalize_text(
            employee.get(
                "email"
            )
        ) == wanted:

            return employee

    return {
        "found": False,
        "message": "Empleado no encontrado.",
    }

# ============================================================
# CACHE DE TRABAJADORES POR RECORD ID
# ============================================================

def get_employee_record_cache() -> dict:

    global _EMPLOYEE_RECORD_CACHE

    if _EMPLOYEE_RECORD_CACHE is not None:

        return _EMPLOYEE_RECORD_CACHE

    print()
    print("=" * 70)
    print("⚡ CARGANDO CACHE DE TRABAJADORES")
    print("=" * 70)

    _EMPLOYEE_RECORD_CACHE = {}

    try:

        records = get_all_employee_records()

    except Exception as error:

        print(
            "⚠️ No se pudo cargar cache de trabajadores:",
            type(error).__name__,
            str(error),
        )

        return _EMPLOYEE_RECORD_CACHE

    for record in records:

        if not isinstance(
            record,
            dict,
        ):

            continue

        record_id = str(
            record.get(
                "id"
            )
            or ""
        ).strip()

        if not record_id:

            continue

        fields = record.get(
            "fields",
            {},
        )

        name = str(
            fields.get(
                FIELD_NAME
            )
            or ""
        ).strip()

        if not name:

            continue

        _EMPLOYEE_RECORD_CACHE[
            record_id
        ] = name

    print(
        "✅ Trabajadores cargados en cache:",
        len(
            _EMPLOYEE_RECORD_CACHE
        ),
    )

    print("=" * 70)

    return _EMPLOYEE_RECORD_CACHE


# ============================================================
# RESOLVER RECORD ID DE TRABAJADOR
# ============================================================

def resolve_employee_record_id(
    value,
):

    if value is None:

        return None

    value = str(
        value
    ).strip()

    if not value:

        return None

    # ========================================================
    # SI YA VIENE COMO NOMBRE
    # ========================================================

    if not value.startswith(
        "rec"
    ):

        return value

    # ========================================================
    # BUSCAR EN CACHE
    # ========================================================

    employee_cache = get_employee_record_cache()

    name = employee_cache.get(
        value
    )

    if name:

        return name

    # ========================================================
    # FALLBACK:
    # CONSULTA INDIVIDUAL
    # ========================================================

    try:

        result = get_record(
            base_id=AIRTABLE_EMPLOYEE_BASE_ID,
            table_id=AIRTABLE_EMPLOYEE_TABLE_ID,
            record_id=value,
        )

    except Exception as error:

        print()
        print("=" * 70)
        print("⚠️ ERROR RESOLVIENDO TRABAJADOR")
        print("=" * 70)

        print(
            "Record ID:",
            value,
        )

        print(
            type(error).__name__,
            str(error),
        )

        print("=" * 70)

        return value

    if not result.get(
        "found"
    ):

        return value

    fields = result.get(
        "fields",
        {},
    )

    name = str(
        fields.get(
            FIELD_NAME
        )
        or ""
    ).strip()

    if not name:

        return value

    # Guardar para futuras consultas.
    employee_cache[
        value
    ] = name

    return name


# ============================================================
# RESOLVER CAMPO LINKED RECORD DE TRABAJADORES
# ============================================================

def resolve_employee_links(
    value,
) -> list:

    if value is None:

        return []

    # ========================================================
    # CONVERTIR SIEMPRE A LISTA
    # ========================================================

    if isinstance(
        value,
        list,
    ):

        values = value

    else:

        values = [
            value
        ]

    resolved = []

    for item in values:

        if item is None:

            continue

        result = resolve_employee_record_id(
            item
        )

        if not result:

            continue

        result = str(
            result
        ).strip()

        if not result:

            continue

        resolved.append(
            result
        )

    # ========================================================
    # ELIMINAR DUPLICADOS MANTENIENDO ORDEN
    # ========================================================

    return list(
        dict.fromkeys(
            resolved
        )
    )