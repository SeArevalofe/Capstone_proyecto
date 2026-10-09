import re
import requests

from app.config import (
    GOOGLE_MAPS_API_KEY,
)


# ============================================================
# GOOGLE GEOCODING
# ============================================================

GOOGLE_GEOCODING_URL = (
    "https://maps.googleapis.com/maps/api/geocode/json"
)


# ============================================================
# LIMPIAR TEXTO
# ============================================================

def clean_text(
    value,
) -> str:

    text = str(
        value
        or ""
    ).strip()

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text


# ============================================================
# LIMPIAR DIRECCIÓN
# ============================================================

def clean_location_address(
    address,
) -> str:

    address = clean_text(
        address
    )

    if not address:

        return ""

    parts = []

    for item in address.split(","):

        item = clean_text(
            item
        )

        if (
            item
            and item not in parts
        ):

            parts.append(
                item
            )

    return ", ".join(
        parts
    )


# ============================================================
# COORDENADA
# ============================================================

def coordinate(
    value,
):

    try:

        return float(
            value
        )

    except (
        TypeError,
        ValueError,
    ):

        return None


# ============================================================
# VALIDAR COORDENADAS
# ============================================================

def valid_coordinates(
    latitude,
    longitude,
) -> bool:

    if (
        latitude is None
        or longitude is None
    ):

        return False

    if not (
        -90
        <= latitude
        <= 90
    ):

        return False

    if not (
        -180
        <= longitude
        <= 180
    ):

        return False

    return True


# ============================================================
# FORMATEAR COORDENADAS
# ============================================================

def format_coordinates(
    latitude,
    longitude,
) -> str:

    if not valid_coordinates(
        latitude,
        longitude,
    ):

        return ""

    return (
        f"{latitude:.6f}, "
        f"{longitude:.6f}"
    )


# ============================================================
# EXTRAER COMPONENTE DE GOOGLE
# ============================================================

def get_address_component(
    components: list,
    component_type: str,
) -> str:

    if not isinstance(
        components,
        list,
    ):

        return ""

    for component in components:

        if not isinstance(
            component,
            dict,
        ):

            continue

        types = component.get(
            "types",
            [],
        )

        if (
            component_type
            not in types
        ):

            continue

        return clean_text(
            component.get(
                "long_name"
            )
        )

    return ""


# ============================================================
# CONSTRUIR DIRECCIÓN SIMPLE
#
# Ejemplo:
#
# Pedro Lagos 980, Santiago
# ============================================================

def build_simple_address(
    google_result: dict,
) -> str:

    if not isinstance(
        google_result,
        dict,
    ):

        return ""

    components = google_result.get(
        "address_components",
        [],
    )

    route = get_address_component(
        components,
        "route",
    )

    street_number = get_address_component(
        components,
        "street_number",
    )

    city = (
        get_address_component(
            components,
            "locality",
        )
        or get_address_component(
            components,
            "administrative_area_level_3",
        )
        or get_address_component(
            components,
            "administrative_area_level_2",
        )
    )

    street = ""

    if (
        route
        and street_number
    ):

        street = (
            f"{route} {street_number}"
        )

    elif route:

        street = route

    if (
        street
        and city
    ):

        return (
            f"{street}, {city}"
        )

    if street:

        return street

    return clean_location_address(
        google_result.get(
            "formatted_address"
        )
    )


# ============================================================
# NORMALIZAR DIRECCIÓN PARA GOOGLE
# ============================================================

def normalize_geocoding_address(
    address,
) -> str:

    address = clean_location_address(
        address
    )

    if not address:

        return ""

    # --------------------------------------------------------
    # K/M -> KM
    # --------------------------------------------------------

    address = re.sub(
        r"\bK\s*/\s*M\b",
        "KM",
        address,
        flags=re.IGNORECASE,
    )

    # --------------------------------------------------------
    # K M -> KM
    # --------------------------------------------------------

    address = re.sub(
        r"\bK\s+M\b",
        "KM",
        address,
        flags=re.IGNORECASE,
    )

    # --------------------------------------------------------
    # K.M. -> KM
    # --------------------------------------------------------

    address = re.sub(
        r"\bK\.?\s*M\.?\b",
        "KM",
        address,
        flags=re.IGNORECASE,
    )

    address = re.sub(
        r"\s+",
        " ",
        address,
    )

    return address.strip()


