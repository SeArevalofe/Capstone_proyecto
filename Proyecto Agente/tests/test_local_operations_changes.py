import asyncio
import os
import unittest

from unittest.mock import Mock, patch

import dotenv
import requests
# Las pruebas no cargan el .env local ni usan servicios externos.
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


from app.agents.operaciones.permissions import (  # noqa: E402
    is_service_type_allowed,
)
from app.agents.central.service import (  # noqa: E402
    process_central_location,
)
from app.agents.operaciones.service import (  # noqa: E402
    build_service_list,
    process_operations_location,
    resolve_service_selection,
    select_service,
)
from app.agents.operaciones.session import (  # noqa: E402
    clear_session,
    create_session,
    get_session,
    save_session,
)
from app.airtable.service_request_repository import (  # noqa: E402
    build_assignment_formula,
    build_service_result,
    get_assigned_service_by_record_id,
    linked_assignment_is_employee_record,
    record_matches_employee_assignment,
    update_service_status_by_record_id,
)
from app.whatsapp.client import (  # noqa: E402
    send_whatsapp_message,
    send_whatsapp_buttons,
    send_whatsapp_location_request,
)
from app.whatsapp.debounce import (  # noqa: E402
    coalesce_text_message,
    register_message_id,
    reset_debounce_state,
)
from app.whatsapp.webhook import (  # noqa: E402
    is_waiting_for_operations_location,
    safe_send_answer_for_current_state,
)
from app.whatsapp.interactive import (  # noqa: E402
    BUTTON_BACK_HOME,
    BUTTON_RESUME_FIELD_SURVEY,
    should_show_usage_notice,
)
from app.config import (  # noqa: E402
    AIRTABLE_SERVICE_DESCRIPTION_FIELD,
    AIRTABLE_SERVICE_SUPERVISOR_FIELD,
    AIRTABLE_SERVICE_STATUS_ACTIVE_RECORD_ID,
    AIRTABLE_SERVICE_STATUS_PAUSED_RECORD_ID,
)


