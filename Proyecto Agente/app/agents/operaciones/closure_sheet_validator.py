import json

from openai import OpenAI

from app.config import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
)

from app.agents.maestro.image_processor import (
    encode_image,
)


# ============================================================
# CLIENTE OPENAI
# ============================================================

client = OpenAI(
    api_key=OPENAI_API_KEY
)


# ============================================================
# LIMPIAR TEXTO
# ============================================================

def clean_text(
    value,
) -> str:

    return str(
        value
        or ""
    ).strip()


# ============================================================
# LIMPIAR RESPUESTA JSON
#
# Por seguridad, elimina bloques ```json ... ```
# si el modelo llegara a incluirlos.
# ============================================================

def clean_json_response(
    value,
) -> str:

    value = clean_text(
        value
    )

    if value.startswith(
        "```json"
    ):

        value = value[
            7:
        ]

    elif value.startswith(
        "```"
    ):

        value = value[
            3:
        ]

    if value.endswith(
        "```"
    ):

        value = value[
            :-3
        ]

    return value.strip()


# ============================================================
# RESPUESTA SEGURA POR DEFECTO
#
# IMPORTANTE:
#
# Ante error, duda o respuesta inválida:
#
# NO aprobamos automáticamente la hoja.
# ============================================================

def build_safe_validation_result(
    reason: str,
    error: str = None,
) -> dict:

    return {
        "valid": False,

        "is_service_closure_sheet": False,

        "stamp_detected": False,

        "stamp_status": "uncertain",

        "signature_detected": False,

        "confidence": "low",

        "reason": clean_text(
            reason
        ),

        "error": (
            clean_text(
                error
            )
            or None
        ),
    }


# ============================================================
# VALIDAR HOJA DE CIERRE DE SERVICIO
#
# OBJETIVO:
#
# 1. Confirmar que la fotografía corresponde realmente
#    a una Hoja de Cierre / Servicio JCF.
#
# 2. Confirmar visualmente la existencia de un TIMBRE
#    físico de recepción / conformidad del cliente.
#
# 3. Detectar firma como información adicional.
#
# IMPORTANTE:
#
# La firma NO es requisito obligatorio.
#
# El TIMBRE sí es requisito obligatorio.
#
# Si existe duda:
#
# stamp_status = "uncertain"
#
# y NO se permite avanzar.
# ============================================================

