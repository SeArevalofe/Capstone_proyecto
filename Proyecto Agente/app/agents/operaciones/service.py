import os

from app.agents.operaciones.permissions import (
    can_use_operations,
    can_perform_field_survey,
    is_service_type_allowed,
    is_helper,
    is_supervisor,
    uses_technician_operations_flow,
)

from app.agents.operaciones.session import (
    create_session,
    get_session,
    save_session,
    clear_session,
    push_history,
    pop_history,
)

from app.agents.operaciones.conversation_engine import (
    is_start_service_request,
    is_close_service_request,
    parse_yes_no,
    extract_cot,
    normalize_text,
)

from app.agents.operaciones.closure_sheet_validator import (
    validate_closure_sheet,
)

from app.airtable.service_request_repository import (
    get_operational_service_context,
    get_active_services_for_employee,
    get_programmed_services_for_employee,
    update_service_status_by_record_id,
)

from app.airtable.activity_repository import (
    create_activity_start,
    get_field_report_from_activity,
)

from app.airtable.service_closure_repository import (
    save_service_closure_form,
    sync_activity_report_to_closure,
    upload_service_sheet_photo,
    upload_service_photo,
)

from app.airtable.employee_repository import (
    resolve_employee_links,
)


# ============================================================
# IDENTIDAD DEL AGENTE
# ============================================================

OPERATIONS_AGENT_NAME = (
    "Agente Operacional"
)


def operations_header() -> str:

    return (
        f" *{OPERATIONS_AGENT_NAME}*\n\n"
    )


def requires_completed_field_report(
    employee: dict,
    service_type,
) -> bool:

    return (
        is_supervisor(employee)
        and normalize_text(service_type) == "cotizacion"
    )


def get_closure_field_report_status(
    employee: dict,
    service_record_id: str,
    service_identifier: str,
    service_type,
) -> dict:

    if not requires_completed_field_report(
        employee=employee,
        service_type=service_type,
    ):
        return {
            "required": False,
            "found": True,
            "reason": None,
        }

    try:
        result = get_field_report_from_activity(
            service_record_id=service_record_id,
            service_identifier=service_identifier,
            technician_record_id=employee.get("record_id"),
        )
    except Exception as error:
        return {
            "required": True,
            "found": False,
            "reason": "field_report_lookup_error",
            "error": str(error),
        }

    return {
        "required": True,
        "found": bool(result.get("found")),
        "reason": result.get("reason"),
    }


def build_pending_field_report_message(
    service_identifier: str,
) -> str:

    service_identifier = clean_text(service_identifier)

    return (
        operations_header()
        + "📋 Levantamiento pendiente\n\n"
        + f"El servicio *{service_identifier}* todavía tiene un "
        + "levantamiento técnico pendiente.\n\n"
        + "⚠️ Para cerrar una cotización, primero debes completar "
        + "y guardar su levantamiento.\n\n"
        + "Puedes retomarlo ahora para continuar."
    )


# ============================================================
# HELPERS GENERALES
# ============================================================

def ensure_list(
    value,
) -> list:

    if value is None:
        return []

    if isinstance(
        value,
        list,
    ):
        return value

    return [
        value
    ]


def clean_text(
    value,
) -> str:

    return str(
        value
        or ""
    ).strip()


def closure_worker_label(session: dict) -> str:

    role = normalize_text(
        session.get("closure_worker_role")
    )
    return "Ayudante" if "ayudante" in role else "Técnico"


def worker_matches_employee(
    worker: dict,
    employee_name: str,
    employee_record_id: str,
) -> bool:

    worker_record_id = clean_text(worker.get("record_id"))
    if employee_record_id and worker_record_id:
        return worker_record_id == employee_record_id

    return (
        normalize_text(worker.get("name"))
        == normalize_text(employee_name)
    )


def get_closure_service_photos(
    session: dict,
) -> list:

    if not isinstance(
        session,
        dict,
    ):

        return []

    photos = []

    for raw_photo in ensure_list(
        session.get(
            "closure_service_photos"
        )
    ):

        if not isinstance(
            raw_photo,
            dict,
        ):

            continue

        path = clean_text(
            raw_photo.get(
                "path"
            )
        )

        if not path:

            continue

        photos.append(
            {
                "path": path,
                "filename": (
                    clean_text(
                        raw_photo.get(
                            "filename"
                        )
                    )
                    or os.path.basename(
                        path
                    )
                ),
                "mime_type": (
                    clean_text(
                        raw_photo.get(
                            "mime_type"
                        )
                    )
                    or "image/jpeg"
                ),
                "uploaded": bool(
                    raw_photo.get(
                        "uploaded"
                    )
                ),
                "attachment_id": clean_text(
                    raw_photo.get(
                        "attachment_id"
                    )
                ) or None,
            }
        )

    if photos:

        return photos

    legacy_path = clean_text(
        session.get(
            "closure_service_photo_path"
        )
    )

    if not legacy_path:

        return []

    return [
        {
            "path": legacy_path,
            "filename": (
                clean_text(
                    session.get(
                        "closure_service_photo_filename"
                    )
                )
                or os.path.basename(
                    legacy_path
                )
            ),
            "mime_type": (
                clean_text(
                    session.get(
                        "closure_service_photo_mime_type"
                    )
                )
                or "image/jpeg"
            ),
            "uploaded": bool(
                session.get(
                    "closure_service_photo_uploaded"
                )
            ),
            "attachment_id": None,
        }
    ]


def append_closure_service_photo(
    session: dict,
    file_path: str,
    filename: str,
    mime_type: str,
) -> int:

    photos = get_closure_service_photos(
        session
    )

    photos.append(
        {
            "path": file_path,
            "filename": filename,
            "mime_type": mime_type,
            "uploaded": False,
            "attachment_id": None,
        }
    )

    session[
        "closure_service_photos"
    ] = photos

    session[
        "service_photos_count"
    ] = len(
        photos
    )

    # Compatibilidad con el flujo anterior de una sola fotografía.
    # Estos campos siempre apuntan a la primera evidencia recibida.
    first_photo = photos[0]
    session[
        "closure_service_photo_path"
    ] = first_photo[
        "path"
    ]
    session[
        "closure_service_photo_filename"
    ] = first_photo[
        "filename"
    ]
    session[
        "closure_service_photo_mime_type"
    ] = first_photo[
        "mime_type"
    ]
    session[
        "closure_service_photo_uploaded"
    ] = False

    return len(
        photos
    )


def clean_coordinate(
    value,
):

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
# NORMALIZAR RESULTADO DE VALIDACIÓN DE HOJA
#
# Permite trabajar tanto si closure_sheet_validator devuelve:
#
# {
#     "stamp_detected": true
# }
#
# como si devuelve adicionalmente:
#
# {
#     "stamp_status": "detected"
# }
# ============================================================

def normalize_closure_sheet_validation(
    validation,
) -> dict:

    if not isinstance(
        validation,
        dict,
    ):

        validation = {}

    is_service_closure_sheet = bool(
        validation.get(
            "is_service_closure_sheet",
            False,
        )
    )

    raw_stamp_detected = validation.get(
        "stamp_detected"
    )

    raw_stamp_status = clean_text(
        validation.get(
            "stamp_status"
        )
    ).lower()

    # ========================================================
    # NORMALIZAR STATUS DEL TIMBRE
    # ========================================================

    if raw_stamp_status in (
        "detected",
        "present",
        "yes",
        "true",
        "found",
    ):

        stamp_status = "detected"
        stamp_detected = True

    elif raw_stamp_status in (
        "not_detected",
        "not detected",
        "absent",
        "missing",
        "no",
        "false",
    ):

        stamp_status = "not_detected"
        stamp_detected = False

    elif raw_stamp_status in (
        "uncertain",
        "unknown",
        "doubtful",
        "inconclusive",
    ):

        stamp_status = "uncertain"
        stamp_detected = False

    else:

        # ----------------------------------------------------
        # COMPATIBILIDAD CON EL JSON SIMPLE
        #
        # {
        #   "stamp_detected": true
        # }
        # ----------------------------------------------------

        if raw_stamp_detected is True:

            stamp_status = "detected"
            stamp_detected = True

        elif raw_stamp_detected is False:

            stamp_status = "not_detected"
            stamp_detected = False

        else:

            stamp_status = "uncertain"
            stamp_detected = False

    signature_detected = bool(
        validation.get(
            "signature_detected",
            False,
        )
    )

    confidence = clean_text(
        validation.get(
            "confidence"
        )
    ).lower()

    reason = clean_text(
        validation.get(
            "reason"
        )
    )

    # ========================================================
    # REGLA OPERACIONAL
    #
    # Para aceptar la hoja:
    #
    # 1. Debe reconocerse como Hoja de Cierre.
    # 2. Debe detectarse timbre.
    #
    # La firma NO bloquea el proceso por ahora.
    # ========================================================

    valid = (
        is_service_closure_sheet
        and stamp_detected
    )

    return {
        "valid": valid,
        "is_service_closure_sheet":
            is_service_closure_sheet,
        "stamp_detected":
            stamp_detected,
        "stamp_status":
            stamp_status,
        "signature_detected":
            signature_detected,
        "confidence":
            confidence,
        "reason":
            reason,
        "raw":
            validation,
    }


# ============================================================
# CONSTRUIR PARES TRABAJADOR / RECORD ID
# ============================================================

def build_worker_pairs(
    raw_values: list,
    resolved_names: list,
) -> list:

    raw_values = ensure_list(
        raw_values
    )

    resolved_names = ensure_list(
        resolved_names
    )

    result = []
    seen_names = set()

    for index, resolved_name in enumerate(
        resolved_names
    ):

        name = clean_text(
            resolved_name
        )

        if not name:
            continue

        normalized_name = (
            name.casefold()
        )

        if normalized_name in seen_names:
            continue

        record_id = None

        if index < len(
            raw_values
        ):

            raw_value = raw_values[
                index
            ]

            if isinstance(
                raw_value,
                dict,
            ):

                record_id = clean_text(
                    raw_value.get(
                        "id"
                    )
                    or raw_value.get(
                        "record_id"
                    )
                )

            else:

                raw_text = clean_text(
                    raw_value
                )

                if raw_text.startswith(
                    "rec"
                ):

                    record_id = raw_text

        seen_names.add(
            normalized_name
        )

        result.append(
            {
                "name": name,
                "record_id": record_id,
            }
        )

    return result


# ============================================================
# CONSTRUIR RESUMEN DEL CIERRE
# ============================================================

def closure_observations_prompt() -> str:

    return (
        "📝 Observaciones del cierre\n\n"
        "¿Quieres agregar alguna observación antes de continuar?\n\n"
        "Si tienes alguna, escríbela o envíala por audio."
    )


MITIGATION_CAUSES = (
    "Especialidad no cubierta",
    "Falta de Materiales y/o Herramientas",
    "Falta de permisos",
    "Aprobación de presupuesto",
)


def is_oc_service(session: dict) -> bool:

    return normalize_text(
        session.get("service_type")
    ) == "oc"


def build_closure_satisfaction_message() -> str:

    return (
        operations_header()
        + "¿El servicio fue culminado de forma satisfactoria?"
    )


def build_mitigation_cause_message() -> str:

    return (
        operations_header()
        + "⚠️ Servicio no culminado\n\n"
        + "Selecciona la Causa de mitigación:\n\n"
        + "1. Especialidad no cubierta\n"
        + "2. Falta de Materiales y/o Herramientas\n"
        + "3. Falta de permisos\n"
        + "4. Aprobación de presupuesto"
    )


def build_unsatisfactory_observations_message(
    mitigation: bool = False,
) -> str:

    if mitigation:
        title = "⚠️ Servicio en mitigación"
        prompt = (
            "Indica por qué el servicio quedó en mitigación.\n\n"
            "✍️ Puedes escribirme directamente en el chat\n"
            "🎙️ o enviarme un mensaje de audio.\n\n"
            "Cuando me envíes la información, continuaré con el registro "
            "del servicio."
        )
    else:
        title = "⚠️ Servicio no culminado"
        prompt = (
            "Cuéntame por qué el servicio no pudo finalizarse "
            "satisfactoriamente.\n\n"
            "✍️ Puedes escribir la observación directamente en el chat\n"
            "🎙️ o enviar un mensaje de audio.\n\n"
            "Cuando me envíes la información, continuaré con el registro "
            "del servicio."
        )

    return operations_header() + title + "\n\n" + prompt