class OperationsFilteringTests(
    unittest.TestCase,
):

    def test_role_service_type_rules(self):

        supervisor = {
            "cargo": "Supervisor",
        }
        technician = {
            "cargo": "Técnico",
        }

        self.assertTrue(
            is_service_type_allowed(
                supervisor,
                "Cotización",
            )
        )
        self.assertFalse(
            is_service_type_allowed(
                supervisor,
                "OC",
            )
        )
        self.assertFalse(
            is_service_type_allowed(
                technician,
                "COTIZACION",
            )
        )
        self.assertTrue(
            is_service_type_allowed(
                technician,
                "OC",
            )
        )

        for service_type in (
            "COTIZACION",
            "Cotización",
            "cotizacion",
        ):
            self.assertTrue(
                is_service_type_allowed(
                    supervisor,
                    service_type,
                )
            )

    def test_assignment_formula_matches_complete_name(self):

        formula = build_assignment_formula(
            employee_name="Matias Alejandro Roa Mura",
            assignment_field="Supervisor Asignado",
        )

        self.assertIn(
            "',matias alejandro roa mura,'",
            formula,
        )
        self.assertIn(
            "','&LOWER(ARRAYJOIN({Supervisor Asignado},','))&','",
            formula,
        )

    def test_matching_employee_link_remains_valid(self):

        employee = {"record_id": "rec-matias"}
        record = {
            "fields": {
                AIRTABLE_SERVICE_SUPERVISOR_FIELD: ["rec-matias"],
            },
        }

        with patch(
            "app.airtable.service_request_repository.get_record"
        ) as get_record:
            self.assertTrue(
                record_matches_employee_assignment(
                    record,
                    AIRTABLE_SERVICE_SUPERVISOR_FIELD,
                    employee,
                )
            )

        get_record.assert_not_called()

    def test_different_comparable_employee_link_is_rejected(self):

        linked_assignment_is_employee_record.cache_clear()
        employee = {"record_id": "rec-matias"}
        record = {
            "fields": {
                AIRTABLE_SERVICE_SUPERVISOR_FIELD: [
                    "rec-other-supervisor",
                ],
            },
        }

        with patch(
            "app.airtable.service_request_repository.get_record",
            return_value={
                "found": True,
                "record_id": "rec-other-supervisor",
                "record": {
                    "id": "rec-other-supervisor",
                    "fields": {
                        "RRHH": ["rec-other-authenticated"],
                        "Nombre del Tecnico": "Otro Supervisor",
                    },
                },
            },
        ):
            self.assertFalse(
                record_matches_employee_assignment(
                    record,
                    AIRTABLE_SERVICE_SUPERVISOR_FIELD,
                    employee,
                )
            )

    def test_non_comparable_link_keeps_airtable_name_match(self):

        linked_assignment_is_employee_record.cache_clear()
        employee = {"record_id": "rec-matias-rrhh"}
        record = {
            "fields": {
                AIRTABLE_SERVICE_SUPERVISOR_FIELD: [
                    "rec-matias-supervisors-table",
                ],
            },
        }
        with patch(
            "app.airtable.service_request_repository.get_record",
            return_value={
                "found": False,
                "reason": "record_not_found",
                "record": None,
                "record_id": "rec-matias-supervisors-table",
            },
        ):
            self.assertTrue(
                record_matches_employee_assignment(
                    record,
                    AIRTABLE_SERVICE_SUPERVISOR_FIELD,
                    employee,
                )
            )

    def test_cot38395_survives_duplicate_rrhh_identity_by_exact_name(self):

        linked_assignment_is_employee_record.cache_clear()
        employee = {
            "nombre": "Matias Alejandro Roa Mura",
            "cargo": "Supervisor",
            "record_id": "recel7afT5onZ0TtR",
        }
        service_record = {
            "id": "recJWXkpF4TRjPTI1",
            "fields": {
                "ID Solicitud de Servicio": "COT38395",
                "Estado del Servicio": ["recta7uHbjZcS9uLH"],
                "Tipo de Servicio": "COTIZACION",
                "Supervisor Asignado": ["reciwBkKarRVNPC3Q"],
            },
        }
        linked_employee = {
            "found": True,
            "record_id": "reciwBkKarRVNPC3Q",
            "record": {
                "id": "reciwBkKarRVNPC3Q",
                "fields": {
                    "RRHH": ["recel7afT5onZ0TtR"],
                    "Nombre del Tecnico": "Matias Alejandro Roa Mura",
                },
            },
        }

        with patch(
            "app.airtable.service_request_repository.get_records",
            return_value={"records": [service_record]},
        ), patch(
            "app.airtable.service_request_repository.get_record",
            return_value=linked_employee,
        ):
            services, _ = build_service_list(employee, "START_SERVICE")

        self.assertEqual(
            services,
            [{
                "identifier": "COT38395",
                "record_id": "recJWXkpF4TRjPTI1",
                "service_type": "COTIZACION",
            }],
        )

    def test_cot38395_is_rejected_for_different_supervisor(self):

        linked_assignment_is_employee_record.cache_clear()
        employee = {
            "nombre": "Supervisor Diferente",
            "cargo": "Supervisor",
            "record_id": "rec-other-authenticated",
        }
        service_record = {
            "id": "recJWXkpF4TRjPTI1",
            "fields": {
                "ID Solicitud de Servicio": "COT38395",
                "Estado del Servicio": ["recta7uHbjZcS9uLH"],
                "Tipo de Servicio": "COTIZACION",
                "Supervisor Asignado": ["reciwBkKarRVNPC3Q"],
            },
        }

        with patch(
            "app.airtable.service_request_repository.get_records",
            return_value={"records": [service_record]},
        ), patch(
            "app.airtable.service_request_repository.get_record",
            return_value={
                "found": True,
                "record_id": "reciwBkKarRVNPC3Q",
                "record": {
                    "id": "reciwBkKarRVNPC3Q",
                    "fields": {
                        "RRHH": ["recel7afT5onZ0TtR"],
                        "Nombre del Tecnico": "Matias Alejandro Roa Mura",
                    },
                },
            },
        ):
            services, _ = build_service_list(employee, "START_SERVICE")

        self.assertEqual(services, [])

    def test_rrhh_lookup_404_preserves_exact_airtable_name_match(self):

        linked_assignment_is_employee_record.cache_clear()
        employee = {
            "nombre": "Matias Alejandro Roa Mura",
            "record_id": "recel7afT5onZ0TtR",
        }
        record = {
            "fields": {
                AIRTABLE_SERVICE_SUPERVISOR_FIELD: [
                    "reciwBkKarRVNPC3Q",
                ],
            },
        }
        not_found = requests.HTTPError("record not found")
        not_found.response = Mock(status_code=404)

        with patch(
            "app.airtable.service_request_repository.get_record",
            side_effect=not_found,
        ):
            self.assertTrue(
                record_matches_employee_assignment(
                    record,
                    AIRTABLE_SERVICE_SUPERVISOR_FIELD,
                    employee,
                )
            )

    def test_rrhh_lookup_network_or_500_fails_closed(self):

        employee = {
            "nombre": "Matias Alejandro Roa Mura",
            "record_id": "recel7afT5onZ0TtR",
        }
        record = {
            "fields": {
                AIRTABLE_SERVICE_SUPERVISOR_FIELD: [
                    "reciwBkKarRVNPC3Q",
                ],
            },
        }

        for error in (
            requests.ConnectionError("network error"),
            requests.HTTPError("server error"),
        ):
            linked_assignment_is_employee_record.cache_clear()
            if isinstance(error, requests.HTTPError):
                error.response = Mock(status_code=500)

            with self.subTest(error=type(error).__name__), patch(
                "app.airtable.service_request_repository.get_record",
                side_effect=error,
            ):
                self.assertFalse(
                    record_matches_employee_assignment(
                        record,
                        AIRTABLE_SERVICE_SUPERVISOR_FIELD,
                        employee,
                    )
                )

    @patch(
        "app.agents.operaciones.service.get_active_services_for_employee"
    )
    @patch(
        "app.agents.operaciones.service.get_programmed_services_for_employee"
    )
    def test_supervisor_start_and_close_keep_status_separate(
        self,
        get_programmed,
        get_active,
    ):

        programmed = {
            "record_id": "rec-programmed",
            "quote_number": "COT38395",
            "service_type": "COTIZACION",
        }
        active = {
            "record_id": "rec-active",
            "quote_number": "COT40000 - Cotización",
            "service_type": "Cotización",
        }
        get_programmed.return_value = {"records": [programmed]}
        get_active.return_value = {"records": [active]}
        supervisor = {"cargo": "Supervisor"}

        start_services, _ = build_service_list(
            supervisor,
            "START_SERVICE",
        )
        with patch(
            "app.agents.operaciones.service."
            "get_field_report_from_activity",
            return_value={
                "found": True,
                "report_text": "Informe guardado",
            },
        ):
            close_services, _ = build_service_list(
                supervisor,
                "CLOSE_SERVICE",
            )

        self.assertEqual(
            [item["record_id"] for item in start_services],
            ["rec-programmed"],
        )
        self.assertEqual(
            [item["record_id"] for item in close_services],
            ["rec-active"],
        )
        get_programmed.assert_called_once_with(supervisor)
        get_active.assert_called_once_with(supervisor)

    @patch(
        "app.agents.operaciones.service."
        "get_programmed_services_for_employee"
    )
    def test_start_list_keeps_full_airtable_id_and_filters_supervisor(
        self,
        get_programmed,
    ):

        get_programmed.return_value = {
            "records": [
                {
                    "record_id": "rec-quote",
                    "quote_number": "COT37470 - Cotización",
                    "service_type": "Cotización",
                },
                {
                    "record_id": "rec-oc",
                    "quote_number": "COT37470 - OC",
                    "service_type": "OC",
                },
            ]
        }

        services, message = build_service_list(
            employee={
                "cargo": "Supervisor",
            },
            action="START_SERVICE",
        )

        self.assertEqual(
            services,
            [
                {
                    "identifier": "COT37470 - Cotización",
                    "record_id": "rec-quote",
                    "service_type": "Cotización",
                }
            ],
        )
        self.assertIn(
            "COT37470 - Cotización",
            message,
        )
        self.assertNotIn(
            "COT37470 - OC",
            message,
        )

    @patch(
        "app.agents.operaciones.service."
        "get_active_services_for_employee"
    )
    def test_close_list_filters_technician_and_uses_only_active_query(
        self,
        get_active,
    ):

        get_active.return_value = {
            "records": [
                {
                    "record_id": "rec-quote",
                    "quote_number": "COT12345 - Cotización",
                    "service_type": "Cotización",
                },
                {
                    "record_id": "rec-oc",
                    "quote_number": "COT12345 - OC",
                    "service_type": "OC",
                },
            ]
        }

        services, message = build_service_list(
            employee={
                "cargo": "Técnico",
            },
            action="CLOSE_SERVICE",
        )

        get_active.assert_called_once()
        self.assertEqual(
            services[0][
                "record_id"
            ],
            "rec-oc",
        )
        self.assertIn(
            "COT12345 - OC",
            message,
        )
        self.assertNotIn(
            "COT12345 - Cotización",
            message,
        )

    def test_numeric_selection_returns_exact_record(self):

        session = {
            "available_services": [
                {
                    "identifier": "COT55555 - Cotización",
                    "record_id": "rec-first",
                },
                {
                    "identifier": "COT55555 - OC",
                    "record_id": "rec-second",
                },
            ]
        }

        selected = resolve_service_selection(
            text="2",
            session=session,
        )

        self.assertEqual(
            selected[
                "record_id"
            ],
            "rec-second",
        )

        self.assertIsNone(
            resolve_service_selection(
                text="COT55555",
                session=session,
            )
        )

    @patch(
        "app.airtable.service_request_repository."
        "get_services_for_employee"
    )
    def test_record_id_lookup_does_not_fall_back_to_base_cot(
        self,
        get_services,
    ):

        get_services.return_value = {
            "records": [
                {
                    "record_id": "rec-first",
                    "quote_number": "COT55555 - Cotización",
                },
                {
                    "record_id": "rec-second",
                    "quote_number": "COT55555 - OC",
                },
            ]
        }

        selected = get_assigned_service_by_record_id(
            record_id="rec-second",
            employee={
                "nombre": "Prueba",
            },
            statuses=[
                "ACTIVO",
            ],
        )

        self.assertEqual(
            selected[
                "quote_number"
            ],
            "COT55555 - OC",
        )

    @patch(
        "app.agents.operaciones.service."
        "get_operational_service_context"
    )
    def test_start_selection_uses_record_id_and_stores_full_identifier(
        self,
        get_context,
    ):

        phone = "selection-test"
        clear_session(
            phone
        )

        get_context.return_value = {
            "found": True,
            "record_id": "rec-exact",
            "cot": "COT77777",
            "quote_number": "COT77777 - OC",
            "oc": "OC-1",
            "status": "PROGRAMADO",
            "service_type": "OC",
            "service_address": "Dirección de prueba",
            "service_description": "Reparar portón principal",
            "technicians": [],
            "helpers": [],
            "supervisors": [],
        }

        select_service(
            phone=phone,
            cot="COT77777 - OC",
            employee={
                "cargo": "Técnico",
                "nombre": "Técnico Prueba",
                "record_id": "rec-worker",
            },
            service_record_id="rec-exact",
        )

        get_context.assert_called_once_with(
            cot="COT77777 - OC",
            employee={
                "cargo": "Técnico",
                "nombre": "Técnico Prueba",
                "record_id": "rec-worker",
            },
            statuses=[
                "PROGRAMADO",
            ],
            record_id="rec-exact",
        )

        session = get_session(
            phone
        )

        self.assertEqual(
            session[
                "cot"
            ],
            "COT77777 - OC",
        )
        self.assertEqual(
            session[
                "waiting_for"
            ],
            "location",
        )
        self.assertEqual(
            session["service_description"],
            "Reparar portón principal",
        )

        clear_session(
            phone
        )


