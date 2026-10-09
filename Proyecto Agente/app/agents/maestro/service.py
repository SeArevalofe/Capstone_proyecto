import re
import unicodedata

from app.airtable.service_request_repository import (
    get_quote,
    upload_field_image,
    get_programmed_services_for_employee,
    get_active_services_for_employee,
    get_paused_services_for_employee,
    get_operational_services_for_employee,
)

from app.airtable.activity_repository import (
    save_field_report_to_activity,
)

from app.airtable.service_closure_repository import (
    sync_report_to_existing_closure,
)

from app.agents.maestro.permissions import (
    can_create_field_report,
    can_save_field_report,
)

from app.agents.maestro.session import (
    start_session,
    get_session,
    save_session,
    delete_session,
    push_history,
    pop_history,
    clear_history,
)

from app.agents.maestro.conversation_engine import (
    analyze_message,
)

from app.agents.maestro.report_preview import (
    build_preview,
)

from app.agents.maestro.validation import (
    expected_question_fields,
    extract_contextual_values,
    field_has_valid_value,
    get_required_missing,
    is_vague_response,
    sanitize_report_data,
)

# ============================================================
# CONSTANTES
# ============================================================

OPERATIVE_STATUSES = (
    "PROGRAMADO",
    "ACTIVO",
    "PAUSADO",
)

SESSION_DEFAULTS = {
    "quote_number": None,
    "quote_record_id": None,
    "activity_record_id": None,
    "quote_record": None,
    "selected_service_id": None,
    "oc": None,
    "service_status": None,
    "available_services": [],
    "requested_service_status": None,
    "last_question_field": None,
    "pending_question_fields": [],
    "status": "active",
    "data": {},
    "critical_missing": [],
    "recommended_missing": [],
    "optional_missing": [],
    "ask_for_observations": False,
    "ready_for_report": False,
    "editing_report": False,
    "status_before_pause": None,
    "pending_new_job": None,
    "last_intent": None,
}

# Cuando el usuario dice explícitamente que está CORRIGIENDO
# estos campos, normalmente desea reemplazarlos en vez de
# acumular información antigua.
REPLACEABLE_LIST_FIELDS = {
    "materiales",
    "cantidades",
    "trabajos_requeridos",
    "equipamiento_necesario",
    "observaciones",
}


# ============================================================
# RETROCEDER UN PASO
# ============================================================

def is_back_request(
    text: str,
) -> bool:

    value = normalize_text(text)

    return value in {
        "volver",
        "atras",
        "volver atras",
        "retroceder",
        "retroceso",
    }


def build_maestro_step_message(
    phone: str,
    employee: dict,
    session: dict,
) -> str:

    if not isinstance(session, dict):
        return (
            "👷 *Agente JCF*\n\n"
            "No hay un paso anterior disponible."
        )

    quote_number = session.get("quote_number")
    available_services = session.get("available_services", [])

    if not quote_number:
        if isinstance(available_services, list) and available_services:
            return build_services_message(
                employee=employee,
                services=available_services,
                requested_status=session.get("requested_service_status"),
            )

        return (
            "👷 *Agente JCF*\n\n"
            "Ya estás en el primer paso del levantamiento.\n\n"
            "Escribe *mis servicios* para ver tus COT "
            "o *Hola* para volver al menú principal."
        )

    preview = build_preview(
        session=session,
        title="Levantamiento retomado",
    )

    status = normalize_text(session.get("status"))

    if status == "awaiting_save_confirmation":
        session["status"] = "ready_to_generate"
        session["last_question_field"] = "final_confirmation"
        save_session(phone, session)
        status = "ready_to_generate"

    if status == "ready_to_generate":

        return combine_preview(
            preview=preview,
            message=(
                "El levantamiento está listo.\n\n"
                "Puedes modificar la información o generar el informe."
            ),
        )

    if session.get("last_question_field") == "observaciones":
        return combine_preview(
            preview=preview,
            message=(
                "Volviste al paso anterior.\n\n"
                "📝 *Observaciones*\n\n"
                "¿Quieres agregar alguna observación adicional?"
            ),
        )

    critical_missing = normalize_list(
        session.get("critical_missing")
    )
    operational_missing = get_operational_missing(
        session.get("data", {})
    )

    if critical_missing:
        return combine_preview(
            preview=preview,
            message=(
                "Volviste al paso anterior.\n\n"
                + build_all_missing_questions(
                    critical_missing=critical_missing,
                    operational_missing=operational_missing,
                    next_question="",
                )
            ),
        )

    last_question_field = session.get("last_question_field")

    if last_question_field:
        question = missing_to_question(last_question_field)
        if question:
            return combine_preview(
                preview=preview,
                message="Volviste al paso anterior.\n\n" + question,
            )

    return combine_preview(
        preview=preview,
        message=(
            "Volviste al paso anterior.\n\n"
            "Continúa desde este punto del levantamiento."
        ),
    )


def handle_maestro_back(
    phone: str,
    employee: dict,
    session: dict,
) -> str:

    if not isinstance(session, dict):
        return (
            "👷 *Agente JCF*\n\n"
            "No hay un levantamiento activo al cual retroceder.\n\n"
            "Escribe *Hola* para volver al menú principal."
        )

    restored_session = pop_history(phone)

    if not restored_session:
        return (
            "👷 *Agente JCF*\n\n"
            "Ya estás en el primer paso disponible.\n\n"
            "Escribe *Hola* si quieres volver al menú principal."
        )

    return build_maestro_step_message(
        phone=phone,
        employee=employee,
        session=restored_session,
    )


# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================

