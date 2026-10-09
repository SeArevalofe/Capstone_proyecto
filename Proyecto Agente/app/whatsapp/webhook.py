
import json
import re

from pathlib import Path

from fastapi import (
    APIRouter,
    Request,
    Query,
    Response,
)

from app.airtable.employee_repository import (
    get_employee_by_phone,
)

from app.whatsapp.client import (
    WHATSAPP_INTERACTIVE_BODY_LIMIT,
    send_whatsapp_message,
    send_whatsapp_buttons,
    send_whatsapp_list,
    send_whatsapp_location_request,
    send_typing_indicator,
)

from app.whatsapp.media import (
    download_media,
    delete_media_file,
    optimize_image,
)

from app.whatsapp.interactive import (
    build_contextual_actions,
    get_button_action,
    is_button_allowed,
    should_show_usage_notice,
)

from app.whatsapp.debounce import (
    cancel_text_burst,
    coalesce_text_message,
    register_message_id,
)


# ============================================================
# AGENTE CENTRAL
# ============================================================

from app.agents.central.service import (
    process_central_action,
    process_central_message,
    process_central_location,
)


# ============================================================
# OPERACIONES
#
# Necesitamos revisar si existe una sesión activa
# esperando fotografías del cierre.
# ============================================================

from app.agents.operaciones.session import (
    clear_session as clear_operations_session,
    get_session as get_operations_session,
)

from app.agents.operaciones.service import (
    build_location_request_message,
    process_operations_image,
)


# ============================================================
# FUNCIONES ESPECÍFICAS DEL AGENTE MAESTRO
# ============================================================

from app.agents.maestro.service import (
    register_audio_transcription,
    register_field_image,
)

from app.agents.maestro.session import (
    clear_session as clear_maestro_session,
    get_session as get_maestro_session,
)

from app.agents.maestro.audio_processor import (
    transcribe_audio,
)

from app.agents.maestro.image_processor import (
    analyze_field_image,
)


# ============================================================
# CONFIG
# ============================================================

from app.config import (
    WHATSAPP_VERIFY_TOKEN,
    DEVELOPMENT_MODE,
    TEST_PHONE,
    TEST_IMPERSONATE_PHONE,
)


router = APIRouter()


# ============================================================
# ESTADOS DE OPERACIONES QUE ESPERAN IMAGEN
# ============================================================

OPERATIONS_IMAGE_STATES = {
    "closure_service_sheet_photo",
    "closure_service_photo",
    "additional_work_photo",
}


AUTHORIZED_RESET_PHONES = {
    "56950903253",
    "56956063333",
    "56936426905",
}

RESET_COMMAND = "/jcf-reset"


def normalize_reset_phone(
    phone: str,
) -> str:

    return "".join(
        character
        for character in str(
            phone
            or ""
        )
        if character.isdigit()
    )


def parse_reset_target(
    text: str,
):

    parts = str(
        text
        or ""
    ).strip().split()

    if (
        len(parts) != 2
        or parts[0] != RESET_COMMAND
        or not re.fullmatch(
            r"\+?569\d{8}",
            parts[1],
        )
    ):

        return None

    return normalize_reset_phone(
        parts[1]
    )


async def intercept_admin_session_reset(
    phone: str,
    text: str,
) -> bool:

    command_text = str(
        text
        or ""
    ).strip()

    if not (
        command_text == RESET_COMMAND
        or command_text.startswith(
            RESET_COMMAND + " "
        )
    ):

        return False

    admin_phone = normalize_reset_phone(
        phone
    )

    if admin_phone not in AUTHORIZED_RESET_PHONES:

        safe_send_whatsapp_message(
            phone=phone,
            message=(
                "⛔ No tienes permisos para reiniciar sesiones."
            ),
        )

        return True

    target_phone = parse_reset_target(
        command_text
    )

    if (
        not target_phone
        or target_phone == admin_phone
    ):

        safe_send_whatsapp_message(
            phone=phone,
            message=(
                "⚠️ Comando inválido.\n\n"
                "Usa:\n"
                "/jcf-reset 569XXXXXXXX"
            ),
        )

        return True

    operations_existed = (
        get_operations_session(
            target_phone
        )
        is not None
    )

    maestro_existed = (
        get_maestro_session(
            target_phone
        )
        is not None
    )

    operations_cleared = clear_operations_session(
        target_phone
    )

    clear_maestro_session(
        target_phone
    )

    await cancel_text_burst(
        target_phone
    )

    print()
    print("=" * 70)
    print(" RESET ADMINISTRATIVO DE SESIÓN")
    print("=" * 70)
    print("Administrador:", admin_phone)
    print("Objetivo:", target_phone)
    print("Operaciones limpiada:", operations_cleared)
    print("Maestro limpiado:", maestro_existed)
    print("=" * 70)

    session_existed = (
        operations_existed
        or maestro_existed
    )

    if session_existed:

        safe_send_whatsapp_message(
            phone=phone,
            message=(
                f"✅ Sesión reiniciada para {target_phone}.\n\n"
                "El trabajador puede escribir \"hola\" "
                "para comenzar nuevamente."
            ),
        )

        safe_send_whatsapp_message(
            phone=target_phone,
            message=(
                "🔄 Tu sesión fue reiniciada.\n\n"
                "Escribe \"hola\" para comenzar nuevamente."
            ),
        )

    else:

        safe_send_whatsapp_message(
            phone=phone,
            message=(
                "✅ El trabajador no tenía una sesión activa.\n\n"
                "Puede escribir \"hola\" para comenzar nuevamente."
            ),
        )

    return True


