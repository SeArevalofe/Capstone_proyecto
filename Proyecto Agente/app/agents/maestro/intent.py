import json

from openai import OpenAI

from app.config import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
)


client = OpenAI(
    api_key=OPENAI_API_KEY
)


def detect_intent(
    message: str,
    has_active_report: bool,
) -> dict:

    prompt = f"""
Eres el clasificador de intención del asistente técnico interno de JCF.

El usuario es un trabajador autorizado de JCF.

Debes interpretar lo que realmente quiere hacer aunque:
- tenga faltas de ortografía,
- use abreviaciones,
- coloque puntos o signos,
- escriba de forma informal,
- no utilice comandos exactos.

Existe un levantamiento activo:
{has_active_report}

Clasifica el mensaje en UNA de estas intenciones:

- start_report
- continue_report
- confirm_report
- cancel_report
- modify_report
- general_question

Ejemplos:

"nuevo levantamiento"
→ start_report

"quiero registrar un trabajo"
→ start_report

"nuebo lebantamiento"
→ start_report

"necesito hacer un levantamiento en terreno"
→ start_report

"partamos con otro trabajo"
→ start_report

"son 5 metros por 2,4"
→ continue_report

"la pintura será blanca"
→ continue_report

"sí está correcto"
→ confirm_report

"dale, guardar"
→ confirm_report

"cancela esto"
→ cancel_report

"me equivoqué, son 6 metros"
→ modify_report

"qué información me falta?"
→ general_question

Mensaje del usuario:
{message}

Responde SOLAMENTE JSON:

{{
    "intent": "...",
    "confidence": 0.0
}}
"""

    response = client.responses.create(
        model=OPENAI_MODEL,
        input=prompt,
        store=False,
    )

    raw = response.output_text.strip()

    try:
        return json.loads(raw)

    except json.JSONDecodeError:
        return {
            "intent": "general_question",
            "confidence": 0,
        }