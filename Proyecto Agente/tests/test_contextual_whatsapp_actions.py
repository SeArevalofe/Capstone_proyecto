cp /tmp/jcf_operations_service_text.py /app/agents/operaciones/service.py
import copy
import os
import tempfile
import unittest

from unittest.mock import patch

import dotenv


dotenv.load_dotenv = lambda *args, **kwargs: False

for name in (
    "OPENAI_API_KEY",
    "AIRTABLE_TOKEN",
    "AIRTABLE_EMPLOYEE_BASE_ID",
    "AIRTABLE_EMPLOYEE_TABLE_ID",
    "AIRTABLE_SERVICE_BASE_ID",
    "AIRTABLE_SERVICE_REQUEST_TABLE_ID",
    "AIRTABLE_SERVICE_CLOSURE_TABLE_ID",
    "WHATSAPP_ACCESS_TOKEN",
    "WHATSAPP_PHONE_NUMBER_ID",
    "WHATSAPP_VERIFY_TOKEN",
):
    os.environ[name] = "test-value"


from app.agents.central.service import (  # noqa: E402
    process_central_action,
    process_central_location,
    process_central_message,
)
from app.agents.maestro.service import (  # noqa: E402
    build_all_missing_questions,
    get_operational_missing,
    process_field_report_message,
    register_audio_transcription,
    reset_report_state,
)
from app.agents.maestro.session import (  # noqa: E402
    delete_session as delete_maestro_session,
    get_session as get_maestro_session,
    save_session as save_maestro_session,
    start_session as start_maestro_session,
)
from app.agents.operaciones.session import (  # noqa: E402
    clear_session as clear_operations_session,
    create_session as create_operations_session,
    get_session as get_operations_session,
    push_history as push_operations_history,
    save_session as save_operations_session,
)
from app.agents.operaciones.service import (  # noqa: E402
    build_validated_closure_sheet_message,
    process_operations_image,
)
from app.whatsapp.interactive import (  # noqa: E402
    ACTION_BACK_HOME,
    ACTION_CLOSE_ADD_MORE_PHOTOS,
    ACTION_CLOSE_CONFIRM_SAVE,
    ACTION_CLOSE_SERVICE,
    ACTION_NO_OBSERVATIONS,
    ACTION_REPORT_GENERATE,
    ACTION_REPORT_MODIFY,
    ACTION_START_SERVICE,
    BUTTON_BACK_HOME,
    BUTTON_CLOSE_ADD_MORE_PHOTOS,
    BUTTON_CLOSE_CONFIRM_SAVE,
    BUTTON_CLOSE_SERVICE,
    BUTTON_NO_OBSERVATIONS,
    BUTTON_REPORT_GENERATE,
    BUTTON_REPORT_MODIFY,
    BUTTON_START_SERVICE,
    build_contextual_actions,
)
from app.whatsapp.webhook import (  # noqa: E402
    safe_send_answer_for_current_state,
    safe_send_whatsapp_buttons,
    split_interactive_body,
)
from app.airtable.service_request_repository import (  # noqa: E402
    upload_field_image as upload_service_field_image,
)
from app.airtable.activity_repository import (  # noqa: E402
    find_activity_start_by_service,
    save_field_report_to_activity,
)
from app.airtable.service_closure_repository import (  # noqa: E402
    find_service_closure_by_service_record_id,
    sync_activity_report_to_closure,
    sync_report_to_closure_record,
    sync_report_to_existing_closure,
)
from app.config import (  # noqa: E402
    AIRTABLE_ACTIVITY_REPORT_FIELD,
    AIRTABLE_ACTIVITY_TABLE_ID,
    AIRTABLE_CLOSURE_INTERNAL_REPORT_FIELD,
    AIRTABLE_SERVICE_CLOSURE_TABLE_ID,
)


PHONE = "contextual-actions-test"
EMPLOYEE = {
    "record_id": "rec-supervisor",
    "nombre": "Supervisor Prueba",
    "cargo": "Supervisor",
}


def complete_data():

    return {
        "cliente": "Cliente",
        "recinto": "Planta",
        "sector": "Sala técnica",
        "tipo_trabajo": "Reparación de tubería",
        "descripcion": "Reemplazar el tramo con filtración",
        "dimensiones": {
            "largo_m": 20,
        },
        "estado_actual": "Tubería deteriorada",
        "materiales": [
            "PVC",
        ],
        "trabajos_requeridos": [
            "Retiro e instalación",
        ],
        "equipamiento_necesario": [
            "Escalera",
        ],
        "tiempo_estimado": "2 días",
        "jornada": "Diurna",
        "personal_requerido": 2,
        "empresa_externa_requerida": False,
        "prioridad": "Alta",
        "observaciones": [],
        "imagenes": [
            {
                "media_id": "media-test",
            },
        ],
    }


def ai_result(extracted_data):

    return {
        "intent": "modify_report",
        "possible_new_job": False,
        "extracted_data": extracted_data,
        "critical_missing": [],
        "recommended_missing": [],
        "optional_missing": [],
        "next_question": "",
        "ask_for_observations": False,
        "ready_for_report": True,
    }