class AutomaticSurveyTransitionTests(
    unittest.TestCase,
):

    def tearDown(self):

        clear_session(
            "transition-test"
        )

    def prepare_location_session(
        self,
        service_type,
    ):

        session = create_session(
            phone="transition-test",
            action="START_SERVICE",
        )
        session.update(
            {
                "cot": "COT99999 - Prueba",
                "service_record_id": "rec-service",
                "service_type": service_type,
                "service_status": "PROGRAMADO",
                "service_description": "Reparar portón principal",
                "technician": "Trabajador Prueba",
                "technician_record_id": "rec-worker",
                "waiting_for": "location",
            }
        )
        save_session(
            phone="transition-test",
            session=session,
        )

    @patch(
        "app.agents.maestro.service."
        "process_field_report_message"
    )
    @patch(
        "app.agents.operaciones.service."
        "update_service_status_by_record_id"
    )
    @patch(
        "app.agents.operaciones.service."
        "create_activity_start"
    )
    def test_technician_start_returns_only_normal_receipt(
        self,
        create_start,
        update_status,
        process_survey,
    ):

        self.prepare_location_session(
            "OC"
        )
        create_start.return_value = {
            "created": True,
        }
        update_status.return_value = {
            "updated": True,
        }

        response = process_operations_location(
            phone="transition-test",
            employee={
                "cargo": "Técnico",
            },
            location_text="Ubicación WhatsApp",
            latitude=-33.4,
            longitude=-70.6,
        )

        process_survey.assert_not_called()
        update_status.assert_called_once_with(
            service_record_id="rec-service",
            status="ACTIVO",
        )
        self.assertIn("Inicio de servicio registrado", response)
        self.assertNotIn("levantamiento", response.lower())
        self.assertNotIn("cotización", response.lower())

    @patch(
        "app.agents.maestro.service."
        "process_field_report_message"
    )
    @patch(
        "app.agents.operaciones.service."
        "update_service_status_by_record_id"
    )
    @patch(
        "app.agents.operaciones.service."
        "create_activity_start"
    )
    def test_technician_role_never_opens_survey(
        self,
        create_start,
        update_status,
        process_survey,
    ):

        self.prepare_location_session(
            "Cotización"
        )
        create_start.return_value = {
            "created": True,
        }
        update_status.return_value = {
            "updated": True,
        }

        response = process_operations_location(
            phone="transition-test",
            employee={
                "cargo": "Técnico",
            },
            location_text="Ubicación WhatsApp",
            latitude=-33.4,
            longitude=-70.6,
        )

        process_survey.assert_not_called()
        update_status.assert_called_once_with(
            service_record_id="rec-service",
            status="ACTIVO",
        )
        self.assertIn("Inicio de servicio registrado", response)
        self.assertNotIn("levantamiento", response.lower())
        self.assertNotIn("cotización", response.lower())

    @patch(
        "app.agents.maestro.session.save_session"
    )
    @patch(
        "app.agents.maestro.session.get_session"
    )
    @patch(
        "app.agents.maestro.service."
        "process_field_report_message"
    )
    @patch(
        "app.agents.operaciones.service."
        "update_service_status_by_record_id"
    )
    @patch(
        "app.agents.operaciones.service."
        "create_activity_start"
    )
    def test_quote_start_keeps_automatic_survey_transition(
        self,
        create_start,
        update_status,
        process_survey,
        get_maestro_session,
        save_maestro_session,
    ):

        self.prepare_location_session(
            "Cotización"
        )
        create_start.return_value = {
            "created": True,
            "record_id": "rec-activity",
            "service_record_id": "rec-service",
        }
        update_status.return_value = {
            "updated": True,
            "record_id": "rec-service",
            "status": "ACTIVO",
        }
        maestro_session = {
            "quote_record_id": "rec-service",
        }
        get_maestro_session.return_value = maestro_session
        process_survey.return_value = (
            "Levantamiento iniciado\n• Estado: *PROGRAMADO*"
        )

        response = process_operations_location(
            phone="transition-test",
            employee={
                "cargo": "Supervisor",
            },
            location_text="Ubicación WhatsApp",
            latitude=-33.4,
            longitude=-70.6,
        )

        process_survey.assert_called_once_with(
            phone="transition-test",
            text="COT99999 - Prueba",
            employee={
                "cargo": "Supervisor",
            },
        )
        self.assertEqual(len(response["messages"]), 2)
        self.assertIn(
            "Inicio de servicio registrado",
            response["messages"][0],
        )
        self.assertIn(
            "Descripción del servicio: Reparar portón principal",
            response["messages"][0],
        )
        self.assertNotIn(
            "Levantamiento iniciado",
            response["messages"][0],
        )
        self.assertEqual(
            response["messages"][1],
            "Levantamiento iniciado\n• Estado: *ACTIVO*",
        )
        update_status.assert_called_once_with(
            service_record_id="rec-service",
            status="ACTIVO",
        )
        self.assertEqual(
            maestro_session["activity_record_id"],
            "rec-activity",
        )
        self.assertEqual(
            maestro_session["quote_record_id"],
            "rec-service",
        )
        self.assertEqual(
            maestro_session["service_status"],
            "ACTIVO",
        )
        save_maestro_session.assert_called_once_with(
            "transition-test",
            maestro_session,
        )

    @patch(
        "app.agents.maestro.service."
        "process_field_report_message"
    )
    @patch(
        "app.agents.operaciones.service."
        "update_service_status_by_record_id"
    )
    @patch(
        "app.agents.operaciones.service."
        "create_activity_start"
    )
    def test_activity_failure_never_activates_service(
        self,
        create_start,
        update_status,
        process_survey,
    ):

        self.prepare_location_session("Cotización")
        create_start.return_value = {
            "created": False,
        }

        response = process_operations_location(
            phone="transition-test",
            employee={"cargo": "Supervisor"},
            location_text="Ubicación WhatsApp",
        )

        update_status.assert_not_called()
        process_survey.assert_not_called()
        self.assertIn("No pude registrar el inicio", response)
        self.assertEqual(
            get_session("transition-test")["service_status"],
            "PROGRAMADO",
        )

    @patch(
        "app.agents.maestro.service."
        "process_field_report_message"
    )
    @patch(
        "app.agents.operaciones.service."
        "update_service_status_by_record_id"
    )
    @patch(
        "app.agents.operaciones.service."
        "create_activity_start"
    )
    def test_status_failure_keeps_session_and_does_not_start_maestro(
        self,
        create_start,
        update_status,
        process_survey,
    ):

        self.prepare_location_session("Cotización")
        create_start.return_value = {
            "created": True,
            "record_id": "rec-activity",
        }
        update_status.return_value = {
            "updated": False,
        }

        response = process_operations_location(
            phone="transition-test",
            employee={"cargo": "Supervisor"},
            location_text="Ubicación WhatsApp",
        )

        process_survey.assert_not_called()
        self.assertIn("no pude actualizar", response)
        preserved = get_session("transition-test")
        self.assertEqual(preserved["service_status"], "PROGRAMADO")
        self.assertEqual(
            preserved["activity_record_id"],
            "rec-activity",
        )
        self.assertTrue(preserved["start_activity_created"])
        self.assertTrue(preserved["service_activation_pending"])

    @patch(
        "app.agents.maestro.service."
        "process_field_report_message"
    )
    @patch(
        "app.agents.operaciones.service."
        "update_service_status_by_record_id"
    )
    @patch(
        "app.agents.operaciones.service."
        "create_activity_start"
    )
    def test_activation_retry_does_not_create_second_activity(
        self,
        create_start,
        update_status,
        process_survey,
    ):

        self.prepare_location_session("Cotización")
        create_start.return_value = {
            "created": True,
            "record_id": "rec-activity",
            "service_record_id": "rec-service",
            "distance_km": 1.25,
        }
        update_status.side_effect = [
            {"updated": False},
            {"updated": True},
        ]
        process_survey.return_value = (
            "Levantamiento iniciado\n• Estado: *ACTIVO*"
        )

        first_response = process_operations_location(
            phone="transition-test",
            employee={"cargo": "Supervisor"},
            location_text="Ubicación WhatsApp",
        )
        second_response = process_operations_location(
            phone="transition-test",
            employee={"cargo": "Supervisor"},
            location_text="Ubicación WhatsApp",
        )

        self.assertIn("no pude actualizar", first_response)
        create_start.assert_called_once()
        self.assertEqual(update_status.call_count, 2)
        process_survey.assert_called_once()
        self.assertIsNone(get_session("transition-test"))
        self.assertIn(
            "Inicio de servicio registrado",
            second_response["messages"][0],
        )

    @patch(
        "app.agents.maestro.service."
        "process_field_report_message"
    )
    @patch(
        "app.agents.operaciones.service."
        "update_service_status_by_record_id"
    )
    @patch(
        "app.agents.operaciones.service."
        "create_activity_start"
    )
    @patch(
        "app.agents.central.service."
        "resolve_location_text"
    )
    def test_valid_location_is_consumed_once_and_enters_maestro(
        self,
        resolve_location,
        create_start,
        update_status,
        process_survey,
    ):

        self.prepare_location_session("Cotización")
        resolve_location.return_value = {
            "resolved": True,
            "text": "Ubicación WhatsApp",
        }
        create_start.return_value = {
            "created": True,
            "record_id": "rec-activity",
            "service_record_id": "rec-service",
        }
        update_status.return_value = {
            "updated": True,
        }
        process_survey.return_value = (
            "Levantamiento iniciado\n• Estado: *ACTIVO*"
        )

        response = process_central_location(
            phone="transition-test",
            employee={"cargo": "Supervisor"},
            latitude=-33.4,
            longitude=-70.6,
        )
        duplicate_response = process_central_location(
            phone="transition-test",
            employee={"cargo": "Supervisor"},
            latitude=-33.4,
            longitude=-70.6,
        )

        create_start.assert_called_once()
        update_status.assert_called_once_with(
            service_record_id="rec-service",
            status="ACTIVO",
        )
        process_survey.assert_called_once()
        self.assertIsNone(get_session("transition-test"))
        self.assertIn(
            "Inicio de servicio registrado",
            response["messages"][0],
        )
        self.assertNotIn(
            "Ahora comparte tu ubicación",
            "\n".join(response["messages"]),
        )
        self.assertIn(
            "no te he solicitado una ubicación",
            duplicate_response,
        )


