"""Internal immigration preparation worksheets -- NOT official IRCC forms.

Only human-verified canonical facts can populate a worksheet. This module is
intentionally program-agnostic; certified IRCC PDF adapters require separate,
version-tested engineering and official form validation.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Worksheet:
    key: str
    title: str
    version: str
    fields: tuple[tuple[str, str, bool], ...]  # (label, canonical path, required)


WORKSHEETS = {
    'study_permit_demo': Worksheet(
        key='study_permit_demo', title='Study permit internal preparation worksheet', version='dev-1',
        fields=(
            ('Given name', 'identity.given_name', True),
            ('Family name', 'identity.family_name', True),
            ('Date of birth', 'identity.date_of_birth', True),
            ('Citizenship', 'identity.citizenship', True),
            ('Passport number', 'identity.passport_number', True),
            ('Institution', 'education.institution', False),
            ('Program of study', 'education.program', False),
        )),
    'work_permit_demo': Worksheet(
        key='work_permit_demo', title='Work permit internal preparation worksheet', version='dev-1',
        fields=(
            ('Given name', 'identity.given_name', True),
            ('Family name', 'identity.family_name', True),
            ('Date of birth', 'identity.date_of_birth', True),
            ('Citizenship', 'identity.citizenship', True),
            ('Passport number', 'identity.passport_number', True),
            ('Employer', 'employment.employer_name', False),
            ('Employment start', 'employment.start_date', False),
            ('Employment end', 'employment.end_date', False),
        )),
}


def build_worksheet(worksheet_key, facts, open_issues):
    if worksheet_key not in WORKSHEETS:
        raise KeyError(worksheet_key)
    template = WORKSHEETS[worksheet_key]
    verified = {}
    for fact in facts:
        if fact.review_status == 'verified':
            verified.setdefault(fact.field_path, []).append(fact)
    fields=[]
    missing=[]
    ambiguities=[]
    for label,path,required in template.fields:
        sources=verified.get(path, [])
        values={f.value.strip() for f in sources}
        if len(values) == 1:
            value=next(iter(values))
            status='verified'
        elif len(values)>1:
            value=None
            status='ambiguous'
            ambiguities.append(path)
        else:
            value=None
            status='missing'
            if required: missing.append(path)
        fields.append({
            'label':label,'field_path':path,'required':required,'status':status,
            'value':value, 'fact_ids':[str(f.id) for f in sources],
            'document_ids':list({str(f.document_id) for f in sources if f.document_id}),
        })
    reasons=[]
    if missing: reasons.append('Missing required verified fields')
    if ambiguities: reasons.append('Conflicting verified values')
    if open_issues: reasons.append('Unresolved evidence issues')
    return {
        'template_id':template.key,'template_version':template.version,'title':template.title,
        'status':'requires_review' if reasons else 'internal_fields_complete',
        'reasons':reasons, 'fields':fields,
        'not_official_form':True,
        'disclaimer':'Internal preparation worksheet only. It is not an IRCC form, application, eligibility decision, or submission package.',
    }
