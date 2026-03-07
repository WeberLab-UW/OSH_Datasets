"""Normalize BOM component fields: category, manufacturer, footprint, value.

Adds seven columns to ``bom_components`` via ALTER TABLE:

    - ``component_category``: Taxonomy label (resistor, capacitor, ic, ...)
    - ``manufacturer_canonical``: Cleaned manufacturer name
    - ``manufacturer_is_distributor``: 1 if name is a distributor, not a mfr
    - ``footprint_normalized``: Standardized package code (e.g. "0603")
    - ``footprint_mount_type``: smd | tht | other
    - ``value_numeric``: Parsed electrical value in base SI units
    - ``value_unit``: SI unit string (ohm, F, H, V, A, Hz)

Three-signal cascade for category classification:
    reference designator (highest) > component name > footprint (lowest).
"""

import re
import sqlite3
from pathlib import Path

from osh_datasets.config import DB_PATH, get_logger
from osh_datasets.db import open_connection

logger = get_logger(__name__)

# ── Component Category Taxonomy ─────────────────────────────────

_REFDES_TWO_LETTER: dict[str, str] = {
    "bt": "battery",
    "cr": "diode",
    "ds": "led",
    "fb": "ferrite_bead",
    "fl": "inductor",
    "mp": "mechanical",
    "rn": "resistor",
    "rv": "resistor",
    "sw": "switch",
    "tp": "test_point",
    "vr": "voltage_regulator",
}

_REFDES_ONE_LETTER: dict[str, str] = {
    "r": "resistor",
    "c": "capacitor",
    "l": "inductor",
    "d": "diode",
    "q": "transistor",
    "u": "ic",
    "j": "connector",
    "p": "connector",
    "f": "fuse",
    "y": "crystal",
    "x": "crystal",
    "k": "relay",
    "t": "transformer",
    "m": "motor",
    "s": "switch",
    "e": "antenna",
    "w": "wire",
    "h": "mechanical",
}

_REFDES_RE = re.compile(r"^([A-Za-z]{1,3})\d")

