"""Generate plain PDF widget appearances for two synthetic test surnames.

The XFA datasets and /V field values are set separately. This helper only
repairs /AP appearance streams and does not perform Adobe validation.
"""
import re


def repair_family_appearances(pdf, page, widgets_by_name, fields, values, blocked):
    # Standard PDF Helvetica font independent of the XFA font encoding.
    font_ref = pdf.get_new_xref()
    pdf.update_object(font_ref, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for key in ("applicant_family", "representative_family"):
        widget = widgets_by_name.get(fields[key].acroform_name)
        if widget is None:
            raise blocked("Missing surname widget")
        kind, ap_dict = pdf.xref_get_key(widget.xref, "AP")
        match = re.search(r"/N (\d+) 0 R", ap_dict)
        if kind != "dict" or not match:
            raise blocked("Missing surname widget appearance")
        value = values[key]
        if not value.isascii() or any(ch in value for ch in "()\\"):
            raise blocked("Unsupported synthetic PDF literal")
        width, height = widget.rect.width, widget.rect.height
        if not 20 < width < 600 or not 12 < height < 100:
            raise blocked("Surname widget dimensions changed")
        baseline = round(height / 2 - 3, 4)
        stream = ("/Tx BMC\nq\nBT\n0 g\n/Helv 9 Tf\n"
                  f"1 0 0 1 2 {baseline} Tm\n({value}) Tj\n"
                  "ET\nQ\nEMC\n").encode("ascii")
        xref = int(match.group(1))
        pdf.update_stream(xref, stream)
        pdf.xref_set_key(xref, "Resources",
                         f"<< /Font << /Helv {font_ref} 0 R >> >>")
