import base64
import json

from openai import OpenAI

from app.config import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
)


client = OpenAI(
    api_key=OPENAI_API_KEY
)


def analyze_field_image(
    file_path: str,
    mime_type: str,
) -> dict:

    image_base64 = encode_image(
        file_path
    )

    prompt = """
Eres el analizador visual del Agente JFC.

Esta fotografía fue tomada por un maestro durante
un levantamiento técnico en terreno.

Analiza SOLO lo que realmente puedes observar.

Puedes identificar, cuando sea visible:

- tipo de elemento o estructura,
- material aparente,
- grietas,
- óxido,
- pintura desprendida,
- humedad,
- daños,
- deterioro,
- obstáculos,
- condiciones de acceso,
- trabajos que aparentemente podrían estar relacionados.

NO inventes:

- dimensiones,
- cantidades,
- marcas,
- espesores,
- materiales no visibles,
- causas de daños,
- soluciones definitivas.

Una fotografía NO reemplaza la confirmación del maestro.

Devuelve solamente JSON válido:

{
    "description": "Descripción técnica breve y profesional",
    "observed_conditions": [],
    "possible_element": null,
    "requires_confirmation": []
}
"""

    response = client.responses.create(
        model=OPENAI_MODEL,

        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": prompt,
                    },
                    {
                        "type": "input_image",
                        "image_url": (
                            f"data:{mime_type};"
                            f"base64,{image_base64}"
                        ),
                    },
                ],
            }
        ],

        store=False,
    )

    raw = (
        response
        .output_text
        .strip()
    )

    try:

        return json.loads(
            raw
        )

    except json.JSONDecodeError:

        return {
            "description": raw,
            "observed_conditions": [],
            "possible_element": None,
            "requires_confirmation": [],
        }


def encode_image(
    file_path: str,
) -> str:

    with open(
        file_path,
        "rb",
    ) as image_file:

        return (
            base64
            .b64encode(
                image_file.read()
            )
            .decode(
                "utf-8"
            )
        )