
import re

import requests

from app.config import (
    WHATSAPP_ACCESS_TOKEN,
    WHATSAPP_PHONE_NUMBER_ID,
    WHATSAPP_API_VERSION,
)


WHATSAPP_INTERACTIVE_BODY_LIMIT = 1024

INTERNAL_AGENT_HEADER_PATTERN = re.compile(
    r"^\s*(?:[^\w\s*]+\s*)?\*?"
    r"(?:Agente(?:\s+(?:Operacional|Maestro))?(?:\s+JCF)?|"
    r"Asistente\s+Central(?:\s+JCF)?)"
    r"\*?\s*(?:\r?\n\s*)*",
    re.IGNORECASE,
)


def sanitize_whatsapp_text(
    value,
) -> str:

    text = str(
        value
        or ""
    )

    return INTERNAL_AGENT_HEADER_PATTERN.sub(
        "",
        text,
        count=1,
    ).lstrip(
        "\r\n"
    )


def send_whatsapp_message(
    phone: str,
    message: str,
) -> dict:

    message = sanitize_whatsapp_text(
        message
    )

    url = (
        f"https://graph.facebook.com/"
        f"{WHATSAPP_API_VERSION}/"
        f"{WHATSAPP_PHONE_NUMBER_ID}/messages"
    )

    headers = {
        "Authorization": (
            f"Bearer {WHATSAPP_ACCESS_TOKEN}"
        ),
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone,
        "type": "text",
        "text": {
            "body": message,
        },
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=20,
    )

    if not response.ok:
        print(
            "Error WhatsApp:",
            response.status_code,
            response.text,
        )

    response.raise_for_status()

    return response.json()


# ============================================================
# ENVIAR BOTONES INTERACTIVOS
# ============================================================

def send_whatsapp_buttons(
    phone: str,
    body: str,
    buttons: list,
    footer: str = "",
) -> dict:

    body_text = sanitize_whatsapp_text(
        body
        or "Selecciona una opción."
    )

    if len(body_text) > WHATSAPP_INTERACTIVE_BODY_LIMIT:
        raise ValueError(
            "El cuerpo interactivo excede el límite de WhatsApp; "
            "debe dividirse antes de enviarlo."
        )

    clean_buttons = []

    for button in buttons or []:

        if not isinstance(
            button,
            dict,
        ):
            continue

        button_id = str(
            button.get(
                "id"
            )
            or ""
        ).strip()

        title = str(
            button.get(
                "title"
            )
            or ""
        ).strip()

        if not button_id or not title:
            continue

        clean_buttons.append(
            {
                "type": "reply",
                "reply": {
                    "id": button_id[:256],
                    "title": title[:20],
                },
            }
        )

        # WhatsApp admite hasta 3 reply buttons.
        if len(
            clean_buttons
        ) >= 3:
            break

    if not clean_buttons:
        raise ValueError(
            "No hay botones válidos para enviar."
        )

    url = (
        f"https://graph.facebook.com/"
        f"{WHATSAPP_API_VERSION}/"
        f"{WHATSAPP_PHONE_NUMBER_ID}/messages"
    )

    headers = {
        "Authorization": (
            f"Bearer {WHATSAPP_ACCESS_TOKEN}"
        ),
        "Content-Type": "application/json",
    }

    interactive = {
        "type": "button",
        "body": {
            "text": body_text,
        },
        "action": {
            "buttons": clean_buttons,
        },
    }

    footer_text = str(
        footer
        or ""
    ).strip()

    if footer_text:
        interactive[
            "footer"
        ] = {
            "text": footer_text[:60],
        }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone,
        "type": "interactive",
        "interactive": interactive,
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=20,
    )

    if not response.ok:
        print(
            "Error WhatsApp interactive:",
            response.status_code,
            response.text,
        )

    response.raise_for_status()

    return response.json()