# Ordered: specific patterns before generic ones.
_NAME_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bschottky\b"), "diode"),
    (re.compile(r"\bzener\b"), "diode"),
    (re.compile(r"\bferrite\s*bead\b"), "ferrite_bead"),
    (re.compile(r"\bvoltage\s*reg"), "voltage_regulator"),
    (re.compile(r"\bldo\b"), "voltage_regulator"),
    (re.compile(r"\blinear\s*reg"), "voltage_regulator"),
    (re.compile(r"\bop[\s-]?amp\b"), "ic"),
    (re.compile(r"\bmicrocontroller\b"), "ic"),
    (re.compile(r"\bmcu\b"), "ic"),
    (re.compile(r"\bfpga\b"), "ic"),
    (re.compile(r"\beeprom\b"), "ic"),
    (re.compile(r"\bflash\b"), "ic"),
    (re.compile(r"\badc\b"), "ic"),
    (re.compile(r"\bdac\b"), "ic"),
    (re.compile(r"\buart\b"), "ic"),
    (re.compile(r"\bi2c\b"), "ic"),
    (re.compile(r"\bspi\b"), "ic"),
    (re.compile(r"\batmega"), "ic"),
    (re.compile(r"\bstm32"), "ic"),
    (re.compile(r"\besp32"), "ic"),
    (re.compile(r"\besp8266"), "ic"),
    (re.compile(r"\barduino\b"), "ic"),
    (re.compile(r"\braspberry\s*pi\b"), "ic"),
    (re.compile(r"\bnrf\d"), "ic"),
    (re.compile(r"\bmosfet\b"), "transistor"),
    (re.compile(r"\bbjt\b"), "transistor"),
    (re.compile(r"\btransistor\b"), "transistor"),
    (re.compile(r"\bled\b"), "led"),
    (re.compile(r"\bleds\b"), "led"),
    (re.compile(r"\brgb\s*led\b"), "led"),
    (re.compile(r"\bdiode\b"), "diode"),
    (re.compile(r"\bbridge\s*rect"), "diode"),
    (re.compile(r"\bcapacitor\b"), "capacitor"),
    (re.compile(r"\bresistor\b"), "resistor"),
    (re.compile(r"\binductor\b"), "inductor"),
    (re.compile(r"\bchoke\b"), "inductor"),
    (re.compile(r"\bconnector\b"), "connector"),
    (re.compile(r"\bheader\b"), "connector"),
    (re.compile(r"\bjst\b"), "connector"),
    (re.compile(r"\bpin\s*header\b"), "connector"),
    (re.compile(r"\bterminal\s*block\b"), "connector"),
    (re.compile(r"\bsocket\b"), "connector"),
    (re.compile(r"\busb\b"), "connector"),
    (re.compile(r"\bswitch\b"), "switch"),
    (re.compile(r"\bbutton\b"), "switch"),
    (re.compile(r"\btact\b"), "switch"),
    (re.compile(r"\bpush\s*button\b"), "switch"),
    (re.compile(r"\bfuse\b"), "fuse"),
    (re.compile(r"\bcrystal\b"), "crystal"),
    (re.compile(r"\boscillator\b"), "crystal"),
    (re.compile(r"\brelay\b"), "relay"),
    (re.compile(r"\btransformer\b"), "transformer"),
    (re.compile(r"\bsensor\b"), "sensor"),
    (re.compile(r"\bthermistor\b"), "sensor"),
    (re.compile(r"\baccelerometer\b"), "sensor"),
    (re.compile(r"\bgyro"), "sensor"),
    (re.compile(r"\bmotor\b"), "motor"),
    (re.compile(r"\bservo\b"), "motor"),
    (re.compile(r"\bstepper\b"), "motor"),
    (re.compile(r"\bbattery\b"), "battery"),
    (re.compile(r"\bbuzzer\b"), "sensor"),
    (re.compile(r"\bspeaker\b"), "sensor"),
    (re.compile(r"\bantenna\b"), "antenna"),
    (re.compile(r"\bpcb\b"), "pcb"),
    (re.compile(r"\bbreadboard\b"), "pcb"),
    (re.compile(r"\bwire"), "wire"),
    (re.compile(r"\bcable\b"), "wire"),
    (re.compile(r"\bjumper\b"), "wire"),
    (re.compile(r"\bscrew\b"), "mechanical"),
    (re.compile(r"\bbolt\b"), "mechanical"),
    (re.compile(r"\bnut\b"), "mechanical"),
    (re.compile(r"\bstandoff\b"), "mechanical"),
    (re.compile(r"\bspacer\b"), "mechanical"),
    (re.compile(r"\bwasher\b"), "mechanical"),
    (re.compile(r"\b3d\s*print"), "mechanical"),
    (re.compile(r"\benclosure\b"), "mechanical"),
    (re.compile(r"\bmount"), "mechanical"),
    # Value-based: if name is just a value like "10k", "100nf"
    (re.compile(r"^\d+(\.\d+)?\s*(k|m|meg)?(ohm)$"), "resistor"),
    (re.compile(r"^\d+(\.\d+)?\s*[kKmM]$"), "resistor"),
    (re.compile(r"^\d+(\.\d+)?\s*(u|n|p)f$"), "capacitor"),
    (re.compile(r"^\d+(\.\d+)?\s*(u|n|m)h$"), "inductor"),
]

_FOOTPRINT_CATEGORY: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)^resistor"), "resistor"),
    (re.compile(r"(?i)^capacitor"), "capacitor"),
    (re.compile(r"(?i)^inductor"), "inductor"),
    (re.compile(r"(?i)^diode"), "diode"),
    (re.compile(r"(?i)^led"), "led"),
    (re.compile(r"(?i)^crystal"), "crystal"),
    (re.compile(r"(?i)\bsot[\s-]?23\b"), "transistor"),
    (re.compile(r"(?i)\bto[\s-]?(92|220|252|263)\b"), "transistor"),
    (re.compile(r"(?i)\bsoic\b"), "ic"),
    (re.compile(r"(?i)\btssop\b"), "ic"),
    (re.compile(r"(?i)\bqfp\b"), "ic"),
    (re.compile(r"(?i)\bqfn\b"), "ic"),
    (re.compile(r"(?i)\bbga\b"), "ic"),
    (re.compile(r"(?i)\bdip[\s-]?\d"), "ic"),
]