def resolve_mitigation_cause(text: str):

    normalized = normalize_text(text)
    aliases = {
        "1": MITIGATION_CAUSES[0],
        normalize_text(MITIGATION_CAUSES[0]): MITIGATION_CAUSES[0],
        "2": MITIGATION_CAUSES[1],
        normalize_text(MITIGATION_CAUSES[1]): MITIGATION_CAUSES[1],
        "3": MITIGATION_CAUSES[2],
        normalize_text(MITIGATION_CAUSES[2]): MITIGATION_CAUSES[2],
        "4": MITIGATION_CAUSES[3],
        normalize_text(MITIGATION_CAUSES[3]): MITIGATION_CAUSES[3],
    }
    return aliases.get(normalized)


def build_closure_observations_message(
    prefix: str = "",
) -> str:

    prefix = clean_text(
        prefix
    )

    response = operations_header()

    if prefix:
        response += prefix + "\n\n"

    return response + closure_observations_prompt()


def build_closure_sheet_request_message(
    prefix: str = "",
    service_identifier: str = "",
) -> str:

    prefix = clean_text(
        prefix
    )
    service_identifier = clean_text(
        service_identifier
    )

    response = operations_header()

    if prefix:
        response += prefix + "\n\n"

    response += "📄 Hoja de Cierre de Servicio\n\n"

    if service_identifier:
        response += (
            "Estás trabajando con el servicio:\n"
            f"*{service_identifier}*\n\n"
            "⚠️ Antes de enviar la fotografía, verifica que la hoja "
            "corresponda a este servicio.\n\n"
        )

    return response + (
        "Envíame una foto de la hoja completa.\n\n"
        "Antes de enviarla, verifica que:\n\n"
        "✅ Se vea completa\n"
        "✅ El texto sea legible\n"
        "✅ Aparezca el timbre del cliente\n\n"
        "📸 Envíala por WhatsApp para continuar."
    )


def build_validated_closure_sheet_message(
    stamp_detected: bool,
    signature_detected: bool,
) -> str:

    stamp_status = (
        "✅ Detectado"
        if stamp_detected
        else "⚠️ No confirmado"
    )
    signature_status = (
        "✅ Detectada"
        if signature_detected
        else "⚠️ No confirmada"
    )

    return (
        operations_header()
        + "✅ Hoja de Cierre validada\n\n"
        + f"• Timbre del cliente: {stamp_status}\n"
        + f"• Firma: {signature_status}\n\n"
        + "📸 Evidencia del trabajo realizado\n\n"
        + "Ahora envíame una foto clara del trabajo terminado.\n\n"
        + "Verifica que:\n"
        + "✅ Se vea el trabajo realizado\n"
        + "✅ La imagen esté clara\n"
        + "✅ Se vea el área intervenida\n\n"
        + "Cuando la envíes, continuaremos con el cierre del servicio."
    )

def build_closure_confirmation_message(
    session: dict,
) -> str:

    unsatisfactory = session.get("closure_satisfactory") is False
    sheet_required = not (
        unsatisfactory
        and is_oc_service(session)
    )

    technician = clean_text(
        session.get(
            "closure_technician"
        )
    )
    worker_label = closure_worker_label(session)

    observations = clean_text(
        session.get(
            "closure_observations"
        )
    )

    closure_helpers = ensure_list(
        session.get(
            "closure_helpers"
        )
    )

    stamp_detected = bool(
        session.get(
            "closure_sheet_stamp_detected"
        )
    )

    signature_detected = bool(
        session.get(
            "closure_sheet_signature_detected"
        )
    )

    evidence_count = len(
        get_closure_service_photos(
            session
        )
    )

    stamp_status = (
        "✅ Detectado"
        if stamp_detected
        else "⚠️ No confirmado"
    )

    signature_status = (
        "✅ Detectada"
        if signature_detected
        else "⚠️ No confirmada"
    )

    response = (
        operations_header()
        + "✅ Revisión del cierre\n\n"
        + f"Servicio: *{session.get('cot')}*\n"
        + f"{worker_label}: {technician}\n"
    )

    if closure_helpers:

        if len(
            closure_helpers
        ) == 1:

            response += (
                f"Ayudante: {closure_helpers[0]}\n"
            )

        else:

            response += (
                "Ayudantes:\n"
                + "\n".join(
                    f"• {name}"
                    for name in closure_helpers
                )
                + "\n"
            )

    else:

        response += (
            "Ayudante: No aplica\n"
        )

    response += (
        "\nObservaciones:\n"
        + f"{observations or 'Sin observaciones'}\n\n"
    )

    if session.get("closure_mitigation_cause"):
        response += (
            "Causa de mitigación: "
            + clean_text(session.get("closure_mitigation_cause"))
            + "\n\n"
        )

    if sheet_required:
        response += (
            "📄 Hoja de cierre: ✅ Validada\n"
            + f"• Timbre del cliente: {stamp_status}\n"
            + f"• Firma: {signature_status}\n\n"
        )

    response += (
        "📸 Evidencia del servicio: ✅ Recibida\n"
        + f"Evidencias registradas: *{evidence_count}*\n\n"
        + "¿Está todo listo para guardar el cierre?"
    )

    return response


def build_additional_photo_request_message() -> str:

    return (
        operations_header()
        + "📸 Añadir evidencia\n\n"
        + "Envíame otra foto del trabajo realizado.\n\n"
        + "Puedes agregar las fotografías que necesites "
        + "antes de guardar el cierre."
    )


def build_additional_photo_added_message(
    session: dict,
) -> str:

    evidence_count = len(
        get_closure_service_photos(
            session
        )
    )

    return (
        operations_header()
        + "✅ Foto añadida correctamente\n\n"
        + f"Evidencias registradas: *{evidence_count}*\n\n"
        + "¿Quieres guardar el cierre o añadir otra fotografía?"
    )


def request_additional_closure_photo(
    phone: str,
    employee: dict,
) -> str:

    if not can_use_operations(
        employee
    ):

        return (
            operations_header()
            + "Tu cargo no tiene permisos para cerrar servicios."
        )

    session = get_session(
        phone
    )

    if (
        not isinstance(
            session,
            dict,
        )
        or session.get(
            "action"
        ) != "CLOSE_SERVICE"
        or clean_text(
            session.get(
                "waiting_for"
            )
        ) != "closure_confirmation"
    ):

        return (
            operations_header()
            + "La revisión del cierre ya no está disponible. "
            + "Continúa con el paso actual."
        )

    session[
        "waiting_for"
    ] = "additional_work_photo"

    save_session(
        phone=phone,
        session=session,
    )

    return build_additional_photo_request_message()


# ============================================================
# RETROCEDER UN PASO
# ============================================================

def is_back_request(
    text: str,
) -> bool:

    value = clean_text(text).casefold()
    value = value.translate(
        str.maketrans(
            "áéíóúüñ",
            "aeiouun",
        )
    )

    return value in {
        "volver",
        "atras",
        "volver atras",
        "retroceder",
        "retroceso",
    }


def cleanup_discarded_closure_files(
    current_session: dict,
    restored_session: dict,
):

    if not isinstance(current_session, dict):
        return

    if not isinstance(restored_session, dict):
        return

    for path_key, uploaded_key in (
        (
            "closure_service_sheet_path",
            "closure_service_sheet_uploaded",
        ),
        (
            "closure_service_photo_path",
            "closure_service_photo_uploaded",
        ),
    ):

        current_path = clean_text(
            current_session.get(path_key)
        )

        restored_path = clean_text(
            restored_session.get(path_key)
        )

        already_uploaded = bool(
            current_session.get(uploaded_key)
        )

        if (
            current_path
            and current_path != restored_path
            and not already_uploaded
            and os.path.isfile(current_path)
        ):
            try:
                os.remove(current_path)
            except OSError:
                pass


def build_operations_step_message(
    session: dict,
) -> str:

    if not isinstance(session, dict):
        return operations_header() + "No hay un paso anterior disponible."

    action = clean_text(session.get("action"))
    waiting_for = clean_text(session.get("waiting_for"))

    if waiting_for == "cot":

        services = ensure_list(
            session.get(
                "available_services"
            )
        )

        lines = [
            f"{index}. *{service.get('identifier')}*"
            for index, service in enumerate(
                services,
                start=1,
            )
            if isinstance(
                service,
                dict,
            )
            and clean_text(
                service.get(
                    "identifier"
                )
            )
        ]

        return (
            operations_header()
            + "Volviste al paso anterior.\n\n"
            + "Selecciona el servicio que deseas iniciar:\n\n"
            + "\n".join(
                lines
            )
        )

    if waiting_for == "cot_close":

        services = ensure_list(
            session.get(
                "available_services"
            )
        )

        lines = [
            f"{index}. *{service.get('identifier')}*"
            for index, service in enumerate(
                services,
                start=1,
            )
            if isinstance(
                service,
                dict,
            )
            and clean_text(
                service.get(
                    "identifier"
                )
            )
        ]

        return (
            operations_header()
            + "Volviste al paso anterior.\n\n"
            + "Selecciona el servicio que deseas cerrar:\n\n"
            + "\n".join(
                lines
            )
        )

    if waiting_for == "helper_confirmation":
        helpers = ensure_list(session.get("available_helpers"))
        helper_name = clean_text(helpers[0]) if helpers else ""

        response = operations_header() + "Volviste al paso anterior.\n\n"

        if helper_name:
            response += (
                "Ayudante asignado:\n"
                + f"• *{helper_name}*\n\n"
            )

        response += (
            "¿Iniciarás este servicio con este ayudante?\n\n"
            "1. Sí\n"
            "2. No"
        )
        return response

    if waiting_for == "helper_mode":
        helpers = ensure_list(session.get("available_helpers"))
        lines = [
            f"{index}. {helper}"
            for index, helper in enumerate(helpers, start=1)
        ]
        return (
            operations_header()
            + "Volviste al paso anterior.\n\n"
            + "Ayudantes asignados a esta COT:\n\n"
            + "\n".join(lines)
            + "\n\n¿Trabajarás con:\n\n"
            + "1. Todos\n"
            + "2. Solo uno"
        )

    if waiting_for == "helper_selection":
        helpers = ensure_list(session.get("available_helpers"))
        lines = [
            f"{index}. {helper}"
            for index, helper in enumerate(helpers, start=1)
        ]
        return (
            operations_header()
            + "Volviste al paso anterior.\n\n"
            + "¿Cuál de los ayudantes trabajará contigo?\n\n"
            + "\n".join(lines)
        )

    if waiting_for == "location":
        return build_location_request_message(
            session=session,
            helper_text="Volviste al paso anterior.",
        )

    if waiting_for == "closure_observations":
        return build_closure_observations_message(
            prefix=(
                "Volviste al paso anterior.\n\n"
                f"Servicio: *{session.get('cot')}*"
            ),
        )

    if waiting_for == "closure_satisfaction":
        return build_closure_satisfaction_message()

    if waiting_for == "closure_mitigation_cause":
        return build_mitigation_cause_message()

    if waiting_for == "closure_unsatisfactory_observations":
        return build_unsatisfactory_observations_message(
            mitigation=not is_oc_service(session),
        )

    if waiting_for == "closure_service_sheet_photo":
        return build_closure_sheet_request_message(
            prefix="Volviste al paso anterior.",
            service_identifier=session.get("cot"),
        )

    if waiting_for == "closure_service_photo":
        return (
            operations_header()
            + "Volviste al paso anterior.\n\n"
            + "📷 Envíame una fotografía del *servicio realizado*.\n\n"
            + "La fotografía debe mostrar el trabajo terminado."
        )

    if waiting_for == "additional_work_photo":
        return build_additional_photo_request_message()

    if waiting_for == "closure_confirmation":
        return build_closure_confirmation_message(session)

    if action == "START_SERVICE":
        return (
            operations_header()
            + "Ya estás en el primer paso del inicio.\n\n"
            + "Escribe *Hola* si quieres volver al menú principal."
        )

    if action == "CLOSE_SERVICE":
        return (
            operations_header()
            + "Ya estás en el primer paso del cierre.\n\n"
            + "Escribe *Hola* si quieres volver al menú principal."
        )

    return operations_header() + "No hay un paso anterior disponible."


