import re
import unicodedata



# ============================================================
# CLASIFICADOR CENTRAL
# ============================================================


from app.agents.central.conversation_engine import (

    classify_message,
)



# ============================================================
# MAESTRO
# ============================================================


from app.agents.maestro.service import (

    process_field_report_message,
    process_maestro_action,
    has_preserved_report_progress,
)

from app.whatsapp.interactive import (
    ACTION_BACK_HOME,
    ACTION_CLOSE_ADD_MORE_PHOTOS,
    ACTION_CLOSE_CONFIRM_SAVE,
    ACTION_CLOSE_SERVICE,
    ACTION_CLOSURE_SATISFIED_YES,
    ACTION_CLOSURE_SATISFIED_NO,
    ACTION_FIELD_SURVEY,
    ACTION_RESUME_FIELD_SURVEY,
    ACTION_NO_OBSERVATIONS,
    ACTION_REPORT_GENERATE,
    ACTION_REPORT_MODIFY,
    ACTION_START_SERVICE,
    ACTION_MITIGATION_CAUSE_SPECIALTY,
    ACTION_MITIGATION_CAUSE_MATERIALS,
    ACTION_MITIGATION_CAUSE_PERMISSIONS,
    ACTION_MITIGATION_CAUSE_BUDGET,
)


from app.agents.maestro.session import (

    get_session as get_maestro_session,
    clear_session as clear_maestro_session,
    save_session as save_maestro_session,
)



# ============================================================
# OPERACIONES
# ============================================================


from app.agents.operaciones.service import (

    process_operations_message,
    process_operations_location,
    request_additional_closure_photo,
    build_pending_field_report_message,
)


from app.agents.operaciones.session import (

    get_session as get_operations_session,
    clear_session as clear_operations_session,
)


from app.agents.operaciones.conversation_engine import (

    is_start_service_request,
    is_close_service_request,
)



# ============================================================
# RRHH
# ============================================================


from app.agents.rrhh.service import (

    process_rrhh_message,
)



# ============================================================
# GEOLOCALIZACIÓN
# ============================================================


from app.geolocation.reverse_geocoder import (

    resolve_location_text,
)



# ============================================================
# AGENTES
# ============================================================


AGENT_MAESTRO = "maestro"
AGENT_OPERATIONS = "operaciones"
AGENT_RRHH = "rrhh"
AGENT_SUPERVISOR = "supervisor"
AGENT_GENERAL = "general"


DETERMINISTIC_OPERATIONS_WAITING_STATES = frozenset(
    {
        "cot",
        "cot_close",
        "service",
        "helper",
        "helper_confirmation",
        "helper_mode",
        "helper_selection",
        "location",
        "registering_start",
        "service_activation",
        "closure_helper_confirmation",
        "closure_helper_selection",
        "closure_satisfaction",
        "closure_mitigation_cause",
        "closure_unsatisfactory_observations",
        "closure_observations",
        "closure_service_sheet_photo",
        "closure_service_photo",
        "closure_confirmation",
        "additional_work_photo",
    }
)



# ============================================================
# FUNCIÓN PRINCIPAL DEL AGENTE CENTRAL
# ============================================================

# ============================================================
# FUNCIÓN PRINCIPAL DEL AGENTE CENTRAL
# ============================================================