def process_field_report_message(
    phone: str,
    text: str,
    employee: dict,
) -> str:

    text_clean = str(
        text
        or ""
    ).strip()

    if not text_clean:

        return (
            " *Agente JCF*\n\n"
            "No recibí información para procesar."
        )

    # ========================================================
    # VOLVER / ATRÁS / RETROCEDER
    # ========================================================

    if is_back_request(
        text_clean
    ):

        return handle_maestro_back(
            phone=phone,
            employee=employee,
            session=get_session(
                phone
            ),
        )

    # ========================================================
    # DEBUG
    # ========================================================

    print()
    print("=" * 70)
    print(" AGENTE MAESTRO JCF")
    print("=" * 70)

    print(
        "Teléfono WhatsApp:",
        phone,
    )

    print(
        "Trabajador:",
        employee.get(
            "nombre"
        ),
    )

    print(
        "Cargo:",
        employee.get(
            "cargo"
        ),
    )

    print(
        "Record ID RRHH2:",
        employee.get(
            "record_id"
        ),
    )

    print(
        "Impersonado:",
        employee.get(
            "impersonated",
            False,
        ),
    )

    print(
        "Mensaje:",
        text_clean,
    )

    print("=" * 70)

    # ========================================================
    # 0. EXPLICACIÓN DE ESTADOS
    # ========================================================

    status_explanation = (
        get_operational_status_explanation(
            text_clean
        )
    )

    if status_explanation:

        return status_explanation

    # ========================================================
    # 1. PREPARAR SESIÓN
    # ========================================================

    session = prepare_session(
        phone=phone,
        employee=employee,
    )

    current_employee_record_id = str(
        employee.get(
            "record_id"
        )
        or ""
    ).strip()

    push_history(
        phone
    )

    session = get_session(
        phone
    )

    was_paused = (
        session.get(
            "status"
        ) == "paused"
    )

    if was_paused:

        session[
            "status"
        ] = (
            session.pop(
                "status_before_pause",
                None,
            )
            or "active"
        )

        save_session(
            phone,
            session,
        )

        if is_resume_report_request(
            text_clean
        ):

            return build_maestro_step_message(
                phone=phone,
                employee=employee,
                session=session,
            )

    # ========================================================
    # 2. VOLVER A LISTA DE SERVICIOS
    #
    # No lo hacemos si el mensaje contiene una COT concreta,
    # porque podría tratarse de un cambio directo.
    # ========================================================

    if (
        session.get(
            "quote_number"
        )
        and wants_service_list(
            text_clean
        )
        and not has_specific_service_reference(
            text_clean
        )
    ):

        print()
        print("=" * 70)
        print(" VOLVIENDO A LISTA DE SERVICIOS")
        print("=" * 70)

        reset_to_service_selection(
            phone=phone,
            employee=employee,
        )

        return process_field_report_message(
            phone=phone,
            text=text_clean,
            employee=employee,
        )

    # ========================================================
    # 3. NO HAY SERVICIO SELECCIONADO
    # ========================================================

    if not session.get(
        "quote_number"
    ):

        return handle_service_selection(
            phone=phone,
            text=text_clean,
            employee=employee,
            session=session,
        )

    # ========================================================
    # 4. TÉCNICO / AYUDANTE
    # ========================================================

    if not can_create_field_report(
        employee
    ):

        return build_read_only_service_message(
            session=session,
        )

    # ========================================================
    # DESDE AQUÍ SOLO SUPERVISOR
    # ========================================================

    editing_generated_report = bool(
        session.get(
            "editing_report",
            False,
        )
    )

    # Migra sesiones locales creadas por la versión anterior, que
    # todavía esperaba una confirmación adicional de guardado.
    if session.get("status") == "awaiting_save_confirmation":
        session["status"] = "ready_to_generate"
        session["last_question_field"] = "final_confirmation"
        save_session(phone, session)

    # ========================================================
    # 5. CONFIRMACIÓN DE GUARDADO
    # ========================================================

    if (
        session.get(
            "status"
        )
        == "awaiting_save_confirmation"
    ):

        save_decision = detect_save_decision(
            text_clean
        )

        print()
        print("=" * 60)
        print(" CONFIRMACIÓN DE GUARDADO")
        print("=" * 60)

        print(
            "Mensaje:",
            text_clean,
        )

        print(
            "Decisión:",
            save_decision,
        )

        print("=" * 60)

        if save_decision == "yes":

            return save_completed_report(
                phone=phone,
                session=session,
            )

        if save_decision == "no":

            session[
                "status"
            ] = "report_generated"

            clear_question_context(
                session
            )

            save_session(
                phone,
                session,
            )

            return (
                " *Agente JCF*\n\n"
                "Perfecto. El informe *no se guardará todavía*.\n\n"
                "La información sigue disponible.\n\n"
                "Puedes indicarme qué deseas modificar "
                "o escribir *guardar* cuando esté correcto."
            )

        editing_generated_report = True

        session[
            "status"
        ] = "active"

        clear_question_context(
            session
        )

        save_session(
            phone,
            session,
        )

    elif (
        session.get(
            "status"
        )
        == "report_generated"
    ):

        save_decision = detect_save_decision(
            text_clean
        )

        if save_decision == "yes":

            return save_completed_report(
                phone=phone,
                session=session,
            )

        editing_generated_report = True

        session[
            "status"
        ] = "active"

        clear_question_context(
            session
        )

        save_session(
            phone,
            session,
        )

    elif (
        session.get(
            "status"
        )
        == "ready_to_generate"
    ):

        if is_generate_report_request(
            text_clean
        ):

            return prepare_report_for_save(
                phone=phone,
                session=session,
                title="Informe generado",
            )

        editing_generated_report = True

        session[
            "status"
        ] = "active"

        session[
            "editing_report"
        ] = True

        clear_question_context(
            session
        )

        save_session(
            phone,
            session,
        )

    # ========================================================
    # 6. RESPUESTA A OBSERVACIONES
    # ========================================================

    if (
        session.get(
            "last_question_field"
        )
        == "observaciones"
        and detect_no_observations(
            text_clean
        )
    ):

        missing_before_observations = (
            get_operational_missing(
                session.get(
                    "data",
                    {},
                )
            )
        )

        if missing_before_observations:

            session[
                "critical_missing"
            ] = missing_before_observations

            session[
                "ready_for_report"
            ] = False

            session[
                "ask_for_observations"
            ] = False

            save_session(
                phone,
                session,
            )

            return respond_with_missing_fields(
                phone=phone,
                session=session,
                preview=build_preview(
                    session=session,
                    title="Levantamiento actualizado",
                ),
                critical_missing=missing_before_observations,
                operational_missing=missing_before_observations,
                next_question="",
            )

        data = session.setdefault(
            "data",
            {},
        )

        data[
            "observaciones"
        ] = [
            "Sin observaciones adicionales"
        ]

        session[
            "ask_for_observations"
        ] = False

        session[
            "ready_for_report"
        ] = True

        session[
            "critical_missing"
        ] = []

        clear_question_context(
            session
        )

        save_session(
            phone,
            session,
        )

        return mark_report_ready_to_generate(
            phone=phone,
            session=session,
            title="Levantamiento listo",
        )

    # ========================================================
    # 7. CAMBIO DIRECTO DE SERVICIO
    # ========================================================

    change_resolution = resolve_service_change(
        text=text_clean,
        session=session,
    )

    if change_resolution.get(
        "requested"
    ):

        if change_resolution.get(
            "multiple"
        ):

            return build_ambiguous_service_message(
                change_resolution.get(
                    "services",
                    [],
                )
            )

        selected_service = (
            change_resolution.get(
                "service"
            )
        )

        if selected_service:

            active_quote = session.get(
                "quote_number"
            )

            new_quote = selected_service.get(
                "quote_number"
            )

            new_oc = selected_service.get(
                "oc"
            )

            if (
                normalize_text(
                    new_quote
                    or new_oc
                )
                == normalize_text(
                    active_quote
                    or session.get(
                        "oc"
                    )
                )
            ):

                return (
                    " *Agente JCF*\n\n"
                    f"Ya estás trabajando con "
                    f"*{new_quote or new_oc}*."
                )

            # ------------------------------------------------
            # Protección contra pérdida de levantamiento
            # ------------------------------------------------

            if has_meaningful_data(
                session.get(
                    "data",
                    {},
                )
            ):

                return (
                    " *Agente JCF*\n\n"
                    f" Actualmente estás trabajando con "
                    f"*{active_quote}* y el levantamiento "
                    "ya contiene información.\n\n"
                    f"El servicio solicitado es "
                    f"*{new_quote or new_oc}*.\n\n"
                    "Para evitar perder información, primero "
                    "finaliza o cancela el levantamiento actual."
                )

            assign_service_to_session(
                session=session,
                service=selected_service,
                reset_report=True,
            )

            save_session(
                phone,
                session,
            )

            print()
            print("=" * 70)
            print(" SERVICIO CAMBIADO")
            print("=" * 70)

            print(
                "Anterior:",
                active_quote,
            )

            print(
                "Nuevo:",
                session.get(
                    "quote_number"
                ),
            )

            print(
                "OC:",
                session.get(
                    "oc"
                ),
            )

            print(
                "Estado:",
                session.get(
                    "service_status"
                ),
            )

            print("=" * 70)

            initial_missing = get_operational_missing(
                session.get(
                    "data",
                    {},
                )
            )

            save_bulk_question_context(
                phone=phone,
                session=session,
                missing=initial_missing,
            )

            return (
                " *Agente JCF*\n\n"
                " *Servicio cambiado correctamente*\n\n"
                f"• Solicitud: *"
                f"{session.get('quote_number') or 'No informada'}*\n"
                f"• OC: *"
                f"{session.get('oc') or 'No informada'}*\n"
                f"• Estado: *"
                f"{session.get('service_status') or 'No informado'}*\n\n"
                "Ahora puedes comenzar el levantamiento "
                "para este servicio.\n\n"
                "Cuéntame qué encontraste en terreno.\n\n"
                + build_all_missing_questions(
                    critical_missing=initial_missing,
                    operational_missing=initial_missing,
                    next_question="",
                )
            )

        # Cambio solicitado sin especificar servicio.
        return show_service_list_again(
            phone=phone,
            employee=employee,
        )

    # ========================================================
    # 8. COTIZACIÓN ESCRITA SIN CAMBIO EXPLÍCITO
    # ========================================================

    detected_quote = extract_quote_number(
        text_clean
    )

    active_quote = session.get(
        "quote_number"
    )

    if detected_quote:

        matching_services = (
            find_matching_services(
                text=text_clean,
                services=session.get(
                    "available_services",
                    [],
                ),
            )
        )

        if not matching_services:

            return (
                " *Servicio no autorizado*\n\n"
                "La solicitud indicada no aparece "
                "entre tus servicios asignados."
            )

        if (
            active_quote
            and not service_identifier_matches(
                active_quote,
                detected_quote,
            )
            and has_meaningful_data(
                session.get(
                    "data",
                    {},
                )
            )
        ):

            return (
                " *Agente JCF*\n\n"
                f" Actualmente estás trabajando "
                f"con *{active_quote}*.\n\n"
                "El levantamiento ya contiene información.\n\n"
                "Si deseas abandonar esta solicitud, "
                "indícame que quieres cambiar de servicio."
            )

    # ========================================================
    # 9. FINALIZACIÓN DIRECTA
    # ========================================================

    finish_action = detect_finish_action(
        text_clean
    )

    if finish_action:

        return handle_finish_action(
            phone=phone,
            session=session,
            finish_action=finish_action,
        )

    # ========================================================
    # 10. SESIÓN VACÍA
    # ========================================================

    session_was_empty = (
        not has_meaningful_data(
            session.get(
                "data",
                {},
            )
        )
    )

    # ========================================================
    # 11. IA
    # ========================================================

    try:

        result = analyze_message(
            message=text_clean,
            session=session,
        )

    except Exception as error:

        print()
        print("=" * 70)
        print(" ERROR ANALIZANDO MENSAJE")
        print("=" * 70)

        print(
            type(error).__name__,
            str(error),
        )

        print("=" * 70)

        return (
            " *Agente JCF*\n\n"
            " No pude interpretar correctamente "
            "la información enviada.\n\n"
            "La información registrada anteriormente "
            "no se ha perdido. Intenta nuevamente."
        )

    intent = str(
        result.get(
            "intent",
            "continue_report",
        )
    ).strip()

    possible_new_job = bool(
        result.get(
            "possible_new_job",
            False,
        )
    )

    extracted_data = result.get(
        "extracted_data",
        {},
    )

    if not isinstance(
        extracted_data,
        dict,
    ):

        extracted_data = {}

    expected_fields = expected_question_fields(
        session
    )

    extracted_data = sanitize_report_data(
        extracted_data=extracted_data,
        source_message=text_clean,
        expected_fields=expected_fields,
    )

    contextual_values = extract_contextual_values(
        message=text_clean,
        expected_fields=expected_fields,
    )

    extracted_data = merge_data(
        current=extracted_data,
        new=contextual_values,
    )

    invalid_required_answer = (
        is_vague_response(
            text_clean
        )
        and not extracted_data
    )

    ai_critical_missing = normalize_list(
        result.get(
            "critical_missing"
        )
    )

    recommended_missing = normalize_list(
        result.get(
            "recommended_missing"
        )
    )

    optional_missing = normalize_list(
        result.get(
            "optional_missing"
        )
    )

    next_question = str(
        result.get(
            "next_question"
        )
        or ""
    ).strip()

    ask_for_observations = bool(
        result.get(
            "ask_for_observations",
            False,
        )
    )

    ready_for_report = bool(
        result.get(
            "ready_for_report",
            False,
        )
    )

    print()
    print("=" * 60)
    print(" ANÁLISIS IA MAESTRO")
    print("=" * 60)

    print(
        "Intención:",
        intent,
    )

    print(
        "Datos:",
        extracted_data,
    )

    print(
        "Faltantes IA:",
        ai_critical_missing,
    )

    print(
        "Siguiente pregunta IA:",
        next_question,
    )

    print("=" * 60)

    # ========================================================
    # 12. CAMBIAR SERVICIO SEGÚN IA
    # ========================================================

    if intent == "change_quote":

        return show_service_list_again(
            phone=phone,
            employee=employee,
        )

    # ========================================================
    # 13. TRABAJO PENDIENTE
    # ========================================================

    if intent == "continue_with_pending_job":

        return continue_pending_job(
            phone=phone,
            session=session,
        )

    if intent == "start_pending_new_job":

        return start_pending_job(
            phone=phone,
            session=session,
            employee=employee,
        )

    # ========================================================
    # 14. POSIBLE NUEVO TRABAJO
    # ========================================================

    if (
        possible_new_job
        and has_real_current_job(
            session
        )
    ):

        session[
            "pending_new_job"
        ] = {
            "raw_message": text_clean,
            "extracted_data": extracted_data,
        }

        clear_question_context(
            session
        )

        save_session(
            phone,
            session,
        )

        return (
            " *Agente JCF*\n\n"
            "Detecté que podrías estar hablando "
            "de un trabajo diferente.\n\n"
            "¿Qué deseas hacer?\n\n"
            "1 Agregarlo al mismo levantamiento.\n"
            "2 Finalizar este trabajo y comenzar otro."
        )

    # ========================================================
    # 15. CANCELAR
    # ========================================================

    if intent == "cancel_report":

        service_id = (
            session.get(
                "selected_service_id"
            )
            or session.get(
                "quote_number"
            )
        )

        delete_session(
            phone
        )

        return (
            " *Levantamiento cancelado*\n\n"
            f"Se canceló el levantamiento asociado "
            f"a *{service_id}*."
        )

    # ========================================================
    # 16. PAUSAR
    # ========================================================

    if intent == "pause_report":

        return process_maestro_action(
            phone=phone,
            action="maestro_back_home",
            employee=employee,
        )

    # ========================================================
    # 17. GUARDAR DATOS EXTRAÍDOS
    # ========================================================

    previous_question_field = session.get(
        "last_question_field"
    )

    session[
        "data"
    ] = merge_data(
        current=session.get(
            "data",
            {},
        ),
        new=extracted_data,
        replace_lists=(
            intent == "modify_report"
            or editing_generated_report
        ),
    )

    session[
        "editing_report"
    ] = False

    if session[
        "data"
    ].get(
        "empresa_externa_requerida"
    ) is False:

        session[
            "data"
        ].pop(
            "empresa_externa_detalle",
            None,
        )

    if (
        previous_question_field
        and field_has_value(
            data=session.get(
                "data",
                {},
            ),
            field=previous_question_field,
        )
    ):

        session[
            "last_question_field"
        ] = None

    # El bloque de preguntas anterior ya fue respondido.
    session[
        "pending_question_fields"
    ] = []

    if intent == "resume_report":

        session[
            "status"
        ] = "active"

    # ========================================================
    # 18. RECALCULAR FALTANTES
    # ========================================================

    operational_missing = (
        get_operational_missing(
            session.get(
                "data",
                {},
            )
        )
    )

    critical_missing = (
        merge_missing_lists(
            operational_missing,
            ai_critical_missing,
        )
    )

    # Filtramos faltantes que ya tengan valor.
    critical_missing = (
        filter_resolved_missing(
            missing=critical_missing,
            data=session.get(
                "data",
                {},
            ),
        )
    )

    # Python es la autoridad final. Los flags de la IA no pueden
    # declarar completo un levantamiento con datos pendientes.
    if critical_missing:

        ready_for_report = False
        ask_for_observations = False

    elif needs_observations(
        session
    ):

        ready_for_report = False
        ask_for_observations = True

    else:

        ready_for_report = True
        ask_for_observations = False

    session[
        "critical_missing"
    ] = critical_missing

    session[
        "recommended_missing"
    ] = recommended_missing

    session[
        "optional_missing"
    ] = optional_missing

    session[
        "ask_for_observations"
    ] = ask_for_observations

    session[
        "ready_for_report"
    ] = ready_for_report

    session[
        "last_intent"
    ] = intent

    save_session(
        phone,
        session,
    )

    if (
        previous_question_field == "observaciones"
        and not critical_missing
        and not needs_observations(
            session
        )
    ):

        clear_question_context(
            session
        )

        save_session(
            phone,
            session,
        )

        return mark_report_ready_to_generate(
            phone=phone,
            session=session,
            title="Levantamiento listo",
        )

    # ========================================================
    # 19. RETOMAR
    # ========================================================

    if intent == "resume_report":

        preview = build_preview(
            session=session,
            title="Levantamiento retomado",
        )

        if critical_missing:

            return respond_with_missing_fields(
                phone=phone,
                session=session,
                preview=preview,
                critical_missing=critical_missing,
                operational_missing=operational_missing,
                next_question="",
                invalid_response=invalid_required_answer,
            )

        return combine_preview(
            preview=preview,
            message=(
                "Perfecto. Retomemos el levantamiento."
            ),
        )

    # ========================================================
    # 20. MODIFICACIÓN
    # ========================================================

    if intent == "modify_report":

        if critical_missing:

            preview = build_preview(
                session=session,
                title="Informe corregido",
            )

            return respond_with_missing_fields(
                phone=phone,
                session=session,
                preview=preview,
                critical_missing=critical_missing,
                operational_missing=operational_missing,
                next_question="",
                invalid_response=invalid_required_answer,
            )

        if editing_generated_report:

            if needs_observations(
                session
            ):

                return ask_for_final_observations(
                    phone=phone,
                    session=session,
                    title="Informe corregido",
                )

            return mark_report_ready_to_generate(
                phone=phone,
                session=session,
                title="Informe corregido",
            )

    # ========================================================
    # 21. TERMINAR DESDE IA
    # ========================================================

    if intent in (
        "complete_report",
        "confirm_report",
    ):

        if critical_missing:

            preview = build_preview(
                session=session,
                title="Levantamiento actualizado",
            )

            return respond_with_missing_fields(
                phone=phone,
                session=session,
                preview=preview,
                critical_missing=critical_missing,
                operational_missing=operational_missing,
                next_question="",
                invalid_response=invalid_required_answer,
            )

        if needs_observations(
            session
        ):

            return ask_for_final_observations(
                phone=phone,
                session=session,
                title="Levantamiento actualizado",
            )

        return mark_report_ready_to_generate(
            phone=phone,
            session=session,
            title="Levantamiento listo",
        )

    # ========================================================
    # 22. INFORME MODIFICADO
    # ========================================================

    if (
        editing_generated_report
        and not critical_missing
        and not needs_observations(
            session
        )
    ):

        return mark_report_ready_to_generate(
            phone=phone,
            session=session,
            title="Informe actualizado",
        )

    # ========================================================
    # 23. PREVIEW
    # ========================================================

    if session_was_empty:

        preview_title = (
            "Levantamiento iniciado"
        )

    elif ready_for_report:

        preview_title = (
            "Levantamiento listo"
        )

    else:

        preview_title = (
            "Levantamiento actualizado"
        )

    preview = build_preview(
        session=session,
        title=preview_title,
    )

    # ========================================================
    # 24. MOSTRAR TODOS LOS FALTANTES
    # ========================================================

    if critical_missing:

        return respond_with_missing_fields(
            phone=phone,
            session=session,
            preview=preview,
            critical_missing=critical_missing,
            operational_missing=operational_missing,
            next_question="",
            invalid_response=invalid_required_answer,
        )

    # ========================================================
    # 25. OBSERVACIONES
    # ========================================================

    if (
        ask_for_observations
        or needs_observations(
            session
        )
    ):

        return ask_for_final_observations(
            phone=phone,
            session=session,
            title=preview_title,
            preview=preview,
        )

    # ========================================================
    # 26. LISTO
    # ========================================================

    if ready_for_report:
        return mark_report_ready_to_generate(
            phone=phone,
            session=session,
            title=preview_title,
        )

    # ========================================================
    # 27. PREGUNTA IA SUELTA
    # ========================================================

    if next_question:

        question_field = detect_question_field(
            next_question
        )

        save_question_context(
            phone=phone,
            session=session,
            field=question_field,
        )

        return combine_preview(
            preview=preview,
            message=next_question,
        )

    # ========================================================
    # 28. PREGUNTA FINAL
    # ========================================================

    session[
        "last_question_field"
    ] = "final_confirmation"

    session[
        "pending_question_fields"
    ] = []

    save_session(
        phone,
        session,
    )

    return combine_preview(
        preview=preview,
        message=(
            "¿Hay algún otro antecedente importante "
            "que debamos registrar?"
        ),
    )