class ContextualActionMenuTests(unittest.TestCase):

    def setUp(self):

        delete_maestro_session(PHONE)
        clear_operations_session(PHONE)

    def tearDown(self):

        delete_maestro_session(PHONE)
        clear_operations_session(PHONE)

    def test_main_menu_without_active_session(self):

        actions = build_contextual_actions(
            employee=EMPLOYEE,
        )

        self.assertEqual(
            [button["id"] for button in actions["buttons"]],
            [
                BUTTON_START_SERVICE,
                BUTTON_CLOSE_SERVICE,
            ],
        )

    @patch("app.whatsapp.webhook.safe_send_whatsapp_message")
    @patch("app.whatsapp.webhook.send_whatsapp_buttons")
    def test_hello_sends_main_menu_for_each_operational_role(
        self,
        send_buttons,
        send_text,
    ):

        send_text.return_value = True

        for role in ("Supervisor", "Técnico", "Ayudante"):
            with self.subTest(role=role):
                send_buttons.reset_mock()
                answer = process_central_message(
                    phone=PHONE,
                    text="hola",
                    employee={"nombre": "Matías", "cargo": role},
                )

                sent = safe_send_answer_for_current_state(
                    phone=PHONE,
                    answer=answer,
                    employee={"nombre": "Matías", "cargo": role},
                )

                self.assertTrue(sent)
                send_buttons.assert_called_once()
                self.assertEqual(
                    [
                        button["id"]
                        for button in send_buttons.call_args.kwargs[
                            "buttons"
                        ]
                    ],
                    [BUTTON_START_SERVICE, BUTTON_CLOSE_SERVICE],
                )

        send_text.assert_not_called()

    @patch("app.whatsapp.webhook.send_whatsapp_buttons")
    def test_safe_button_sender_calls_whatsapp_client(
        self,
        send_buttons,
    ):

        sent = safe_send_whatsapp_buttons(
            phone=PHONE,
            body="Selecciona una gestión",
            buttons=[
                {"id": BUTTON_START_SERVICE, "title": "Inicio"},
                {"id": BUTTON_CLOSE_SERVICE, "title": "Cierre"},
            ],
        )

        self.assertTrue(sent)
        send_buttons.assert_called_once()

    def test_active_operations_states_never_add_main_menu(self):

        waiting_states = (
            "location",
            "closure_observations",
            "closure_satisfaction",
            "closure_mitigation_cause",
            "closure_service_sheet_photo",
            "closure_service_photo",
            "closure_confirmation",
        )

        for waiting_for in waiting_states:
            with self.subTest(waiting_for=waiting_for):
                actions = build_contextual_actions(
                    employee=EMPLOYEE,
                    operations_session={
                        "status": "active",
                        "action": (
                            "START_SERVICE"
                            if waiting_for == "location"
                            else "CLOSE_SERVICE"
                        ),
                        "waiting_for": waiting_for,
                    },
                )
                ids = {
                    button["id"]
                    for button in actions.get("buttons", [])
                }
                self.assertNotIn(BUTTON_START_SERVICE, ids)
                self.assertNotIn(BUTTON_CLOSE_SERVICE, ids)

    def test_active_maestro_states_never_add_main_menu(self):

        sessions = (
            {"status": "active", "last_question_field": "cliente"},
            {
                "status": "active",
                "last_question_field": "observaciones",
            },
            {"status": "ready_to_generate"},
        )

        for session in sessions:
            with self.subTest(session=session):
                actions = build_contextual_actions(
                    employee=EMPLOYEE,
                    maestro_session=session,
                )
                ids = {
                    button["id"]
                    for button in actions.get("buttons", [])
                }
                self.assertNotIn(BUTTON_START_SERVICE, ids)
                self.assertNotIn(BUTTON_CLOSE_SERVICE, ids)

    def test_operations_flow_hides_global_menu(self):

        actions = build_contextual_actions(
            employee=EMPLOYEE,
            operations_session={
                "status": "active",
                "action": "START_SERVICE",
                "waiting_for": "helper_confirmation",
            },
        )

        self.assertEqual(actions["buttons"], [])
        self.assertFalse(actions["request_location"])

    def test_waiting_location_requests_native_location_only(self):

        actions = build_contextual_actions(
            employee=EMPLOYEE,
            operations_session={
                "status": "active",
                "action": "START_SERVICE",
                "waiting_for": "location",
            },
        )

        self.assertEqual(actions["buttons"], [])
        self.assertTrue(actions["request_location"])

    def test_closure_observations_expose_only_contextual_buttons(self):

        actions = build_contextual_actions(
            employee={"cargo": "Técnico"},
            operations_session={
                "status": "active",
                "action": "CLOSE_SERVICE",
                "waiting_for": "closure_observations",
            },
        )

        self.assertEqual(
            actions["buttons"],
            [
                {
                    "id": BUTTON_NO_OBSERVATIONS,
                    "title": "Sin observaciones",
                },
                {
                    "id": BUTTON_BACK_HOME,
                    "title": "← Volver al inicio",
                },
            ],
        )

    @patch("app.agents.central.service.process_maestro_action")
    def test_closure_no_observations_button_advances_to_sheet(
        self,
        process_maestro_action,
    ):

        session = create_operations_session(
            phone=PHONE,
            action="CLOSE_SERVICE",
        )
        session["cot"] = "COT38395"
        session["waiting_for"] = "closure_observations"
        save_operations_session(PHONE, session)

        response = process_central_action(
            phone=PHONE,
            action=ACTION_NO_OBSERVATIONS,
            employee={"cargo": "Técnico"},
        )

        current = get_operations_session(PHONE)
        self.assertEqual(
            current["closure_observations"],
            "Sin observaciones",
        )
        self.assertEqual(
            current["waiting_for"],
            "closure_service_sheet_photo",
        )
        self.assertIn("📄 Hoja de Cierre de Servicio", response)
        self.assertNotIn("escribe: *Sin observaciones*", response)
        process_maestro_action.assert_not_called()

    @patch("app.agents.central.service.process_field_report_message")
    @patch("app.agents.central.service.classify_message")
    def test_active_closure_consumes_text_observation_before_ai(
        self,
        classify_message,
        process_maestro,
    ):

        session = create_operations_session(
            phone=PHONE,
            action="CLOSE_SERVICE",
        )
        session["cot"] = "COT38395"
        session["waiting_for"] = "closure_observations"
        save_operations_session(PHONE, session)

        observation = (
            "Agregar que se debe pintar la soldadura de color verde"
        )
        response = process_central_message(
            phone=PHONE,
            text=observation,
            employee={"cargo": "Técnico"},
        )

        current = get_operations_session(PHONE)
        self.assertEqual(current["cot"], "COT38395")
        self.assertEqual(current["closure_observations"], observation)
        self.assertEqual(
            current["waiting_for"],
            "closure_service_sheet_photo",
        )
        self.assertIn("📄 Hoja de Cierre de Servicio", response)
        classify_message.assert_not_called()
        process_maestro.assert_not_called()

    @patch("app.agents.central.service.process_field_report_message")
    @patch("app.agents.central.service.classify_message")
    def test_active_closure_consumes_audio_transcription_before_ai(
        self,
        classify_message,
        process_maestro,
    ):

        session = create_operations_session(
            phone=PHONE,
            action="CLOSE_SERVICE",
        )
        session["cot"] = "COT38395"
        session["waiting_for"] = "closure_observations"
        save_operations_session(PHONE, session)

        transcription = "Se debe proteger y pintar la soldadura verde"
        register_audio_transcription(
            phone=PHONE,
            transcription=transcription,
        )
        response = process_central_message(
            phone=PHONE,
            text=transcription,
            employee={"cargo": "Técnico"},
        )

        current = get_operations_session(PHONE)
        self.assertEqual(current["cot"], "COT38395")
        self.assertEqual(current["closure_observations"], transcription)
        self.assertEqual(
            current["waiting_for"],
            "closure_service_sheet_photo",
        )
        self.assertIn("📄 Hoja de Cierre de Servicio", response)
        classify_message.assert_not_called()
        process_maestro.assert_not_called()

    @patch(
        "app.agents.operaciones.service."
        "get_active_services_for_employee"
    )
    @patch(
        "app.agents.operaciones.service."
        "get_programmed_services_for_employee"
    )
    def test_empty_start_leaves_no_session_and_close_can_begin(
        self,
        get_programmed,
        get_active,
    ):

        get_programmed.return_value = {"records": []}
        get_active.return_value = {
            "records": [
                {
                    "record_id": "rec-service",
                    "quote_number": "COT38395 - Cotización",
                    "service_type": "Cotización",
                }
            ]
        }

        start_response = process_central_action(
            phone=PHONE,
            action=ACTION_START_SERVICE,
            employee=EMPLOYEE,
        )

        self.assertIn("No tienes servicios *PROGRAMADO*", start_response)
        self.assertIsNone(get_operations_session(PHONE))

        close_response = process_central_action(
            phone=PHONE,
            action=ACTION_CLOSE_SERVICE,
            employee=EMPLOYEE,
        )

        current = get_operations_session(PHONE)
        self.assertEqual(current["action"], "CLOSE_SERVICE")
        self.assertEqual(current["waiting_for"], "cot_close")
        self.assertIn("COT38395 - Cotización", close_response)

    @patch(
        "app.agents.operaciones.service."
        "get_active_services_for_employee"
    )
    def test_empty_close_leaves_no_active_session(
        self,
        get_active,
    ):

        get_active.return_value = {"records": []}

        response = process_central_action(
            phone=PHONE,
            action=ACTION_CLOSE_SERVICE,
            employee=EMPLOYEE,
        )

        self.assertIn("No tienes servicios *ACTIVO*", response)
        self.assertIsNone(get_operations_session(PHONE))

    def test_closure_back_button_preserves_active_closure_session(self):

        session = create_operations_session(
            phone=PHONE,
            action="CLOSE_SERVICE",
        )
        session["waiting_for"] = "cot_close"
        save_operations_session(PHONE, session)
        push_operations_history(PHONE)

        session = get_operations_session(PHONE)
        session["cot"] = "COT38395"
        session["waiting_for"] = "closure_observations"
        save_operations_session(PHONE, session)

        process_central_action(
            phone=PHONE,
            action=ACTION_BACK_HOME,
            employee={"cargo": "Técnico"},
        )

        restored = get_operations_session(PHONE)
        self.assertEqual(restored["action"], "CLOSE_SERVICE")
        self.assertEqual(restored["waiting_for"], "cot_close")

    def test_validated_sheet_message_keeps_dynamic_signature_status(self):

        response = build_validated_closure_sheet_message(
            stamp_detected=True,
            signature_detected=False,
        )

        self.assertIn("• Timbre del cliente: ✅ Detectado", response)
        self.assertIn("• Firma: ⚠️ No confirmada", response)
        self.assertIn("📸 Evidencia del trabajo realizado", response)

    def test_maestro_states_expose_only_their_own_actions(self):

        cases = (
            (
                {
                    "status": "active",
                    "quote_number": "COT1 - Cotización",
                    "last_question_field": "cliente",
                },
                [BUTTON_BACK_HOME],
            ),
            (
                {
                    "status": "active",
                    "quote_number": "COT1 - Cotización",
                    "last_question_field": "observaciones",
                },
                [BUTTON_NO_OBSERVATIONS, BUTTON_BACK_HOME],
            ),
            (
                {
                    "status": "ready_to_generate",
                    "quote_number": "COT1 - Cotización",
                },
                [BUTTON_REPORT_MODIFY, BUTTON_REPORT_GENERATE],
            ),
        )

        for session, expected in cases:

            with self.subTest(status=session["status"]):

                actions = build_contextual_actions(
                    employee=EMPLOYEE,
                    maestro_session=session,
                )

                self.assertEqual(
                    [button["id"] for button in actions["buttons"]],
                    expected,
                )

    @patch("app.whatsapp.webhook.safe_send_whatsapp_message")
    @patch("app.whatsapp.webhook.safe_send_whatsapp_buttons")
    def test_webhook_sender_uses_contextual_buttons(
        self,
        send_buttons,
        send_text,
    ):

        send_buttons.return_value = True

        session = start_maestro_session(
            phone=PHONE,
            employee=EMPLOYEE,
        )
        session["quote_number"] = "COT1 - Cotización"
        session["last_question_field"] = "observaciones"
        save_maestro_session(PHONE, session)

        sent = safe_send_answer_for_current_state(
            phone=PHONE,
            answer="¿Quieres agregar observaciones?",
            employee=EMPLOYEE,
        )

        self.assertTrue(sent)
        send_text.assert_not_called()
        sent_buttons = send_buttons.call_args.kwargs["buttons"]
        self.assertEqual(
            [button["id"] for button in sent_buttons],
            [BUTTON_NO_OBSERVATIONS, BUTTON_BACK_HOME],
        )

    @patch("app.whatsapp.webhook.safe_send_whatsapp_message")
    @patch("app.whatsapp.webhook.safe_send_whatsapp_buttons")
    def test_structured_start_sends_operations_then_survey(
        self,
        send_buttons,
        send_text,
    ):

        send_text.return_value = True
        send_buttons.return_value = True
        session = start_maestro_session(PHONE, EMPLOYEE)
        session["quote_number"] = "COT38395 - Cotización"
        session["last_question_field"] = "sector"
        save_maestro_session(PHONE, session)

        sent = safe_send_answer_for_current_state(
            phone=PHONE,
            answer={
                "messages": [
                    "✅ Inicio de servicio registrado",
                    "✅ Levantamiento iniciado\n\n*1.* ¿En qué sector específico?",
                ],
            },
            employee=EMPLOYEE,
        )

        self.assertTrue(sent)
        send_text.assert_called_once_with(
            phone=PHONE,
            message="✅ Inicio de servicio registrado",
        )
        self.assertEqual(
            send_buttons.call_args.kwargs["body"],
            "✅ Levantamiento iniciado\n\n*1.* ¿En qué sector específico?",
        )
        self.assertEqual(
            send_buttons.call_args.kwargs["buttons"][0]["id"],
            BUTTON_BACK_HOME,
        )

    @patch("app.whatsapp.webhook.safe_send_whatsapp_message")
    @patch("app.whatsapp.webhook.safe_send_whatsapp_buttons")
    def test_questions_and_back_button_use_one_interactive_message(
        self,
        send_buttons,
        send_text,
    ):

        send_buttons.return_value = True
        session = start_maestro_session(PHONE, EMPLOYEE)
        session["quote_number"] = "COT38395 - Cotización"
        session["last_question_field"] = None
        save_maestro_session(PHONE, session)

        answer = (
            "👷 *Agente JCF*\n\n"
            "*Cotización*\n• COT38395 - Cotización\n\n"
            + build_all_missing_questions(
                get_operational_missing(session["data"]),
            )
        )

        self.assertLessEqual(len(answer), 1024)
        sent = safe_send_answer_for_current_state(
            phone=PHONE,
            answer=answer,
            employee=EMPLOYEE,
        )

        self.assertTrue(sent)
        send_text.assert_not_called()
        send_buttons.assert_called_once()
        self.assertEqual(send_buttons.call_args.kwargs["body"], answer)
        self.assertEqual(
            send_buttons.call_args.kwargs["buttons"][0]["id"],
            BUTTON_BACK_HOME,
        )

        combined_sent = "\n".join(
            [
                call.kwargs["message"]
                for call in send_text.call_args_list
            ]
            + [send_buttons.call_args.kwargs["body"]]
        )
        for index in range(1, 14):
            self.assertIn(f"*{index}.*", combined_sent)

        self.assertNotIn("¿A qué cliente", combined_sent)
        self.assertNotIn("¿En qué recinto", combined_sent)

    def test_oversize_interactive_body_splits_only_on_complete_lines(self):

        questions = [
            f"*{index}.* ¿Pregunta {index}? " + ("detalle " * 18)
            for index in range(1, 16)
        ]
        body = (
            "👷 *Agente JCF*\n\n"
            "*Faltan algunos antecedentes*\n\n"
            + "\n".join(questions)
            + "\n\nPuedes responder *todo junto* por texto o audio."
        )

        chunks = split_interactive_body(body)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 1024 for chunk in chunks))
        self.assertRegex(chunks[-1], r"\*\d+\.\*")

        combined = "\n".join(chunks)
        for index, question in enumerate(questions, start=1):
            self.assertEqual(combined.count(question.strip()), 1)
            self.assertEqual(combined.count(f"*{index}.*"), 1)

    @patch("app.whatsapp.webhook.safe_send_whatsapp_message")
    @patch("app.whatsapp.webhook.safe_send_whatsapp_buttons")
    def test_long_questions_put_buttons_on_last_question_block(
        self,
        send_buttons,
        send_text,
    ):

        send_buttons.return_value = True
        send_text.return_value = True
        session = start_maestro_session(PHONE, EMPLOYEE)
        session["quote_number"] = "COT38395 - Cotización"
        session["last_question_field"] = None
        save_maestro_session(PHONE, session)

        answer = "\n".join(
            f"*{index}.* ¿Pregunta {index}? " + ("detalle " * 18)
            for index in range(1, 16)
        ) + "\n\nPuedes responder *todo junto* por texto o audio."

        sent = safe_send_answer_for_current_state(
            phone=PHONE,
            answer=answer,
            employee=EMPLOYEE,
        )

        self.assertTrue(sent)
        self.assertGreaterEqual(send_text.call_count, 1)
        send_buttons.assert_called_once()
        self.assertLessEqual(
            len(send_buttons.call_args.kwargs["body"]),
            1024,
        )
        self.assertRegex(
            send_buttons.call_args.kwargs["body"],
            r"\*\d+\.\*",
        )

        combined = "\n".join(
            [
                call.kwargs["message"]
                for call in send_text.call_args_list
            ]
            + [send_buttons.call_args.kwargs["body"]]
        )
        for index in range(1, 16):
            self.assertEqual(combined.count(f"*{index}.*"), 1)


