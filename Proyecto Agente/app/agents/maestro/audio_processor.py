import subprocess
import tempfile
import time

from pathlib import Path

from openai import OpenAI

from app.config import (
    OPENAI_API_KEY,
    OPENAI_TRANSCRIPTION_MODEL,
)


client = OpenAI(
    api_key=OPENAI_API_KEY,
    timeout=20.0,
    max_retries=1,
)


SUPPORTED_OPENAI_AUDIO_EXTENSIONS = {
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpga",
    ".m4a",
    ".ogg",
    ".wav",
    ".webm",
}


# ============================================================
# TRANSCRIBIR AUDIO
# ============================================================

def transcribe_audio(
    file_path: str,
) -> str:

    print()
    print("=" * 60)
    print("🎙️ PROCESANDO AUDIO")
    print("=" * 60)

    source_path = Path(
        file_path
    )

    if not source_path.exists():

        raise FileNotFoundError(
            f"No existe el archivo de audio: {file_path}"
        )

    print(
        "📁 Archivo original:",
        source_path
    )

    # ========================================================
    # 1. PREPARAR AUDIO PARA OPENAI
    # ========================================================

    prepared_path = prepare_audio_for_openai(
        source_path
    )

    print(
        "🎧 Archivo preparado:",
        prepared_path
    )

    # ========================================================
    # 2. TRANSCRIBIR
    # ========================================================

    if prepared_path == source_path:

        print(
            "📤 Enviando audio original a OpenAI..."
        )

    else:

        print(
            "📤 Enviando audio convertido a OpenAI..."
        )

    try:

        with open(
            prepared_path,
            "rb",
        ) as audio_file:

            start_time = time.time()

            transcription = (
                client
                .audio
                .transcriptions
                .create(
                    model=OPENAI_TRANSCRIPTION_MODEL,
                    file=audio_file,
                    prompt=(
                        "Audio de un maestro de JCF realizando "
                        "un levantamiento técnico en terreno. "
                        "La conversación está en español de Chile. "
                        "Puede mencionar clientes, empresas, recintos, "
                        "medidas, metros, centímetros, materiales, "
                        "pinturas, rejas, muros, puertas, pisos, "
                        "electricidad, gasfitería, reparaciones, "
                        "cantidades y trabajos de construcción. "
                        "Transcribe fielmente el contenido."
                    ),
                )
            )

            elapsed = time.time() - start_time

            print(
                f"⏱️ Transcripción completada en {elapsed:.2f} segundos"
            )

        text = (
            transcription.text
            .strip()
        )

        print()
        print("✅ AUDIO TRANSCRITO")
        print("-" * 60)
        print(text)
        print("-" * 60)

        return text

    except Exception as error:

        print()
        print("=" * 60)
        print("❌ ERROR TRANSCRIPCIÓN OPENAI")
        print("=" * 60)
        print(
            type(error).__name__,
            str(error),
        )
        print("=" * 60)

        raise

    finally:

        # Si generamos un archivo temporal,
        # lo eliminamos después de transcribir.

        if (
            prepared_path != source_path
            and prepared_path.exists()
        ):

            try:

                prepared_path.unlink()

                print(
                    "🧹 Archivo temporal eliminado."
                )

            except Exception as error:

                print(
                    "⚠️ No se pudo eliminar "
                    "el archivo temporal:",
                    error
                )


# ============================================================
# PREPARAR AUDIO PARA OPENAI
# ============================================================

def prepare_audio_for_openai(
    source_path: Path,
) -> Path:

    extension = (
        source_path
        .suffix
        .lower()
    )

    # Si ya viene en un formato aceptado,
    # no necesitamos convertirlo.

    if extension in SUPPORTED_OPENAI_AUDIO_EXTENSIONS:

        print(
            "✅ Formato compatible directamente:",
            extension
        )

        return source_path

    # ========================================================
    # WHATSAPP NORMALMENTE MANDA OGG/OPUS
    # ========================================================

    print(
        "🔄 Formato no compatible directamente:",
        extension
    )

    print(
        "🔄 Convirtiendo audio a WAV..."
    )

    temporary_file = tempfile.NamedTemporaryFile(
        suffix=".wav",
        delete=False,
    )

    temporary_file.close()

    output_path = Path(
        temporary_file.name
    )

    command = [
        "ffmpeg",

        # No mostrar demasiada información
        "-loglevel",
        "error",

        # Sobrescribir si existe
        "-y",

        # Entrada
        "-i",
        str(source_path),

        # Una sola pista de audio
        "-ac",
        "1",

        # 16 kHz es suficiente para voz
        "-ar",
        "16000",

        # PCM WAV
        "-acodec",
        "pcm_s16le",

        str(output_path),
    ]

    try:

        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )

    except FileNotFoundError:

        raise RuntimeError(
            "No se encontró FFmpeg. "
            "Instálalo en tu Mac con: brew install ffmpeg"
        )

    except subprocess.CalledProcessError as error:

        print()
        print(
            "❌ ERROR FFMPEG:"
        )

        print(
            error.stderr
        )

        raise RuntimeError(
            "No fue posible convertir el audio "
            "de WhatsApp a WAV."
        )

    if not output_path.exists():

        raise RuntimeError(
            "FFmpeg no generó el archivo WAV."
        )

    if output_path.stat().st_size == 0:

        raise RuntimeError(
            "El archivo WAV generado está vacío."
        )

    print(
        "✅ Conversión finalizada."
    )

    return output_path