# ── Manufacturer Canonicalization ────────────────────────────────

_GARBAGE_MFR: frozenset[str] = frozenset(
    {
        "",
        "na",
        "n/a",
        "n.a.",
        "none",
        "null",
        "unknown",
        "generic",
        "various",
        "dnp",
        "do not place",
        "tbd",
        "any",
        "-",
        "--",
        "assorted",
        "misc",
        "not specified",
        "see bom",
        "see notes",
    }
)

# (canonical_name, is_distributor)
_MFR_MAP: dict[str, tuple[str, bool]] = {
    # ── Passive component manufacturers ──
    "yageo": ("Yageo", False),
    "kemet": ("KEMET", False),
    "murata": ("Murata", False),
    "murata electronics": ("Murata", False),
    "murata manufacturing": ("Murata", False),
    "vishay": ("Vishay", False),
    "vishay intertechnology": ("Vishay", False),
    "panasonic": ("Panasonic", False),
    "panasonic electronic components": ("Panasonic", False),
    "samsung": ("Samsung Electro-Mechanics", False),
    "samsung electro-mechanics": ("Samsung Electro-Mechanics", False),
    "samsung(三星)": ("Samsung Electro-Mechanics", False),
    "tdk": ("TDK", False),
    "tdk corporation": ("TDK", False),
    "avx": ("AVX", False),
    "avx corporation": ("AVX", False),
    "bourns": ("Bourns", False),
    "bourns inc": ("Bourns", False),
    "wurth electronics": ("Wurth Elektronik", False),
    "wurth elektronik": ("Wurth Elektronik", False),
    "wurth": ("Wurth Elektronik", False),
    "uni-royal(厚声)": ("UNI-ROYAL", False),
    "uniohm": ("UniOhm", False),
    "kento": ("KENTO", False),
    "multicomp": ("Multicomp", False),
    "multicomp pro": ("Multicomp", False),
    # ── Semiconductor manufacturers ──
    "texas instruments": ("Texas Instruments", False),
    "ti": ("Texas Instruments", False),
    "st micro": ("STMicroelectronics", False),
    "stmicroelectronics": ("STMicroelectronics", False),
    "st": ("STMicroelectronics", False),
    "microchip": ("Microchip Technology", False),
    "microchip technology": ("Microchip Technology", False),
    "atmel": ("Microchip Technology", False),
    "on semiconductor": ("onsemi", False),
    "on semi": ("onsemi", False),
    "onsemi": ("onsemi", False),
    "nxp": ("NXP Semiconductors", False),
    "nxp semiconductors": ("NXP Semiconductors", False),
    "infineon": ("Infineon Technologies", False),
    "infineon technologies": ("Infineon Technologies", False),
    "analog devices": ("Analog Devices", False),
    "adi": ("Analog Devices", False),
    "linear tech": ("Analog Devices", False),
    "linear technology": ("Analog Devices", False),
    "maxim": ("Analog Devices", False),
    "maxim integrated": ("Analog Devices", False),
    "renesas": ("Renesas Electronics", False),
    "renesas electronics": ("Renesas Electronics", False),
    "broadcom": ("Broadcom", False),
    "nordic semiconductor": ("Nordic Semiconductor", False),
    "nordic": ("Nordic Semiconductor", False),
    "espressif": ("Espressif Systems", False),
    "espressif systems": ("Espressif Systems", False),
    "cypress": ("Infineon Technologies", False),
    "cypress semiconductor": ("Infineon Technologies", False),
    "lattice": ("Lattice Semiconductor", False),
    "lattice semiconductor": ("Lattice Semiconductor", False),
    "xilinx": ("AMD", False),
    "amd": ("AMD", False),
    "intel": ("Intel", False),
    # ── Connector manufacturers ──
    "molex": ("Molex", False),
    "jst": ("JST", False),
    "te connectivity": ("TE Connectivity", False),
    "te": ("TE Connectivity", False),
    "tyco": ("TE Connectivity", False),
    "samtec": ("Samtec", False),
    "amphenol": ("Amphenol", False),
    "hirose": ("Hirose Electric", False),
    "hirose electric": ("Hirose Electric", False),
    "phoenix contact": ("Phoenix Contact", False),
    "wago": ("WAGO", False),
    # ── Frequency control ──
    "abracon": ("Abracon", False),
    # ── Power ──
    "mean well": ("Mean Well", False),
    "recom": ("RECOM Power", False),
    "traco power": ("TRACO Power", False),
    # ── Other manufacturers ──
    "littelfuse": ("Littelfuse", False),
    "rohm": ("ROHM Semiconductor", False),
    "rohm semiconductor": ("ROHM Semiconductor", False),
    "diodes inc": ("Diodes Incorporated", False),
    "diodes incorporated": ("Diodes Incorporated", False),
    "toshiba": ("Toshiba", False),
    "boomele": ("BOOMELE", False),
    "reliapro": ("ReliaPro", False),
    # ── Distributors (flagged) ──
    "digikey": ("Digi-Key", True),
    "digi-key": ("Digi-Key", True),
    "digi-key electronics": ("Digi-Key", True),
    "mouser": ("Mouser Electronics", True),
    "mouser electronics": ("Mouser Electronics", True),
    "mouser.com": ("Mouser Electronics", True),
    "lcsc": ("LCSC", True),
    "farnell": ("Farnell", True),
    "element14": ("Farnell", True),
    "newark": ("Newark", True),
    "arrow": ("Arrow Electronics", True),
    "arrow electronics": ("Arrow Electronics", True),
    "amazon": ("Amazon", True),
    "amazon.com": ("Amazon", True),
    "ebay": ("eBay", True),
    "ebay.com": ("eBay", True),
    "aliexpress": ("AliExpress", True),
    "ali express": ("AliExpress", True),
    "banggood": ("Banggood", True),
    "sparkfun": ("SparkFun", True),
    "sparkfun electronics": ("SparkFun", True),
    "adafruit": ("Adafruit", True),
    "adafruit industries": ("Adafruit", True),
    "pololu": ("Pololu", True),
    "mcmaster-carr": ("McMaster-Carr", True),
    "mcmaster carr": ("McMaster-Carr", True),
    "mcmaster": ("McMaster-Carr", True),
    "rs components": ("RS Components", True),
    "rs online": ("RS Components", True),
    "tme": ("TME", True),
    "www.tme.eu": ("TME", True),
    "chip1stop": ("Chip1Stop", True),
    "seeed studio": ("Seeed Studio", True),
    "seeed": ("Seeed Studio", True),
    "seedstudio": ("Seeed Studio", True),
}

