import base64
import os
from urllib.parse import quote

import requests

from typing import Optional

from app.config import (
    AIRTABLE_TOKEN,
)

# ============================================================
# CONFIGURACIÓN GENERAL AIRTABLE
# ============================================================

AIRTABLE_API_URL = (
    "https://api.airtable.com/v0"
)

# ============================================================
# HEADERS
# ============================================================

def get_headers() -> dict:

    if not AIRTABLE_TOKEN:

        raise RuntimeError(
            "No se encontró AIRTABLE_TOKEN."
        )

    return {
        "Authorization": (
            f"Bearer {AIRTABLE_TOKEN}"
        ),
        "Content-Type": "application/json",
    }

# ============================================================
# CONSTRUIR URL
# ============================================================

def get_table_url(
    base_id: str,
    table_id: str,
) -> str:

    if not base_id:

        raise ValueError(
            "base_id es obligatorio."
        )

    if not table_id:

        raise ValueError(
            "table_id es obligatorio."
        )

    return (
        f"{AIRTABLE_API_URL}/"
        f"{base_id}/"
        f"{table_id}"
    )


# ============================================================
# OBTENER REGISTROS
# ============================================================

def get_records(
    base_id: str,
    table_id: str,
    params: Optional[dict] = None,
) -> dict:

    url = get_table_url(
        base_id=base_id,
        table_id=table_id,
    )

    print()
    print("=" * 70)
    print("🔎 AIRTABLE - GET RECORDS")
    print("=" * 70)

    print(
        "Base:",
        base_id
    )

    print(
        "Tabla:",
        table_id
    )

    if params:

        print(
            "Parámetros:",
            params
        )

    print("=" * 70)

    try:

        response = requests.get(
            url,
            headers=get_headers(),
            params=params,
            timeout=20,
        )

    except requests.RequestException as error:

        print()
        print("=" * 70)
        print("❌ ERROR DE CONEXIÓN CON AIRTABLE")
        print("=" * 70)

        print(
            type(error).__name__,
            str(error),
        )

        print("=" * 70)

        raise

    print(
        "Status Airtable:",
        response.status_code
    )

    if not response.ok:

        print()
        print("=" * 70)
        print("❌ ERROR AIRTABLE")
        print("=" * 70)

        print(
            "URL:",
            url
        )

        print(
            "Status:",
            response.status_code
        )

        try:

            print(
                response.json()
            )

        except Exception:

            print(
                response.text
            )

        print("=" * 70)

        response.raise_for_status()

    return response.json()

# ============================================================
# OBTENER REGISTRO POR ID
# ============================================================

def get_record(
    base_id: str,
    table_id: str,
    record_id: str,
) -> dict:

    if not record_id:

        raise ValueError(
            "record_id es obligatorio."
        )

    table_url = get_table_url(
        base_id=base_id,
        table_id=table_id,
    )

    url = (
        f"{table_url}/"
        f"{record_id}"
    )

    print()
    print("=" * 70)
    print("🔎 AIRTABLE - GET RECORD")
    print("=" * 70)

    print(
        "Base:",
        base_id
    )

    print(
        "Tabla:",
        table_id
    )

    print(
        "Record ID:",
        record_id
    )

    print("=" * 70)

    try:

        response = requests.get(
            url,
            headers=get_headers(),
            timeout=20,
        )

    except requests.RequestException as error:

        print()
        print("=" * 70)
        print("❌ ERROR DE CONEXIÓN CON AIRTABLE")
        print("=" * 70)

        print(
            type(error).__name__,
            str(error),
        )

        print("=" * 70)

        raise

    print(
        "Status Airtable:",
        response.status_code
    )

    if response.status_code == 404:

        return {
            "found": False,
            "reason": "record_not_found",
            "record": None,
            "record_id": record_id,
        }

    if not response.ok:

        print()
        print("=" * 70)
        print("❌ ERROR AIRTABLE")
        print("=" * 70)

        print(
            response.text
        )

        print("=" * 70)

        response.raise_for_status()

    record = response.json()

    return {
        "found": True,
        "reason": None,
        "record": record,
        "record_id": record.get(
            "id"
        ),
        "fields": record.get(
            "fields",
            {},
        ),
    }