def handle_operations_back(
    phone: str,
    session: dict,
) -> str:

    if not isinstance(session, dict):
        return (
            operations_header()
            + "No hay un proceso activo al cual retroceder.\n\n"
            + "Escribe *Hola* para volver al menú principal."
        )

    if clean_text(session.get("closure_record_id")):
        return (
            operations_header()
            + "Este cierre ya tiene un registro creado en Airtable.\n\n"
            + "Por seguridad no puedo retroceder a un paso anterior "
            + "desde este punto. Continúa el proceso actual."
        )

    current_session = dict(session)
    restored_session = pop_history(phone)

    if not restored_session:
        return (
            operations_header()
            + "Ya estás en el primer paso de este proceso.\n\n"
            + "Escribe *Hola* si quieres volver al menú principal."
        )

    cleanup_discarded_closure_files(
        current_session=current_session,
        restored_session=restored_session,
    )

    return build_operations_step_message(restored_session)


# ============================================================
# PROCESAR MENSAJE DE OPERACIONES
# ============================================================

def process_operations_message(
    phone: str,
    text: str,
    employee: dict,
) -> str:

    text = clean_text(
        text
    )

    employee = (
        employee
        if isinstance(
            employee,
            dict,
        )
        else {}
    )

    # ========================================================
    # VALIDAR PERMISOS
    # ========================================================

    if not can_use_operations(
        employee
    ):

        return (
            operations_header()
            + "Tu cargo no tiene permisos para "
            + "iniciar o cerrar servicios."
        )

    # ========================================================
    # SESIÓN ACTUAL
    # ========================================================

    session = get_session(
        phone
    )

    # ========================================================
    # VOLVER / ATRÁS / RETROCEDER
    # ========================================================

    if is_back_request(
        text
    ):

        return handle_operations_back(
            phone=phone,
            session=session,
        )

    # ========================================================
    # INICIAR SERVICIO
    # ========================================================

    if is_start_service_request(
        text
    ):

        services, message = build_service_list(
            employee=employee,
            action="START_SERVICE",
        )

        if not services:

            return message

        clear_session(
            phone
        )

        session = create_session(
            phone=phone,
            action="START_SERVICE",
        )

        session[
            "available_services"
        ] = services

        session[
            "waiting_for"
        ] = "cot"

        save_session(
            phone=phone,
            session=session,
        )

        selection = resolve_service_selection(
            text=text,
            session=session,
        )

        if selection:

            return select_service(
                phone=phone,
                cot=selection.get(
                    "identifier"
                ),
                employee=employee,
                service_record_id=selection.get(
                    "record_id"
                ),
            )

        return message

    # ========================================================
    # CERRAR SERVICIO
    #
    # FLUJO:
    #
    # COT
    # 
    # Técnico automático
    # 
    # Ayudante automático
    # 
    # Observaciones
    # 
    # Hoja de Cierre
    # 
    # IA valida:
    #   - que sea Hoja de Cierre
    #   - que tenga timbre
    # 
    # Foto Servicio Realizado
    # 
    # Confirmación
    # 
    # Crear registro Airtable
    # 
    # Subir ambas fotografías
    # ========================================================

    if is_close_service_request(
        text
    ):

        services, message = build_service_list(
            employee=employee,
            action="CLOSE_SERVICE",
        )

        if not services:

            return message

        clear_session(
            phone
        )

        session = create_session(
            phone=phone,
            action="CLOSE_SERVICE",
        )

        session[
            "available_services"
        ] = services

        session[
            "waiting_for"
        ] = "cot_close"

        save_session(
            phone=phone,
            session=session,
        )

        selection = resolve_service_selection(
            text=text,
            session=session,
        )

        if selection:

            return select_service_for_closure(
                phone=phone,
                cot=selection.get(
                    "identifier"
                ),
                employee=employee,
                service_record_id=selection.get(
                    "record_id"
                ),
            )

        return message

    # ========================================================
    # NO HAY SESIÓN
    # ========================================================

    if not session:

        return (
            operations_header()
            + "Indícame si deseas iniciar "
            + "o cerrar un servicio."
        )

    waiting_for = clean_text(
        session.get(
            "waiting_for"
        )
    )

    # El Inicio de Actividad ya existe y solo falta activar la Solicitud.
    # Un mensaje de reintento continúa desde ese punto sin volver a pedir
    # ubicación ni volver a crear el Inicio.
    if waiting_for == "service_activation":
        return process_operations_location(
            phone=phone,
            employee=employee,
            location_text=session.get(
                "start_location"
            ),
            latitude=session.get(
                "start_latitude"
            ),
            longitude=session.get(
                "start_longitude"
            ),
        )

    # ========================================================
    # ESPERANDO COT PARA INICIAR
    # ========================================================

    if waiting_for == "cot":

        selection = resolve_service_selection(
            text=text,
            session=session,
        )

        if not selection:

            return (
                operations_header()
                + "No pude identificar la COT.\n\n"
                + "Responde con el número de una opción "
                + "o escribe una COT, por ejemplo: *COT37470*."
            )

        return select_service(
            phone=phone,
            cot=selection.get(
                "identifier"
            ),
            employee=employee,
            service_record_id=selection.get(
                "record_id"
            ),
        )

    # ========================================================
    # ESPERANDO COT PARA CERRAR
    # ========================================================

    if waiting_for == "cot_close":

        selection = resolve_service_selection(
            text=text,
            session=session,
        )

        if not selection:

            return (
                operations_header()
                + "No pude identificar la COT.\n\n"
                + "Responde con el número de una opción "
                + "o escribe el ID completo del servicio."
            )

        return select_service_for_closure(
            phone=phone,
            cot=selection.get(
                "identifier"
            ),
            employee=employee,
            service_record_id=selection.get(
                "record_id"
            ),
        )

    # ========================================================
    # INICIO:
    # CONFIRMAR AYUDANTE
    # ========================================================

    if waiting_for == "helper_confirmation":

        answer = parse_yes_no(
            text
        )

        if answer is None:

            helpers = ensure_list(
                session.get(
                    "available_helpers"
                )
            )

            helper_name = (
                clean_text(
                    helpers[0]
                )
                if helpers
                else ""
            )

            message = (
                operations_header()
            )

            if helper_name:

                message += (
                    "Ayudante asignado:\n"
                    f"• *{helper_name}*\n\n"
                )

            message += (
                "¿Iniciarás este servicio con "
                "este ayudante?\n\n"
                "1. Sí\n"
                "2. No"
            )

            return message

        push_history(
            phone
        )

        session = get_session(
            phone
        )

        if answer is False:

            session[
                "use_helper"
            ] = False

            session[
                "helper_mode"
            ] = None

            session[
                "selected_helpers"
            ] = []

            session[
                "selected_helper_ids"
            ] = []

            session[
                "waiting_for"
            ] = "location"

            save_session(
                phone=phone,
                session=session,
            )

            return build_location_request_message(
                session=session,
                helper_text=(
                    "Servicio sin ayudante."
                ),
            )

        helpers = ensure_list(
            session.get(
                "available_helpers"
            )
        )

        helper_ids = ensure_list(
            session.get(
                "available_helper_ids"
            )
        )

        if not helpers:

            return (
                operations_header()
                + "No pude recuperar el ayudante "
                + "asignado a esta COT.\n\n"
                + "Vuelve a seleccionar el servicio."
            )

        selected_helper = clean_text(
            helpers[
                0
            ]
        )

        selected_helper_id = (
            helper_ids[
                0
            ]
            if helper_ids
            else None
        )

        session[
            "use_helper"
        ] = True

        session[
            "helper_mode"
        ] = "ONE"

        session[
            "selected_helpers"
        ] = [
            selected_helper
        ]

        session[
            "selected_helper_ids"
        ] = (
            [
                selected_helper_id
            ]
            if selected_helper_id
            else []
        )

        session[
            "waiting_for"
        ] = "location"

        save_session(
            phone=phone,
            session=session,
        )

        return build_location_request_message(
            session=session,
            helper_text=(
                f"Ayudante seleccionado: "
                f"*{selected_helper}*"
            ),
        )

    # ========================================================
    # INICIO:
    # TODOS O SOLO UNO
    # ========================================================

    if waiting_for == "helper_mode":

        value = clean_text(
            text
        )

        helpers = ensure_list(
            session.get(
                "available_helpers"
            )
        )

        helper_ids = ensure_list(
            session.get(
                "available_helper_ids"
            )
        )

        if not helpers:

            return (
                operations_header()
                + "No pude recuperar los ayudantes "
                + "asignados a esta COT.\n\n"
                + "Vuelve a seleccionar el servicio."
            )

        if len(
            helpers
        ) == 1:

            session[
                "waiting_for"
            ] = "helper_confirmation"

            save_session(
                phone=phone,
                session=session,
            )

            return (
                operations_header()
                + "Ayudante asignado:\n"
                + f"• *{helpers[0]}*\n\n"
                + "¿Iniciarás este servicio con "
                + "este ayudante?\n\n"
                + "1. Sí\n"
                + "2. No"
            )

        if value in (
            "1",
            "2",
        ):

            push_history(
                phone
            )

            session = get_session(
                phone
            )

        if value == "1":

            session[
                "use_helper"
            ] = True

            session[
                "helper_mode"
            ] = "ALL"

            session[
                "selected_helpers"
            ] = list(
                helpers
            )

            session[
                "selected_helper_ids"
            ] = list(
                helper_ids
            )

            session[
                "waiting_for"
            ] = "location"

            save_session(
                phone=phone,
                session=session,
            )

            names = "\n".join(
                f"• {name}"
                for name in helpers
            )

            return build_location_request_message(
                session=session,
                helper_text=(
                    "Ayudantes seleccionados:\n"
                    f"{names}"
                ),
            )

        if value == "2":

            session[
                "helper_mode"
            ] = "ONE"

            session[
                "waiting_for"
            ] = "helper_selection"

            save_session(
                phone=phone,
                session=session,
            )

            lines = []

            for index, helper in enumerate(
                helpers,
                start=1,
            ):

                lines.append(
                    f"{index}. {helper}"
                )

            return (
                operations_header()
                + "¿Cuál de los ayudantes trabajará "
                + "contigo?\n\n"
                + "\n".join(
                    lines
                )
            )

        return (
            operations_header()
            + "Selecciona una opción válida:\n\n"
            + "1. Todos\n"
            + "2. Solo uno"
        )

    # ========================================================
    # INICIO:
    # SELECCIONAR UN AYUDANTE
    # ========================================================

    if waiting_for == "helper_selection":

        helpers = ensure_list(
            session.get(
                "available_helpers"
            )
        )

        helper_ids = ensure_list(
            session.get(
                "available_helper_ids"
            )
        )

        value = clean_text(
            text
        )

        try:

            selected_index = (
                int(
                    value
                )
                - 1
            )

        except ValueError:

            selected_index = -1

        if not (
            0
            <= selected_index
            < len(
                helpers
            )
        ):

            lines = []

            for index, helper in enumerate(
                helpers,
                start=1,
            ):

                lines.append(
                    f"{index}. {helper}"
                )

            return (
                operations_header()
                + "Selecciona un ayudante válido:\n\n"
                + "\n".join(
                    lines
                )
            )

        push_history(
            phone
        )

        session = get_session(
            phone
        )

        selected_name = clean_text(
            helpers[
                selected_index
            ]
        )

        selected_id = (
            helper_ids[
                selected_index
            ]
            if selected_index
            < len(
                helper_ids
            )
            else None
        )

        session[
            "use_helper"
        ] = True

        session[
            "helper_mode"
        ] = "ONE"

        session[
            "selected_helpers"
        ] = [
            selected_name
        ]

        session[
            "selected_helper_ids"
        ] = (
            [
                selected_id
            ]
            if selected_id
            else []
        )

        session[
            "waiting_for"
        ] = "location"

        save_session(
            phone=phone,
            session=session,
        )

        return build_location_request_message(
            session=session,
            helper_text=(
                f"Ayudante seleccionado: "
                f"*{selected_name}*"
            ),
        )

    # ========================================================
    # CIERRE TÉCNICO: RESULTADO SATISFACTORIO
    # ========================================================

    if waiting_for == "closure_satisfaction":

        answer = parse_yes_no(text)
        if answer is None:
            return build_closure_satisfaction_message()

        session["closure_satisfactory"] = answer
        session["closure_mitigation_cause"] = None

        if answer:
            session["waiting_for"] = "closure_observations"
            save_session(phone=phone, session=session)
            return build_closure_observations_message()

        if is_oc_service(session):
            session["waiting_for"] = (
                "closure_unsatisfactory_observations"
            )
            save_session(phone=phone, session=session)
            return build_unsatisfactory_observations_message(
                mitigation=False,
            )

        session["waiting_for"] = "closure_mitigation_cause"
        save_session(phone=phone, session=session)
        return build_mitigation_cause_message()

    # ========================================================
    # CIERRE TÉCNICO: CAUSA DE MITIGACIÓN
    # ========================================================

    if waiting_for == "closure_mitigation_cause":

        cause = resolve_mitigation_cause(text)
        if not cause:
            return build_mitigation_cause_message()

        session["closure_mitigation_cause"] = cause
        session["waiting_for"] = "closure_unsatisfactory_observations"
        save_session(phone=phone, session=session)
        return build_unsatisfactory_observations_message(
            mitigation=True,
        )

    # ========================================================
    # CIERRE TÉCNICO NO SATISFACTORIO: EXPLICACIÓN
    # ========================================================

    if waiting_for == "closure_unsatisfactory_observations":

        observations = clean_text(text)
        if not observations:
            return build_unsatisfactory_observations_message(
                mitigation=not is_oc_service(session),
            )

        session["closure_observations"] = observations
        session["observations"] = observations
        session["closure_service_photos"] = []
        session["service_photos_count"] = 0
        session["closure_service_photo_uploaded"] = False
        session["closure_service_sheet_path"] = None
        session["closure_service_sheet_uploaded"] = False
        session["closure_sheet_is_valid"] = False
        session["closure_sheet_is_service_closure_sheet"] = False
        session["closure_sheet_stamp_detected"] = False

        if is_oc_service(session):
            session["waiting_for"] = "closure_service_photo"
            save_session(phone=phone, session=session)
            return (
                operations_header()
                + "Observación registrada.\n\n"
                + "📸 Evidencia del trabajo realizado\n\n"
                + "Envíame una foto clara del trabajo realizado."
            )

        session["waiting_for"] = "closure_service_sheet_photo"
        save_session(phone=phone, session=session)
        return build_closure_sheet_request_message(
            prefix="Observación de mitigación registrada.",
            service_identifier=session.get("cot"),
        )

    # ========================================================
    # CIERRE:
    # OBSERVACIONES
    # ========================================================

    if waiting_for == "closure_observations":

        observations = clean_text(
            text
        )

        if not observations:

            return build_closure_observations_message()

        push_history(
            phone
        )

        session = get_session(
            phone
        )

        session[
            "closure_observations"
        ] = observations

        session[
            "observations"
        ] = observations

        # ====================================================
        # REINICIAR HOJA DE CIERRE
        # ====================================================

        session[
            "closure_service_sheet_path"
        ] = None

        session[
            "closure_service_sheet_filename"
        ] = None

        session[
            "closure_service_sheet_mime_type"
        ] = None

        session[
            "closure_service_sheet_uploaded"
        ] = False

        # ====================================================
        # REINICIAR VALIDACIÓN IA
        # ====================================================

        session[
            "closure_sheet_validation"
        ] = None

        session[
            "closure_sheet_is_valid"
        ] = False

        session[
            "closure_sheet_is_service_closure_sheet"
        ] = False

        session[
            "closure_sheet_stamp_detected"
        ] = False

        session[
            "closure_sheet_stamp_status"
        ] = None

        session[
            "closure_sheet_signature_detected"
        ] = False

        session[
            "closure_sheet_validation_confidence"
        ] = None

        session[
            "closure_sheet_validation_reason"
        ] = None

        # ====================================================
        # REINICIAR FOTO SERVICIO
        # ====================================================

        session[
            "closure_service_photo_path"
        ] = None

        session[
            "closure_service_photo_filename"
        ] = None

        session[
            "closure_service_photo_mime_type"
        ] = None

        session[
            "closure_service_photo_uploaded"
        ] = False

        session[
            "closure_service_photos"
        ] = []

        session[
            "service_photos_count"
        ] = 0

        session[
            "waiting_for"
        ] = "closure_service_sheet_photo"

        save_session(
            phone=phone,
            session=session,
        )

        return build_closure_sheet_request_message(
            prefix="Observaciones registradas.",
            service_identifier=session.get("cot"),
        )

    # ========================================================
    # CIERRE:
    # ESPERANDO FOTO HOJA
    #
    # Si llega texto en lugar de imagen.
    # ========================================================

    if waiting_for == "closure_service_sheet_photo":

        return build_closure_sheet_request_message(
            service_identifier=session.get("cot"),
        )

    # ========================================================
    # CIERRE:
    # ESPERANDO FOTO SERVICIO
    # ========================================================

    if waiting_for == "closure_service_photo":

        return (
            operations_header()
            + "Estoy esperando una fotografía "
            + "del *servicio realizado*.\n\n"
            + "Envíala como imagen desde WhatsApp."
        )

    if waiting_for == "additional_work_photo":

        return build_additional_photo_request_message()

    # ========================================================
    # CIERRE:
    # CONFIRMACIÓN FINAL
    # ========================================================

    if waiting_for == "closure_confirmation":

        answer = parse_yes_no(
            text
        )

        if answer is None:

            return build_closure_confirmation_message(
                session
            )

        # ====================================================
        # CANCELAR
        # ====================================================

        if answer is False:

            existing_closure_id = clean_text(
                session.get(
                    "closure_record_id"
                )
            )

            if existing_closure_id:

                return (
                    operations_header()
                    + "El registro del cierre ya fue "
                    + "creado en Airtable, por lo que "
                    + "no puedo cancelarlo desde este paso.\n\n"
                    + "Continúa con el proceso para "
                    + "completar las fotografías."
                )

            clear_session(
                phone
            )

            return (
                operations_header()
                + "El cierre fue cancelado.\n\n"
                + "No se creó ningún registro "
                + "en Airtable."
            )

        # ====================================================
        # DATOS DEL CIERRE
        # ====================================================

        service_record_id = clean_text(
            session.get(
                "service_record_id"
            )
        )

        technician_record_id = clean_text(
            session.get(
                "closure_technician_record_id"
            )
        )

        helper_record_ids = ensure_list(
            session.get(
                "closure_helper_ids"
            )
        )

        closure_helpers = ensure_list(
            session.get(
                "closure_helpers"
            )
        )

        service_sheet_path = clean_text(
            session.get(
                "closure_service_sheet_path"
            )
        )

        unsatisfactory = (
            session.get("closure_satisfactory") is False
        )
        sheet_required = not (
            unsatisfactory
            and is_oc_service(session)
        )
        closure_sheet_validation_required = not unsatisfactory

        service_photos = get_closure_service_photos(
            session
        )

        session[
            "closure_service_photos"
        ] = service_photos

        session[
            "service_photos_count"
        ] = len(
            service_photos
        )

        # ====================================================
        # VALIDAR SERVICIO
        # ====================================================

        if not service_record_id:

            return (
                operations_header()
                + "No pude identificar el registro "
                + "de la Solicitud de Servicio "
                + "en Airtable.\n\n"
                + "No se creó el cierre."
            )

        # ====================================================
        # VALIDAR TÉCNICO
        # ====================================================

        if not technician_record_id:

            return (
                operations_header()
                + "No pude identificar correctamente "
                + "al técnico que realiza el cierre.\n\n"
                + "No se creó el registro."
            )

        # ====================================================
        # VALIDAR AYUDANTES
        # ====================================================

        if (
            closure_helpers
            and not helper_record_ids
        ):

            return (
                operations_header()
                + "Detecté ayudante en esta COT, "
                + "pero no pude obtener correctamente "
                + "su registro de Airtable.\n\n"
                + "No se creó el cierre."
            )

        # ====================================================
        # VALIDAR FOTO HOJA
        # ====================================================

        if (
            sheet_required
            and (
            not service_sheet_path
            or not os.path.isfile(
                service_sheet_path
            )
            )
        ):

            session[
                "waiting_for"
            ] = "closure_service_sheet_photo"

            save_session(
                phone=phone,
                session=session,
            )

            return (
                operations_header()
                + "No encontré la fotografía "
                + "de la Hoja de Cierre de Servicio.\n\n"
                + " Envíamela nuevamente."
            )

        # ====================================================
        # VALIDACIÓN DE SEGURIDAD:
        # HOJA + TIMBRE
        #
        # Aunque la imagen ya fue revisada al recibirla,
        # volvemos a comprobar el estado antes de crear
        # el cierre en Airtable.
        # ====================================================

        sheet_is_valid = bool(
            session.get(
                "closure_sheet_is_valid"
            )
        )

        is_service_closure_sheet = bool(
            session.get(
                "closure_sheet_is_service_closure_sheet"
            )
        )

        stamp_detected = bool(
            session.get(
                "closure_sheet_stamp_detected"
            )
        )

        stamp_status = clean_text(
            session.get(
                "closure_sheet_stamp_status"
            )
        ).lower()

        if (
            closure_sheet_validation_required
            and sheet_required
            and (
            not sheet_is_valid
            or not is_service_closure_sheet
            or not stamp_detected
            or stamp_status != "detected"
            )
        ):

            session[
                "waiting_for"
            ] = "closure_service_sheet_photo"

            save_session(
                phone=phone,
                session=session,
            )

            return (
                operations_header()
                + " La Hoja de Cierre todavía "
                + "no tiene un timbre validado.\n\n"
                + " Envíame nuevamente una fotografía "
                + "de la hoja completa con el timbre "
                + "del cliente claramente visible."
            )

        # ====================================================
        # VALIDAR FOTO SERVICIO
        # ====================================================

        missing_service_photos = [
            photo
            for photo in service_photos
            if (
                not photo.get(
                    "uploaded"
                )
                and not os.path.isfile(
                    photo.get(
                        "path",
                        "",
                    )
                )
            )
        ]

        if (
            not service_photos
            or missing_service_photos
        ):

            session[
                "waiting_for"
            ] = "closure_service_photo"

            save_session(
                phone=phone,
                session=session,
            )

            return (
                operations_header()
                + "No encontré la fotografía "
                + "del servicio realizado.\n\n"
                + " Envíamela nuevamente."
            )

        # ====================================================
        # CREAR CIERRE SOLO SI TODAVÍA NO EXISTE
        # ====================================================

        closure_record_id = clean_text(
            session.get(
                "closure_record_id"
            )
        )

        if not closure_record_id:

            result = save_service_closure_form(
                service_record_id=(
                    service_record_id
                ),

                quote_number=session.get(
                    "cot"
                ),

                oc=session.get(
                    "oc"
                ),

                technician_record_id=(
                    technician_record_id
                ),

                helper_record_ids=(
                    helper_record_ids
                ),

                observations=session.get(
                    "closure_observations"
                ),

                mitigation_cause=session.get(
                    "closure_mitigation_cause"
                ),

                append_observations=uses_technician_operations_flow(
                    employee
                ),
            )

            if not result.get(
                "saved"
            ):

                print()
                print("=" * 70)
                print(" NO SE PUDO CREAR EL CIERRE")
                print("=" * 70)

                print(
                    "Resultado:",
                    result,
                )

                print("=" * 70)

                return (
                    operations_header()
                    + "No pude crear el cierre "
                    + "del servicio en Airtable.\n\n"
                    + "La sesión permanece activa "
                    + "para volver a intentarlo.\n\n"
                    + "Motivo técnico: "
                    + f"{result.get('reason')}"
                )

            closure_record_id = clean_text(
                result.get(
                    "closure_record_id"
                )
            )

            if not closure_record_id:

                return (
                    operations_header()
                    + "Airtable creó el registro, "
                    + "pero no pude obtener su Record ID.\n\n"
                    + "No puedo continuar con las fotografías."
                )

            session[
                "closure_record_id"
            ] = closure_record_id

            session[
                "closure_confirmed"
            ] = True

            save_session(
                phone=phone,
                session=session,
            )

        # El cierre ya existe (recién creado o recuperado en sesión).
        # Si el levantamiento principal está disponible, se copia al campo
        # interno sin alterar la respuesta ni detener el cierre.
        try:
            sync_result = sync_activity_report_to_closure(
                closure_record_id=closure_record_id,
                service_record_id=service_record_id,
                service_identifier=session.get("cot"),
            )

            if not sync_result.get("synced"):
                print(
                    "Sincronización interna de levantamiento pendiente:",
                    sync_result.get("reason"),
                )
        except Exception as error:
            print(
                "Error sincronizando levantamiento durante cierre:",
                type(error).__name__,
            )

        # ====================================================
        # SUBIR FOTO HOJA DE CIERRE
        # ====================================================

        if (
            sheet_required
            and not session.get(
            "closure_service_sheet_uploaded"
            )
        ):

            sheet_result = upload_service_sheet_photo(
                closure_record_id=(
                    closure_record_id
                ),

                file_path=(
                    service_sheet_path
                ),

                filename=(
                    clean_text(
                        session.get(
                            "closure_service_sheet_filename"
                        )
                    )
                    or None
                ),

                mime_type=(
                    clean_text(
                        session.get(
                            "closure_service_sheet_mime_type"
                        )
                    )
                    or "image/jpeg"
                ),
            )

            if not sheet_result.get(
                "uploaded"
            ):

                print()
                print("=" * 70)
                print(
                    " ERROR SUBIENDO HOJA DE CIERRE"
                )
                print("=" * 70)

                print(
                    sheet_result
                )

                print("=" * 70)

                return (
                    operations_header()
                    + "El cierre fue creado, pero "
                    + "no pude subir la fotografía "
                    + "de la Hoja de Cierre.\n\n"
                    + "La sesión permanece activa "
                    + "para volver a intentarlo.\n\n"
                    + "Motivo técnico: "
                    + f"{sheet_result.get('reason')}"
                )

            session[
                "closure_service_sheet_uploaded"
            ] = True

            save_session(
                phone=phone,
                session=session,
            )

        # ====================================================
        # SUBIR FOTO DEL SERVICIO
        # ====================================================

        for photo_index, service_photo in enumerate(
            service_photos
        ):

            if service_photo.get(
                "uploaded"
            ):

                continue

            photo_result = upload_service_photo(
                closure_record_id=closure_record_id,
                file_path=service_photo.get(
                    "path"
                ),
                filename=(
                    service_photo.get(
                        "filename"
                    )
                    or None
                ),
                mime_type=(
                    service_photo.get(
                        "mime_type"
                    )
                    or "image/jpeg"
                ),
            )

            if not photo_result.get(
                "uploaded"
            ):

                print()
                print("=" * 70)
                print(
                    " ERROR SUBIENDO FOTO DEL SERVICIO"
                )
                print("=" * 70)

                print(
                    photo_result
                )

                print("=" * 70)

                return (
                    operations_header()
                    + "El cierre fue creado y la "
                    + "Hoja de Cierre fue guardada, "
                    + "pero no pude subir la fotografía "
                    + "del servicio realizado.\n\n"
                    + "La sesión permanece activa "
                    + "para volver a intentarlo.\n\n"
                    + "Motivo técnico: "
                    + f"{photo_result.get('reason')}"
                )

            service_photos[
                photo_index
            ][
                "uploaded"
            ] = True

            service_photos[
                photo_index
            ][
                "attachment_id"
            ] = clean_text(
                photo_result.get(
                    "attachment_id"
                )
            ) or None

            session[
                "closure_service_photos"
            ] = service_photos

            session[
                "closure_service_photo_uploaded"
            ] = all(
                photo.get(
                    "uploaded"
                )
                for photo in service_photos
            )

            save_session(
                phone=phone,
                session=session,
            )

        # ====================================================
        # PAUSAR SERVICIO DESPUÉS DEL CIERRE COMPLETO
        #
        # El cierre y todas sus evidencias ya fueron confirmados
        # por Airtable. Si este paso falla, conservamos la sesión
        # y closure_record_id para reintentar sin crear otro cierre.
        # ====================================================

        if unsatisfactory:
            session["service_pause_pending"] = False
            session["service_status"] = "ACTIVO"
            cot = clean_text(session.get("cot"))
            clear_session(phone)
            return (
                operations_header()
                + "✅ Intento de cierre registrado correctamente\n\n"
                + f"Servicio: *{cot}*\n"
                + "Estado del servicio: *ACTIVO*"
            )

        status_result = update_service_status_by_record_id(
            service_record_id=service_record_id,
            status="PAUSADO",
        )

        if not status_result.get("updated"):

            session["service_pause_pending"] = True
            session["waiting_for"] = "closure_confirmation"

            save_session(
                phone=phone,
                session=session,
            )

            print()
            print("=" * 70)
            print(" CIERRE GUARDADO, PAUSA PENDIENTE")
            print("=" * 70)
            print("COT:", session.get("cot"))
            print("Cierre Record ID:", closure_record_id)
            print("Servicio Record ID:", service_record_id)
            print("Resultado estado:", status_result)
            print("=" * 70)

            return (
                operations_header()
                + "El cierre fue guardado, pero no pude "
                + "actualizar el estado operacional del servicio.\n\n"
                + "La sesión permanece activa para reintentar "
                + "sin crear otro cierre."
            )

        session["service_pause_pending"] = False
        session["service_status"] = "PAUSADO"

        save_session(
            phone=phone,
            session=session,
        )

        # ====================================================
        # DATOS RESPUESTA FINAL
        # ====================================================

        cot = clean_text(
            session.get(
                "cot"
            )
        )

        technician = clean_text(
            session.get(
                "closure_technician"
            )
        )
        worker_label = closure_worker_label(session)

        observations = clean_text(
            session.get(
                "closure_observations"
            )
        )

        signature_detected = bool(
            session.get(
                "closure_sheet_signature_detected"
            )
        )

        print()
        print("=" * 70)
        print(" CIERRE OPERACIONAL FINALIZADO")
        print("=" * 70)

        print(
            "COT:",
            cot,
        )

        print(
            "Nuevo Record ID cierre:",
            closure_record_id,
        )

        print(
            f"{worker_label}:",
            technician,
        )

        print(
            "Ayudantes:",
            closure_helpers
            or "NO APLICA",
        )

        print(
            "Observaciones:",
            observations,
        )

        print(
            "Hoja de cierre:",
            "SUBIDA",
        )

        print(
            "Timbre:",
            "VALIDADO",
        )

        print(
            "Firma:",
            (
                "DETECTADA"
                if signature_detected
                else "NO CONFIRMADA"
            ),
        )

        print(
            "Foto servicio:",
            "SUBIDA",
        )

        print("=" * 70)

        # ====================================================
        # FINALIZAR SESIÓN
        # ====================================================

        clear_session(
            phone
        )

        response = (
            operations_header()
            + " *Cierre registrado correctamente*\n\n"
            + f"Servicio: *{cot}*\n"
            + f"{worker_label}: {technician}\n"
        )

        if closure_helpers:

            if len(
                closure_helpers
            ) == 1:

                response += (
                    f"Ayudante: {closure_helpers[0]}\n"
                )

            else:

                response += (
                    "Ayudantes:\n"
                    + "\n".join(
                        f"• {name}"
                        for name in closure_helpers
                    )
                    + "\n"
                )

        else:

            response += (
                "Ayudante: No aplica\n"
            )

        response += (
            f"Observaciones: {observations}\n"
            + " Hoja de cierre: \n"
            + " Timbre:  Validado\n"
            + " Foto del servicio: "
        )

        return response

    # ========================================================
    # INICIO:
    # ESPERANDO UBICACIÓN
    # ========================================================

    if waiting_for == "location":

        service_address = clean_text(
            session.get(
                "service_address"
            )
        )

        response = (
            operations_header()
            + "Estoy esperando una ubicación "
            + "de WhatsApp.\n\n"
        )

        if service_address:

            response += (
                "Dirección del servicio:\n"
                f" {service_address}\n\n"
            )

        response += (
            "Comparte tu ubicación actual "
            "desde el menú de adjuntos."
        )

        return response

    # ========================================================
    # ESTADO DESCONOCIDO
    # ========================================================

    return (
        operations_header()
        + "No pude determinar el siguiente paso "
        + "del proceso."
    )


