"""Boundary tests for internal IMM5476 syntax checks; not IRCC acceptance."""
from app.imm5476_field_validation import plausible_observed_value


def test_valid_synthetic_dates_emails_and_uci():
    for key, value in [
        ("applicant_dob", "2001-06-09"),
        ("applicant_email", "applicant@example.test"),
        ("representative_email", "agent+intake@example.test"),
        ("uci", "1234-5678"),
        ("uci", "12345678"),
        ("uci", "12-3456-7890"),
        ("uci", "1234567890"),
    ]:
        assert plausible_observed_value(key, value), (key, value)


def test_invalid_syntax_fails_closed():
    for key, value in [
        ("applicant_dob", "2001-02-30"),
        ("applicant_dob", "2001-6-9"),
        ("applicant_dob", "2099-01-01"),
        ("applicant_email", "not-an-email"),
        ("applicant_email", "a@example.test\\nother"),
        ("representative_email", "person at example.test"),
        ("uci", "12-34"),
        ("uci", "123456789"),
        ("uci", "12A4-5678"),
    ]:
        assert not plausible_observed_value(key, value), (key, value)
