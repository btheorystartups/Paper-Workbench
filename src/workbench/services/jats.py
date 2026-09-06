"""JATS validation. Ships a DTD for the JATS structural subset this workbench emits and
validates output against it with lxml. This is real DTD validation — honestly scoped to
the element subset we produce, not the full JATS 1.3 DTD (point WB at the official DTD via
validate_jats(dtd_path=...) for that). Without lxml, falls back to a well-formedness check.
"""

from dataclasses import dataclass, field

# DTD covering exactly the elements export_service._jats_xml emits. Kept in sync with it.
JATS_SUBSET_DTD = """
<!ELEMENT article (front, body, back?)>
<!ATTLIST article article-type CDATA #IMPLIED
                  xmlns:xlink CDATA #IMPLIED>
<!ELEMENT front (article-meta)>
<!ELEMENT article-meta (title-group, contrib-group?)>
<!ELEMENT title-group (article-title)>
<!ELEMENT article-title (#PCDATA)>
<!ELEMENT contrib-group (contrib*)>
<!ELEMENT contrib (name, role*)>
<!ATTLIST contrib contrib-type CDATA #IMPLIED>
<!ELEMENT name (surname, given-names?)>
<!ELEMENT surname (#PCDATA)>
<!ELEMENT given-names (#PCDATA)>
<!ELEMENT role (#PCDATA)>
<!ATTLIST role vocab CDATA #IMPLIED
               vocab-identifier CDATA #IMPLIED>
<!ELEMENT body (sec*)>
<!ELEMENT sec (title, p*)>
<!ATTLIST sec id CDATA #IMPLIED>
<!ELEMENT title (#PCDATA)>
<!ELEMENT p (#PCDATA)>
<!ELEMENT back (ref-list)>
<!ELEMENT ref-list (ref*)>
<!ELEMENT ref (mixed-citation)>
<!ATTLIST ref id CDATA #IMPLIED>
<!ELEMENT mixed-citation (#PCDATA)>
"""


@dataclass
class ValidationResult:
    well_formed: bool
    valid: bool | None  # None when no DTD validation was possible
    method: str  # "dtd-subset" | "dtd-file" | "well-formed-only"
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"well_formed": self.well_formed, "valid": self.valid,
                "method": self.method, "errors": self.errors}


def _lxml_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("lxml") is not None


def validate_jats(xml_text: str, *, dtd_path: str | None = None) -> ValidationResult:
    """Validate a JATS document. Uses the bundled subset DTD by default, or a full
    JATS DTD file if `dtd_path` is given. Falls back to a well-formedness check when
    lxml is not installed."""
    if not _lxml_available():
        return _well_formed_only(xml_text)

    from lxml import etree

    try:
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        doc = etree.fromstring(xml_text.encode("utf-8"), parser)
    except etree.XMLSyntaxError as exc:
        return ValidationResult(well_formed=False, valid=False, method="dtd-subset",
                                errors=[f"not well-formed: {exc}"])

    if dtd_path:
        dtd = etree.DTD(dtd_path)
        method = "dtd-file"
    else:
        from io import StringIO

        dtd = etree.DTD(StringIO(JATS_SUBSET_DTD))
        method = "dtd-subset"

    valid = dtd.validate(doc)
    errors = [str(e) for e in dtd.error_log.filter_from_errors()]
    return ValidationResult(well_formed=True, valid=valid, method=method, errors=errors)


def _well_formed_only(xml_text: str) -> ValidationResult:
    import xml.etree.ElementTree as ET

    try:
        ET.fromstring(xml_text)
        return ValidationResult(well_formed=True, valid=None, method="well-formed-only")
    except ET.ParseError as exc:
        return ValidationResult(well_formed=False, valid=None, method="well-formed-only",
                                errors=[str(exc)])
