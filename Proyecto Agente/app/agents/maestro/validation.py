import re
import unicodedata


# Orden estable para que las preguntas siempre aparezcan de forma
# predecible y el usuario pueda responderlas juntas o parcialmente.
REQUIRED_FIELD_LABELS = (
    ("sector", "sector"),
    ("tipo_trabajo", "tipo de trabajo"),
    ("descripcion", "descripcion"),
    ("dimensiones", "dimensiones"),
    ("estado_actual", "estado actual"),
    ("materiales", "materiales"),
    ("trabajos_requeridos", "trabajos requeridos"),
    ("equipamiento_necesario", "equipamiento necesario"),
    ("tiempo_estimado", "tiempo estimado"),
    ("jornada", "jornada"),
    ("personal_requerido", "personal requerido"),
    ("empresa_externa_requerida", "empresa externa"),
    ("prioridad", "prioridad"),
)

CONDITIONAL_EXTERNAL_DETAIL_LABEL = (
    "servicio requerido de la empresa externa"
)

LIST_FIELDS = {
    "materiales",
    "cantidades",
    "trabajos_requeridos",
    "equipamiento_necesario",
    "observaciones",
}

EXPLICIT_NOT_APPLICABLE_FIELDS = {
    "dimensiones",
    "estado_actual",
    "materiales",
    "equipamiento_necesario",
}

VAGUE_RESPONSES = {
    "no se",
    "nose",
    "ni idea",
    "no tengo idea",
    "no sabria",
    "ok",
    "okay",
    "chao",
    "hola",
    "listo",
    "dale",
    "bueno",
    "si",
    "no",
    "ya",
    "perfecto",
    "gracias",
}

NOT_APPLICABLE_RESPONSES = {
    "no aplica",
    "no corresponde",
    "no es aplicable",
}

FIELD_ASSOCIATION_TERMS = {
    "dimensiones": (
        "dimension",
        "dimensiones",
        "medida",
        "medidas",
    ),
    "estado_actual": (
        "estado actual",
        "condicion actual",
    ),
    "materiales": (
        "material",
        "materiales",
    ),
    "equipamiento_necesario": (
        "equipo",
        "equipamiento",
        "herramienta",
        "herramientas",
    ),
}

NO_ADDITIONAL_ITEMS_RESPONSES = {
    "ninguno",
    "ninguna",
    "no requiere",
    "no se requiere",
    "sin materiales",
    "sin equipamiento",
}


