import os
import sys
import tempfile
import types
import unittest

from unittest.mock import patch

import dotenv


dotenv.load_dotenv = lambda *args, **kwargs: False


class _OpenAIStub:

    def __init__(self, *args, **kwargs):
        pass


sys.modules["openai"] = types.SimpleNamespace(OpenAI=_OpenAIStub)

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
    process_central_message,
)
from app.agents.operaciones.service import (  # noqa: E402
    MITIGATION_CAUSES,
    build_service_list,
    process_operations_image,
    process_operations_message,
    select_service_for_closure,
)
from app.agents.operaciones.session import (  # noqa: E402
    clear_session,
    create_session,
    get_session,
    save_session,
)
from app.airtable.service_closure_repository import (  # noqa: E402
    save_service_closure_form,
)
from app.airtable.activity_repository import (  # noqa: E402
    get_field_report_from_activity,
)
from app.config import (  # noqa: E402
    AIRTABLE_CLOSURE_MITIGATION_CAUSE_FIELD,
    AIRTABLE_CLOSURE_OBSERVATIONS_FIELD,
)
from app.whatsapp.interactive import (  # noqa: E402
    ACTION_CLOSURE_SATISFIED_NO,
    ACTION_CLOSURE_SATISFIED_YES,
    ACTION_MITIGATION_CAUSE_MATERIALS,
    BUTTON_CLOSURE_SATISFIED_NO,
    BUTTON_CLOSURE_SATISFIED_YES,
    build_contextual_actions,
)


PHONE = "technician-closure-outcome"
TECHNICIAN = {
    "record_id": "rec-technician",
    "nombre": "Técnico Prueba",
    "cargo": "Técnico",
}
SUPERVISOR = {
    "record_id": "rec-supervisor",
    "nombre": "Supervisor Prueba",
    "cargo": "Supervisor",
}


def service_context(service_type="OC"):
    return {
        "found": True,
        "record_id": "rec-service",
        "quote_number": f"COT38395 - {service_type}",
        "cot": "COT38395",
        "oc": "OC-123",
        "status": "ACTIVO",
        "service_type": service_type,
        "helpers": [],
    }