class ClosureMultiplePhotoTests(unittest.TestCase):

    phone = "closure-multiple-photo-test"
    employee = {
        "record_id": "rec-technician",
        "nombre": "Matias Alejandro Roa Mura",
        "cargo": "Técnico",
    }

    def setUp(self):

        clear_operations_session(self.phone)
        delete_maestro_session(self.phone)
        self.temp_directory = tempfile.TemporaryDirectory()

    def tearDown(self):

        clear_operations_session(self.phone)
        delete_maestro_session(self.phone)
        self.temp_directory.cleanup()

    def make_image(self, filename):

        path = os.path.join(
            self.temp_directory.name,
            filename,
        )

        with open(path, "wb") as image_file:
            image_file.write(b"test-image")

        return path

    def prepare_first_photo(self):

        session = create_operations_session(
            phone=self.phone,
            action="CLOSE_SERVICE",
        )
        session.update(
            {
                "cot": "COT38395",
                "service_record_id": "rec-service",
                "service_status": "ACTIVO",
                "closure_technician": "Matias Alejandro Roa Mura",
                "closure_technician_record_id": "rec-technician",
                "closure_helpers": [],
                "closure_helper_ids": [],
                "closure_observations": (
                    "Agregar que se debe pintar la soldadura "
                    "de color verde."
                ),
                "closure_service_sheet_path": self.make_image(
                    "closure-sheet.jpg"
                ),
                "closure_service_sheet_filename": "closure-sheet.jpg",
                "closure_service_sheet_mime_type": "image/jpeg",
                "closure_service_sheet_uploaded": False,
                "closure_sheet_is_valid": True,
                "closure_sheet_is_service_closure_sheet": True,
                "closure_sheet_stamp_detected": True,
                "closure_sheet_stamp_status": "detected",
                "closure_sheet_signature_detected": True,
                "waiting_for": "closure_service_photo",
            }
        )
        save_operations_session(
            self.phone,
            session,
        )

        first_photo = self.make_image(
            "work-1.jpg"
        )
        response = process_operations_image(
            phone=self.phone,
            employee=self.employee,
            file_path=first_photo,
            filename="work-1.jpg",
            mime_type="image/jpeg",
        )

        return first_photo, response

    def test_first_work_photo_shows_review_buttons(self):

        _, response = self.prepare_first_photo()
        session = get_operations_session(
            self.phone
        )
        actions = build_contextual_actions(
            employee=self.employee,
            operations_session=session,
        )

        self.assertIn("✅ Revisión del cierre", response)
        self.assertIn("Servicio: *COT38395*", response)
        self.assertIn("📄 Hoja de cierre: ✅ Validada", response)
        self.assertIn("Evidencias registradas: *1*", response)
        self.assertEqual(
            [button["id"] for button in actions["buttons"]],
            [
                BUTTON_CLOSE_CONFIRM_SAVE,
                BUTTON_CLOSE_ADD_MORE_PHOTOS,
            ],
        )

    @patch("app.agents.operaciones.service.update_service_status_by_record_id")
    @patch("app.agents.operaciones.service.save_service_closure_form")
    def test_add_more_photos_preserves_closure_without_saving(
        self,
        save_closure,
        update_status,
    ):

        first_photo, _ = self.prepare_first_photo()
        before = copy.deepcopy(
            get_operations_session(
                self.phone
            )
        )

        response = process_central_action(
            phone=self.phone,
            action=ACTION_CLOSE_ADD_MORE_PHOTOS,
            employee=self.employee,
        )

        current = get_operations_session(
            self.phone
        )
        self.assertEqual(current["waiting_for"], "additional_work_photo")
        self.assertEqual(current["cot"], before["cot"])
        self.assertEqual(
            current["service_record_id"],
            before["service_record_id"],
        )
        self.assertEqual(
            current["closure_observations"],
            before["closure_observations"],
        )
        self.assertEqual(
            current["closure_service_sheet_path"],
            before["closure_service_sheet_path"],
        )
        self.assertEqual(
            current["closure_service_photos"][0]["path"],
            first_photo,
        )
        self.assertIn("📸 Añadir evidencia", response)
        save_closure.assert_not_called()
        update_status.assert_not_called()

    @patch("app.agents.operaciones.service.build_service_list")
    @patch("app.agents.central.service.process_field_report_message")
    @patch("app.agents.central.service.classify_message")
    def test_additional_photos_append_and_remain_in_operations(
        self,
        classify_message,
        process_maestro,
        build_service_list,
    ):

        first_photo, _ = self.prepare_first_photo()
        process_central_action(
            phone=self.phone,
            action=ACTION_CLOSE_ADD_MORE_PHOTOS,
            employee=self.employee,
        )

        reminder = process_central_message(
            phone=self.phone,
            text="¿Dónde envío la siguiente foto?",
            employee=self.employee,
        )

        self.assertIn("📸 Añadir evidencia", reminder)
        classify_message.assert_not_called()
        process_maestro.assert_not_called()
        build_service_list.assert_not_called()

        second_photo = self.make_image(
            "work-2.jpg"
        )
        response = process_operations_image(
            phone=self.phone,
            employee=self.employee,
            file_path=second_photo,
            filename="work-2.jpg",
            mime_type="image/jpeg",
        )

        current = get_operations_session(
            self.phone
        )
        self.assertEqual(current["cot"], "COT38395")
        self.assertEqual(
            [photo["path"] for photo in current["closure_service_photos"]],
            [first_photo, second_photo],
        )
        self.assertEqual(current["service_photos_count"], 2)
        self.assertIn("Evidencias registradas: *2*", response)

        actions = build_contextual_actions(
            employee=self.employee,
            operations_session=current,
        )
        self.assertEqual(
            [button["id"] for button in actions["buttons"]],
            [
                BUTTON_CLOSE_CONFIRM_SAVE,
                BUTTON_CLOSE_ADD_MORE_PHOTOS,
            ],
        )

        process_central_action(
            phone=self.phone,
            action=ACTION_CLOSE_ADD_MORE_PHOTOS,
            employee=self.employee,
        )
        third_photo = self.make_image(
            "work-3.jpg"
        )
        process_operations_image(
            phone=self.phone,
            employee=self.employee,
            file_path=third_photo,
            filename="work-3.jpg",
            mime_type="image/jpeg",
        )

        current = get_operations_session(
            self.phone
        )
        self.assertEqual(current["cot"], "COT38395")
        self.assertEqual(
            [photo["path"] for photo in current["closure_service_photos"]],
            [first_photo, second_photo, third_photo],
        )
        self.assertEqual(current["service_photos_count"], 3)

    @patch("app.agents.operaciones.service.update_service_status_by_record_id")
    @patch("app.agents.operaciones.service.upload_service_photo")
    @patch("app.agents.operaciones.service.upload_service_sheet_photo")
    @patch("app.agents.operaciones.service.sync_activity_report_to_closure")
    @patch("app.agents.operaciones.service.save_service_closure_form")
    def test_confirm_save_uploads_every_accumulated_evidence(
        self,
        save_closure,
        sync_report,
        upload_sheet,
        upload_photo,
        update_status,
    ):

        first_photo, _ = self.prepare_first_photo()

        additional_photos = [
            self.make_image("work-2.jpg"),
            self.make_image("work-3.jpg"),
        ]

        for index, photo_path in enumerate(
            additional_photos,
            start=2,
        ):
            process_central_action(
                phone=self.phone,
                action=ACTION_CLOSE_ADD_MORE_PHOTOS,
                employee=self.employee,
            )
            process_operations_image(
                phone=self.phone,
                employee=self.employee,
                file_path=photo_path,
                filename=f"work-{index}.jpg",
                mime_type="image/jpeg",
            )

        save_closure.return_value = {
            "saved": True,
            "closure_record_id": "rec-closure",
        }
        sync_report.return_value = {
            "synced": False,
            "reason": "not_available",
        }
        upload_sheet.return_value = {
            "uploaded": True,
            "attachment_id": "att-sheet",
        }
        upload_photo.side_effect = [
            {
                "uploaded": True,
                "attachment_id": f"att-{index}",
            }
            for index in range(1, 4)
        ]
        update_status.return_value = {
            "updated": True,
            "record_id": "rec-service",
            "status": "PAUSADO",
        }

        response = process_central_action(
            phone=self.phone,
            action=ACTION_CLOSE_CONFIRM_SAVE,
            employee=self.employee,
        )

        save_closure.assert_called_once()
        upload_sheet.assert_called_once()
        self.assertEqual(upload_photo.call_count, 3)
        self.assertEqual(
            [
                call.kwargs["file_path"]
                for call in upload_photo.call_args_list
            ],
            [first_photo] + additional_photos,
        )
        self.assertIn("Cierre registrado correctamente", response)
        update_status.assert_called_once_with(
            service_record_id="rec-service",
            status="PAUSADO",
        )
        self.assertIsNone(get_operations_session(self.phone))

    @patch("app.agents.operaciones.service.update_service_status_by_record_id")
    @patch("app.agents.operaciones.service.save_service_closure_form")
    def test_failed_closure_does_not_pause_service(
        self,
        save_closure,
        update_status,
    ):

        self.prepare_first_photo()
        save_closure.return_value = {
            "saved": False,
            "reason": "airtable_create_failed",
        }

        response = process_central_action(
            phone=self.phone,
            action=ACTION_CLOSE_CONFIRM_SAVE,
            employee=self.employee,
        )

        update_status.assert_not_called()
        current = get_operations_session(self.phone)
        self.assertIsNotNone(current)
        self.assertEqual(current["service_status"], "ACTIVO")
        self.assertIsNone(current["closure_record_id"])
        self.assertIn("No pude crear el cierre", response)

    @patch("app.agents.operaciones.service.update_service_status_by_record_id")
    @patch("app.agents.operaciones.service.upload_service_photo")
    @patch("app.agents.operaciones.service.upload_service_sheet_photo")
    @patch("app.agents.operaciones.service.sync_activity_report_to_closure")
    @patch("app.agents.operaciones.service.save_service_closure_form")
    def test_partial_failure_retries_pause_without_duplicate_closure(
        self,
        save_closure,
        sync_report,
        upload_sheet,
        upload_photo,
        update_status,
    ):

        self.prepare_first_photo()
        save_closure.return_value = {
            "saved": True,
            "closure_record_id": "rec-closure",
        }
        sync_report.return_value = {
            "synced": False,
            "reason": "not_available",
        }
        upload_sheet.return_value = {
            "uploaded": True,
            "attachment_id": "att-sheet",
        }
        upload_photo.return_value = {
            "uploaded": True,
            "attachment_id": "att-work",
        }
        update_status.side_effect = [
            {
                "updated": False,
                "reason": "service_status_update_failed",
            },
            {
                "updated": True,
                "record_id": "rec-service",
                "status": "PAUSADO",
            },
        ]

        first_response = process_central_action(
            phone=self.phone,
            action=ACTION_CLOSE_CONFIRM_SAVE,
            employee=self.employee,
        )

        current = get_operations_session(self.phone)
        self.assertIsNotNone(current)
        self.assertEqual(current["closure_record_id"], "rec-closure")
        self.assertEqual(current["service_status"], "ACTIVO")
        self.assertTrue(current["service_pause_pending"])
        self.assertIn("estado operacional", first_response)

        second_response = process_central_action(
            phone=self.phone,
            action=ACTION_CLOSE_CONFIRM_SAVE,
            employee=self.employee,
        )

        save_closure.assert_called_once()
        upload_sheet.assert_called_once()
        upload_photo.assert_called_once()
        self.assertEqual(update_status.call_count, 2)
        for call in update_status.call_args_list:
            self.assertEqual(
                call.kwargs,
                {
                    "service_record_id": "rec-service",
                    "status": "PAUSADO",
                },
            )
        self.assertIn("Cierre registrado correctamente", second_response)
        self.assertIsNone(get_operations_session(self.phone))