# ============================================================
# CREAR REGISTRO
# ============================================================

def create_record(
    base_id: str,
    table_id: str,
    fields: dict,
) -> dict:

    if not isinstance(
        fields,
        dict,
    ):

        raise ValueError(
            "fields debe ser un diccionario."
        )

    if not fields:

        raise ValueError(
            "No se recibieron campos para crear."
        )

    url = get_table_url(
        base_id=base_id,
        table_id=table_id,
    )

    payload = {
        "fields": fields,
    }

    print()
    print("=" * 70)
    print("➕ AIRTABLE - CREATE RECORD")
    print("=" * 70)

    print(
        "Base:",
        base_id
    )

    print(
        "Tabla:",
        table_id
    )

    print("=" * 70)

    try:

        response = requests.post(
            url,
            headers=get_headers(),
            json=payload,
            timeout=20,
        )

    except requests.RequestException as error:

        print()
        print("=" * 70)
        print("❌ ERROR DE CONEXIÓN CON AIRTABLE")
        print("=" * 70)

        print(
            type(error).__name__,
            str(error),
        )

        print("=" * 70)

        raise

    print(
        "Status Airtable:",
        response.status_code
    )

    if not response.ok:

        print()
        print("=" * 70)
        print("❌ ERROR CREANDO REGISTRO")
        print("=" * 70)

        print(
            response.text
        )

        print("=" * 70)

        response.raise_for_status()

    record = response.json()

    return {
        "created": True,
        "record": record,
        "record_id": record.get(
            "id"
        ),
        "fields": record.get(
            "fields",
            {},
        ),
    }


# ============================================================
# ACTUALIZAR REGISTRO
# ============================================================

def update_record(
    base_id: str,
    table_id: str,
    record_id: str,
    fields: dict,
) -> dict:

    if not record_id:

        raise ValueError(
            "record_id es obligatorio."
        )

    if not isinstance(
        fields,
        dict,
    ):

        raise ValueError(
            "fields debe ser un diccionario."
        )

    if not fields:

        raise ValueError(
            "No se recibieron campos para actualizar."
        )

    table_url = get_table_url(
        base_id=base_id,
        table_id=table_id,
    )

    url = (
        f"{table_url}/"
        f"{record_id}"
    )

    payload = {
        "fields": fields,
    }

    print()
    print("=" * 70)
    print("✏️ AIRTABLE - UPDATE RECORD")
    print("=" * 70)

    print(
        "Base:",
        base_id
    )

    print(
        "Tabla:",
        table_id
    )

    print(
        "Record ID:",
        record_id
    )

    print("=" * 70)

    try:

        response = requests.patch(
            url,
            headers=get_headers(),
            json=payload,
            timeout=20,
        )

    except requests.RequestException as error:

        print()
        print("=" * 70)
        print("❌ ERROR DE CONEXIÓN CON AIRTABLE")
        print("=" * 70)

        print(
            type(error).__name__,
            str(error),
        )

        print("=" * 70)

        raise

    print(
        "Status Airtable:",
        response.status_code
    )

    if not response.ok:

        print()
        print("=" * 70)
        print("❌ ERROR ACTUALIZANDO REGISTRO")
        print("=" * 70)

        print(
            response.text
        )

        print("=" * 70)

        response.raise_for_status()

    record = response.json()

    return {
        "updated": True,
        "record": record,
        "record_id": record.get(
            "id"
        ),
        "fields": record.get(
            "fields",
            {},
        ),
    }


# ============================================================
# SUBIR ARCHIVO A UN CAMPO ATTACHMENT
# ============================================================

