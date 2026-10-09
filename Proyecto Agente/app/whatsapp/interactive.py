import re
import unicodedata

from app.agents.operaciones.permissions import (
    can_use_operations,
    can_perform_field_survey,
)


# ============================================================
# IDS INTERNOS ESTABLES
# ============================================================

BUTTON_FIELD_SURVEY = "jcf_field_survey"
BUTTON_RESUME_FIELD_SURVEY = "jcf_resume_field_survey"
BUTTON_START_SERVICE = "jcf_start_service"
BUTTON_CLOSE_SERVICE = "jcf_close_service"
BUTTON_BACK_HOME = "jcf_back_home"
BUTTON_NO_OBSERVATIONS = "jcf_no_observations"
BUTTON_REPORT_MODIFY = "jcf_report_modify"
BUTTON_REPORT_GENERATE = "jcf_report_generate"
BUTTON_CLOSE_CONFIRM_SAVE = "close_confirm_save"
BUTTON_CLOSE_ADD_MORE_PHOTOS = "close_add_more_photos"
BUTTON_CLOSURE_SATISFIED_YES = "closure_satisfied_yes"
BUTTON_CLOSURE_SATISFIED_NO = "closure_satisfied_no"
MITIGATION_CAUSE_SPECIALTY = "mitigation_specialty_not_covered"
MITIGATION_CAUSE_MATERIALS = "mitigation_missing_materials_tools"
MITIGATION_CAUSE_PERMISSIONS = "mitigation_missing_permissions"
MITIGATION_CAUSE_BUDGET = "mitigation_budget_approval"


ACTION_START_SERVICE = "start_service"
ACTION_CLOSE_SERVICE = "close_service"
ACTION_FIELD_SURVEY = "field_survey"
ACTION_RESUME_FIELD_SURVEY = "resume_field_survey"
ACTION_BACK_HOME = "maestro_back_home"
ACTION_NO_OBSERVATIONS = "maestro_no_observations"
ACTION_REPORT_MODIFY = "maestro_report_modify"
ACTION_REPORT_GENERATE = "maestro_report_generate"
ACTION_CLOSE_CONFIRM_SAVE = "close_confirm_save"
ACTION_CLOSE_ADD_MORE_PHOTOS = "close_add_more_photos"
ACTION_CLOSURE_SATISFIED_YES = "closure_satisfied_yes"
ACTION_CLOSURE_SATISFIED_NO = "closure_satisfied_no"
ACTION_MITIGATION_CAUSE_SPECIALTY = "mitigation_specialty_not_covered"
ACTION_MITIGATION_CAUSE_MATERIALS = "mitigation_missing_materials_tools"
ACTION_MITIGATION_CAUSE_PERMISSIONS = "mitigation_missing_permissions"
ACTION_MITIGATION_CAUSE_BUDGET = "mitigation_budget_approval"


# ============================================================
# INTENCIONES QUE YA ENTIENDE EL AGENTE CENTRAL
# ============================================================

BUTTON_INTENTS = {
    BUTTON_FIELD_SURVEY: (
        "Quiero realizar un levantamiento"
    ),
    BUTTON_START_SERVICE: (
        "Quiero iniciar un servicio"
    ),
    BUTTON_CLOSE_SERVICE: (
        "Quiero cerrar un servicio"
    ),
}

