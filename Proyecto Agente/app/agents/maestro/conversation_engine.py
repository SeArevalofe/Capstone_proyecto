import json

from openai import OpenAI

from app.config import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
)

from app.agents.maestro.validation import (
    expected_question_fields,
    sanitize_report_data,
)


client = OpenAI(
    api_key=OPENAI_API_KEY
)


# ============================================================
# INTENCIONES PERMITIDAS
# ============================================================

ALLOWED_INTENTS = {
    "start_report",
    "continue_report",
    "modify_report",
    "pause_report",
    "resume_report",
    "complete_report",
    "confirm_report",
    "cancel_report",
    "general_question",
    "continue_with_pending_job",
    "start_pending_new_job",
    "change_quote",
}


# ============================================================
# CAMPOS PERMITIDOS DENTRO DE DATA
# ============================================================

ALLOWED_DATA_FIELDS = {
    "cliente",
    "recinto",
    "sector",
    "tipo_trabajo",
    "descripcion",
    "dimensiones",
    "superficie_m2",
    "materiales",
    "cantidades",
    "estado_actual",
    "trabajos_requeridos",
    "equipamiento_necesario",
    "tiempo_estimado",
    "jornada",
    "personal_requerido",
    "empresa_externa_requerida",
    "empresa_externa_detalle",
    "prioridad",
    "observaciones",
}


# ============================================================
# RESULTADO POR DEFECTO
# ============================================================

def get_default_result(
    message: str = "",
    error_code: str = None,
) -> dict:

    return {
        "intent": "continue_report",

        "possible_new_job": False,

        "extracted_data": {},

        "critical_missing": [],

        "recommended_missing": [],

        "optional_missing": [],

        "next_question": (
            "No pude interpretar correctamente "
            "la información recibida. "
            "Por favor, intenta enviarla nuevamente."
        ),

        "ask_for_observations": False,

        "ready_for_report": False,

        # ====================================================
        # IMPORTANTE:
        # Python puede usar esto para NO continuar el flujo
        # como si la IA hubiese interpretado correctamente.
        # ====================================================
        "processing_error": True,

        "error_code": (
            error_code
            or "unknown_processing_error"
        ),
    }


# ============================================================
# LIMPIAR DATOS DE SESIÓN PARA LA IA
#
# IMPORTANTE:
#
# NO enviamos:
#
# - available_services
# - quote_record completo
# - records Airtable
# - fields Airtable
# - listas completas de servicios
#
# Solo enviamos lo necesario para interpretar
# el levantamiento actual.
# ============================================================

def build_ai_session_context(
    session: dict,
) -> dict:

    if not isinstance(
        session,
        dict,
    ):

        session = {}

    raw_data = session.get(
        "data",
        {},
    )

    clean_data = {}

    if isinstance(
        raw_data,
        dict,
    ):

        for field in ALLOWED_DATA_FIELDS:

            value = raw_data.get(
                field
            )

            if value is None:

                continue

            clean_data[
                field
            ] = value

    # ========================================================
    # TRABAJO PENDIENTE
    #
    # Tampoco enviamos objetos gigantes.
    # Solo extracted_data del trabajo pendiente.
    # ========================================================

    pending_new_job = session.get(
        "pending_new_job"
    )

    clean_pending_job = None

    if isinstance(
        pending_new_job,
        dict,
    ):

        pending_data = pending_new_job.get(
            "extracted_data",
            {},
        )

        if isinstance(
            pending_data,
            dict,
        ):

            clean_pending_data = {}

            for field in ALLOWED_DATA_FIELDS:

                value = pending_data.get(
                    field
                )

                if value is None:

                    continue

                clean_pending_data[
                    field
                ] = value

            clean_pending_job = {
                "extracted_data": (
                    clean_pending_data
                )
            }

    # ========================================================
    # CONTEXTO MÍNIMO
    # ========================================================

    result = {
        "quote_number": session.get(
            "quote_number"
        ),

        "selected_service_id": session.get(
            "selected_service_id"
        ),

        "oc": session.get(
            "oc"
        ),

        "service_status": session.get(
            "service_status"
        ),

        "status": session.get(
            "status"
        ),

        "last_question_field": session.get(
            "last_question_field"
        ),

        "pending_question_fields": session.get(
            "pending_question_fields",
            [],
        ),

        "last_intent": session.get(
            "last_intent"
        ),

        "ask_for_observations": session.get(
            "ask_for_observations",
            False,
        ),

        "ready_for_report": session.get(
            "ready_for_report",
            False,
        ),

        "data": clean_data,

        "pending_new_job": (
            clean_pending_job
        ),
    }

    return result