class ServiceStatusRepositoryTests(unittest.TestCase):

    def test_service_description_uses_exact_airtable_field(self):

        result = build_service_result(
            {
                "id": "rec-service",
                "fields": {
                    AIRTABLE_SERVICE_DESCRIPTION_FIELD: (
                        "Reparar portón principal"
                    ),
                },
            }
        )

        self.assertEqual(
            AIRTABLE_SERVICE_DESCRIPTION_FIELD,
            "Descripcion del Servicio",
        )
        self.assertEqual(
            result["service_description"],
            "Reparar portón principal",
        )

    @patch("app.airtable.service_request_repository.update_record")
    def test_status_update_uses_exact_service_record_id(self, update_record):

        update_record.return_value = {
            "updated": True,
            "record_id": "rec-service",
        }

        result = update_service_status_by_record_id(
            service_record_id="rec-service",
            status="ACTIVO",
        )

        self.assertTrue(result["updated"])
        self.assertEqual(
            update_record.call_args.kwargs["record_id"],
            "rec-service",
        )
        self.assertEqual(
            update_record.call_args.kwargs["fields"],
            {
                "Estado del Servicio": [
                    "recNAjJDSZ4xVfxMm",
                ],
            },
        )
        self.assertEqual(
            AIRTABLE_SERVICE_STATUS_ACTIVE_RECORD_ID,
            "recNAjJDSZ4xVfxMm",
        )

    @patch("app.airtable.service_request_repository.update_record")
    def test_paused_status_uses_linked_record_payload(self, update_record):

        update_record.return_value = {
            "updated": True,
            "record_id": "rec-exact-service",
        }

        result = update_service_status_by_record_id(
            service_record_id="rec-exact-service",
            status="PAUSADO",
        )

        self.assertTrue(result["updated"])
        self.assertEqual(
            update_record.call_args.kwargs,
            {
                "base_id": os.environ["AIRTABLE_SERVICE_BASE_ID"],
                "table_id": os.environ["AIRTABLE_SERVICE_REQUEST_TABLE_ID"],
                "record_id": "rec-exact-service",
                "fields": {
                    "Estado del Servicio": [
                        "rec7BtzNpCP0JwHWH",
                    ],
                },
            },
        )
        self.assertEqual(
            AIRTABLE_SERVICE_STATUS_PAUSED_RECORD_ID,
            "rec7BtzNpCP0JwHWH",
        )