# ============================================================
# PREPARAR SESIÓN
# ============================================================

def prepare_session(
    phone: str,
    employee: dict,
) -> dict:

    session = get_session(
        phone
    )

    current_record_id = str(
        employee.get(
            "record_id"
        )
        or ""
    ).strip()

    # ========================================================
    # CONTROL DE IMPERSONACIÓN / CAMBIO DE USUARIO
    # ========================================================

    if session:

        session_record_id = str(
            session.get(
                "employee_record_id"
            )
            or ""
        ).strip()

        if (
            session_record_id
            and current_record_id
            and session_record_id
            != current_record_id
        ):

            print()
            print("=" * 70)
            print(" CAMBIO DE USUARIO IMPERSONADO")
            print("=" * 70)

            print(
                "Sesión anterior:",
                session_record_id,
            )

            print(
                "Trabajador actual:",
                current_record_id,
            )

            print("=" * 70)

            delete_session(
                phone
            )

            session = None

    if not session:

        session = start_session(
            phone=phone,
            employee=employee,
        )

    session = initialize_session_context(
        session=session,
        employee=employee,
    )

    save_session(
        phone,
        session,
    )

    return session


# ============================================================
# INICIALIZAR CONTEXTO SESIÓN
# ============================================================

def initialize_session_context(
    session: dict,
    employee: dict,
) -> dict:

    if not isinstance(
        session,
        dict,
    ):

        session = {}

    session[
        "employee_record_id"
    ] = str(
        employee.get(
            "record_id"
        )
        or ""
    ).strip()

    session[
        "employee_name"
    ] = employee.get(
        "nombre"
    )

    session[
        "employee_position"
    ] = employee.get(
        "cargo"
    )

    session[
        "employee_phone"
    ] = employee.get(
        "telefono"
    )

    session[
        "impersonated"
    ] = bool(
        employee.get(
            "impersonated",
            False,
        )
    )

    for key, default_value in (
        SESSION_DEFAULTS.items()
    ):

        if key in session:

            continue

        if isinstance(
            default_value,
            list,
        ):

            session[
                key
            ] = list(
                default_value
            )

        elif isinstance(
            default_value,
            dict,
        ):

            session[
                key
            ] = dict(
                default_value
            )

        else:

            session[
                key
            ] = default_value

    session.pop(
        "pending_quote_selection",
        None,
    )

    # ========================================================
    # LIMPIAR POSIBLES REGISTROS GRANDES DE VERSIONES ANTIGUAS
    #
    # quote_record ya no necesita quedar dentro de la sesión.
    # El record_id es suficiente para volver a consultar
    # Airtable cuando sea necesario.
    # ========================================================

    session[
        "quote_record"
    ] = None

    services = session.get(
        "available_services",
        [],
    )

    if isinstance(
        services,
        list,
    ):

        session[
            "available_services"
        ] = [
            compact_service(
                service
            )
            for service in services
            if isinstance(
                service,
                dict,
            )
        ]

    return session


# ============================================================
# RESETEAR LEVANTAMIENTO
# ============================================================

def reset_report_state(
    session: dict,
) -> dict:

    # Pertenece al servicio anterior y nunca debe reutilizarse
    # después de cambiar la solicitud seleccionada.
    session["activity_record_id"] = None

    session[
        "data"
    ] = {}

    session[
        "critical_missing"
    ] = []

    session[
        "recommended_missing"
    ] = []

    session[
        "optional_missing"
    ] = []

    session[
        "ask_for_observations"
    ] = False

    session[
        "ready_for_report"
    ] = False

    session[
        "editing_report"
    ] = False

    session[
        "pending_new_job"
    ] = None

    session[
        "status_before_pause"
    ] = None

    session[
        "last_intent"
    ] = None

    session[
        "status"
    ] = "active"

    clear_question_context(
        session
    )

    refresh_deterministic_completion(
        session
    )

    return session


# ============================================================
# LIMPIAR CONTEXTO DE PREGUNTAS
# ============================================================

def clear_question_context(
    session: dict,
):

    session[
        "last_question_field"
    ] = None

    session[
        "pending_question_fields"
    ] = []


# ============================================================
# COMPACTAR SERVICIO
#
# Evitamos guardar "record" y "fields" completos dentro de
# la sesión. Con muchos servicios esto reducía muchísimo
# el contexto enviado posteriormente a OpenAI.
# ============================================================

def compact_service(
    service: dict,
) -> dict:

    if not isinstance(
        service,
        dict,
    ):

        return {}

    status = (
        service.get(
            "status_label"
        )
        or service.get(
            "service_status"
        )
    )

    raw_status = service.get(
        "status"
    )

    if not status:

        if isinstance(
            raw_status,
            str,
        ):

            status = raw_status

    return {
        "record_id": service.get(
            "record_id"
        ),

        "quote_number": service.get(
            "quote_number"
        ),

        "oc": service.get(
            "oc"
        ),

        "status_label": status,

        "service_type": service.get(
            "service_type"
        ),

        # Solamente conservamos raw status si es texto.
        "status": (
            raw_status
            if isinstance(
                raw_status,
                str,
            )
            else None
        ),
    }


# ============================================================
# ASIGNAR SERVICIO A SESIÓN
# ============================================================

def assign_service_to_session(
    session: dict,
    service: dict,
    reset_report: bool = False,
) -> dict:

    if reset_report:

        reset_report_state(
            session
        )

    quote_number = service.get(
        "quote_number"
    )

    oc = service.get(
        "oc"
    )

    status = (
        service.get(
            "status_label"
        )
        or service.get(
            "status"
        )
        or "No informado"
    )

    if isinstance(
        status,
        list,
    ):

        status = (
            service.get(
                "status_label"
            )
            or "No informado"
        )

    session[
        "quote_number"
    ] = quote_number

    session[
        "selected_service_id"
    ] = (
        quote_number
        or oc
    )

    session[
        "oc"
    ] = oc

    session[
        "service_status"
    ] = str(
        status
    ).strip()

    session[
        "quote_record_id"
    ] = service.get(
        "record_id"
    )

    # No almacenamos el record completo.
    session[
        "quote_record"
    ] = None

    session[
        "status"
    ] = "active"

    clear_question_context(
        session
    )

    return session


# ============================================================
# RESETEAR A SELECCIÓN DE SERVICIO
# ============================================================

def reset_to_service_selection(
    phone: str,
    employee: dict,
) -> dict:

    delete_session(
        phone
    )

    session = start_session(
        phone=phone,
        employee=employee,
    )

    session = initialize_session_context(
        session=session,
        employee=employee,
    )

    save_session(
        phone,
        session,
    )

    return session


# ============================================================
# MOSTRAR LISTA NUEVAMENTE
# ============================================================

def show_service_list_again(
    phone: str,
    employee: dict,
) -> str:

    reset_to_service_selection(
        phone=phone,
        employee=employee,
    )

    return process_field_report_message(
        phone=phone,
        text="mis servicios",
        employee=employee,
    )


# ============================================================
# SELECCIÓN INICIAL DE SERVICIO
# ============================================================

def handle_service_selection(
    phone: str,
    text: str,
    employee: dict,
    session: dict,
) -> str:

    requested_status = (
        detect_requested_service_status(
            text
        )
    )

    available_services = session.get(
        "available_services",
        [],
    )

    is_numeric_selection = bool(
        re.fullmatch(
            r"\s*\d+\s*",
            text,
        )
    )

    should_reuse_services = (
        is_numeric_selection
        and isinstance(
            available_services,
            list,
        )
        and bool(
            available_services
        )
    )

    # ========================================================
    # REUTILIZAR LISTA
    # ========================================================

    if should_reuse_services:

        services = available_services

        print()
        print("=" * 70)
        print(" REUTILIZANDO SERVICIOS DE LA SESIÓN")
        print("=" * 70)

        print(
            "Cantidad:",
            len(
                services
            ),
        )

        print("=" * 70)

    # ========================================================
    # CONSULTAR AIRTABLE
    # ========================================================

    else:

        print()
        print("=" * 70)
        print(" CONSULTANDO SERVICIOS EN AIRTABLE")
        print("=" * 70)

        print(
            "Trabajador:",
            employee.get(
                "nombre"
            ),
        )

        print(
            "Cargo:",
            employee.get(
                "cargo"
            ),
        )

        print(
            "Estado:",
            requested_status
            or "OPERATIVOS",
        )

        print("=" * 70)

        try:

            if requested_status == "PROGRAMADO":

                result = (
                    get_programmed_services_for_employee(
                        employee
                    )
                )

            elif requested_status == "ACTIVO":

                result = (
                    get_active_services_for_employee(
                        employee
                    )
                )

            elif requested_status == "PAUSADO":

                result = (
                    get_paused_services_for_employee(
                        employee
                    )
                )

            else:

                result = (
                    get_operational_services_for_employee(
                        employee
                    )
                )

        except Exception as error:

            print()
            print("=" * 70)
            print(" ERROR BUSCANDO SERVICIOS")
            print("=" * 70)

            print(
                type(error).__name__,
                str(error),
            )

            print("=" * 70)

            return (
                " *Agente JCF*\n\n"
                " No pude consultar tus servicios "
                "en este momento.\n\n"
                "Intenta nuevamente."
            )

        raw_services = result.get(
            "records",
            [],
        )

        if not isinstance(
            raw_services,
            list,
        ):

            raw_services = []

        # Los levantamientos solamente corresponden a
        # servicios cuyo Tipo de Servicio sea Cotización.
        raw_services = [
            service
            for service in raw_services
            if normalize_text(
                service.get(
                    "service_type"
                )
            ) == "cotizacion"
        ]

        services = [
            compact_service(
                service
            )
            for service in raw_services
        ]

        # IMPORTANTE:
        # guardamos solamente la versión compacta.
        session[
            "available_services"
        ] = services

        session[
            "requested_service_status"
        ] = requested_status

        save_session(
            phone,
            session,
        )

    print()
    print("=" * 70)
    print(" RESULTADO SERVICIOS")
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
            "| OC:",
            service.get(
                "oc"
            ),
            "| Estado:",
            service.get(
                "status_label"
            ),
        )

    print("=" * 70)

    # ========================================================
    # SERVICIO SELECCIONADO
    # ========================================================

    selected_service = find_selected_service(
        text=text,
        services=services,
    )

    if selected_service:

        assign_service_to_session(
            session=session,
            service=selected_service,
            reset_report=True,
        )

        save_session(
            phone,
            session,
        )

        quote_number = session.get(
            "quote_number"
        )

        oc = session.get(
            "oc"
        )

        service_status = session.get(
            "service_status"
        )

        print()
        print("=" * 70)
        print(" SERVICIO SELECCIONADO")
        print("=" * 70)

        print(
            "Solicitud:",
            quote_number,
        )

        print(
            "OC:",
            oc,
        )

        print(
            "Estado:",
            service_status,
        )

        print(
            "Record ID:",
            session.get(
                "quote_record_id"
            ),
        )

        print("=" * 70)

        if not can_create_field_report(
            employee
        ):

            return (
                " *Agente JCF*\n\n"
                " Servicio seleccionado.\n\n"
                f"• Solicitud: *"
                f"{quote_number or 'No informada'}*\n"
                f"• OC: *"
                f"{oc or 'No informada'}*\n"
                f"• Estado: *"
                f"{service_status or 'No informado'}*\n\n"
                "Puedes consultar este servicio.\n\n"
                " Solamente un Supervisor puede "
                "crear o modificar un levantamiento."
            )

        initial_missing = get_operational_missing(
            session.get(
                "data",
                {},
            )
        )

        save_bulk_question_context(
            phone=phone,
            session=session,
            missing=initial_missing,
        )

        return (
            " *Agente JCF*\n\n"
            f" Seleccionaste *"
            f"{quote_number or oc}*.\n\n"
            f"• Estado: *"
            f"{service_status or 'No informado'}*\n\n"
            "El servicio está asignado a ti.\n\n"
            "Puedes comenzar el levantamiento.\n\n"
            "Cuéntame todo lo que encontraste en terreno. "
            "Puedes hacerlo por texto o enviarme un audio.\n\n"
            + build_all_missing_questions(
                critical_missing=initial_missing,
                operational_missing=initial_missing,
                next_question="",
            )
        )

    # ========================================================
    # SIN SERVICIOS
    # ========================================================

    if not services:

        if requested_status:

            return (
                " *Agente JCF*\n\n"
                "No tienes servicios "
                f"*{requested_status}* "
                "asignados actualmente."
            )

        return (
            " *Agente JCF*\n\n"
            "No tienes servicios operativos "
            "asignados actualmente."
        )

    return build_services_message(
        employee=employee,
        services=services,
        requested_status=requested_status,
    )


