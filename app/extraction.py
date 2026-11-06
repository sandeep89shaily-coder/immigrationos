"""Deterministic extraction adapter for synthetic documents, not a legal assessment.

A future reviewed AI provider must return proposals via the same untrusted queue;
this parser never writes verified facts or decides immigration eligibility.
"""
import io
import re
from typing import NamedTuple

from fastapi import HTTPException


class ProposedField(NamedTuple):
    field_path: str
    value: str
    source_page: int
    source_excerpt: str
    extraction_method: str
    confidence: float


# Labels are strictly anchored: don't infer entire histories from free text.
# All samples used for testing are fictional and the parser is intentionally conservative.
LABELS = {
    'given name': 'identity.given_name',
    'first name': 'identity.given_name',
    'surname': 'identity.family_name',
    'last name': 'identity.family_name',
    'date of birth': 'identity.date_of_birth',
    'passport number': 'identity.passport_number',
    'citizenship': 'identity.citizenship',
    'employer name': 'employment.employer_name',
    'employment start': 'employment.start_date',
    'employment end': 'employment.end_date',
    'institution': 'education.institution',
    'program of study': 'education.program',
}
# Accept ASCII letters and whitespace in labels; values may include Unicode.
LINE = re.compile(r'^\s*([A-Za-z ]{3,40})\s*:\s*(.{1,120})\s*$', re.UNICODE)


def read_pages(blob: bytes, mime: str) -> list[str]:
    if mime == 'text/plain':
        try:
            return [blob.decode('utf-8')[:100000]]
        except UnicodeDecodeError:
            raise HTTPException(status_code=422, detail='Not valid UTF-8') from None
    if mime == 'application/pdf':
        from pypdf import PdfReader
        try:
            reader = PdfReader(io.BytesIO(blob), strict=True)
            if reader.is_encrypted or len(reader.pages)>30:
                raise HTTPException(status_code=422, detail='Encrypted or oversized PDFs are not supported')
            return [(page.extract_text() or '')[:30000] for page in reader.pages]
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=422, detail='Unable to extract text from this PDF') from None
    raise HTTPException(status_code=422, detail='This document type requires a separate OCR adapter')


def propose_facts(blob: bytes, mime: str) -> list[ProposedField]:
    results=[]
    seen=set()
    for page_number, content in enumerate(read_pages(blob, mime), 1):
        for rawline in content.splitlines():
            line=rawline.strip()
            match=LINE.match(line)
            if not match: continue
            path=LABELS.get(' '.join(match.group(1).lower().split()))
            if not path: continue
            value=match.group(2).strip()
            if not value or value.lower() in {'n/a','unknown','none','not applicable'}: continue
            fingerprint=(path,value.casefold(),page_number)
            if fingerprint in seen: continue
            seen.add(fingerprint)
            results.append(ProposedField(path,value,page_number,line[:500],'label_match_v1',0.65))
            if len(results)>=100: return results
    return results