def process_central_message(

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
            " *Asistente Central JCF*\n\n"
            "No recibí información para procesar."
        )

    employee = (
        employee
        if isinstance(
            employee,
            dict,
        )
        else {}
    )

    print()
    print("=" * 70)
    print(" AGENTE CENTRAL JCF")
    print("=" * 70)

    print(
        "Teléfono:",
        phone,
    )

    print(
        "Usuario:",
        employee.get(
            "nombre"
        )
        or "No identificado",
    )

    print(
        "Cargo:",
        employee.get(
            "cargo"
        )
        or "No informado",
    )

    print(
        "Mensaje:",
        text_clean,
    )

    print("=" * 70)

    # Una respuesta a un paso operacional activo pertenece a ese
    # flujo antes de cualquier saludo, palabra clave o clasificación IA.
    operations_session = get_operations_session(
        phone
    )

    if (
        has_active_operations_session(
            operations_session
        )
        and should_remain_in_operations(
            text=text_clean,
            session=operations_session,
        )
    ):

        print()
        print("=" * 70)
        print(" CONTINUACIÓN DETERMINÍSTICA DE OPERACIONES")
        print("=" * 70)
        print(
            "Paso:",
            operations_session.get(
                "waiting_for"
            ),
        )
        print(" Enviando directamente a Operaciones.")
        print("=" * 70)

        return dispatch_to_agent(
            agent=AGENT_OPERATIONS,
            phone=phone,
            text=text_clean,
            employee=employee,
        )

    # ========================================================
    # 0. RUTA RÁPIDA - MENSAJES GENERALES
    #
    # MUY IMPORTANTE:
    #
    # Estos mensajes NO necesitan:
    #
    # - consultar sesiones;
    # - llamar OpenAI;
    # - clasificar con IA;
    # - consultar Maestro;
    # - consultar Operaciones.
    #
    # Ejemplos:
    #
    # hola
    # gracias
    # buenos días
    # quién eres
    # qué puedes hacer
    #
    # La sesión de Maestro u Operaciones NO se elimina.
    # Solamente respondemos temporalmente desde General.
    # ========================================================

    if looks_like_clear_general_message(
        text_clean
    ):

        print()
        print("=" * 70)
        print(" RUTA RÁPIDA CENTRAL")
        print("=" * 70)

        print(
            "Tipo:",
            "mensaje_general",
        )

        print(
            " Respuesta directa sin OpenAI."
        )

        print("=" * 70)

        return process_general_message(
            text=text_clean,
            employee=employee,
        )

    # ========================================================
    # 0.5 VOLVER / ATRÁS / RETROCEDER
    # ========================================================

    if is_back_request(
        text_clean
    ):

        operations_session = get_operations_session(
            phone
        )

        maestro_session = get_maestro_session(
            phone
        )

        if has_active_operations_session(
            operations_session
        ):
            return dispatch_to_agent(
                agent=AGENT_OPERATIONS,
                phone=phone,
                text=text_clean,
                employee=employee,
            )

        if has_active_maestro_session(
            maestro_session
        ):
            return dispatch_to_agent(
                agent=AGENT_MAESTRO,
                phone=phone,
                text=text_clean,
                employee=employee,
            )

        return (
            "🧠 *Asistente Central JCF*\n\n"
            "No hay un proceso activo al cual retroceder.\n\n"
            "Escribe *Hola* para ver nuevamente el menú principal."
        )

    # ========================================================
    # 1. OPERACIONES EXPLÍCITAS
    #
    # También las detectamos ANTES de recuperar sesiones.
    #
    # No necesitamos OpenAI para saber que:
    #
    # "quiero iniciar un servicio"
    # "quiero cerrar un servicio"
    #
    # pertenecen a Operaciones.
    # ========================================================

    if (
        is_start_service_request(
            text_clean
        )
        or is_close_service_request(
            text_clean
        )
    ):

        print()
        print("=" * 70)
        print(" OPERACIÓN EXPLÍCITA DETECTADA")
        print("=" * 70)

        existing_maestro_session = get_maestro_session(
            phone
        )

        if (
            has_active_maestro_session(
                existing_maestro_session
            )
            and is_close_service_request(text_clean)
        ):
            if normalize_text(
                existing_maestro_session.get("status")
            ) != "paused":
                existing_maestro_session[
                    "status_before_pause"
                ] = (
                    existing_maestro_session.get("status")
                    or "active"
                )
                existing_maestro_session[
                    "status"
                ] = "paused"

            save_maestro_session(
                phone,
                existing_maestro_session,
            )

            return build_pending_field_report_message(
                existing_maestro_session.get("quote_number")
            )

        if (
            has_active_maestro_session(
                existing_maestro_session
            )
            and has_preserved_report_progress(
                existing_maestro_session
            )
        ):

            return (
                " *Levantamiento protegido*\n\n"
                "Existe un levantamiento con información guardada para "
                f"*{existing_maestro_session.get('quote_number')}*.\n\n"
                "No iniciaré otro proceso porque eso podría hacerte perder "
                "el contexto actual. Escribe *retomar levantamiento* para "
                "continuar, o finaliza/cancela explícitamente el anterior."
            )

        # ========================================================
        # IMPORTANTE
        #
        # Si el trabajador comienza explícitamente un flujo
        # operacional, eliminamos cualquier sesión pendiente
        # del Maestro.
        #
        # Así una selección anterior no interfiere.
        # ========================================================

        clear_maestro_session(
            phone
        )

        print(
            " Sesión Maestro anterior limpiada."
        )

        print(
            " Enviando a Operaciones."
        )

        print("=" * 70)

        return dispatch_to_agent(
            agent=AGENT_OPERATIONS,
            phone=phone,
            text=text_clean,
            employee=employee,
        )

    # ========================================================
    # 2. LEVANTAMIENTO TÉCNICO EXPLÍCITO
    #
    # Tampoco necesita OpenAI.
    # ========================================================

    if looks_like_explicit_field_survey(
        text_clean
    ):

        print()
        print("=" * 70)
        print(" LEVANTAMIENTO TÉCNICO DETECTADO")
        print("=" * 70)

        # ========================================================
        # MUY IMPORTANTE
        #
        # Si antes estaba iniciando/cerrando un servicio y ahora
        # dice explícitamente que quiere realizar un
        # levantamiento, abandonamos la sesión Operaciones.
        #
        # Esto evita que después:
        #
        # 1
        # 5
        # COT37417
        #
        # sean capturados por Operaciones.
        # ========================================================

        clear_operations_session(
            phone
        )

        print(
            " Sesión Operaciones anterior limpiada."
        )

        print(
            " Enviando a Maestro."
        )

        print("=" * 70)

        return dispatch_to_agent(
            agent=AGENT_MAESTRO,
            phone=phone,
            text=text_clean,
            employee=employee,
        )

    # ========================================================
    # 3. CONSULTA EXPLÍCITA DE SERVICIOS
    #
    # Tampoco necesita OpenAI.
    # ========================================================

    if looks_like_service_list_request(
        text_clean
    ):

        print()
        print("=" * 70)
        print(" RUTA RÁPIDA CENTRAL")
        print("=" * 70)

        print(
            "Tipo:",
            "consulta_servicios",
        )

        print(
            " Enviando directamente a Maestro."
        )

        print("=" * 70)

        return dispatch_to_agent(
            agent=AGENT_MAESTRO,
            phone=phone,
            text=text_clean,
            employee=employee,
        )

    # ========================================================
    # 4. CONSULTA SOBRE ESTADO OPERATIVO
    #
    # Tampoco necesita OpenAI.
    # ========================================================

    if looks_like_operational_status_question(
        text_clean
    ):

        print()
        print("=" * 70)
        print(" RUTA RÁPIDA CENTRAL")
        print("=" * 70)

        print(
            "Tipo:",
            "estado_operativo",
        )

        print(
            " Enviando directamente a Maestro."
        )

        print("=" * 70)

        return dispatch_to_agent(
            agent=AGENT_MAESTRO,
            phone=phone,
            text=text_clean,
            employee=employee,
        )

    # ========================================================
    # 5. RECUPERAR SESIONES
    #
    # Recién llegamos aquí cuando el mensaje NO pudo
    # resolverse por las rutas rápidas anteriores.
    # ========================================================

    maestro_session = get_maestro_session(
        phone
    )

    operations_session = get_operations_session(
        phone
    )

    # ========================================================
    # DEBUG SESIÓN OPERACIONES
    # ========================================================

    print()
    print("=" * 70)
    print(" ESTADO SESIÓN OPERACIONES")
    print("=" * 70)

    if isinstance(
        operations_session,
        dict,
    ):

        print(
            "Existe sesión:",
            True,
        )

        print(
            "Acción:",
            operations_session.get(
                "action"
            ),
        )

        print(
            "COT:",
            operations_session.get(
                "cot"
            ),
        )

        print(
            "Esperando:",
            operations_session.get(
                "waiting_for"
            ),
        )

        print(
            "Estado:",
            operations_session.get(
                "status"
            ),
        )

    else:

        print(
            "Existe sesión:",
            False,
        )

    print("=" * 70)

    # ========================================================
    # DEBUG SESIÓN MAESTRO
    # ========================================================

    print()
    print("=" * 70)
    print(" ESTADO SESIÓN MAESTRO")
    print("=" * 70)

    if isinstance(
        maestro_session,
        dict,
    ):

        print(
            "Existe sesión:",
            True,
        )

        print(
            "Solicitud seleccionada:",
            maestro_session.get(
                "quote_number"
            ),
        )

        print(
            "Cantidad servicios disponibles:",
            len(
                maestro_session.get(
                    "available_services",
                    [],
                )
                or []
            ),
        )

        print(
            "Estado sesión:",
            maestro_session.get(
                "status"
            ),
        )

    else:

        print(
            "Existe sesión:",
            False,
        )

    print("=" * 70)

    # ========================================================
    # 6. SESIÓN OPERACIONES ACTIVA
    # ========================================================

    if has_active_operations_session(
        operations_session
    ):

        # ====================================================
        # CONTINUACIÓN DIRECTA DE OPERACIONES
        # ====================================================

        if should_remain_in_operations(
            text=text_clean,
            session=operations_session,
        ):

            print()
            print("=" * 70)
            print(" CONTINUACIÓN SESIÓN OPERACIONES")
            print("=" * 70)

            print(
                " Enviando directamente a Operaciones."
            )

            print("=" * 70)

            return dispatch_to_agent(
                agent=AGENT_OPERATIONS,
                phone=phone,
                text=text_clean,
                employee=employee,
            )

        # ====================================================
        # POSIBLE CAMBIO DE DOMINIO
        #
        # AQUÍ SÍ usamos IA porque el mensaje ya no pudo
        # clasificarse con reglas deterministas.
        # ====================================================

        decision = classify_message(
            text=text_clean,
            employee=employee,
            maestro_session_active=(
                has_active_maestro_session(
                    maestro_session
                )
            ),
            operations_session_active=True,
        )

        selected_agent = decision.get(
            "agent",
            AGENT_OPERATIONS,
        )

        confidence = decision.get(
            "confidence",
            0,
        )

        reason = decision.get(
            "reason",
            "",
        )

        print()
        print("=" * 70)
        print(" IA CENTRAL - CAMBIO DE DOMINIO")
        print("=" * 70)

        print(
            "Agente:",
            selected_agent,
        )

        print(
            "Confianza:",
            confidence,
        )

        print(
            "Motivo:",
            reason,
        )

        print("=" * 70)

        if selected_agent == AGENT_OPERATIONS:

            return dispatch_to_agent(
                agent=AGENT_OPERATIONS,
                phone=phone,
                text=text_clean,
                employee=employee,
            )

        if selected_agent in (
            AGENT_RRHH,
            AGENT_MAESTRO,
            AGENT_SUPERVISOR,
        ):

            return dispatch_to_agent(
                agent=selected_agent,
                phone=phone,
                text=text_clean,
                employee=employee,
            )

        if (
            selected_agent == AGENT_GENERAL
            and looks_like_clear_general_message(
                text_clean
            )
        ):

            return dispatch_to_agent(
                agent=AGENT_GENERAL,
                phone=phone,
                text=text_clean,
                employee=employee,
            )

        # ====================================================
        # SEGURIDAD:
        # Si no estamos seguros, conservar Operaciones.
        # ====================================================

        return dispatch_to_agent(
            agent=AGENT_OPERATIONS,
            phone=phone,
            text=text_clean,
            employee=employee,
        )

    # ========================================================
    # 7. SELECCIÓN NUMÉRICA PENDIENTE DEL MAESTRO
    # ========================================================

    if is_pending_service_selection(
        session=maestro_session,
        text=text_clean,
    ):

        print()
        print("=" * 70)
        print(" SELECCIÓN DIRECTA DE SERVICIO MAESTRO")
        print("=" * 70)

        print(
            "Respuesta:",
            text_clean,
        )

        print(
            " Enviando directamente a Maestro."
        )

        print("=" * 70)

        return dispatch_to_agent(
            agent=AGENT_MAESTRO,
            phone=phone,
            text=text_clean,
            employee=employee,
        )

    # ========================================================
    # 8. SELECCIÓN POR COT / OC DE LISTA MAESTRO
    # ========================================================

    if has_pending_service_list(
        maestro_session
    ):

        if matches_available_service(
            session=maestro_session,
            text=text_clean,
        ):

            print()
            print("=" * 70)
            print(" SERVICIO DE LISTA MAESTRO DETECTADO")
            print("=" * 70)

            print(
                "Mensaje:",
                text_clean,
            )

            print(
                " Enviando directamente a Maestro."
            )

            print("=" * 70)

            return dispatch_to_agent(
                agent=AGENT_MAESTRO,
                phone=phone,
                text=text_clean,
                employee=employee,
            )

    # ========================================================
    # 9. ID DE SOLICITUD CLARO
    #
    # Sin sesión Operaciones:
    #
    # COT37470
    #
    # pertenece a Maestro.
    # ========================================================

    if looks_like_service_request(
        text_clean
    ):

        print()
        print("=" * 70)
        print(" ID DE SOLICITUD DETECTADO")
        print("=" * 70)

        print(
            " Enviando a Maestro."
        )

        print("=" * 70)

        return dispatch_to_agent(
            agent=AGENT_MAESTRO,
            phone=phone,
            text=text_clean,
            employee=employee,
        )

    # ========================================================
    # 10. SESIÓN MAESTRO ACTIVA
    # ========================================================

    if has_active_maestro_session(
        maestro_session
    ):

        print()
        print("=" * 70)
        print(" SESIÓN MAESTRO ACTIVA")
        print("=" * 70)

        # ====================================================
        # CONTINUACIÓN DIRECTA
        # ====================================================

        if should_remain_in_maestro(
            text=text_clean,
            session=maestro_session,
        ):

            print(
                " Continuando directamente en Maestro."
            )

            print("=" * 70)

            return dispatch_to_agent(
                agent=AGENT_MAESTRO,
                phone=phone,
                text=text_clean,
                employee=employee,
            )

        # ====================================================
        # POSIBLE CAMBIO DE DOMINIO
        # ====================================================

        decision = classify_message(
            text=text_clean,
            employee=employee,
            maestro_session_active=True,
            operations_session_active=False,
        )

        selected_agent = decision.get(
            "agent",
            AGENT_MAESTRO,
        )

        confidence = decision.get(
            "confidence",
            0,
        )

        reason = decision.get(
            "reason",
            "",
        )

        print()
        print("=" * 70)
        print(" IA CENTRAL - CAMBIO DE DOMINIO")
        print("=" * 70)

        print(
            "Agente:",
            selected_agent,
        )

        print(
            "Confianza:",
            confidence,
        )

        print(
            "Motivo:",
            reason,
        )

        print("=" * 70)

        if selected_agent in (
            AGENT_RRHH,
            AGENT_OPERATIONS,
            AGENT_SUPERVISOR,
        ):

            return dispatch_to_agent(
                agent=selected_agent,
                phone=phone,
                text=text_clean,
                employee=employee,
            )

        if selected_agent == AGENT_GENERAL:

            if looks_like_clear_general_message(
                text_clean
            ):

                return dispatch_to_agent(
                    agent=AGENT_GENERAL,
                    phone=phone,
                    text=text_clean,
                    employee=employee,
                )

            selected_agent = AGENT_MAESTRO

        return dispatch_to_agent(
            agent=selected_agent,
            phone=phone,
            text=text_clean,
            employee=employee,
        )

    # ========================================================
    # 11. ÚLTIMO RECURSO: IA
    #
    # SOLO llegamos a OpenAI cuando:
    #
    # - no era saludo;
    # - no era Operaciones;
    # - no era levantamiento;
    # - no era consulta de servicios;
    # - no era estado operativo;
    # - no existía una continuación clara de sesión;
    # - no era una COT.
    #
    # Es decir: solamente mensajes realmente ambiguos.
    # ========================================================

    print()
    print("=" * 70)
    print(" CLASIFICACIÓN IA NECESARIA")
    print("=" * 70)

    print(
        "Mensaje no resuelto por reglas locales:",
        text_clean,
    )

    print("=" * 70)

    decision = classify_message(
        text=text_clean,
        employee=employee,
        maestro_session_active=False,
        operations_session_active=False,
    )

    agent = decision.get(
        "agent",
        AGENT_GENERAL,
    )

    confidence = decision.get(
        "confidence",
        0,
    )

    reason = decision.get(
        "reason",
        "",
    )

    print()
    print("=" * 70)
    print(" DECISIÓN DEL AGENTE CENTRAL")
    print("=" * 70)

    print(
        "Agente:",
        agent,
    )

    print(
        "Confianza:",
        confidence,
    )

    print(
        "Motivo:",
        reason,
    )

    print("=" * 70)

    return dispatch_to_agent(
        agent=agent,
        phone=phone,
        text=text_clean,
        employee=employee,
    )