_CHINESE_PAREN_RE = re.compile(r"\([^)]*[\u4e00-\u9fff][^)]*\)")

# ── Footprint Normalization ──────────────────────────────────────

_FP_EDA_PREFIX_RE = re.compile(
    r"^(?:Resistor|Capacitor|Inductor|Diode|LED|Crystal|Connector"
    r"|Button_Switch|Relay|Fuse|Transformer|Sensor)_"
    r"(?:SMD|THT|Castellated)?:?"
)
_FP_SUFFIX_RE = re.compile(r"_(?:Pad[\d.x]+mm(?:_HandSolder)?|HandSolder|DWS|Metric)$")
_FP_METRIC_SUFFIX_RE = re.compile(r"_\d{4}Metric$")

_FP_NAMED_PKG_RE = re.compile(
    r"(?i)\b(SOT[\s-]?(?:23|89|223|323|363|523|363)"
    r"(?:[\s-]\d+)?|"
    r"TO[\s-]?(?:92|220|252|263|247|3P)|"
    r"(?:T|S|VS)?SOP[\s-]?\d+|"
    r"SOIC[\s-]?\d+|"
    r"QFP[\s-]?\d+|"
    r"QFN[\s-]?\d+|"
    r"LQFP[\s-]?\d+|"
    r"TQFP[\s-]?\d+|"
    r"BGA[\s-]?\d+|"
    r"DIP[\s-]?\d+|"
    r"SIP[\s-]?\d+|"
    r"PLCC[\s-]?\d+|"
    r"LGA[\s-]?\d+|"
    r"SC[\s-]?70)\b"
)