def upload_attachment(
    base_id: str,
    record_id: str,
    field_id: str,
    file_path: str,
    filename: str = None,
    mime_type: str = "image/jpeg",
) -> dict:

    record_id = str(record_id or "").strip()
    field_id = str(field_id or "").strip()
    file_path = str(file_path or "").strip()

    if not base_id:
        return {"uploaded": False, "reason": "missing_base_id"}

    if not record_id:
        return {"uploaded": False, "reason": "missing_record_id"}

    if not field_id:
        return {"uploaded": False, "reason": "missing_field_id"}

    if not file_path:
        return {"uploaded": False, "reason": "missing_file_path"}

    if not os.path.isfile(file_path):
        return {"uploaded": False, "reason": "file_not_found"}

    filename = str(
        filename
        or os.path.basename(file_path)
        or "archivo"
    ).strip()

    try:
        with open(file_path, "rb") as file_handle:
            encoded_file = base64.b64encode(
                file_handle.read()
            ).decode("ascii")
    except OSError as error:
        return {
            "uploaded": False,
            "reason": "file_read_error",
            "error": str(error),
        }

    url = (
        "https://content.airtable.com/v0/"
        f"{base_id}/{record_id}/"
        f"{quote(field_id, safe='')}/uploadAttachment"
    )

    try:
        response = requests.post(
            url,
            headers=get_headers(),
            json={
                "contentType": str(mime_type or "image/jpeg"),
                "filename": filename,
                "file": encoded_file,
            },
            timeout=60,
        )
    except requests.RequestException as error:
        return {
            "uploaded": False,
            "reason": "airtable_connection_error",
            "error": str(error),
        }

    if not response.ok:
        return {
            "uploaded": False,
            "reason": "airtable_upload_failed",
            "status_code": response.status_code,
            "response": response.text,
        }

    try:
        result = response.json()
    except ValueError:
        result = {}

    attachments = result.get("fields", {}).get(field_id, [])
    attachment_id = None

    if isinstance(attachments, list) and attachments:
        last_attachment = attachments[-1]
        if isinstance(last_attachment, dict):
            attachment_id = last_attachment.get("id")

    return {
        "uploaded": True,
        "record_id": record_id,
        "attachment_id": attachment_id,
        "filename": filename,
        "mime_type": mime_type,
        "field_id": field_id,
    }


# ============================================================
# ELIMINAR REGISTRO
# ============================================================

def delete_record(
    base_id: str,
    table_id: str,
    record_id: str,
) -> dict:

    if not record_id:

        raise ValueError(
            "record_id es obligatorio."
        )

    table_url = get_table_url(
        base_id=base_id,
        table_id=table_id,
    )

    url = (
        f"{table_url}/"
        f"{record_id}"
    )

    print()
    print("=" * 70)
    print("🗑️ AIRTABLE - DELETE RECORD")
    print("=" * 70)

    print(
        "Base:",
        base_id
    )

    print(
        "Tabla:",
        table_id
    )

    print(
        "Record ID:",
        record_id
    )

    print("=" * 70)

    try:

        response = requests.delete(
            url,
            headers=get_headers(),
            timeout=20,
        )

    except requests.RequestException as error:

        print()
        print("=" * 70)
        print("❌ ERROR DE CONEXIÓN CON AIRTABLE")
        print("=" * 70)

        print(
            type(error).__name__,
            str(error),
        )

        print("=" * 70)

        raise

    print(
        "Status Airtable:",
        response.status_code
    )

    if not response.ok:

        print()
        print("=" * 70)
        print("❌ ERROR ELIMINANDO REGISTRO")
        print("=" * 70)

        print(
            response.text
        )

        print("=" * 70)

        response.raise_for_status()

    result = response.json()

    return {
        "deleted": result.get(
            "deleted",
            False,
        ),
        "record_id": result.get(
            "id"
        ),
    }