BUTTON_ACTIONS = {
    BUTTON_FIELD_SURVEY: ACTION_FIELD_SURVEY,
    BUTTON_RESUME_FIELD_SURVEY: ACTION_RESUME_FIELD_SURVEY,
    BUTTON_START_SERVICE: ACTION_START_SERVICE,
    BUTTON_CLOSE_SERVICE: ACTION_CLOSE_SERVICE,
    BUTTON_BACK_HOME: ACTION_BACK_HOME,
    BUTTON_NO_OBSERVATIONS: ACTION_NO_OBSERVATIONS,
    BUTTON_REPORT_MODIFY: ACTION_REPORT_MODIFY,
    BUTTON_REPORT_GENERATE: ACTION_REPORT_GENERATE,
    BUTTON_CLOSE_CONFIRM_SAVE: ACTION_CLOSE_CONFIRM_SAVE,
    BUTTON_CLOSE_ADD_MORE_PHOTOS: ACTION_CLOSE_ADD_MORE_PHOTOS,
    BUTTON_CLOSURE_SATISFIED_YES: ACTION_CLOSURE_SATISFIED_YES,
    BUTTON_CLOSURE_SATISFIED_NO: ACTION_CLOSURE_SATISFIED_NO,
    MITIGATION_CAUSE_SPECIALTY: ACTION_MITIGATION_CAUSE_SPECIALTY,
    MITIGATION_CAUSE_MATERIALS: ACTION_MITIGATION_CAUSE_MATERIALS,
    MITIGATION_CAUSE_PERMISSIONS: ACTION_MITIGATION_CAUSE_PERMISSIONS,
    MITIGATION_CAUSE_BUDGET: ACTION_MITIGATION_CAUSE_BUDGET,
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
        r"[^\w\s]",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ============================================================
# CONSTRUIR MENÚ SEGÚN CARGO
# ============================================================

def build_main_menu(
    employee: dict,
) -> dict:

    buttons = []

    # ========================================================
    # OPERACIONES
    #
    # El levantamiento ya NO aparece como opción independiente.
    #
    # El flujo será:
    #
    # Inicio de servicio
    #       ↓
    # COT PROGRAMADA
    #       ↓
    # Ubicación
    #       ↓
    # Inicio registrado
    #       ↓
    # Si Tipo de Servicio == Cotización
    #       ↓
    # Levantamiento automático
    # ========================================================

    if can_use_operations(
        employee
    ):

        buttons.append(
            {
                "id": BUTTON_START_SERVICE,
                "title": "Inicio de servicio",
            }
        )

        buttons.append(
            {
                "id": BUTTON_CLOSE_SERVICE,
                "title": "Cierre de servicio",
            }
        )

    # IMPORTANTE:
    # Se mantiene el mismo contrato que utilizaba
    # el webhook: un diccionario con "buttons".
    return {
        "buttons": buttons,
        "prompt": "Selecciona una gestión para continuar.",
    }


def _session_is_active(
    session: dict,
) -> bool:

    if not isinstance(
        session,
        dict,
    ):

        return False

    return normalize_text(
        session.get(
            "status"
        )
    ) not in {
        "completed",
        "cancelled",
    }


def should_show_usage_notice(
    text: str,
    operations_session=None,
    maestro_session=None,
) -> bool:

    """Muestra el aviso solo para un saludo sin flujos en curso."""

    greeting = normalize_text(
        text
    ) in {
        "hola",
        "holi",
        "buenas",
        "buenos dias",
        "buenas tardes",
        "buenas noches",
    }

    return bool(
        greeting
        and not _session_is_active(
            operations_session
        )
        and not _session_is_active(
            maestro_session
        )
    )


def build_contextual_actions(
    employee: dict,
    operations_session=None,
    maestro_session=None,
    response_text: str = "",
) -> dict:

    """Devuelve exclusivamente las acciones válidas para el estado actual."""

    normalized_response = normalize_text(
        response_text
    )

    if (
        can_perform_field_survey(employee)
        and "levantamiento pendiente" in normalized_response
        and "para cerrar una cotizacion" in normalized_response
    ):
        return {
            "buttons": [
                {
                    "id": BUTTON_RESUME_FIELD_SURVEY,
                    "title": "Retomar",
                },
                {
                    "id": BUTTON_BACK_HOME,
                    "title": "← Volver al inicio",
                },
            ],
            "request_location": False,
            "prompt": "",
        }

    if _session_is_active(
        operations_session
    ):

        if (
            operations_session.get("action") == "CLOSE_SERVICE"
            and operations_session.get("waiting_for")
            == "closure_satisfaction"
        ):
            return {
                "buttons": [
                    {
                        "id": BUTTON_CLOSURE_SATISFIED_YES,
                        "title": "Sí",
                    },
                    {
                        "id": BUTTON_CLOSURE_SATISFIED_NO,
                        "title": "No",
                    },
                ],
                "request_location": False,
                "prompt": "",
            }

        if (
            operations_session.get("action") == "CLOSE_SERVICE"
            and operations_session.get("waiting_for")
            == "closure_mitigation_cause"
        ):
            return {
                "buttons": [],
                "list": {
                    "button": "Seleccionar causa",
                    "section_title": "Causas de mitigación",
                    "rows": [
                        {
                            "id": MITIGATION_CAUSE_SPECIALTY,
                            "title": "Especialidad no cubierta",
                        },
                        {
                            "id": MITIGATION_CAUSE_MATERIALS,
                            "title": "Falta de Materiales",
                            "description": "y/o Herramientas",
                        },
                        {
                            "id": MITIGATION_CAUSE_PERMISSIONS,
                            "title": "Falta de permisos",
                        },
                        {
                            "id": MITIGATION_CAUSE_BUDGET,
                            "title": "Aprobación presupuesto",
                            "description": "Aprobación de presupuesto",
                        },
                    ],
                },
                "request_location": False,
                "prompt": "",
            }

        if (
            operations_session.get("action") == "CLOSE_SERVICE"
            and operations_session.get("waiting_for")
            == "closure_confirmation"
        ):
            return {
                "buttons": [
                    {
                        "id": BUTTON_CLOSE_CONFIRM_SAVE,
                        "title": "Sí, guardar",
                    },
                    {
                        "id": BUTTON_CLOSE_ADD_MORE_PHOTOS,
                        "title": "Añadir más fotos",
                    },
                ],
                "request_location": False,
                "prompt": "",
            }

        if (
            operations_session.get("action") == "CLOSE_SERVICE"
            and operations_session.get("waiting_for")
            == "closure_observations"
        ):
            return {
                "buttons": [
                    {
                        "id": BUTTON_NO_OBSERVATIONS,
                        "title": "Sin observaciones",
                    },
                    {
                        "id": BUTTON_BACK_HOME,
                        "title": "← Volver al inicio",
                    },
                ],
                "request_location": False,
                "prompt": "",
            }

        return {
            "buttons": [],
            "request_location": (
                operations_session.get(
                    "action"
                ) == "START_SERVICE"
                and operations_session.get(
                    "waiting_for"
                ) == "location"
            ),
            "prompt": "",
        }

    if _session_is_active(
        maestro_session
    ):

        status = normalize_text(
            maestro_session.get(
                "status"
            )
        )

        if status == "paused":

            return build_main_menu(
                employee
            )

        if status == "saving_report":

            return {
                "buttons": [],
                "request_location": False,
                "prompt": "",
            }

        if status in {
            "ready_to_generate",
            "report_generated",
            "awaiting_save_confirmation",
        }:

            return {
                "buttons": [
                    {
                        "id": BUTTON_REPORT_MODIFY,
                        "title": "Modificar informe",
                    },
                    {
                        "id": BUTTON_REPORT_GENERATE,
                        "title": "Generar informe",
                    },
                ],
                "prompt": "Elige si deseas modificar o generar el informe.",
            }

        if maestro_session.get(
            "last_question_field"
        ) == "observaciones":

            return {
                "buttons": [
                    {
                        "id": BUTTON_NO_OBSERVATIONS,
                        "title": "No",
                    },
                    {
                        "id": BUTTON_BACK_HOME,
                        "title": "← Volver al inicio",
                    },
                ],
                "prompt": "Puedes escribir una observación o seleccionar No.",
            }

        return {
            "buttons": [
                {
                    "id": BUTTON_BACK_HOME,
                    "title": "← Volver al inicio",
                },
            ],
            "prompt": "El levantamiento continúa activo.",
        }

    return build_main_menu(
        employee
    )

# ============================================================
# TRADUCIR BUTTON_REPLY.ID A INTENCIÓN EXISTENTE
# ============================================================

def get_button_intent(
    button_id: str,
) -> str:

    value = str(
        button_id
        or ""
    ).strip()

    return BUTTON_INTENTS.get(
        value,
        "",
    )


def get_button_action(
    button_id: str,
) -> str:

    return BUTTON_ACTIONS.get(
        str(
            button_id
            or ""
        ).strip(),
        "",
    )


# ============================================================
# VALIDAR QUE EL BOTÓN CORRESPONDA AL CARGO
# ============================================================

def is_button_allowed(
    button_id: str,
    employee: dict,
) -> bool:

    value = str(
        button_id
        or ""
    ).strip()

    if value in (
        BUTTON_FIELD_SURVEY,
        BUTTON_RESUME_FIELD_SURVEY,
    ):

        return can_perform_field_survey(
            employee
        )

    if value in (
        BUTTON_START_SERVICE,
        BUTTON_CLOSE_SERVICE,
        BUTTON_CLOSE_CONFIRM_SAVE,
        BUTTON_CLOSE_ADD_MORE_PHOTOS,
        BUTTON_CLOSURE_SATISFIED_YES,
        BUTTON_CLOSURE_SATISFIED_NO,
        MITIGATION_CAUSE_SPECIALTY,
        MITIGATION_CAUSE_MATERIALS,
        MITIGATION_CAUSE_PERMISSIONS,
        MITIGATION_CAUSE_BUDGET,
    ):

        return can_use_operations(
            employee
        )

    if value in (
        BUTTON_BACK_HOME,
        BUTTON_NO_OBSERVATIONS,
    ):

        return (
            can_use_operations(
                employee
            )
            or can_perform_field_survey(
                employee
            )
        )

    if value in (
        BUTTON_REPORT_MODIFY,
        BUTTON_REPORT_GENERATE,
    ):

        return can_perform_field_survey(
            employee
        )

    return False


# ============================================================
# CUÁNDO MOSTRAR EL MENÚ PRINCIPAL
#
# Compatibilidad para consumidores antiguos. El webhook actual usa
# build_contextual_actions(), que además considera las sesiones.
# ============================================================

def should_offer_main_menu(
    text: str,
) -> bool:

    value = normalize_text(
        text
    )

    return value in {
        "hola",
        "holi",
        "buenas",
        "buenos dias",
        "buenas tardes",
        "buenas noches",
        "menu",
        "menu principal",
        "inicio",
    }