_FP_KICAD_SIZE_RE = re.compile(r"[A-Z]_(\d{4})_\d{4}")
_FP_TYPED_SIZE_RE = re.compile(r"^[RCLDF](\d{3,4})$", re.IGNORECASE)
_FP_BARE_IMPERIAL_RE = re.compile(r"^(\d{4})$")
_FP_SHORT_IMPERIAL_RE = re.compile(r"^(\d{3})$")
_FP_IMPERIAL_IN_TEXT_RE = re.compile(r"\b(\d{4})\s*\(")

_SMD_SIZES: frozenset[str] = frozenset(
    {
        "0201",
        "0402",
        "0603",
        "0805",
        "1206",
        "1210",
        "1812",
        "2010",
        "2012",
        "2512",
        "3216",
        "3225",
        "4532",
        "5025",
    }
)

_SMD_PACKAGES: frozenset[str] = frozenset(
    {
        "sot",
        "soic",
        "ssop",
        "tssop",
        "msop",
        "vsop",
        "qfp",
        "lqfp",
        "tqfp",
        "qfn",
        "dfn",
        "bga",
        "lga",
        "plcc",
        "sc70",
        "sop",
        "son",
        "wlcsp",
    }
)

_THT_PACKAGES: frozenset[str] = frozenset(
    {
        "dip",
        "sip",
        "to-92",
        "to-220",
        "to-247",
        "to-252",
        "to-263",
        "to-3p",
    }
)

# Canonical forms for named packages.  Keys are uppercased with all
# whitespace/hyphens removed so that "SOT23", "SOT-23", "SOT 23" all
# resolve to the same canonical "SOT-23".
_PKG_CANONICAL: dict[str, str] = {
    "SOT23": "SOT-23", "SOT233": "SOT-23-3",
    "SOT234": "SOT-23-4", "SOT235": "SOT-23-5",
    "SOT236": "SOT-23-6",
    "SOT89": "SOT-89", "SOT223": "SOT-223",
    "SOT323": "SOT-323", "SOT363": "SOT-363",
    "SOT523": "SOT-523",
    "SC70": "SC-70",
    "TO92": "TO-92", "TO220": "TO-220",
    "TO252": "TO-252", "TO263": "TO-263",
    "TO247": "TO-247", "TO3P": "TO-3P",
}

# Regex to insert a hyphen between a known package family prefix and
# the pin/size number when no separator exists.  Covers families whose
# names end with letters immediately followed by digits.
_PKG_HYPHEN_RE = re.compile(
    r"^(SOT|SC|TO|DIP|SIP|QFP|QFN|BGA|LGA|PLCC"
    r"|LQFP|TQFP|SOIC|SOP|SSOP|TSSOP|MSOP|VSOP)(\d)"
)


def _canonicalize_package(raw_match: str) -> str:
    """Normalize a named package match to a canonical hyphenated form.

    Handles "SOT23" -> "SOT-23", "SOT 23-5" -> "SOT-23-5", etc.

    Args:
        raw_match: The raw regex match group from _FP_NAMED_PKG_RE.

    Returns:
        Canonical uppercased package code with consistent hyphens.
    """
    pkg = raw_match.upper().strip()
    # Build a lookup key by stripping all whitespace and hyphens
    key = re.sub(r"[\s-]+", "", pkg)
    canonical = _PKG_CANONICAL.get(key)
    if canonical is not None:
        return canonical
    # Collapse whitespace to hyphen first
    pkg = re.sub(r"\s+", "-", pkg)
    # Insert hyphen between family prefix and digits if missing
    pkg = _PKG_HYPHEN_RE.sub(r"\1-\2", pkg)
    return pkg


# ── Value Extraction ─────────────────────────────────────────────

_SI_MULT: dict[str, float] = {
    "p": 1e-12,
    "n": 1e-9,
    "u": 1e-6,
    "m": 1e-3,
    "k": 1e3,
    "meg": 1e6,
    "g": 1e9,
}

_UNIT_MAP: dict[str, str] = {
    "ohm": "ohm",
    "r": "ohm",
    "f": "F",
    "farad": "F",
    "h": "H",
    "henry": "H",
    "v": "V",
    "volt": "V",
    "a": "A",
    "amp": "A",
    "hz": "Hz",
    "hertz": "Hz",
}