def send_whatsapp_list(
    phone: str,
    body: str,
    rows: list,
    button: str = "Seleccionar",
    section_title: str = "Opciones",
) -> dict:

    body_text = sanitize_whatsapp_text(
        body or "Selecciona una opción."
    )
    if len(body_text) > WHATSAPP_INTERACTIVE_BODY_LIMIT:
        raise ValueError(
            "El cuerpo interactivo excede el límite de WhatsApp."
        )

    clean_rows = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        row_id = str(row.get("id") or "").strip()
        title = str(row.get("title") or "").strip()
        description = str(row.get("description") or "").strip()
        if not row_id or not title:
            continue
        clean_row = {
            "id": row_id[:200],
            "title": title[:24],
        }
        if description:
            clean_row["description"] = description[:72]
        clean_rows.append(clean_row)

    if not clean_rows:
        raise ValueError("No hay opciones válidas para enviar.")

    url = (
        f"https://graph.facebook.com/"
        f"{WHATSAPP_API_VERSION}/"
        f"{WHATSAPP_PHONE_NUMBER_ID}/messages"
    )
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": body_text},
            "action": {
                "button": str(button or "Seleccionar")[:20],
                "sections": [
                    {
                        "title": str(section_title or "Opciones")[:24],
                        "rows": clean_rows,
                    }
                ],
            },
        },
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=20,
    )
    if not response.ok:
        print(
            "Error WhatsApp interactive list:",
            response.status_code,
            response.text,
        )
    response.raise_for_status()
    return response.json()

# ============================================================
# SOLICITAR UBICACIÓN NATIVA DE WHATSAPP
# ============================================================

def send_whatsapp_location_request(
    phone: str,
    body: str,
) -> dict:

    body_text = sanitize_whatsapp_text(
        body
        or "Comparte tu ubicación actual para continuar."
    )

    if len(body_text) > WHATSAPP_INTERACTIVE_BODY_LIMIT:
        raise ValueError(
            "La solicitud de ubicación excede el límite de WhatsApp."
        )

    url = (
        f"https://graph.facebook.com/"
        f"{WHATSAPP_API_VERSION}/"
        f"{WHATSAPP_PHONE_NUMBER_ID}/messages"
    )

    headers = {
        "Authorization": (
            f"Bearer {WHATSAPP_ACCESS_TOKEN}"
        ),
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone,
        "type": "interactive",
        "interactive": {
            "type": "location_request_message",
            "body": {
                "text": body_text,
            },
            "action": {
                "name": "send_location",
            },
        },
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=20,
    )

    if not response.ok:
        print(
            "Error WhatsApp location request:",
            response.status_code,
            response.text,
        )

    response.raise_for_status()

    return response.json()


# ============================================================

# MARCAR COMO LEÍDO + INDICADOR "ESCRIBIENDO..."

# ============================================================

def send_typing_indicator(

    message_id: str,

) -> bool:

    if not message_id:

        return False

    url = (

        f"https://graph.facebook.com/"

        f"{WHATSAPP_API_VERSION}/"

        f"{WHATSAPP_PHONE_NUMBER_ID}/messages"

    )

    headers = {

        "Authorization": (

            f"Bearer {WHATSAPP_ACCESS_TOKEN}"

        ),

        "Content-Type": "application/json",

    }

    payload = {

        "messaging_product": "whatsapp",

        "status": "read",

        "message_id": message_id,

        "typing_indicator": {

            "type": "text",

        },

    }

    try:

        response = requests.post(

            url,

            headers=headers,

            json=payload,

            timeout=10,

        )

        print()

        print("=" * 60)

        print("⌨️ WHATSAPP - TYPING")

        print("=" * 60)

        print(

            "Message ID:",

            message_id,

        )

        print(

            "Status:",

            response.status_code,

        )

        if not response.ok:

            print(

                "⚠️ Respuesta Meta:",

                response.text,

            )

            return False

        print(

            "✅ Mensaje marcado como leído "

            "y typing solicitado."

        )

        print("=" * 60)

        return True

    except Exception as error:

        print()

        print("=" * 60)

        print("⚠️ ERROR TYPING WHATSAPP")

        print("=" * 60)

        print(

            type(error).__name__,

            str(error),

        )

        print("=" * 60)

        return False
