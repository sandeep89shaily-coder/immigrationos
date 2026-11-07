"""Synthetic IMM5476 appearance repair for two special surname fields.

No production adapter or Adobe validation claims. Fixes PDF /AP appearance,
which cannot be inferred from /V or XFA datasets alone.
"""
import re


def repair_family_appearances(pdf, page, widgets_by_name, fields, values, blocked):
    for family_key, given_key in (
        ("applicant_family", "applicant_given"),
        ("representative_family", "representative_given"),
    ):
        family = widgets_by_name.get(fields[family_key].acroform_name)
        given = widgets_by_name.get(fields[given_key].acroform_name)
        if family is None or given is None:
            raise blocked("Missing paired name widgets")
        if abs(family.rect.width - given.rect.width) > 0.1:
            raise blocked("Unexpected name field geometry")
        def get_ap_xref(widget):
            kind, value = pdf.xref_get_key(widget.xref, "AP")
            match = re.search(r"/N (\d+) 0 R", value)
            if kind != "dict" or match is None:
                raise blocked("Missing widget appearance")
            return int(match.group(1))
        family_ref, given_ref = get_ap_xref(family), get_ap_xref(given)
        donor = pdf.xref_stream(given_ref)
        old = ("(" + values[given_key] + ") Tj").encode("ascii")
        new = ("(" + values[family_key] + ") Tj").encode("ascii")
        if donor.count(old) != 1 or b"/Helv 9 Tf" not in donor:
            raise blocked("Unexpected given-name appearance stream")
        font_kind, font_resources = pdf.xref_get_key(given_ref, "Resources")
        if font_kind != "dict" or "/Helv" not in font_resources:
            raise blocked("Required appearance font missing")
        pdf.update_stream(family_ref, donor.replace(old, new))
        pdf.xref_set_key(family_ref, "Resources", font_resources)