def process_central_action(
    phone: str,
    action: str,
    employee: dict,
) -> str:

    action = str(
        action
        or ""
    ).strip()

    mapped_texts = {
        ACTION_START_SERVICE: "Quiero iniciar un servicio",
        ACTION_CLOSE_SERVICE: "Quiero cerrar un servicio",
        ACTION_FIELD_SURVEY: "Quiero realizar un levantamiento",
    }

    if action == ACTION_RESUME_FIELD_SURVEY:

        maestro_session = get_maestro_session(
            phone
        )

        if not (
            has_active_maestro_session(maestro_session)
            and normalize_text(maestro_session.get("status")) == "paused"
        ):
            return (
                " *Agente JCF*\n\n"
                "El levantamiento pausado ya no está disponible."
            )

        clear_operations_session(
            phone
        )

        return process_central_message(
            phone=phone,
            text="retomar levantamiento",
            employee=employee,
        )

    if action in {
        ACTION_START_SERVICE,
        ACTION_CLOSE_SERVICE,
    }:

        operations_session = get_operations_session(
            phone
        )

        if has_active_operations_session(
            operations_session
        ):

            return (
                " *Agente Operacional JCF*\n\n"
                "Ya existe un proceso operacional activo. "
                "Continúa con el paso actual antes de iniciar otro."
            )

    if action in mapped_texts:

        return process_central_message(
            phone=phone,
            text=mapped_texts[
                action
            ],
            employee=employee,
        )

    if action in {
        ACTION_CLOSE_CONFIRM_SAVE,
        ACTION_CLOSE_ADD_MORE_PHOTOS,
    }:

        operations_session = get_operations_session(
            phone
        )

        is_closure_review_step = bool(
            has_active_operations_session(
                operations_session
            )
            and operations_session.get(
                "action"
            ) == "CLOSE_SERVICE"
            and operations_session.get(
                "waiting_for"
            ) == "closure_confirmation"
        )

        if not is_closure_review_step:

            return (
                " *Agente Operacional JCF*\n\n"
                "La revisión del cierre ya no está disponible. "
                "Continúa con el paso actual."
            )

        if action == ACTION_CLOSE_ADD_MORE_PHOTOS:

            return request_additional_closure_photo(
                phone=phone,
                employee=employee,
            )

        return process_operations_message(
            phone=phone,
            text="Sí",
            employee=employee,
        )

    closure_action_texts = {
        ACTION_CLOSURE_SATISFIED_YES: "Sí",
        ACTION_CLOSURE_SATISFIED_NO: "No",
        ACTION_MITIGATION_CAUSE_SPECIALTY:
            "Especialidad no cubierta",
        ACTION_MITIGATION_CAUSE_MATERIALS:
            "Falta de Materiales y/o Herramientas",
        ACTION_MITIGATION_CAUSE_PERMISSIONS:
            "Falta de permisos",
        ACTION_MITIGATION_CAUSE_BUDGET:
            "Aprobación de presupuesto",
    }

    if action in closure_action_texts:
        operations_session = get_operations_session(phone)
        expected_state = (
            "closure_satisfaction"
            if action in {
                ACTION_CLOSURE_SATISFIED_YES,
                ACTION_CLOSURE_SATISFIED_NO,
            }
            else "closure_mitigation_cause"
        )
        if not (
            has_active_operations_session(operations_session)
            and operations_session.get("action") == "CLOSE_SERVICE"
            and operations_session.get("waiting_for") == expected_state
        ):
            return (
                " *Agente Operacional JCF*\n\n"
                "La opción seleccionada ya no está disponible. "
                "Continúa con el paso actual."
            )

        return process_operations_message(
            phone=phone,
            text=closure_action_texts[action],
            employee=employee,
        )

    if action in {
        ACTION_BACK_HOME,
        ACTION_NO_OBSERVATIONS,
    }:

        operations_session = get_operations_session(
            phone
        )

        is_closure_observations_step = bool(
            has_active_operations_session(
                operations_session
            )
            and operations_session.get(
                "action"
            ) == "CLOSE_SERVICE"
            and operations_session.get(
                "waiting_for"
            ) == "closure_observations"
        )

        if is_closure_observations_step:

            return process_operations_message(
                phone=phone,
                text=(
                    "Sin observaciones"
                    if action == ACTION_NO_OBSERVATIONS
                    else "volver"
                ),
                employee=employee,
            )

    if action in {
        ACTION_BACK_HOME,
        ACTION_NO_OBSERVATIONS,
        ACTION_REPORT_MODIFY,
        ACTION_REPORT_GENERATE,
    }:

        return process_maestro_action(
            phone=phone,
            action=action,
            employee=employee,
        )

    return (
        " *Asistente Central JCF*\n\n"
        "La acción seleccionada ya no está disponible."
    )



