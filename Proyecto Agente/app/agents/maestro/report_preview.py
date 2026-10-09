# ============================================================
# CONSTRUIR PREVIEW DEL LEVANTAMIENTO
# ============================================================

def build_preview(
    session: dict,
    title: str = "Levantamiento actualizado",
) -> str:

    data = session.get(
        "data",
        {},
    )

    quote_number = session.get(
        "quote_number"
    )

    lines = [
        "👷 *Agente JCF*",
        "",
        f"✅ *{title}*",
        "",
    ]

    # ========================================================
    # COTIZACIÓN
    # ========================================================

    if quote_number:

        add_section(
            lines,
            "Cotización",
            [
                quote_number
            ],
        )

    # ========================================================
    # CLIENTE
    # ========================================================

    cliente = data.get(
        "cliente"
    )

    if cliente:

        add_section(
            lines,
            "Cliente",
            [
                cliente
            ],
        )

    # ========================================================
    # RECINTO
    # ========================================================

    recinto = data.get(
        "recinto"
    )

    if recinto:

        add_section(
            lines,
            "Recinto",
            [
                recinto
            ],
        )

    # ========================================================
    # SECTOR
    # ========================================================

    sector = data.get(
        "sector"
    )

    if sector:

        add_section(
            lines,
            "Sector",
            [
                sector
            ],
        )

    # ========================================================
    # TRABAJO
    # ========================================================

    tipo_trabajo = data.get(
        "tipo_trabajo"
    )

    if tipo_trabajo:

        add_section(
            lines,
            "Trabajo",
            [
                tipo_trabajo
            ],
        )

    # ========================================================
    # DESCRIPCIÓN
    # ========================================================

    descripcion = data.get(
        "descripcion"
    )

    if (
        descripcion
        and not same_text(
            descripcion,
            tipo_trabajo,
        )
    ):

        add_section(
            lines,
            "Descripción",
            [
                descripcion
            ],
        )

    # ========================================================
    # DIMENSIONES
    # ========================================================

    dimensiones = data.get(
        "dimensiones",
        {},
    )

    dimension_lines = []

    if isinstance(
        dimensiones,
        dict,
    ):

        if (
            dimensiones.get(
                "aplica"
            ) is False
            or dimensiones.get(
                "no_aplica"
            ) is True
        ):

            dimension_lines.append(
                "No aplica para este trabajo"
            )

        dimension_map = [
            (
                "largo_m",
                "Largo",
                "m",
            ),
            (
                "ancho_m",
                "Ancho",
                "m",
            ),
            (
                "alto_m",
                "Alto",
                "m",
            ),
            (
                "diametro_m",
                "Diámetro",
                "m",
            ),
            (
                "espesor_mm",
                "Espesor",
                "mm",
            ),
            (
                "espesor_cm",
                "Espesor",
                "cm",
            ),
        ]

        for (
            key,
            label,
            unit,
        ) in dimension_map:

            value = dimensiones.get(
                key
            )

            if value is not None:

                dimension_lines.append(
                    f"{label}: "
                    f"{format_number(value)} "
                    f"{unit}"
                )

    if dimension_lines:

        add_section(
            lines,
            "Dimensiones",
            dimension_lines,
        )

    # ========================================================
    # SUPERFICIE
    # ========================================================

    superficie = data.get(
        "superficie_m2"
    )

    if superficie is not None:

        add_section(
            lines,
            "Superficie aproximada",
            [
                f"{format_number(superficie)} m²"
            ],
        )

    # ========================================================
    # ESTADO ACTUAL
    # ========================================================

    estado_actual = data.get(
        "estado_actual"
    )

    if estado_actual:

        add_section(
            lines,
            "Estado actual",
            [
                estado_actual
            ],
        )

    # ========================================================
    # MATERIALES
    # ========================================================

    materiales = data.get(
        "materiales",
        [],
    )

    material_lines = []

    if isinstance(
        materiales,
        list,
    ):

        for material in materiales:

            formatted = format_list_item(
                material
            )

            if formatted:

                material_lines.append(
                    formatted
                )

    if material_lines:

        add_section(
            lines,
            "Materiales considerados",
            material_lines,
        )

    # ========================================================
    # CANTIDADES
    # ========================================================

    cantidades = data.get(
        "cantidades",
        [],
    )

    quantity_lines = []

    if isinstance(
        cantidades,
        list,
    ):

        for cantidad in cantidades:

            formatted = format_quantity(
                cantidad
            )

            if formatted:

                quantity_lines.append(
                    formatted
                )

    if quantity_lines:

        add_section(
            lines,
            "Cantidades / aplicación",
            quantity_lines,
        )

    # ========================================================
    # TRABAJOS REQUERIDOS
    # ========================================================

    trabajos = data.get(
        "trabajos_requeridos",
        [],
    )

    work_lines = []

    if isinstance(
        trabajos,
        list,
    ):

        for trabajo in trabajos:

            if trabajo:

                work_lines.append(
                    str(
                        trabajo
                    )
                )

    if work_lines:

        add_section(
            lines,
            "Trabajos requeridos",
            work_lines,
        )

    # ========================================================
    # EQUIPAMIENTO NECESARIO
    # ========================================================

    equipamiento = data.get(
        "equipamiento_necesario",
        [],
    )

    equipment_lines = []

    if isinstance(
        equipamiento,
        list,
    ):

        for item in equipamiento:

            formatted = format_list_item(
                item
            )

            if formatted:

                equipment_lines.append(
                    formatted
                )

    elif equipamiento:

        equipment_lines.append(
            str(
                equipamiento
            )
        )

    if equipment_lines:

        add_section(
            lines,
            "Equipamiento necesario",
            equipment_lines,
        )

    # ========================================================
    # TIEMPO ESTIMADO
    # ========================================================

    tiempo_estimado = data.get(
        "tiempo_estimado"
    )

    if tiempo_estimado:

        add_section(
            lines,
            "Tiempo estimado",
            [
                str(
                    tiempo_estimado
                )
            ],
        )

    # ========================================================
    # JORNADA
    # ========================================================

    jornada = data.get(
        "jornada"
    )

    if jornada:

        add_section(
            lines,
            "Jornada",
            [
                str(
                    jornada
                )
            ],
        )

    # ========================================================
    # PERSONAL REQUERIDO
    # ========================================================

    personal_requerido = data.get(
        "personal_requerido"
    )

    if personal_requerido is not None:

        personal_text = format_personnel(
            personal_requerido
        )

        add_section(
            lines,
            "Personal requerido",
            [
                personal_text
            ],
        )

    # ========================================================
    # EMPRESA EXTERNA
    # ========================================================

    empresa_externa = data.get(
        "empresa_externa_requerida"
    )

    empresa_externa_detalle = data.get(
        "empresa_externa_detalle"
    )

    if empresa_externa is not None:

        if empresa_externa is True:

            external_text = "Sí"

            if empresa_externa_detalle:

                external_text += (
                    f" — "
                    f"{empresa_externa_detalle}"
                )

        else:

            external_text = "No"

        add_section(
            lines,
            "Empresa externa requerida",
            [
                external_text
            ],
        )

    # ========================================================
    # PRIORIDAD
    # ========================================================

    prioridad = data.get(
        "prioridad"
    )

    if prioridad:

        add_section(
            lines,
            "Prioridad",
            [
                str(
                    prioridad
                )
            ],
        )

    # ========================================================
    # OBSERVACIONES
    # ========================================================

    observaciones = data.get(
        "observaciones",
        [],
    )

    observation_lines = []

    if isinstance(
        observaciones,
        list,
    ):

        for observacion in observaciones:

            if observacion:

                observation_lines.append(
                    str(
                        observacion
                    )
                )

    elif observaciones:

        observation_lines.append(
            str(
                observaciones
            )
        )

    if observation_lines:

        add_section(
            lines,
            "Observaciones",
            observation_lines,
        )

    # ========================================================
    # REGISTRO FOTOGRÁFICO
    # ========================================================

    imagenes = data.get(
        "imagenes",
        [],
    )

    if (
        isinstance(
            imagenes,
            list,
        )
        and imagenes
    ):

        photo_count = len(
            imagenes
        )

        photo_text = (
            f"{photo_count} fotografía"
            if photo_count == 1
            else f"{photo_count} fotografías"
        )

        add_section(
            lines,
            "Registro fotográfico",
            [
                f"{photo_text} asociadas al levantamiento"
            ],
        )

    return "\n".join(
        lines
    ).strip()


