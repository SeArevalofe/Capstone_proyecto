import os
import unittest

from unittest.mock import AsyncMock, Mock, patch

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


from app.agents.maestro.session import (  # noqa: E402
    clear_session as clear_maestro_session,
    get_session as get_maestro_session,
    start_session as start_maestro_session,
)
from app.agents.operaciones.session import (  # noqa: E402
    clear_session as clear_operations_session,
    create_session as create_operations_session,
    get_session as get_operations_session,
)
from app.whatsapp.debounce import reset_debounce_state  # noqa: E402
from app.whatsapp.webhook import (  # noqa: E402
    intercept_admin_session_reset,
    receive_whatsapp_message,
)


ADMIN_PHONES = (
    "56950903253",
    "56956063333",
    "56936426905",
)
TARGET_PHONE = "56912345678"
OTHER_PHONE = "56987654321"


class AdminSessionResetTests(unittest.IsolatedAsyncioTestCase):

    def setUp(self):

        reset_debounce_state()

        for phone in (
            *ADMIN_PHONES,
            TARGET_PHONE,
            OTHER_PHONE,
            "56900000000",
        ):
            clear_operations_session(phone)
            clear_maestro_session(phone)

    def tearDown(self):

        self.setUp()

    def create_maestro_session(self, phone):

        return start_maestro_session(
            phone=phone,
            employee={
                "record_id": "rec-worker",
                "nombre": "Trabajador Prueba",
                "cargo": "Supervisor",
            },
        )

    async def assert_authorized_admin_resets(self, admin_phone):

        create_operations_session(TARGET_PHONE, "START_SERVICE")
        self.create_maestro_session(TARGET_PHONE)

        with patch(
            "app.whatsapp.webhook.safe_send_whatsapp_message"
        ) as send_message:
            intercepted = await intercept_admin_session_reset(
                phone=admin_phone,
                text=f"/jcf-reset +{TARGET_PHONE}",
            )

        self.assertTrue(intercepted)
        self.assertIsNone(get_operations_session(TARGET_PHONE))
        self.assertIsNone(get_maestro_session(TARGET_PHONE))
        self.assertIn(
            f"Sesión reiniciada para {TARGET_PHONE}",
            send_message.call_args_list[0].kwargs["message"],
        )
        self.assertEqual(
            send_message.call_args_list[1].kwargs["phone"],
            TARGET_PHONE,
        )

    async def test_56950903253_can_reset_another_worker(self):

        await self.assert_authorized_admin_resets(ADMIN_PHONES[0])

    async def test_56956063333_can_reset_another_worker(self):

        await self.assert_authorized_admin_resets(ADMIN_PHONES[1])

    async def test_56936426905_can_reset_another_worker(self):

        await self.assert_authorized_admin_resets(ADMIN_PHONES[2])

    async def test_unauthorized_phone_cannot_reset(self):

        create_operations_session(TARGET_PHONE, "START_SERVICE")

        with patch(
            "app.whatsapp.webhook.safe_send_whatsapp_message"
        ) as send_message:
            intercepted = await intercept_admin_session_reset(
                phone="56900000000",
                text=f"/jcf-reset {TARGET_PHONE}",
            )

        self.assertTrue(intercepted)
        self.assertIsNotNone(get_operations_session(TARGET_PHONE))
        self.assertEqual(
            send_message.call_args.kwargs["message"],
            "⛔ No tienes permisos para reiniciar sesiones.",
        )

    async def test_only_target_session_is_deleted(self):

        create_operations_session(TARGET_PHONE, "START_SERVICE")
        create_operations_session(OTHER_PHONE, "CLOSE_SERVICE")

        with patch("app.whatsapp.webhook.safe_send_whatsapp_message"):
            await intercept_admin_session_reset(
                ADMIN_PHONES[0],
                f"/jcf-reset {TARGET_PHONE}",
            )

        self.assertIsNone(get_operations_session(TARGET_PHONE))
        self.assertIsNotNone(get_operations_session(OTHER_PHONE))

    async def test_admin_session_remains_active(self):

        create_operations_session(ADMIN_PHONES[0], "START_SERVICE")
        create_operations_session(TARGET_PHONE, "START_SERVICE")

        with patch("app.whatsapp.webhook.safe_send_whatsapp_message"):
            await intercept_admin_session_reset(
                ADMIN_PHONES[0],
                f"/jcf-reset {TARGET_PHONE}",
            )

        self.assertIsNotNone(get_operations_session(ADMIN_PHONES[0]))

    async def test_other_workers_keep_their_sessions(self):

        self.create_maestro_session(TARGET_PHONE)
        self.create_maestro_session(OTHER_PHONE)

        with patch("app.whatsapp.webhook.safe_send_whatsapp_message"):
            await intercept_admin_session_reset(
                ADMIN_PHONES[1],
                f"/jcf-reset {TARGET_PHONE}",
            )

        self.assertIsNone(get_maestro_session(TARGET_PHONE))
        self.assertIsNotNone(get_maestro_session(OTHER_PHONE))

    async def test_invalid_target_does_not_clear_sessions(self):

        create_operations_session(TARGET_PHONE, "START_SERVICE")

        with (
            patch(
                "app.whatsapp.webhook.clear_operations_session"
            ) as clear_operations,
            patch(
                "app.whatsapp.webhook.clear_maestro_session"
            ) as clear_maestro,
            patch(
                "app.whatsapp.webhook.safe_send_whatsapp_message"
            ) as send_message,
        ):
            intercepted = await intercept_admin_session_reset(
                ADMIN_PHONES[0],
                "/jcf-reset Matias",
            )

        self.assertTrue(intercepted)
        clear_operations.assert_not_called()
        clear_maestro.assert_not_called()
        self.assertIsNotNone(get_operations_session(TARGET_PHONE))
        self.assertIn(
            "Comando inválido",
            send_message.call_args.kwargs["message"],
        )

    async def test_target_without_session_does_not_error(self):

        with patch(
            "app.whatsapp.webhook.safe_send_whatsapp_message"
        ) as send_message:
            intercepted = await intercept_admin_session_reset(
                ADMIN_PHONES[2],
                f"/jcf-reset {TARGET_PHONE}",
            )

        self.assertTrue(intercepted)
        send_message.assert_called_once()
        self.assertIn(
            "no tenía una sesión activa",
            send_message.call_args.kwargs["message"],
        )

    async def test_webhook_reset_does_not_call_airtable_or_agents(self):

        create_operations_session(TARGET_PHONE, "START_SERVICE")

        request = Mock()
        request.json = AsyncMock(
            return_value={
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "messages": [
                                        {
                                            "from": ADMIN_PHONES[0],
                                            "id": "wamid-admin-reset",
                                            "type": "text",
                                            "text": {
                                                "body": (
                                                    "/jcf-reset "
                                                    + TARGET_PHONE
                                                ),
                                            },
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ]
            }
        )

        with (
            patch(
                "app.whatsapp.webhook.identify_employee"
            ) as identify_employee,
            patch(
                "app.whatsapp.webhook.get_employee_by_phone"
            ) as get_employee,
            patch(
                "app.whatsapp.webhook.process_central_message"
            ) as process_central,
            patch(
                "app.whatsapp.webhook.safe_send_whatsapp_message"
            ),
        ):
            response = await receive_whatsapp_message(request)

        self.assertEqual(response, {"status": "ok"})
        identify_employee.assert_not_called()
        get_employee.assert_not_called()
        process_central.assert_not_called()
        self.assertIsNone(get_operations_session(TARGET_PHONE))


if __name__ == "__main__":
    unittest.main()