class MaestroContextualWorkflowTests(unittest.TestCase):

    def setUp(self):

        delete_maestro_session(PHONE)
        clear_operations_session(PHONE)

        self.sync_closure_patcher = patch(
            "app.agents.maestro.service.sync_report_to_existing_closure"
        )
        self.sync_closure = self.sync_closure_patcher.start()
        self.sync_closure.return_value = {
            "synced": False,
            "reason": "closure_not_found",
        }

        session = start_maestro_session(
            phone=PHONE,
            employee=EMPLOYEE,
        )
        session["quote_number"] = "COT12345 - Cotización"
        session["selected_service_id"] = "COT12345 - Cotización"
        session["quote_record_id"] = "rec-service"
        save_maestro_session(PHONE, session)

    def tearDown(self):

        delete_maestro_session(PHONE)
        clear_operations_session(PHONE)
        self.sync_closure_patcher.stop()

    def _prepare_observations_question(self):

        session = get_maestro_session(PHONE)
        session["data"] = complete_data()
        session["critical_missing"] = []
        session["ask_for_observations"] = True
        session["last_question_field"] = "observaciones"
        session["pending_question_fields"] = []
        save_maestro_session(PHONE, session)
        return session

    def test_no_observations_button_moves_to_generate_actions(self):

        self._prepare_observations_question()

        response = process_central_action(
            phone=PHONE,
            action=ACTION_NO_OBSERVATIONS,
            employee=EMPLOYEE,
        )

        session = get_maestro_session(PHONE)

        self.assertEqual(session["status"], "ready_to_generate")
        self.assertEqual(
            session["data"]["observaciones"],
            ["Sin observaciones adicionales"],
        )
        self.assertIn("generar el informe", response)

    @patch("app.agents.maestro.service.analyze_message")
    def test_text_observation_moves_to_generate_actions(self, analyze):

        self._prepare_observations_question()
        analyze.return_value = ai_result(
            {
                "observaciones": [
                    "Existe una filtración menor",
                ],
            }
        )

        process_field_report_message(
            phone=PHONE,
            text="Existe una filtración menor",
            employee=EMPLOYEE,
        )

        session = get_maestro_session(PHONE)
        self.assertEqual(session["status"], "ready_to_generate")
        self.assertEqual(
            session["data"]["observaciones"],
            ["Existe una filtración menor"],
        )

    @patch("app.agents.maestro.service.analyze_message")
    def test_ready_report_does_not_require_finish_message(self, analyze):

        session = get_maestro_session(PHONE)
        session["data"] = complete_data()
        session["data"]["observaciones"] = [
            "Sin observaciones adicionales",
        ]
        session["critical_missing"] = []
        save_maestro_session(PHONE, session)
        analyze.return_value = ai_result({})

        response = process_field_report_message(
            phone=PHONE,
            text="La información entregada es correcta",
            employee=EMPLOYEE,
        )

        current = get_maestro_session(PHONE)
        self.assertEqual(current["status"], "ready_to_generate")
        self.assertNotIn("indicarme que terminaste", response)
        self.assertIn("generar el informe", response)

        actions = build_contextual_actions(
            employee=EMPLOYEE,
            maestro_session=current,
        )
        self.assertEqual(
            [button["id"] for button in actions["buttons"]],
            [BUTTON_REPORT_MODIFY, BUTTON_REPORT_GENERATE],
        )

    @patch("app.agents.maestro.service.analyze_message")
    def test_audio_transcription_uses_same_observation_flow(self, analyze):

        self._prepare_observations_question()
        analyze.return_value = ai_result(
            {
                "observaciones": [
                    "Acceso restringido durante la mañana",
                ],
            }
        )

        register_audio_transcription(
            phone=PHONE,
            transcription="Acceso restringido durante la mañana",
        )
        process_central_message(
            phone=PHONE,
            text="Observación: acceso restringido durante la mañana",
            employee=EMPLOYEE,
        )

        session = get_maestro_session(PHONE)
        self.assertEqual(session["status"], "ready_to_generate")
        self.assertEqual(
            session["data"]["observaciones"],
            ["Acceso restringido durante la mañana"],
        )

    @patch("app.agents.maestro.service.analyze_message")
    def test_modify_preserves_report_and_returns_to_generate_actions(
        self,
        analyze,
    ):

        session = self._prepare_observations_question()
        session["data"]["observaciones"] = ["Sin observaciones adicionales"]
        session["status"] = "ready_to_generate"
        session["last_question_field"] = "final_confirmation"
        save_maestro_session(PHONE, session)

        original_client = session["data"]["cliente"]
        original_images = copy.deepcopy(session["data"]["imagenes"])

        process_central_action(
            phone=PHONE,
            action=ACTION_REPORT_MODIFY,
            employee=EMPLOYEE,
        )

        analyze.return_value = ai_result(
            {
                "personal_requerido": 3,
            }
        )

        process_field_report_message(
            phone=PHONE,
            text="En realidad necesitamos 3 personas",
            employee=EMPLOYEE,
        )

        session = get_maestro_session(PHONE)
        self.assertEqual(session["status"], "ready_to_generate")
        self.assertEqual(session["data"]["personal_requerido"], 3)
        self.assertEqual(session["data"]["cliente"], original_client)
        self.assertEqual(session["data"]["imagenes"], original_images)

    @patch("app.agents.maestro.service.save_field_report_to_activity")
    def test_generate_saves_immediately_and_finishes_session(self, save_report):

        session = self._prepare_observations_question()
        session["data"]["observaciones"] = ["Sin observaciones adicionales"]
        session["status"] = "ready_to_generate"
        session["last_question_field"] = "final_confirmation"
        session["activity_record_id"] = "rec-activity"
        save_maestro_session(PHONE, session)

        save_report.return_value = {
            "saved": True,
            "record_id": "rec-activity",
            "save_mode": "new",
        }

        response = process_central_action(
            phone=PHONE,
            action=ACTION_REPORT_GENERATE,
            employee=EMPLOYEE,
        )

        save_report.assert_called_once()
        self.assertEqual(
            save_report.call_args.kwargs["activity_record_id"],
            "rec-activity",
        )
        self.assertEqual(
            save_report.call_args.kwargs["service_record_id"],
            "rec-service",
        )
        self.assertIsNone(get_maestro_session(PHONE))
        self.assertIn("Levantamiento guardado", response)
        self.assertNotIn("¿Deseas guardarlo?", response)
        self.sync_closure.assert_called_once()
        self.assertEqual(
            self.sync_closure.call_args.kwargs["report_text"],
            save_report.call_args.kwargs["report_text"],
        )
        self.assertNotIn("sincron", response.lower())

    @patch("app.agents.maestro.service.save_field_report_to_activity")
    def test_secondary_sync_failure_does_not_fail_main_report(self, save_report):

        session = self._prepare_observations_question()
        session["data"]["observaciones"] = ["Sin observaciones adicionales"]
        session["status"] = "ready_to_generate"
        session["activity_record_id"] = "rec-activity"
        save_maestro_session(PHONE, session)
        save_report.return_value = {
            "saved": True,
            "record_id": "rec-activity",
            "save_mode": "replace",
        }
        self.sync_closure.return_value = {
            "synced": False,
            "reason": "closure_report_update_error",
        }

        response = process_central_action(
            phone=PHONE,
            action=ACTION_REPORT_GENERATE,
            employee=EMPLOYEE,
        )

        self.assertIsNone(get_maestro_session(PHONE))
        self.assertIn("Levantamiento guardado", response)
        self.assertNotIn("cierre", response.lower())
        self.assertNotIn("sincron", response.lower())

    @patch("app.agents.maestro.service.save_field_report_to_activity")
    def test_generate_failure_preserves_session_for_retry(self, save_report):

        session = self._prepare_observations_question()
        session["data"]["observaciones"] = ["Sin observaciones adicionales"]
        session["status"] = "ready_to_generate"
        save_maestro_session(PHONE, session)

        save_report.return_value = {
            "saved": False,
            "reason": "airtable_update_failed",
            "status_code": 422,
        }

        response = process_central_action(
            phone=PHONE,
            action=ACTION_REPORT_GENERATE,
            employee=EMPLOYEE,
        )

        save_report.assert_called_once()
        preserved = get_maestro_session(PHONE)
        self.assertIsNotNone(preserved)
        self.assertEqual(preserved["status"], "ready_to_generate")
        self.assertEqual(preserved["data"], session["data"])
        self.assertIn("información sigue disponible", response)

    @patch("app.agents.maestro.service.save_field_report_to_activity")
    def test_generate_server_error_also_preserves_session(self, save_report):

        session = self._prepare_observations_question()
        session["data"]["observaciones"] = ["Sin observaciones adicionales"]
        session["status"] = "ready_to_generate"
        session["activity_record_id"] = "rec-activity"
        original_data = copy.deepcopy(session["data"])
        save_maestro_session(PHONE, session)
        save_report.return_value = {
            "saved": False,
            "reason": "airtable_update_exception",
            "status_code": 500,
        }

        response = process_central_action(
            phone=PHONE,
            action=ACTION_REPORT_GENERATE,
            employee=EMPLOYEE,
        )

        preserved = get_maestro_session(PHONE)
        self.assertEqual(preserved["status"], "ready_to_generate")
        self.assertEqual(preserved["data"], original_data)
        self.assertIn("No fue posible guardar", response)

    @patch("app.agents.maestro.service.save_field_report_to_activity")
    def test_repeated_generate_while_saving_does_not_write_again(
        self,
        save_report,
    ):

        session = self._prepare_observations_question()
        session["data"]["observaciones"] = ["Sin observaciones adicionales"]
        session["status"] = "saving_report"
        save_maestro_session(PHONE, session)

        response = process_central_action(
            phone=PHONE,
            action=ACTION_REPORT_GENERATE,
            employee=EMPLOYEE,
        )

        save_report.assert_not_called()
        self.assertIn("Guardado en curso", response)
        self.assertEqual(
            get_maestro_session(PHONE)["status"],
            "saving_report",
        )

    def test_back_home_and_resume_preserve_everything(self):

        session = get_maestro_session(PHONE)
        session["data"] = complete_data()
        session["data"].pop("prioridad")
        session["critical_missing"] = get_operational_missing(session["data"])
        session["last_question_field"] = "prioridad"
        session["pending_question_fields"] = ["prioridad"]
        save_maestro_session(PHONE, session)

        before = copy.deepcopy(session)

        process_central_action(
            phone=PHONE,
            action=ACTION_BACK_HOME,
            employee=EMPLOYEE,
        )

        paused = get_maestro_session(PHONE)
        self.assertEqual(paused["status"], "paused")
        self.assertEqual(paused["data"], before["data"])
        self.assertEqual(
            paused["pending_question_fields"],
            before["pending_question_fields"],
        )

        response = process_central_message(
            phone=PHONE,
            text="retomar levantamiento",
            employee=EMPLOYEE,
        )

        resumed = get_maestro_session(PHONE)
        self.assertEqual(resumed["status"], "active")
        self.assertEqual(resumed["data"], before["data"])
        self.assertIn(
            "¿Qué prioridad tiene este trabajo? (Alta, media o baja)",
            response,
        )
        self.assertNotIn("¿A qué cliente", response)

    def test_start_action_cannot_destroy_existing_progress(self):

        session = get_maestro_session(PHONE)
        session["data"] = complete_data()
        save_maestro_session(PHONE, session)
        before = copy.deepcopy(session["data"])

        response = process_central_action(
            phone=PHONE,
            action=ACTION_START_SERVICE,
            employee=EMPLOYEE,
        )

        self.assertIn("Levantamiento protegido", response)
        self.assertEqual(get_maestro_session(PHONE)["data"], before)

    def test_stale_global_button_cannot_replace_operations_flow(self):

        delete_maestro_session(PHONE)
        operations = create_operations_session(
            phone=PHONE,
            action="START_SERVICE",
        )
        operations["waiting_for"] = "helper_confirmation"

        response = process_central_action(
            phone=PHONE,
            action=ACTION_START_SERVICE,
            employee=EMPLOYEE,
        )

        self.assertIn("proceso operacional activo", response)
        current = get_operations_session(PHONE)
        self.assertEqual(current["action"], "START_SERVICE")
        self.assertEqual(current["waiting_for"], "helper_confirmation")

    def test_accidental_location_does_not_change_maestro_session(self):

        session = get_maestro_session(PHONE)
        session["data"] = complete_data()
        session["critical_missing"] = []
        save_maestro_session(PHONE, session)
        before = copy.deepcopy(session)

        response = process_central_location(
            phone=PHONE,
            employee=EMPLOYEE,
            latitude=-33.4,
            longitude=-70.6,
        )

        after = get_maestro_session(PHONE)
        self.assertEqual(after, before)
        self.assertIn("no te he solicitado una ubicación", response)