# "10kohm", "100nf", "4.7uf", "220ohm", "1mh"
_VALUE_STANDARD_RE = re.compile(
    r"^(\d+(?:\.\d+)?)\s*"
    r"(p|n|u|m|k|meg|g)?"
    r"(ohm|f|h|v|a|hz)\b",
    re.IGNORECASE,
)

# R-notation: "4k7" -> 4.7k, "2u2" -> 2.2u
_VALUE_R_NOTATION_RE = re.compile(
    r"^(\d+)(k|m|meg|u|n|p|r)(\d+)$",
    re.IGNORECASE,
)

# Bare value with multiplier only: "10k", "4.7k", "100"
_VALUE_BARE_MULT_RE = re.compile(
    r"^(\d+(?:\.\d+)?)\s*(k|m|meg)$",
    re.IGNORECASE,
)


# ── Public Functions ─────────────────────────────────────────────


def classify_component(
    reference: str | None,
    component_normalized: str | None,
    footprint: str | None,
) -> str | None:
    """Classify a BOM component into a taxonomy category.

    Uses a three-signal cascade: reference designator (highest
    confidence), component name keywords, then footprint hints.

    Args:
        reference: Component designator (e.g. "R1", "U3", "SW1").
        component_normalized: Lowercased normalized component name.
        footprint: Raw footprint string from EDA tool.

    Returns:
        Category string or None if unclassifiable.
    """
    # Signal 1: reference designator
    if reference:
        first_ref = reference.split(",")[0].strip()
        match = _REFDES_RE.match(first_ref)
        if match:
            prefix = match.group(1).lower()
            if len(prefix) >= 2 and prefix[:2] in _REFDES_TWO_LETTER:
                return _REFDES_TWO_LETTER[prefix[:2]]
            if prefix[0] in _REFDES_ONE_LETTER:
                return _REFDES_ONE_LETTER[prefix[0]]

    # Signal 2: component name keywords
    if component_normalized:
        for pattern, category in _NAME_RULES:
            if pattern.search(component_normalized):
                return category

    # Signal 3: footprint hints
    if footprint:
        for pattern, category in _FOOTPRINT_CATEGORY:
            if pattern.search(footprint):
                return category

    return None


def canonicalize_manufacturer(
    manufacturer: str | None,
) -> tuple[str | None, int | None]:
    """Canonicalize a manufacturer name and flag distributors.

    Args:
        manufacturer: Raw manufacturer string from BOM.

    Returns:
        Tuple of (canonical_name, is_distributor). Both None if
        input is garbage/empty. is_distributor is 1 for distributors,
        0 for manufacturers, None for unmapped pass-through values.
    """
    if manufacturer is None:
        return None, None

    cleaned = manufacturer.strip()
    if not cleaned:
        return None, None

    lookup = _CHINESE_PAREN_RE.sub("", cleaned).strip().lower()
    if lookup in _GARBAGE_MFR:
        return None, None

    entry = _MFR_MAP.get(lookup)
    if entry is not None:
        return entry[0], 1 if entry[1] else 0

    return cleaned.title(), None