class WhatsAppLocationRequestTests(
    unittest.TestCase,
):

    @patch("app.whatsapp.client.requests.post")
    @patch("app.whatsapp.webhook.get_maestro_session")
    @patch("app.whatsapp.webhook.get_operations_session")
    def test_normal_greeting_sends_usage_notice_before_main_menu(
        self,
        get_operations_session,
        get_maestro_session,
        post,
    ):

        get_operations_session.return_value = None
        get_maestro_session.return_value = None
        response = Mock()
        response.ok = True
        response.json.return_value = {"messages": [{"id": "wamid.test"}]}
        post.return_value = response

        sent = safe_send_answer_for_current_state(
            phone="56900000000",
            answer="Respuesta de saludo del Agente Central",
            employee={"cargo": "Supervisor"},
            source_text="hola",
        )

        self.assertTrue(sent)
        self.assertEqual(post.call_count, 2)

        notice_payload = post.call_args_list[0].kwargs["json"]
        self.assertEqual(notice_payload["type"], "text")
        self.assertIn("🛡️ *AVISO DE USO*", notice_payload["text"]["body"])

        menu_payload = post.call_args_list[1].kwargs["json"]
        self.assertEqual(menu_payload["type"], "interactive")
        self.assertEqual(
            menu_payload["interactive"]["body"]["text"],
            "🏗️ *MENÚ PRINCIPAL JCF*\n\n¿Qué deseas realizar?",
        )
        self.assertEqual(
            [
                button["reply"]["id"]
                for button in menu_payload["interactive"]["action"]["buttons"]
            ],
            [
                "jcf_start_service",
                "jcf_close_service",
            ],
        )

    def test_usage_notice_is_blocked_by_any_active_flow(self):

        active_operations_states = (
            "location",
            "closure_observations",
            "closure_service_sheet_photo",
            "closure_work_photo",
            "closure_mitigation_cause",
        )

        for waiting_for in active_operations_states:
            with self.subTest(waiting_for=waiting_for):
                self.assertFalse(
                    should_show_usage_notice(
                        text="hola",
                        operations_session={
                            "status": "active",
                            "waiting_for": waiting_for,
                        },
                        maestro_session=None,
                    )
                )

        self.assertFalse(
            should_show_usage_notice(
                text="hola",
                operations_session=None,
                maestro_session={
                    "status": "paused",
                    "quote_number": "COT38395",
                },
            )
        )
        self.assertFalse(
            should_show_usage_notice(
                text="hola",
                operations_session=None,
                maestro_session={
                    "status": "active",
                    "quote_number": "COT38395",
                },
            )
        )

    @patch("app.whatsapp.client.requests.post")
    @patch("app.whatsapp.webhook.get_maestro_session")
    @patch("app.whatsapp.webhook.get_operations_session")
    def test_paused_maestro_greeting_does_not_send_usage_notice(
        self,
        get_operations_session,
        get_maestro_session,
        post,
    ):

        get_operations_session.return_value = None
        get_maestro_session.return_value = {
            "status": "paused",
            "quote_number": "COT38395",
        }
        response = Mock()
        response.ok = True
        response.json.return_value = {"messages": [{"id": "wamid.test"}]}
        post.return_value = response

        sent = safe_send_answer_for_current_state(
            phone="56900000000",
            answer="Respuesta de flujo existente",
            employee={"cargo": "Supervisor"},
            source_text="hola",
        )

        self.assertTrue(sent)
        post.assert_called_once()
        payload = post.call_args.kwargs["json"]
        self.assertNotIn("AVISO DE USO", str(payload))

    @patch("app.whatsapp.client.requests.post")
    @patch("app.whatsapp.webhook.get_maestro_session")
    @patch("app.whatsapp.webhook.get_operations_session")
    def test_pending_field_report_payload_contains_resume_buttons(
        self,
        get_operations_session,
        get_maestro_session,
        post,
    ):

        get_operations_session.return_value = None
        get_maestro_session.return_value = None
        response = Mock()
        response.ok = True
        response.json.return_value = {"messages": [{"id": "wamid.test"}]}
        post.return_value = response

        answer = (
            "📋 Levantamiento pendiente\n\n"
            "El servicio *COT38395 - Cotización* todavía tiene un "
            "levantamiento técnico pendiente.\n\n"
            "⚠️ Para cerrar una cotización, primero debes completar "
            "y guardar su levantamiento.\n\n"
            "Puedes retomarlo ahora para continuar."
        )

        sent = safe_send_answer_for_current_state(
            phone="56900000000",
            answer=answer,
            employee={"cargo": "Supervisor"},
        )

        self.assertTrue(sent)
        post.assert_called_once()
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["type"], "interactive")
        self.assertEqual(payload["interactive"]["type"], "button")
        payload_buttons = payload["interactive"]["action"]["buttons"]
        self.assertEqual(
            [
                button["reply"]["id"]
                for button in payload_buttons
            ],
            [
                BUTTON_RESUME_FIELD_SURVEY,
                BUTTON_BACK_HOME,
            ],
        )
        self.assertEqual(
            payload_buttons[0]["reply"]["title"],
            "Retomar",
        )
        self.assertEqual(
            payload_buttons[1]["reply"]["title"],
            "← Volver al inicio",
        )
        self.assertNotIn("jcf_start_service", str(payload_buttons))
        self.assertNotIn("jcf_close_service", str(payload_buttons))

    @patch("app.whatsapp.client.requests.post")
    def test_visible_payloads_strip_only_internal_agent_headers(self, post):

        response = Mock()
        response.ok = True
        response.json.return_value = {"messages": []}
        post.return_value = response

        send_whatsapp_message(
            phone="56900000000",
            message=(
                "👷 *Agente Operacional JCF*\n\n"
                "Inicio de servicio registrado"
            ),
        )
        send_whatsapp_buttons(
            phone="56900000000",
            body="*Agente Maestro JCF*\n\n¿En qué sector específico?",
            buttons=[{"id": "volver", "title": "Volver"}],
        )
        send_whatsapp_location_request(
            phone="56900000000",
            body="Asistente Central JCF\n\nComparte tu ubicación.",
        )

        payloads = [
            call.kwargs["json"]
            for call in post.call_args_list
        ]
        self.assertEqual(
            payloads[0]["text"]["body"],
            "Inicio de servicio registrado",
        )
        self.assertEqual(
            payloads[1]["interactive"]["body"]["text"],
            "¿En qué sector específico?",
        )
        self.assertEqual(
            payloads[2]["interactive"]["body"]["text"],
            "Comparte tu ubicación.",
        )

        send_whatsapp_message(
            phone="56900000000",
            message="Supervisor: Agente Operacional de turno",
        )
        self.assertEqual(
            post.call_args.kwargs["json"]["text"]["body"],
            "Supervisor: Agente Operacional de turno",
        )

    @patch("app.whatsapp.webhook.safe_send_whatsapp_location_request")
    @patch("app.whatsapp.webhook.safe_send_whatsapp_message")
    def test_activation_pending_does_not_request_location_again(
        self,
        send_message,
        send_location,
    ):

        send_message.return_value = True
        session = create_session(
            phone="activation-pending-test",
            action="START_SERVICE",
        )
        session.update(
            {
                "waiting_for": "service_activation",
                "start_activity_created": True,
                "activity_record_id": "rec-activity",
            }
        )
        save_session(
            phone="activation-pending-test",
            session=session,
        )

        try:
            sent = safe_send_answer_for_current_state(
                phone="activation-pending-test",
                answer="No pude activar el servicio; puedes reintentar.",
                employee={"cargo": "Supervisor"},
            )
        finally:
            clear_session("activation-pending-test")

        self.assertTrue(sent)
        send_location.assert_not_called()
        send_message.assert_called_once()

    @patch(
        "app.whatsapp.client.requests.post"
    )
    def test_buttons_reject_oversize_body_instead_of_truncating(
        self,
        post,
    ):

        with self.assertRaises(ValueError):
            send_whatsapp_buttons(
                phone="56900000000",
                body="x" * 1025,
                buttons=[
                    {
                        "id": "test",
                        "title": "Continuar",
                    }
                ],
            )

        post.assert_not_called()

    @patch(
        "app.whatsapp.client.requests.post"
    )
    def test_location_request_uses_native_cloud_api_payload(
        self,
        post,
    ):

        response = Mock()
        response.ok = True
        response.json.return_value = {
            "messages": [],
        }
        post.return_value = response

        send_whatsapp_location_request(
            phone="56900000000",
            body="Comparte tu ubicación actual.",
        )

        payload = post.call_args.kwargs[
            "json"
        ]

        self.assertEqual(
            payload[
                "interactive"
            ][
                "type"
            ],
            "location_request_message",
        )
        self.assertEqual(
            payload[
                "interactive"
            ][
                "action"
            ][
                "name"
            ],
            "send_location",
        )

    @patch(
        "app.whatsapp.webhook.safe_send_whatsapp_message"
    )
    @patch(
        "app.whatsapp.webhook.safe_send_whatsapp_location_request"
    )
    @patch(
        "app.whatsapp.webhook.get_operations_session"
    )
    def test_waiting_location_uses_native_request_instead_of_text_menu(
        self,
        get_operations_session,
        send_location_request,
        send_text,
    ):

        get_operations_session.return_value = {
            "action": "START_SERVICE",
            "waiting_for": "location",
            "cot": "COT12345 - OC",
            "service_address": "Dirección de prueba",
        }
        send_location_request.return_value = True

        self.assertTrue(
            is_waiting_for_operations_location(
                "56900000000"
            )
        )

        sent = safe_send_answer_for_current_state(
            phone="56900000000",
            answer="Respuesta general con menú",
        )

        self.assertTrue(
            sent
        )
        send_location_request.assert_called_once()
        send_text.assert_not_called()