# ============================================================
# MANEJAR FINALIZACIÓN
# ============================================================

def enforce_report_completion_gate(
    phone: str,
    session: dict,
    title: str,
):

    missing = refresh_deterministic_completion(
        session
    )

    save_session(
        phone,
        session,
    )

    if missing:

        return respond_with_missing_fields(
            phone=phone,
            session=session,
            preview=build_preview(
                session=session,
                title=title,
            ),
            critical_missing=missing,
            operational_missing=missing,
            next_question="",
        )

    if needs_observations(
        session
    ):

        return ask_for_final_observations(
            phone=phone,
            session=session,
            title=title,
        )

    return None

def handle_finish_action(
    phone: str,
    session: dict,
    finish_action: str,
) -> str:

    blocked_response = enforce_report_completion_gate(
        phone=phone,
        session=session,
        title="Levantamiento actualizado",
    )

    if blocked_response:

        return blocked_response

    return mark_report_ready_to_generate(
        phone=phone,
        session=session,
        title="Levantamiento listo",
    )


def process_maestro_action(
    phone: str,
    action: str,
    employee: dict,
) -> str:

    session = get_session(
        phone
    )

    if not isinstance(
        session,
        dict,
    ):

        return (
            " *Agente JCF*\n\n"
            "No existe un levantamiento activo para esta acción."
        )

    if not can_create_field_report(
        employee
    ):

        return (
            " *Acción no autorizada*\n\n"
            "Tu cargo no puede modificar levantamientos."
        )

    action = str(
        action
        or ""
    ).strip()

    if action == "maestro_back_home":

        if session.get(
            "status"
        ) != "paused":

            session[
                "status_before_pause"
            ] = session.get(
                "status"
            ) or "active"

        session[
            "status"
        ] = "paused"

        save_session(
            phone,
            session,
        )

        return (
            " *Menú principal JCF*\n\n"
            "El levantamiento quedó pausado de forma segura. "
            "La solicitud, respuestas, imágenes, audios procesados "
            "y preguntas pendientes se conservaron.\n\n"
            "Cuando quieras continuar, escribe "
            "*retomar levantamiento*."
        )

    if action == "maestro_no_observations":

        if session.get(
            "last_question_field"
        ) != "observaciones":

            return (
                " *Agente JCF*\n\n"
                "La pregunta de observaciones ya no está activa."
            )

        return process_field_report_message(
            phone=phone,
            text="No tengo observaciones",
            employee=employee,
        )

    if action == "maestro_report_modify":

        if session.get(
            "status"
        ) not in (
            "ready_to_generate",
            "report_generated",
            "awaiting_save_confirmation",
        ):

            return (
                " *Agente JCF*\n\n"
                "El informe todavía no está en una etapa modificable."
            )

        session[
            "status"
        ] = "active"

        session[
            "editing_report"
        ] = True

        clear_question_context(
            session
        )

        save_session(
            phone,
            session,
        )

        return (
            " *Modificar informe*\n\n"
            "Indícame por texto o audio qué información deseas cambiar. "
            "El resto del levantamiento se conservará."
        )

    if action == "maestro_report_generate":

        if session.get("status") == "saving_report":
            return (
                "⏳ *Guardado en curso*\n\n"
                "El informe ya se está guardando."
            )

        if session.get(
            "status"
        ) not in (
            "ready_to_generate",
            "report_generated",
            "awaiting_save_confirmation",
        ):

            return enforce_report_completion_gate(
                phone=phone,
                session=session,
                title="Levantamiento actualizado",
            ) or (
                " *Agente JCF*\n\n"
                "El levantamiento todavía no está listo para generar."
            )

        return save_completed_report(
            phone=phone,
            session=session,
        )

    return (
        " *Agente JCF*\n\n"
        "La acción seleccionada ya no está disponible."
    )


def has_preserved_report_progress(
    session: dict,
) -> bool:

    if not isinstance(
        session,
        dict,
    ):

        return False

    data = session.get(
        "data",
        {},
    )

    images = (
        data.get(
            "imagenes",
            [],
        )
        if isinstance(
            data,
            dict,
        )
        else []
    )

    return bool(
        has_meaningful_data(
            data
        )
        or images
    )


# ============================================================
# CAMBIO DE SERVICIO
# ============================================================

def resolve_service_change(
    text: str,
    session: dict,
) -> dict:

    if not is_service_change_request(
        text
    ):

        return {
            "requested": False,
        }

    services = session.get(
        "available_services",
        [],
    )

    matches = find_matching_services(
        text=text,
        services=services,
    )

    if len(
        matches
    ) == 1:

        return {
            "requested": True,
            "multiple": False,
            "service": matches[0],
        }

    if len(
        matches
    ) > 1:

        return {
            "requested": True,
            "multiple": True,
            "services": matches,
        }

    return {
        "requested": True,
        "multiple": False,
        "service": None,
    }


# ============================================================
# BUSCAR SERVICIOS QUE COINCIDEN
# ============================================================

def find_matching_services(
    text: str,
    services: list,
) -> list:

    if not isinstance(
        services,
        list,
    ):

        return []

    normalized_message = normalize_text(
        text
    )

    # ========================================================
    # 1. COINCIDENCIA EXACTA CON ID COMPLETO
    # ========================================================

    exact_matches = []

    for service in services:

        quote = normalize_text(
            service.get(
                "quote_number"
            )
            or ""
        )

        oc = normalize_text(
            service.get(
                "oc"
            )
            or ""
        )

        if (
            quote
            and quote in normalized_message
        ):

            exact_matches.append(
                service
            )

        elif (
            oc
            and oc in normalized_message
        ):

            exact_matches.append(
                service
            )

    if exact_matches:

        return remove_duplicate_services(
            exact_matches
        )

    # ========================================================
    # 2. CÓDIGO COTXXXX
    # ========================================================

    match = re.search(
        r"\bcot\s*(\d{3,})\b",
        normalized_message,
    )

    if not match:

        return []

    requested_code = (
        f"cot{match.group(1)}"
    )

    matches = []

    for service in services:

        quote = normalize_text(
            service.get(
                "quote_number"
            )
            or ""
        )

        if (
            quote
            and quote.startswith(
                requested_code
            )
        ):

            matches.append(
                service
            )

    return remove_duplicate_services(
        matches
    )


# ============================================================
# COMPATIBILIDAD:
# BUSCAR UN SERVICIO EN EL MENSAJE
# ============================================================

def find_service_in_message(
    text: str,
    services: list,
):

    matches = find_matching_services(
        text=text,
        services=services,
    )

    if len(
        matches
    ) == 1:

        return matches[
            0
        ]

    return None


# ============================================================
# ELIMINAR SERVICIOS DUPLICADOS
# ============================================================

def remove_duplicate_services(
    services: list,
) -> list:

    result = []
    seen = set()

    for service in services:

        record_id = str(
            service.get(
                "record_id"
            )
            or ""
        ).strip()

        if record_id:

            key = (
                "record",
                record_id,
            )

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
            )

        if key in seen:

            continue

        seen.add(
            key
        )

        result.append(
            service
        )

    return result


# ============================================================
# MENSAJE DE AMBIGÜEDAD
# ============================================================

def build_ambiguous_service_message(
    services: list,
) -> str:

    lines = [
        " *Agente JCF*",
        "",
        "Encontré más de un servicio que coincide.",
        "",
        "Indícame exactamente cuál deseas utilizar:",
        "",
    ]

    for index, service in enumerate(
        services,
        start=1,
    ):

        quote = (
            service.get(
                "quote_number"
            )
            or "Sin solicitud"
        )

        oc = service.get(
            "oc"
        )

        line = (
            f"*{index}.* *{quote}*"
        )

        if oc:

            line += (
                f" — OC: {oc}"
            )

        lines.append(
            line
        )

    lines.extend(
        [
            "",
            (
                "Escribe el identificador completo "
                "del servicio que deseas utilizar."
            ),
        ]
    )

    return "\n".join(
        lines
    )


# ============================================================
# DETECTAR SOLICITUD DE CAMBIO
# ============================================================

def is_service_change_request(
    text: str,
) -> bool:

    value = normalize_text(
        text
    )

    explicit_service_phrases = (
        "cambiar la oc",
        "cambia la oc",
        "cambiar oc",
        "cambia oc",
        "cambiar servicio",
        "cambia el servicio",
        "cambiar de servicio",
        "cambiar solicitud",
        "cambia la solicitud",
        "cambiar cotizacion",
        "cambia la cotizacion",
        "otra cotizacion",
        "otra solicitud",
        "otra oc",
        "esa no era",
        "esa no corresponde",
        "me equivoque de cotizacion",
        "me equivoque de solicitud",
        "me equivoque de oc",
        "volver a mis servicios",
        "volver a la lista",
    )

    if any(
        phrase in value
        for phrase in explicit_service_phrases
    ):
        return True

    # Verbos como "cambiar" también describen el trabajo técnico
    # (por ejemplo, cambiar un portón o sus bisagras). Solo se
    # interpretan como cambio de solicitud cuando vienen acompañados
    # por un identificador concreto de servicio.
    has_target_service = bool(
        re.search(
            r"\b(?:cot|oc)\s*[-:]?\s*\d{3,}\b",
            value,
        )
    )

    if not has_target_service:
        return False

    targeted_change_phrases = (
        "cambia a",
        "cambiar a",
        "quiero cambiar a",
        "quiero trabajar con",
        "trabajemos con",
        "pasemos a",
        "pasar a",
        "vamos con",
        "mejor usa",
        "usar otra",
        "utilizar otra",
    )

    return any(
        phrase in value
        for phrase in targeted_change_phrases
    )


# ============================================================
# REFERENCIA ESPECÍFICA DE SERVICIO
# ============================================================

def has_specific_service_reference(
    text: str,
) -> bool:

    value = normalize_text(
        text
    )

    return bool(
        re.search(
            r"\bcot\s*\d{3,}\b",
            value,
        )
    )


# ============================================================
# COMPARAR IDENTIFICADORES
# ============================================================

def service_identifier_matches(
    first,
    second,
) -> bool:

    first_value = normalize_text(
        first
    )

    second_value = normalize_text(
        second
    )

    if not first_value or not second_value:

        return False

    if first_value == second_value:

        return True

    first_base = extract_base_quote(
        first_value
    )

    second_base = extract_base_quote(
        second_value
    )

    return bool(
        first_base
        and second_base
        and first_base == second_base
    )


# ============================================================
# EXTRAER COT BASE
# ============================================================

def extract_base_quote(
    value,
):

    text = normalize_text(
        value
    )

    match = re.search(
        r"\bcot\s*(\d{3,})\b",
        text,
    )

    if not match:

        return None

    return (
        f"cot{match.group(1)}"
    )


# ============================================================
# BUSCAR SERVICIO SELECCIONADO
# ============================================================

def find_selected_service(
    text: str,
    services: list,
):

    if not services:

        return None

    number_match = re.fullmatch(
        r"\s*(\d+)\s*",
        str(
            text
        ),
    )

    if number_match:

        index = (
            int(
                number_match.group(
                    1
                )
            )
            - 1
        )

        if (
            0 <= index < len(
                services
            )
        ):

            return services[
                index
            ]

    matches = find_matching_services(
        text=text,
        services=services,
    )

    if len(
        matches
    ) == 1:

        return matches[
            0
        ]

    return None


# ============================================================
# DETECTAR ESTADO SOLICITADO
# ============================================================