def normalize_footprint(
    footprint: str | None,
) -> tuple[str | None, str | None]:
    """Normalize a footprint string to a standard package code.

    Args:
        footprint: Raw footprint string from EDA tool.

    Returns:
        Tuple of (normalized_code, mount_type). mount_type is
        "smd", "tht", or "other". Both None if unparseable.
    """
    if not footprint or footprint.strip() == "":
        return None, None

    raw = footprint.strip()

    # Strip EDA library prefix (keep result for KiCad match)
    prefix_stripped = _FP_EDA_PREFIX_RE.sub("", raw)

    # KiCad-style must run before metric suffix stripping:
    # "R_0603_1608Metric" needs both size groups intact.
    kicad = _FP_KICAD_SIZE_RE.search(prefix_stripped)
    if kicad:
        code = kicad.group(1)
        return code, "smd" if code in _SMD_SIZES else "other"

    # Strip metric/pad suffixes for remaining checks
    stripped = _FP_SUFFIX_RE.sub("", prefix_stripped)
    stripped = _FP_METRIC_SUFFIX_RE.sub("", stripped)

    # Named packages (SOT-23, DIP-8, QFN-32, etc.)
    named = _FP_NAMED_PKG_RE.search(stripped)
    if named:
        pkg = _canonicalize_package(named.group(1))
        mount = _classify_mount(pkg)
        return pkg, mount

    # Type-prefixed: R0603, C0402
    typed = _FP_TYPED_SIZE_RE.match(stripped)
    if typed:
        code = typed.group(1)
        if len(code) == 3:
            code = f"0{code}"
        return code, "smd" if code in _SMD_SIZES else "other"

    # Bare 4-digit imperial: 0603, 0805
    bare = _FP_BARE_IMPERIAL_RE.match(stripped)
    if bare:
        code = bare.group(1)
        return code, "smd" if code in _SMD_SIZES else "other"

    # 3-digit shorthand: 603 -> 0603
    short = _FP_SHORT_IMPERIAL_RE.match(stripped)
    if short:
        code = f"0{short.group(1)}"
        if code in _SMD_SIZES:
            return code, "smd"

    # Imperial in descriptive text: "0603 (1608 metric)"
    text_match = _FP_IMPERIAL_IN_TEXT_RE.search(stripped)
    if text_match:
        code = text_match.group(1)
        return code, "smd" if code in _SMD_SIZES else "other"

    return None, None


def extract_value(
    component_normalized: str | None,
    category: str | None,
) -> tuple[float | None, str | None]:
    """Parse an electrical value from a normalized component name.

    Args:
        component_normalized: Lowercased normalized component name.
        category: Component category (used for disambiguation).

    Returns:
        Tuple of (value_in_base_si_units, unit_string). Both None
        if no value could be parsed.
    """
    if not component_normalized:
        return None, None

    text = component_normalized.strip()

    # Standard notation: "10kohm", "100nf", "4.7uf"
    m = _VALUE_STANDARD_RE.match(text)
    if m:
        num = float(m.group(1))
        mult_key = (m.group(2) or "").lower()
        unit_key = m.group(3).lower()
        mult = _SI_MULT.get(mult_key, 1.0)
        unit = _UNIT_MAP.get(unit_key)
        if unit is not None:
            return num * mult, unit

    # R-notation: "4k7" -> 4700, "2u2" -> 2.2e-6
    m = _VALUE_R_NOTATION_RE.match(text)
    if m:
        whole = m.group(1)
        sep = m.group(2).lower()
        frac = m.group(3)
        num = float(f"{whole}.{frac}")
        if sep == "r":
            return num, "ohm"
        mult = _SI_MULT.get(sep, 1.0)
        unit = _infer_unit_from_multiplier(sep, category)
        if unit is not None:
            return num * mult, unit

    # Bare multiplier: "10k", "100" (only for resistors/capacitors)
    m = _VALUE_BARE_MULT_RE.match(text)
    if m and category == "resistor":
        num = float(m.group(1))
        mult_key = m.group(2).lower()
        mult = _SI_MULT.get(mult_key, 1.0)
        return num * mult, "ohm"

    return None, None


def enrich_bom_components(db_path: Path = DB_PATH) -> int:
    """Add normalized columns to bom_components and populate them.

    Safe to call multiple times; adds columns only if missing.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Number of rows processed.
    """
    conn = open_connection(db_path)

    _ensure_columns(conn)

    rows = conn.execute(
        "SELECT id, reference, component_normalized, footprint, "
        "manufacturer FROM bom_components"
    ).fetchall()

    updates: list[
        tuple[
            str | None,
            str | None,
            int | None,
            str | None,
            str | None,
            float | None,
            str | None,
            int,
        ]
    ] = []

    for row_id, ref, comp_norm, fp, mfr in rows:
        category = classify_component(ref, comp_norm, fp)
        canon_mfr, is_dist = canonicalize_manufacturer(mfr)
        fp_norm, mount = normalize_footprint(fp)
        val_num, val_unit = extract_value(comp_norm, category)

        updates.append(
            (
                category,
                canon_mfr,
                is_dist,
                fp_norm,
                mount,
                val_num,
                val_unit,
                row_id,
            )
        )

    conn.executemany(
        "UPDATE bom_components SET "
        "component_category = ?, "
        "manufacturer_canonical = ?, "
        "manufacturer_is_distributor = ?, "
        "footprint_normalized = ?, "
        "footprint_mount_type = ?, "
        "value_numeric = ?, "
        "value_unit = ? "
        "WHERE id = ?",
        updates,
    )
    conn.commit()

    _log_summary(conn, len(updates))
    conn.close()
    return len(updates)


