"""Public blank-template monitoring is fail-closed and never authorizes form use."""
from datetime import datetime, timezone
from hashlib import sha256

import pytest

from app.official_template_observation import (
    OfficialTemplateObservationError, observe_blank_template
)
from tests.test_form_template_inspector import create_fixture, write_modified_pdf, add_xfa


def test_observation_records_revision_hint_but_never_claims_validation():
    raw = create_fixture()
    result = observe_blank_template(raw, observed_at=datetime(2026, 11, 6, tzinfo=timezone.utc))
    assert result["claimed_official_revision"] == "11-2025"
    assert result["baseline_comparison"] == "baseline_not_yet_approved"
    assert result["source_url"].startswith("https://www.canada.ca/")
    assert result["source_authenticity_independently_verified"] is False
    assert result["revision_confirmed_by_pdf_review"] is False
    assert result["release_approved"] is False
    assert result["official_autofill_supported"] is False
    assert result["pdf_bytes_saved"] is False


def test_pinned_checksum_detects_changes_but_never_approves_template():
    raw = create_fixture()
    digest = sha256(raw).hexdigest()
    matching = observe_blank_template(raw, pinned_sha256=digest)
    changed = observe_blank_template(raw, pinned_sha256="0" * 64)
    assert matching["baseline_comparison"] == "same_bytes"
    assert changed["baseline_comparison"] == "changed_bytes"
    assert matching["release_approved"] is False
    assert changed["release_approved"] is False


def test_xfa_template_observation_remains_unapproved():
    raw = write_modified_pdf(create_fixture(), add_xfa)
    result = observe_blank_template(raw)
    assert result["technical_inspection"]["classification"] == "xfa_or_hybrid_requires_adobe_workflow"
    assert result["official_autofill_supported"] is False


@pytest.mark.parametrize("checksum", ["fake", "g" * 64, ""])
def test_bad_expected_fingerprints_are_rejected(checksum):
    with pytest.raises(OfficialTemplateObservationError):
        observe_blank_template(create_fixture(), pinned_sha256=checksum)


def test_invalid_pdf_fails_safely():
    with pytest.raises(OfficialTemplateObservationError):
        observe_blank_template(b"Not PDF")