class TechnicianClosureOutcomeTests(unittest.TestCase):

    def setUp(self):
        clear_session(PHONE)
        self.temp_directory = tempfile.TemporaryDirectory()

    def tearDown(self):
        clear_session(PHONE)
        self.temp_directory.cleanup()

    def image(self, name):
        path = os.path.join(self.temp_directory.name, name)
        with open(path, "wb") as image_file:
            image_file.write(b"image")
        return path

    @patch("app.agents.operaciones.service.get_field_report_from_activity")
    @patch(
        "app.agents.operaciones.service.get_operational_service_context"
    )
    def test_supervisor_keeps_existing_observation_flow(
        self,
        get_context,
        get_report,
    ):
        get_context.return_value = service_context("Cotización")
        get_report.return_value = {
            "found": True,
            "report_text": "Informe guardado",
        }
        response = select_service_for_closure(
            phone=PHONE,
            cot="COT38395 - Cotización",
            employee=SUPERVISOR,
            service_record_id="rec-service",
        )
        session = get_session(PHONE)
        self.assertEqual(session["waiting_for"], "closure_observations")
        self.assertIn("Observaciones del cierre", response)
        self.assertNotIn("culminado de forma satisfactoria", response)

    @patch("app.agents.operaciones.service.get_field_report_from_activity")
    @patch("app.agents.operaciones.service.get_active_services_for_employee")
    def test_supervisor_close_list_only_includes_saved_reports(
        self,
        get_active,
        get_report,
    ):
        get_active.return_value = {
            "records": [
                {
                    "record_id": "rec-service",
                    "quote_number": "COT38395 - Cotización",
                    "service_type": "COTIZACION",
                }
            ]
        }

        get_report.return_value = {
            "found": False,
            "reason": "empty_activity_report",
        }
        services, response = build_service_list(
            SUPERVISOR,
            "CLOSE_SERVICE",
        )

        self.assertEqual(services, [])
        self.assertIn("Levantamiento pendiente", response)
        get_report.assert_called_once_with(
            service_record_id="rec-service",
            service_identifier="COT38395 - Cotización",
            technician_record_id="rec-supervisor",
        )

        get_report.reset_mock()
        get_report.return_value = {
            "found": True,
            "report_text": "Informe guardado",
        }
        services, response = build_service_list(
            SUPERVISOR,
            "CLOSE_SERVICE",
        )

        self.assertEqual(
            [service["identifier"] for service in services],
            ["COT38395 - Cotización"],
        )
        self.assertIn("COT38395 - Cotización", response)

    @patch("app.agents.operaciones.service.get_field_report_from_activity")
    @patch(
        "app.agents.operaciones.service.get_operational_service_context"
    )
    def test_supervisor_cannot_bypass_pending_report_on_direct_selection(
        self,
        get_context,
        get_report,
    ):
        get_context.return_value = service_context("Cotización")
        get_report.return_value = {
            "found": False,
            "reason": "empty_activity_report",
        }

        response = select_service_for_closure(
            phone=PHONE,
            cot="COT38395 - Cotización",
            employee=SUPERVISOR,
            service_record_id="rec-service",
        )

        self.assertIn("📋 Levantamiento pendiente", response)
        self.assertIn("*COT38395 - Cotización*", response)
        self.assertIsNone(get_session(PHONE))

    @patch("app.agents.operaciones.service.get_field_report_from_activity")
    @patch(
        "app.agents.operaciones.service.get_operational_service_context"
    )
    def test_supervisor_airtable_error_blocks_closure_safely(
        self,
        get_context,
        get_report,
    ):
        get_context.return_value = service_context("Cotización")
        get_report.side_effect = TimeoutError("Airtable timeout")

        response = select_service_for_closure(
            phone=PHONE,
            cot="COT38395 - Cotización",
            employee=SUPERVISOR,
            service_record_id="rec-service",
        )

        self.assertIn("Levantamiento pendiente", response)
        self.assertIsNone(get_session(PHONE))

    @patch("app.agents.operaciones.service.get_field_report_from_activity")
    @patch(
        "app.agents.operaciones.service.get_operational_service_context"
    )
    def test_technician_and_helper_do_not_query_field_report(
        self,
        get_context,
        get_report,
    ):
        helper = {
            "record_id": "rec-helper",
            "nombre": "Ayudante Prueba",
            "cargo": "Ayudante",
        }
        get_context.return_value = service_context("OC")

        for employee in (TECHNICIAN, helper):
            with self.subTest(cargo=employee["cargo"]):
                clear_session(PHONE)
                response = select_service_for_closure(
                    phone=PHONE,
                    cot="COT38395 - OC",
                    employee=employee,
                    service_record_id="rec-service",
                )
                self.assertIn("¿El servicio fue culminado", response)

        get_report.assert_not_called()

    @patch("app.airtable.activity_repository.find_activity_start_by_service")
    def test_saved_report_must_belong_to_authenticated_supervisor(
        self,
        find_activity,
    ):
        find_activity.return_value = {
            "found": True,
            "record_id": "rec-activity",
            "fields": {
                "Tecnico": ["rec-other-supervisor"],
                "Levantamientos WSP": "Informe de otra persona",
            },
        }

        result = get_field_report_from_activity(
            service_record_id="rec-service",
            service_identifier="COT38395 - Cotización",
            technician_record_id="rec-supervisor",
        )

        self.assertFalse(result["found"])
        self.assertEqual(result["reason"], "activity_technician_mismatch")
        find_activity.assert_called_once_with(
            service_record_id="rec-service",
            cot="COT38395 - Cotización",
        )

    @patch("app.airtable.activity_repository.get_records")
    def test_report_from_another_service_does_not_enable_closure(
        self,
        get_records,
    ):
        get_records.return_value = {
            "records": [
                {
                    "id": "rec-other-activity",
                    "fields": {
                        "ID Cuadro": ["rec-other-service"],
                        "Tecnico": ["rec-supervisor"],
                        "Levantamientos WSP": "Otro informe",
                    },
                }
            ]
        }

        result = get_field_report_from_activity(
            service_record_id="rec-service",
            service_identifier="COT38395 - Cotización",
            technician_record_id="rec-supervisor",
        )

        self.assertFalse(result["found"])
        params = get_records.call_args.kwargs["params"]
        self.assertEqual(params["maxRecords"], 2)
        self.assertEqual(params["pageSize"], 2)

    @patch(
        "app.agents.operaciones.service.get_operational_service_context"
    )
    def test_technician_gets_stable_yes_no_buttons(self, get_context):
        get_context.return_value = service_context("OC")
        response = select_service_for_closure(
            phone=PHONE,
            cot="COT38395 - OC",
            employee=TECHNICIAN,
            service_record_id="rec-service",
        )
        session = get_session(PHONE)
        actions = build_contextual_actions(
            employee=TECHNICIAN,
            operations_session=session,
        )
        self.assertIn("¿El servicio fue culminado", response)
        self.assertEqual(session["service_type"], "OC")
        self.assertEqual(
            [button["id"] for button in actions["buttons"]],
            [
                BUTTON_CLOSURE_SATISFIED_YES,
                BUTTON_CLOSURE_SATISFIED_NO,
            ],
        )

    def prepare_satisfaction(self, service_type):
        session = create_session(PHONE, "CLOSE_SERVICE")
        session.update(
            {
                "cot": f"COT38395 - {service_type}",
                "service_record_id": "rec-service",
                "service_type": service_type,
                "service_status": "ACTIVO",
                "waiting_for": "closure_satisfaction",
            }
        )
        save_session(PHONE, session)

    def test_sheet_request_shows_full_service_for_all_operational_roles(self):
        employees = (
            SUPERVISOR,
            TECHNICIAN,
            {
                "record_id": "rec-helper",
                "nombre": "Ayudante Prueba",
                "cargo": "Ayudante",
            },
        )

        for employee in employees:
            with self.subTest(cargo=employee["cargo"]):
                clear_session(PHONE)
                session = create_session(PHONE, "CLOSE_SERVICE")
                session.update(
                    {
                        "cot": "COT12345 - OC",
                        "waiting_for": "closure_service_sheet_photo",
                    }
                )
                save_session(PHONE, session)

                response = process_operations_message(
                    PHONE,
                    "mensaje sin imagen",
                    employee,
                )

                self.assertIn("*COT12345 - OC*", response)
                self.assertIn(
                    "verifica que la hoja corresponda a este servicio",
                    response,
                )
                self.assertEqual(
                    get_session(PHONE)["waiting_for"],
                    "closure_service_sheet_photo",
                )

    def test_yes_continues_existing_closure_flow(self):
        self.prepare_satisfaction("OC")
        response = process_central_action(
            PHONE,
            ACTION_CLOSURE_SATISFIED_YES,
            TECHNICIAN,
        )
        session = get_session(PHONE)
        self.assertTrue(session["closure_satisfactory"])
        self.assertEqual(session["waiting_for"], "closure_observations")
        self.assertIn("Observaciones del cierre", response)

    def test_no_oc_skips_mitigation_and_sheet_then_requests_images(self):
        self.prepare_satisfaction("OC")
        response = process_central_action(
            PHONE,
            ACTION_CLOSURE_SATISFIED_NO,
            TECHNICIAN,
        )
        self.assertIn("Servicio no culminado", response)
        self.assertNotIn("Causa de mitigación", response)
        self.assertEqual(
            get_session(PHONE)["waiting_for"],
            "closure_unsatisfactory_observations",
        )

        response = process_central_message(
            PHONE,
            "No llegaron los materiales.",
            TECHNICIAN,
        )
        session = get_session(PHONE)
        self.assertEqual(session["waiting_for"], "closure_service_photo")
        self.assertIsNone(session["closure_service_sheet_path"])
        self.assertIn("Evidencia del trabajo", response)

    def test_no_non_oc_uses_exact_four_mitigation_options(self):
        self.prepare_satisfaction("GARANTIA")
        response = process_operations_message(PHONE, "No", TECHNICIAN)
        session = get_session(PHONE)
        actions = build_contextual_actions(
            employee=TECHNICIAN,
            operations_session=session,
        )
        self.assertEqual(session["waiting_for"], "closure_mitigation_cause")
        for cause in MITIGATION_CAUSES:
            self.assertIn(cause, response)
        self.assertEqual(len(actions["list"]["rows"]), 4)

        response = process_central_action(
            PHONE,
            ACTION_MITIGATION_CAUSE_MATERIALS,
            TECHNICIAN,
        )
        session = get_session(PHONE)
        self.assertEqual(
            session["closure_mitigation_cause"],
            "Falta de Materiales y/o Herramientas",
        )
        self.assertEqual(
            session["waiting_for"],
            "closure_unsatisfactory_observations",
        )
        self.assertIn("Servicio en mitigación", response)

        response = process_central_message(
            PHONE,
            "El repuesto no estaba disponible.",
            TECHNICIAN,
        )
        self.assertEqual(
            get_session(PHONE)["waiting_for"],
            "closure_service_sheet_photo",
        )
        self.assertIn("Hoja de Cierre", response)

    @patch("app.agents.operaciones.service.update_service_status_by_record_id")
    @patch("app.agents.operaciones.service.upload_service_photo")
    @patch("app.agents.operaciones.service.sync_activity_report_to_closure")
    @patch("app.agents.operaciones.service.save_service_closure_form")
    def test_unsatisfactory_oc_saves_photos_and_never_pauses(
        self,
        save_closure,
        sync_report,
        upload_photo,
        update_status,
    ):
        photo = self.image("work.jpg")
        session = create_session(PHONE, "CLOSE_SERVICE")
        session.update(
            {
                "cot": "COT38395 - OC",
                "service_record_id": "rec-service",
                "service_type": "OC",
                "service_status": "ACTIVO",
                "closure_technician": "Técnico Prueba",
                "closure_technician_record_id": "rec-technician",
                "closure_satisfactory": False,
                "closure_observations": "Cliente no autorizó ingreso.",
                "closure_service_photos": [
                    {
                        "path": photo,
                        "filename": "work.jpg",
                        "mime_type": "image/jpeg",
                        "uploaded": False,
                    }
                ],
                "waiting_for": "closure_confirmation",
            }
        )
        save_session(PHONE, session)
        save_closure.return_value = {
            "saved": True,
            "closure_record_id": "rec-closure",
        }
        sync_report.return_value = {"synced": False}
        upload_photo.return_value = {"uploaded": True}

        response = process_operations_message(PHONE, "Sí", TECHNICIAN)

        update_status.assert_not_called()
        upload_photo.assert_called_once()
        save_closure.assert_called_once()
        self.assertTrue(save_closure.call_args.kwargs["append_observations"])
        self.assertIn("Estado del servicio: *ACTIVO*", response)
        self.assertIsNone(get_session(PHONE))

    @patch("app.airtable.service_closure_repository.create_record")
    @patch("app.airtable.service_closure_repository.update_record")
    @patch(
        "app.airtable.service_closure_repository."
        "find_service_closure_by_service_record_id"
    )
    def test_existing_observations_are_appended_without_duplicate_record(
        self,
        find_closure,
        update_record,
        create_record,
    ):
        find_closure.return_value = {
            "found": True,
            "record_id": "rec-closure",
            "fields": {
                AIRTABLE_CLOSURE_OBSERVATIONS_FIELD:
                    "Primera observación",
            },
        }
        update_record.return_value = {
            "updated": True,
            "record_id": "rec-closure",
        }

        result = save_service_closure_form(
            service_record_id="rec-service",
            quote_number="COT38395 - GARANTIA",
            technician_record_id="rec-technician",
            observations="Segunda observación",
            mitigation_cause="Falta de permisos",
            append_observations=True,
        )

        self.assertTrue(result["saved"])
        create_record.assert_not_called()
        fields = update_record.call_args.kwargs["fields"]
        self.assertEqual(
            fields[AIRTABLE_CLOSURE_OBSERVATIONS_FIELD],
            "Primera observación\nSegunda observación",
        )
        self.assertEqual(
            fields[AIRTABLE_CLOSURE_MITIGATION_CAUSE_FIELD],
            "Falta de permisos",
        )

    @patch("app.airtable.service_closure_repository.create_record")
    @patch("app.airtable.service_closure_repository.update_record")
    @patch(
        "app.airtable.service_closure_repository."
        "find_service_closure_by_service_record_id"
    )
    def test_retry_does_not_append_same_observation_twice(
        self,
        find_closure,
        update_record,
        create_record,
    ):
        find_closure.return_value = {
            "found": True,
            "record_id": "rec-closure",
            "fields": {
                AIRTABLE_CLOSURE_OBSERVATIONS_FIELD:
                    "Observación ya registrada",
            },
        }
        update_record.return_value = {"updated": True}

        save_service_closure_form(
            service_record_id="rec-service",
            quote_number="COT38395 - OC",
            technician_record_id="rec-technician",
            observations="Observación ya registrada",
            append_observations=True,
        )

        fields = update_record.call_args.kwargs["fields"]
        self.assertEqual(
            fields[AIRTABLE_CLOSURE_OBSERVATIONS_FIELD],
            "Observación ya registrada",
        )
        create_record.assert_not_called()

    def test_audio_transcription_state_stays_in_operations(self):
        self.prepare_satisfaction("OC")
        process_operations_message(PHONE, "No", TECHNICIAN)
        transcription = "El cliente impidió el acceso al área."

        with patch(
            "app.agents.central.service.classify_message"
        ) as classify_message:
            response = process_central_message(
                PHONE,
                transcription,
                TECHNICIAN,
            )

        classify_message.assert_not_called()
        session = get_session(PHONE)
        self.assertEqual(session["closure_observations"], transcription)
        self.assertEqual(session["waiting_for"], "closure_service_photo")
        self.assertIn("Evidencia", response)


if __name__ == "__main__":
    unittest.main()