def detect_requested_service_status(
    text: str,
):

    value = normalize_text(
        text
    )

    programmed_words = (
        "programado",
        "programados",
        "programada",
        "programadas",
        "programacion",
    )

    if any(
        word in value
        for word in programmed_words
    ):

        return "PROGRAMADO"

    active_words = (
        "activo",
        "activos",
        "activa",
        "activas",
        "en ejecucion",
        "en curso",
    )

    if any(
        word in value
        for word in active_words
    ):

        return "ACTIVO"

    paused_words = (
        "pausado",
        "pausados",
        "pausada",
        "pausadas",
        "detenido",
        "detenidos",
        "pendiente de continuar",
    )

    if any(
        word in value
        for word in paused_words
    ):

        return "PAUSADO"

    return None


# ============================================================
# EXPLICAR ESTADOS OPERATIVOS
# ============================================================

def get_operational_status_explanation(
    text: str,
):

    value = normalize_text(
        text
    )

    asks_meaning = any(
        phrase in value
        for phrase in (
            "que significa",
            "que quiere decir",
            "que es un servicio",
            "que es el estado",
            "explicame",
            "en que consiste",
            "por que aparece",
            "para que sirve",
        )
    )

    if not asks_meaning:

        return None

    if "programado" in value:

        return (
            " *Agente JCF*\n\n"
            "*PROGRAMADO*\n\n"
            "Un servicio PROGRAMADO ya tiene definida "
            "su programación para poder realizarse.\n\n"
            "En esta etapa se consideran antecedentes como:\n\n"
            "• Fecha de programación\n"
            "• Técnico asignado\n"
            "• Supervisor asignado\n"
            "• Ayudante, cuando corresponde\n"
            "• Permisos necesarios\n"
            "• Herramientas\n"
            "• Materiales\n\n"
            "Es el paso previo a comenzar la ejecución "
            "del servicio."
        )

    if "activo" in value:

        return (
            " *Agente JCF*\n\n"
            "*ACTIVO*\n\n"
            "Un servicio ACTIVO es un servicio cuya "
            "ejecución ya se encuentra en desarrollo.\n\n"
            "El trabajo ya comenzó y está siendo "
            "atendido operativamente."
        )

    if "pausado" in value:

        return (
            " *Agente JCF*\n\n"
            "*PAUSADO*\n\n"
            "Un servicio PAUSADO es un trabajo que comenzó "
            "pero quedó temporalmente pendiente de continuar.\n\n"
            "Por ejemplo, si no logra terminarse durante "
            "la jornada programada y debe continuar otro día, "
            "puede quedar pausado y posteriormente reprogramarse."
        )

    restricted_statuses = (
        "ingresado",
        "ejecutado",
        "enviado",
        "validado",
        "validados",
        "facturado",
        "pagado",
    )

    if any(
        status in value
        for status in restricted_statuses
    ):

        return (
            " *Agente JCF*\n\n"
            "Ese estado corresponde a otra etapa del "
            "proceso administrativo del servicio.\n\n"
            "Desde este módulo puedo ayudarte con los "
            "estados operativos disponibles para trabajadores:\n\n"
            "• PROGRAMADO\n"
            "• ACTIVO\n"
            "• PAUSADO"
        )

    return None


# ============================================================
# MENSAJE DE SERVICIOS
# ============================================================

def build_services_message(
    employee: dict,
    services: list,
    requested_status=None,
) -> str:

    if not services:

        return (
            " *Agente JCF*\n\n"
            "No encontré servicios operativos "
            "asignados actualmente."
        )

    name = first_name(
        employee.get(
            "nombre"
        )
    )

    lines = [
        " *Agente JCF*",
        "",
        f"Hola {name} ",
        "",
    ]

    if requested_status:

        count = len(
            services
        )

        plural = {
            "PROGRAMADO": (
                "servicio PROGRAMADO"
                if count == 1
                else "servicios PROGRAMADOS"
            ),

            "ACTIVO": (
                "servicio ACTIVO"
                if count == 1
                else "servicios ACTIVOS"
            ),

            "PAUSADO": (
                "servicio PAUSADO"
                if count == 1
                else "servicios PAUSADOS"
            ),
        }

        description = plural.get(
            requested_status,
            (
                f"servicio {requested_status}"
                if count == 1
                else f"servicios {requested_status}"
            ),
        )

        if count == 1:

            lines.append(
                f"Tienes *1 {description}* asignado:"
            )

        else:

            lines.append(
                f"Tienes *{count} {description}* asignados:"
            )

        lines.append(
            ""
        )

        for index, service in enumerate(
            services,
            start=1,
        ):

            append_service_line(
                lines=lines,
                index=index,
                service=service,
            )

    else:

        lines.append(
            "Estos son tus servicios operativos asignados:"
        )

        lines.append(
            ""
        )

        index = 1

        for status, title in (
            (
                "programado",
                "PROGRAMADOS",
            ),
            (
                "activo",
                "ACTIVOS",
            ),
            (
                "pausado",
                "PAUSADOS",
            ),
        ):

            filtered = [
                service
                for service in services
                if normalize_text(
                    service.get(
                        "status_label"
                    )
                    or service.get(
                        "status"
                    )
                )
                == status
            ]

            if not filtered:

                continue

            lines.append(
                f"*{title}*"
            )

            for service in filtered:

                append_service_line(
                    lines=lines,
                    index=index,
                    service=service,
                )

                index += 1

            lines.append(
                ""
            )

    lines.extend(
        [
            "",
            (
                "Marca el número que corresponde a la COT "
                "o escribe la COT que quieres trabajar."
            ),
        ]
    )

    if not can_create_field_report(
        employee
    ):

        lines.extend(
            [
                "",
                (
                    " Puedes consultar tus servicios. "
                    "Los levantamientos solamente pueden "
                    "ser creados o modificados por un Supervisor."
                ),
            ]
        )

    return "\n".join(
        lines
    )


# ============================================================
# AGREGAR SERVICIO A MENSAJE
# ============================================================

def append_service_line(
    lines: list,
    index: int,
    service: dict,
):

    quote = (
        service.get(
            "quote_number"
        )
        or "Sin ID"
    )

    oc = (
        service.get(
            "oc"
        )
        or ""
    )

    line = (
        f"*{index}.* *{quote}*"
    )

    if oc:

        line += (
            f" — OC: {oc}"
        )

    lines.append(
        line
    )


# ============================================================
# COMPATIBILIDAD
# ============================================================

def build_programmed_services_message(
    employee: dict,
    services: list,
) -> str:

    return build_services_message(
        employee=employee,
        services=services,
        requested_status="PROGRAMADO",
    )


# ============================================================
# MENSAJE SOLO LECTURA
# ============================================================

def build_read_only_service_message(
    session: dict,
) -> str:

    quote = (
        session.get(
            "quote_number"
        )
        or "No informada"
    )

    oc = (
        session.get(
            "oc"
        )
        or "No informada"
    )

    status = session.get(
        "service_status"
    )

    if (
        not status
        or isinstance(
            status,
            list,
        )
    ):

        status = "No informado"

    return (
        " *Agente JCF*\n\n"
        f"Servicio seleccionado: *{quote}*\n"
        f"OC: *{oc}*\n"
        f"Estado: *{status}*\n\n"
        "Tu perfil tiene acceso de consulta.\n"
        "Los levantamientos solamente pueden ser creados "
        "o modificados por un Supervisor.\n\n"
        "Puedes escribir:\n"
        "• *mis servicios programados*\n"
        "• *mis servicios activos*\n"
        "• *mis servicios pausados*\n"
        "• *mis servicios*"
    )


# ============================================================
# QUIERE VER LISTA
# ============================================================

def wants_service_list(
    text: str,
) -> bool:

    value = normalize_text(
        text
    )

    phrases = (
        "mis servicios",
        "mis servicios programados",
        "mis servicios activos",
        "mis servicios pausados",
        "ver mis servicios",
        "ver servicios",
        "mostrar mis servicios",
        "mostrar servicios",
        "muestrame mis servicios",
        "cuales son mis servicios",
        "que servicios tengo",
        "servicios asignados",
        "otra oc",
        "otra solicitud",
        "otra cotizacion",
        "cambiar servicio",
        "cambiar de servicio",
        "volver a mis servicios",
        "volver a la lista",
    )

    return any(
        phrase in value
        for phrase in phrases
    )


# ============================================================
# OBSERVACIONES
# ============================================================

def detect_no_observations(
    text: str,
) -> bool:

    normalized = normalize_text(
        text
    )

    values = {
        "no",
        "n",
        "ninguna",
        "ninguno",
        "nada",
        "nada mas",
        "no nada mas",
        "no hay nada mas",
        "no tengo nada mas",
        "no tengo mas",
        "sin observaciones",
        "sin observacion",
        "ninguna observacion",
        "ninguna observacion adicional",
        "no tengo observaciones",
        "no tengo observacion",
        "no tengo ninguna observacion",
        "no quiero agregar nada",
        "no quiero agregar nada mas",
        "no necesito agregar nada",
        "no necesito agregar nada mas",
        "eso es todo",
        "eso seria todo",
        "seria todo",
        "listo",
        "todo listo",
        "esta bien asi",
        "esta correcto asi",
        "dejalo asi",
        "dejarlo asi",
    }

    if normalized in values:

        return True

    return (
        "sin observacion" in normalized
        or "no tengo observacion" in normalized
        or "ninguna observacion" in normalized
    )


# ============================================================
# DETECTAR FINALIZACIÓN
# ============================================================

def is_generate_report_request(
    text: str,
) -> bool:

    return normalize_text(
        text
    ) in {
        "generar informe",
        "genera el informe",
        "generar el informe",
        "crear informe",
        "crear el informe",
    }


def is_resume_report_request(
    text: str,
) -> bool:

    return normalize_text(
        text
    ) in {
        "retomar",
        "reanudar",
        "continuar levantamiento",
        "retomar levantamiento",
        "reanudar levantamiento",
    }

def detect_finish_action(
    text: str,
):

    normalized = normalize_text(
        text
    )

    save_phrases = (
        "registralo",
        "registrar informe",
        "registra el informe",
        "registra todo",
        "puedes registrarlo",
        "quiero registrarlo",
        "guardalo",
        "guardar informe",
        "guarda el informe",
        "guarda todo",
        "puedes guardarlo",
        "quiero guardarlo",
        "confirmalo",
        "confirmar informe",
        "confirma el informe",
        "todo ok registralo",
        "todo ok guardalo",
        "todo bien registralo",
        "todo bien guardalo",
        "todo correcto registralo",
        "todo correcto guardalo",
        "esta correcto registralo",
        "esta correcto guardalo",
        "nada registralo",
        "nada guardalo",
        "no falta nada registralo",
        "no falta nada guardalo",
        "eso es todo registralo",
        "eso es todo guardalo",
        "eso seria todo registralo",
        "eso seria todo guardalo",
        "termine registralo",
        "termine guardalo",
        "ya termine registralo",
        "ya termine guardalo",
        "finalice registralo",
        "finalice guardalo",
        "listo registralo",
        "listo guardalo",
        "todo listo registralo",
        "todo listo guardalo",
        "procede a guardar",
        "procede a registrar",
    )

    for phrase in save_phrases:

        if phrase in normalized:

            return "save"

    finish_phrases = {
        "cerrar",
        "cierra",
        "finalizar",
        "finaliza",
        "terminar",
        "termina",
        "termine",
        "ya termine",
        "he terminado",
        "hemos terminado",
        "terminamos",
        "ya terminamos",
        "terminado",
        "finalice",
        "ya finalice",
        "hemos finalizado",
        "finalizamos",
        "finalizado",
        "listo",
        "todo listo",
        "esta listo",
        "ya esta listo",
        "eso es todo",
        "eso seria todo",
        "seria todo",
        "no hay nada mas",
        "no falta nada",
        "nada mas",
        "ningun dato mas",
        "ningun antecedente mas",
        "no tengo nada mas",
        "no necesito agregar nada",
        "no necesito agregar nada mas",
        "puedes cerrar",
        "puedes finalizar",
        "puedes terminar",
        "cierra el levantamiento",
        "cerrar levantamiento",
        "cerrar informe",
        "terminar levantamiento",
        "terminar informe",
        "finalizar levantamiento",
        "finalizar informe",
        "ya esta",
        "esta completo",
        "todo completo",
        "completo",
        "todo ok",
        "todo bien",
        "todo correcto",
    }

    if normalized in finish_phrases:

        return "finish"

    return None


# ============================================================
# PREPARAR INFORME
# ============================================================

def mark_report_ready_to_generate(
    phone: str,
    session: dict,
    title: str = "Levantamiento listo",
) -> str:

    blocked_response = enforce_report_completion_gate(
        phone=phone,
        session=session,
        title=title,
    )

    if blocked_response:

        return blocked_response

    session[
        "status"
    ] = "ready_to_generate"

    session[
        "ready_for_report"
    ] = True

    session[
        "ask_for_observations"
    ] = False

    session[
        "editing_report"
    ] = False

    session[
        "last_question_field"
    ] = "final_confirmation"

    session[
        "pending_question_fields"
    ] = []

    save_session(
        phone,
        session,
    )

    return combine_preview(
        preview=build_preview(
            session=session,
            title=title,
        ),
        message=(
            "Todos los antecedentes y las observaciones están resueltos.\n\n"
            "Puedes modificar la información o generar el informe. "
            "Todavía no se ha guardado nada."
        ),
    )