# ============================================================
# PROCESAR IMAGEN DE OPERACIONES
#
# EXCLUSIVAMENTE PARA CIERRE.
#
# El webhook debe descargar la imagen primero y entregar
# aquí la ruta local.
# ============================================================

def process_operations_image(
    phone: str,
    employee: dict,
    file_path: str,
    filename: str = None,
    mime_type: str = "image/jpeg",
) -> str:

    employee = (
        employee
        if isinstance(
            employee,
            dict,
        )
        else {}
    )

    # ========================================================
    # VALIDAR PERMISOS
    # ========================================================

    if not can_use_operations(
        employee
    ):

        return (
            operations_header()
            + "Tu cargo no tiene permisos para "
            + "iniciar o cerrar servicios."
        )

    session = get_session(
        phone
    )

    if not session:

        return (
            operations_header()
            + "No hay ningún proceso de operaciones "
            + "esperando una fotografía."
        )

    if session.get(
        "action"
    ) != "CLOSE_SERVICE":

        return (
            operations_header()
            + "El proceso actual no corresponde "
            + "al cierre de un servicio."
        )

    waiting_for = clean_text(
        session.get(
            "waiting_for"
        )
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
    # VALIDAR ARCHIVO
    # ========================================================

    if not file_path:

        return (
            operations_header()
            + "No pude recuperar la fotografía "
            + "recibida.\n\n"
            + "Intenta enviarla nuevamente."
        )

    if not os.path.isfile(
        file_path
    ):

        print()
        print("=" * 70)
        print(" IMAGEN DE CIERRE NO ENCONTRADA")
        print("=" * 70)

        print(
            "Ruta:",
            file_path,
        )

        print("=" * 70)

        return (
            operations_header()
            + "No pude guardar correctamente "
            + "la fotografía recibida.\n\n"
            + "Intenta enviarla nuevamente."
        )

    # ========================================================
    # FOTO 1:
    # HOJA DE CIERRE
    #
    # ANTES DE ACEPTAR:
    #
    # 1. IA debe reconocer Hoja de Cierre.
    # 2. IA debe detectar timbre del cliente.
    #
    # Si no cumple:
    # NO se avanza.
    # ========================================================

    if waiting_for == "closure_service_sheet_photo":

        if session.get("closure_satisfactory") is False:

            push_history(
                phone
            )

            session = get_session(
                phone
            )

            session[
                "closure_service_sheet_path"
            ] = file_path

            session[
                "closure_service_sheet_filename"
            ] = filename

            session[
                "closure_service_sheet_mime_type"
            ] = mime_type

            session[
                "closure_service_sheet_uploaded"
            ] = False

            session[
                "closure_sheet_validation"
            ] = None

            session[
                "closure_sheet_is_valid"
            ] = False

            session[
                "closure_sheet_is_service_closure_sheet"
            ] = False

            session[
                "closure_sheet_stamp_detected"
            ] = False

            session[
                "closure_sheet_stamp_status"
            ] = None

            session[
                "closure_sheet_signature_detected"
            ] = False

            session[
                "waiting_for"
            ] = "closure_service_photo"

            save_session(
                phone=phone,
                session=session,
            )

            print()
            print("=" * 70)
            print(" HOJA DE SERVICIO RECIBIDA")
            print("=" * 70)

            print(
                "COT:",
                session.get(
                    "cot"
                ),
            )

            print(
                "Archivo:",
                file_path,
            )

            print("=" * 70)

            return (
                operations_header()
                + "✅ Hoja de Servicio recibida correctamente.\n\n"
                + "📸 Ahora envíame una fotografía del trabajo realizado.\n\n"
                + "La imagen debe mostrar claramente el estado actual "
                + "del servicio."
            )

        print()
        print("=" * 70)
        print(" VALIDANDO HOJA DE CIERRE CON IA")
        print("=" * 70)

        print(
            "COT:",
            session.get(
                "cot"
            ),
        )

        print(
            "Archivo:",
            file_path,
        )

        print(
            "Mime type:",
            mime_type,
        )

        print("=" * 70)

        # ====================================================
        # LLAMAR VALIDACIÓN IA
        # ====================================================

        try:

            validation_raw = validate_closure_sheet(
                file_path=file_path,
                mime_type=mime_type,
            )

        except Exception as error:

            print()
            print("=" * 70)
            print(" ERROR VALIDANDO HOJA CON IA")
            print("=" * 70)

            print(
                type(error).__name__,
                str(error),
            )

            print("=" * 70)

            validation_raw = {
                "is_service_closure_sheet": False,
                "stamp_detected": False,
                "signature_detected": False,
                "confidence": "low",
                "reason": (
                    "No fue posible analizar "
                    "la imagen correctamente."
                ),
                "error": str(
                    error
                ),
            }

        # ====================================================
        # NORMALIZAR RESULTADO
        # ====================================================

        validation = (
            normalize_closure_sheet_validation(
                validation_raw
            )
        )

        sheet_valid = bool(
            validation.get(
                "valid"
            )
        )

        is_service_closure_sheet = bool(
            validation.get(
                "is_service_closure_sheet"
            )
        )

        stamp_detected = bool(
            validation.get(
                "stamp_detected"
            )
        )

        stamp_status = clean_text(
            validation.get(
                "stamp_status"
            )
        )

        signature_detected = bool(
            validation.get(
                "signature_detected"
            )
        )

        confidence = clean_text(
            validation.get(
                "confidence"
            )
        )

        reason = clean_text(
            validation.get(
                "reason"
            )
        )

        # ====================================================
        # GUARDAR RESULTADO EN SESIÓN
        # ====================================================

        session[
            "closure_sheet_validation"
        ] = validation

        session[
            "closure_sheet_is_valid"
        ] = sheet_valid

        session[
            "closure_sheet_is_service_closure_sheet"
        ] = is_service_closure_sheet

        session[
            "closure_sheet_stamp_detected"
        ] = stamp_detected

        session[
            "closure_sheet_stamp_status"
        ] = stamp_status

        session[
            "closure_sheet_signature_detected"
        ] = signature_detected

        session[
            "closure_sheet_validation_confidence"
        ] = confidence

        session[
            "closure_sheet_validation_reason"
        ] = reason

        save_session(
            phone=phone,
            session=session,
        )

        # ====================================================
        # DEBUG IA
        # ====================================================

        print()
        print("=" * 70)
        print(" RESULTADO VALIDACIÓN HOJA")
        print("=" * 70)

        print(
            "Es Hoja de Cierre:",
            is_service_closure_sheet,
        )

        print(
            "Estado timbre:",
            stamp_status,
        )

        print(
            "Timbre detectado:",
            stamp_detected,
        )

        print(
            "Firma detectada:",
            signature_detected,
        )

        print(
            "Confianza:",
            confidence,
        )

        print(
            "Hoja válida:",
            sheet_valid,
        )

        print(
            "Motivo:",
            reason,
        )

        print("=" * 70)

        # ====================================================
        # NO ES HOJA DE CIERRE
        # ====================================================

        if not is_service_closure_sheet:

            session[
                "closure_service_sheet_path"
            ] = None

            session[
                "closure_service_sheet_filename"
            ] = None

            session[
                "closure_service_sheet_mime_type"
            ] = None

            session[
                "waiting_for"
            ] = "closure_service_sheet_photo"

            save_session(
                phone=phone,
                session=session,
            )

            response = (
                operations_header()
                + " La imagen recibida no parece "
                + "corresponder a una *Hoja de Cierre "
                + "de Servicio*.\n\n"
                + " Envíame nuevamente la hoja correcta.\n\n"
                + "Procura que el documento se vea "
                + "completo y legible."
            )

            if reason:

                print(
                    "Motivo IA:",
                    reason,
                )

            return response

        # ====================================================
        # TIMBRE NO DETECTADO
        # ====================================================

        if stamp_status == "not_detected":

            session[
                "closure_service_sheet_path"
            ] = None

            session[
                "closure_service_sheet_filename"
            ] = None

            session[
                "closure_service_sheet_mime_type"
            ] = None

            session[
                "waiting_for"
            ] = "closure_service_sheet_photo"

            save_session(
                phone=phone,
                session=session,
            )

            return (
                operations_header()
                + " Reconocí correctamente la "
                + "*Hoja de Cierre de Servicio*, "
                + "pero no detecté el *timbre del cliente*.\n\n"
                + " El timbre es obligatorio para "
                + "registrar el cierre.\n\n"
                + "Solicita el timbre correspondiente "
                + "y luego envíame nuevamente una "
                + "fotografía completa y legible."
            )

        # ====================================================
        # TIMBRE NO SE PUEDE CONFIRMAR
        # ====================================================

        if stamp_status == "uncertain":

            session[
                "closure_service_sheet_path"
            ] = None

            session[
                "closure_service_sheet_filename"
            ] = None

            session[
                "closure_service_sheet_mime_type"
            ] = None

            session[
                "waiting_for"
            ] = "closure_service_sheet_photo"

            save_session(
                phone=phone,
                session=session,
            )

            return (
                operations_header()
                + " Reconocí la *Hoja de Cierre*, "
                + "pero no logro confirmar claramente "
                + "el timbre del cliente.\n\n"
                + "Puede estar borroso, oscuro, cortado "
                + "o poco visible.\n\n"
                + " Toma nuevamente la fotografía "
                + "mostrando la hoja completa y el "
                + "timbre claramente visible."
            )

        # ====================================================
        # PROTECCIÓN EXTRA
        # ====================================================

        if not sheet_valid:

            session[
                "closure_service_sheet_path"
            ] = None

            session[
                "closure_service_sheet_filename"
            ] = None

            session[
                "closure_service_sheet_mime_type"
            ] = None

            session[
                "waiting_for"
            ] = "closure_service_sheet_photo"

            save_session(
                phone=phone,
                session=session,
            )

            return (
                operations_header()
                + " No pude validar correctamente "
                + "la Hoja de Cierre.\n\n"
                + " Envíame nuevamente una fotografía "
                + "completa, legible y con el timbre "
                + "del cliente claramente visible."
            )

        # ====================================================
        # HOJA APROBADA
        #
        # RECIÉN AQUÍ GUARDAMOS LA FOTO COMO VÁLIDA.
        # ====================================================

        push_history(
            phone
        )

        session = get_session(
            phone
        )

        session[
            "closure_sheet_validation"
        ] = validation
        session[
            "closure_sheet_is_valid"
        ] = sheet_valid
        session[
            "closure_sheet_is_service_closure_sheet"
        ] = is_service_closure_sheet
        session[
            "closure_sheet_stamp_detected"
        ] = stamp_detected
        session[
            "closure_sheet_stamp_status"
        ] = stamp_status
        session[
            "closure_sheet_signature_detected"
        ] = signature_detected
        session[
            "closure_sheet_validation_confidence"
        ] = confidence
        session[
            "closure_sheet_validation_reason"
        ] = reason

        session[
            "closure_service_sheet_path"
        ] = file_path

        session[
            "closure_service_sheet_filename"
        ] = filename

        session[
            "closure_service_sheet_mime_type"
        ] = mime_type

        session[
            "closure_service_sheet_uploaded"
        ] = False

        session[
            "waiting_for"
        ] = "closure_service_photo"

        save_session(
            phone=phone,
            session=session,
        )

        print()
        print("=" * 70)
        print(" HOJA DE CIERRE APROBADA")
        print("=" * 70)

        print(
            "COT:",
            session.get(
                "cot"
            ),
        )

        print(
            "Archivo:",
            file_path,
        )

        print(
            "Timbre:",
            "DETECTADO",
        )

        print(
            "Firma:",
            (
                "DETECTADA"
                if signature_detected
                else "NO CONFIRMADA"
            ),
        )

        print(
            "Confianza:",
            confidence,
        )

        print("=" * 70)

        return build_validated_closure_sheet_message(
            stamp_detected=stamp_detected,
            signature_detected=signature_detected,
        )

    # ========================================================
    # FOTO 2:
    # SERVICIO REALIZADO
    # ========================================================

    if waiting_for in (
        "closure_service_photo",
        "additional_work_photo",
    ):

        is_additional_photo = (
            waiting_for
            == "additional_work_photo"
        )

        push_history(
            phone
        )

        session = get_session(
            phone
        )

        evidence_count = append_closure_service_photo(
            session=session,
            file_path=file_path,
            filename=filename,
            mime_type=mime_type,
        )

        session[
            "waiting_for"
        ] = "closure_confirmation"

        save_session(
            phone=phone,
            session=session,
        )

        print()
        print("=" * 70)
        print(" FOTO DEL SERVICIO RECIBIDA")
        print("=" * 70)

        print(
            "COT:",
            session.get(
                "cot"
            ),
        )

        print(
            "Archivo:",
            file_path,
        )

        print(
            "Evidencias:",
            evidence_count,
        )

        print("=" * 70)

        if is_additional_photo:

            return build_additional_photo_added_message(
                session
            )

        return build_closure_confirmation_message(
            session
        )

    # ========================================================
    # YA TENEMOS LAS DOS FOTOS
    # ========================================================

    if waiting_for == "closure_confirmation":

        return build_closure_confirmation_message(
            session
        )

    return (
        operations_header()
        + "No estaba esperando una fotografía "
        + "en este momento."
    )


# ============================================================
# MENSAJE PARA SOLICITAR UBICACIÓN
# ============================================================

def build_service_list(
    employee: dict,
    action: str,
) -> tuple[list, str]:

    action = clean_text(
        action
    ).upper()

    is_start = action == "START_SERVICE"
    status = (
        "PROGRAMADO"
        if is_start
        else "ACTIVO"
    )

    try:

        if is_start:

            result = get_programmed_services_for_employee(
                employee
            )

        else:

            result = get_active_services_for_employee(
                employee
            )

    except Exception as error:

        print(
            f"Error consultando servicios {status}:",
            type(error).__name__,
            str(error),
        )

        return [], (
            operations_header()
            + f"No pude consultar tus servicios {status.lower()}s "
            + "en este momento. Intenta nuevamente."
        )

    services = []
    pending_field_reports = []

    for record in ensure_list(
        result.get(
            "records"
        )
    ):

        if not isinstance(
            record,
            dict,
        ):

            continue

        identifier = clean_text(
            record.get(
                "quote_number"
            )
        )

        if (
            not identifier
            or not is_service_type_allowed(
                employee=employee,
                service_type=record.get(
                    "service_type"
                ),
            )
        ):

            continue

        if not is_start:
            report_status = get_closure_field_report_status(
                employee=employee,
                service_record_id=clean_text(
                    record.get("record_id")
                ),
                service_identifier=identifier,
                service_type=record.get("service_type"),
            )

            if (
                report_status.get("required")
                and not report_status.get("found")
            ):
                pending_field_reports.append(identifier)
                continue

        services.append(
            {
                "identifier": identifier,
                "record_id": clean_text(
                    record.get(
                        "record_id"
                    )
                ),
                "service_type": record.get(
                    "service_type"
                ),
            }
        )

    if not services and pending_field_reports:
        return [], build_pending_field_report_message(
            pending_field_reports[0]
        )

    if not services:

        return [], (
            operations_header()
            + f"No tienes servicios *{status}* que correspondan "
            + "a tu cargo en este momento."
        )

    lines = [
        f"{index}. *{service['identifier']}*"
        for index, service in enumerate(
            services,
            start=1,
        )
    ]

    action_text = (
        "iniciar"
        if is_start
        else "cerrar"
    )

    message = (
        operations_header()
        + f"Vamos a {action_text} un servicio.\n\n"
        + f"Selecciona un servicio {status.lower()}:\n\n"
        + "\n".join(
            lines
        )
        + "\n\nResponde con el número de la opción "
        + "o escribe el ID completo del servicio."
    )

    return services, message


def resolve_service_selection(
    text: str,
    session: dict,
):

    value = clean_text(
        text
    )

    if value.isdigit():
        services = ensure_list(
            session.get(
                "available_services"
            )
        )

        index = int(
            value
        ) - 1

        if 0 <= index < len(
            services
        ):
            selected = services[
                index
            ]

            if isinstance(
                selected,
                dict,
            ):
                return selected

    services = ensure_list(
        session.get(
            "available_services"
        )
    )

    normalized_value = normalize_text(
        value
    )

    exact_matches = [
        service
        for service in services
        if isinstance(
            service,
            dict,
        )
        and normalize_text(
            service.get(
                "identifier"
            )
        ) == normalized_value
    ]

    if len(
        exact_matches
    ) == 1:

        return exact_matches[
            0
        ]

    cot = extract_cot(
        value
    )

    if not cot:

        return None

    cot_matches = [
        service
        for service in services
        if isinstance(
            service,
            dict,
        )
        and extract_cot(
            service.get(
                "identifier"
            )
        ) == cot
    ]

    if len(
        cot_matches
    ) == 1:

        return cot_matches[
            0
        ]

    if len(
        cot_matches
    ) > 1:

        return None

    return {
        "identifier": cot,
        "record_id": None,
    }


def build_location_request_message(
    session: dict,
    helper_text: str = "",
) -> str:

    service_address = clean_text(
        session.get(
            "service_address"
        )
    )

    cot = clean_text(
        session.get(
            "cot"
        )
    )

    response = (
        operations_header()
    )

    if cot:

        response += (
            f"Servicio: *{cot}*\n\n"
        )

    if helper_text:

        response += (
            helper_text
            + "\n\n"
        )

    if service_address:

        response += (
            "Dirección del servicio:\n"
            f" {service_address}\n\n"
        )

    response += (
        "Ahora comparte tu ubicación actual "
        "desde WhatsApp para registrar "
        "el inicio del servicio."
    )

    return response


# ============================================================
# SELECCIONAR SERVICIO PARA INICIO
# ============================================================

def select_service(
    phone: str,
    cot: str,
    employee: dict,
    service_record_id: str = None,
) -> str:

    context = get_operational_service_context(
        cot=cot,
        employee=employee,
        statuses=[
            "PROGRAMADO",
        ],
        record_id=service_record_id,
    )

    print()
    print("=" * 70)
    print(" DEBUG COT SELECCIONADA - INICIO")
    print("=" * 70)

    print(
        "COT solicitada:",
        cot,
    )

    print(
        "Contexto found:",
        context.get(
            "found"
        ),
    )

    print(
        "Record ID:",
        context.get(
            "record_id"
        ),
    )

    print(
        "COT devuelta:",
        context.get(
            "cot"
        ),
    )

    print(
        "Estado:",
        context.get(
            "status"
        ),
    )

    print(
        "Dirección servicio:",
        context.get(
            "service_address"
        ),
    )

    print(
        "Técnicos recibidos:",
        context.get(
            "technicians"
        ),
    )

    print(
        "Ayudantes recibidos:",
        context.get(
            "helpers"
        ),
    )

    print(
        "Supervisores recibidos:",
        context.get(
            "supervisors"
        ),
    )

    print("=" * 70)

    if not context.get(
        "found"
    ):

        return (
            operations_header()
            + f"No encontré *{cot}* entre los "
            + "servicios programados que tienes "
            + "asignados."
        )

    if not is_service_type_allowed(
        employee=employee,
        service_type=context.get(
            "service_type"
        ),
    ):

        return (
            operations_header()
            + "Ese servicio programado no corresponde "
            + "al tipo habilitado para tu cargo."
        )

    session = get_session(
        phone
    )

    if not session:

        session = create_session(
            phone=phone,
            action="START_SERVICE",
        )

        session[
            "waiting_for"
        ] = "cot"

        save_session(
            phone=phone,
            session=session,
        )

    push_history(
        phone
    )

    session = get_session(
        phone
    )

    session[
        "cot"
    ] = (
        context.get(
            "quote_number"
        )
        or context.get(
            "cot"
        )
        or cot
    )

    session[
        "oc"
    ] = context.get(
        "oc"
    )

    session[
        "service_record_id"
    ] = context.get(
        "record_id"
    )

    session["service_type"] = context.get("service_type")
    session["service_status"] = context.get("status") or "ACTIVO"

    session[
        "service_address"
    ] = clean_text(
        context.get(
            "service_address"
        )
    )

    session[
        "service_description"
    ] = clean_text(
        context.get(
            "service_description"
        )
    )

    session[
        "service_type"
    ] = clean_text(
        context.get(
            "service_type"
        )
    )

    session[
        "service_status"
    ] = clean_text(
        context.get(
            "status"
        )
    ).upper()

    raw_technicians = ensure_list(
        context.get(
            "technicians"
        )
    )

    raw_helpers = ensure_list(
        context.get(
            "helpers"
        )
    )

    technicians_resolved = (
        resolve_employee_links(
            raw_technicians
        )
        if raw_technicians
        else []
    )

    helpers_resolved = (
        resolve_employee_links(
            raw_helpers
        )
        if raw_helpers
        else []
    )

    technicians_resolved = ensure_list(
        technicians_resolved
    )

    helpers_resolved = ensure_list(
        helpers_resolved
    )

    technician_pairs = build_worker_pairs(
        raw_values=raw_technicians,
        resolved_names=technicians_resolved,
    )

    helper_pairs = build_worker_pairs(
        raw_values=raw_helpers,
        resolved_names=helpers_resolved,
    )

    helpers = [
        worker.get(
            "name"
        )
        for worker in helper_pairs
        if worker.get(
            "name"
        )
    ]

    helper_ids = [
        worker.get(
            "record_id"
        )
        for worker in helper_pairs
        if worker.get(
            "record_id"
        )
    ]

    employee_name = clean_text(
        employee.get(
            "nombre"
        )
    )

    employee_record_id = clean_text(
        employee.get(
            "record_id"
        )
    )

    session["operator_role"] = clean_text(
        employee.get("cargo")
    )

    if is_helper(employee):
        helper_pairs = [
            worker
            for worker in helper_pairs
            if not worker_matches_employee(
                worker=worker,
                employee_name=employee_name,
                employee_record_id=employee_record_id,
            )
        ]
        helpers = [
            worker.get("name")
            for worker in helper_pairs
            if worker.get("name")
        ]
        helper_ids = [
            worker.get("record_id")
            for worker in helper_pairs
            if worker.get("record_id")
        ]

    if employee_name:

        session[
            "technician"
        ] = employee_name

        session[
            "technician_record_id"
        ] = (
            employee_record_id
            or None
        )

    elif technician_pairs:

        session[
            "technician"
        ] = technician_pairs[
            0
        ].get(
            "name"
        )

        session[
            "technician_record_id"
        ] = technician_pairs[
            0
        ].get(
            "record_id"
        )

    session[
        "available_helpers"
    ] = helpers

    session[
        "available_helper_ids"
    ] = helper_ids

    session[
        "use_helper"
    ] = None

    session[
        "helper_mode"
    ] = None

    session[
        "selected_helpers"
    ] = []

    session[
        "selected_helper_ids"
    ] = []

    save_session(
        phone=phone,
        session=session,
    )

    # ========================================================
    # SIN AYUDANTES
    # ========================================================

    if len(
        helpers
    ) == 0:

        session[
            "use_helper"
        ] = False

        session[
            "waiting_for"
        ] = "location"

        save_session(
            phone=phone,
            session=session,
        )

        return build_location_request_message(
            session=session,
            helper_text=(
                "Esta COT no tiene ayudantes asignados."
            ),
        )

    # ========================================================
    # UN AYUDANTE
    # ========================================================

    if len(
        helpers
    ) == 1:

        session[
            "waiting_for"
        ] = "helper_confirmation"

        save_session(
            phone=phone,
            session=session,
        )

        response = (
            operations_header()
            + "Servicio seleccionado: "
            + f"*{session.get('cot')}*\n\n"
        )

        service_address = clean_text(
            session.get(
                "service_address"
            )
        )

        if service_address:

            response += (
                "Dirección del servicio:\n"
                f" {service_address}\n\n"
            )

        response += (
            "Ayudante asignado:\n"
            f"• *{helpers[0]}*\n\n"
            "¿Iniciarás este servicio con "
            "este ayudante?\n\n"
            "1. Sí\n"
            "2. No"
        )

        return response

    # ========================================================
    # VARIOS AYUDANTES
    # ========================================================

    lines = []

    for index, helper in enumerate(
        helpers,
        start=1,
    ):

        lines.append(
            f"{index}. {helper}"
        )

    session[
        "use_helper"
    ] = True

    session[
        "waiting_for"
    ] = "helper_mode"

    save_session(
        phone=phone,
        session=session,
    )

    response = (
        operations_header()
        + "Servicio seleccionado: "
        + f"*{session.get('cot')}*\n\n"
    )

    service_address = clean_text(
        session.get(
            "service_address"
        )
    )

    if service_address:

        response += (
            "Dirección del servicio:\n"
            f" {service_address}\n\n"
        )

    response += (
        "Ayudantes asignados a esta COT:\n\n"
        + "\n".join(
            lines
        )
        + "\n\n¿Trabajarás con:\n\n"
        + "1. Todos\n"
        + "2. Solo uno"
    )

    return response


# ============================================================
# SELECCIONAR SERVICIO PARA CIERRE
# ============================================================

def select_service_for_closure(
    phone: str,
    cot: str,
    employee: dict,
    service_record_id: str = None,
) -> str:

    context = get_operational_service_context(
        cot=cot,
        employee=employee,
        statuses=[
            "ACTIVO",
        ],
        record_id=service_record_id,
    )

    print()
    print("=" * 70)
    print(" DEBUG COT SELECCIONADA - CIERRE")
    print("=" * 70)

    print(
        "COT solicitada:",
        cot,
    )

    print(
        "Encontrada:",
        context.get(
            "found"
        ),
    )

    print(
        "COT devuelta:",
        context.get(
            "cot"
        ),
    )

    print(
        "Estado:",
        context.get(
            "status"
        ),
    )

    print(
        "Record ID:",
        context.get(
            "record_id"
        ),
    )

    print(
        "Ayudantes:",
        context.get(
            "helpers"
        ),
    )

    print("=" * 70)

    if not context.get(
        "found"
    ):

        return (
            operations_header()
            + f"No encontré *{cot}* entre los "
            + "servicios activos "
            + "que tienes asignados."
        )

    if not is_service_type_allowed(
        employee=employee,
        service_type=context.get(
            "service_type"
        ),
    ):

        return (
            operations_header()
            + "Ese servicio activo no corresponde "
            + "al tipo habilitado para tu cargo."
        )

    service_identifier = (
        context.get("quote_number")
        or context.get("cot")
        or cot
    )
    report_status = get_closure_field_report_status(
        employee=employee,
        service_record_id=context.get("record_id"),
        service_identifier=service_identifier,
        service_type=context.get("service_type"),
    )

    if (
        report_status.get("required")
        and not report_status.get("found")
    ):
        return build_pending_field_report_message(
            service_identifier
        )

    session = get_session(
        phone
    )

    if not session:

        session = create_session(
            phone=phone,
            action="CLOSE_SERVICE",
        )

        session[
            "waiting_for"
        ] = "cot_close"

        save_session(
            phone=phone,
            session=session,
        )

    push_history(
        phone
    )

    session = get_session(
        phone
    )

    # ========================================================
    # SERVICIO
    # ========================================================

    session[
        "cot"
    ] = (
        context.get(
            "quote_number"
        )
        or context.get(
            "cot"
        )
        or cot
    )

    session[
        "oc"
    ] = context.get(
        "oc"
    )

    session[
        "service_record_id"
    ] = context.get(
        "record_id"
    )

    session["service_type"] = context.get("service_type")
    session["service_status"] = context.get("status") or "ACTIVO"

    # ========================================================
    # TÉCNICO QUE CIERRA
    # ========================================================

    technician_name = clean_text(
        employee.get(
            "nombre"
        )
    )

    technician_record_id = clean_text(
        employee.get(
            "record_id"
        )
    )

    session[
        "closure_technician"
    ] = technician_name

    session[
        "closure_technician_record_id"
    ] = (
        technician_record_id
        or None
    )

    session["closure_worker_role"] = clean_text(
        employee.get("cargo")
    )

    # ========================================================
    # AYUDANTES
    # ========================================================

    raw_helpers = ensure_list(
        context.get(
            "helpers"
        )
    )

    helpers_resolved = (
        resolve_employee_links(
            raw_helpers
        )
        if raw_helpers
        else []
    )

    helpers_resolved = ensure_list(
        helpers_resolved
    )

    helper_pairs = build_worker_pairs(
        raw_values=raw_helpers,
        resolved_names=helpers_resolved,
    )

    if is_helper(employee):
        helper_pairs = [
            worker
            for worker in helper_pairs
            if not worker_matches_employee(
                worker=worker,
                employee_name=technician_name,
                employee_record_id=technician_record_id,
            )
        ]

    helpers = [
        worker.get(
            "name"
        )
        for worker in helper_pairs
        if worker.get(
            "name"
        )
    ]

    helper_ids = [
        worker.get(
            "record_id"
        )
        for worker in helper_pairs
        if worker.get(
            "record_id"
        )
    ]

    session[
        "available_helpers"
    ] = helpers

    session[
        "available_helper_ids"
    ] = helper_ids

    # ========================================================
    # REINICIAR DATOS CIERRE
    # ========================================================

    session[
        "closure_use_helper"
    ] = False

    session[
        "closure_helper"
    ] = None

    session[
        "closure_helper_record_id"
    ] = None

    session[
        "closure_helpers"
    ] = []

    session[
        "closure_helper_ids"
    ] = []

    session[
        "closure_observations"
    ] = None

    session["closure_satisfactory"] = None
    session["closure_mitigation_cause"] = None

    session[
        "closure_confirmed"
    ] = False

    session[
        "closure_record_id"
    ] = None

    # ========================================================
    # HOJA DE CIERRE
    # ========================================================

    session[
        "closure_service_sheet_path"
    ] = None

    session[
        "closure_service_sheet_filename"
    ] = None

    session[
        "closure_service_sheet_mime_type"
    ] = None

    session[
        "closure_service_sheet_uploaded"
    ] = False

    # ========================================================
    # VALIDACIÓN IA HOJA
    # ========================================================

    session[
        "closure_sheet_validation"
    ] = None

    session[
        "closure_sheet_is_valid"
    ] = False

    session[
        "closure_sheet_is_service_closure_sheet"
    ] = False

    session[
        "closure_sheet_stamp_detected"
    ] = False

    session[
        "closure_sheet_stamp_status"
    ] = None

    session[
        "closure_sheet_signature_detected"
    ] = False

    session[
        "closure_sheet_validation_confidence"
    ] = None

    session[
        "closure_sheet_validation_reason"
    ] = None

    # ========================================================
    # FOTO SERVICIO
    # ========================================================

    session[
        "closure_service_photo_path"
    ] = None

    session[
        "closure_service_photo_filename"
    ] = None

    session[
        "closure_service_photo_mime_type"
    ] = None

    session[
        "closure_service_photo_uploaded"
    ] = False

    session[
        "closure_service_photos"
    ] = []

    session[
        "service_photos_count"
    ] = 0

    # ========================================================
    # AYUDANTES AUTOMÁTICOS
    # ========================================================

    if helpers:

        session[
            "closure_use_helper"
        ] = True

        session[
            "closure_helpers"
        ] = list(
            helpers
        )

        session[
            "closure_helper_ids"
        ] = list(
            helper_ids
        )

        session[
            "closure_helper"
        ] = clean_text(
            helpers[
                0
            ]
        )

        session[
            "closure_helper_record_id"
        ] = (
            helper_ids[
                0
            ]
            if helper_ids
            else None
        )

    # ========================================================
    # SIGUIENTE PASO
    # ========================================================

    session["waiting_for"] = (
        "closure_satisfaction"
        if uses_technician_operations_flow(employee)
        else "closure_observations"
    )

    save_session(
        phone=phone,
        session=session,
    )

    # ========================================================
    # DEBUG
    # ========================================================

    print()
    print("=" * 70)
    print(" DATOS CIERRE GUARDADOS EN SESIÓN")
    print("=" * 70)

    print(
        "COT:",
        session.get(
            "cot"
        ),
    )

    print(
        "Service Record ID:",
        session.get(
            "service_record_id"
        ),
    )

    print(
        f"{closure_worker_label(session)}:",
        technician_name,
    )

    print(
        "Técnico Record ID:",
        technician_record_id,
    )

    print(
        "Ayudantes detectados:",
        helpers,
    )

    print(
        "Ayudantes Record IDs:",
        helper_ids,
    )

    print(
        "Siguiente estado:",
        session.get(
            "waiting_for"
        ),
    )

    print("=" * 70)

    # ========================================================
    # RESPUESTA
    # ========================================================

    response = (
        operations_header()
        + "Servicio seleccionado: "
        + f"*{session.get('cot')}*\n\n"
        + f"{closure_worker_label(session)} que cierra:\n"
        + f"• *{technician_name}*\n\n"
    )

    if helpers:

        if len(
            helpers
        ) == 1:

            response += (
                "Ayudante asignado:\n"
                + f"• *{helpers[0]}*\n\n"
            )

        else:

            response += (
                "Ayudantes asignados:\n"
            )

            for helper in helpers:

                response += (
                    f"• {helper}\n"
                )

            response += "\n"

    else:

        response += (
            "Ayudante: *No aplica*\n\n"
        )

    if uses_technician_operations_flow(employee):
        response += "¿El servicio fue culminado de forma satisfactoria?"
    else:
        response += closure_observations_prompt()

    return response


# ============================================================
# PROCESAR UBICACIÓN
#
# EXCLUSIVAMENTE PARA INICIO.
# ============================================================

def process_operations_location(
    phone: str,
    employee: dict,
    location_text: str,
    latitude=None,
    longitude=None,
):

    session = get_session(
        phone
    )

    if not session:

        return (
            operations_header()
            + "No hay ningún proceso esperando "
            + "una ubicación."
        )

    if session.get(
        "action"
    ) == "CLOSE_SERVICE":

        return (
            operations_header()
            + "El cierre del servicio no está "
            + "esperando una ubicación.\n\n"
            + "Continúa respondiendo las preguntas "
            + "del formulario de cierre."
        )

    waiting_for = session.get(
        "waiting_for"
    )

    if waiting_for not in (
        "location",
        "service_activation",
    ):

        return (
            operations_header()
            + "No estaba esperando una ubicación "
            + "en este momento."
        )

    action = session.get(
        "action"
    )

    activation_retry = (
        waiting_for == "service_activation"
        and session.get("start_activity_created")
    )

    latitude = clean_coordinate(
        latitude
    )

    longitude = clean_coordinate(
        longitude
    )

    location_text = clean_text(
        location_text
    )

    # ========================================================
    # GUARDAR GPS
    # ========================================================

    session[
        "start_latitude"
    ] = latitude

    session[
        "start_longitude"
    ] = longitude

    session[
        "start_location"
    ] = location_text

    if not activation_retry:
        # La ubicación ya fue consumida. Mientras se registra el Inicio,
        # el webhook no debe interpretarla como todavía pendiente.
        session[
            "waiting_for"
        ] = "registering_start"

    save_session(
        phone=phone,
        session=session,
    )

    print()
    print("=" * 70)
    print(" UBICACIÓN EN OPERACIONES")
    print("=" * 70)

    print(
        "COT:",
        session.get(
            "cot"
        ),
    )

    print(
        "Ubicación inicio:",
        location_text,
    )

    print(
        "Latitud inicio:",
        latitude,
    )

    print(
        "Longitud inicio:",
        longitude,
    )

    print(
        "Dirección servicio:",
        session.get(
            "service_address"
        ),
    )

    print("=" * 70)

    if action != "START_SERVICE":

        return (
            operations_header()
            + "La sesión actual no corresponde "
            + "a un inicio de servicio válido."
        )

    # ========================================================
    # CREAR INICIO
    # ========================================================

    if session.get(
        "start_activity_created"
    ):
        # Un intento anterior ya creó/localizó el Inicio, pero falló la
        # activación del servicio. No se vuelve a escribir el Inicio.
        result = {
            "created": True,
            "record_id": session.get(
                "activity_record_id"
            ),
            "service_record_id": session.get(
                "service_record_id"
            ),
            "distance_km": session.get(
                "start_distance_km"
            ),
        }
    else:
        result = create_activity_start(
            cot=session.get(
                "cot"
            ),

            service_record_id=session.get(
                "service_record_id"
            ),

            technician_name=session.get(
                "technician"
            ),

            technician_record_id=session.get(
                "technician_record_id"
            ),

            helper_names=session.get(
                "selected_helpers",
                [],
            ),

            helper_record_ids=session.get(
                "selected_helper_ids",
                [],
            ),

            location=location_text,

            service_address=session.get(
                "service_address"
            ),

            start_latitude=latitude,

            start_longitude=longitude,
        )

    if not result.get(
        "created"
    ):

        session[
            "waiting_for"
        ] = "location"

        save_session(
            phone=phone,
            session=session,
        )

        print()
        print("=" * 70)
        print(" NO SE PUDO REGISTRAR INICIO")
        print("=" * 70)

        print(
            "Resultado:",
            result,
        )

        print("=" * 70)

        return (
            operations_header()
            + "No pude registrar el inicio "
            + "del servicio en Airtable.\n\n"
            + "La sesión permanece activa "
            + "para volver a intentarlo."
        )

    # Este estado se persiste antes de activar el servicio. Si Airtable
    # falla en el siguiente PATCH, el reintento conoce el Inicio exacto
    # y omite create_activity_start().
    session[
        "activity_record_id"
    ] = result.get(
        "record_id"
    )

    session[
        "start_activity_created"
    ] = True

    session[
        "service_activation_pending"
    ] = True

    session[
        "waiting_for"
    ] = "service_activation"

    session[
        "start_distance_km"
    ] = result.get(
        "distance_km"
    )

    save_session(
        phone=phone,
        session=session,
    )

    # El inicio existe correctamente. Recién ahora se activa la
    # Solicitud de Servicio exacta que originó esta sesión.
    service_record_id = clean_text(
        session.get(
            "service_record_id"
        )
    )

    status_result = update_service_status_by_record_id(
        service_record_id=service_record_id,
        status="ACTIVO",
    )

    if not status_result.get(
        "updated"
    ):
        return (
            operations_header()
            + "El Inicio de Actividad fue registrado, pero no pude "
            + "actualizar el Estado del Servicio a *ACTIVO*.\n\n"
            + "La sesión permanece disponible para reintentar y no "
            + "se inició el levantamiento."
        )

    session[
        "service_status"
    ] = "ACTIVO"

    session[
        "service_activation_pending"
    ] = False

    session[
        "waiting_for"
    ] = None

    save_session(
        phone=phone,
        session=session,
    )

    # ========================================================
    # RESPUESTA
    # ========================================================

    cot = clean_text(
        session.get(
            "cot"
        )
    )

    helper_names = ensure_list(
        session.get(
            "selected_helpers"
        )
    )

    service_description = clean_text(
        session.get(
            "service_description"
        )
    )

    service_address = clean_text(
        session.get(
            "service_address"
        )
    )

    distance_km = session.get(
        "start_distance_km"
    )

    service_type = clean_text(
        session.get(
            "service_type"
        )
    )

    is_quote_service = (
        normalize_text(
            service_type
        )
        == "cotizacion"
    )

    should_start_survey = (
        can_perform_field_survey(
            employee
        )
        and is_quote_service
    )

    response = (
        operations_header()
        + " *Inicio de servicio registrado*\n\n"
        + f"Servicio: *{cot}*\n"
    )

    if service_description:

        response += (
            "Descripción del servicio: "
            f"{service_description}\n"
        )

    if len(
        helper_names
    ) == 1:

        response += (
            "Ayudante: "
            f"{helper_names[0]}\n"
        )

    elif len(
        helper_names
    ) > 1:

        response += (
            "Ayudantes:\n"
            + "\n".join(
                f"• {name}"
                for name in helper_names
            )
            + "\n"
        )

    else:

        response += (
            "Ayudante: No aplica\n"
        )

    if service_address:

        response += (
            "Dirección servicio: "
            f"{service_address}\n"
        )

    response += (
        "Ubicación inicio: "
        f"{location_text}"
    )

    if distance_km is not None:

        response += (
            "\nDistancia al servicio: "
            f"{distance_km} km"
        )

    # La sesión de Operaciones ya cumplió su objetivo.
    clear_session(
        phone
    )

    if not should_start_survey:
        return response

    # Solo Supervisor + Cotización continúa al flujo real de Maestro.
    # Conservamos el record exacto creado/localizado en Inicio.
    try:
        from app.agents.maestro.service import (
            process_field_report_message,
        )
        from app.agents.maestro.session import (
            get_session as get_maestro_session,
            save_session as save_maestro_session,
        )

        survey_response = process_field_report_message(
            phone=phone,
            text=cot,
            employee=employee,
        )

        maestro_session = get_maestro_session(
            phone
        )

        if isinstance(maestro_session, dict):
            maestro_session["activity_record_id"] = session.get(
                "activity_record_id"
            )
            maestro_session["quote_record_id"] = (
                result.get("service_record_id")
                or maestro_session.get("quote_record_id")
            )
            maestro_session["service_status"] = "ACTIVO"
            save_maestro_session(
                phone,
                maestro_session,
            )

        # Airtable ya confirmó ACTIVO. Esto protege el primer mensaje
        # ante cualquier contexto antiguo que Maestro hubiera reutilizado.
        survey_response = str(
            survey_response
            or ""
        ).replace(
            "• Estado: *PROGRAMADO*",
            "• Estado: *ACTIVO*",
        )

    except Exception as error:
        print(
            "Error iniciando levantamiento automático:",
            type(error).__name__,
            str(error),
        )
        response += (
            "\n\nEl servicio es de tipo *Cotización*, "
            "pero no pude abrir el levantamiento automáticamente. "
            "El inicio del servicio sí quedó registrado."
        )
        return response

    # El comprobante operacional y el levantamiento son unidades de UX
    # distintas. El webhook enviará el primero como texto normal y
    # asociará las acciones contextuales solamente al segundo.
    return {
        "messages": [
            response,
            survey_response,
        ],
    }
