import asyncio
import time


# Esperamos un breve período de silencio antes de procesar texto.
# 0,8 s separaba en dos tandas mensajes escritos con ritmo humano
# normal. La ventana es deslizante: cada texto nuevo reinicia la espera.
TEXT_BURST_WINDOW_SECONDS = 2.5
MESSAGE_ID_TTL_SECONDS = 10 * 60
MAX_SEEN_MESSAGE_IDS = 2000


_text_bursts = {}
_seen_message_ids = {}
_state_lock = asyncio.Lock()


async def register_message_id(
    message_id: str,
) -> bool:

    message_id = str(
        message_id
        or ""
    ).strip()

    if not message_id:

        return True

    now = time.monotonic()

    async with _state_lock:

        expired_before = (
            now
            - MESSAGE_ID_TTL_SECONDS
        )

        expired_ids = [
            stored_id
            for stored_id, stored_at in _seen_message_ids.items()
            if stored_at < expired_before
        ]

        for stored_id in expired_ids:

            _seen_message_ids.pop(
                stored_id,
                None,
            )

        if message_id in _seen_message_ids:

            return False

        _seen_message_ids[
            message_id
        ] = now

        if len(
            _seen_message_ids
        ) > MAX_SEEN_MESSAGE_IDS:

            oldest_ids = sorted(
                _seen_message_ids,
                key=_seen_message_ids.get,
            )[
                :len(
                    _seen_message_ids
                ) - MAX_SEEN_MESSAGE_IDS
            ]

            for stored_id in oldest_ids:

                _seen_message_ids.pop(
                    stored_id,
                    None,
                )

    return True


async def coalesce_text_message(
    phone: str,
    text: str,
    window_seconds: float = TEXT_BURST_WINDOW_SECONDS,
):

    phone = str(
        phone
        or ""
    ).strip()

    text = str(
        text
        or ""
    ).strip()

    if not phone or not text:

        return text

    token = object()

    async with _state_lock:

        burst = _text_bursts.setdefault(
            phone,
            {
                "parts": [],
                "token": None,
            },
        )

        burst[
            "parts"
        ].append(
            text
        )

        burst[
            "token"
        ] = token

    await asyncio.sleep(
        max(
            0.0,
            float(
                window_seconds
            ),
        )
    )

    async with _state_lock:

        burst = _text_bursts.get(
            phone
        )

        if (
            not isinstance(
                burst,
                dict,
            )
            or burst.get(
                "token"
            ) is not token
        ):

            return None

        parts = burst.get(
            "parts",
            [],
        )

        _text_bursts.pop(
            phone,
            None,
        )

    return "\n".join(
        part
        for part in parts
        if str(
            part
            or ""
        ).strip()
    )


async def cancel_text_burst(
    phone: str,
):

    phone = str(
        phone
        or ""
    ).strip()

    if not phone:

        return

    async with _state_lock:

        _text_bursts.pop(
            phone,
            None,
        )


def reset_debounce_state():

    _text_bursts.clear()
    _seen_message_ids.clear()