# ============================================================
# VERIFICACIÓN WEBHOOK
# ============================================================

@router.get("/webhook/whatsapp")
def verify_webhook(
    hub_mode: str = Query(
        default="",
        alias="hub.mode",
    ),
    hub_verify_token: str = Query(
        default="",
        alias="hub.verify_token",
    ),
    hub_challenge: str = Query(
        default="",
        alias="hub.challenge",
    ),
):

    if (
        hub_mode == "subscribe"
        and hub_verify_token == WHATSAPP_VERIFY_TOKEN
    ):

        print(
            "✅ Webhook verificado por Meta"
        )

        return Response(
            content=hub_challenge,
            media_type="text/plain",
        )

    print()
    print("=" * 60)
    print("❌ VERIFICACIÓN WEBHOOK RECHAZADA")
    print("=" * 60)

    print(
        "Modo recibido:",
        hub_mode,
    )

    print(
        "Token recibido:",
        hub_verify_token,
    )

    print("=" * 60)

    return Response(
        content="Verification failed",
        status_code=403,
    )


# ============================================================
# WEBHOOK PRINCIPAL
# ============================================================

@router.post("/webhook/whatsapp")
async def receive_whatsapp_message(
    request: Request,
):

    try:

        # ====================================================
        # 1. LEER JSON COMPLETO DE META
        # ====================================================

        data = await request.json()

        print()
        print("=" * 80)
        print("📦 WEBHOOK COMPLETO RECIBIDO DESDE META")
        print("=" * 80)

        print(
            json.dumps(
                data,
                indent=2,
                ensure_ascii=False,
            )
        )

        print("=" * 80)

        # ====================================================
        # 2. EXTRAER MENSAJE
        # ====================================================

        message = extract_message(
            data
        )

        if not message:

            print(
                "ℹ️ Evento recibido, pero no contiene "
                "un mensaje de usuario."
            )

            return {
                "status": "ok"
            }

        # ====================================================
        # 3. EXTRAER TELÉFONO Y MESSAGE ID
        # ====================================================

        phone = str(
            message.get(
                "from",
                ""
            )
            or ""
        ).strip()

        message_id = str(
            message.get(
                "id",
                ""
            )
            or ""
        ).strip()

        if not phone:

            print(
                "⚠️ El mensaje no contiene "
                "teléfono de origen."
            )

            return {
                "status": "ok"
            }

        # ====================================================
        # 4. TIPO DE MENSAJE
        # ====================================================

        message_type = str(
            message.get(
                "type"
            )
            or ""
        ).strip().lower()

        if not await register_message_id(
            message_id
        ):

            print(
                "ℹ️ Mensaje duplicado ignorado:",
                message_id,
            )

            return {
                "status": "ok"
            }

        text = ""

        if message_type == "text":

            text = str(
                message
                .get(
                    "text",
                    {}
                )
                .get(
                    "body",
                    ""
                )
                or ""
            ).strip()

            if await intercept_admin_session_reset(
                phone=phone,
                text=text,
            ):

                return {
                    "status": "ok"
                }

            text = await coalesce_text_message(
                phone=phone,
                text=text,
            )

            if text is None:

                return {
                    "status": "ok"
                }

        else:

            # Una selección interactiva, ubicación u otro evento
            # no debe quedar esperando detrás de una ráfaga de texto.
            await cancel_text_burst(
                phone
            )

        print()
        print("=" * 60)
        print("📩 WHATSAPP RECIBIDO")
        print("=" * 60)

        print(
            "Teléfono:",
            phone
        )

        print(
            "Tipo:",
            message_type
        )

        print("=" * 60)

        # ====================================================
        # 5. MARCAR LEÍDO + TYPING
        # ====================================================

        if message_id:

            send_typing_indicator(
                message_id=message_id,
            )

        # ====================================================
        # 6. IDENTIFICAR / AUTORIZAR EMPLEADO
        # ====================================================

        employee = identify_employee(
            phone
        )

        if not employee.get(
            "found"
        ):

            print()
            print("=" * 60)
            print("⛔ USUARIO NO AUTORIZADO")
            print("=" * 60)

            print(
                "Teléfono:",
                phone
            )

            print(
                "Motivo:",
                employee.get(
                    "message"
                )
            )

            print("=" * 60)

            safe_send_whatsapp_message(
                phone=phone,
                message=(
                    "Hola. Este canal es de uso interno de JCF. "
                    "No encontramos este número registrado como "
                    "trabajador autorizado."
                ),
            )

            return {
                "status": "ok"
            }

        print()
        print("=" * 60)
        print("✅ CONTEXTO DEL TRABAJADOR")
        print("=" * 60)

        print(
            "Nombre:",
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

        print(
            "Record ID:",
            employee.get(
                "record_id"
            )
        )

        print(
            "Impersonado:",
            employee.get(
                "impersonated",
                False,
            )
        )

        print("=" * 60)

        if (
            is_waiting_for_operations_location(
                phone
            )
            and message_type not in (
                "text",
                "location",
            )
        ):

            safe_send_answer_for_current_state(
                phone=phone,
                answer=(
                    "Para continuar necesito una ubicación real enviada "
                    "con la función de ubicación de WhatsApp. Una foto, "
                    "audio, enlace o captura no reemplaza esa ubicación."
                ),
                employee=employee,
            )

            return {
                "status": "ok"
            }

        # ====================================================
        # 7. TEXTO
        # ====================================================

        if message_type == "text":

            print(
                "📝 Texto recibido:",
                text
            )

            if not text:

                return {
                    "status": "ok"
                }

            answer = process_central_message(
                phone=phone,
                text=text,
                employee=employee,
            )

            print()
            print("=" * 60)
            print("🤖 RESPUESTA AGENTE CENTRAL JCF")
            print("=" * 60)

            print(
                answer
            )

            print("=" * 60)

            safe_send_answer_for_current_state(
                phone=phone,
                answer=answer,
                employee=employee,
                source_text=text,
            )

            return {
                "status": "ok"
            }

        # ====================================================
        # 8. BOTÓN INTERACTIVO
        # ====================================================

        if message_type == "interactive":

            interactive = message.get(
                "interactive",
                {}
            )

            if not isinstance(
                interactive,
                dict,
            ):

                interactive = {}

            interactive_type = str(
                interactive.get(
                    "type"
                )
                or ""
            ).strip().lower()

            print()
            print("=" * 70)
            print("🔘 INTERACCIÓN WHATSAPP RECIBIDA")
            print("=" * 70)

            print(
                "Tipo interactivo:",
                interactive_type
                or "NO INFORMADO",
            )

            if interactive_type not in (
                "button_reply",
                "list_reply",
            ):

                print(
                    "⚠️ Interacción no soportada."
                )

                print("=" * 70)

                safe_send_whatsapp_message(
                    phone=phone,
                    message=(
                        "⚠️ Esta interacción de WhatsApp "
                        "todavía no está habilitada.\n\n"
                        "Puedes escribirme tu solicitud "
                        "por texto."
                    ),
                )

                return {
                    "status": "ok"
                }

            reply_key = (
                "button_reply"
                if interactive_type == "button_reply"
                else "list_reply"
            )

            button_reply = interactive.get(
                reply_key,
                {}
            )

            if not isinstance(
                button_reply,
                dict,
            ):

                button_reply = {}

            button_id = str(
                button_reply.get(
                    "id"
                )
                or ""
            ).strip()

            button_title = str(
                button_reply.get(
                    "title"
                )
                or ""
            ).strip()

            print(
                "Button ID:",
                button_id
                or "VACÍO",
            )

            print(
                "Título:",
                button_title
                or "VACÍO",
            )

            print("=" * 70)

            if not button_id:

                safe_send_whatsapp_message(
                    phone=phone,
                    message=(
                        "⚠️ No pude identificar la opción "
                        "seleccionada.\n\n"
                        "Puedes intentarlo nuevamente o "
                        "escribirme tu solicitud."
                    ),
                )

                return {
                    "status": "ok"
                }

            # Seguridad adicional: el menú visual depende del
            # cargo, pero el backend tampoco confía solo en UI.
            if not is_button_allowed(
                button_id=button_id,
                employee=employee,
            ):

                safe_send_whatsapp_message(
                    phone=phone,
                    message=(
                        "⛔ Esta opción no está disponible "
                        "para tu cargo actual."
                    ),
                )

                return {
                    "status": "ok"
                }

            action = get_button_action(
                button_id
            )

            if not action:

                safe_send_whatsapp_message(
                    phone=phone,
                    message=(
                        "⚠️ La opción seleccionada ya no "
                        "está disponible.\n\n"
                        "Escribe *hola* para volver al menú."
                    ),
                )

                return {
                    "status": "ok"
                }

            print()
            print("=" * 70)
            print("🔀 BOTÓN → INTENCIÓN CENTRAL")
            print("=" * 70)

            print(
                "Button ID:",
                button_id,
            )

            print(
                "Acción:",
                action,
            )

            print("=" * 70)

            answer = process_central_action(
                phone=phone,
                action=action,
                employee=employee,
            )

            print()
            print("=" * 60)
            print("🤖 RESPUESTA BOTÓN INTERACTIVO")
            print("=" * 60)

            print(
                answer
            )

            print("=" * 60)

            safe_send_answer_for_current_state(
                phone=phone,
                answer=answer,
                employee=employee,
            )

            return {
                "status": "ok"
            }

        # ====================================================
        # 9. UBICACIÓN
        # ====================================================

        if message_type == "location":

            location = message.get(
                "location",
                {}
            )

            if not isinstance(
                location,
                dict,
            ):

                location = {}

            latitude = location.get(
                "latitude"
            )

            longitude = location.get(
                "longitude"
            )

            address = str(
                location.get(
                    "address"
                )
                or ""
            ).strip()

            name = str(
                location.get(
                    "name"
                )
                or ""
            ).strip()

            print()
            print("=" * 60)
            print("📍 UBICACIÓN WHATSAPP RECIBIDA")
            print("=" * 60)

            print(
                "Latitud:",
                latitude,
            )

            print(
                "Longitud:",
                longitude,
            )

            print(
                "Dirección:",
                address,
            )

            print(
                "Nombre:",
                name,
            )

            print("=" * 60)

            answer = process_central_location(
                phone=phone,
                employee=employee,
                latitude=latitude,
                longitude=longitude,
                address=address,
                name=name,
            )

            print()
            print("=" * 60)
            print("📍 RESPUESTA UBICACIÓN")
            print("=" * 60)

            print(
                answer
            )

            print("=" * 60)

            safe_send_answer_for_current_state(
                phone=phone,
                answer=answer,
                employee=employee,
            )

            return {
                "status": "ok"
            }

        # ====================================================
        # 10. AUDIO
        # ====================================================

        if message_type == "audio":

            media_id = (
                message
                .get(
                    "audio",
                    {}
                )
                .get(
                    "id"
                )
            )

            print()
            print("=" * 60)
            print("🎙️ AUDIO RECIBIDO")
            print("=" * 60)

            print(
                "Media ID:",
                media_id
            )

            print("=" * 60)

            if not media_id:

                return {
                    "status": "ok"
                }

            safe_send_whatsapp_message(
                phone=phone,
                message=(
                    "🎙️ Recibí tu audio. "
                    "Lo estoy interpretando."
                ),
            )

            audio_path = None

            try:

                media = download_media(
                    media_id=media_id,
                    phone=phone,
                    temporary=True,
                )

                audio_path = media.get(
                    "path"
                )

                if not audio_path:

                    raise RuntimeError(
                        "No se obtuvo la ruta temporal del audio."
                    )

                transcription = transcribe_audio(
                    audio_path
                )

                transcription = str(
                    transcription
                    or ""
                ).strip()

                print()
                print("=" * 60)
                print("📝 AUDIO TRANSCRITO")
                print("=" * 60)

                print(
                    transcription
                )

                print("=" * 60)

                if not transcription:

                    safe_send_whatsapp_message(
                        phone=phone,
                        message=(
                            "⚠️ No pude interpretar claramente "
                            "el contenido del audio."
                        ),
                    )

                    return {
                        "status": "ok"
                    }

                register_audio_transcription(
                    phone=phone,
                    transcription=transcription,
                )

                answer = process_central_message(
                    phone=phone,
                    text=transcription,
                    employee=employee,
                )

                safe_send_answer_for_current_state(
                    phone=phone,
                    answer=(
                        "🎙️ *Audio interpretado*\n\n"
                        + answer
                    ),
                    employee=employee,
                )

                return {
                    "status": "ok"
                }

            except Exception as error:

                print()
                print("=" * 60)
                print("❌ ERROR PROCESANDO AUDIO")
                print("=" * 60)

                print(
                    type(error).__name__,
                    str(error),
                )

                print("=" * 60)

                safe_send_whatsapp_message(
                    phone=phone,
                    message=(
                        "⚠️ Ocurrió un problema al procesar "
                        "el audio.\n\n"
                        "Puedes intentarlo nuevamente o "
                        "enviar la información por texto."
                    ),
                )

                return {
                    "status": "ok"
                }

            finally:

                if audio_path:

                    delete_media_file(
                        audio_path
                    )

        # ====================================================
        # 11. IMAGEN
        #
        # MUY IMPORTANTE:
        #
        # Antes de tratar una foto como imagen del Agente
        # Maestro, revisamos Operaciones.
        #
        # Si Operaciones está esperando:
        #
        # closure_service_sheet_photo
        #
        # o:
        #
        # closure_service_photo
        #
        # la imagen pertenece al cierre operacional.
        # ====================================================

        if message_type == "image":

            image = message.get(
                "image",
                {}
            )

            if not isinstance(
                image,
                dict,
            ):

                image = {}

            media_id = image.get(
                "id"
            )

            caption = str(
                image.get(
                    "caption"
                )
                or ""
            ).strip()

            incoming_mime_type = str(
                image.get(
                    "mime_type"
                )
                or "image/jpeg"
            ).strip()

            print()
            print("=" * 60)
            print("📷 IMAGEN RECIBIDA")
            print("=" * 60)

            print(
                "Media ID:",
                media_id
            )

            print(
                "Caption:",
                caption
            )

            print(
                "Mime type:",
                incoming_mime_type
            )

            print("=" * 60)

            if not media_id:

                return {
                    "status": "ok"
                }

            # =================================================
            # REVISAR SESIÓN DE OPERACIONES
            # =================================================

            operations_session = get_operations_session(
                phone
            )

            operations_waiting_for = ""

            operations_action = ""

            if isinstance(
                operations_session,
                dict,
            ):

                operations_waiting_for = str(
                    operations_session.get(
                        "waiting_for"
                    )
                    or ""
                ).strip()

                operations_action = str(
                    operations_session.get(
                        "action"
                    )
                    or ""
                ).strip()

            is_operations_closure_image = (
                operations_action
                == "CLOSE_SERVICE"
                and operations_waiting_for
                in OPERATIONS_IMAGE_STATES
            )

            print()
            print("=" * 70)
            print("🔎 CLASIFICANDO IMAGEN RECIBIDA")
            print("=" * 70)

            print(
                "Sesión Operaciones:",
                bool(
                    operations_session
                ),
            )

            print(
                "Acción:",
                operations_action
                or "NINGUNA",
            )

            print(
                "Esperando:",
                operations_waiting_for
                or "NINGUNO",
            )

            print(
                "¿Imagen de cierre operacional?:",
                is_operations_closure_image,
            )

            print("=" * 70)

            # =================================================
            # RUTA 1:
            # IMAGEN DE CIERRE OPERACIONAL
            # =================================================

            if is_operations_closure_image:

                original_path = None
                optimized_path = None

                # ---------------------------------------------
                # IMPORTANTE:
                #
                # Las imágenes deben permanecer guardadas
                # hasta la confirmación final.
                #
                # NO se eliminan en el finally de este bloque.
                # ---------------------------------------------

                try:

                    print()
                    print("=" * 70)
                    print("⚙️ IMAGEN DIRIGIDA A OPERACIONES")
                    print("=" * 70)

                    print(
                        "Estado:",
                        operations_waiting_for,
                    )

                    print("=" * 70)

                    media = download_media(
                        media_id=media_id,
                        phone=phone,
                        temporary=True,
                    )

                    if not isinstance(
                        media,
                        dict,
                    ):

                        media = {}

                    original_path = media.get(
                        "path"
                    )

                    if not original_path:

                        raise RuntimeError(
                            "No se obtuvo la ruta temporal "
                            "de la fotografía."
                        )

                    # =========================================
                    # OPTIMIZAR FOTO
                    # =========================================

                    optimized_path = optimize_image(
                        file_path=original_path,
                        max_width=1600,
                        quality=80,
                    )

                    if not optimized_path:

                        raise RuntimeError(
                            "No se pudo generar la "
                            "imagen optimizada."
                        )

                    optimized_path = str(
                        optimized_path
                    )

                    filename = Path(
                        optimized_path
                    ).name

                    mime_type = "image/jpeg"

                    print()
                    print("=" * 70)
                    print("📦 FOTO PREPARADA PARA OPERACIONES")
                    print("=" * 70)

                    print(
                        "Original:",
                        original_path,
                    )

                    print(
                        "Optimizada:",
                        optimized_path,
                    )

                    print(
                        "Filename:",
                        filename,
                    )

                    print(
                        "Mime:",
                        mime_type,
                    )

                    print("=" * 70)

                    # =========================================
                    # ENTREGAR FOTO A OPERACIONES
                    # =========================================

                    answer = process_operations_image(
                        phone=phone,
                        employee=employee,
                        file_path=optimized_path,
                        filename=filename,
                        mime_type=mime_type,
                    )

                    print()
                    print("=" * 70)
                    print("⚙️ RESPUESTA IMAGEN OPERACIONES")
                    print("=" * 70)

                    print(
                        answer
                    )

                    print("=" * 70)

                    safe_send_answer_for_current_state(
                        phone=phone,
                        answer=answer,
                        employee=employee,
                    )

                    # =========================================
                    # BORRAR ORIGINAL
                    #
                    # La imagen optimizada NO se borra.
                    # Está guardada en la sesión y será usada
                    # al confirmar el cierre.
                    # =========================================

                    if (
                        original_path
                        and str(
                            original_path
                        )
                        != str(
                            optimized_path
                        )
                    ):

                        delete_media_file(
                            original_path
                        )

                        original_path = None

                    return {
                        "status": "ok"
                    }

                except Exception as error:

                    print()
                    print("=" * 70)
                    print(
                        "❌ ERROR PROCESANDO FOTO "
                        "DE CIERRE OPERACIONAL"
                    )
                    print("=" * 70)

                    print(
                        type(error).__name__,
                        str(error),
                    )

                    print("=" * 70)

                    # =========================================
                    # SI HUBO ERROR, LIMPIAMOS ARCHIVOS
                    # =========================================

                    if original_path:

                        delete_media_file(
                            original_path
                        )

                    if (
                        optimized_path
                        and str(
                            optimized_path
                        )
                        != str(
                            original_path
                            or ""
                        )
                    ):

                        delete_media_file(
                            optimized_path
                        )

                    safe_send_whatsapp_message(
                        phone=phone,
                        message=(
                            "⚠️ Ocurrió un problema al recibir "
                            "la fotografía del cierre.\n\n"
                            "Puedes enviarla nuevamente."
                        ),
                    )

                    return {
                        "status": "ok"
                    }

            # =================================================
            # RUTA 2:
            # IMAGEN DEL AGENTE MAESTRO
            #
            # Solamente llegamos aquí si Operaciones NO está
            # esperando una de las fotos del cierre.
            # =================================================

            original_path = None
            optimized_path = None

            try:

                print()
                print("=" * 70)
                print("🧠 IMAGEN DIRIGIDA A AGENTE MAESTRO")
                print("=" * 70)

                media = download_media(
                    media_id=media_id,
                    phone=phone,
                    temporary=True,
                )

                if not isinstance(
                    media,
                    dict,
                ):

                    media = {}

                original_path = media.get(
                    "path"
                )

                if not original_path:

                    raise RuntimeError(
                        "No se obtuvo la ruta temporal "
                        "de la imagen."
                    )

                optimized_path = optimize_image(
                    file_path=original_path,
                    max_width=1600,
                    quality=75,
                )

                if not optimized_path:

                    raise RuntimeError(
                        "No se pudo generar "
                        "la imagen optimizada."
                    )

                optimized_path = str(
                    optimized_path
                )

                media[
                    "path"
                ] = optimized_path

                media[
                    "filename"
                ] = Path(
                    optimized_path
                ).name

                media[
                    "mime_type"
                ] = "image/jpeg"

                analysis = analyze_field_image(
                    file_path=optimized_path,
                    mime_type="image/jpeg",
                )

                if not isinstance(
                    analysis,
                    dict,
                ):

                    analysis = {}

                image_record = {

                    "media_id": media_id,

                    "filename": media.get(
                        "filename"
                    ),

                    "local_path": optimized_path,

                    "mime_type": "image/jpeg",

                    "caption": caption,

                    "description": (
                        analysis.get(
                            "description"
                        )
                        or ""
                    ),

                    "observed_conditions": (
                        analysis.get(
                            "observed_conditions",
                            []
                        )
                    ),

                    "possible_element": (
                        analysis.get(
                            "possible_element"
                        )
                    ),

                    "requires_confirmation": (
                        analysis.get(
                            "requires_confirmation",
                            []
                        )
                    ),
                }

                result = register_field_image(
                    phone=phone,
                    image_data=image_record,
                )

                if not isinstance(
                    result,
                    dict,
                ):

                    result = {
                        "saved": False,
                        "reason": "invalid_register_result",
                    }

                image_registered = bool(
                    result.get(
                        "saved"
                    )
                )

                if not image_registered:

                    reason = result.get(
                        "reason"
                    )

                    if caption:

                        answer = process_central_message(
                            phone=phone,
                            text=caption,
                            employee=employee,
                        )

                        safe_send_answer_for_current_state(
                            phone=phone,
                            answer=(
                                "📷 Recibí la imagen, pero no "
                                "pude asociarla al levantamiento.\n\n"
                                + answer
                            ),
                            employee=employee,
                        )

                        return {
                            "status": "ok"
                        }

                    if reason == "not_authorized":

                        safe_send_whatsapp_message(
                            phone=phone,
                            message=(
                                "📷 Recibí la imagen, pero tu perfil "
                                "no tiene permiso para asociar "
                                "fotografías a un levantamiento."
                            ),
                        )

                        return {
                            "status": "ok"
                        }

                    if reason in (
                        "missing_session",
                        "missing_quote",
                    ):

                        safe_send_whatsapp_message(
                            phone=phone,
                            message=(
                                "📷 Recibí la imagen, pero todavía "
                                "no existe un levantamiento activo "
                                "al cual asociarla.\n\n"
                                "Primero selecciona el servicio "
                                "que deseas trabajar."
                            ),
                        )

                        return {
                            "status": "ok"
                        }

                    if reason in (
                        "service_not_found",
                        "duplicate_service",
                        "service_lookup_error",
                    ):

                        safe_send_whatsapp_message(
                            phone=phone,
                            message=(
                                "⚠️ Recibí la imagen, pero no pude "
                                "localizar correctamente la Solicitud "
                                "de Servicio en Airtable.\n\n"
                                "La fotografía no quedó almacenada. "
                                "Puedes intentarlo nuevamente."
                            ),
                        )

                        return {
                            "status": "ok"
                        }

                    safe_send_whatsapp_message(
                        phone=phone,
                        message=(
                            "⚠️ No pude guardar la fotografía "
                            "en Airtable.\n\n"
                            "La imagen temporal fue eliminada. "
                            "Puedes intentarlo nuevamente."
                        ),
                    )

                    return {
                        "status": "ok"
                    }

                description = (
                    analysis.get(
                        "description"
                    )
                    or (
                        "Imagen registrada "
                        "sin descripción adicional."
                    )
                )

                count = result.get(
                    "count",
                    1,
                )

                message_text = (
                    "📷 *Imagen registrada*\n\n"
                    f"{description}\n\n"
                    f"Fotografías asociadas al levantamiento: "
                    f"{count}."
                )

                if caption:

                    answer = process_central_message(
                        phone=phone,
                        text=caption,
                        employee=employee,
                    )

                    message_text += (
                        "\n\n"
                        + answer
                    )

                safe_send_answer_for_current_state(
                    phone=phone,
                    answer=message_text,
                    employee=employee,
                )

                return {
                    "status": "ok"
                }

            except Exception as error:

                print()
                print("=" * 60)
                print("❌ ERROR PROCESANDO IMAGEN")
                print("=" * 60)

                print(
                    type(error).__name__,
                    str(error),
                )

                print("=" * 60)

                safe_send_whatsapp_message(
                    phone=phone,
                    message=(
                        "⚠️ Ocurrió un problema al procesar "
                        "la imagen.\n\n"
                        "La fotografía temporal no quedará "
                        "almacenada en el servidor.\n\n"
                        "Puedes intentar enviarla nuevamente."
                    ),
                )

                return {
                    "status": "ok"
                }

            finally:

                # =============================================
                # ESTA LIMPIEZA ES SOLO PARA AGENTE MAESTRO.
                #
                # Las fotos de Operaciones salen por return
                # antes de llegar a este bloque.
                # =============================================

                print()
                print("=" * 60)
                print("🧹 LIMPIEZA DE IMÁGENES TEMPORALES")
                print("=" * 60)

                if original_path:

                    delete_media_file(
                        original_path
                    )

                if (
                    optimized_path
                    and str(
                        optimized_path
                    )
                    != str(
                        original_path
                        or ""
                    )
                ):

                    delete_media_file(
                        optimized_path
                    )

                print("=" * 60)

        # ====================================================
        # 12. OTROS TIPOS
        # ====================================================

        print(
            "⚠️ Tipo no soportado:",
            message_type
        )

        safe_send_whatsapp_message(
            phone=phone,
            message=(
                "Por ahora puedo procesar mensajes "
                "de texto, botones, audios, imágenes "
                "y ubicación."
            ),
        )

        return {
            "status": "ok"
        }

    except Exception as error:

        print()
        print("=" * 60)
        print("❌ ERROR EN WEBHOOK")
        print("=" * 60)

        print(
            type(error).__name__,
            str(error),
        )

        print("=" * 60)

    return {
        "status": "ok"
    }


# ============================================================
# ENVÍO SEGURO DE BOTONES INTERACTIVOS
# ============================================================

def safe_send_whatsapp_buttons(
    phone: str,
    body: str,
    buttons: list,
    footer: str = "",
) -> bool:

    if not buttons:

        return False

    try:

        send_whatsapp_buttons(
            phone=phone,
            body=body,
            buttons=buttons,
            footer=footer,
        )

        print(
            "✅ Menú interactivo enviado por WhatsApp"
        )

        return True

    except Exception as error:

        print()
        print("=" * 60)
        print("⚠️ ERROR ENVIANDO BOTONES WHATSAPP")
        print("=" * 60)

        print(
            type(error).__name__,
            str(error),
        )

        print(
            "➡️ Se usará respuesta de texto como fallback."
        )

        print("=" * 60)

        return False


def safe_send_whatsapp_list(
    phone: str,
    body: str,
    list_config: dict,
) -> bool:

    if not isinstance(list_config, dict):
        return False

    try:
        send_whatsapp_list(
            phone=phone,
            body=body,
            rows=list_config.get("rows", []),
            button=list_config.get("button", "Seleccionar"),
            section_title=list_config.get(
                "section_title",
                "Opciones",
            ),
        )
        print("✅ Lista interactiva enviada por WhatsApp")
        return True
    except Exception as error:
        print()
        print("=" * 60)
        print("⚠️ ERROR ENVIANDO LISTA WHATSAPP")
        print("=" * 60)
        print(type(error).__name__, str(error))
        print("➡️ Se usará respuesta de texto como fallback.")
        print("=" * 60)
        return False


# ============================================================
# EXTRAER MENSAJE
# ============================================================

def extract_message(
    data: dict,
):

    if not isinstance(
        data,
        dict,
    ):

        return None

    entries = data.get(
        "entry",
        []
    )

    if not entries:

        return None

    first_entry = entries[
        0
    ]

    if not isinstance(
        first_entry,
        dict,
    ):

        return None

    changes = first_entry.get(
        "changes",
        []
    )

    if not changes:

        return None

    first_change = changes[
        0
    ]

    if not isinstance(
        first_change,
        dict,
    ):

        return None

    value = first_change.get(
        "value",
        {}
    )

    if not isinstance(
        value,
        dict,
    ):

        return None

    messages = value.get(
        "messages",
        []
    )

    if not messages:

        return None

    first_message = messages[
        0
    ]

    if not isinstance(
        first_message,
        dict,
    ):

        return None

    return first_message


# ============================================================
# IDENTIFICAR EMPLEADO
# ============================================================

def identify_employee(
    phone: str,
) -> dict:

    if (
        DEVELOPMENT_MODE
        and phone == TEST_PHONE
    ):

        print()
        print("=" * 70)
        print("🧪 MODO IMPERSONACIÓN")
        print("=" * 70)

        print(
            "WhatsApp real:",
            phone
        )

        print(
            "Teléfono que se desea simular:",
            TEST_IMPERSONATE_PHONE
        )

        if not TEST_IMPERSONATE_PHONE:

            return {
                "found": False,
                "message": (
                    "TEST_IMPERSONATE_PHONE "
                    "no está configurado."
                ),
            }

        employee = get_employee_by_phone(
            TEST_IMPERSONATE_PHONE
        )

        if not employee.get(
            "found"
        ):

            return {
                "found": False,
                "message": (
                    "El trabajador configurado para "
                    "la prueba no existe en RRHH2."
                ),
            }

        employee[
            "impersonated"
        ] = True

        employee[
            "development_mode"
        ] = True

        employee[
            "real_test_phone"
        ] = phone

        employee[
            "impersonated_phone"
        ] = TEST_IMPERSONATE_PHONE

        print()
        print(
            "✅ Trabajador simulado:",
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

        print("=" * 70)

        return employee

    employee = get_employee_by_phone(
        phone
    )

    if employee.get(
        "found"
    ):

        employee[
            "impersonated"
        ] = False

        employee[
            "development_mode"
        ] = False

        return employee

    return {
        "found": False,
        "message": (
            "No se encontró este teléfono "
            "en RRHH2."
        ),
    }


# ============================================================
# ENVÍO SEGURO
# ============================================================

def safe_send_whatsapp_location_request(
    phone: str,
    message: str,
) -> bool:

    try:
        send_whatsapp_location_request(
            phone=phone,
            body=message,
        )

        print(
            "✅ Solicitud de ubicación enviada por WhatsApp"
        )

        return True

    except Exception as error:
        print()
        print("=" * 60)
        print("⚠️ ERROR SOLICITANDO UBICACIÓN")
        print("=" * 60)
        print(
            type(error).__name__,
            str(error),
        )
        print("=" * 60)

        return False


def is_waiting_for_operations_location(
    phone: str,
) -> bool:

    operations_session = get_operations_session(
        phone
    )

    return bool(
        isinstance(
            operations_session,
            dict,
        )
        and operations_session.get(
            "action"
        ) == "START_SERVICE"
        and operations_session.get(
            "waiting_for"
        ) == "location"
    )


def safe_send_answer_for_current_state(
    phone: str,
    answer,
    employee: dict = None,
    source_text: str = "",
) -> bool:

    messages = normalize_outbound_messages(
        answer
    )

    if not messages:
        return False

    for prior_message in messages[:-1]:
        if not safe_send_whatsapp_message(
            phone=phone,
            message=prior_message,
        ):
            return False

    answer = messages[-1]

    operations_session = get_operations_session(
        phone
    )

    maestro_session = get_maestro_session(
        phone
    )

    if should_show_usage_notice(
        text=source_text,
        operations_session=operations_session,
        maestro_session=maestro_session,
    ):
        usage_notice = (
            "━━━━━━━━━━━━━━\n"
            "🛡️ *AVISO DE USO*\n"
            "━━━━━━━━━━━━━━\n\n"
            "🤖 Este asistente utiliza inteligencia artificial "
            "como apoyo operativo.\n\n"
            "La información generada debe ser revisada antes de "
            "considerarse definitiva.\n\n"
            "🔐 Durante el uso pueden procesarse mensajes, audios, "
            "imágenes, ubicación y datos asociados al servicio.\n\n"
            "📄 Los Términos de Servicio, Política de Privacidad y "
            "Aviso de Exención de Responsabilidad completos serán "
            "formalizados posteriormente."
        )

        if not safe_send_whatsapp_message(
            phone=phone,
            message=usage_notice,
        ):
            return False

        answer = (
            "🏗️ *MENÚ PRINCIPAL JCF*\n\n"
            "¿Qué deseas realizar?"
        )

    actions = build_contextual_actions(
        employee=(
            employee
            if isinstance(
                employee,
                dict,
            )
            else {}
        ),
        operations_session=operations_session,
        maestro_session=maestro_session,
        response_text=answer,
    )

    if actions.get(
        "request_location"
    ):

        location_message = build_location_request_message(
            session=operations_session,
        )

        sent = safe_send_whatsapp_location_request(
            phone=phone,
            message=location_message,
        )

        if sent:
            return True

    buttons = actions.get(
        "buttons",
        [],
    )

    list_config = actions.get("list")

    if list_config:
        body_parts = split_interactive_body(answer)
        for body_part in body_parts[:-1]:
            if not safe_send_whatsapp_message(
                phone=phone,
                message=body_part,
            ):
                return False

        answer = body_parts[-1]
        if safe_send_whatsapp_list(
            phone=phone,
            body=answer,
            list_config=list_config,
        ):
            return True

    if buttons:

        body_parts = split_interactive_body(
            answer
        )

        for body_part in body_parts[:-1]:
            if not safe_send_whatsapp_message(
                phone=phone,
                message=body_part,
            ):
                return False

        answer_text = body_parts[-1]
        answer = answer_text

        buttons_sent = safe_send_whatsapp_buttons(
            phone=phone,
            body=answer_text,
            buttons=buttons,
            footer=actions.get(
                "footer",
                "",
            ),
        )

        if buttons_sent:

            return True

    return safe_send_whatsapp_message(
        phone=phone,
        message=answer,
    )


def normalize_outbound_messages(
    answer,
) -> list:

    if isinstance(answer, dict):
        raw_messages = answer.get(
            "messages",
            [],
        )
    else:
        raw_messages = [answer]

    return [
        str(message).strip()
        for message in raw_messages
        if str(message or "").strip()
    ]


def split_interactive_body(
    body: str,
    limit: int = WHATSAPP_INTERACTIVE_BODY_LIMIT,
) -> list:

    text = str(body or "").strip()

    if not text:
        return ["Selecciona una opción."]

    if len(text) <= limit:
        return [text]

    chunks = []
    current_lines = []

    for line in text.splitlines():
        if len(line) > limit:
            raise ValueError(
                "Una línea individual excede el límite interactivo; "
                "no se recortará contenido."
            )

        candidate = "\n".join(
            current_lines + [line]
        ).strip()

        if current_lines and len(candidate) > limit:
            chunk = "\n".join(current_lines).strip()
            if chunk:
                chunks.append(chunk)
            current_lines = [line]
        else:
            current_lines.append(line)

    final_chunk = "\n".join(current_lines).strip()
    if final_chunk:
        chunks.append(final_chunk)

    # Si el último bloque contiene solo la indicación final, mover la
    # última pregunta completa a ese bloque para que los botones nunca
    # viajen en un mensaje auxiliar sin preguntas.
    if (
        len(chunks) > 1
        and not contains_numbered_question(chunks[-1])
        and contains_numbered_question(chunks[-2])
    ):
        previous_lines = chunks[-2].splitlines()
        question_index = next(
            (
                index
                for index in range(len(previous_lines) - 1, -1, -1)
                if re.match(r"^\*?\d+\.\*?\s", previous_lines[index].strip())
            ),
            None,
        )

        if question_index is not None:
            moved_lines = previous_lines[question_index:]
            candidate = (
                "\n".join(moved_lines).strip()
                + "\n\n"
                + chunks[-1]
            ).strip()
            remaining = "\n".join(
                previous_lines[:question_index]
            ).strip()

            if remaining and len(candidate) <= limit:
                chunks[-2] = remaining
                chunks[-1] = candidate

    return chunks


def contains_numbered_question(
    text: str,
) -> bool:

    return any(
        re.match(r"^\*?\d+\.\*?\s", line.strip())
        for line in str(text or "").splitlines()
    )


def safe_send_whatsapp_message(
    phone: str,
    message: str,
) -> bool:

    if not message:

        return False

    try:

        send_whatsapp_message(
            phone=phone,
            message=message,
        )

        print(
            "✅ Respuesta enviada por WhatsApp"
        )

        return True

    except Exception as error:

        print()
        print("=" * 60)
        print("⚠️ ERROR ENVIANDO RESPUESTA A WHATSAPP")
        print("=" * 60)

        print(
            type(error).__name__,
            str(error),
        )

        print("=" * 60)

        return False
