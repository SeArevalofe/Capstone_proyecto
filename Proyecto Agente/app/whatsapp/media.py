import mimetypes
import os
import tempfile
import uuid

from pathlib import Path
from PIL import Image

import requests

from app.config import (
    WHATSAPP_ACCESS_TOKEN,
    WHATSAPP_API_VERSION,
    MEDIA_DIR,
)


# ============================================================
# OBTENER INFORMACIÓN DEL ARCHIVO DESDE META
# ============================================================

def get_media_info(
    media_id: str,
) -> dict:

    url = (
        f"https://graph.facebook.com/"
        f"{WHATSAPP_API_VERSION}/"
        f"{media_id}"
    )

    headers = {
        "Authorization": (
            f"Bearer {WHATSAPP_ACCESS_TOKEN}"
        )
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=30,
    )

    if not response.ok:

        print()
        print("=" * 60)
        print("❌ ERROR OBTENIENDO MEDIA")
        print("=" * 60)

        print(
            "Status:",
            response.status_code,
        )

        print(
            response.text
        )

        print("=" * 60)

    response.raise_for_status()

    return response.json()


# ============================================================
# DESCARGAR ARCHIVO
#
# temporary=False
#     Guarda normalmente en storage/media.
#     Se utiliza, por ejemplo, para imágenes.
#
# temporary=True
#     Guarda en carpeta temporal del sistema.
#     Se utiliza para audios.
#
#     Posteriormente webhook.py lo elimina.
# ============================================================

def download_media(
    media_id: str,
    phone: str,
    temporary: bool = False,
) -> dict:

    media_info = get_media_info(
        media_id
    )

    download_url = media_info.get(
        "url"
    )

    mime_type = (
        media_info.get(
            "mime_type"
        )
        or "application/octet-stream"
    )

    if not download_url:

        raise RuntimeError(
            "Meta no entregó URL para descargar el archivo."
        )

    headers = {
        "Authorization": (
            f"Bearer {WHATSAPP_ACCESS_TOKEN}"
        )
    }

    response = requests.get(
        download_url,
        headers=headers,
        timeout=60,
    )

    if not response.ok:

        print()
        print("=" * 60)
        print("❌ ERROR DESCARGANDO MEDIA")
        print("=" * 60)

        print(
            "Status:",
            response.status_code,
        )

        print(
            response.text
        )

        print("=" * 60)

    response.raise_for_status()

    extension = get_extension(
        mime_type
    )

    # ========================================================
    # ARCHIVO TEMPORAL
    #
    # Ideal para audio:
    #
    # /var/folders/.../tmpxxxx.ogg
    #
    # No queda dentro de storage/media.
    # ========================================================

    if temporary:

        temp_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=extension,
            prefix=(
                f"jcf_{phone}_"
            ),
        )

        try:

            temp_file.write(
                response.content
            )

            temp_file.flush()

        finally:

            temp_file.close()

        file_path = Path(
            temp_file.name
        )

        filename = file_path.name

        storage_type = "temporary"

    # ========================================================
    # ARCHIVO PERSISTENTE
    #
    # Se mantiene para imágenes u otros archivos que sí
    # necesitemos conservar temporalmente en storage/media.
    # ========================================================

    else:

        filename = (
            f"{phone}_"
            f"{uuid.uuid4().hex}"
            f"{extension}"
        )

        file_path = (
            Path(MEDIA_DIR)
            / filename
        )

        with open(
            file_path,
            "wb",
        ) as file:

            file.write(
                response.content
            )

        storage_type = "persistent"

    print()
    print("=" * 60)
    print("📥 MEDIA DESCARGADA")
    print("=" * 60)

    print(
        "Media ID:",
        media_id,
    )

    print(
        "Tipo:",
        mime_type,
    )

    print(
        "Modo:",
        storage_type,
    )

    print(
        "Path:",
        str(
            file_path
        ),
    )

    print("=" * 60)

    return {
        "media_id": media_id,

        "filename": filename,

        "path": str(
            file_path
        ),

        "mime_type": mime_type,

        "sha256": media_info.get(
            "sha256"
        ),

        "temporary": temporary,

        "storage_type": storage_type,
    }


# ============================================================
# ELIMINAR ARCHIVO LOCAL
# ============================================================

