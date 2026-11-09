"""Self-contained synthetic XFA incremental-PDF verifier regression tests.

No official government documents or actual applicant data are used.
"""
from hashlib import sha256
from io import BytesIO

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, TextStringObject

from scripts.verify_xfa_trial_readback import EXPECTED, verify


def _xml(values):
    return ('''<xfa:datasets xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/">
<xfa:data><IMM_5476><Page1>
<SectionA><familyName>''' + values[0] + '''</familyName><givenName>''' +
values[1] + '''</givenName></SectionA>
<SectionB><familyName>''' + values[2] + '''</familyName><givenName>''' +
values[3] + '''</givenName></SectionB>
</Page1></IMM_5476></xfa:data></xfa:datasets>''').encode()


def synthetic_incremental_pair(*, change_dataset=False, change_acro=False):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    names = list(EXPECTED)
    original_fields = []
    for key in names:
        obj = DictionaryObject({
            NameObject("/FT"): NameObject("/Tx"),
            NameObject("/T"): TextStringObject(key),
            NameObject("/V"): TextStringObject(""),
        })
        original_fields.append(writer._add_object(obj))
    stream = DecodedStreamObject()
    stream.set_data(_xml(["", "", "", ""]))
    stream_ref = writer._add_object(stream)
    acro = DictionaryObject({
        NameObject("/Fields"): ArrayObject(original_fields),
        NameObject("/XFA"): ArrayObject([TextStringObject("datasets"), stream_ref]),
    })
    writer._root_object[NameObject("/AcroForm")] = writer._add_object(acro)
    tmp = BytesIO()
    writer.write(tmp)
    original = tmp.getvalue()
    writer = PdfWriter(BytesIO(original), incremental=True)
    acro = writer._root_object["/AcroForm"].get_object()
    values = list(EXPECTED.values())
    for ref, value in zip(acro["/Fields"], values):
        ref.get_object()[NameObject("/V")] = TextStringObject(
            "wrong value" if change_acro and value == "Sharma" else value)
    if change_dataset:
        values[0] = "wrong value"
    acro["/XFA"][1].get_object().set_data(_xml(values))
    tmp = BytesIO()
    writer.write(tmp)
    return original, tmp.getvalue()


def _check(original, output, **kwargs):
    return verify(original, output, expected_input_hash=sha256(original).hexdigest(),
                  **kwargs)


def test_independent_readback_accepts_only_technical_fictional_subset():
    original, output = synthetic_incremental_pair()
    assert output.startswith(original)
    result = _check(original, output)
    assert result["status"] == "technical_subset_passed_not_adobe_validated"
    assert result["technical_subset_readback_verified"] is True
    assert result["official_source_sha256_verified"] is False
    assert result["acroform_readback"]["matched"] == 4
    assert result["xfa_datasets_readback"]["matched"] == 4
    assert result["adobe_reader_tested"] is False
    assert result["government_submission_supported"] is False
    assert "Sharma" not in str(result)
    assert "Anita" not in str(result)


def test_independent_readback_fails_on_tampered_original_or_nonincremental_output():
    original, output = synthetic_incremental_pair()
    assert _check(original, output[8:])["status"] == "blocked"
    assert _check(original, output.replace(original[:15], b"%PDF-NOT-VALID", 1))["status"] == "blocked"
    wrong_hash = verify(original, output, expected_input_hash="0"*64)
    assert wrong_hash["blocker"] == "original_checksum_mismatch"
    # A rewritten PDF with same fields is not acceptable if prefix is gone.
    assert _check(original, output[len(original):])["status"] == "blocked"
    assert _check(original, output, official=True)["blocker"] == "not_sha_pinned_official_imm5476"


def test_independent_readback_requires_both_xfa_and_acroform_roundtrip():
    original, output = synthetic_incremental_pair(change_dataset=True)
    result = _check(original, output)
    assert result["blocker"] == "xfa_datasets_readback_mismatch"
    original, output = synthetic_incremental_pair(change_acro=True)
    result = _check(original, output)
    assert result["blocker"] == "acroform_readback_mismatch"


def test_missing_and_corrupt_xfa_fail_closed():
    original, output = synthetic_incremental_pair()
    assert _check(original, original)["blocker"] == "signed_original_prefix_not_preserved"
    reader = PdfReader(BytesIO(output), strict=True)
    assert len(reader.pages) == 1
