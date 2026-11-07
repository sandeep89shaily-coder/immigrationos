"""Build genuine-template XDP inputs and independently verify trial vendor PDFs.

Research-only. Fixed fictional names; never accepts arbitrary applicant data.
The official IMM5476 blank is fetched transiently by GitHub Actions and must
match the uploaded government PDF's pinned SHA-256 before any output is made.
"""
from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from pypdf import PdfReader
from app.imm5476_official_poc import (
    SOURCE_SHA256, _FIELDS, _find_xfa_packet,
    _parse_xml, _xfa_leaf, SYNTHETIC_VALUES,
)

_KEYS = tuple(SYNTHETIC_VALUES)  # 12 observed fictional fields, never actual client data
_XDP = "http://ns.adobe.com/xdp/"
_XFA = "http://www.xfa.org/schema/xfa-data/1.0/"
ET.register_namespace("xdp", _XDP)
ET.register_namespace("xfa", _XFA)


def _xfa_node(root, path):
    """Navigate a typed XFA path, allowing an intermediate rich-text parent."""
    roots = [e for e in root if e.tag.rsplit("}", 1)[-1] == "data"]
    if len(roots) != 1:
        raise ValueError("XFA data node missing or duplicated")
    current = roots[0]
    for name, index in path:
        matches = [child for child in current
                   if child.tag.rsplit("}", 1)[-1] == name]
        if index >= len(matches):
            raise ValueError("XFA path changed: " + name)
        current = matches[index]
    return current


def checked_blank(blank_path: Path) -> bytes:
    data = blank_path.read_bytes()
    if sha256(data).hexdigest() != SOURCE_SHA256 or len(data) > 12 * 1024 * 1024:
        raise ValueError("Official IMM5476 blank does not match approved SHA-256")
    return data


def prepare(blank: Path, out_dir: Path) -> None:
    checked_blank(blank)
    out_dir.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(blank, strict=True)
    if len(reader.pages) != 4:
        raise ValueError("Official form page count changed")
    original = _find_xfa_packet(reader, "datasets").get_object().get_data()
    for variant in ("scalar", "rich", "appointing-paid-cicc"):
        root = _parse_xml(original)
        for key in _KEYS:
            binding = _FIELDS[key]
            if variant != "rich" and key.endswith("_family"):
                # Preserve all surrounding form data but replace ONLY the
                # special XHTML value node with simple XFA element text.
                node_path = binding.xfa_path[:-3]
                surname = _xfa_node(root, node_path)
                for child in list(surname):
                    surname.remove(child)
                surname.text = SYNTHETIC_VALUES[key]
            else:
                _xfa_leaf(root, binding.xfa_path).text = SYNTHETIC_VALUES[key]
        if variant == "appointing-paid-cicc":
            # The source XFA item labels for option zero are both "1".
            for radio_name in ("RadioButtonList", "compensated"):
                matched = [node for node in root.iter()
                           if node.tag.rsplit("}", 1)[-1] == radio_name]
                if len(matched) != 1 or len(matched[0]) != 0:
                    raise ValueError("Official XFA radio structure changed")
                matched[0].text = "1"
        xdp = ET.Element(f"{{{_XDP}}}xdp")
        xdp.append(root)
        xml = ET.tostring(xdp, encoding="utf-8", xml_declaration=True)
        parsed = _parse_xml(xml)
        if parsed.tag != f"{{{_XDP}}}xdp":
            raise ValueError("Invalid generated XDP envelope")
        for key in _KEYS:
            path = _FIELDS[key].xfa_path
            if variant != "rich" and key.endswith("_family"):
                path = path[:-3]
            node = _xfa_node(parsed[0], path)
            if len(node) != 0 or node.text != SYNTHETIC_VALUES[key]:
                raise ValueError("Incorrect fictional XDP field: " + key)
        (out_dir / f"fictional-{variant}.xdp").write_bytes(xml)
    print("Prepared three genuine-template XDP files, including fictional radio choice; NO PDF modifications")


