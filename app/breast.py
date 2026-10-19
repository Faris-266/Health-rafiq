"""Breast-health logic: risk category, screening schedule, symptom triage.  (Pure functions, no I/O.)

WHAT THIS IS NOT: it does not diagnose, does not compute a statistical risk score (Gail / Tyrer-Cuzick style
models need clinical validation and clinician input) and never tells a woman she is "fine". It
  1. sorts women into "average" vs "elevated" screening pathway from yes/no history answers,
  2. tracks when a screening mammogram is due,
  3. routes any reported breast change to a clinician and tracks it until she has been SEEN.
All numbers come from app/breast_policy.json, which a responsible clinician must approve.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .config import load_breast_policy
from .nlu import BREAST_CODES
from .triage import Level, Reason, TriageResult

CONCERN = {"breast_lump", "breast_shape_change", "nipple_discharge", "nipple_retraction", "breast_skin_change", "axillary_lump"}
PAIN_ONLY = {"breast_pain"}
assert CONCERN | PAIN_ONLY == BREAST_CODES

ELIGIBLE = {"up_to_date", "due_soon", "due", "overdue"}


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, min(d.day, 28))


def age_of(birth_year: int | None, today: date) -> int | None:
    return None if not birth_year else today.year - birth_year


def risk_category(flags: dict, policy: dict | None = None) -> str:
    """'elevated' if ANY listed history flag is True; 'average' if the questions were answered; 'unknown' if none were."""
    keys = (policy or load_breast_policy())["elevated_risk_flags"]
    if any(flags.get(k) is True for k in keys):
        return "elevated"
    return "average" if any(flags.get(k) is False for k in keys) else "unknown"


def screening_status(age: int | None, risk: str, last: date | None, today: date,
                     manual_due: date | None = None, policy: dict | None = None) -> tuple[str, date | None]:
    """→ (status, next_due). Status is one of
    unknown | not_yet | individualised | specialist_plan | up_to_date | due_soon | due | overdue."""
    pol = (policy or load_breast_policy())["mammogram"]
    if age is None:
        return "unknown", None
    if risk == "elevated" and manual_due is None:
        return "specialist_plan", None          # a clinician must set an individual plan; we never guess it
    if risk != "elevated":
        if age < pol["start_age"]:
            return "not_yet", None
        if age > pol["stop_age"]:
            return "individualised", None
    due = manual_due or (add_months(last, pol["interval_months"]) if last else today)
    delta = (due - today).days
    if delta > pol["due_soon_days"]:
        return "up_to_date", due
    if delta > 0:
        return "due_soon", due
    if delta >= -pol["overdue_after_days"]:
        return "due", due
    return "overdue", due


def evaluate_breast(symptoms: set[str], risk: str = "unknown", free_text: str | None = None,
                    policy: dict | None = None) -> TriageResult:
    pol = policy or load_breast_policy()
    sx = set(symptoms)
    reasons: list[Reason] = []
    actions: list[str] = []
    concern = sorted(sx & CONCERN)
    if concern:
        reasons.append(Reason("breast_concern", Level.URGENT, {"symptoms": concern}))
        actions.append("see_clinic_prompt")
    if "breast_skin_change" in sx and "fever" in sx:
        reasons.append(Reason("breast_infection_signs", Level.URGENT, {}))
        actions.insert(0, "same_day_care")
    if sx & PAIN_ONLY and not concern:
        reasons.append(Reason("breast_pain", Level.WATCH, {}))
        actions.append("see_clinic_routine")
    if free_text:
        reasons.append(Reason("free_text", Level.WATCH, {"text": free_text[:300]}))
        if not actions:
            actions.append("see_clinic_routine")
    if risk == "elevated" and reasons:
        reasons.append(Reason("elevated_risk", max(r.level for r in reasons), {}))
    level = max((r.level for r in reasons), default=Level.NORMAL)
    return TriageResult(level, reasons, actions, False, pol["version"])


def referral_dates(priority: str, now: date, policy: dict | None = None) -> tuple[date, date]:
    """(contact_by, visit_by) for a new referral."""
    r = (policy or load_breast_policy())["referral"]
    if priority == "urgent":
        return now + timedelta(days=r["urgent_contact_days"]), now + timedelta(days=r["urgent_visit_days"])
    return now + timedelta(days=r["routine_visit_days"] // 3), now + timedelta(days=r["routine_visit_days"])


@dataclass
class ScreeningOutcome:
    next_due: date | None
    referral_priority: str | None     # None | 'urgent' | 'routine'
    reason: str


def outcome_of_screening(kind: str, done_on: date, birads: int | None, result: str | None,
                         policy: dict | None = None) -> ScreeningOutcome:
    """What should happen after a screening result is recorded. BI-RADS 0/4/5 → urgent referral; 3 → 6-month recheck."""
    pol = policy or load_breast_policy()
    if kind == "mammogram" and birads is not None:
        rule = pol["birads"].get(str(birads))
        if rule is None:
            raise ValueError("BI-RADS must be 0-6")
        if rule["action"] in ("recall", "referral"):
            return ScreeningOutcome(None, rule.get("priority", "urgent"), f"birads_{birads}")
        if rule["action"] == "short_interval":
            return ScreeningOutcome(add_months(done_on, rule["months"]), None, "birads_3")
        if rule["action"] == "known":
            return ScreeningOutcome(None, None, "birads_6")
        return ScreeningOutcome(add_months(done_on, pol["mammogram"]["interval_months"]), None, "routine")
    if result in ("abnormal", "needs_followup"):
        return ScreeningOutcome(None, "urgent" if result == "abnormal" else "routine", f"{kind}_{result}")
    if kind == "mammogram":
        return ScreeningOutcome(add_months(done_on, pol["mammogram"]["interval_months"]), None, "routine")
    return ScreeningOutcome(None, None, "recorded")
