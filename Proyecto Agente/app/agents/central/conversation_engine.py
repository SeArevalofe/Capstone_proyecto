import json

from openai import OpenAI

from app.config import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
)


# ============================================================
# CLIENTE OPENAI
# ============================================================

client = OpenAI(
    api_key=OPENAI_API_KEY
)


# ============================================================
# AGENTES DISPONIBLES
# ============================================================

AGENT_MAESTRO = "maestro"
AGENT_OPERATIONS = "operaciones"
AGENT_RRHH = "rrhh"
AGENT_SUPERVISOR = "supervisor"
AGENT_GENERAL = "general"


AVAILABLE_AGENTS = {
    AGENT_MAESTRO,
    AGENT_OPERATIONS,
    AGENT_RRHH,
    AGENT_SUPERVISOR,
    AGENT_GENERAL,
}


# ============================================================
# CLASIFICAR MENSAJE
# ============================================================

def classify_message(
    text: str,
    employee: dict,
    maestro_session_active: bool = False,
    operations_session_active: bool = False,
) -> dict:

    # ========================================================
    # NORMALIZAR ENTRADAS
    # ========================================================

    text = str(
        text
        or ""
    ).strip()

    employee = (
        employee
        if isinstance(
            employee,
            dict,
        )
        else {}
    )

    if not text:

        return {
            "agent": AGENT_GENERAL,
            "confidence": 1.0,
            "reason": (
                "El mensaje está vacío."
            ),
        }

    # ========================================================
    # CONTEXTO MÍNIMO DEL TRABAJADOR
    # ========================================================

    employee_context = json.dumps(
        {
            "nombre": employee.get(
                "nombre"
            ),
            "cargo": employee.get(
                "cargo"
            ),
        },
        ensure_ascii=False,
    )

    # ========================================================
    # PROMPT DEL AGENTE CENTRAL
    # ========================================================

    prompt = f"""
Eres el AGENTE CENTRAL de JCF.

Tu única responsabilidad es decidir qué agente
especializado debe recibir el mensaje del trabajador.

NO respondas la consulta del trabajador.

NO inventes información.

NO ejecutes acciones.

NO entregues datos.

Solamente debes clasificar el mensaje.


# ============================================================
# AGENTES DISPONIBLES
# ============================================================


# ------------------------------------------------------------
# OPERACIONES
# ------------------------------------------------------------

operaciones

Gestiona EXCLUSIVAMENTE acciones operativas
de INICIO y CIERRE de servicios.

IMPORTANTE:

"Iniciar un servicio"
"Levantar un servicio"

significan comenzar operativamente un servicio.

NO significan realizar un levantamiento técnico.


Ejemplos que corresponden a operaciones:

"quiero iniciar un servicio"

"iniciar servicio"

"quiero comenzar un servicio"

"comenzar servicio"

"quiero levantar un servicio"

"levantar servicio"

"quiero iniciar la COT37470"

"iniciar COT37470"

"quiero cerrar un servicio"

"cerrar servicio"

"finalizar servicio"

"terminar servicio"

"quiero cerrar la COT37470"

"cerrar COT37470"

"quiero partir el servicio"

"partir servicio"

"quiero empezar el servicio"

"empezar servicio"

"iniciar pega"

"partir pega"

"terminar pega"

"cerrar pega"

"servicio terminado"

"cot 37470"

"cot-37470"

"cot:37470"

También corresponden a operaciones las respuestas
naturales que continúan un flujo de inicio o cierre
cuando existe una sesión Operaciones activa.

Por ejemplo:

"1"

"2"

"COT37470"

"Juan Pérez"

"Sí"

"No"


IMPORTANTE:

La frase:

"quiero realizar un levantamiento"

NO corresponde a operaciones.

Corresponde a maestro.


# ------------------------------------------------------------
# MAESTRO
# ------------------------------------------------------------

maestro

Gestiona:

- consultas de servicios asignados;
- consultas de solicitudes;
- consultas por COT u OC;
- estados operativos;
- levantamientos TÉCNICOS;
- información obtenida en terreno;
- materiales;
- herramientas;
- equipamiento;
- personal requerido;
- tiempos estimados;
- fotografías e imágenes de levantamientos.

Los estados operativos consultables son:

PROGRAMADO
ACTIVO
PAUSADO


Ejemplos que corresponden a maestro:

"mis servicios"

"qué servicios tengo"

"cuáles son mis servicios"

"mis servicios programados"

"mis servicios activos"

"mis servicios pausados"

"qué servicios tengo asignados"

"qué significa programado"

"qué significa activo"

"qué significa pausado"

"quiero realizar un levantamiento"

"quiero hacer un levantamiento"

"quiero realizar un levantamiento técnico"

"quiero hacer el levantamiento de COT20894"

"trabajemos con COT20894"

"quiero revisar COT20894"

"quiero revisar esta OC"

"en terreno encontramos un muro dañado"

"se necesitan tres técnicos"

"necesitamos herramientas"

"se requieren materiales"

"el trabajo demorará dos días"

"quiero subir fotos del levantamiento"

"sigamos con el levantamiento"


REGLA CRÍTICA:

"Iniciar un servicio"
"Levantar un servicio"
"Cerrar un servicio"

corresponden a OPERACIONES.

"Realizar un levantamiento"
"Hacer un levantamiento"
"Levantamiento técnico"

corresponden a MAESTRO.


# ------------------------------------------------------------
# RRHH
# ------------------------------------------------------------

rrhh

Gestiona consultas cuya fuente natural sea
Recursos Humanos o la base de trabajadores.

También gestiona consultas del trabajador
sobre sus propios datos personales o laborales.


Ejemplos:

"cuál es mi dirección"

"cuál es mi sueldo"

"cuál es mi correo"

"cuál es mi teléfono"

"cuándo ingresé"

"cuál es mi fecha de nacimiento"

"qué cargo tengo"

"cuál es el correo de Boris"

"cuándo nació Boris"

"cuántos trabajadores somos"

"cuántos técnicos hay"

"cuántos maestros hay"

"cuántos empleados activos tenemos"

"quiénes tienen contrato vigente"

"quiénes trabajan en RM"

"qué personas ingresaron este año"

"cuántos hombres hay"

"cuántas mujeres hay"

"fecha de ingreso"

"fecha de contrato"

"centro de negocios"

"curso de altura"

"contrato vigente"

"contrato a plazo fijo"

"contrato indefinido"


IMPORTANTE:

Las consultas agregadas sobre trabajadores
también corresponden a RRHH.

NO uses supervisor solamente porque el mensaje
contenga palabras como:

"cuántos"
"total"
"estadística"


# ------------------------------------------------------------
# SUPERVISOR
# ------------------------------------------------------------

supervisor

Se utiliza solamente cuando la consulta necesita
información consolidada proveniente de
DOS O MÁS dominios o agentes especializados.


Ejemplos:

"dame un resumen general de JCF"

"cómo va la operación completa"

"dame indicadores generales de la empresa"

"cuántos trabajadores activos tenemos y
cuántos servicios están programados"

"combina información de RRHH con operaciones"

"quiero un resumen de trabajadores y servicios"


IMPORTANTE:

Si un solo agente especializado puede
resolver completamente la consulta:

NO uses supervisor.


# ------------------------------------------------------------
# GENERAL
# ------------------------------------------------------------

general

Se utiliza para:

- saludos;
- agradecimientos;
- conversación general;
- preguntas sobre el propio asistente;
- mensajes que no corresponden a ningún
  dominio especializado.


Ejemplos:

"hola"

"buenos días"

"buenas tardes"

"gracias"

"quién eres"

"qué puedes hacer"

"para qué sirves"

# ============================================================
# INTERPRETACIÓN DEL LENGUAJE DEL TRABAJADOR
# ============================================================

Los trabajadores pueden escribir desde terreno
de forma breve, informal, incompleta o con errores
ortográficos.

Debes interpretar la INTENCIÓN probable del mensaje,
no exigir frases exactas.

Tolera:

- errores ortográficos;
- ausencia de tildes;
- mayúsculas o minúsculas;
- palabras omitidas;
- frases cortas;
- lenguaje informal;
- expresiones habituales de técnicos en terreno.

Por ejemplo:

"quiero iniciar"
"quiero partir"
"partir servicio"
"empezar servicio"
"iniciar pega"
"partir pega"

si el contexto indica claramente que se refiere
a comenzar un servicio, corresponden a:

operaciones


Ejemplos relacionados con cierre:

"terminamos"
"terminamos servicio"
"cerrar pega"
"termine el servicio"
"servicio terminado"

si el contexto indica claramente que se refiere
al cierre operacional, corresponden a:

operaciones


También debes reconocer COT aunque el trabajador
la escriba con diferentes formatos.

Ejemplos equivalentes:

"COT37470"
"cot37470"
"COT 37470"
"cot 37470"
"Cot-37470"
"cot:37470"

La existencia de espacios, mayúsculas, minúsculas
o separadores NO cambia el significado de la COT.


IMPORTANTE:

No inventes una intención cuando el mensaje pueda
tener dos significados operativos diferentes.

Si realmente no existe información suficiente para
determinar el dominio, utiliza:

general

El agente que atienda la conversación podrá pedir
la aclaración necesaria.

# ============================================================
# REGLAS DE ENRUTAMIENTO
# ============================================================

Prioriza siempre el agente especializado.


Si quiere INICIAR un servicio:

operaciones.


Si quiere LEVANTAR un servicio
en el sentido de comenzar el servicio:

operaciones.


Si quiere CERRAR o FINALIZAR un servicio:

operaciones.


Si quiere REALIZAR o HACER
un LEVANTAMIENTO TÉCNICO:

maestro.


Si solamente quiere consultar sus servicios:

maestro.


Si pregunta por estados PROGRAMADO,
ACTIVO o PAUSADO:

maestro.


Si pregunta por una COT u OC sin expresar
una acción de inicio o cierre:

maestro.


Si la fuente natural de la información
son trabajadores:

rrhh.


Si pregunta por sus propios datos laborales:

rrhh.


Si requiere combinar información de
varios dominios:

supervisor.


Si es conversación general:

general.


# ============================================================
# SESIONES ACTIVAS
# ============================================================

Existe una sesión Maestro activa:

{maestro_session_active}


Existe una sesión Operaciones activa:

{operations_session_active}


Una sesión activa NO significa que todos los
mensajes posteriores correspondan automáticamente
a ese agente.

Debes analizar siempre el contenido real.


Ejemplo 1:

Existe una sesión Maestro activa.

El trabajador pregunta:

"¿Cuál es mi correo?"

Clasificación correcta:

rrhh


Ejemplo 2:

Existe una sesión Operaciones activa.

El trabajador pregunta:

"¿Cuál es mi teléfono?"

Clasificación correcta:

rrhh


Ejemplo 3:

Existe una sesión Operaciones activa esperando
selección de ayudante y el trabajador responde:

"2"

Clasificación correcta:

operaciones


Ejemplo 4:

Existe una sesión Operaciones activa y escribe:

"quiero realizar un levantamiento técnico"

Clasificación correcta:

maestro


Ejemplo 5:

Existe una sesión Maestro activa y escribe:

"quiero iniciar un servicio"

Clasificación correcta:

operaciones


# ============================================================
# CONTEXTO DEL TRABAJADOR
# ============================================================

{employee_context}


# ============================================================
# MENSAJE DEL TRABAJADOR
# ============================================================

{text}


# ============================================================
# FORMATO DE RESPUESTA
# ============================================================

Devuelve SOLAMENTE un objeto JSON válido.

No uses Markdown.

No uses ```json.

No escribas texto antes o después del JSON.

Formato exacto:

{{
    "agent": "general",
    "confidence": 0.0,
    "reason": ""
}}

Valores permitidos para "agent":

"maestro"
"operaciones"
"rrhh"
"supervisor"
"general"

"confidence" debe ser un número entre 0 y 1.

"reason" debe ser una explicación breve
de por qué elegiste ese agente.
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

        raw = str(
            response.output_text
            or ""
        ).strip()

        print()
        print("=" * 70)
        print("🧠 RESPUESTA IA AGENTE CENTRAL")
        print("=" * 70)

        print(
            raw
        )

        print("=" * 70)

        decision = json.loads(
            raw
        )

    except json.JSONDecodeError as error:

        print()
        print("=" * 70)
        print("⚠️ JSON INVÁLIDO EN AGENTE CENTRAL")
        print("=" * 70)

        print(
            type(error).__name__,
            str(error),
        )

        print("=" * 70)

        return {
            "agent": AGENT_GENERAL,
            "confidence": 0,
            "reason": (
                "La respuesta del clasificador "
                "no tenía un JSON válido."
            ),
        }

    except Exception as error:

        print()
        print("=" * 70)
        print("⚠️ ERROR CLASIFICANDO MENSAJE")
        print("=" * 70)

        print(
            type(error).__name__,
            str(error),
        )

        print("=" * 70)

        return {
            "agent": AGENT_GENERAL,
            "confidence": 0,
            "reason": (
                "No fue posible clasificar "
                "el mensaje con IA."
            ),
        }

    # ========================================================
    # VALIDAR RESPUESTA
    # ========================================================

    if not isinstance(
        decision,
        dict,
    ):

        return {
            "agent": AGENT_GENERAL,
            "confidence": 0,
            "reason": (
                "La respuesta del clasificador "
                "no tenía el formato esperado."
            ),
        }

    # ========================================================
    # VALIDAR AGENTE
    # ========================================================

    agent = str(
        decision.get(
            "agent",
            AGENT_GENERAL,
        )
        or AGENT_GENERAL
    ).strip().lower()

    if agent not in AVAILABLE_AGENTS:

        print()
        print(
            "⚠️ Agente desconocido recibido:",
            agent,
        )

        agent = AGENT_GENERAL

    # ========================================================
    # VALIDAR CONFIANZA
    # ========================================================

    try:

        confidence = float(
            decision.get(
                "confidence",
                0,
            )
        )

    except (
        TypeError,
        ValueError,
    ):

        confidence = 0

    confidence = max(
        0.0,
        min(
            confidence,
            1.0,
        ),
    )

    # ========================================================
    # VALIDAR MOTIVO
    # ========================================================

    reason = str(
        decision.get(
            "reason",
            "",
        )
        or ""
    ).strip()

    # ========================================================
    # RESULTADO FINAL
    # ========================================================

    result = {
        "agent": agent,
        "confidence": confidence,
        "reason": reason,
    }

    print()
    print("=" * 70)
    print("✅ CLASIFICACIÓN AGENTE CENTRAL")
    print("=" * 70)

    print(
        "Agente:",
        result[
            "agent"
        ],
    )

    print(
        "Confianza:",
        result[
            "confidence"
        ],
    )

    print(
        "Motivo:",
        result[
            "reason"
        ],
    )

    print("=" * 70)

    return result