def verify(blank: Path, filled: Path, report: Path) -> bool:
    original = checked_blank(blank)
    result = {"official_template_pinned": True,
              "output_path": filled.name,
              "adobe_acrobat_tested": False,
              "official_validated": False,
              "submission_ready": False}
    try:
        data = filled.read_bytes()
        if len(data) > 20 * 1024 * 1024 or not data.startswith(b"%PDF-"):
            raise ValueError("Not a reasonable generated PDF")
        result["output_sha256"] = sha256(data).hexdigest()
        result["original_pdf_byte_prefix_preserved"] = data.startswith(original)
        reader = PdfReader(filled, strict=False)
        result["pages"] = len(reader.pages)
        # Qoppa's incremental output can expose a nonstandard /AP dictionary
        # that makes pypdf.get_fields() fail. Do not mistake this parser issue
        # for missing XFA values; independently read widgets via PyMuPDF.
        try:
            reader.get_fields()
            result["pypdf_field_parser"] = "success"
        except Exception as exc:
            result["pypdf_field_parser"] = type(exc).__name__
        import fitz
        with fitz.open(str(filled)) as doc:
            widget_values = {
                widget.field_name: str(widget.field_value)
                for page in doc for widget in (page.widgets() or [])
            }
        try:
            ds = _find_xfa_packet(reader, "datasets").get_object().get_data()
            root = _parse_xml(ds)
            xfa_values = {}
            for key in _KEYS:
                wanted = SYNTHETIC_VALUES[key]
                if key.endswith("_family"):
                    parent = _xfa_node(root, _FIELDS[key].xfa_path[:-3])
                    encoded = "".join(parent.itertext()).strip()
                    # A vendor may serialize XFA rich text as escaped XHTML
                    # inside the XFA datasets. Record whether the expected
                    # name is present in the actual rich-text payload.
                    same = (encoded == wanted or bool(re.search(
                        r">" + re.escape(wanted) + r"</span>", encoded)))
                else:
                    same = _xfa_leaf(root, _FIELDS[key].xfa_path).text == wanted
                xfa_values[key] = same
            result["xfa_matches"] = xfa_values
        except Exception as exc:
            result["xfa_error"] = type(exc).__name__ + ": " + str(exc)[:120]
        result["acroform_matches"] = {
            key: widget_values.get(_FIELDS[key].acroform_name, "").strip() ==
                 SYNTHETIC_VALUES[key] for key in _KEYS
        }
        xfa = result.get("xfa_matches", {})
        result["all_xfa_match"] = len(xfa) == len(_KEYS) and all(xfa.values())
        result["all_acroform_match"] = all(result["acroform_matches"].values())
        original_reader = PdfReader(blank, strict=True)
        signature = original_reader.trailer["/Root"]["/Perms"]["/UR3"].get_object()
        br = [int(x) for x in signature["/ByteRange"]]
        def signed(blob):
            if len(br) != 4 or any(v < 0 for v in br) or (
                    br[0] + br[1] > len(blob) or br[2] + br[3] > len(blob)):
                raise ValueError("Original Reader usage-rights ByteRange out of bounds")
            return b"".join(blob[br[i]:br[i]+br[i+1]] for i in (0, 2))
        result["original_ur3_signed_bytes_unchanged"] = (
            signed(data) == signed(original))
        passed = (result["pages"] == 4 and result["all_xfa_match"] and
                  result["all_acroform_match"] and
                  result["original_ur3_signed_bytes_unchanged"])
        result["status"] = ("values_and_signed_bytes_pass_with_parser_warning"
                            if passed and result["pypdf_field_parser"] != "success"
                            else "values_and_signed_bytes_pass"
                            if passed else "structural_or_data_mismatch")
    except Exception as exc:
        result.update(status="readback_error", error_type=type(exc).__name__,
                      error=str(exc)[:250])
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return result["status"].startswith("values_and_signed_bytes_pass")


def main() -> None:
    p = ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("prepare")
    a.add_argument("original", type=Path)
    a.add_argument("out_dir", type=Path)
    b = sub.add_parser("verify")
    b.add_argument("original", type=Path)
    b.add_argument("filled", type=Path)
    b.add_argument("report", type=Path)
    args = p.parse_args()
    if args.cmd == "prepare":
        prepare(args.original, args.out_dir)
    elif not verify(args.original, args.filled, args.report):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
