import os
import tempfile
import unittest

from pathlib import Path
from types import SimpleNamespace
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


from app.agents.maestro.audio_processor import (  # noqa: E402
    prepare_audio_for_openai,
    transcribe_audio,
)
from app.whatsapp.media import get_extension  # noqa: E402
from app.whatsapp.webhook import receive_whatsapp_message  # noqa: E402


class AudioProcessorTests(unittest.TestCase):

    def make_audio_file(self, suffix):

        temporary = tempfile.NamedTemporaryFile(
            suffix=suffix,
            delete=False,
        )
        temporary.write(b"audio-test")
        temporary.close()

        path = Path(temporary.name)
        self.addCleanup(
            lambda: path.unlink(missing_ok=True)
        )
        return path

    @patch("app.agents.maestro.audio_processor.subprocess.run")
    @patch(
        "app.agents.maestro.audio_processor."
        "client.audio.transcriptions.create"
    )
    def test_ogg_is_sent_directly_without_ffmpeg(
        self,
        create_transcription,
        run_ffmpeg,
    ):

        source_path = self.make_audio_file(".ogg")
        create_transcription.return_value = SimpleNamespace(
            text="Audio correctamente transcrito",
        )

        result = transcribe_audio(
            str(source_path)
        )

        self.assertEqual(result, "Audio correctamente transcrito")
        run_ffmpeg.assert_not_called()
        create_transcription.assert_called_once()
        self.assertEqual(
            create_transcription.call_args.kwargs["file"].name,
            str(source_path),
        )
        self.assertEqual(
            prepare_audio_for_openai(source_path),
            source_path,
        )

    def test_whatsapp_ogg_opus_mime_uses_ogg_extension(self):

        self.assertEqual(
            get_extension("audio/ogg; codecs=opus"),
            ".ogg",
        )

    @patch("app.agents.maestro.audio_processor.subprocess.run")
    @patch(
        "app.agents.maestro.audio_processor."
        "client.audio.transcriptions.create"
    )
    def test_wav_remains_directly_supported(
        self,
        create_transcription,
        run_ffmpeg,
    ):

        source_path = self.make_audio_file(".wav")
        create_transcription.return_value = SimpleNamespace(
            text="Transcripción WAV",
        )

        self.assertEqual(
            transcribe_audio(str(source_path)),
            "Transcripción WAV",
        )
        run_ffmpeg.assert_not_called()

    @patch("builtins.print")
    @patch(
        "app.agents.maestro.audio_processor."
        "client.audio.transcriptions.create"
    )
    def test_openai_error_is_logged_and_raised(
        self,
        create_transcription,
        print_mock,
    ):

        source_path = self.make_audio_file(".ogg")
        create_transcription.side_effect = RuntimeError(
            "OpenAI no disponible"
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "OpenAI no disponible",
        ):
            transcribe_audio(str(source_path))

        log_lines = [
            " ".join(str(argument) for argument in call.args)
            for call in print_mock.call_args_list
        ]
        self.assertTrue(
            any(
                "ERROR TRANSCRIPCIÓN OPENAI" in line
                for line in log_lines
            )
        )
        self.assertTrue(
            any(
                "OpenAI no disponible" in line
                for line in log_lines
            )
        )


class AudioWebhookCleanupTests(unittest.IsolatedAsyncioTestCase):

    def make_audio_file(self):

        temporary = tempfile.NamedTemporaryFile(
            suffix=".ogg",
            delete=False,
        )
        temporary.write(b"audio-test")
        temporary.close()
        return Path(temporary.name)

    def build_request(self):

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
                                            "from": "56900000000",
                                            "id": "wamid-audio-test",
                                            "type": "audio",
                                            "audio": {
                                                "id": "media-audio-test",
                                                "mime_type": (
                                                    "audio/ogg; codecs=opus"
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
        return request

    def common_patches(self, audio_path):

        return (
            patch(
                "app.whatsapp.webhook.register_message_id",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "app.whatsapp.webhook.cancel_text_burst",
                new=AsyncMock(return_value=None),
            ),
            patch("app.whatsapp.webhook.send_typing_indicator"),
            patch(
                "app.whatsapp.webhook.identify_employee",
                return_value={
                    "found": True,
                    "nombre": "Trabajador Prueba",
                    "cargo": "Técnico",
                    "record_id": "rec-worker",
                },
            ),
            patch("app.whatsapp.webhook.safe_send_whatsapp_message"),
            patch(
                "app.whatsapp.webhook.download_media",
                return_value={
                    "path": str(audio_path),
                    "mime_type": "audio/ogg; codecs=opus",
                    "temporary": True,
                },
            ),
        )

    async def test_original_temporary_audio_is_deleted_after_success(self):

        audio_path = self.make_audio_file()
        patches = self.common_patches(audio_path)

        with patches[0], patches[1], patches[2], patches[3], patches[4], \
                patches[5], \
                patch(
                    "app.whatsapp.webhook.transcribe_audio",
                    return_value="Trabajo terminado",
                ), \
                patch("app.whatsapp.webhook.register_audio_transcription"), \
                patch(
                    "app.whatsapp.webhook.process_central_message",
                    return_value="Respuesta del agente",
                ), \
                patch("app.whatsapp.webhook.safe_send_answer_for_current_state"):

            await receive_whatsapp_message(
                self.build_request()
            )

        self.assertFalse(audio_path.exists())

    async def test_original_temporary_audio_is_deleted_after_openai_error(self):

        audio_path = self.make_audio_file()
        patches = self.common_patches(audio_path)

        with patches[0], patches[1], patches[2], patches[3], \
                patches[4] as send_message, patches[5], \
                patch(
                    "app.whatsapp.webhook.transcribe_audio",
                    side_effect=RuntimeError("OpenAI no disponible"),
                ):

            await receive_whatsapp_message(
                self.build_request()
            )

        self.assertFalse(audio_path.exists())
        sent_messages = [
            call.kwargs["message"]
            for call in send_message.call_args_list
        ]
        self.assertTrue(
            any(
                "Ocurrió un problema al procesar el audio" in message
                for message in sent_messages
            )
        )