# ============================================================
# PROCESAR UBICACIÓN RECIBIDA POR CENTRAL
# ============================================================


def process_central_location(

    phone: str,
    employee: dict,
    latitude=None,
    longitude=None,
    address=None,
    name=None,
) -> str:

    print()
    print("=" * 70)
    print(" UBICACIÓN RECIBIDA POR CENTRAL")
    print("=" * 70)

    print(
        "Teléfono:",
        phone,
    )

    print(
        "Latitud:",
        latitude,
    )

    print(
        "Longitud:",
        longitude,
    )

    print(
        "Dirección WhatsApp:",
        address,
    )

    print(
        "Nombre:",
        name,
    )

    print("=" * 70)

    # ========================================================
    # VERIFICAR SESIÓN OPERACIONES
    # ========================================================

    operations_session = get_operations_session(
        phone
    )

    if not has_active_operations_session(
        operations_session
    ):

        return (
            " *Asistente Central JCF*\n\n"
            "Recibí tu ubicación, pero en este momento no te he "
            "solicitado una ubicación para iniciar o cerrar un "
            "servicio. Continúa con el proceso actual."
        )

    if (
        operations_session.get(
            "waiting_for"
        )
        != "location"
    ):

        return (
            " *Asistente Central JCF*\n\n"
            "Recibí tu ubicación, pero en este momento no te he "
            "solicitado una ubicación para iniciar o cerrar un "
            "servicio. Continúa con el proceso actual."
        )

    # ========================================================
    # RESOLVER DIRECCIÓN
    # ========================================================

    resolved = resolve_location_text(
        latitude=latitude,
        longitude=longitude,
        address=address,
        name=name,
    )

    if not resolved.get(
        "resolved"
    ):

        return (
            " No pude obtener una dirección "
            "válida desde la ubicación enviada.\n\n"
            "Intenta compartir nuevamente tu "
            "ubicación actual desde WhatsApp."
        )

    location_text = str(
        resolved.get(
            "text"
        )
        or ""
    ).strip()

    if not location_text:

        return (
            " No pude obtener una dirección "
            "válida desde la ubicación enviada."
        )

    # ========================================================
    # DERIVAR A OPERACIONES
    # ========================================================

    return process_operations_location(
        phone=phone,
        employee=employee,
        location_text=location_text,
        latitude=latitude,
        longitude=longitude,
    )



