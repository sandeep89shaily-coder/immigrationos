"""Vendor-trial selection and safety tests; do not require Aspose installation."""
from pathlib import Path

import pytest

from app.imm5476_official_poc import _FIELDS
from scripts.evaluate_aspose_xfa import (
    AsposeTrialBlocked, TARGET_KEYS, resolve_field_names, run_trial,
)


def test_select_exact_observed_xfa_names_without_guessing():
    names = [_FIELDS[key].acroform_name for key in TARGET_KEYS]
    assert resolve_field_names(names) == dict(zip(TARGET_KEYS, names))


def test_select_vendor_name_with_observed_prefix_only():
    base = _FIELDS["applicant_family"].acroform_name
    assert resolve_field_names(["xfa[0].form[0]." + base]) == {
        "applicant_family": "xfa[0].form[0]." + base}


def test_never_guess_from_ambiguous_or_unrelated_names():
    value = _FIELDS["representative_family"].acroform_name
    with pytest.raises(AsposeTrialBlocked, match="Ambiguous"):
        resolve_field_names([value, "xfa[0].form[0]." + value])
    assert resolve_field_names(["UnrelatedTextField", "familyName[0]"]) == {}


def test_invalid_blank_pdf_is_rejected_before_loading_commercial_engine(tmp_path):
    source = tmp_path / "unapproved.pdf"
    target = tmp_path / "fictional.pdf"
    source.write_bytes(b"%PDF-1.7\\nUnapproved counterfeit")
    with pytest.raises(AsposeTrialBlocked, match="SHA-256"):
        run_trial(source, target)
    assert not target.exists()


def test_never_overwrite_existing_output_or_original(tmp_path):
    source = tmp_path / "imm5476.pdf"
    source.write_bytes(b"synthetic fixture")
    with pytest.raises(AsposeTrialBlocked, match="separate output"):
        run_trial(source, source)
    existing = tmp_path / "exists.pdf"
    existing.write_bytes(b"preexisting")
    with pytest.raises(AsposeTrialBlocked, match="new, separate"):
        run_trial(source, existing)
    assert existing.read_bytes() == b"preexisting"