def prepare_report_for_save(
    phone: str,
    session: dict,
    title: str = "Informe generado",
) -> str:

    return save_completed_report(
        phone=phone,
        session=session,
    )


# ============================================================
# GUARDAR INFORME
# ============================================================

def save_completed_report(
    phone: str,
    session: dict,
) -> str:

    employee_for_permission = {
        "cargo": session.get(
            "employee_position"
        ),
    }

    if not can_save_field_report(
        employee_for_permission
    ):

        return (
            " *Acción no autorizada*\n\n"
            "Solamente un Supervisor puede "
            "guardar levantamientos."
        )

    if session.get("status") == "saving_report":
        return (
            "⏳ *Guardado en curso*\n\n"
            "El informe ya se está guardando. No es necesario "
            "pulsar Generar informe nuevamente."
        )

    blocked_response = enforce_report_completion_gate(
        phone=phone,
        session=session,
        title="Levantamiento actualizado",
    )

    if blocked_response:

        return blocked_response

    quote_number = session.get(
        "quote_number"
    )

    quote_record_id = session.get(
        "quote_record_id"
    )

    activity_record_id = session.get(
        "activity_record_id"
    )

    service_id = (
        session.get(
            "selected_service_id"
        )
        or quote_number
    )

    if not quote_number:

        return (
            " No pude guardar el informe "
            "porque no tiene una solicitud asociada."
        )

    # Evita escrituras simultáneas del mismo levantamiento.
    session["status"] = "saving_report"
    save_session(phone, session)

    # ========================================================
    # RECUPERAR RECORD ID SI FALTA
    # ========================================================

    if not quote_record_id:

        try:

            quote_result = get_quote(
                quote_number
            )

        except Exception as error:

            print(
                " Error recuperando solicitud:",
                type(error).__name__,
                str(error),
            )

            return preserve_save_state(
                phone=phone,
                session=session,
                message=(
                    " No pude localizar nuevamente "
                    "la solicitud en Airtable.\n\n"
                    "La información del levantamiento "
                    "no se ha perdido."
                ),
            )

        if not quote_result.get(
            "found"
        ):

            return preserve_save_state(
                phone=phone,
                session=session,
                message=(
                    " La solicitud asociada al levantamiento "
                    "ya no fue encontrada en Airtable.\n\n"
                    "La información no se ha perdido."
                ),
            )

        if quote_result.get(
            "multiple"
        ):

            return preserve_save_state(
                phone=phone,
                session=session,
                message=(
                    " La solicitud aparece duplicada "
                    "en Airtable.\n\n"
                    "El informe no se guardó para evitar "
                    "escribir en un registro incorrecto."
                ),
            )

        quote_record_id = quote_result.get(
            "record_id"
        )

        record = quote_result.get(
            "record"
        )

        if (
            not quote_record_id
            and isinstance(
                record,
                dict,
            )
        ):

            quote_record_id = record.get(
                "id"
            )

        if not quote_record_id:

            return preserve_save_state(
                phone=phone,
                session=session,
                message=(
                    " Encontré la solicitud, pero "
                    "no pude obtener su identificador "
                    "interno de Airtable."
                ),
            )

        real_service_id = get_service_id_from_record(
            record
        )

        if real_service_id:

            service_id = real_service_id

        session[
            "quote_record_id"
        ] = quote_record_id

        session[
            "selected_service_id"
        ] = service_id

        # No almacenamos record completo.
        session[
            "quote_record"
        ] = None

        save_session(
            phone,
            session,
        )

    report_text = build_preview(
        session=session,
        title="Informe de levantamiento",
    )

    print()
    print("=" * 60)
    print(" GUARDANDO INFORME EN AIRTABLE")
    print("=" * 60)

    print(
        "Solicitud:",
        service_id,
    )

    print(
        "Record Inicio Actividades:",
        activity_record_id or "Se resolverá por vínculo exacto",
    )

    print()
    print(
        report_text
    )

    print("=" * 60)

    try:

        save_result = save_field_report_to_activity(
            report_text=report_text,
            activity_record_id=activity_record_id,
            service_record_id=quote_record_id,
            service_identifier=service_id,
        )

    except Exception as error:

        print()
        print("=" * 60)
        print(" ERROR GUARDANDO INFORME")
        print("=" * 60)

        print(
            type(error).__name__,
            str(error),
        )

        print("=" * 60)

        return preserve_save_state(
            phone=phone,
            session=session,
            message=(
                " Ocurrió un problema al guardar "
                "el informe en Airtable.\n\n"
                "La información no se ha perdido.\n\n"
                "Puedes pulsar *Generar informe* para intentarlo nuevamente "
                "o *Modificar informe* si necesitas corregir algo."
            ),
        )

    if not save_result.get(
        "saved"
    ):

        print(
            " Resultado del guardado:",
            save_result,
        )

        reason = save_result.get(
            "reason"
        )

        reason_message = (
            get_save_error_message(
                reason
            )
        )

        return preserve_save_state(
            phone=phone,
            session=session,
            message=reason_message,
        )

    print()
    print("=" * 60)
    print(" INFORME GUARDADO CORRECTAMENTE")
    print("=" * 60)

    print(
        "Solicitud:",
        service_id,
    )

    print(
        "Record Inicio Actividades:",
        save_result.get(
            "record_id"
        ),
    )

    print(
        "Modo:",
        save_result.get(
            "save_mode"
        ),
    )

    print("=" * 60)

    # Copia interna opcional. Nunca crea un cierre y nunca invalida el
    # guardado principal del levantamiento.
    try:
        sync_result = sync_report_to_existing_closure(
            service_record_id=quote_record_id,
            service_identifier=service_id,
            report_text=report_text,
        )

        if (
            not sync_result.get("synced")
            and sync_result.get("reason") != "closure_not_found"
        ):
            print(
                "Sincronización interna de cierre pendiente:",
                sync_result.get("reason"),
            )
    except Exception as error:
        print(
            "Error en sincronización interna de cierre:",
            type(error).__name__,
        )

    delete_session(
        phone
    )

    return (
        "✅ *Levantamiento guardado*\n\n"
        "El informe del servicio quedó registrado correctamente."
    )


# ============================================================
# PRESERVAR ESTADO DE GUARDADO
# ============================================================

def preserve_save_state(
    phone: str,
    session: dict,
    message: str,
) -> str:

    session[
        "status"
    ] = "ready_to_generate"

    session[
        "last_question_field"
    ] = "final_confirmation"

    session[
        "pending_question_fields"
    ] = []

    save_session(
        phone,
        session,
    )

    return message


# ============================================================
# MENSAJES DE ERROR AL GUARDAR
# ============================================================

def get_save_error_message(
    reason,
) -> str:

    messages = {
        "service_not_found": (
            " No pude encontrar nuevamente la solicitud "
            "original en Airtable.\n\n"
            "La información no se ha perdido."
        ),

        "duplicate_service": (
            " Encontré más de una solicitud coincidente "
            "en Airtable.\n\n"
            "No guardé el levantamiento para evitar escribir "
            "en un registro incorrecto."
        ),

        "airtable_update_failed": (
            " Airtable no confirmó la actualización "
            "del levantamiento.\n\n"
            "La información sigue disponible."
        ),
    }

    return messages.get(
        reason,
        (
            " No fue posible guardar el informe.\n\n"
            "La información sigue disponible "
            "y no se ha perdido."
        ),
    )


# ============================================================
# DECISIÓN GUARDADO
# ============================================================

def detect_save_decision(
    text: str,
):

    normalized = normalize_text(
        text
    )

    yes_values = {
        "si",
        "s",
        "ok",
        "guardar",
        "guardalo",
        "guarda",
        "guardar informe",
        "guardar el informe",
        "registrar",
        "registralo",
        "registra",
        "registrar informe",
        "confirmar",
        "confirmo",
        "confirmado",
        "esta correcto",
        "esta bien",
        "correcto",
        "dale",
        "proceder",
        "procede",
        "si guardar",
        "si guardalo",
        "si guarda",
        "si registralo",
        "si registra",
        "si registrar",
        "si confirmo",
        "confirmar y guardar",
    }

    if normalized in yes_values:

        return "yes"

    no_values = {
        "no",
        "n",
        "todavia no",
        "aun no",
        "no guardar",
        "no guardes",
        "no lo guardes",
        "no registrar",
        "no registres",
        "no lo registres",
        "no todavia",
    }

    if normalized in no_values:

        return "no"

    return None


# ============================================================
# AUDIO
# ============================================================

def register_audio_transcription(
    phone: str,
    transcription: str,
) -> dict:

    # La transcripción se utiliza solamente en memoria
    # durante el procesamiento actual.
    print(
        " Transcripción recibida. "
        "No se almacenará en la sesión."
    )

    return {
        "saved": False,
        "temporary": True,
    }

# ============================================================
# IMAGEN
# ============================================================

def register_field_image(
    phone: str,
    image_data: dict,
) -> dict:

    session = get_session(
        phone
    )

    # ========================================================
    # VALIDAR SESIÓN
    # ========================================================

    if not session:

        return {
            "saved": False,
            "count": 0,
            "reason": "missing_session",
        }

    quote_number = session.get(
        "quote_number"
    )

    if not quote_number:

        return {
            "saved": False,
            "count": 0,
            "reason": "missing_quote",
        }

    employee_for_permission = {
        "cargo": session.get(
            "employee_position"
        ),
    }

    if not can_create_field_report(
        employee_for_permission
    ):

        return {
            "saved": False,
            "count": 0,
            "reason": "not_authorized",
        }

    if not isinstance(
        image_data,
        dict,
    ):

        return {
            "saved": False,
            "count": 0,
            "reason": "invalid_image_data",
        }

    # ========================================================
    # PREPARAR LISTA DE IMÁGENES DE LA SESIÓN
    #
    # IMPORTANTE:
    # aquí solo se guardarán METADATOS.
    # Nunca guardaremos la ruta física.
    # ========================================================

    data = session.setdefault(
        "data",
        {},
    )

    images = data.setdefault(
        "imagenes",
        [],
    )

    media_id = image_data.get(
        "media_id"
    )

    # ========================================================
    # EVITAR DUPLICADOS
    # ========================================================

    if media_id:

        duplicate = any(
            isinstance(
                image,
                dict,
            )
            and image.get(
                "media_id"
            )
            == media_id
            for image in images
        )

        if duplicate:

            return {
                "saved": True,
                "count": len(
                    images
                ),
                "duplicate": True,
            }

    # ========================================================
    # OBTENER ARCHIVO TEMPORAL
    # ========================================================

    local_path = image_data.get(
        "local_path"
    )

    if not local_path:

        return {
            "saved": False,
            "count": len(
                images
            ),
            "reason": "missing_local_path",
        }

    filename = (
        image_data.get(
            "filename"
        )
        or "levantamiento.jpg"
    )

    mime_type = (
        image_data.get(
            "mime_type"
        )
        or "image/jpeg"
    )

    # ========================================================
    # SUBIR DIRECTAMENTE A AIRTABLE
    # ========================================================

    try:

        upload_result = upload_field_image(
            quote_number=quote_number,
            record_id=session.get(
                "quote_record_id"
            ),
            file_path=local_path,
            filename=filename,
            mime_type=mime_type,
        )

    except Exception as error:

        print()
        print("=" * 70)
        print(" ERROR SUBIENDO IMAGEN")
        print("=" * 70)

        print(
            type(error).__name__,
            str(error),
        )

        print("=" * 70)

        return {
            "saved": False,
            "count": len(
                images
            ),
            "reason": "image_upload_exception",
        }

    if not upload_result.get(
        "uploaded"
    ):

        return {
            "saved": False,
            "count": len(
                images
            ),
            "reason": upload_result.get(
                "reason",
                "image_upload_failed",
            ),
        }

    # La fotografía ya quedó persistida en Airtable.
    # "Volver" no debe cruzar este límite.
    clear_history(
        phone
    )

    # ========================================================
    # SOLO METADATOS EN LA SESIÓN
    #
    # NO GUARDAR:
    # local_path
    # bytes
    # base64
    # URL temporal
    # ========================================================

    stored_image = {
        "media_id": media_id,

        "filename": filename,

        "mime_type": mime_type,

        "airtable_attachment_id": (
            upload_result.get(
                "attachment_id"
            )
        ),

        "airtable_service_record_id": (
            upload_result.get(
                "service_record_id"
            )
        ),

        "caption": (
            image_data.get(
                "caption"
            )
            or ""
        ),

        "description": (
            image_data.get(
                "description"
            )
            or ""
        ),

        "observed_conditions": (
            image_data.get(
                "observed_conditions",
                []
            )
        ),

        "possible_element": (
            image_data.get(
                "possible_element"
            )
        ),

        "requires_confirmation": (
            image_data.get(
                "requires_confirmation",
                []
            )
        ),
    }

    images.append(
        stored_image
    )

    save_session(
        phone,
        session,
    )

    print()
    print("=" * 70)
    print(" IMAGEN REGISTRADA")
    print("=" * 70)

    print(
        "COT:",
        quote_number,
    )

    print(
        "Attachment:",
        stored_image.get(
            "airtable_attachment_id"
        ),
    )

    print(
        "Imágenes sesión:",
        len(
            images
        ),
    )

    print("=" * 70)

    return {
        "saved": True,
        "count": len(
            images
        ),
        "attachment_id": (
            stored_image.get(
                "airtable_attachment_id"
            )
        ),
        "service_record_id": (
            stored_image.get(
                "airtable_service_record_id"
            )
        ),
    }

