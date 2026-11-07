"""LAB-ONLY XFA datasets proof-of-concept on synthetic PDFs.

NOT approved for actual IRCC forms. This isolates the XML datasets technique
from official Adobe JavaScript, usage rights, signature and barcode validation.
No AcroForm fallback, XFA removal, flattening, or barcode manipulation.
"""
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from typing import Mapping
import xml.etree.ElementTree as ET

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, StreamObject

from app.xfa_probe import MAX_XFA_PACKET, XfaProbeError, _local, _xml


class XfaDatasetBlocked(ValueError):
    pass


@dataclass(frozen=True)
class LabXfaApproval:
    original_sha256: str
    approved_paths: frozenset[tuple[str, ...]]
    synthetic_only: bool = False


def _packet_stream(acro):
    xfa = acro.get("/XFA")
    if xfa is None:
        raise XfaDatasetBlocked("No XFA datasets present")
    entry = xfa.get_object() if hasattr(xfa, "get_object") else xfa
    if not isinstance(entry, ArrayObject) or len(entry) % 2 or not entry:
        raise XfaDatasetBlocked("Lab adapter requires named XFA packet array")
    matches = []
    for i in range(0, len(entry), 2):
        if str(entry[i]) == "datasets":
            item = entry[i+1].get_object()
            if not isinstance(item, StreamObject):
                raise XfaDatasetBlocked("Datasets is not a PDF stream")
            matches.append((entry, i+1, item))
    if len(matches) != 1:
        raise XfaDatasetBlocked("Exactly one XFA datasets packet is required")
    return matches[0]


def _locate(root, path):
    if not path or any(not name or name in (".", "..") for name in path):
        raise XfaDatasetBlocked("Empty or invalid XFA path")
    # Start under xfa:datasets/xfa:data. Do not construct new elements.
    data_nodes = [child for child in root if _local(child.tag) == "data"]
    if len(data_nodes) != 1:
        raise XfaDatasetBlocked("Datasets must contain exactly one data node")
    current = data_nodes[0]
    for name in path:
        matches = [child for child in current if _local(child.tag) == name]
        if len(matches) != 1:
            raise XfaDatasetBlocked("Path is absent or ambiguous (repeated groups require an approved mapper)")
        current = matches[0]
    if len(current):
        raise XfaDatasetBlocked("Cannot overwrite an XFA parent node")
    return current


def fill_synthetic_xfa_dataset(pdf: bytes, values: Mapping[tuple[str, ...], str],
                               approval: LabXfaApproval) -> bytes:
    if not approval.synthetic_only:
        raise XfaDatasetBlocked("This writer is only authorized for synthetic test fixtures")
    if sha256(pdf).hexdigest() != approval.original_sha256:
        raise XfaDatasetBlocked("Template checksum mismatch")
    if (not values or set(values) != approval.approved_paths or
            any(not isinstance(v, str) or not v or len(v) > 600 for v in values.values())):
        raise XfaDatasetBlocked("Only exact approved synthetic paths and text values allowed")
    try:
        reader = PdfReader(BytesIO(pdf), strict=True)
        if reader.is_encrypted:
            raise XfaDatasetBlocked("Encrypted forms unsupported")
        if "/Perms" in reader.trailer["/Root"]:
            raise XfaDatasetBlocked("Signed or rights-managed PDF cannot be rewritten")
        raw_acro = reader.trailer["/Root"].get("/AcroForm")
        if not raw_acro:
            raise XfaDatasetBlocked("Missing form dictionary")
        _, _, source = _packet_stream(raw_acro.get_object())
        root = _xml(source.get_data())
        if _local(root.tag) != "datasets":
            raise XfaDatasetBlocked("Expected XFA datasets packet")
        for path, value in values.items():
            _locate(root, path).text = value
        new_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        if len(new_xml) > MAX_XFA_PACKET:
            raise XfaDatasetBlocked("Resulting datasets exceeds safe size")
        writer = PdfWriter()
        writer.append(reader)
        acro = writer._root_object["/AcroForm"].get_object()
        entry, index, _ = _packet_stream(acro)
        replacement = DecodedStreamObject()
        replacement.set_data(new_xml)
        entry[index] = writer._add_object(replacement)
        buffer = BytesIO()
        writer.write(buffer)
        output = buffer.getvalue()
        # Independent PDF and XML read-back of each exact target.
        result = PdfReader(BytesIO(output), strict=True)
        _, _, saved = _packet_stream(result.trailer["/Root"]["/AcroForm"].get_object())
        saved_root = _xml(saved.get_data())
        for path, expected in values.items():
            if _locate(saved_root, path).text != expected:
                raise XfaDatasetBlocked("Written XFA values failed independent read-back")
        return output
    except XfaDatasetBlocked:
        raise
    except (XfaProbeError, ET.ParseError, ValueError, TypeError, KeyError) as exc:
        raise XfaDatasetBlocked("XFA layout cannot be safely modified") from exc
    except Exception as exc:
        raise XfaDatasetBlocked("XFA PDF rewrite failed") from exc