# ============================================================
# LIMPIAR EXTRACTED DATA
#
# Evitamos que la IA agregue:
#
# quote_number
# record_id
# selected_service_id
# etc.
# ============================================================

def sanitize_extracted_data(
    extracted_data,
    message: str = "",
    session: dict = None,
) -> dict:

    if not isinstance(
        extracted_data,
        dict,
    ):

        return {}

    result = {}

    for field in ALLOWED_DATA_FIELDS:

        if field not in extracted_data:

            continue

        value = extracted_data.get(
            field
        )

        # ----------------------------------------------------
        # No guardar vacíos
        # ----------------------------------------------------

        if value is None:

            continue

        if value == "":

            continue

        if value == []:

            continue

        if value == {}:

            continue

        result[
            field
        ] = value

    return sanitize_report_data(
        extracted_data=result,
        source_message=message,
        expected_fields=expected_question_fields(
            session
        ),
    )


# ============================================================
# NORMALIZAR LISTA
# ============================================================

def normalize_list(
    value,
) -> list:

    if not isinstance(
        value,
        list,
    ):

        return []

    result = []

    for item in value:

        if item is None:

            continue

        if isinstance(
            item,
            str,
        ):

            item = item.strip()

            if not item:

                continue

        if item not in result:

            result.append(
                item
            )

    return result


# ============================================================
# ANALIZAR MENSAJE DEL MAESTRO
# ============================================================