# ============================================================
# GENERAR VARIANTES PARA BUSCAR DIRECCIÓN
# ============================================================

def build_geocoding_variants(
    address,
) -> list:

    original = clean_location_address(
        address
    )

    normalized = normalize_geocoding_address(
        original
    )

    variants = []

    def add_variant(
        value,
    ):

        value = clean_location_address(
            value
        )

        if (
            value
            and value not in variants
        ):

            variants.append(
                value
            )

    # --------------------------------------------------------
    # ORIGINAL
    # --------------------------------------------------------

    add_variant(
        original
    )

    # --------------------------------------------------------
    # NORMALIZADA
    # --------------------------------------------------------

    add_variant(
        normalized
    )

    # --------------------------------------------------------
    # + CHILE
    # --------------------------------------------------------

    if normalized:

        add_variant(
            f"{normalized}, Chile"
        )

    # --------------------------------------------------------
    # + SANTIAGO, CHILE
    # --------------------------------------------------------

    if normalized:

        add_variant(
            f"{normalized}, Santiago, Chile"
        )

    return variants


# ============================================================
# GOOGLE REVERSE GEOCODING
#
# LAT/LONG -> DIRECCIÓN
# ============================================================

def reverse_geocode_google(
    latitude,
    longitude,
) -> dict:

    latitude = coordinate(
        latitude
    )

    longitude = coordinate(
        longitude
    )

    if not valid_coordinates(
        latitude,
        longitude,
    ):

        return {
            "resolved": False,
            "address": "",
            "reason": "invalid_coordinates",
        }

    if not GOOGLE_MAPS_API_KEY:

        print()
        print("=" * 70)
        print("⚠️ GOOGLE MAPS API KEY NO CONFIGURADA")
        print("=" * 70)

        return {
            "resolved": False,
            "address": "",
            "reason": "missing_api_key",
        }

    params = {
        "latlng": (
            f"{latitude},"
            f"{longitude}"
        ),

        "key": (
            GOOGLE_MAPS_API_KEY
        ),

        "language": "es",

        "region": "cl",
    }

    print()
    print("=" * 70)
    print("🌎 GOOGLE REVERSE GEOCODING")
    print("=" * 70)

    print(
        "Latitud:",
        latitude,
    )

    print(
        "Longitud:",
        longitude,
    )

    print("=" * 70)

    try:

        response = requests.get(
            GOOGLE_GEOCODING_URL,
            params=params,
            timeout=8,
        )

    except requests.RequestException as error:

        print()
        print("=" * 70)
        print("❌ ERROR CONECTANDO CON GOOGLE MAPS")
        print("=" * 70)

        print(
            type(error).__name__,
            str(error),
        )

        print("=" * 70)

        return {
            "resolved": False,
            "address": "",
            "reason": "connection_error",
            "error": str(
                error
            ),
        }

    if not response.ok:

        print()
        print("=" * 70)
        print("❌ ERROR HTTP GOOGLE MAPS")
        print("=" * 70)

        print(
            "Status:",
            response.status_code,
        )

        print("=" * 70)

        return {
            "resolved": False,
            "address": "",
            "reason": "http_error",
        }

    try:

        data = response.json()

    except Exception as error:

        return {
            "resolved": False,
            "address": "",
            "reason": "invalid_json",
            "error": str(
                error
            ),
        }

    status = clean_text(
        data.get(
            "status"
        )
    )

    results = data.get(
        "results",
        [],
    )

    if not isinstance(
        results,
        list,
    ):

        results = []

    print()
    print("=" * 70)
    print("📍 RESPUESTA GOOGLE MAPS")
    print("=" * 70)

    print(
        "Status:",
        status,
    )

    print(
        "Resultados:",
        len(
            results
        ),
    )

    if data.get(
        "error_message"
    ):

        print(
            "Error Google:",
            data.get(
                "error_message"
            ),
        )

    print("=" * 70)

    if (
        status != "OK"
        or not results
    ):

        return {
            "resolved": False,
            "address": "",
            "reason": (
                status
                or "no_results"
            ),
        }

    first_result = results[
        0
    ]

    address = build_simple_address(
        first_result
    )

    if not address:

        return {
            "resolved": False,
            "address": "",
            "reason": "missing_address",
        }

    print()
    print("=" * 70)
    print("✅ DIRECCIÓN GOOGLE RESUELTA")
    print("=" * 70)

    print(
        address
    )

    print("=" * 70)

    return {
        "resolved": True,

        "address": address,

        "formatted_address": clean_location_address(
            first_result.get(
                "formatted_address"
            )
        ),

        "reason": None,

        "source": "google_reverse_geocoding",
    }