class SurveyPersistenceRepositoryTests(unittest.TestCase):

    def test_reset_report_clears_previous_activity_record(self):

        session = {
            "activity_record_id": "rec-old-activity",
            "data": {},
        }

        reset_report_state(session)

        self.assertIsNone(session["activity_record_id"])

    @patch("app.airtable.activity_repository.find_activity_start_by_service")
    @patch("app.airtable.activity_repository.update_record")
    def test_report_saves_on_exact_activity_record(
        self,
        update_record,
        find_activity,
    ):

        update_record.return_value = {"updated": True}

        with patch(
            "app.airtable.service_closure_repository.save_service_closure_form"
        ) as closure_save:
            result = save_field_report_to_activity(
                activity_record_id="rec-activity",
                service_record_id="rec-service",
                service_identifier="COT12345 - Cotización",
                report_text="Informe final",
            )

        closure_save.assert_not_called()

        self.assertTrue(result["saved"])
        self.assertEqual(result["record_id"], "rec-activity")
        find_activity.assert_not_called()
        self.assertEqual(
            update_record.call_args.kwargs["table_id"],
            AIRTABLE_ACTIVITY_TABLE_ID,
        )
        self.assertEqual(
            update_record.call_args.kwargs["record_id"],
            "rec-activity",
        )
        self.assertEqual(
            update_record.call_args.kwargs["fields"],
            {
                AIRTABLE_ACTIVITY_REPORT_FIELD: "Informe final",
            },
        )
        self.assertNotEqual(AIRTABLE_ACTIVITY_TABLE_ID, "tbldFExZgKAHyLdvH")
        self.assertNotEqual(AIRTABLE_ACTIVITY_TABLE_ID, "tblrtCdwiR1sYOb48")

    @patch("app.airtable.activity_repository.update_record")
    @patch("app.airtable.activity_repository.find_activity_start_by_service")
    def test_report_fallback_uses_exact_service_identifier(
        self,
        find_activity,
        update_record,
    ):

        find_activity.return_value = {
            "found": True,
            "record_id": "rec-activity-oc",
        }
        update_record.return_value = {"updated": True}

        result = save_field_report_to_activity(
            service_record_id="rec-service-oc",
            service_identifier="COT37373 - OC",
            report_text="Informe OC",
        )

        self.assertTrue(result["saved"])
        find_activity.assert_called_once_with(
            service_record_id="rec-service-oc",
            cot="COT37373 - OC",
        )
        self.assertEqual(
            update_record.call_args.kwargs["record_id"],
            "rec-activity-oc",
        )

    @patch("app.airtable.activity_repository.get_records")
    def test_activity_lookup_uses_exact_full_id_and_service_link(
        self,
        get_records,
    ):

        get_records.return_value = {
            "records": [
                {
                    "id": "rec-activity-oc",
                    "fields": {
                        "ID Cuadro": ["rec-service-oc"],
                    },
                },
                {
                    "id": "rec-wrong-link",
                    "fields": {
                        "ID Cuadro": ["rec-other-service"],
                    },
                },
            ]
        }

        result = find_activity_start_by_service(
            service_record_id="rec-service-oc",
            cot="COT37373 - OC",
        )

        self.assertTrue(result["found"])
        self.assertEqual(result["record_id"], "rec-activity-oc")
        formula = get_records.call_args.kwargs["params"]["filterByFormula"]
        self.assertIn("{ID Registro}", formula)
        self.assertIn("COT37373 - OC", formula)
        self.assertNotIn("FIND(", formula)

    @patch("app.airtable.service_request_repository.find_closure_for_service")
    @patch("app.airtable.service_request_repository.upload_attachment")
    @patch("app.airtable.service_request_repository.get_record_by_id")
    def test_survey_image_uses_service_request_without_closure_lookup(
        self,
        get_record,
        upload_attachment,
        find_closure,
    ):

        get_record.return_value = {
            "found": True,
            "record_id": "rec-service",
            "record": {"id": "rec-service", "fields": {}},
        }
        upload_attachment.return_value = {
            "uploaded": True,
            "attachment_id": "att-test",
        }

        with tempfile.NamedTemporaryFile() as image_file:
            result = upload_service_field_image(
                quote_number="COT12345 - Cotización",
                record_id="rec-service",
                file_path=image_file.name,
            )

        self.assertTrue(result["uploaded"])
        self.assertEqual(result["service_record_id"], "rec-service")
        find_closure.assert_not_called()
        self.assertEqual(
            upload_attachment.call_args.kwargs["record_id"],
            "rec-service",
        )