class MessageDebounceTests(
    unittest.IsolatedAsyncioTestCase,
):

    async def asyncSetUp(self):

        reset_debounce_state()

    async def test_rapid_texts_produce_one_combined_message(self):

        first = asyncio.create_task(
            coalesce_text_message(
                phone="56900000000",
                text="Hola",
                window_seconds=0.03,
            )
        )

        await asyncio.sleep(
            0.005
        )

        second = asyncio.create_task(
            coalesce_text_message(
                phone="56900000000",
                text="quiero iniciar un servicio",
                window_seconds=0.03,
            )
        )

        self.assertIsNone(
            await first
        )
        self.assertEqual(
            await second,
            "Hola\nquiero iniciar un servicio",
        )

    async def test_spaced_text_burst_still_produces_one_response(self):

        tasks = []

        for text in (
            "primer mensaje",
            "segundo mensaje",
            "tercer mensaje",
        ):

            tasks.append(
                asyncio.create_task(
                    coalesce_text_message(
                        phone="56900000000",
                        text=text,
                        window_seconds=0.06,
                    )
                )
            )

            await asyncio.sleep(
                0.035
            )

        results = await asyncio.gather(
            *tasks
        )

        self.assertEqual(
            results,
            [
                None,
                None,
                (
                    "primer mensaje\n"
                    "segundo mensaje\n"
                    "tercer mensaje"
                ),
            ],
        )

    async def test_duplicate_message_id_is_processed_once(self):

        self.assertTrue(
            await register_message_id(
                "wamid.test"
            )
        )
        self.assertFalse(
            await register_message_id(
                "wamid.test"
            )
        )