# ============================================================
# GOOGLE FORWARD GEOCODING
#
# DIRECCIÓN -> LAT/LONG
#
# Se utiliza para encontrar las coordenadas de la
# dirección oficial del servicio.
# ============================================================

def geocode_address_google(
    address,
) -> dict:

    address = clean_location_address(
        address
    )

    if not address:

        return {
            "resolved": False,
            "reason": "missing_address",
            "latitude": None,
            "longitude": None,
        }

    if not GOOGLE_MAPS_API_KEY:

        return {
            "resolved": False,
            "reason": "missing_api_key",
            "latitude": None,
            "longitude": None,
        }

    variants = build_geocoding_variants(
        address
    )

    print()
    print("=" * 70)
    print("🌎 GOOGLE FORWARD GEOCODING")
    print("=" * 70)

    print(
        "Dirección original:",
        address,
    )

    print(
        "Variantes:",
        variants,
    )

    print("=" * 70)

    attempted = []

    last_status = None

    # ========================================================
    # PROBAR VARIANTES
    # ========================================================

    for variant in variants:

        attempted.append(
            variant
        )

        print()
        print("=" * 70)
        print("🔎 INTENTO GEOCODING")
        print("=" * 70)

        print(
            "Dirección:",
            variant,
        )

        print("=" * 70)

        try:

            response = requests.get(
                GOOGLE_GEOCODING_URL,
                params={
                    "address": variant,
                    "key": GOOGLE_MAPS_API_KEY,
                    "language": "es",
                    "region": "cl",
                    "components": "country:CL",
                },
                timeout=8,
            )

        except requests.RequestException as error:

            print(
                "❌ Error Google:",
                type(error).__name__,
                str(error),
            )

            continue

        if not response.ok:

            print(
                "❌ HTTP Google:",
                response.status_code,
            )

            continue

        try:

            data = response.json()

        except Exception as error:

            print(
                "❌ JSON Google inválido:",
                str(error),
            )

            continue

        status = clean_text(
            data.get(
                "status"
            )
        )

        last_status = status

        results = data.get(
            "results",
            [],
        )

        if not isinstance(
            results,
            list,
        ):

            results = []

        print(
            "Status:",
            status,
        )

        print(
            "Resultados:",
            len(
                results
            ),
        )

        if data.get(
            "error_message"
        ):

            print(
                "Error Google:",
                data.get(
                    "error_message"
                ),
            )

        if (
            status != "OK"
            or not results
        ):

            continue

        first_result = results[
            0
        ]

        geometry = first_result.get(
            "geometry",
            {},
        )

        location = geometry.get(
            "location",
            {},
        )

        latitude = coordinate(
            location.get(
                "lat"
            )
        )

        longitude = coordinate(
            location.get(
                "lng"
            )
        )

        if not valid_coordinates(
            latitude,
            longitude,
        ):

            continue

        formatted_address = clean_location_address(
            first_result.get(
                "formatted_address"
            )
        )

        print()
        print("=" * 70)
        print("✅ DIRECCIÓN DEL SERVICIO GEOCODIFICADA")
        print("=" * 70)

        print(
            "Variante utilizada:",
            variant,
        )

        print(
            "Dirección Google:",
            formatted_address,
        )

        print(
            "Latitud:",
            latitude,
        )

        print(
            "Longitud:",
            longitude,
        )

        print("=" * 70)

        return {
            "resolved": True,

            "reason": None,

            "latitude": latitude,

            "longitude": longitude,

            "formatted_address": (
                formatted_address
            ),

            "matched_variant": variant,

            "attempted_variants": (
                attempted
            ),

            "source": (
                "google_forward_geocoding"
            ),
        }

    print()
    print("=" * 70)
    print("⚠️ GOOGLE NO PUDO RESOLVER LA DIRECCIÓN")
    print("=" * 70)

    print(
        "Dirección:",
        address,
    )

    print(
        "Intentos:",
        attempted,
    )

    print(
        "Último estado Google:",
        last_status,
    )

    print("=" * 70)

    return {
        "resolved": False,

        "reason": "address_not_resolved",

        "google_status": last_status,

        "latitude": None,

        "longitude": None,

        "attempted_variants": (
            attempted
        ),
    }