def analyze_message(
    message: str,
    session: dict,
) -> dict:

    message = str(
        message
        or ""
    ).strip()

    # ========================================================
    # CONTEXTO REDUCIDO
    # ========================================================

    ai_session = (
        build_ai_session_context(
            session
        )
    )

    session_json = json.dumps(
        ai_session,
        ensure_ascii=False,
        indent=2,
        default=str,
    )

    # ========================================================
    # DEBUG CONTEXTO
    # ========================================================

    print()
    print("=" * 70)
    print("🧠 CONTEXTO REDUCIDO ENVIADO A OPENAI")
    print("=" * 70)

    print(
        session_json
    )

    print()
    print(
        "Longitud contexto:",
        len(
            session_json
        ),
        "caracteres",
    )

    print(
        "Longitud mensaje:",
        len(
            message
        ),
        "caracteres",
    )

    print("=" * 70)

    prompt = f"""
Eres el motor de interpretación del Agente JCF.

NO respondes directamente al trabajador.

Python controla el flujo general.

Tu única responsabilidad es interpretar
el mensaje recibido y devolver JSON estructurado.


# ============================================================
# OBJETIVO
# ============================================================

El Agente JCF gestiona levantamientos técnicos
asociados a solicitudes de servicio existentes.

Los mensajes pueden provenir de:

- texto escrito,
- transcripciones de audio,
- información complementaria de imágenes.

Debes extraer solamente información útil.

No guardes frases de relleno,
repeticiones ni la transcripción completa.


# ============================================================
# SOLICITUD ACTUAL
# ============================================================

La sesión puede incluir:

quote_number
selected_service_id
oc
service_status

Estos identificadores pertenecen a Python.

NO deben aparecer dentro de extracted_data.

NO inventes una cotización.

NO cambies una cotización.

NO copies COTXXXXX dentro de:

cliente
recinto
sector
tipo_trabajo
descripcion


Si existe quote_number,
todo el levantamiento actual pertenece
a esa solicitud.


# ============================================================
# CAMBIO DE SOLICITUD
# ============================================================

Usa:

intent = "change_quote"

cuando el usuario quiera abandonar
la solicitud actual y seleccionar otra.

Ejemplos:

"esa no era"

"me equivoqué de cotización"

"quiero otra"

"cambiemos de solicitud"

"quiero seleccionar otra"

"esta no corresponde"

"volvamos atrás"

"quiero cambiar el servicio"


Cuando intent sea change_quote:

possible_new_job = false

extracted_data = {{}}

critical_missing = []

recommended_missing = []

optional_missing = []

next_question = ""

ask_for_observations = false

ready_for_report = false


change_quote tiene prioridad
sobre cualquier otra interpretación.


# ============================================================
# MODIFICACIÓN DEL INFORME
# ============================================================

Cuando el usuario corrige información existente,
usa:

intent = "modify_report"


Ejemplos:

"me equivoqué, son 4 personas"

extracted_data:

{{
    "personal_requerido": 4
}}


"cambia el tiempo a 3 días"

extracted_data:

{{
    "tiempo_estimado": "3 días"
}}


No confundas esto con change_quote.


# ============================================================
# TRABAJO NUEVO DENTRO DE LA MISMA SOLICITUD
# ============================================================

possible_new_job = true

solamente cuando ya existe un trabajo
y el usuario menciona claramente
otra intervención diferente.

Ejemplo:

Trabajo actual:

"Reparación de muro"

Usuario:

"también hay que cambiar una puerta"

Puede ser:

possible_new_job = true


NO marques possible_new_job cuando solamente:

- agrega herramientas,
- agrega materiales,
- agrega medidas,
- agrega personal,
- agrega duración,
- agrega prioridad,
- agrega empresa externa,
- agrega observaciones,
- corrige información.


# ============================================================
# TRABAJO PENDIENTE
# ============================================================

Si existe pending_new_job:

Respuesta:

"1"
"mismo trabajo"
"agrégalo"
"va junto"

→ intent = "continue_with_pending_job"


Respuesta:

"2"
"otro"
"uno nuevo"
"separado"

→ intent = "start_pending_new_job"


# ============================================================
# ÚLTIMA PREGUNTA
# ============================================================

La sesión puede contener:

last_question_field

Úsalo como contexto principal
para respuestas breves.


Ejemplos:


last_question_field = "tiempo_estimado"

Usuario:

"2 días"

→ tiempo_estimado = "2 días"


last_question_field = "personal_requerido"

Usuario:

"5"

→ personal_requerido = 5


last_question_field = "jornada"

Usuario:

"noche"

→ jornada = "Nocturna"


last_question_field = "prioridad"

Usuario:

"urgente"

→ prioridad = "Urgente"


last_question_field = "empresa_externa_requerida"

Usuario:

"no"

→ empresa_externa_requerida = false


last_question_field = "observaciones"

Usuario:

"no"

→ observaciones = [
    "Sin observaciones adicionales"
]


Pero change_quote siempre tiene prioridad.


# ============================================================
# CAMPOS DISPONIBLES
# ============================================================

Los únicos campos permitidos son:

cliente
recinto
sector
tipo_trabajo
descripcion
dimensiones
superficie_m2
materiales
cantidades
estado_actual
trabajos_requeridos
equipamiento_necesario
tiempo_estimado
jornada
personal_requerido
empresa_externa_requerida
empresa_externa_detalle
prioridad
observaciones


No existen:

cotizacion
service_id
quote_number
selected_service_id
record_id


# ============================================================
# EXTRACCIÓN TÉCNICA
# ============================================================

Debes interpretar lenguaje natural,
errores ortográficos y transcripciones imperfectas.


Ejemplo:

"la cortina metalica tiene oxido
y hay que cambiarla"

Puede producir:

{{
    "tipo_trabajo":
        "Reemplazo de cortina metálica",

    "estado_actual":
        "Cortina metálica con presencia de óxido",

    "trabajos_requeridos": [
        "Retiro de cortina metálica existente",
        "Reemplazo de cortina metálica"
    ]
}}


Ejemplo:

"mide seis metros por dos coma cuatro"

Puede producir:

{{
    "dimensiones": {{
        "largo_m": 6,
        "alto_m": 2.4
    }},

    "superficie_m2": 14.4
}}


No inventes medidas
si el usuario no las menciona.


# ============================================================
# DESCRIPCIÓN
# ============================================================

descripcion debe agregar información útil.

No la rellenes simplemente
para repetir tipo_trabajo.


# ============================================================
# ESTADO ACTUAL
# ============================================================

Ejemplo:

"la cortina tiene oxido"

→

estado_actual =
"Cortina metálica con presencia de óxido"


# ============================================================
# TRABAJOS REQUERIDOS
# ============================================================

Ejemplo:

"hay que sacar la existente
e instalar una nueva"

→

trabajos_requeridos = [
    "Retiro de elemento existente",
    "Instalación de elemento nuevo"
]


# ============================================================
# EQUIPAMIENTO NECESARIO
# ============================================================

Ejemplo:

"necesitamos escalera, zapatos y lentes"

→

equipamiento_necesario = [
    "Escalera",
    "Zapatos de seguridad",
    "Lentes de seguridad"
]


Si dice:

"ninguno"

→

equipamiento_necesario = [
    "No requiere equipamiento adicional"
]


# ============================================================
# TIEMPO
# ============================================================

"unas cinco horas"

→

tiempo_estimado = "5 horas"


"dos días"

→

tiempo_estimado = "2 días"


# ============================================================
# JORNADA
# ============================================================

"de día"

→

jornada = "Diurna"


"de noche"

→

jornada = "Nocturna"


"ambas"

→

jornada = "Mixta"


# ============================================================
# PERSONAL
# ============================================================

"se necesitan tres personas"

→

personal_requerido = 3


# ============================================================
# EMPRESA EXTERNA
# ============================================================

"no necesitamos empresa externa"

→

empresa_externa_requerida = false


"necesitamos una empresa externa
para retirar escombros"

→

empresa_externa_requerida = true

empresa_externa_detalle =
"Retiro de escombros"


"una empresa externa debe recoger
los suministros y llevarlos al sector"

→

empresa_externa_requerida = true

empresa_externa_detalle =
"Retiro y traslado de suministros al sector"


# ============================================================
# PRIORIDAD
# ============================================================

"emergencia"

→ prioridad = "Emergencia"


"urgente"

→ prioridad = "Urgente"


"alta"

→ prioridad = "Alta"


"media"

→ prioridad = "Media"


"baja"

→ prioridad = "Baja"


# ============================================================
# NO INVENTAR
# ============================================================

Nunca inventes:

- medidas,
- cantidades,
- materiales,
- colores,
- ubicaciones,
- herramientas,
- equipamiento,
- duración,
- personal,
- jornada,
- empresa externa,
- prioridad,
- cliente,
- recinto,
- sector.


# ============================================================
# INFORMACIÓN YA EXISTENTE
# ============================================================

Revisa siempre:

session["data"]

No preguntes nuevamente un dato
que ya exista.


# ============================================================
# DATOS OPERATIVOS
# ============================================================

Antes de cerrar normalmente deben quedar resueltos:

equipamiento_necesario
tiempo_estimado
jornada
personal_requerido
empresa_externa_requerida
empresa_externa_detalle si corresponde
prioridad


Python además posee validaciones propias.

Tú debes ayudar a identificar faltantes,
pero NO inventarlos.

Python es la autoridad final sobre la completitud.
Aunque estimes que existe información suficiente,
no intentes omitir preguntas pendientes de la sesión.

Respuestas vagas como "ok", "listo", "chao",
"hola", "no sé", "nose" o "ni idea" no completan
ningún antecedente técnico.

"No aplica" solo puede cerrar un campo técnico cuando
el usuario lo declara explícitamente para ese campo.


# ============================================================
# FALTANTES
# ============================================================

Clasifica en:

critical_missing
recommended_missing
optional_missing


critical_missing:

datos indispensables para que el levantamiento
sea técnicamente entendible.


recommended_missing:

datos útiles pero no absolutamente indispensables.


optional_missing:

datos secundarios.


NO agregues la cotización
como critical_missing.


# ============================================================
# SIGUIENTE PREGUNTA
# ============================================================

next_question debe ser una sola pregunta principal.

No preguntes varias cosas
en una sola respuesta.


Ejemplo correcto:

"¿Cuántas personas se necesitarán para realizar el trabajo?"


Ejemplo incorrecto:

"¿Cuántas personas serán y cuánto demorará?"


# ============================================================
# OBSERVACIONES
# ============================================================

Las observaciones van al final.

ask_for_observations = true

solo cuando:

- no queden faltantes críticos,
- exista información técnica suficiente,
- los datos operativos estén suficientemente resueltos,
- aún no existan observaciones.


Si:

last_question_field = "observaciones"

y usuario responde:

"no"
"ninguna"
"nada"
"sin observaciones"

→

observaciones = [
    "Sin observaciones adicionales"
]

ask_for_observations = false

ready_for_report = true


# ============================================================
# LISTO PARA INFORME
# ============================================================

ready_for_report = true

solamente cuando exista información suficiente
para crear un informe útil.


No marques ready_for_report = true
si faltan datos esenciales.


# ============================================================
# FINALIZAR
# ============================================================

Frases como:

"terminé"
"eso es todo"
"listo"
"ya está"
"finalicé"
"no tengo nada más"

→ intent = "complete_report"


Finalizar NO significa guardar.

Python controla el guardado.


# ============================================================
# INTENCIONES PERMITIDAS
# ============================================================

Solo puedes devolver:

start_report
continue_report
modify_report
pause_report
resume_report
complete_report
confirm_report
cancel_report
general_question
continue_with_pending_job
start_pending_new_job
change_quote


# ============================================================
# PRIORIDAD DE INTENCIONES
# ============================================================

1. change_quote
2. cancel_report
3. pause_report
4. resume_report
5. continue_with_pending_job
6. start_pending_new_job
7. modify_report
8. complete_report
9. start_report
10. continue_report
11. general_question


# ============================================================
# EJEMPLO IMPORTANTE DE AUDIO
# ============================================================

Mensaje:

"Bueno, dentro de este terreno encontramos
que se realizó una inspección.
La cortina metálica tiene óxido,
se requiere cambiar con emergencia.
Se necesitan herramientas como escalera,
zapatos y lentes.
Además se necesitará una empresa externa
que recoja los suministros
y los lleve hacia el sector."


Resultado aproximado:

{{
    "intent": "continue_report",

    "possible_new_job": false,

    "extracted_data": {{

        "tipo_trabajo":
            "Reemplazo de cortina metálica",

        "estado_actual":
            "Cortina metálica con presencia de óxido",

        "trabajos_requeridos": [
            "Reemplazo de cortina metálica"
        ],

        "equipamiento_necesario": [
            "Escalera",
            "Zapatos de seguridad",
            "Lentes de seguridad"
        ],

        "empresa_externa_requerida": true,

        "empresa_externa_detalle":
            "Retiro y traslado de suministros al sector",

        "prioridad":
            "Emergencia"
    }},

    "critical_missing": [],

    "recommended_missing": [],

    "optional_missing": [],

    "next_question":
        "¿Cuánto tiempo estimas que tomará realizar el trabajo?",

    "ask_for_observations": false,

    "ready_for_report": false
}}


# ============================================================
# SESIÓN ACTUAL REDUCIDA
# ============================================================

{session_json}


# ============================================================
# MENSAJE DEL MAESTRO
# ============================================================

{message}


Devuelve SOLAMENTE JSON válido:

{{
    "intent": "continue_report",

    "possible_new_job": false,

    "extracted_data": {{

        "cliente": null,

        "recinto": null,

        "sector": null,

        "tipo_trabajo": null,

        "descripcion": null,

        "dimensiones": {{}},

        "superficie_m2": null,

        "materiales": [],

        "cantidades": [],

        "estado_actual": null,

        "trabajos_requeridos": [],

        "equipamiento_necesario": [],

        "tiempo_estimado": null,

        "jornada": null,

        "personal_requerido": null,

        "empresa_externa_requerida": null,

        "empresa_externa_detalle": null,

        "prioridad": null,

        "observaciones": []
    }},

    "critical_missing": [],

    "recommended_missing": [],

    "optional_missing": [],

    "next_question": "",

    "ask_for_observations": false,

    "ready_for_report": false
}}
"""

    # ========================================================
    # CONSULTAR OPENAI
    # ========================================================

    try:

        response = client.responses.create(
            model=OPENAI_MODEL,
            input=prompt,
            store=False,
        )

    except Exception as error:

        error_name = (
            type(
                error
            ).__name__
        )

        error_text = str(
            error
        )

        print()
        print("=" * 70)
        print("❌ ERROR CONSULTANDO OPENAI")
        print("=" * 70)

        print(
            error_name,
            error_text,
        )

        print("=" * 70)

        # ====================================================
        # IDENTIFICAR CONTEXT WINDOW
        # ====================================================

        if (
            "context_length_exceeded"
            in error_text
            or "context window"
            in error_text.lower()
            or "input exceeds"
            in error_text.lower()
        ):

            return get_default_result(
                message=message,
                error_code=(
                    "context_length_exceeded"
                ),
            )

        return get_default_result(
            message=message,
            error_code=(
                "openai_request_error"
            ),
        )

    raw = (
        response
        .output_text
        .strip()
    )

    print()
    print("=" * 70)
    print("📦 RESPUESTA CRUDA OPENAI")
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

    except json.JSONDecodeError:

        print()
        print("=" * 70)
        print("❌ OPENAI DEVOLVIÓ JSON INVÁLIDO")
        print("=" * 70)

        print(
            raw
        )

        print("=" * 70)

        return get_default_result(
            message=message,
            error_code=(
                "invalid_json"
            ),
        )

    # ========================================================
    # VALIDAR DICT
    # ========================================================

    if not isinstance(
        result,
        dict,
    ):

        return get_default_result(
            message=message,
            error_code=(
                "invalid_response_type"
            ),
        )

    # ========================================================
    # DEFAULTS
    # ========================================================

    result.setdefault(
        "intent",
        "continue_report",
    )

    result.setdefault(
        "possible_new_job",
        False,
    )

    result.setdefault(
        "extracted_data",
        {},
    )

    result.setdefault(
        "critical_missing",
        [],
    )

    result.setdefault(
        "recommended_missing",
        [],
    )

    result.setdefault(
        "optional_missing",
        [],
    )

    result.setdefault(
        "next_question",
        "",
    )

    result.setdefault(
        "ask_for_observations",
        False,
    )

    result.setdefault(
        "ready_for_report",
        False,
    )

    # ========================================================
    # MARCAR RESPUESTA CORRECTA
    # ========================================================

    result[
        "processing_error"
    ] = False

    result[
        "error_code"
    ] = None

    # ========================================================
    # SANITIZAR EXTRACTED DATA
    # ========================================================

    result[
        "extracted_data"
    ] = sanitize_extracted_data(
        extracted_data=result.get(
            "extracted_data"
        ),
        message=message,
        session=session,
    )

    # ========================================================
    # NORMALIZAR LISTAS
    # ========================================================

    result[
        "critical_missing"
    ] = normalize_list(
        result.get(
            "critical_missing"
        )
    )

    result[
        "recommended_missing"
    ] = normalize_list(
        result.get(
            "recommended_missing"
        )
    )

    result[
        "optional_missing"
    ] = normalize_list(
        result.get(
            "optional_missing"
        )
    )

    # ========================================================
    # BOOLEANOS
    # ========================================================

    result[
        "possible_new_job"
    ] = bool(
        result.get(
            "possible_new_job"
        )
    )

    result[
        "ask_for_observations"
    ] = bool(
        result.get(
            "ask_for_observations"
        )
    )

    result[
        "ready_for_report"
    ] = bool(
        result.get(
            "ready_for_report"
        )
    )

    # ========================================================
    # NEXT QUESTION
    # ========================================================

    if not isinstance(
        result.get(
            "next_question"
        ),
        str,
    ):

        result[
            "next_question"
        ] = ""

    else:

        result[
            "next_question"
        ] = result[
            "next_question"
        ].strip()

    # ========================================================
    # VALIDAR INTENCIÓN
    # ========================================================

    intent = result.get(
        "intent"
    )

    if intent not in ALLOWED_INTENTS:

        print()
        print("=" * 70)
        print("⚠️ INTENCIÓN DESCONOCIDA")
        print("=" * 70)

        print(
            "Recibida:",
            intent
        )

        print("=" * 70)

        result[
            "intent"
        ] = "continue_report"

    # ========================================================
    # PROTECCIÓN CHANGE_QUOTE
    # ========================================================

    if (
        result.get(
            "intent"
        )
        == "change_quote"
    ):

        result[
            "possible_new_job"
        ] = False

        result[
            "extracted_data"
        ] = {}

        result[
            "critical_missing"
        ] = []

        result[
            "recommended_missing"
        ] = []

        result[
            "optional_missing"
        ] = []

        result[
            "next_question"
        ] = ""

        result[
            "ask_for_observations"
        ] = False

        result[
            "ready_for_report"
        ] = False

        print()
        print("=" * 70)
        print("🔄 CAMBIO DE COTIZACIÓN DETECTADO")
        print("=" * 70)

        print(
            "Mensaje:",
            message
        )

        print(
            "Solicitud actual:",
            (
                session.get(
                    "selected_service_id"
                )
                or session.get(
                    "quote_number"
                )
            )
        )

        print("=" * 70)

    # ========================================================
    # PROTECCIÓN EMPRESA EXTERNA
    #
    # Si explícitamente dijo que NO requiere,
    # no puede quedar detalle antiguo inventado
    # desde este mensaje.
    # ========================================================

    extracted_data = result.get(
        "extracted_data",
        {},
    )

    if (
        extracted_data.get(
            "empresa_externa_requerida"
        )
        is False
    ):

        extracted_data.pop(
            "empresa_externa_detalle",
            None,
        )

    # ========================================================
    # DEBUG FINAL
    # ========================================================

    print()
    print("=" * 70)
    print("🧠 RESULTADO FINAL IA")
    print("=" * 70)

    print(
        "Intent:",
        result.get(
            "intent"
        )
    )

    print(
        "Possible new job:",
        result.get(
            "possible_new_job"
        )
    )

    print(
        "Extracted data:",
        result.get(
            "extracted_data"
        )
    )

    print(
        "Critical missing:",
        result.get(
            "critical_missing"
        )
    )

    print(
        "Recommended missing:",
        result.get(
            "recommended_missing"
        )
    )

    print(
        "Optional missing:",
        result.get(
            "optional_missing"
        )
    )

    print(
        "Next question:",
        result.get(
            "next_question"
        )
    )

    print(
        "Ask observations:",
        result.get(
            "ask_for_observations"
        )
    )

    print(
        "Ready:",
        result.get(
            "ready_for_report"
        )
    )

    print(
        "Processing error:",
        result.get(
            "processing_error"
        )
    )

    print("=" * 70)

    return result
