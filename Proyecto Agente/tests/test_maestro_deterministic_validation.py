import copy
import os
import unittest

from unittest.mock import patch

import dotenv


# Estas pruebas no leen el .env local ni llaman servicios externos.
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
    os.environ[
        name
    ] = "test-value"


from app.agents.maestro.service import (  # noqa: E402
    assign_service_to_session,
    ask_for_final_observations,
    get_operational_missing,
    initialize_session_context,
    is_service_change_request,
    prepare_report_for_save,
    process_field_report_message,
    register_audio_transcription,
    save_bulk_question_context,
)
from app.agents.central.service import (  # noqa: E402
    process_central_action,
    process_central_message,
)
from app.agents.maestro.session import (  # noqa: E402
    delete_session,
    get_session,
    save_session,
    start_session,
)
from app.agents.maestro.validation import (  # noqa: E402
    field_has_valid_value,
    get_required_missing,
    sanitize_report_data,
)
from app.whatsapp.interactive import (  # noqa: E402
    ACTION_BACK_HOME,
    ACTION_CLOSE_SERVICE,
    ACTION_RESUME_FIELD_SURVEY,
    BUTTON_BACK_HOME,
    BUTTON_RESUME_FIELD_SURVEY,
    build_contextual_actions,
)


def complete_report_data(
    external_required=False,
):

    data = {
        "cliente": "Cliente de prueba",
        "recinto": "Planta principal",
        "sector": "Sala de bombas",
        "tipo_trabajo": "Reemplazo de canalización",
        "descripcion": (
            "Cambiar la canalización deteriorada del sector"
        ),
        "dimensiones": {
            "largo_m": 20,
            "diametro_m": 0.025,
        },
        "estado_actual": "Canalización quebrada y con filtraciones",
        "materiales": [
            "PVC de 25 mm",
        ],
        "trabajos_requeridos": [
            "Retirar canalización existente",
            "Instalar canalización nueva",
        ],
        "equipamiento_necesario": [
            "Escalera",
            "Elementos de protección personal",
        ],
        "tiempo_estimado": "2 días",
        "jornada": "Diurna",
        "personal_requerido": 3,
        "empresa_externa_requerida": external_required,
        "prioridad": "Alta",
        "observaciones": [],
    }

    if external_required:

        data[
            "empresa_externa_detalle"
        ] = "Retiro de residuos"

    return data


def ai_result(
    extracted_data=None,
    ready=True,
    ask_observations=True,
):

    return {
        "intent": "continue_report",
        "possible_new_job": False,
        "extracted_data": extracted_data or {},
        "critical_missing": [],
        "recommended_missing": [],
        "optional_missing": [],
        "next_question": "Antes de generar, ¿algo más?",
        "ask_for_observations": ask_observations,
        "ready_for_report": ready,
    }


AUDIO_TECHNICAL_MESSAGE = (
    "Corresponde al cliente Falabella, en el recinto bodega, "
    "sector bodega 1. Se va a cambiar un portón y se requiere "
    "cambiar las bisagras. Las medidas son 64 metros por 3 de "
    "altura. El área está despejada y se necesitan bisagras "
    "laminadas de 3x4. No se requiere trabajo de intervención. "
    "El equipamiento necesario es una escalera y una soldadora. "
    "Tomará una hora, en jornada diurna, con el técnico y un "
    "ayudante. No se requiere empresa externa y la prioridad es media."
)