# ============================================================
# RESOLVER UBICACIÓN WHATSAPP
#
# PRIORIDAD:
#
# 1. Dirección entregada directamente por WhatsApp.
# 2. Coordenadas -> Google Maps.
# 3. Nombre del lugar.
# 4. Coordenadas como fallback.
# ============================================================

def resolve_location_text(
    latitude=None,
    longitude=None,
    address=None,
    name=None,
) -> dict:

    latitude = coordinate(
        latitude
    )

    longitude = coordinate(
        longitude
    )

    address = clean_location_address(
        address
    )

    name = clean_text(
        name
    )

    coordinates_text = format_coordinates(
        latitude,
        longitude,
    )

    print()
    print("=" * 70)
    print("🌎 RESOLVIENDO UBICACIÓN")
    print("=" * 70)

    print(
        "Latitud:",
        latitude,
    )

    print(
        "Longitud:",
        longitude,
    )

    print(
        "Dirección WhatsApp:",
        address,
    )

    print(
        "Nombre WhatsApp:",
        name,
    )

    print("=" * 70)

    # ========================================================
    # DIRECCIÓN WHATSAPP
    # ========================================================

    if address:

        return {
            "resolved": True,

            "text": address,

            "address": address,

            "coordinates": coordinates_text,

            "source": "whatsapp_address",

            "latitude": latitude,

            "longitude": longitude,
        }

    # ========================================================
    # GOOGLE REVERSE GEOCODING
    # ========================================================

    if valid_coordinates(
        latitude,
        longitude,
    ):

        google_result = reverse_geocode_google(
            latitude=latitude,
            longitude=longitude,
        )

        if google_result.get(
            "resolved"
        ):

            google_address = clean_text(
                google_result.get(
                    "address"
                )
            )

            return {
                "resolved": True,

                "text": google_address,

                "address": google_address,

                "formatted_address": (
                    google_result.get(
                        "formatted_address"
                    )
                ),

                "coordinates": coordinates_text,

                "source": (
                    "google_reverse_geocoding"
                ),

                "latitude": latitude,

                "longitude": longitude,
            }

    # ========================================================
    # NOMBRE DEL LUGAR
    # ========================================================

    if name:

        return {
            "resolved": True,

            "text": name,

            "address": "",

            "coordinates": coordinates_text,

            "source": "whatsapp_name",

            "latitude": latitude,

            "longitude": longitude,
        }

    # ========================================================
    # FALLBACK COORDENADAS
    # ========================================================

    if coordinates_text:

        print()
        print("=" * 70)
        print("⚠️ USANDO COORDENADAS COMO FALLBACK")
        print("=" * 70)

        print(
            coordinates_text
        )

        print("=" * 70)

        return {
            "resolved": True,

            "text": coordinates_text,

            "address": "",

            "coordinates": coordinates_text,

            "source": "coordinates_fallback",

            "latitude": latitude,

            "longitude": longitude,
        }

    return {
        "resolved": False,

        "text": "",

        "address": "",

        "coordinates": "",

        "source": None,

        "latitude": None,

        "longitude": None,
    }