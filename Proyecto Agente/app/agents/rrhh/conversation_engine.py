import json

from openai import OpenAI

from app.config import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
)

from app.agents.rrhh.schemas import (
    sanitize_rrhh_analysis,
)


client = OpenAI(
    api_key=OPENAI_API_KEY
)


# ============================================================
# INTERPRETAR CONSULTA RRHH
# ============================================================

def analyze_rrhh_message(
    message: str,
    employee: dict = None,
) -> dict:

    employee = (
        employee
        if isinstance(
            employee,
            dict,
        )
        else {}
    )

    authenticated_name = (
        employee.get(
            "nombre"
        )
        or ""
    )

    authenticated_position = (
        employee.get(
            "cargo"
        )
        or ""
    )

    prompt = f"""
Eres el motor de interpretación del Agente RRHH de JCF.

NO respondes directamente al usuario.

Tu única función es convertir una consulta natural
en una acción estructurada.

Python realizará las consultas y aplicará todos
los permisos de seguridad.

La fuente real de información es Airtable.


# ============================================================
# USUARIO AUTENTICADO
# ============================================================

Nombre:
{authenticated_name}

Cargo:
{authenticated_position}


# ============================================================
# REGLA MUY IMPORTANTE: "YO", "MI", "MIS"
# ============================================================

Cuando el usuario pregunte por sí mismo:

"mi dirección"
"cuál es mi correo"
"qué teléfono tengo registrado"
"cuándo nací"
"qué cargo tengo"
"cuándo ingresé"
"mi contrato"
"mis datos"
"cuál es mi fecha de nacimiento"

debes interpretar que la persona consultada es:

"{authenticated_name}"

Por lo tanto debes devolver:

action = "get_employee"

employee_name = "{authenticated_name}"

NO solicites nuevamente el nombre.

NO preguntes quién es.

El sistema ya conoce la identidad del usuario.


# ============================================================
# ACCIONES DISPONIBLES
# ============================================================

Puedes utilizar solamente:

get_employee

Para consultar datos de una persona concreta.

Ejemplos:

"cuál es mi correo"

"cuál es el teléfono de Pedro"

"cuándo nací"

"qué cargo tiene Juan"


search_employees

Cuando se buscan trabajadores que cumplen condiciones.

Ejemplos:

"quiénes son técnicos"

"qué trabajadores están en la región metropolitana"


count_employees

Cuando se solicita una cantidad.

Ejemplos:

"cuántos trabajadores somos"

"cuántos técnicos hay"

"cuántos trabajadores activos tenemos"


list_employees

Cuando se solicita una lista general.

Ejemplos:

"muéstrame los trabajadores"

"quiénes trabajan en JCF"


general_rrhh_question

Solamente para preguntas conceptuales que no requieran
consultar trabajadores en Airtable.


# ============================================================
# CAMPOS DISPONIBLES
# ============================================================

nombre
email
cargo
contrato_vigente
region
cedula
genero
folio_trabajador
fecha_ingreso
fecha_renovacion_contrato
fecha_nacimiento
fecha_curso_altura
telefono
direccion
centro_negocios
fecha_termino_contrato
indefinido
plazo_fijo


# ============================================================
# FILTROS DISPONIBLES
# ============================================================

nombre
email
cargo
contrato_vigente
region
genero
centro_negocios
fecha_ingreso
fecha_nacimiento
indefinido
plazo_fijo


# ============================================================
# EJEMPLOS SOBRE EL PROPIO USUARIO
# ============================================================

Usuario:

"cuál es mi dirección"

Resultado:

{{
    "action": "get_employee",
    "employee_name": "{authenticated_name}",
    "requested_fields": [
        "direccion"
    ],
    "filters": {{}},
    "summary": "Consultar dirección del usuario autenticado"
}}


Usuario:

"cuando nací"

Resultado:

{{
    "action": "get_employee",
    "employee_name": "{authenticated_name}",
    "requested_fields": [
        "fecha_nacimiento"
    ],
    "filters": {{}},
    "summary": "Consultar fecha de nacimiento del usuario autenticado"
}}


Usuario:

"dime mis datos"

Resultado:

{{
    "action": "get_employee",
    "employee_name": "{authenticated_name}",
    "requested_fields": [
        "nombre",
        "cargo",
        "email",
        "telefono",
        "region",
        "centro_negocios",
        "fecha_ingreso",
        "contrato_vigente"
    ],
    "filters": {{}},
    "summary": "Consultar datos del usuario autenticado"
}}


# ============================================================
# EJEMPLOS DE TERCEROS
# ============================================================

Usuario:

"cuándo nació Boris Marrero"

Resultado:

{{
    "action": "get_employee",
    "employee_name": "Boris Marrero",
    "requested_fields": [
        "fecha_nacimiento"
    ],
    "filters": {{}},
    "summary": "Consultar fecha de nacimiento de Boris Marrero"
}}


Usuario:

"cuál es la dirección de Pedro Pérez"

Resultado:

{{
    "action": "get_employee",
    "employee_name": "Pedro Pérez",
    "requested_fields": [
        "direccion"
    ],
    "filters": {{}},
    "summary": "Consultar dirección de Pedro Pérez"
}}


# ============================================================
# EJEMPLOS DE CONTEO
# ============================================================

Usuario:

"cuántos trabajadores somos"

Resultado:

{{
    "action": "count_employees",
    "employee_name": null,
    "requested_fields": [],
    "filters": {{}},
    "summary": "Contar trabajadores"
}}


Usuario:

"cuántos técnicos hay"

Resultado:

{{
    "action": "count_employees",
    "employee_name": null,
    "requested_fields": [],
    "filters": {{
        "cargo": "Tecnico"
    }},
    "summary": "Contar técnicos"
}}


# ============================================================
# REGLAS
# ============================================================

Nunca inventes datos.

Nunca inventes trabajadores.

Nunca inventes resultados de Airtable.

No respondas directamente.

No decidas permisos.

Python decide los permisos.

No generes SQL.

No generes fórmulas Airtable.

No agregues campos inexistentes.

Si habla en primera persona:
employee_name debe ser exactamente
"{authenticated_name}".

Si pregunta una cantidad:
count_employees.

Si pregunta información sobre una persona:
get_employee.

Si pregunta quiénes cumplen una condición:
search_employees.

Si solicita todos los trabajadores:
list_employees.


# ============================================================
# CONSULTA DEL USUARIO
# ============================================================

{message}


Devuelve SOLAMENTE JSON válido:

{{
    "action": "general_rrhh_question",
    "employee_name": null,
    "requested_fields": [],
    "filters": {{}},
    "summary": ""
}}
"""

    response = client.responses.create(
        model=OPENAI_MODEL,
        input=prompt,
        store=False,
    )

    raw = (
        response
        .output_text
        .strip()
    )

    print()
    print("=" * 70)
    print("🧠 INTERPRETACIÓN RRHH")
    print("=" * 70)

    print(
        "Consulta:",
        message
    )

    print(
        "Respuesta IA:",
        raw
    )

    print("=" * 70)

    try:

        analysis = json.loads(
            raw
        )

    except json.JSONDecodeError:

        print(
            "❌ JSON inválido generado por IA RRHH"
        )

        return {
            "action": "general_rrhh_question",
            "employee_name": None,
            "requested_fields": [],
            "filters": {},
            "summary": "",
        }

    return sanitize_rrhh_analysis(
        analysis
    )