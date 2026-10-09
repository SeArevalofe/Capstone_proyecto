import copy
import time

# ============================================================
# CONFIGURACIÓN
# ============================================================

SESSION_TIMEOUT_SECONDS = 60 * 60

SESSIONS = {}

HISTORY_KEY = "_history"
MAX_HISTORY_STEPS = 20

def start_session(
    phone: str,
    employee: dict,
) -> dict:

    now = time.time()

    session = {

        "phone": phone,

        "employee_record_id": (
            employee.get(
                "record_id"
            )
        ),

        "employee_name": (
            employee.get(
                "nombre"
            )
            or "Trabajador"
        ),

        "employee_email": (
            employee.get(
                "email"
            )
        ),

        "employee_position": (
            employee.get(
                "cargo"
            )
        ),

        "status": "active",

        # ====================================================
        # SERVICIO
        # ====================================================

        "quote_number": None,

        "oc": None,

        "quote_record_id": None,

        # Record exacto de Registros - Inicio Actividades.
        "activity_record_id": None,

        "quote_record": None,

        "selected_service_id": None,

        # ====================================================
        # SERVICIOS DISPONIBLES
        # ====================================================

        "available_services": [],

        # ====================================================
        # LEVANTAMIENTO
        # ====================================================

        "data": {

            "cliente": None,
            "recinto": None,
            "sector": None,

            "tipo_trabajo": None,
            "descripcion": None,

            "dimensiones": {},
            "superficie_m2": None,

            "materiales": [],
            "cantidades": [],

            "estado_actual": None,
            "trabajos_requeridos": [],

            "equipamiento_necesario": [],

            "tiempo_estimado": None,

            "jornada": None,

            "personal_requerido": None,

            "empresa_externa_requerida": None,

            "empresa_externa_detalle": None,

            "prioridad": None,

            "observaciones": [],

            "imagenes": [],
        },

        "pending_new_job": None,

        "critical_missing": [],

        "recommended_missing": [],

        "optional_missing": [],

        "ask_for_observations": False,

        "last_intent": None,

        "last_question_field": None,

        "pending_question_fields": [],

        "ready_for_report": False,

        "editing_report": False,

        "status_before_pause": None,

        # ====================================================
        # CONTROL DE INACTIVIDAD
        # ====================================================

        "created_at": now,

        "last_activity": now,

        HISTORY_KEY: [],
    }

    SESSIONS[
        phone
    ] = session

    return session


def get_session(
    phone: str,
):

    phone = str(
        phone
        or ""
    ).strip()

    if not phone:

        return None

    session = SESSIONS.get(
        phone
    )

    if not isinstance(
        session,
        dict,
    ):

        return None

    last_activity = session.get(
        "last_activity"
    )

    # Compatibilidad con una sesión que pudiera existir
    # desde antes de incorporar el timeout.
    if last_activity is None:

        session[
            "last_activity"
        ] = time.time()

        SESSIONS[
            phone
        ] = session

        return session

    try:

        last_activity = float(
            last_activity
        )

    except (
        TypeError,
        ValueError,
    ):

        last_activity = time.time()

        session[
            "last_activity"
        ] = last_activity

        SESSIONS[
            phone
        ] = session

    # ========================================================
    # EXPIRACIÓN
    # ========================================================

    if (
        time.time()
        - last_activity
        > SESSION_TIMEOUT_SECONDS
    ):

        SESSIONS.pop(
            phone,
            None,
        )

        print()
        print("=" * 70)
        print(" SESIÓN MAESTRO EXPIRADA")
        print("=" * 70)

        print(
            "Teléfono:",
            phone,
        )

        print("=" * 70)

        return None

    return session


def save_session(
    phone: str,
    session: dict,
):

    phone = str(
        phone
        or ""
    ).strip()

    if not phone:

        raise ValueError(
            "phone es obligatorio."
        )

    if not isinstance(
        session,
        dict,
    ):

        raise ValueError(
            "session debe ser diccionario."
        )

    session[
        "phone"
    ] = phone

    session[
        "last_activity"
    ] = time.time()

    SESSIONS[
        phone
    ] = session

    return session


def delete_session(
    phone: str,
):

    return SESSIONS.pop(
        phone,
        None,
    )


# ============================================================
# LIMPIAR SESIÓN
# ============================================================

def clear_session(
    phone: str,
) -> None:

    phone = str(
        phone
        or ""
    ).strip()

    if not phone:
        return

    if phone in SESSIONS:

        del SESSIONS[
            phone
        ]


# ============================================================
# HISTORIAL / RETROCESO
# ============================================================

def _history_snapshot(
    session: dict,
) -> dict:

    snapshot = copy.deepcopy(
        session
    )

    snapshot.pop(
        HISTORY_KEY,
        None,
    )

    return snapshot


def push_history(
    phone: str,
) -> bool:

    session = get_session(
        phone
    )

    if not isinstance(session, dict):
        return False

    history = session.setdefault(
        HISTORY_KEY,
        [],
    )

    if not isinstance(history, list):
        history = []
        session[HISTORY_KEY] = history

    snapshot = _history_snapshot(session)

    if history:
        last_snapshot = history[-1]
        if isinstance(last_snapshot, dict) and last_snapshot == snapshot:
            return False

    history.append(snapshot)

    if len(history) > MAX_HISTORY_STEPS:
        del history[:len(history) - MAX_HISTORY_STEPS]

    save_session(phone, session)
    return True


def pop_history(
    phone: str,
):

    session = get_session(phone)

    if not isinstance(session, dict):
        return None

    history = session.get(HISTORY_KEY, [])

    if not isinstance(history, list) or not history:
        return None

    current = _history_snapshot(session)
    restored = None

    while history:
        candidate = history.pop()
        if not isinstance(candidate, dict):
            continue
        if candidate == current:
            continue
        restored = copy.deepcopy(candidate)
        break

    if restored is None:
        session[HISTORY_KEY] = history
        save_session(phone, session)
        return None

    restored[HISTORY_KEY] = history
    save_session(phone, restored)
    return restored


def clear_history(
    phone: str,
) -> bool:

    session = get_session(phone)

    if not isinstance(session, dict):
        return False

    session[HISTORY_KEY] = []
    save_session(phone, session)
    return True
