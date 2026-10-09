import copy
import time


# ============================================================
# CONFIGURACIÓN
# ============================================================

SESSION_TIMEOUT_SECONDS = 30 * 60


# ============================================================
# SESIONES
# ============================================================

SESSIONS = {}

HISTORY_KEY = "_history"
MAX_HISTORY_STEPS = 20


# ============================================================
# NORMALIZAR TELÉFONO
# ============================================================

def normalize_phone(
    phone,
) -> str:

    return str(
        phone
        or ""
    ).strip()


# ============================================================
# CREAR SESIÓN
# ============================================================

def create_session(
    phone: str,
    action: str,
) -> dict:

    phone = normalize_phone(
        phone
    )

    if not phone:

        raise ValueError(
            "phone es obligatorio."
        )

    action = str(
        action
        or ""
    ).strip().upper()

    if action not in (
        "START_SERVICE",
        "CLOSE_SERVICE",
    ):

        raise ValueError(
            "Acción Operaciones inválida."
        )

    now = time.time()

    session = {
        # ====================================================
        # IDENTIFICACIÓN DE SESIÓN
        # ====================================================

        "phone": phone,
        "action": action,

        # ====================================================
        # SERVICIO
        # ====================================================

        "cot": None,
        "oc": None,
        "service_record_id": None,
        "service_type": None,
        "service_status": None,

        "available_services": [],

        # Dirección oficial del servicio.
        "service_address": None,

        # Descripción oficial del mismo registro de Airtable.
        "service_description": None,

        # ====================================================
        # TÉCNICO
        # ====================================================

        "technician": None,
        "technician_record_id": None,
        "operator_role": None,

        # ====================================================
        # AYUDANTES DISPONIBLES
        # ====================================================

        "available_helpers": [],
        "available_helper_ids": [],

        # ====================================================
        # ELECCIÓN DE AYUDANTES PARA INICIO
        # ====================================================

        "use_helper": None,

        # Valores posibles:
        #
        # None
        # ONE
        # ALL
        #
        "helper_mode": None,

        "selected_helpers": [],
        "selected_helper_ids": [],

        # ====================================================
        # INICIO DE SERVICIO
        # ====================================================

        "start_location": None,
        "start_latitude": None,
        "start_longitude": None,
        "activity_record_id": None,
        "start_activity_created": False,
        "service_activation_pending": False,
        "start_distance_km": None,

        # ====================================================
        # CIERRE DE SERVICIO
        # ====================================================

        # ----------------------------------------------------
        # REGISTRO DE AIRTABLE
        # ----------------------------------------------------

        "closure_record_id": None,
        "service_pause_pending": False,

        # ----------------------------------------------------
        # TÉCNICO DEL CIERRE
        # ----------------------------------------------------

        "closure_technician": None,
        "closure_technician_record_id": None,
        "closure_worker_role": None,

        # ----------------------------------------------------
        # AYUDANTE DEL CIERRE
        # ----------------------------------------------------

        # True:
        # se utilizará ayudante.
        #
        # False:
        # no aplica ayudante.
        #
        # None:
        # todavía no se ha respondido.
        #
        "closure_use_helper": None,

        # Un ayudante.
        "closure_helper": None,
        "closure_helper_record_id": None,

        # Preparado para múltiples ayudantes en el futuro.
        "closure_helpers": [],
        "closure_helper_ids": [],

        # ----------------------------------------------------
        # OBSERVACIONES
        # ----------------------------------------------------

        "closure_observations": None,
        "closure_satisfactory": None,
        "closure_mitigation_cause": None,

        # Evidencias del trabajo realizado. Cada elemento conserva
        # path, filename, mime_type y estado de subida a Airtable.
        "closure_service_photos": [],

        # ----------------------------------------------------
        # CONFIRMACIÓN
        # ----------------------------------------------------

        # El usuario confirmó que los datos mostrados
        # son correctos y pueden guardarse en Airtable.
        "closure_confirmed": False,

        # ----------------------------------------------------
        # UBICACIÓN DE CIERRE
        # ----------------------------------------------------

        "end_location": None,
        "end_latitude": None,
        "end_longitude": None,

        # ====================================================
        # CAMPOS HISTÓRICOS / COMPATIBILIDAD
        # ====================================================

        # Se mantienen porque otras partes del proyecto
        # pueden seguir utilizándolos.
        "observations": None,

        "service_sheet_photo_uploaded": False,

        "service_sheet_photo_count": 0,

        "service_photos_count": 0,

        # ====================================================
        # ESTADO DE CONVERSACIÓN
        # ====================================================

        # Ejemplos:
        #
        # cot
        # helper_confirmation
        # helper_mode
        # helper_selection
        # location
        #
        # CIERRE:
        #
        # cot_close
        # closure_helper_confirmation
        # closure_helper_selection
        # closure_satisfaction
        # closure_mitigation_cause
        # closure_unsatisfactory_observations
        # closure_observations
        # closure_confirmation
        #
        "waiting_for": None,

        # active
        # completed
        # cancelled
        "status": "active",

        "created_at": now,

        "last_activity": now,

        HISTORY_KEY: [],
    }

    SESSIONS[
        phone
    ] = session

    return session


