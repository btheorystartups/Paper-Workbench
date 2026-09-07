"""Offline JATS validation against the official NISO JATS 1.3 distribution.

The bundled default is the unmodified Journal Archiving and Interchange MathML 2
DTD. It is the honest general-purpose choice for Paper-Workbench: unlike the
Publishing and Article Authoring tag sets, it does not require us to invent journal
identifiers, ISSNs, abstracts, or references that may not exist yet. A caller may
still select a stricter local entry-point DTD with ``WB_JATS_DTD_PATH``.
"""

from dataclasses import dataclass, field
from pathlib import Path

JATS_VERSION = "1.3"
JATS_TAG_SET = "Journal Archiving and Interchange"
JATS_MATHML_VERSION = "2.0"
JATS_DISTRIBUTION_URL = (
    "https://public.nlm.nih.gov/projects/jats/archiving/1.3/"
    "JATS-Archiving-1-3-MathML2-DTD.zip"
)
JATS_DISTRIBUTION_SHA256 = (
    "fe9ea21a6d86bcfe245ab00f11006a2863bb50de94edebf24988151a09804e2c"
)
_BUNDLED_DTD = (
    Path(__file__).resolve().parents[1]
    / "schemas"
    / "jats_1_3_archiving"
    / "JATS-archivearticle1-3.dtd"
)


@dataclass
class ValidationResult:
    well_formed: bool
    valid: bool | None  # None only when lxml is unavailable.
    method: str  # "dtd-jats-1.3-archiving" | "dtd-file" | "well-formed-only"
    errors: list[str] = field(default_factory=list)
    schema: str | None = None
    schema_version: str | None = None
    distribution_sha256: str | None = None

    def as_dict(self) -> dict:
        return {
            "well_formed": self.well_formed,
            "valid": self.valid,
            "method": self.method,
            "errors": self.errors,
            "schema": self.schema,
            "schema_version": self.schema_version,
            "distribution_sha256": self.distribution_sha256,
        }


def bundled_jats_dtd_path() -> Path:
    """Return the packaged official JATS 1.3 DTD entry point."""
    return _BUNDLED_DTD


def _lxml_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("lxml") is not None


def validate_jats(xml_text: str, *, dtd_path: str | None = None) -> ValidationResult:
    """Validate JATS XML offline and fail closed when the selected DTD cannot load.

    With no override, validation uses the packaged official NISO JATS 1.3 Archiving
    DTD and its local modules. ``no_network=True`` prevents validation from fetching
    schemas or entities at runtime.
    """
    custom_dtd = bool(dtd_path)
    method = "dtd-file" if custom_dtd else "dtd-jats-1.3-archiving"
    schema = "custom DTD" if custom_dtd else JATS_TAG_SET
    schema_version = None if custom_dtd else JATS_VERSION
    distribution_sha256 = None if custom_dtd else JATS_DISTRIBUTION_SHA256

    if not _lxml_available():
        return _well_formed_only(xml_text)

    from lxml import etree

    try:
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        doc = etree.fromstring(xml_text.encode("utf-8"), parser)
    except etree.XMLSyntaxError as exc:
        return ValidationResult(
            well_formed=False,
            valid=False,
            method=method,
            errors=[f"not well-formed: {exc}"],
            schema=schema,
            schema_version=schema_version,
            distribution_sha256=distribution_sha256,
        )

    path = Path(dtd_path) if custom_dtd else bundled_jats_dtd_path()
    if not path.is_file():
        return ValidationResult(
            well_formed=True,
            valid=False,
            method=method,
            errors=[f"DTD file not found: {path}"],
            schema=schema,
            schema_version=schema_version,
            distribution_sha256=distribution_sha256,
        )
    try:
        dtd = etree.DTD(str(path))
    except (OSError, etree.DTDParseError) as exc:
        return ValidationResult(
            well_formed=True,
            valid=False,
            method=method,
            errors=[f"DTD could not be loaded: {exc}"],
            schema=schema,
            schema_version=schema_version,
            distribution_sha256=distribution_sha256,
        )

    valid = dtd.validate(doc)
    errors = [str(error) for error in dtd.error_log.filter_from_errors()]
    return ValidationResult(
        well_formed=True,
        valid=valid,
        method=method,
        errors=errors,
        schema=schema,
        schema_version=schema_version,
        distribution_sha256=distribution_sha256,
    )


def _well_formed_only(xml_text: str) -> ValidationResult:
    import xml.etree.ElementTree as ET

    try:
        ET.fromstring(xml_text)
        return ValidationResult(
            well_formed=True,
            valid=None,
            method="well-formed-only",
            errors=["lxml is unavailable; official DTD validation did not run"],
        )
    except ET.ParseError as exc:
        return ValidationResult(
            well_formed=False,
            valid=None,
            method="well-formed-only",
            errors=[str(exc)],
        )