class MaestroDeterministicValidationTests(
    unittest.TestCase,
):

    phone = "maestro-validation-test"
    employee = {
        "record_id": "rec-supervisor",
        "nombre": "Supervisor Prueba",
        "cargo": "Supervisor",
    }

    def setUp(self):

        delete_session(
            self.phone
        )

        session = start_session(
            phone=self.phone,
            employee=self.employee,
        )
        initialize_session_context(
            session=session,
            employee=self.employee,
        )
        assign_service_to_session(
            session=session,
            service={
                "record_id": "rec-service",
                "quote_number": "COT12345 - Cotización",
                "oc": "OC-123",
                "status_label": "PROGRAMADO",
                "service_type": "Cotización",
            },
            reset_report=True,
        )
        save_session(
            self.phone,
            session,
        )
        save_bulk_question_context(
            phone=self.phone,
            session=session,
            missing=get_operational_missing(
                session.get(
                    "data",
                    {},
                )
            ),
        )

    def tearDown(self):

        delete_session(
            self.phone
        )

    @patch(
        "app.agents.operaciones.service.update_service_status_by_record_id"
    )
    @patch("app.agents.operaciones.service.create_activity_start")
    @patch("app.agents.maestro.service.start_session")
    def test_resume_button_preserves_progress_and_only_asks_missing_fields(
        self,
        start_maestro_session,
        create_activity_start,
        update_service_status,
    ):

        session = get_session(
            self.phone
        )
        session["data"] = complete_report_data()
        session["data"].pop("prioridad")
        session["critical_missing"] = get_operational_missing(
            session["data"]
        )
        session["pending_question_fields"] = ["prioridad"]
        session["last_question_field"] = "prioridad"
        session["data"]["imagenes"] = ["imagen-previa.jpg"]
        session["survey_images"] = ["imagen-procesada.jpg"]
        session["processed_audio"] = ["audio-previo.ogg"]
        save_session(
            self.phone,
            session,
        )

        before = copy.deepcopy(
            get_session(self.phone)
        )
        original_session_id = id(get_session(self.phone))

        blocked_response = process_central_action(
            phone=self.phone,
            action=ACTION_CLOSE_SERVICE,
            employee=self.employee,
        )
        blocked_session = get_session(
            self.phone
        )
        actions = build_contextual_actions(
            employee=self.employee,
            maestro_session=blocked_session,
            response_text=blocked_response,
        )

        self.assertIn("Levantamiento pendiente", blocked_response)
        self.assertEqual(blocked_session["status"], "paused")
        self.assertEqual(
            blocked_session["status_before_pause"],
            "active",
        )
        self.assertEqual(blocked_session["data"], before["data"])
        self.assertEqual(
            [button["id"] for button in actions["buttons"]],
            [
                BUTTON_RESUME_FIELD_SURVEY,
                BUTTON_BACK_HOME,
            ],
        )
        self.assertEqual(
            actions["buttons"][0]["title"],
            "Retomar",
        )

        response = process_central_action(
            phone=self.phone,
            action=ACTION_RESUME_FIELD_SURVEY,
            employee=self.employee,
        )

        resumed = get_session(
            self.phone
        )
        self.assertEqual(resumed["status"], "active")
        self.assertEqual(id(resumed), original_session_id)
        self.assertEqual(resumed["quote_number"], before["quote_number"])
        self.assertEqual(resumed["data"], before["data"])
        self.assertEqual(
            resumed["survey_images"],
            before["survey_images"],
        )
        self.assertEqual(
            resumed["processed_audio"],
            before["processed_audio"],
        )
        self.assertIn(
            "¿Qué prioridad tiene este trabajo? (Alta, media o baja)",
            response,
        )
        self.assertNotIn("¿En qué sector", response)
        start_maestro_session.assert_not_called()
        create_activity_start.assert_not_called()
        update_service_status.assert_not_called()

    @patch("app.agents.maestro.service.start_session")
    def test_close_with_empty_report_pauses_and_resumes_same_session(
        self,
        start_maestro_session,
    ):

        session = get_session(
            self.phone
        )
        session["data"] = {}
        session["critical_missing"] = get_operational_missing({})
        session["pending_question_fields"] = list(
            session["critical_missing"]
        )
        session["last_question_field"] = "sector"
        save_session(
            self.phone,
            session,
        )
        original_session_id = id(get_session(self.phone))

        process_central_action(
            phone=self.phone,
            action=ACTION_BACK_HOME,
            employee=self.employee,
        )
        self.assertEqual(
            get_session(self.phone)["status"],
            "paused",
        )

        response = process_central_action(
            phone=self.phone,
            action=ACTION_CLOSE_SERVICE,
            employee=self.employee,
        )

        preserved = get_session(
            self.phone
        )
        actions = build_contextual_actions(
            employee=self.employee,
            maestro_session=preserved,
            response_text=response,
        )

        self.assertIn("Levantamiento pendiente", response)
        self.assertIsNotNone(preserved)
        self.assertEqual(preserved["status"], "paused")
        self.assertEqual(preserved["status_before_pause"], "active")
        self.assertEqual(
            preserved["quote_number"],
            "COT12345 - Cotización",
        )
        self.assertEqual(
            [button["id"] for button in actions["buttons"]],
            [
                BUTTON_RESUME_FIELD_SURVEY,
                BUTTON_BACK_HOME,
            ],
        )

        resumed_response = process_central_action(
            phone=self.phone,
            action=ACTION_RESUME_FIELD_SURVEY,
            employee=self.employee,
        )
        resumed = get_session(self.phone)
        self.assertEqual(id(resumed), original_session_id)
        self.assertEqual(resumed["status"], "active")
        self.assertEqual(
            resumed["quote_number"],
            "COT12345 - Cotización",
        )
        self.assertIn("¿En qué sector", resumed_response)
        start_maestro_session.assert_not_called()

    @patch(
        "app.agents.maestro.service.analyze_message"
    )
    def test_vague_messages_cannot_complete_report(
        self,
        analyze,
    ):

        for message in (
            "Chao",
            "No sé",
            "Ok",
        ):

            with self.subTest(
                message=message
            ):

                analyze.return_value = ai_result(
                    extracted_data={
                        "tipo_trabajo": message,
                    },
                )

                response = process_field_report_message(
                    phone=self.phone,
                    text=message,
                    employee=self.employee,
                )

                session = get_session(
                    self.phone
                )

                self.assertFalse(
                    session[
                        "ready_for_report"
                    ]
                )
                self.assertFalse(
                    session[
                        "ask_for_observations"
                    ]
                )
                self.assertFalse(
                    field_has_valid_value(
                        session[
                            "data"
                        ],
                        "tipo_trabajo",
                    )
                )
                self.assertIn(
                    "Faltan algunos antecedentes",
                    response,
                )
                self.assertNotIn(
                    "Antes de generar el informe",
                    response,
                )

    @patch(
        "app.agents.maestro.service.analyze_message"
    )
    def test_only_job_type_and_description_leave_other_fields_pending(
        self,
        analyze,
    ):

        analyze.return_value = ai_result(
            extracted_data={
                "tipo_trabajo": "Cambio de canalización",
                "descripcion": (
                    "Reemplazar el tramo dañado de la canalización"
                ),
            },
        )

        response = process_field_report_message(
            phone=self.phone,
            text=(
                "Se requiere el reemplazo del tramo dañado de la canalización"
            ),
            employee=self.employee,
        )

        session = get_session(
            self.phone
        )

        self.assertNotIn(
            "tipo de trabajo",
            session[
                "critical_missing"
            ],
        )
        self.assertNotIn(
            "descripcion",
            session[
                "critical_missing"
            ],
        )
        self.assertIn(
            "tiempo estimado",
            session[
                "critical_missing"
            ],
        )
        self.assertIn(
            "¿Cuánto tiempo estimas",
            response,
        )

    @patch(
        "app.agents.maestro.service.analyze_message"
    )
    def test_complete_technical_data_asks_observations_only_then(
        self,
        analyze,
    ):

        technical_data = complete_report_data()
        technical_data.pop("cliente")
        technical_data.pop("recinto")
        analyze.return_value = ai_result(
            extracted_data=technical_data,
        )

        response = process_field_report_message(
            phone=self.phone,
            text=(
                "Entrego todos los antecedentes técnicos del trabajo"
            ),
            employee=self.employee,
        )

        session = get_session(
            self.phone
        )

        self.assertEqual(
            session[
                "critical_missing"
            ],
            [],
        )
        self.assertFalse(
            session[
                "ready_for_report"
            ]
        )
        self.assertTrue(
            session[
                "ask_for_observations"
            ]
        )
        self.assertIn(
            "Antes de generar el informe",
            response,
        )

    def test_cliente_and_recinto_are_optional(self):

        data = complete_report_data()
        data.pop("cliente")
        data.pop("recinto")

        missing = get_required_missing(
            data
        )

        self.assertNotIn("cliente", missing)
        self.assertNotIn("recinto", missing)
        self.assertEqual(missing, [])

    @patch("app.agents.maestro.service.show_service_list_again")
    @patch("app.agents.maestro.service.analyze_message")
    def test_active_session_technical_text_does_not_list_services(
        self,
        analyze,
        show_service_list,
    ):

        session = get_session(self.phone)
        session["quote_number"] = "COT38395"
        session["selected_service_id"] = "COT38395"
        save_session(self.phone, session)

        technical_text = (
            "Se requiere cambiar las bisagras de un portón "
            "en el sector bodega 1"
        )
        analyze.return_value = ai_result(
            extracted_data={
                "sector": "Bodega 1",
                "tipo_trabajo": "Cambio de bisagras de portón",
                "descripcion": technical_text,
            },
            ready=False,
            ask_observations=False,
        )

        response = process_field_report_message(
            phone=self.phone,
            text=technical_text,
            employee=self.employee,
        )

        show_service_list.assert_not_called()
        current = get_session(self.phone)
        self.assertEqual(current["quote_number"], "COT38395")
        self.assertEqual(current["selected_service_id"], "COT38395")
        self.assertEqual(
            current["data"]["tipo_trabajo"],
            "Cambio de bisagras de portón",
        )
        self.assertIn("Faltan algunos antecedentes", response)

    @patch("app.agents.maestro.service.show_service_list_again")
    @patch("app.agents.maestro.service.analyze_message")
    def test_active_session_audio_transcription_stays_in_current_report(
        self,
        analyze,
        show_service_list,
    ):

        session = get_session(self.phone)
        session["quote_number"] = "COT38395"
        session["selected_service_id"] = "COT38395"
        save_session(self.phone, session)

        analyze.return_value = ai_result(
            extracted_data=complete_report_data(),
        )

        register_audio_transcription(
            phone=self.phone,
            transcription=AUDIO_TECHNICAL_MESSAGE,
        )
        response = process_central_message(
            phone=self.phone,
            text=AUDIO_TECHNICAL_MESSAGE,
            employee=self.employee,
        )

        show_service_list.assert_not_called()
        current = get_session(self.phone)
        self.assertEqual(current["quote_number"], "COT38395")
        self.assertEqual(current["selected_service_id"], "COT38395")
        self.assertEqual(current["critical_missing"], [])
        self.assertTrue(current["ask_for_observations"])
        self.assertFalse(current["ready_for_report"])
        self.assertIn("Antes de generar el informe", response)

    def test_technical_change_words_are_not_service_change_requests(self):

        self.assertFalse(
            is_service_change_request(
                AUDIO_TECHNICAL_MESSAGE
            )
        )
        self.assertTrue(
            is_service_change_request(
                "Quiero cambiar de servicio"
            )
        )

    def test_no_observations_moves_to_generation_actions(self):

        session = get_session(
            self.phone
        )
        session[
            "data"
        ] = complete_report_data()
        save_session(
            self.phone,
            session,
        )

        ask_for_final_observations(
            phone=self.phone,
            session=session,
        )

        response = process_field_report_message(
            phone=self.phone,
            text="No tengo observaciones",
            employee=self.employee,
        )

        session = get_session(
            self.phone
        )

        self.assertEqual(
            session[
                "status"
            ],
            "ready_to_generate",
        )
        self.assertTrue(
            session[
                "ready_for_report"
            ]
        )
        self.assertIn(
            "generar el informe",
            response,
        )

    @patch(
        "app.agents.maestro.service.analyze_message"
    )
    def test_finish_before_completion_is_blocked(
        self,
        analyze,
    ):

        for message in (
            "Terminé",
            "Listo",
            "Eso es todo",
        ):

            with self.subTest(message=message):

                response = process_field_report_message(
                    phone=self.phone,
                    text=message,
                    employee=self.employee,
                )

                self.assertIn(
                    "Faltan algunos antecedentes",
                    response,
                )
                self.assertNotEqual(
                    get_session(
                        self.phone
                    )[
                        "status"
                    ],
                    "awaiting_save_confirmation",
                )

        analyze.assert_not_called()

    def test_external_company_false_needs_no_detail(self):

        data = complete_report_data(
            external_required=False,
        )

        self.assertNotIn(
            "servicio requerido de la empresa externa",
            get_required_missing(
                data
            ),
        )

    def test_external_company_true_requires_detail(self):

        data = complete_report_data(
            external_required=True,
        )
        data.pop(
            "empresa_externa_detalle"
        )

        self.assertIn(
            "servicio requerido de la empresa externa",
            get_required_missing(
                data
            ),
        )

    def test_external_company_accepts_natural_yes_and_no_answers(self):

        for message, expected in (
            (
                "No hace falta",
                False,
            ),
            (
                "Sí se requiere",
                True,
            ),
        ):

            with self.subTest(
                message=message
            ):

                sanitized = sanitize_report_data(
                    extracted_data={},
                    source_message=message,
                    expected_fields=[
                        "empresa_externa_requerida",
                    ],
                )

                self.assertIs(
                    sanitized[
                        "empresa_externa_requerida"
                    ],
                    expected,
                )

    @patch(
        "app.agents.maestro.service.analyze_message"
    )
    def test_vague_observation_answer_is_asked_again(
        self,
        analyze,
    ):

        session = get_session(
            self.phone
        )
        session[
            "data"
        ] = complete_report_data()
        save_session(
            self.phone,
            session,
        )

        ask_for_final_observations(
            phone=self.phone,
            session=session,
        )

        analyze.return_value = ai_result(
            extracted_data={},
            ready=True,
            ask_observations=False,
        )

        response = process_field_report_message(
            phone=self.phone,
            text="No sé",
            employee=self.employee,
        )

        session = get_session(
            self.phone
        )

        self.assertEqual(
            session[
                "status"
            ],
            "active",
        )
        self.assertFalse(
            session[
                "ready_for_report"
            ]
        )
        self.assertTrue(
            session[
                "ask_for_observations"
            ]
        )
        self.assertIn(
            "Antes de generar el informe",
            response,
        )

    def test_previous_valid_answers_are_not_requested_again(self):

        data = complete_report_data()
        data.pop(
            "prioridad"
        )

        missing = get_required_missing(
            data
        )

        self.assertEqual(
            missing,
            [
                "prioridad"
            ],
        )

    def test_explicit_no_aplica_is_valid_for_dimensions(self):

        sanitized = sanitize_report_data(
            extracted_data={
                "dimensiones": "No aplica",
            },
            source_message="Las dimensiones no aplican a este trabajo",
            expected_fields=[
                "dimensiones",
            ],
        )

        self.assertEqual(
            sanitized[
                "dimensiones"
            ],
            {
                "aplica": False,
            },
        )

    def test_ambiguous_no_aplica_does_not_fill_multiple_fields(self):

        sanitized = sanitize_report_data(
            extracted_data={
                "dimensiones": {
                    "aplica": False,
                },
                "materiales": [
                    "No aplica",
                ],
                "estado_actual": "No aplica",
            },
            source_message="No aplica",
            expected_fields=[
                "dimensiones",
                "materiales",
                "estado_actual",
            ],
        )

        self.assertEqual(
            sanitized,
            {},
        )

    def test_preview_gate_cannot_be_bypassed_directly(self):

        session = get_session(
            self.phone
        )

        response = prepare_report_for_save(
            phone=self.phone,
            session=session,
        )

        self.assertIn(
            "Faltan algunos antecedentes",
            response,
        )
        self.assertNotEqual(
            session[
                "status"
            ],
            "awaiting_save_confirmation",
        )