# ============================================================
# TRABAJO PENDIENTE:
# INCORPORAR AL MISMO LEVANTAMIENTO
# ============================================================

def continue_pending_job(
    phone: str,
    session: dict,
) -> str:

    pending = session.get(
        "pending_new_job"
    )

    if not pending:

        return (
            "No existe ningún trabajo pendiente "
            "de confirmación."
        )

    pending_data = (
        pending.get(
            "extracted_data",
            {},
        )
        if isinstance(
            pending,
            dict,
        )
        else {}
    )

    session[
        "data"
    ] = merge_data(
        current=session.get(
            "data",
            {},
        ),
        new=pending_data,
    )

    session[
        "pending_new_job"
    ] = None

    clear_question_context(
        session
    )

    save_session(
        phone,
        session,
    )

    preview = build_preview(
        session=session,
        title="Levantamiento actualizado",
    )

    return combine_preview(
        preview=preview,
        message=(
            "Perfecto. Lo incorporé dentro "
            "del mismo levantamiento."
        ),
    )


# ============================================================
# NUEVO TRABAJO DENTRO DE MISMA SOLICITUD
# ============================================================

def start_pending_job(
    phone: str,
    session: dict,
    employee: dict,
) -> str:

    pending = session.get(
        "pending_new_job"
    )

    preserved = {
        "quote_number": session.get(
            "quote_number"
        ),

        "quote_record_id": session.get(
            "quote_record_id"
        ),

        "activity_record_id": session.get(
            "activity_record_id"
        ),

        "selected_service_id": session.get(
            "selected_service_id"
        ),

        "oc": session.get(
            "oc"
        ),

        "service_status": session.get(
            "service_status"
        ),

        "available_services": session.get(
            "available_services",
            [],
        ),
    }

    delete_session(
        phone
    )

    new_session = start_session(
        phone=phone,
        employee=employee,
    )

    new_session = initialize_session_context(
        session=new_session,
        employee=employee,
    )

    for key, value in preserved.items():

        new_session[
            key
        ] = value

    pending_data = {}

    if isinstance(
        pending,
        dict,
    ):

        pending_data = pending.get(
            "extracted_data",
            {},
        )

    new_session[
        "data"
    ] = merge_data(
        current={},
        new=pending_data,
    )

    new_session[
        "pending_new_job"
    ] = None

    clear_question_context(
        new_session
    )

    save_session(
        phone,
        new_session,
    )

    preview = build_preview(
        session=new_session,
        title="Levantamiento iniciado",
    )

    return combine_preview(
        preview=preview,
        message=(
            "El trabajo anterior quedó finalizado.\n\n"
            f"Seguiremos trabajando dentro de "
            f"*{new_session.get('selected_service_id')}*.\n\n"
            "Ahora continuemos con este nuevo trabajo."
        ),
    )


# ============================================================
# EXTRAER COTIZACIÓN
# ============================================================

def extract_quote_number(
    text: str,
):

    if not text:

        return None

    original = str(
        text
    ).strip()

    exact_match = re.fullmatch(
        r"\s*"
        r"(COT\s*\d{3,}"
        r"(?:\s*-\s*[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9 ]+)*"
        r")"
        r"\s*",
        original,
        flags=re.IGNORECASE,
    )

    if exact_match:

        return normalize_service_id(
            exact_match.group(
                1
            )
        )

    clean = normalize_text(
        original
    )

    match = re.search(
        r"\bcot\s*(\d{3,})\b",
        clean,
    )

    if match:

        return (
            f"COT{match.group(1)}"
        )

    quote_context = has_quote_context(
        clean
    )

    patterns = (
        r"\bcotizacion\s+(\d{3,})\b",
        r"\bcotizacion\s+numero\s+(\d{3,})\b",
        r"\bnumero\s+de\s+cotizacion\s+(\d{3,})\b",
        r"\bnumero\s+cotizacion\s+(\d{3,})\b",
        r"\bcotizacion\s+(?:es|seria)\s+(\d{3,})\b",
        r"\bla\s+cotizacion\s+(?:es|seria)\s+(\d{3,})\b",
        r"\bla\s+cotizacion\s+(\d{3,})\b",
    )

    for pattern in patterns:

        match = re.search(
            pattern,
            clean,
        )

        if match:

            return (
                f"COT{match.group(1)}"
            )

    if quote_context:

        numbers = re.findall(
            r"\b\d{3,}\b",
            clean,
        )

        if len(
            numbers
        ) == 1:

            return (
                f"COT{numbers[0]}"
            )

        spoken_number = extract_spoken_number(
            clean
        )

        if spoken_number:

            return (
                f"COT{spoken_number}"
            )

    return None


# ============================================================
# CONTEXTO COTIZACIÓN
# ============================================================

def has_quote_context(
    text: str,
) -> bool:

    if not text:

        return False

    phrases = (
        "cotizacion",
        "cot ",
        "numero de cotizacion",
        "trabajar con",
        "trabajemos con",
        "quiero trabajar",
        "quisiera trabajar",
        "voy a trabajar",
        "usar cotizacion",
        "utilizar la",
        "ocupar la",
    )

    return any(
        phrase in text
        for phrase in phrases
    )


# ============================================================
# NÚMERO HABLADO
# ============================================================

def extract_spoken_number(
    text: str,
):

    if not text:

        return None

    word_to_digit = {
        "cero": "0",
        "uno": "1",
        "una": "1",
        "dos": "2",
        "tres": "3",
        "cuatro": "4",
        "cinco": "5",
        "seis": "6",
        "siete": "7",
        "ocho": "8",
        "nueve": "9",
    }

    sequences = []
    current = []

    for word in text.split():

        if word in word_to_digit:

            current.append(
                word_to_digit[
                    word
                ]
            )

        else:

            if len(
                current
            ) >= 3:

                sequences.append(
                    "".join(
                        current
                    )
                )

            current = []

    if len(
        current
    ) >= 3:

        sequences.append(
            "".join(
                current
            )
        )

    if not sequences:

        return None

    return max(
        sequences,
        key=len,
    )


# ============================================================
# ID SERVICIO DESDE RECORD
# ============================================================

def get_service_id_from_record(
    record: dict,
):

    if not isinstance(
        record,
        dict,
    ):

        return None

    fields = record.get(
        "fields",
        {},
    )

    value = fields.get(
        "ID Solicitud de Servicio"
    )

    if value is None:

        return None

    return str(
        value
    ).strip()


# ============================================================
# EXISTE TRABAJO ACTUAL
# ============================================================

def has_real_current_job(
    session: dict,
) -> bool:

    data = session.get(
        "data",
        {},
    )

    return bool(
        data.get(
            "tipo_trabajo"
        )
        or data.get(
            "descripcion"
        )
    )


# ============================================================
# FALTANTES OPERATIVOS
# ============================================================

def get_operational_missing(
    data: dict,
) -> list:

    return get_required_missing(
        data
    )


def refresh_deterministic_completion(
    session: dict,
) -> list:

    data = session.get(
        "data",
        {},
    )

    missing = get_operational_missing(
        data
    )

    session[
        "critical_missing"
    ] = missing

    if missing:

        session[
            "ready_for_report"
        ] = False

        session[
            "ask_for_observations"
        ] = False

        if session.get(
            "status"
        ) in (
            "ready_to_generate",
            "report_generated",
            "awaiting_save_confirmation",
        ):

            session[
                "status"
            ] = "active"

        return missing

    observations_resolved = field_has_valid_value(
        data=data,
        field="observaciones",
    )

    session[
        "ask_for_observations"
    ] = not observations_resolved

    session[
        "ready_for_report"
    ] = observations_resolved

    if (
        not observations_resolved
        and session.get(
            "status"
        ) in (
            "ready_to_generate",
            "report_generated",
            "awaiting_save_confirmation",
        )
    ):

        session[
            "status"
        ] = "active"

    return missing


# ============================================================
# FILTRAR FALTANTES YA RESUELTOS
# ============================================================

def filter_resolved_missing(
    missing: list,
    data: dict,
) -> list:

    result = []

    for item in normalize_list(
        missing
    ):

        field = missing_to_field(
            item
        )

        if (
            field
            and field_has_value(
                data=data,
                field=field,
            )
        ):

            continue

        result.append(
            item
        )

    return result


# ============================================================
# MAPEAR FALTANTE A CAMPO
# ============================================================

def missing_to_field(
    missing,
):

    value = normalize_text(
        missing
    )

    mappings = (
        (
            "servicio requerido de la empresa externa",
            "empresa_externa_detalle",
        ),
        (
            "empresa externa detalle",
            "empresa_externa_detalle",
        ),
        (
            "equipamiento",
            "equipamiento_necesario",
        ),
        (
            "tiempo",
            "tiempo_estimado",
        ),
        (
            "jornada",
            "jornada",
        ),
        (
            "cantidad de personas",
            "personal_requerido",
        ),
        (
            "personal",
            "personal_requerido",
        ),
        (
            "empresa externa",
            "empresa_externa_requerida",
        ),
        (
            "prioridad",
            "prioridad",
        ),
        (
            "cliente",
            "cliente",
        ),
        (
            "recinto",
            "recinto",
        ),
        (
            "sector",
            "sector",
        ),
        (
            "ubicacion",
            "sector",
        ),
        (
            "tipo de trabajo",
            "tipo_trabajo",
        ),
        (
            "tipo_trabajo",
            "tipo_trabajo",
        ),
        (
            "descripcion",
            "descripcion",
        ),
        (
            "dimension",
            "dimensiones",
        ),
        (
            "medida",
            "dimensiones",
        ),
        (
            "estado actual",
            "estado_actual",
        ),
        (
            "material",
            "materiales",
        ),
        (
            "trabajos requeridos",
            "trabajos_requeridos",
        ),
        (
            "observacion",
            "observaciones",
        ),
    )

    for phrase, field in mappings:

        if phrase in value:

            return field

    return None


# ============================================================
# PREGUNTA PARA FALTANTE
# ============================================================

def missing_to_question(
    missing,
):

    value = normalize_text(
        missing
    )

    exact_questions = {
        "equipamiento necesario": (
            "¿Qué equipamiento se necesita?"
        ),

        "tiempo estimado": (
            "¿Cuánto tiempo estimas que tomará el trabajo?"
        ),

        "jornada": (
            "¿La jornada será diurna, nocturna o mixta?"
        ),

        "personal requerido": (
            "¿Cuántas personas se necesitan?"
        ),

        "empresa externa": (
            "¿Se requiere una empresa externa?"
        ),

        "servicio requerido de la empresa externa": (
            "¿Qué servicio realizará la empresa externa?"
        ),

        "prioridad": (
            "¿Qué prioridad tiene este trabajo? "
            "(Alta, media o baja)"
        ),

        "cliente": (
            "¿A qué cliente corresponde?"
        ),

        "recinto": (
            "¿En qué recinto se realizará?"
        ),

        "sector": (
            "¿En qué sector específico?"
        ),

        "tipo de trabajo": (
            "¿Qué trabajo se realizará?"
        ),

        "tipo_trabajo": (
            "¿Qué trabajo se realizará?"
        ),

        "descripcion": (
            "Describe el trabajo en detalle."
        ),

        "dimensiones": (
            "¿Cuáles son las medidas o dimensiones?"
        ),

        "estado actual": (
            "¿Cuál es el estado actual del área?"
        ),

        "estado_actual": (
            "¿Cuál es el estado actual del área?"
        ),

        "materiales": (
            "¿Qué materiales se necesitan?"
        ),

        "trabajos requeridos": (
            "¿Qué trabajos o intervenciones se requieren?"
        ),
    }

    if value in exact_questions:

        return exact_questions[
            value
        ]

    if (
        "dimension" in value
        or "medida" in value
    ):

        return (
            "¿Cuáles son las dimensiones o medidas "
            "relevantes del trabajo?"
        )

    if "material" in value:

        return (
            "¿Qué materiales serán necesarios "
            "para realizar el trabajo?"
        )

    if "estado" in value:

        return (
            "¿Cuál es el estado actual "
            "del elemento o sector inspeccionado?"
        )

    if "cliente" in value:

        return (
            "¿A qué cliente corresponde el trabajo?"
        )

    if "recinto" in value:

        return (
            "¿En qué recinto se realizará el trabajo?"
        )

    if (
        "sector" in value
        or "ubicacion" in value
    ):

        return (
            "¿En qué sector o ubicación específica "
            "se realizará el trabajo?"
        )

    if (
        "trabajo requerido" in value
        or "intervencion" in value
    ):

        return (
            "¿Qué intervenciones o trabajos "
            "se deberán realizar?"
        )

    if "equipamiento" in value:

        return (
            "¿Qué equipamiento será necesario "
            "para realizar el trabajo?"
        )

    if "tiempo" in value:

        return (
            "¿Cuánto tiempo estimas que tomará "
            "realizar el trabajo?"
        )

    if "jornada" in value:

        return (
            "¿El trabajo se realizará en jornada "
            "diurna, nocturna o en ambas?"
        )

    if (
        "personal" in value
        or "personas" in value
    ):

        return (
            "¿Cuántas personas se necesitarán "
            "para realizar el trabajo?"
        )

    if "prioridad" in value:

        return (
            "¿Qué prioridad tiene este trabajo? "
            "(Alta, media o baja)"
        )

    if (
        "empresa externa" in value
        and (
            "detalle" in value
            or "servicio" in value
        )
    ):

        return (
            "¿Qué servicio deberá realizar "
            "la empresa externa?"
        )

    if "empresa externa" in value:

        return (
            "¿Se requiere una empresa externa "
            "para realizar alguna parte del trabajo?"
        )

    original = str(
        missing
        or ""
    ).strip()

    if not original:

        return None

    return (
        f"¿Puedes indicar {original}?"
    )