# ── Private Helpers ──────────────────────────────────────────────


def _classify_mount(package: str) -> str:
    """Determine mount type from a normalized package name.

    Args:
        package: Uppercased package code (e.g. "SOT-23", "DIP-8").

    Returns:
        "smd", "tht", or "other".
    """
    pkg_lower = package.lower().split("-")[0]
    if pkg_lower in _SMD_PACKAGES:
        return "smd"
    if pkg_lower in _THT_PACKAGES or package.lower() in _THT_PACKAGES:
        return "tht"
    return "other"


def _infer_unit_from_multiplier(
    mult_key: str,
    category: str | None,
) -> str | None:
    """Infer SI unit from multiplier key and component category.

    Args:
        mult_key: Lowercase multiplier character (k, m, u, n, p).
        category: Component category for disambiguation.

    Returns:
        SI unit string or None if ambiguous.
    """
    if mult_key == "k" or mult_key == "meg":
        return "ohm"
    if mult_key in ("u", "n", "p"):
        if category == "capacitor":
            return "F"
        if category == "inductor":
            return "H"
        return "F"
    if mult_key == "m":
        if category == "inductor":
            return "H"
        if category == "resistor":
            return "ohm"
        return None
    return None


def _ensure_columns(conn: sqlite3.Connection) -> None:  # noqa: F821
    """Add normalized columns and indexes if they don't exist.

    Args:
        conn: Open SQLite connection.
    """
    existing = {
        r[1] for r in conn.execute("PRAGMA table_info(bom_components)").fetchall()
    }

    new_cols: list[tuple[str, str]] = [
        ("component_category", "TEXT"),
        ("manufacturer_canonical", "TEXT"),
        ("manufacturer_is_distributor", "INTEGER"),
        ("footprint_normalized", "TEXT"),
        ("footprint_mount_type", "TEXT"),
        ("value_numeric", "REAL"),
        ("value_unit", "TEXT"),
    ]

    for col_name, col_type in new_cols:
        if col_name not in existing:
            conn.execute(f"ALTER TABLE bom_components ADD COLUMN {col_name} {col_type}")

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_bom_category "
        "ON bom_components(component_category)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_bom_mfr_canon "
        "ON bom_components(manufacturer_canonical)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_bom_fp_norm "
        "ON bom_components(footprint_normalized)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_bom_fp_mount "
        "ON bom_components(footprint_mount_type)"
    )


def _log_summary(conn: sqlite3.Connection, total: int) -> None:  # noqa: F821
    """Log enrichment summary statistics.

    Args:
        conn: Open SQLite connection.
        total: Total rows processed.
    """
    cats = conn.execute(
        "SELECT COUNT(*) FROM bom_components WHERE component_category IS NOT NULL"
    ).fetchone()
    mfrs = conn.execute(
        "SELECT COUNT(*) FROM bom_components WHERE manufacturer_canonical IS NOT NULL"
    ).fetchone()
    fps = conn.execute(
        "SELECT COUNT(*) FROM bom_components WHERE footprint_normalized IS NOT NULL"
    ).fetchone()
    vals = conn.execute(
        "SELECT COUNT(*) FROM bom_components WHERE value_numeric IS NOT NULL"
    ).fetchone()

    logger.info(
        "BOM enrichment: %d rows processed. "
        "Categories: %d, Manufacturers: %d, "
        "Footprints: %d, Values: %d",
        total,
        cats[0] if cats else 0,
        mfrs[0] if mfrs else 0,
        fps[0] if fps else 0,
        vals[0] if vals else 0,
    )


if __name__ == "__main__":
    result = enrich_bom_components()
    print(f"Enriched {result} BOM component rows.")