# ============================================================
# DERIVAR A AGENTE ESPECIALIZADO
# ============================================================


def dispatch_to_agent(

    agent: str,
    phone: str,
    text: str,
    employee: dict,
) -> str:

    print()
    print("=" * 70)
    print(" AGENTE CENTRAL - DERIVACIÓN")
    print("=" * 70)

    print(
        "Agente destino:",
        agent,
    )

    print(
        "Usuario:",
        employee.get(
            "nombre"
        )
        or "No identificado",
    )

    print("=" * 70)

    # ========================================================
    # OPERACIONES
    # ========================================================

    if agent == AGENT_OPERATIONS:

        return process_operations_message(
            phone=phone,
            text=text,
            employee=employee,
        )

    # ========================================================
    # MAESTRO
    # ========================================================

    if agent == AGENT_MAESTRO:

        return process_field_report_message(
            phone=phone,
            text=text,
            employee=employee,
        )

    # ========================================================
    # RRHH
    # ========================================================

    if agent == AGENT_RRHH:

        return process_rrhh_message(
            phone=phone,
            text=text,
            employee=employee,
        )

    # ========================================================
    # SUPERVISOR
    # ========================================================

    if agent == AGENT_SUPERVISOR:

        return process_supervisor_message(
            text=text,
            employee=employee,
        )

    # ========================================================
    # GENERAL
    # ========================================================

    return process_general_message(
        text=text,
        employee=employee,
    )