# ============================================================
# AGREGAR SECCIÓN
# ============================================================

def add_section(
    lines: list,
    title: str,
    values: list,
):

    valid_values = [
        value
        for value in values
        if value not in (
            None,
            "",
        )
    ]

    if not valid_values:

        return

    lines.append(
        f"*{title}*"
    )

    for value in valid_values:

        lines.append(
            f"• {value}"
        )

    lines.append("")


# ============================================================
# COMPARAR TEXTOS
# ============================================================

def same_text(
    first,
    second,
) -> bool:

    if not first or not second:

        return False

    first_clean = (
        str(
            first
        )
        .strip()
        .lower()
    )

    second_clean = (
        str(
            second
        )
        .strip()
        .lower()
    )

    return (
        first_clean
        == second_clean
    )


# ============================================================
# FORMATEAR ELEMENTO DE LISTA
# ============================================================

def format_list_item(
    item,
):

    if isinstance(
        item,
        str,
    ):

        return item

    if not isinstance(
        item,
        dict,
    ):

        return str(
            item
        )

    name = (
        item.get(
            "nombre"
        )
        or item.get(
            "material"
        )
        or item.get(
            "item"
        )
        or item.get(
            "equipo"
        )
    )

    quantity = item.get(
        "cantidad"
    )

    unit = item.get(
        "unidad"
    )

    if not name:

        return None

    text = str(
        name
    )

    if quantity is not None:

        text += (
            f": {quantity}"
        )

    if unit:

        text += (
            f" {unit}"
        )

    return text


# ============================================================
# FORMATEAR CANTIDAD
# ============================================================

def format_quantity(
    item,
):

    if isinstance(
        item,
        str,
    ):

        return item

    if not isinstance(
        item,
        dict,
    ):

        return str(
            item
        )

    name = (
        item.get(
            "item"
        )
        or item.get(
            "material"
        )
        or item.get(
            "nombre"
        )
    )

    quantity = item.get(
        "cantidad"
    )

    unit = item.get(
        "unidad"
    )

    if not name:

        return None

    text = str(
        name
    )

    if quantity is not None:

        text += (
            f": {quantity}"
        )

    if unit:

        text += (
            f" {unit}"
        )

    return text


# ============================================================
# FORMATEAR PERSONAL
# ============================================================

def format_personnel(
    value,
) -> str:

    try:

        number = int(
            value
        )

        if number == 1:

            return (
                "1 persona"
            )

        return (
            f"{number} personas"
        )

    except (
        TypeError,
        ValueError,
    ):

        return str(
            value
        )


# ============================================================
# FORMATO DE NÚMEROS
# ============================================================

def format_number(
    value,
) -> str:

    if isinstance(
        value,
        float,
    ):

        if value.is_integer():

            return str(
                int(
                    value
                )
            )

        return (
            f"{value:.2f}"
            .rstrip(
                "0"
            )
            .rstrip(
                "."
            )
            .replace(
                ".",
                ",",
            )
        )

    return str(
        value
    )