class ClosureReportSynchronizationTests(unittest.TestCase):

    @patch("app.airtable.service_closure_repository.get_records")
    def test_closure_lookup_uses_one_filtered_request(self, get_records):

        get_records.return_value = {
            "records": [
                {
                    "id": "rec-closure",
                    "fields": {
                        "fldzA9Zub8a9ihoZe": ["rec-service"],
                    },
                },
            ],
            "offset": "must-not-be-followed",
        }

        result = find_service_closure_by_service_record_id(
            service_record_id="rec-service",
            service_identifier="COT38395",
        )

        self.assertTrue(result["found"])
        self.assertEqual(result["record_id"], "rec-closure")
        get_records.assert_called_once()
        params = get_records.call_args.kwargs["params"]
        self.assertEqual(params["maxRecords"], 1)
        self.assertEqual(params["pageSize"], 1)
        self.assertIn("{Servicio que Cierra}", params["filterByFormula"])
        self.assertIn("COT38395", params["filterByFormula"])
        self.assertNotIn("offset", params)

    @patch("app.airtable.service_closure_repository.update_record")
    def test_internal_report_uses_exact_destination_field(self, update_record):

        update_record.return_value = {"updated": True}

        result = sync_report_to_closure_record(
            closure_record_id="rec-closure",
            report_text="Informe final exacto",
        )

        self.assertTrue(result["synced"])
        self.assertEqual(
            update_record.call_args.kwargs,
            {
                "base_id": update_record.call_args.kwargs["base_id"],
                "table_id": AIRTABLE_SERVICE_CLOSURE_TABLE_ID,
                "record_id": "rec-closure",
                "fields": {
                    AIRTABLE_CLOSURE_INTERNAL_REPORT_FIELD: (
                        "Informe final exacto"
                    ),
                },
            },
        )
        self.assertEqual(
            AIRTABLE_CLOSURE_INTERNAL_REPORT_FIELD,
            "Informe Levantamientos WSP",
        )

    @patch("app.airtable.service_closure_repository.sync_report_to_closure_record")
    @patch("app.airtable.service_closure_repository.find_service_closure_by_service_record_id")
    def test_missing_closure_does_not_create_or_update(
        self,
        find_closure,
        sync_record,
    ):

        find_closure.return_value = {
            "found": False,
            "reason": "closure_not_found",
        }

        result = sync_report_to_existing_closure(
            service_record_id="rec-service",
            service_identifier="COT38395",
            report_text="Informe principal",
        )

        self.assertFalse(result["synced"])
        self.assertEqual(result["reason"], "closure_not_found")
        sync_record.assert_not_called()

    @patch("app.airtable.service_closure_repository.sync_report_to_closure_record")
    @patch("app.airtable.activity_repository.get_field_report_from_activity")
    def test_real_closure_copies_saved_activity_report(
        self,
        get_report,
        sync_record,
    ):

        get_report.return_value = {
            "found": True,
            "report_text": "Mismo informe guardado",
        }
        sync_record.return_value = {"synced": True}

        result = sync_activity_report_to_closure(
            closure_record_id="rec-closure",
            service_record_id="rec-service-oc",
            service_identifier="COT37910 - OC",
        )

        self.assertTrue(result["synced"])
        get_report.assert_called_once_with(
            service_record_id="rec-service-oc",
            service_identifier="COT37910 - OC",
        )
        sync_record.assert_called_once_with(
            closure_record_id="rec-closure",
            report_text="Mismo informe guardado",
        )


if __name__ == "__main__":
    unittest.main()