# ============================================================
# RESPUESTA GENERAL DEL CENTRAL
# ============================================================


def process_general_message(

    text: str,
    employee: dict,
) -> str:

    name = employee.get(
        "nombre"
    )

    if name:

        greeting = (
            f"Hola {first_name(name)} "
        )

    else:

        greeting = (
            "Hola "
        )

    normalized = normalize_text(
        text
    )

    # ========================================================
    # GRACIAS
    # ========================================================

    if normalized in (
        "gracias",
        "muchas gracias",
        "vale gracias",
        "ok gracias",
        "perfecto gracias",
    ):

        return (
            " *Asistente Central JCF*\n\n"
            "¡De nada! "
        )

    # ========================================================
    # QUIÉN ERES / QUÉ PUEDES HACER
    # ========================================================

    if any(
        phrase in normalized
        for phrase in (
            "quien eres",
            "que eres",
            "que puedes hacer",
            "para que sirves",
        )
    ):

        return (
            " *Asistente Central JCF*\n\n"
            "Soy el asistente interno de JCF.\n\n"
            "Puedo ayudarte con inicio y cierre "
            "de servicios, levantamientos técnicos "
            "y consultas de RRHH."
        )

    # ========================================================
    # SALUDO
    # ========================================================

    return (
        " *Asistente Central JCF*\n\n"
        f"{greeting}\n\n"
        "¿En qué gestión necesitas ayuda?\n\n"
        "Puedes escribirme de forma natural. "
        "Identificaré qué agente de JCF "
        "debe atender tu solicitud."
    )