# ============================================================
# MOSTRAR TODAS LAS PREGUNTAS
# ============================================================

def build_all_missing_questions(
    critical_missing: list,
    operational_missing: list = None,
    next_question: str = "",
) -> str:

    combined_missing = merge_missing_lists(
        normalize_list(
            critical_missing
        ),
        normalize_list(
            operational_missing
        ),
    )

    questions = []
    normalized_questions = set()

    for missing in combined_missing:

        question = missing_to_question(
            missing
        )

        if not question:

            continue

        normalized = normalize_text(
            question
        )

        if normalized in normalized_questions:

            continue

        normalized_questions.add(
            normalized
        )

        questions.append(
            question
        )

    next_question = str(
        next_question
        or ""
    ).strip()

    if next_question:

        normalized_next = normalize_text(
            next_question
        )

        if (
            normalized_next
            not in normalized_questions
        ):

            # Evitar agregar una segunda pregunta de IA
            # que trate exactamente sobre uno de los campos
            # que ya estamos preguntando.
            field = detect_question_field(
                next_question
            )

            existing_fields = {
                detect_question_field(
                    question
                )
                for question in questions
            }

            if (
                not field
                or field not in existing_fields
            ):

                questions.append(
                    next_question
                )

    if not questions:

        return build_missing_message(
            missing=combined_missing,
            next_question="",
        )

    lines = [
        " *Faltan algunos antecedentes*",
        "",
        (
            "Indica lo siguiente para completar el levantamiento:"
        ),
        "",
    ]

    for index, question in enumerate(
        questions,
        start=1,
    ):

        lines.append(
            f"*{index}.* {question}"
        )

    lines.extend(
        [
            "",
            (
                "Puedes responder *todo junto* por texto o audio."
            ),
        ]
    )

    return "\n".join(
        lines
    )


# ============================================================
# RESPONDER CON FALTANTES
# ============================================================

def respond_with_missing_fields(
    phone: str,
    session: dict,
    preview: str,
    critical_missing: list,
    operational_missing: list,
    next_question: str = "",
    invalid_response: bool = False,
) -> str:

    pending_message = (
        build_all_missing_questions(
            critical_missing=critical_missing,
            operational_missing=operational_missing,
            next_question=next_question,
        )
    )

    if invalid_response:

        pending_message = (
            "Ese mensaje no contiene un antecedente técnico "
            "válido para completar el levantamiento. "
            "No inventaré información.\n\n"
            + pending_message
        )

    save_bulk_question_context(
        phone=phone,
        session=session,
        missing=critical_missing,
    )

    quote_number = (
        session.get("selected_service_id")
        or session.get("quote_number")
    )

    header = "👷 *Agente JCF*"

    if quote_number:
        header += f"\n\n*Cotización*\n• {quote_number}"

    return header + "\n\n" + pending_message


# ============================================================
# GUARDAR CONTEXTO PREGUNTAS MÚLTIPLES
# ============================================================

def save_bulk_question_context(
    phone: str,
    session: dict,
    missing: list,
):

    fields = []

    for item in normalize_list(
        missing
    ):

        field = missing_to_field(
            item
        )

        if (
            field
            and field not in fields
        ):

            fields.append(
                field
            )

    session[
        "last_question_field"
    ] = None

    session[
        "pending_question_fields"
    ] = fields

    save_session(
        phone,
        session,
    )

    print()
    print("=" * 70)
    print(" PREGUNTAS PENDIENTES EN BLOQUE")
    print("=" * 70)

    print(
        "Campos:",
        fields,
    )

    print("=" * 70)


# ============================================================
# OBSERVACIONES FINALES
# ============================================================

def ask_for_final_observations(
    phone: str,
    session: dict,
    title: str = "Levantamiento actualizado",
    preview: str = None,
) -> str:

    session[
        "ask_for_observations"
    ] = True

    session[
        "last_question_field"
    ] = "observaciones"

    session[
        "pending_question_fields"
    ] = []

    save_session(
        phone,
        session,
    )

    quote_number = (
        session.get("selected_service_id")
        or session.get("quote_number")
    )

    lines = ["👷 *Agente JCF*"]

    if quote_number:
        lines.extend(["", "*Cotización*", f"• {quote_number}"])

    lines.extend(
        [
            "",
            "*Observaciones*",
            "",
            "Antes de generar el informe, "
            "¿quieres agregar alguna observación adicional?",
        ]
    )

    return "\n".join(lines)


# ============================================================
# COMPATIBILIDAD: SIGUIENTE PREGUNTA
# ============================================================

def choose_next_question(
    next_question: str,
    operational_missing: list,
) -> tuple:

    if next_question:

        return (
            next_question,
            detect_question_field(
                next_question
            ),
        )

    if not operational_missing:

        return (
            "",
            None,
        )

    first_missing = operational_missing[
        0
    ]

    question = missing_to_question(
        first_missing
    )

    field = missing_to_field(
        first_missing
    )

    return (
        question
        or "",
        field,
    )


# ============================================================
# DETECTAR CAMPO DE PREGUNTA
# ============================================================

def detect_question_field(
    question: str,
):

    if not question:

        return None

    text = normalize_text(
        question
    )

    rules = (
        (
            "que servicio debera realizar",
            "empresa_externa_detalle",
        ),
        (
            "servicio realizara la empresa",
            "empresa_externa_detalle",
        ),
        (
            "equipamiento",
            "equipamiento_necesario",
        ),
        (
            "cuanto tiempo",
            "tiempo_estimado",
        ),
        (
            "jornada",
            "jornada",
        ),
        (
            "cuantas personas",
            "personal_requerido",
        ),
        (
            "empresa externa",
            "empresa_externa_requerida",
        ),
        (
            "prioridad",
            "prioridad",
        ),
        (
            "observacion",
            "observaciones",
        ),
        (
            "cliente",
            "cliente",
        ),
        (
            "recinto",
            "recinto",
        ),
        (
            "sector",
            "sector",
        ),
        (
            "dimension",
            "dimensiones",
        ),
        (
            "cuanto mide",
            "dimensiones",
        ),
        (
            "estado",
            "estado_actual",
        ),
        (
            "material",
            "materiales",
        ),
    )

    for phrase, field in rules:

        if phrase in text:

            return field

    return None


# ============================================================
# GUARDAR CONTEXTO PREGUNTA
# ============================================================

def save_question_context(
    phone: str,
    session: dict,
    field,
):

    session[
        "last_question_field"
    ] = field

    session[
        "pending_question_fields"
    ] = []

    save_session(
        phone,
        session,
    )

    if field:

        print(
            " Esperando respuesta para:",
            field,
        )


# ============================================================
# CAMPO TIENE VALOR
# ============================================================

def field_has_value(
    data: dict,
    field: str,
) -> bool:

    if not isinstance(
        data,
        dict,
    ):

        return False

    if not field:

        return False

    if field in (
        "save_confirmation",
        "final_confirmation",
    ):

        return False

    return field_has_valid_value(
        data=data,
        field=field,
    )


# ============================================================
# NECESITA OBSERVACIONES
# ============================================================

def needs_observations(
    session: dict,
) -> bool:

    data = session.get(
        "data",
        {},
    )

    return not field_has_valid_value(
        data=data,
        field="observaciones",
    )


# ============================================================
# UNIR FALTANTES
# ============================================================

def merge_missing_lists(
    first: list,
    second: list,
) -> list:

    result = []
    normalized_seen = set()

    for collection in (
        first,
        second,
    ):

        if not isinstance(
            collection,
            list,
        ):

            continue

        for item in collection:

            normalized = normalize_text(
                item
            )

            if not normalized:

                continue

            if normalized in normalized_seen:

                continue

            normalized_seen.add(
                normalized
            )

            result.append(
                item
            )

    return result


# ============================================================
# NORMALIZAR LISTA
# ============================================================

def normalize_list(
    value,
) -> list:

    if isinstance(
        value,
        list,
    ):

        return value

    if value in (
        None,
        "",
    ):

        return []

    return [
        value
    ]


# ============================================================
# MENSAJE FALTANTES
# ============================================================

def build_missing_message(
    missing: list,
    next_question: str,
) -> str:

    if next_question:

        return next_question

    lines = [
        " *Información pendiente*",
        "",
        "Para continuar necesito confirmar:",
        "",
    ]

    for item in missing:

        lines.append(
            f"• {item}"
        )

    return "\n".join(
        lines
    )


# ============================================================
# PREVIEW + MENSAJE
# ============================================================

def combine_preview(
    preview: str,
    message: str,
) -> str:

    if preview and message:

        return (
            preview
            + "\n\n"
            + message
        )

    return (
        preview
        or message
        or ""
    )


# ============================================================
# HAY INFORMACIÓN REAL
# ============================================================

def has_meaningful_data(
    data: dict,
) -> bool:

    if not isinstance(
        data,
        dict,
    ):

        return False

    for key, value in data.items():

        if key == "imagenes":

            continue

        if isinstance(
            value,
            bool,
        ):

            return True

        if value not in (
            None,
            "",
            [],
            {},
        ):

            return True

    return False


# ============================================================
# COMBINAR DATOS
# ============================================================

def merge_data(
    current: dict,
    new: dict,
    replace_lists: bool = False,
) -> dict:

    if not isinstance(
        current,
        dict,
    ):

        current = {}

    if not isinstance(
        new,
        dict,
    ):

        return current

    for key, value in new.items():

        if value is None:

            continue

        if isinstance(
            value,
            str,
        ) and not value.strip():

            continue

        # ====================================================
        # DICCIONARIOS
        # ====================================================

        if isinstance(
            value,
            dict,
        ):

            if not value:

                continue

            existing = current.get(
                key
            )

            if not isinstance(
                existing,
                dict,
            ):

                existing = {}

            current[
                key
            ] = merge_data(
                current=existing,
                new=value,
                replace_lists=replace_lists,
            )

            continue

        # ====================================================
        # LISTAS
        # ====================================================

        if isinstance(
            value,
            list,
        ):

            if not value:

                continue

            # ------------------------------------------------
            # En una modificación explícita reemplazamos
            # listas susceptibles de corrección.
            # ------------------------------------------------

            if (
                replace_lists
                and key in REPLACEABLE_LIST_FIELDS
            ):

                current[
                    key
                ] = deduplicate_list(
                    value
                )

                continue

            existing = current.get(
                key
            )

            if not isinstance(
                existing,
                list,
            ):

                existing = []

            combined = list(
                existing
            )

            for item in value:

                if item in (
                    None,
                    "",
                ):

                    continue

                if item not in combined:

                    combined.append(
                        item
                    )

            current[
                key
            ] = combined

            continue

        # ====================================================
        # VALOR SIMPLE
        # ====================================================

        current[
            key
        ] = value

    return current


# ============================================================
# ELIMINAR DUPLICADOS DE LISTA
# ============================================================

def deduplicate_list(
    values: list,
) -> list:

    result = []

    for value in values:

        if value in (
            None,
            "",
        ):

            continue

        if value not in result:

            result.append(
                value
            )

    return result


# ============================================================
# NORMALIZAR TEXTO
# ============================================================

def normalize_text(
    text,
) -> str:

    if text is None:

        return ""

    value = str(
        text
    ).strip().lower()

    value = "".join(
        character
        for character in unicodedata.normalize(
            "NFD",
            value,
        )
        if unicodedata.category(
            character
        )
        != "Mn"
    )

    value = re.sub(
        r"[^\w\s]",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


# ============================================================
# NORMALIZAR ID SERVICIO
# ============================================================

def normalize_service_id(
    text: str,
) -> str:

    if not text:

        return ""

    value = str(
        text
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

    value = value.upper().strip()

    value = re.sub(
        r"^COT\s+",
        "COT",
        value,
    )

    return value


# ============================================================
# PRIMER NOMBRE
# ============================================================

def first_name(
    name,
) -> str:

    if not name:

        return "Trabajador"

    return str(
        name
    ).strip().split()[0]
