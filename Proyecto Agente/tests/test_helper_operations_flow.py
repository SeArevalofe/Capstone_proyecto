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


from app.agents.maestro.permissions import (  # noqa: E402
    get_assignment_field_for_employee,
)
from app.agents.operaciones.permissions import (  # noqa: E402
    can_perform_field_survey,
    is_helper,
    is_service_type_allowed,
    uses_technician_operations_flow,
)
from app.agents.operaciones.service import (  # noqa: E402
    build_service_list,
    process_operations_location,
    process_operations_message,
    select_service,
    select_service_for_closure,
)
from app.agents.operaciones.session import (  # noqa: E402
    clear_session,
    create_session,
    get_session,
    save_session,
)
from app.airtable.service_request_repository import (  # noqa: E402
    get_programmed_services_for_employee,
)


HELPER = {
    "record_id": "rec-helper",
    "nombre": "Ayudante Uno",
    "cargo": "Ayudante",
}
TECHNICIAN = {
    "record_id": "rec-technician",
    "nombre": "Técnico Uno",
    "cargo": "Técnico",
}


def context(service_type="OC", status="PROGRAMADO"):
    return {
        "found": True,
        "record_id": "rec-service",
        "cot": "COT50000",
        "quote_number": f"COT50000 - {service_type}",
        "oc": "OC-50000",
        "status": status,
        "service_type": service_type,
        "service_address": "Dirección de prueba",
        "service_description": "Trabajo de prueba",
        "technicians": ["rec-technician"],
        "helpers": ["rec-helper", "rec-other-helper"],
        "supervisors": [],
    }