# ============================================================
# SUPERVISOR
# ============================================================


def process_supervisor_message(

    text: str,
    employee: dict,
) -> str:

    return (
        " *Supervisor Central JCF*\n\n"
        "Entendí que necesitas información "
        "consolidada de la operación.\n\n"
        "Este módulo se utilizará para combinar "
        "información proveniente de varios agentes "
        "especializados."
    )



# ============================================================
# SESIÓN OPERACIONES ACTIVA
# ============================================================


def has_active_operations_session(

    session,
) -> bool:

    if not isinstance(
        session,
        dict,
    ):

        return False

    status = normalize_text(
        session.get(
            "status"
        )
    )

    if status in (
        "completed",
        "cancelled",
    ):

        return False

    return True



# ============================================================
# CONTINUACIÓN NATURAL DE OPERACIONES
# ============================================================


def should_remain_in_operations(

    text: str,
    session: dict,
) -> bool:

    if not isinstance(
        session,
        dict,
    ):

        return False

    waiting_for = str(
        session.get(
            "waiting_for"
        )
        or ""
    ).strip().lower()

    return (
        waiting_for
        in DETERMINISTIC_OPERATIONS_WAITING_STATES
    )



# ============================================================
# SESIÓN MAESTRO ACTIVA
# ============================================================


def has_active_maestro_session(

    session,
) -> bool:

    if not isinstance(
        session,
        dict,
    ):

        return False

    status = normalize_text(
        session.get(
            "status"
        )
    )

    if status in (
        "completed",
        "cancelled",
    ):

        return False

    quote_number = session.get(
        "quote_number"
    )

    if quote_number:

        return True

    available_services = session.get(
        "available_services",
        [],
    )

    if (
        isinstance(
            available_services,
            list,
        )
        and bool(
            available_services
        )
    ):

        return True

    return False



# ============================================================
# EXISTE LISTA PENDIENTE MAESTRO
# ============================================================


def has_pending_service_list(

    session,
) -> bool:

    if not isinstance(
        session,
        dict,
    ):

        return False

    if session.get(
        "quote_number"
    ):

        return False

    services = session.get(
        "available_services",
        [],
    )

    return (
        isinstance(
            services,
            list,
        )
        and bool(
            services
        )
    )



# ============================================================
# RESPUESTA NUMÉRICA DE LISTA MAESTRO
# ============================================================


def is_pending_service_selection(

    session,
    text: str,
) -> bool:

    if not has_pending_service_list(
        session
    ):

        return False

    value = str(
        text
        or ""
    ).strip()

    if not re.fullmatch(
        r"\d+",
        value,
    ):

        return False

    services = session.get(
        "available_services",
        [],
    )

    try:

        selected_index = int(
            value
        )

    except Exception:

        return False

    return (
        1
        <= selected_index
        <= len(
            services
        )
    )



# ============================================================
# MENSAJE COINCIDE CON SERVICIO DISPONIBLE MAESTRO
# ============================================================


def matches_available_service(

    session,
    text: str,
) -> bool:

    if not has_pending_service_list(
        session
    ):

        return False

    wanted = normalize_text(
        text
    )

    if not wanted:

        return False

    services = session.get(
        "available_services",
        [],
    )

    for service in services:

        if not isinstance(
            service,
            dict,
        ):

            continue

        quote = normalize_text(
            service.get(
                "quote_number"
            )
        )

        oc = normalize_text(
            service.get(
                "oc"
            )
        )

        if (
            quote
            and (
                wanted == quote
                or quote in wanted
            )
        ):

            return True

        if (
            oc
            and (
                wanted == oc
                or oc in wanted
            )
        ):

            return True

    return False



# ============================================================
# CONTINUACIÓN NATURAL DE MAESTRO
# ============================================================