def delete_media_file(
    file_path,
) -> bool:

    if not file_path:

        return False

    try:

        path = Path(
            file_path
        )

        if not path.exists():

            print(
                "ℹ️ Archivo ya no existe:",
                str(
                    path
                ),
            )

            return True

        if not path.is_file():

            print(
                "⚠️ La ruta no corresponde "
                "a un archivo:",
                str(
                    path
                ),
            )

            return False

        path.unlink()

        print()
        print("=" * 60)
        print("🧹 ARCHIVO TEMPORAL ELIMINADO")
        print("=" * 60)

        print(
            str(
                path
            )
        )

        print("=" * 60)

        return True

    except Exception as error:

        print()
        print("=" * 60)
        print("⚠️ ERROR ELIMINANDO ARCHIVO TEMPORAL")
        print("=" * 60)

        print(
            type(error).__name__,
            str(error),
        )

        print(
            "Archivo:",
            file_path,
        )

        print("=" * 60)

        return False


# ============================================================
# EXTENSIÓN
# ============================================================

def get_extension(
    mime_type: str,
) -> str:

    # Quitar parámetros como:
    #
    # audio/ogg; codecs=opus
    #
    # y dejar solamente:
    #
    # audio/ogg

    clean_mime = (
        str(
            mime_type
            or ""
        )
        .split(";")[0]
        .strip()
        .lower()
    )

    known_types = {

        # AUDIO
        "audio/ogg": ".ogg",
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/mp4": ".m4a",
        "audio/x-m4a": ".m4a",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/webm": ".webm",

        # IMAGEN
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/heic": ".heic",
        "image/heif": ".heif",

        # DOCUMENTOS
        "application/pdf": ".pdf",
    }

    if clean_mime in known_types:

        return known_types[
            clean_mime
        ]

    extension = mimetypes.guess_extension(
        clean_mime
    )

    if extension:

        return extension

    return ".bin"


# ============================================================
# OPTIMIZACIÓN DE IMAGEN
# ============================================================

def optimize_image(
    file_path: str,
    max_width: int = 1600,
    quality: int = 75,
) -> str:

    path = Path(
        file_path
    )

    if not path.exists():

        raise FileNotFoundError(
            f"No existe la imagen: {file_path}"
        )

    optimized_path = (
        path.parent
        / f"{path.stem}_optimized.jpg"
    )

    try:

        from PIL import (
            Image,
            ImageOps,
        )

        with Image.open(
            path
        ) as image:

            # =================================================
            # CORREGIR ORIENTACIÓN DE CELULAR / EXIF
            # =================================================

            image = ImageOps.exif_transpose(
                image
            )

            # =================================================
            # CONVERTIR A RGB
            # =================================================

            if image.mode != "RGB":

                image = image.convert(
                    "RGB"
                )

            # =================================================
            # REDIMENSIONAR CONSERVANDO PROPORCIÓN
            #
            # Nunca agranda la imagen.
            # =================================================

            width, height = image.size

            if width > max_width:

                ratio = (
                    max_width
                    / float(
                        width
                    )
                )

                new_height = max(
                    1,
                    int(
                        height
                        * ratio
                    ),
                )

                image = image.resize(
                    (
                        max_width,
                        new_height,
                    ),
                    Image.Resampling.LANCZOS,
                )

            # =================================================
            # GUARDAR JPEG OPTIMIZADO
            # =================================================

            image.save(
                optimized_path,
                format="JPEG",
                quality=quality,
                optimize=True,
                progressive=True,
            )

    except Exception:

        # Eliminar archivo parcialmente generado,
        # si ocurrió algún error durante la optimización.

        if optimized_path.exists():

            try:

                optimized_path.unlink()

            except Exception:

                pass

        raise

    print()
    print("=" * 60)
    print("🗜️ IMAGEN OPTIMIZADA")
    print("=" * 60)

    print(
        "Original:",
        path
    )

    print(
        "Optimizada:",
        optimized_path
    )

    try:

        original_size = (
            path.stat().st_size
        )

        optimized_size = (
            optimized_path.stat().st_size
        )

        print(
            "Peso original:",
            round(
                original_size / 1024,
                1,
            ),
            "KB",
        )

        print(
            "Peso optimizado:",
            round(
                optimized_size / 1024,
                1,
            ),
            "KB",
        )

        if original_size > 0:

            reduction = (
                (
                    original_size
                    - optimized_size
                )
                / original_size
                * 100
            )

            print(
                "Reducción:",
                f"{round(reduction, 1)}%",
            )

    except Exception:

        pass

    print("=" * 60)

    return str(
        optimized_path
    )