"""
hl7apy-backed message model with resilient ER7 fallback parsing and
Z-segment profile awareness.

The model is intentionally simple: a list of ParsedSegment, each with a list of
ParsedField, each with a list of ParsedRepetition, each with a list of
ParsedComponent, each with a list of ParsedSubcomponent. The UI layer walks
these directly.

hl7apy is used for typed field/component metadata on standard segments. For
unknown or Z-segments, we consult app.zprofiles; anything still unidentified
falls back to generic labels (Field N [ST]).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from hl7apy.consts import VALIDATION_LEVEL
from hl7apy.core import Message as HL7Message
from hl7apy.exceptions import HL7apyException
from hl7apy.parser import parse_message as hl7apy_parse

import importlib
import importlib.util as _ilu
import os as _os

_zprofiles_path = _os.path.join(_os.path.dirname(__file__), "zprofiles", "zprofiles")
zprofiles = (
    importlib.import_module(".zprofiles.zprofiles", package=__package__)
    if _ilu.find_spec(".zprofiles.zprofiles", package=__package__) is not None
    and _os.path.isdir(_zprofiles_path)
    else None
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ParsedSubcomponent:
    position: int
    name: str
    datatype: str
    value: str


@dataclass
class ParsedComponent:
    position: int
    name: str
    datatype: str
    raw: str
    subcomponents: List[ParsedSubcomponent] = field(default_factory=list)


@dataclass
class ParsedRepetition:
    index: int
    raw: str
    components: List[ParsedComponent] = field(default_factory=list)


@dataclass
class ParsedField:
    position: int
    name: str
    datatype: str
    raw: str
    repetitions: List[ParsedRepetition] = field(default_factory=list)


@dataclass
class ParsedSegment:
    name: str
    occurrence: int
    raw: str
    is_z_segment: bool
    fields: List[ParsedField] = field(default_factory=list)

    @property
    def display(self) -> str:
        if self.occurrence == 0:
            return self.name
        return f"{self.name}[{self.occurrence}]"


@dataclass
class ParsedMessage:
    raw: str
    encoding_chars: "EncodingChars"
    message_type: str
    trigger_event: str
    version: str
    segments: List[ParsedSegment] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Encoding characters
# ---------------------------------------------------------------------------


@dataclass
class EncodingChars:
    field_sep: str = "|"
    component_sep: str = "^"
    repetition_sep: str = "~"
    escape_char: str = "\\"
    subcomponent_sep: str = "&"

    @classmethod
    def from_msh(cls, raw: str) -> "EncodingChars":
        """Parse MSH-1 + MSH-2 from a raw message. Very tolerant."""
        if not raw or len(raw) < 8 or not raw.startswith("MSH"):
            return cls()
        fs = raw[3]
        encoding = raw[4:8]
        try:
            return cls(
                field_sep=fs,
                component_sep=encoding[0],
                repetition_sep=encoding[1],
                escape_char=encoding[2],
                subcomponent_sep=encoding[3],
            )
        except IndexError:
            return cls(field_sep=fs)


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def normalize_er7(raw: str) -> str:
    """Normalize line endings so hl7apy always sees \\r between segments."""
    if raw is None:
        return ""
    # Strip BOM
    if raw.startswith("\ufeff"):
        raw = raw[1:]
    # Normalize any combo of CRLF/LF/CR to CR
    normalized = raw.replace("\r\n", "\r").replace("\n", "\r")
    # Collapse blank trailing segments
    while normalized.endswith("\r"):
        normalized = normalized[:-1]
    return normalized


# ---------------------------------------------------------------------------
# hl7apy-backed field metadata lookup
# ---------------------------------------------------------------------------


def _field_metadata(hl7apy_field) -> tuple[str, str]:
    """Extract (name, datatype) from an hl7apy Field/Component, resilient to
    missing metadata on unknown segments."""
    name = getattr(hl7apy_field, "long_name", None) or getattr(hl7apy_field, "name", "")
    dt = ""
    try:
        dt = hl7apy_field.datatype or ""
    except Exception:
        dt = ""
    return (str(name) if name else "", str(dt) if dt else "")


# ---------------------------------------------------------------------------
# Top-level parser
# ---------------------------------------------------------------------------


def parse(raw: str) -> ParsedMessage:
    """Parse ER7 text into a ParsedMessage. Never raises on malformed input —
    unrecoverable errors are captured in ``warnings``."""
    normalized = normalize_er7(raw)
    encoding = EncodingChars.from_msh(normalized)

    msg_type, trigger, version = _extract_header_info(normalized, encoding)

    parsed = ParsedMessage(
        raw=normalized,
        encoding_chars=encoding,
        message_type=msg_type,
        trigger_event=trigger,
        version=version,
    )

    # First, try hl7apy for typed access. If that fails we fall back entirely
    # to ER7 string splitting.
    hl7apy_msg: Optional[HL7Message] = None
    if normalized.startswith("MSH"):
        try:
            hl7apy_msg = hl7apy_parse(
                normalized,
                validation_level=VALIDATION_LEVEL.TOLERANT,
                find_groups=False,
            )
        except HL7apyException as e:
            parsed.warnings.append(f"hl7apy parse failed: {e}; using ER7 fallback.")
        except Exception as e:  # noqa: BLE001 — hl7apy surfaces a variety of errors
            parsed.warnings.append(f"Unexpected parse error: {e}; using ER7 fallback.")

    segment_lines = [s for s in normalized.split("\r") if s]
    occurrence_counter: dict[str, int] = {}

    for idx, seg_raw in enumerate(segment_lines):
        seg_name = seg_raw[:3] if len(seg_raw) >= 3 else seg_raw
        occ = occurrence_counter.get(seg_name, 0)
        occurrence_counter[seg_name] = occ + 1

        hl7apy_seg = None
        if hl7apy_msg is not None:
            hl7apy_seg = _locate_hl7apy_segment(hl7apy_msg, seg_name, occ)

        parsed.segments.append(
            _build_segment(seg_raw, seg_name, occ, encoding, hl7apy_seg)
        )

    return parsed


def _extract_header_info(
    raw: str, enc: EncodingChars
) -> tuple[str, str, str]:
    """Pull message type / trigger event / version directly from MSH without
    relying on hl7apy (so we still populate them when parsing fails)."""
    if not raw.startswith("MSH"):
        return ("", "", "")
    first_seg = raw.split("\r", 1)[0]
    fields = first_seg.split(enc.field_sep)
    # MSH: MSH-1 is field_sep itself, so fields[1] corresponds to MSH-2,
    # fields[2] corresponds to MSH-3, etc.
    msg_type = trigger = version = ""
    if len(fields) > 8:
        type_field = fields[8]  # MSH-9
        parts = type_field.split(enc.component_sep)
        if parts:
            msg_type = parts[0]
        if len(parts) > 1:
            trigger = parts[1]
    if len(fields) > 11:
        version = fields[11]  # MSH-12
    return msg_type, trigger, version


def _locate_hl7apy_segment(msg: HL7Message, name: str, occurrence: int):
    """Return the Nth occurrence of the named segment in an hl7apy message
    tree, recursing into groups if necessary."""
    seen = [0]

    def walk(node):
        for child in getattr(node, "children", []):
            if getattr(child, "name", "") == name:
                if seen[0] == occurrence:
                    return child
                seen[0] += 1
            if hasattr(child, "children") and child.children and child.name != name:
                result = walk(child)
                if result is not None:
                    return result
        return None

    return walk(msg)


# ---------------------------------------------------------------------------
# Segment / field / component / sub-component builders
# ---------------------------------------------------------------------------


def _atomic_field(position: int, name: str, datatype: str, value: str) -> ParsedField:
    """Build a field whose value is displayed verbatim — no repetition,
    component, or sub-component splitting. Used for MSH-1 and MSH-2."""
    return ParsedField(
        position=position,
        name=name,
        datatype=datatype,
        raw=value,
        repetitions=[
            ParsedRepetition(
                index=0,
                raw=value,
                components=[
                    ParsedComponent(
                        position=1,
                        name=name,
                        datatype=datatype,
                        raw=value,
                        subcomponents=[
                            ParsedSubcomponent(
                                position=1,
                                name="Sub-component 1",
                                datatype="ST",
                                value=value,
                            )
                        ],
                    )
                ],
            )
        ],
    )


def _build_segment(
    raw_seg: str,
    name: str,
    occurrence: int,
    enc: EncodingChars,
    hl7apy_seg,
) -> ParsedSegment:
    is_z = len(name) == 3 and name.startswith("Z")
    segment = ParsedSegment(
        name=name,
        occurrence=occurrence,
        raw=raw_seg,
        is_z_segment=is_z,
    )

    fields_raw = raw_seg.split(enc.field_sep)
    # MSH-1 (field separator) and MSH-2 (encoding characters) are atomic by
    # HL7 spec — neither is subject to repetition/component/sub-component
    # parsing because their value *is* the delimiter declaration.
    if name == "MSH":
        segment.fields.append(_atomic_field(1, "Field Separator", "ST", enc.field_sep))
        enc_raw = fields_raw[1] if len(fields_raw) > 1 else ""
        msh2_name, msh2_dt = _resolve_field_metadata("MSH", 2, hl7apy_seg)
        segment.fields.append(
            _atomic_field(2, msh2_name or "Encoding Characters", msh2_dt or "ST", enc_raw)
        )
        start_pos = 3
        data_fields = fields_raw[2:]
    else:
        start_pos = 1
        data_fields = fields_raw[1:]

    for i, field_raw in enumerate(data_fields):
        position = start_pos + i
        name_dt = _resolve_field_metadata(name, position, hl7apy_seg)
        segment.fields.append(
            _build_field(field_raw, position, name_dt, enc, name)
        )

    return segment


def _resolve_field_metadata(
    seg_name: str, position: int, hl7apy_seg
) -> tuple[str, str]:
    """Resolve field (name, datatype) via Z-profile first for Z-segments
    (hl7apy returns placeholder metadata for them), then hl7apy for known
    standard segments, else generic fallback."""
    if seg_name.startswith("Z") and zprofiles is not None:
        return zprofiles.field_label(seg_name, position)
    if hl7apy_seg is not None:
        try:
            attr = f"{seg_name.lower()}_{position}"
            child = getattr(hl7apy_seg, attr, None)
            if child is not None:
                name, dt = _field_metadata(child)
                if name:
                    return name, dt or "ST"
        except Exception:
            pass
    return f"Field {position}", "ST"


def _build_field(
    raw_field: str,
    position: int,
    name_dt: tuple[str, str],
    enc: EncodingChars,
    seg_name: str,
) -> ParsedField:
    name, datatype = name_dt
    f = ParsedField(position=position, name=name, datatype=datatype, raw=raw_field)
    reps = raw_field.split(enc.repetition_sep) if raw_field else [""]
    for rep_idx, rep_raw in enumerate(reps):
        f.repetitions.append(_build_repetition(rep_raw, rep_idx, seg_name, position, enc))
    return f


def _build_repetition(
    raw_rep: str, index: int, seg_name: str, field_pos: int, enc: EncodingChars
) -> ParsedRepetition:
    r = ParsedRepetition(index=index, raw=raw_rep)
    comps = raw_rep.split(enc.component_sep) if raw_rep else [""]
    for ci, comp_raw in enumerate(comps):
        r.components.append(
            _build_component(comp_raw, ci + 1, seg_name, field_pos, enc)
        )
    return r


def _build_component(
    raw_comp: str,
    position: int,
    seg_name: str,
    field_pos: int,
    enc: EncodingChars,
) -> ParsedComponent:
    # Component names from Z-profile if applicable; otherwise generic
    if seg_name.startswith("Z") and zprofiles is not None:
        name, dt = zprofiles.component_label(seg_name, field_pos, position)
    else:
        name, dt = f"Component {position}", "ST"
    c = ParsedComponent(position=position, name=name, datatype=dt, raw=raw_comp)
    if raw_comp and enc.subcomponent_sep in raw_comp:
        subs = raw_comp.split(enc.subcomponent_sep)
        for si, sub_raw in enumerate(subs):
            c.subcomponents.append(
                ParsedSubcomponent(
                    position=si + 1,
                    name=f"Sub-component {si + 1}",
                    datatype="ST",
                    value=sub_raw,
                )
            )
    else:
        c.subcomponents.append(
            ParsedSubcomponent(
                position=1, name="Sub-component 1", datatype="ST", value=raw_comp
            )
        )
    return c