# ============================================================
# OBTENER SESIÓN
# ============================================================

def get_session(
    phone: str,
):

    phone = normalize_phone(
        phone
    )

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

    try:

        last_activity = float(
            last_activity
        )

    except (
        TypeError,
        ValueError,
    ):

        last_activity = 0

    # ========================================================
    # EXPIRACIÓN
    # ========================================================

    if (
        last_activity
        and (
            time.time()
            - last_activity
            > SESSION_TIMEOUT_SECONDS
        )
    ):

        SESSIONS.pop(
            phone,
            None,
        )

        print()
        print("=" * 70)
        print(" SESIÓN OPERACIONES EXPIRADA")
        print("=" * 70)

        print(
            "Teléfono:",
            phone,
        )

        print("=" * 70)

        return None

    return session


# ============================================================
# GUARDAR SESIÓN
# ============================================================

def save_session(
    phone: str,
    session: dict,
) -> dict:

    phone = normalize_phone(
        phone
    )

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


# ============================================================
# ACTUALIZAR SESIÓN
# ============================================================

def update_session(
    phone: str,
    **changes,
):

    session = get_session(
        phone
    )

    if not session:

        return None

    session.update(
        changes
    )

    return save_session(
        phone=phone,
        session=session,
    )


# ============================================================
# MARCAR SESIÓN COMO COMPLETADA
# ============================================================

def complete_session(
    phone: str,
):

    session = get_session(
        phone
    )

    if not session:

        return None

    session[
        "status"
    ] = "completed"

    session[
        "waiting_for"
    ] = None

    return save_session(
        phone=phone,
        session=session,
    )


# ============================================================
# CANCELAR SESIÓN
# ============================================================

def cancel_session(
    phone: str,
):

    session = get_session(
        phone
    )

    if not session:

        return None

    session[
        "status"
    ] = "cancelled"

    session[
        "waiting_for"
    ] = None

    return save_session(
        phone=phone,
        session=session,
    )


# ============================================================
# BORRAR SESIÓN
# ============================================================

def clear_session(
    phone: str,
) -> bool:

    phone = normalize_phone(
        phone
    )

    if not phone:

        return False

    existed = (
        phone in SESSIONS
    )

    SESSIONS.pop(
        phone,
        None,
    )

    return existed


# ============================================================
# EXISTE SESIÓN ACTIVA
# ============================================================

def has_active_session(
    phone: str,
) -> bool:

    session = get_session(
        phone
    )

    if not session:

        return False

    return (
        session.get(
            "status"
        )
        not in (
            "completed",
            "cancelled",
        )
    )


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


def _comparable_snapshot(
    session: dict,
) -> dict:

    snapshot = _history_snapshot(
        session
    )

    snapshot.pop(
        "last_activity",
        None,
    )

    return snapshot


def push_history(
    phone: str,
) -> bool:

    session = get_session(
        phone
    )

    if not session:
        return False

    history = session.setdefault(
        HISTORY_KEY,
        [],
    )

    if not isinstance(
        history,
        list,
    ):
        history = []
        session[HISTORY_KEY] = history

    snapshot = _history_snapshot(
        session
    )

    if history:
        last_snapshot = history[-1]
        if (
            isinstance(last_snapshot, dict)
            and _comparable_snapshot(last_snapshot)
            == _comparable_snapshot(snapshot)
        ):
            return False

    history.append(snapshot)

    if len(history) > MAX_HISTORY_STEPS:
        del history[:len(history) - MAX_HISTORY_STEPS]

    save_session(
        phone=phone,
        session=session,
    )

    return True


def pop_history(
    phone: str,
):

    session = get_session(
        phone
    )

    if not session:
        return None

    history = session.get(
        HISTORY_KEY,
        [],
    )

    if not isinstance(history, list) or not history:
        return None

    current_comparable = _comparable_snapshot(
        session
    )

    restored = None

    while history:
        candidate = history.pop()

        if not isinstance(candidate, dict):
            continue

        if _comparable_snapshot(candidate) == current_comparable:
            continue

        restored = copy.deepcopy(candidate)
        break

    if restored is None:
        session[HISTORY_KEY] = history
        save_session(
            phone=phone,
            session=session,
        )
        return None

    restored[HISTORY_KEY] = history

    return save_session(
        phone=phone,
        session=restored,
    )


def clear_history(
    phone: str,
) -> bool:

    session = get_session(
        phone
    )

    if not session:
        return False

    session[HISTORY_KEY] = []

    save_session(
        phone=phone,
        session=session,
    )

    return True
