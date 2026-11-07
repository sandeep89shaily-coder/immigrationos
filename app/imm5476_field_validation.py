"""Conservative syntax checks for observed IMM5476 fields.

These checks cannot establish identity, admissibility, IRCC acceptance, or
professional correctness. They only prevent obvious malformed strings from
being labelled evidence-ready in internal review checkpoints.
"""
from datetime import date
import re

_EMAIL = re.compile(r"^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$")
_UCI = re.compile(r"^(?:\\d{4}-?\\d{4}|\\d{2}-?\\d{4}-?\\d{4})$")


def plausible_observed_value(key: str, value: str) -> bool:
    value = value.strip()
    if not value or len(value) > 1000:
        return False
    if key == "applicant_dob":
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return False
        return parsed.isoformat() == value and parsed <= date.today()
    if key in {"applicant_email", "representative_email"}:
        return len(value) <= 254 and bool(_EMAIL.fullmatch(value))
    if key == "uci":
        return bool(_UCI.fullmatch(value))
    return True