class HelperOperationsFlowTests(unittest.TestCase):

    phone = "helper-operations-test"

    def setUp(self):
        clear_session(self.phone)
        clear_session(self.phone + "-other")
        self.temp_directory = tempfile.TemporaryDirectory()

    def tearDown(self):
        clear_session(self.phone)
        clear_session(self.phone + "-other")
        self.temp_directory.cleanup()

    def image(self, name):
        path = os.path.join(self.temp_directory.name, name)
        with open(path, "wb") as image_file:
            image_file.write(b"image")
        return path

    def test_helper_shares_technician_operations_but_not_role(self):
        self.assertTrue(is_helper(HELPER))
        self.assertTrue(uses_technician_operations_flow(HELPER))
        self.assertTrue(uses_technician_operations_flow(TECHNICIAN))
        self.assertFalse(can_perform_field_survey(HELPER))
        self.assertEqual(HELPER["cargo"], "Ayudante")
        self.assertTrue(is_service_type_allowed(HELPER, "OC"))
        self.assertFalse(is_service_type_allowed(HELPER, "Cotización"))

    @patch("app.airtable.service_request_repository.get_records")
    def test_helper_query_uses_helper_assignment_and_exact_record_id(
        self,
        get_records,
    ):
        get_records.return_value = {
            "records": [
                {
                    "id": "rec-service-own",
                    "fields": {
                        "ID Solicitud de Servicio": "COT1 - OC",
                        "Estado del Servicio": "PROGRAMADO",
                        "Tipo de Servicio": "OC",
                        "Ayudante Asignado": ["rec-helper"],
                    },
                },
                {
                    "id": "rec-service-other",
                    "fields": {
                        "ID Solicitud de Servicio": "COT2 - OC",
                        "Estado del Servicio": "PROGRAMADO",
                        "Tipo de Servicio": "OC",
                        "Ayudante Asignado": ["rec-other-helper"],
                    },
                },
            ]
        }

        result = get_programmed_services_for_employee(HELPER)

        self.assertEqual(
            get_assignment_field_for_employee(HELPER),
            "Ayudante Asignado",
        )
        formula = get_records.call_args.kwargs["params"]["filterByFormula"]
        self.assertIn("{Ayudante Asignado}", formula)
        self.assertEqual(
            [record["record_id"] for record in result["records"]],
            ["rec-service-own"],
        )

    @patch(
        "app.agents.operaciones.service."
        "get_programmed_services_for_employee"
    )
    def test_helper_start_list_uses_technician_type_restriction(
        self,
        get_programmed,
    ):
        get_programmed.return_value = {
            "records": [
                {
                    "record_id": "rec-oc",
                    "quote_number": "COT1 - OC",
                    "service_type": "OC",
                },
                {
                    "record_id": "rec-quote",
                    "quote_number": "COT2 - Cotización",
                    "service_type": "Cotización",
                },
            ]
        }

        services, message = build_service_list(HELPER, "START_SERVICE")

        get_programmed.assert_called_once_with(HELPER)
        self.assertEqual([item["record_id"] for item in services], ["rec-oc"])
        self.assertIn("COT1 - OC", message)
        self.assertNotIn("COT2 - Cotización", message)

    @patch("app.agents.operaciones.service.resolve_employee_links")
    @patch(
        "app.agents.operaciones.service.get_operational_service_context"
    )
    def test_helper_can_start_and_is_not_duplicated_as_additional_helper(
        self,
        get_context,
        resolve_links,
    ):
        get_context.return_value = context()
        resolve_links.side_effect = [
            ["Técnico Uno"],
            ["Ayudante Uno", "Ayudante Dos"],
        ]

        response = select_service(
            phone=self.phone,
            cot="COT50000 - OC",
            employee=HELPER,
            service_record_id="rec-service",
        )

        session = get_session(self.phone)
        self.assertEqual(session["operator_role"], "Ayudante")
        self.assertEqual(session["technician"], "Ayudante Uno")
        self.assertEqual(session["technician_record_id"], "rec-helper")
        self.assertEqual(session["available_helpers"], ["Ayudante Dos"])
        self.assertEqual(session["available_helper_ids"], ["rec-other-helper"])
        self.assertEqual(session["waiting_for"], "helper_confirmation")
        self.assertIn("Ayudante Dos", response)

    @patch("app.agents.operaciones.service.resolve_employee_links")
    @patch(
        "app.agents.operaciones.service.get_operational_service_context"
    )
    def test_helper_can_close_and_gets_satisfaction_question(
        self,
        get_context,
        resolve_links,
    ):
        get_context.return_value = context(status="ACTIVO")
        resolve_links.return_value = ["Ayudante Uno", "Ayudante Dos"]

        response = select_service_for_closure(
            phone=self.phone,
            cot="COT50000 - OC",
            employee=HELPER,
            service_record_id="rec-service",
        )

        session = get_session(self.phone)
        self.assertEqual(session["closure_worker_role"], "Ayudante")
        self.assertEqual(session["closure_technician"], "Ayudante Uno")
        self.assertEqual(session["available_helpers"], ["Ayudante Dos"])
        self.assertEqual(session["waiting_for"], "closure_satisfaction")
        self.assertIn("Ayudante que cierra", response)
        self.assertIn("¿El servicio fue culminado", response)

    @patch("app.agents.maestro.service.process_field_report_message")
    @patch("app.agents.operaciones.service.update_service_status_by_record_id")
    @patch("app.agents.operaciones.service.create_activity_start")
    def test_helper_successful_start_activates_without_maestro(
        self,
        create_start,
        update_status,
        process_maestro,
    ):
        session = create_session(self.phone, "START_SERVICE")
        session.update(
            {
                "cot": "COT50000 - OC",
                "service_record_id": "rec-service",
                "service_type": "OC",
                "service_status": "PROGRAMADO",
                "technician": "Ayudante Uno",
                "technician_record_id": "rec-helper",
                "operator_role": "Ayudante",
                "waiting_for": "location",
            }
        )
        save_session(self.phone, session)
        create_start.return_value = {
            "created": True,
            "record_id": "rec-activity",
        }
        update_status.return_value = {"updated": True}

        response = process_operations_location(
            phone=self.phone,
            employee=HELPER,
            location_text="Ubicación WhatsApp",
            latitude=-33.4,
            longitude=-70.6,
        )

        process_maestro.assert_not_called()
        update_status.assert_called_once_with(
            service_record_id="rec-service",
            status="ACTIVO",
        )
        self.assertIn("Inicio de servicio registrado", response)
        self.assertNotIn("levantamiento", response.lower())

    @patch("app.agents.operaciones.service.update_service_status_by_record_id")
    @patch("app.agents.operaciones.service.upload_service_photo")
    @patch("app.agents.operaciones.service.upload_service_sheet_photo")
    @patch("app.agents.operaciones.service.sync_activity_report_to_closure")
    @patch("app.agents.operaciones.service.save_service_closure_form")
    def test_helper_satisfactory_closure_pauses(
        self,
        save_closure,
        sync_report,
        upload_sheet,
        upload_photo,
        update_status,
    ):
        sheet = self.image("sheet.jpg")
        photo = self.image("work.jpg")
        session = create_session(self.phone, "CLOSE_SERVICE")
        session.update(
            {
                "cot": "COT50000 - OC",
                "service_record_id": "rec-service",
                "service_type": "OC",
                "service_status": "ACTIVO",
                "closure_worker_role": "Ayudante",
                "closure_technician": "Ayudante Uno",
                "closure_technician_record_id": "rec-helper",
                "closure_satisfactory": True,
                "closure_observations": "Sin observaciones",
                "closure_service_sheet_path": sheet,
                "closure_service_sheet_uploaded": False,
                "closure_sheet_is_valid": True,
                "closure_sheet_is_service_closure_sheet": True,
                "closure_sheet_stamp_detected": True,
                "closure_sheet_stamp_status": "detected",
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
        save_session(self.phone, session)
        save_closure.return_value = {
            "saved": True,
            "closure_record_id": "rec-closure",
        }
        sync_report.return_value = {"synced": False}
        upload_sheet.return_value = {"uploaded": True}
        upload_photo.return_value = {"uploaded": True}
        update_status.return_value = {"updated": True}

        response = process_operations_message(self.phone, "Sí", HELPER)

        self.assertTrue(save_closure.call_args.kwargs["append_observations"])
        update_status.assert_called_once_with(
            service_record_id="rec-service",
            status="PAUSADO",
        )
        self.assertIn("Cierre registrado correctamente", response)

    @patch("app.agents.operaciones.service.update_service_status_by_record_id")
    @patch("app.agents.operaciones.service.upload_service_photo")
    @patch("app.agents.operaciones.service.sync_activity_report_to_closure")
    @patch("app.agents.operaciones.service.save_service_closure_form")
    def test_helper_unsatisfactory_oc_keeps_active_and_photos(
        self,
        save_closure,
        sync_report,
        upload_photo,
        update_status,
    ):
        photo = self.image("work.jpg")
        session = create_session(self.phone, "CLOSE_SERVICE")
        session.update(
            {
                "cot": "COT50000 - OC",
                "service_record_id": "rec-service",
                "service_type": "OC",
                "service_status": "ACTIVO",
                "closure_worker_role": "Ayudante",
                "closure_technician": "Ayudante Uno",
                "closure_technician_record_id": "rec-helper",
                "closure_satisfactory": False,
                "closure_observations": "Faltaron materiales",
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
        save_session(self.phone, session)
        save_closure.return_value = {
            "saved": True,
            "closure_record_id": "rec-closure",
        }
        sync_report.return_value = {"synced": False}
        upload_photo.return_value = {"uploaded": True}

        response = process_operations_message(self.phone, "Sí", HELPER)

        update_status.assert_not_called()
        upload_photo.assert_called_once()
        self.assertTrue(save_closure.call_args.kwargs["append_observations"])
        self.assertIn("Estado del servicio: *ACTIVO*", response)

    def test_helper_non_oc_no_uses_mitigation_and_sessions_are_isolated(self):
        first = create_session(self.phone, "CLOSE_SERVICE")
        first.update(
            {
                "cot": "COT50000 - GARANTIA",
                "service_type": "GARANTIA",
                "waiting_for": "closure_satisfaction",
            }
        )
        save_session(self.phone, first)
        second = create_session(self.phone + "-other", "START_SERVICE")
        second["cot"] = "COT-OTHER"
        save_session(self.phone + "-other", second)

        response = process_operations_message(self.phone, "No", HELPER)

        self.assertIn("Causa de mitigación", response)
        self.assertEqual(
            get_session(self.phone)["waiting_for"],
            "closure_mitigation_cause",
        )

        response = process_operations_message(
            self.phone,
            "Falta de Materiales y/o Herramientas",
            HELPER,
        )
        self.assertIn("mitigación", response)
        self.assertEqual(
            get_session(self.phone)["waiting_for"],
            "closure_unsatisfactory_observations",
        )

        response = process_operations_message(
            self.phone,
            "El repuesto no estaba disponible",
            HELPER,
        )
        self.assertIn("Hoja de Cierre", response)
        self.assertEqual(
            get_session(self.phone)["waiting_for"],
            "closure_service_sheet_photo",
        )
        self.assertEqual(get_session(self.phone + "-other")["cot"], "COT-OTHER")

    def test_helper_unsatisfactory_oc_skips_mitigation(self):
        session = create_session(self.phone, "CLOSE_SERVICE")
        session.update(
            {
                "cot": "COT50000 - OC",
                "service_type": "OC",
                "waiting_for": "closure_satisfaction",
            }
        )
        save_session(self.phone, session)

        response = process_operations_message(self.phone, "No", HELPER)

        self.assertNotIn("Causa de mitigación", response)
        self.assertEqual(
            get_session(self.phone)["waiting_for"],
            "closure_unsatisfactory_observations",
        )

        response = process_operations_message(
            self.phone,
            "El trabajo quedó pendiente",
            HELPER,
        )
        self.assertIn("Evidencia del trabajo", response)
        self.assertEqual(
            get_session(self.phone)["waiting_for"],
            "closure_service_photo",
        )


if __name__ == "__main__":
    unittest.main()
