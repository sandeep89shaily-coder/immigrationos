"""Conservative, read-only timeline questions for applicant history.

Never infers an IRCC lookback requirement or interprets an absent end date
as "present". Flags are requests for human clarification, not legal findings.
"""
from datetime import date, timedelta
from hashlib import sha256
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import OrgAccess, READ_ROLES, allow, get_org_access
from app.applicant_history_models import ApplicantHistory
from app.db import get_db
from app.models import Case

router = APIRouter(prefix="/api/v1/orgs/{org_id}/cases/{case_id}",
                   tags=["applicant-timeline-audit"])
KINDS = ("address", "employment", "education")
MAX_WINDOW_DAYS = 36525


def _date(value):
    if isinstance(value, date) and not isinstance(value, str):
        return value
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def audit_history_timeline(*, records: list[ApplicantHistory],
                           client_id: UUID, org_id: UUID,
                           start: date, end: date) -> dict:
    """Evaluate only confirmed bounded intervals within a caller-chosen window."""
    if end < start or (end - start).days > MAX_WINDOW_DAYS:
        raise ValueError("Invalid timeline window")
    report = {}
    for kind in KINDS:
        items = [r for r in records
                 if r.client_id == client_id and r.org_id == org_id and r.kind == kind]
        flags = []
        spans = []
        unresolved_end = False
        for item in items:
            begin = _date(item.details.get("start_date"))
            finish_raw = item.details.get("end_date")
            finish = _date(finish_raw)
            if begin is None or (finish_raw is not None and finish is None):
                flags.append({"type": "invalid_date", "record_ids": [str(item.id)]})
                unresolved_end = True
                continue
            if finish is not None and finish < begin:
                flags.append({"type": "reversed_period", "record_ids": [str(item.id)]})
                unresolved_end = True
                continue
            if finish is None:
                flags.append({"type": "end_date_not_supplied",
                              "record_ids": [str(item.id)]})
                # Unbounded periods cannot prove coverage; avoid false gaps.
                if begin <= end:
                    unresolved_end = True
                continue
            if finish < start or begin > end:
                continue
            spans.append((max(begin, start), min(finish, end), str(item.id)))
        spans.sort(key=lambda x: (x[0], x[1], x[2]))
        for index, (begin, finish, record_id) in enumerate(spans):
            for previous_start, previous_end, previous_id in spans[:index]:
                if previous_end >= begin:
                    flags.append({
                        "type": "overlap_for_review",
                        "record_ids": sorted([previous_id, record_id]),
                        "start_date": begin.isoformat(),
                        "end_date": min(previous_end, finish).isoformat(),
                    })
        # Do not report or certify chronological coverage if an end date
        # is unresolved. This suppresses misleading missing-period flags.
        if not unresolved_end:
            cursor = start
            for begin, finish, _ in spans:
                if begin > cursor:
                    flags.append({"type": "uncovered_period_for_review",
                                  "start_date": cursor.isoformat(),
                                  "end_date": (begin - timedelta(days=1)).isoformat(),
                                  "record_ids": []})
                if finish >= cursor:
                    cursor = finish + timedelta(days=1)
            if cursor <= end:
                flags.append({"type": "uncovered_period_for_review",
                              "start_date": cursor.isoformat(),
                              "end_date": end.isoformat(), "record_ids": []})
        # Education periods commonly overlap jobs; do not compare categories
        # or treat uncovered education as evidence of non-compliance.
        for flag in flags:
            flag["flag_sha256"] = sha256(json.dumps(
                {"kind": kind, "flag": flag},
                sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        report[kind] = {
            "record_count": len(items),
            "explicit_bounded_records_in_window": len(spans),
            "coverage_evaluable": not unresolved_end,
            "flags": flags,
            "review_required": bool(flags),
        }
    result = {
        "window_start": start.isoformat(), "window_end": end.isoformat(),
        "window_selected_by": "requester_not_ircc_rule",
        "categories": report,
        "total_flags": sum(len(section["flags"]) for section in report.values()),
        "all_histories_verified": False,
        "timeline_complete_for_ircc": False,
        "official_form_generation_allowed": False,
        "warning": (
            "Internal date consistency prompts only. Dates, periods, relevance, "
            "continuous coverage, exemptions, and filing requirements need "
            "professional and documentary review. Missing end dates are not assumed current."
        ),
    }
    result["snapshot_sha256"] = sha256(json.dumps(
        {"report": result, "versions": sorted(
            (str(r.id), r.version, r.kind, r.details)
            for r in records if r.client_id == client_id and r.org_id == org_id
            and r.kind in KINDS)},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()).hexdigest()
    return result


@router.get("/history-timeline-audit")
def get_history_timeline_audit(org_id: UUID, case_id: UUID, response: Response,
                               start_date: date = Query(...),
                               end_date: date = Query(...),
                               db: Session = Depends(get_db),
                               access: OrgAccess = Depends(get_org_access)):
    allow(access, READ_ROLES)
    if end_date < start_date or (end_date - start_date).days > MAX_WINDOW_DAYS:
        raise HTTPException(422, "Choose a valid history review window")
    case = db.scalar(select(Case).where(Case.org_id == org_id, Case.id == case_id))
    if case is None:
        raise HTTPException(404, "Case not available")
    records = db.scalars(select(ApplicantHistory).where(
        ApplicantHistory.org_id == org_id,
        ApplicantHistory.client_id == case.client_id,
        ApplicantHistory.kind.in_(KINDS)
    )).all()
    response.headers["Cache-Control"] = "no-store"
    return audit_history_timeline(
        records=records, client_id=case.client_id, org_id=org_id,
        start=start_date, end=end_date)