def should_remain_in_maestro(

    text: str,
    session: dict,
) -> bool:

    value = normalize_text(
        text
    )

    if not value:

        return True

    # ========================================================
    # NO ATRAPAR OPERACIONES
    # ========================================================

    if (
        is_start_service_request(
            text
        )
        or is_close_service_request(
            text
        )
    ):

        return False

    # ========================================================
    # RESPUESTAS CORTAS
    # ========================================================

    short_answers = {
        "si",
        "no",
        "ok",
        "dale",
        "listo",
        "correcto",
        "perfecto",
        "continuar",
        "continua",
        "seguir",
        "sigue",
        "guardar",
        "guardalo",
        "registrar",
        "registralo",
        "terminar",
        "termine",
        "finalizar",
        "finalice",
        "ninguna",
        "ninguno",
        "nada",
        "nada mas",
    }

    if value in short_answers:

        return True

    # ========================================================
    # OPCIÓN NUMÉRICA
    # ========================================================

    if re.fullmatch(
        r"\d+",
        value,
    ):

        return True

    # ========================================================
    # VOCABULARIO TÉCNICO DE MAESTRO
    # ========================================================

    maestro_terms = (
        "levantamiento",
        "material",
        "materiales",
        "herramienta",
        "herramientas",
        "equipamiento",
        "pintura",
        "reparacion",
        "reparar",
        "instalar",
        "instalacion",
        "muro",
        "techo",
        "puerta",
        "luminaria",
        "enchufe",
        "metros",
        "medida",
        "medidas",
        "dimension",
        "dimensiones",
        "dias",
        "horas",
        "jornada",
        "personal",
        "empresa externa",
        "observacion",
        "observaciones",
        "prioridad",
        "foto",
        "fotos",
        "imagen",
        "imagenes",
    )

    if any(
        term in value
        for term in maestro_terms
    ):

        return True

    # ========================================================
    # CAMPO PENDIENTE
    #
    # Ya NO devolvemos True automáticamente solo porque
    # exista last_question_field.
    #
    # Primero permitimos que Central pueda detectar cambios
    # de dominio como RRHH u Operaciones.
    # ========================================================

    last_question_field = session.get(
        "last_question_field"
    )

    if last_question_field:

        # Solo consideramos automáticamente continuación
        # respuestas breves.
        word_count = len(
            value.split()
        )

        if word_count <= 6:

            return True

    return False



# ============================================================
# LEVANTAMIENTO TÉCNICO EXPLÍCITO
# ============================================================


def looks_like_explicit_field_survey(

    text: str,
) -> bool:

    value = normalize_text(
        text
    )

    if not value:
        return False

    phrases = (
        # ====================================================
        # LEVANTAR SERVICIO
        # ====================================================

        "levantar servicio",
        "levantar un servicio",
        "levantar el servicio",

        "quiero levantar servicio",
        "quiero levantar un servicio",
        "quiero levantar el servicio",

        "quisiera levantar servicio",
        "quisiera levantar un servicio",
        "quisiera levantar el servicio",

        "necesito levantar servicio",
        "necesito levantar un servicio",

        # ====================================================
        # LEVANTAMIENTO
        # ====================================================

        "realizar levantamiento",
        "realizar un levantamiento",
        "realizar el levantamiento",

        "hacer levantamiento",
        "hacer un levantamiento",
        "hacer el levantamiento",

        "quiero realizar levantamiento",
        "quiero realizar un levantamiento",

        "quiero hacer levantamiento",
        "quiero hacer un levantamiento",

        "levantamiento tecnico",

        # ====================================================
        # CONTINUAR LEVANTAMIENTO
        # ====================================================

        "continuar levantamiento",
        "continuar el levantamiento",
        "seguir con el levantamiento",
        "sigamos con el levantamiento",
    )

    return any(
        phrase in value
        for phrase in phrases
    )


# ============================================================
# PEDIDO DE LISTA DE SERVICIOS
# ============================================================


def looks_like_service_list_request(

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
        "cuales son mis servicios",
        "cuales servicios tengo",
        "que servicios tengo",
        "quiero ver mis servicios",
        "quisiera ver mis servicios",
        "quiero saber mis servicios",
        "quisiera saber mis servicios",
        "mostrar mis servicios",
        "muestrame mis servicios",
        "servicios asignados",
        "servicios que tengo asignados",
        "otra solicitud",
        "otra oc",
        "cambiar de servicio",
        "volver a mis servicios",
    )

    return any(
        phrase in value
        for phrase in phrases
    )



# ============================================================
# PREGUNTA SOBRE ESTADO OPERATIVO
# ============================================================


def looks_like_operational_status_question(

    text: str,
) -> bool:

    value = normalize_text(
        text
    )

    if not value:

        return False

    operational_statuses = (
        "programado",
        "programados",
        "programada",
        "programadas",
        "activo",
        "activos",
        "activa",
        "activas",
        "pausado",
        "pausados",
        "pausada",
        "pausadas",
    )

    if not any(
        status in value
        for status in operational_statuses
    ):

        return False

    contexts = (
        "servicio",
        "servicios",
        "estado",
        "estados",
        "que significa",
        "que quiere decir",
        "que es",
        "mis ",
        "tengo",
        "asignado",
        "asignados",
    )

    return any(
        context in value
        for context in contexts
    )



# ============================================================
# SOLICITUD DE RETROCESO
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


# ============================================================
# MENSAJE GENERAL CLARO
# ============================================================


def looks_like_clear_general_message(

    text: str,
) -> bool:

    value = normalize_text(
        text
    )

    general_values = {
        "hola",
        "holi",
        "buenas",
        "buenos dias",
        "buenas tardes",
        "buenas noches",
        "gracias",
        "muchas gracias",
        "quien eres",
        "que eres",
        "que puedes hacer",
        "para que sirves",
    }

    return value in general_values



# ============================================================
# PARECE ID DE SOLICITUD
# ============================================================


def looks_like_service_request(

    text: str,
) -> bool:

    if not text:

        return False

    return bool(
        re.search(
            r"\bCOT\s*\d{3,}\b",
            str(
                text
            ),
            flags=re.IGNORECASE,
        )
    )



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
# PRIMER NOMBRE
# ============================================================


def first_name(

    name: str,
) -> str:

    if not name:

        return ""

    return str(
        name
    ).strip().split()[0]