def normalize_validation_text(
    value,
) -> str:

    text = str(
        value
        or ""
    ).strip().lower()

    text = "".join(
        character
        for character in unicodedata.normalize(
            "NFD",
            text,
        )
        if unicodedata.category(
            character
        ) != "Mn"
    )

    text = re.sub(
        r"[^\w\s]",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def is_vague_response(
    value,
) -> bool:

    raw = str(
        value
        or ""
    ).strip()

    normalized = normalize_validation_text(
        raw
    )

    if not raw:

        return True

    if not normalized:

        # Emojis, puntuación u otros símbolos sin contenido.
        return True

    return normalized in VAGUE_RESPONSES


def parse_natural_boolean(
    value,
):

    normalized = normalize_validation_text(
        value
    )

    if not normalized:

        return None

    false_values = {
        "no",
        "no se requiere",
        "no requiere",
        "no hace falta",
        "no necesitamos",
        "no necesitamos empresa externa",
        "sin empresa externa",
    }

    true_values = {
        "si",
        "si se requiere",
        "se requiere",
        "necesitamos empresa externa",
        "necesitamos una empresa externa",
        "requiere empresa externa",
    }

    if normalized in false_values:

        return False

    if normalized in true_values:

        return True

    if (
        "empresa externa" in normalized
        and any(
            phrase in normalized
            for phrase in (
                "no se requiere",
                "no requiere",
                "no hace falta",
                "no necesitamos",
                "sin empresa",
            )
        )
    ):

        return False

    if (
        "empresa externa" in normalized
        and any(
            phrase in normalized
            for phrase in (
                "si se requiere",
                "se requiere",
                "necesitamos",
                "requiere una",
            )
        )
    ):

        return True

    return None


def is_explicit_not_applicable(
    value,
) -> bool:

    return normalize_validation_text(
        value
    ) in NOT_APPLICABLE_RESPONSES


def is_contextual_not_applicable(
    message: str,
    field: str,
    expected_fields: list,
) -> bool:

    normalized = normalize_validation_text(
        message
    )

    if not any(
        phrase in normalized
        for phrase in NOT_APPLICABLE_RESPONSES
    ):

        return False

    if expected_fields == [
        field
    ]:

        return True

    return any(
        term in normalized
        for term in FIELD_ASSOCIATION_TERMS.get(
            field,
            (),
        )
    )


def _is_meaningful_scalar(
    value,
    allow_not_applicable: bool = False,
) -> bool:

    if isinstance(
        value,
        bool,
    ):

        return False

    if isinstance(
        value,
        (
            int,
            float,
        ),
    ):

        return value > 0

    normalized = normalize_validation_text(
        value
    )

    if not normalized:

        return False

    if normalized in VAGUE_RESPONSES:

        return False

    if normalized in NOT_APPLICABLE_RESPONSES:

        return allow_not_applicable

    return bool(
        re.search(
            r"[a-z0-9]",
            normalized,
        )
    )


def field_has_valid_value(
    data: dict,
    field: str,
) -> bool:

    if not isinstance(
        data,
        dict,
    ):

        return False

    value = data.get(
        field
    )

    if field == "empresa_externa_requerida":

        return isinstance(
            value,
            bool,
        )

    if field == "personal_requerido":

        if isinstance(
            value,
            bool,
        ):

            return False

        try:

            return float(
                value
            ) > 0

        except (
            TypeError,
            ValueError,
        ):

            return False

    if field == "dimensiones":

        if isinstance(
            value,
            dict,
        ):

            if (
                value.get(
                    "aplica"
                ) is False
                or value.get(
                    "no_aplica"
                ) is True
            ):

                return True

            return any(
                _is_meaningful_scalar(
                    dimension_value
                )
                for dimension_value in value.values()
            )

        return is_explicit_not_applicable(
            value
        )

    if field in LIST_FIELDS:

        if not isinstance(
            value,
            list,
        ):

            return False

        allow_not_applicable = (
            field in EXPLICIT_NOT_APPLICABLE_FIELDS
            or field == "observaciones"
        )

        return any(
            _is_meaningful_scalar(
                item,
                allow_not_applicable=allow_not_applicable,
            )
            for item in value
        )

    if field == "jornada":

        normalized = normalize_validation_text(
            value
        )

        return normalized in {
            "diurna",
            "nocturna",
            "mixta",
            "dia",
            "de dia",
            "noche",
            "de noche",
            "ambas",
        }

    if field == "prioridad":

        return normalize_validation_text(
            value
        ) in {
            "emergencia",
            "urgente",
            "alta",
            "media",
            "baja",
            "normal",
        }

    return _is_meaningful_scalar(
        value,
        allow_not_applicable=(
            field in EXPLICIT_NOT_APPLICABLE_FIELDS
        ),
    )


def get_required_missing(
    data: dict,
) -> list:

    if not isinstance(
        data,
        dict,
    ):

        data = {}

    missing = [
        label
        for field, label in REQUIRED_FIELD_LABELS
        if not field_has_valid_value(
            data=data,
            field=field,
        )
    ]

    if (
        field_has_valid_value(
            data=data,
            field="tipo_trabajo",
        )
        and field_has_valid_value(
            data=data,
            field="descripcion",
        )
        and normalize_validation_text(
            data.get(
                "tipo_trabajo"
            )
        ) == normalize_validation_text(
            data.get(
                "descripcion"
            )
        )
        and "descripcion" not in missing
    ):

        missing.append(
            "descripcion"
        )

    if (
        data.get(
            "empresa_externa_requerida"
        ) is True
        and not field_has_valid_value(
            data=data,
            field="empresa_externa_detalle",
        )
    ):

        missing.append(
            CONDITIONAL_EXTERNAL_DETAIL_LABEL
        )

    return missing


def expected_question_fields(
    session: dict,
) -> list:

    if not isinstance(
        session,
        dict,
    ):

        return []

    fields = []

    last_field = session.get(
        "last_question_field"
    )

    if last_field:

        fields.append(
            last_field
        )

    pending_fields = session.get(
        "pending_question_fields",
        [],
    )

    if isinstance(
        pending_fields,
        list,
    ):

        for field in pending_fields:

            if field and field not in fields:

                fields.append(
                    field
                )

    return fields


def extract_contextual_values(
    message: str,
    expected_fields: list,
) -> dict:

    expected_fields = (
        expected_fields
        if isinstance(
            expected_fields,
            list,
        )
        else []
    )

    normalized = normalize_validation_text(
        message
    )

    result = {}

    if "empresa_externa_requerida" in expected_fields:

        boolean_value = parse_natural_boolean(
            message
        )

        is_explicit_phrase = (
            "empresa externa" in normalized
        )

        if (
            boolean_value is not None
            and (
                len(
                    expected_fields
                ) == 1
                or is_explicit_phrase
            )
        ):

            result[
                "empresa_externa_requerida"
            ] = boolean_value

    if (
        "dimensiones" in expected_fields
        and is_explicit_not_applicable(
            message
        )
        and len(
            expected_fields
        ) == 1
    ):

        result[
            "dimensiones"
        ] = {
            "aplica": False,
        }

    return result


def sanitize_report_data(
    extracted_data,
    source_message: str = "",
    expected_fields: list = None,
) -> dict:

    if not isinstance(
        extracted_data,
        dict,
    ):

        return {}

    expected_fields = (
        expected_fields
        if isinstance(
            expected_fields,
            list,
        )
        else []
    )

    contextual_values = extract_contextual_values(
        message=source_message,
        expected_fields=expected_fields,
    )

    if (
        is_vague_response(
            source_message
        )
        and not contextual_values
    ):

        return {}

    result = {}

    for field, raw_value in extracted_data.items():

        value = raw_value

        if field == "empresa_externa_requerida":

            if not isinstance(
                value,
                bool,
            ):

                value = parse_natural_boolean(
                    value
                )

            if not isinstance(
                value,
                bool,
            ):

                continue

        elif field == "personal_requerido":

            if isinstance(
                value,
                bool,
            ):

                continue

            try:

                numeric_value = float(
                    value
                )

            except (
                TypeError,
                ValueError,
            ):

                continue

            if numeric_value <= 0:

                continue

            value = (
                int(
                    numeric_value
                )
                if numeric_value.is_integer()
                else numeric_value
            )

        elif field == "dimensiones":

            dimension_not_applicable = (
                is_explicit_not_applicable(
                    value
                )
                or (
                    isinstance(
                        value,
                        dict,
                    )
                    and (
                        value.get(
                            "aplica"
                        ) is False
                        or value.get(
                            "no_aplica"
                        ) is True
                    )
                )
            )

            if dimension_not_applicable:

                if not is_contextual_not_applicable(
                    message=source_message,
                    field=field,
                    expected_fields=expected_fields,
                ):

                    continue

                value = {
                    "aplica": False,
                }

        elif field in LIST_FIELDS:

            if not isinstance(
                value,
                list,
            ):

                continue

            sanitized_items = []

            for item in value:

                if (
                    is_explicit_not_applicable(
                        item
                    )
                    and field in EXPLICIT_NOT_APPLICABLE_FIELDS
                    and not is_contextual_not_applicable(
                        message=source_message,
                        field=field,
                        expected_fields=expected_fields,
                    )
                ):

                    continue

                if _is_meaningful_scalar(
                    item,
                    allow_not_applicable=(
                        field in EXPLICIT_NOT_APPLICABLE_FIELDS
                        or field == "observaciones"
                    ),
                ):

                    sanitized_items.append(
                        item
                    )

            value = sanitized_items

            if not value:

                continue

        elif (
            field in EXPLICIT_NOT_APPLICABLE_FIELDS
            and is_explicit_not_applicable(
                value
            )
            and not is_contextual_not_applicable(
                message=source_message,
                field=field,
                expected_fields=expected_fields,
            )
        ):

            continue

        candidate_data = {
            field: value,
        }

        if field_has_valid_value(
            data=candidate_data,
            field=field,
        ):

            result[
                field
            ] = value

    result.update(
        contextual_values
    )

    if result.get(
        "empresa_externa_requerida"
    ) is False:

        result.pop(
            "empresa_externa_detalle",
            None,
        )

    return result
