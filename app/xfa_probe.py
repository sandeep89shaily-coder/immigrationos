"""Bounded read-only probe for XFA packet organization.

Returns only structure metadata. Does not interpret individual field values,
approve any IRCC revision, fill PDFs, or use Adobe's validation runtime.
"""
from collections import Counter
from io import BytesIO
import re
import xml.etree.ElementTree as ET

from pypdf.generic import ArrayObject, StreamObject

MAX_XFA_PACKET = 3 * 1024 * 1024
MAX_XFA_TOTAL = 8 * 1024 * 1024
MAX_XML_NODES = 20000
MAX_XML_DEPTH = 64
SENSITIVE_XML = re.compile(rb"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)
SIMPLE_PACKET_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,40}$")


class XfaProbeError(ValueError):
    pass


def _plain(value):
    return value.get_object() if hasattr(value, "get_object") else value


def _xml(data):
    if len(data) > MAX_XFA_PACKET or not data.strip():
        raise XfaProbeError("XFA packet length is invalid")
    if SENSITIVE_XML.search(data):
        raise XfaProbeError("External entities and DTD declarations are forbidden")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise XfaProbeError("XFA packet is not safely parsed XML") from exc
    nodes = 0
    stack = [(root, 1)]
    while stack:
        element, depth = stack.pop()
        nodes += 1
        if nodes > MAX_XML_NODES or depth > MAX_XML_DEPTH:
            raise XfaProbeError("XFA XML exceeds safe structural limits")
        stack.extend((child, depth + 1) for child in element)
    return root


def _local(tag):
    return tag.rsplit("}", 1)[-1].rsplit(":", 1)[-1]


def probe_xfa(xfa_entry) -> dict:
    """Classify known PDF /XFA representation; fail closed on anomalies.

    PDF standard permits either an XFA stream or an ordered array with packet
    names alternating with stream objects. No XML content is returned.
    """
    entry = _plain(xfa_entry)
    packets = []
    if isinstance(entry, ArrayObject):
        if len(entry) % 2 or len(entry) == 0 or len(entry) > 128:
            raise XfaProbeError("Malformed XFA packet array")
        for i in range(0, len(entry), 2):
            name = str(_plain(entry[i]))
            packet = _plain(entry[i + 1])
            if not SIMPLE_PACKET_NAME.fullmatch(name) or not isinstance(packet, StreamObject):
                raise XfaProbeError("Invalid XFA packet name or stream")
            packets.append((name, bytes(packet.get_data())))
    elif isinstance(entry, StreamObject):
        packets = [("complete_xdp", bytes(entry.get_data()))]
    else:
        raise XfaProbeError("XFA entry is not an XML stream or packet array")
    if sum(len(payload) for _, payload in packets) > MAX_XFA_TOTAL:
        raise XfaProbeError("XFA stream exceeds inspection limit")

    packet_names = [name for name, _ in packets]
    if len(set(packet_names)) != len(packet_names):
        raise XfaProbeError("Duplicate named XFA packets")

    root_tags = Counter()
    template_present = False
    datasets_present = False
    dynamic_indicators = set()
    for name, payload in packets:
        root = _xml(payload)
        root_tags[_local(root.tag)] += 1
        if name == "template" or any(_local(e.tag) == "template" for e in root.iter()):
            template_present = True
        if name == "datasets" or any(_local(e.tag) == "datasets" for e in root.iter()):
            datasets_present = True
        for elem in root.iter():
            tag = _local(elem.tag)
            if tag == "dynamicRender" and (elem.text or "").strip().lower() == "required":
                dynamic_indicators.add("dynamic_render_required")
            if tag in {"occur", "instanceManager"}:
                dynamic_indicators.add("repeating_or_managed_instances")
            if tag == "subform" and elem.attrib.get("layout") in {"flowed", "tb", "lr-tb", "rl-tb"}:
                dynamic_indicators.add("flowed_subform")
    if "template" in packet_names:
        template_present = True
    if "datasets" in packet_names:
        datasets_present = True

    return {
        "xfa_container": "named_packets" if isinstance(entry, ArrayObject) else "single_stream",
        "packet_names": packet_names,
        "root_element_counts": dict(sorted(root_tags.items())),
        "template_packet_present": template_present,
        "datasets_packet_present": datasets_present,
        "dynamic_indicators": sorted(dynamic_indicators),
        "xfa_layout_assessment": "dynamic_indicators_detected" if dynamic_indicators else "indeterminate",
        "xfa_fill_supported": False,
        "adobe_validation_verified": False,
        "note": "Heuristic structural inventory only. Static/dynamic behavior requires actual Adobe rendering and interaction tests.",
    }