def validate_closure_sheet(
    file_path: str,
    mime_type: str = "image/jpeg",
) -> dict:

    file_path = clean_text(
        file_path
    )

    mime_type = (
        clean_text(
            mime_type
        )
        or "image/jpeg"
    )

    # ========================================================
    # VALIDAR RUTA
    # ========================================================

    if not file_path:

        return build_safe_validation_result(
            reason="missing_file_path"
        )

    # ========================================================
    # CODIFICAR IMAGEN
    # ========================================================

    try:

        image_base64 = encode_image(
            file_path
        )

    except Exception as error:

        print()
        print("=" * 70)
        print("❌ ERROR CODIFICANDO HOJA DE CIERRE")
        print("=" * 70)

        print(
            type(error).__name__,
            str(error),
        )

        print("=" * 70)

        return build_safe_validation_result(
            reason="image_encode_error",
            error=str(
                error
            ),
        )

    # ========================================================
    # PROMPT VISUAL
    # ========================================================

    prompt = """
Eres el validador visual del Agente Operacional de JCF.

La imagen que recibirás supuestamente corresponde a una
HOJA DE CIERRE DE SERVICIO utilizada por JCF en terreno.

Tu función NO es transcribir todo el documento.

Tu función es validar visualmente dos cosas principales:

1. Que la fotografía realmente parezca corresponder a una
   hoja/formulario de servicio o cierre de servicio de JCF.

2. Que exista un TIMBRE FÍSICO visible de recepción,
   conformidad, mantenimiento, responsable, cliente,
   local o empresa atendida.

Debes ser conservador.

============================================================
QUÉ PUEDE CONSIDERARSE HOJA DE CIERRE
============================================================

Puede considerarse hoja de cierre cuando visualmente se
observa un formulario técnico de JCF o JCF Servicios con
elementos compatibles con una hoja de trabajo o servicio,
por ejemplo:

- logo JCF / JCF Servicios,
- datos del servicio,
- número de presupuesto o servicio,
- nombre del local,
- ubicación,
- fecha,
- motivo de solicitud,
- descripción de trabajo,
- materiales,
- mano de obra,
- maquinaria o herramientas,
- observaciones,
- espacios de firma,
- espacios para timbre o recepción.

No es necesario que todos esos elementos estén visibles,
pero debe existir evidencia suficiente de que se trata
del documento correcto.

============================================================
QUÉ SE CONSIDERA TIMBRE VÁLIDO
============================================================

Un timbre válido debe parecer un sello físico aplicado
sobre el documento después de su impresión.

Puede contener, por ejemplo:

- nombre del cliente,
- nombre del local,
- departamento de mantenimiento,
- recepción,
- responsable,
- empresa,
- RUT,
- cargo,
- fecha,
- palabras de conformidad,
- sello rectangular,
- sello circular,
- tinta superpuesta al formulario.

Ejemplos conceptuales:

"Walmart Chile"
"Departamento de Mantenimiento"
"Responsable"
"RUT"
"Recepción Conforme"

No necesitas leer perfectamente el texto del timbre.
Lo importante es identificar visualmente que existe un
sello o timbre físico real sobre el documento.

============================================================
NO CONFUNDIR CON TIMBRE
============================================================

NO debes considerar como timbre:

- el logo impreso de JCF,
- el logo impreso del cliente,
- encabezados del formulario,
- textos preimpresos,
- cajas o líneas del formulario,
- código o número de la hoja,
- escritura manuscrita normal,
- una firma por sí sola,
- fotografías,
- marcas del papel,
- elementos gráficos impresos originalmente.

Una firma manuscrita NO equivale automáticamente a timbre.

============================================================
ESTADO DEL TIMBRE
============================================================

Debes clasificar el timbre utilizando exactamente uno
de estos valores:

"detected"
"not_detected"
"uncertain"

Usa:

"detected"
solo cuando existe evidencia visual suficientemente clara
de un timbre físico.

"not_detected"
cuando la hoja se aprecia correctamente pero no se observa
ningún timbre físico.

"uncertain"
cuando existe algo que podría ser un timbre pero la imagen
es borrosa, está cortada, oscura, distante o no permite
confirmarlo con suficiente seguridad.

============================================================
FIRMA
============================================================

También indica si visualmente parece existir una firma.

La firma NO determina si el cierre es válido.
Solo se registra como información adicional.

============================================================
REGLAS IMPORTANTES
============================================================

No inventes.

No asumas que existe timbre solo porque existe una firma.

No asumas que el logo de Walmart, JCF u otra empresa
corresponde a un timbre.

Si no puedes distinguir claramente un timbre de un elemento
impreso, utiliza "uncertain".

Si la fotografía no parece una hoja de servicio/cierre de
JCF, is_service_closure_sheet debe ser false.

============================================================
RESPUESTA
============================================================

Devuelve SOLAMENTE JSON válido.

Utiliza exactamente esta estructura:

{
    "is_service_closure_sheet": true,
    "stamp_detected": true,
    "stamp_status": "detected",
    "signature_detected": true,
    "confidence": "high",
    "reason": "Descripción breve de la evidencia visual observada."
}

confidence solamente puede ser:

"high"
"medium"
"low"

stamp_detected debe ser true SOLAMENTE cuando
stamp_status sea exactamente "detected".

Si stamp_status es "not_detected" o "uncertain",
stamp_detected debe ser false.
"""

    # ========================================================
    # CONSULTAR IA
    # ========================================================

    try:

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

    except Exception as error:

        print()
        print("=" * 70)
        print("❌ ERROR IA VALIDANDO HOJA DE CIERRE")
        print("=" * 70)

        print(
            type(error).__name__,
            str(error),
        )

        print("=" * 70)

        return build_safe_validation_result(
            reason="openai_validation_error",
            error=str(
                error
            ),
        )

    # ========================================================
    # TEXTO DEVUELTO
    # ========================================================

    raw = clean_json_response(
        response.output_text
    )

    print()
    print("=" * 70)
    print("🤖 RESPUESTA IA - HOJA DE CIERRE")
    print("=" * 70)

    print(
        raw
    )

    print("=" * 70)

    # ========================================================
    # PARSEAR JSON
    # ========================================================

    try:

        result = json.loads(
            raw
        )

    except json.JSONDecodeError as error:

        print()
        print("=" * 70)
        print("❌ JSON INVÁLIDO EN VALIDACIÓN DE HOJA")
        print("=" * 70)

        print(
            str(error)
        )

        print(
            "Respuesta:",
            raw,
        )

        print("=" * 70)

        return build_safe_validation_result(
            reason="invalid_ai_json",
            error=str(
                error
            ),
        )

    if not isinstance(
        result,
        dict,
    ):

        return build_safe_validation_result(
            reason="invalid_ai_result"
        )

    # ========================================================
    # NORMALIZAR RESULTADOS
    # ========================================================

    is_service_closure_sheet = bool(
        result.get(
            "is_service_closure_sheet"
        )
    )

    stamp_status = clean_text(
        result.get(
            "stamp_status"
        )
    ).lower()

    if stamp_status not in (
        "detected",
        "not_detected",
        "uncertain",
    ):

        stamp_status = (
            "uncertain"
        )

    # ========================================================
    # NO CONFIAMOS CIEGAMENTE EN stamp_detected
    #
    # Lo derivamos nosotros desde stamp_status.
    # ========================================================

    stamp_detected = (
        stamp_status
        == "detected"
    )

    signature_detected = bool(
        result.get(
            "signature_detected"
        )
    )

    confidence = clean_text(
        result.get(
            "confidence"
        )
    ).lower()

    if confidence not in (
        "high",
        "medium",
        "low",
    ):

        confidence = "low"

    reason = clean_text(
        result.get(
            "reason"
        )
    )

    # ========================================================
    # REGLA FINAL
    #
    # Para ser válida:
    #
    # - debe ser hoja de cierre;
    # - el timbre debe estar DETECTADO.
    # ========================================================

    valid = (
        is_service_closure_sheet
        and stamp_detected
    )

    validation = {
        "valid": valid,

        "is_service_closure_sheet":
            is_service_closure_sheet,

        "stamp_detected":
            stamp_detected,

        "stamp_status":
            stamp_status,

        "signature_detected":
            signature_detected,

        "confidence":
            confidence,

        "reason":
            reason,

        "error":
            None,
    }

    # ========================================================
    # DEBUG FINAL
    # ========================================================

    print()
    print("=" * 70)
    print("🔍 VALIDACIÓN HOJA DE CIERRE")
    print("=" * 70)

    print(
        "Es hoja de cierre:",
        is_service_closure_sheet,
    )

    print(
        "Estado timbre:",
        stamp_status,
    )

    print(
        "Timbre detectado:",
        stamp_detected,
    )

    print(
        "Firma detectada:",
        signature_detected,
    )

    print(
        "Confianza:",
        confidence,
    )

    print(
        "Válida:",
        valid,
    )

    print(
        "Motivo:",
        reason,
    )

    print("=" * 70)

    return validation