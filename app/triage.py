"""Deterministic, rule-based triage.

SAFETY DESIGN
  * No LLM decides severity. Every escalation traces to a rule + a threshold
    in thresholds.json, which a physician must review and approve.
  * The system collects and routes. It never diagnoses or changes medication.
  * Rules are intentionally biased toward over-triage (a false alarm costs a
    phone call; a missed alarm can cost a life).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from statistics import mean

from .config import load_thresholds


class Level(IntEnum):
    NORMAL = 0
    WATCH = 1
    URGENT = 2

    @property
    def label(self) -> str:
        return self.name.lower()


# ── Symptom taxonomy ────────────────────────────────────────────────────────
RED_FLAGS = {
    "chest_pain", "breathless", "fainting", "stroke_signs", "confusion",
    "seizure", "vomiting_persistent", "self_harm",
}
WATCH_SYMPTOMS = {
    "dizziness", "blurred_vision", "headache", "thirst", "frequent_urination",
    "fatigue", "leg_swelling", "foot_numbness", "foot_wound", "nausea", "vomiting",
    "abdominal_pain", "palpitations", "shaking_sweating", "fall", "cramps",
}
HYPO_SYMPTOMS = {"shaking_sweating", "dizziness", "confusion", "fainting"}
HYPER_SYMPTOMS = {"nausea", "vomiting", "vomiting_persistent", "abdominal_pain", "breathless"}
BP_SYMPTOMS = {"headache", "blurred_vision", "dizziness", "palpitations", "nausea"}
BP_EMERGENCY_SYMPTOMS = {"headache", "blurred_vision", "chest_pain", "breathless", "confusion", "stroke_signs"}
LOW_BP_SYMPTOMS = {"dizziness", "fainting", "confusion", "fall"}


@dataclass
class Reason:
    code: str
    level: Level
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"code": self.code, "level": int(self.level), "data": self.data}


@dataclass
class TriageInput:
    glucose: float | None = None            # mg/dL
    glucose_context: str = "fasting"        # fasting | post_meal | random
    sys: int | None = None
    dia: int | None = None
    symptoms: set[str] = field(default_factory=set)
    free_text: str | None = None            # unclassified complaint, forwarded verbatim
    meds_taken: bool | None = None
    missed_med_days: int = 0                # consecutive days incl. today when meds_taken is False
    history_glucose: list[float] = field(default_factory=list)  # oldest → newest, excl. current
    history_sys: list[float] = field(default_factory=list)


@dataclass
class TriageResult:
    level: Level
    reasons: list[Reason]
    actions: list[str]
    emergency: bool
    rules_version: str

    @property
    def codes(self) -> set[str]:
        return {r.code for r in self.reasons}


def evaluate(inp: TriageInput, th: dict | None = None) -> TriageResult:
    th = th or load_thresholds()
    g, bp, tr = th["glucose_mgdl"], th["bp_mmhg"], th["trend"]
    reasons: list[Reason] = []
    actions: list[str] = []
    emergency = False
    sx = set(inp.symptoms)

    def act(*codes: str) -> None:
        for c in codes:
            if c not in actions:
                actions.append(c)

    # 1 ── Red-flag symptoms always escalate, regardless of any measurement.
    for s in sorted(sx & RED_FLAGS):
        reasons.append(Reason("red_flag_symptom", Level.URGENT, {"symptom": s}))
        emergency = True
    if "self_harm" in sx:
        act("crisis_support", "call_emergency")
    elif sx & RED_FLAGS:
        act("call_emergency")

    # 2 ── Glucose
    v = inp.glucose
    if v is not None:
        ctx = inp.glucose_context
        high_cut = g["fasting_watch_high"] if ctx == "fasting" else g["post_meal_watch_high"]
        if v < g["urgent_low"]:
            reasons.append(Reason("glucose_low_severe", Level.URGENT, {"value": v}))
            act("eat_fast_sugar", "recheck_15min", "call_if_worse")
            if sx & HYPO_SYMPTOMS:
                emergency = True
                act("call_emergency")
        elif v < g["watch_low"]:
            if sx & HYPO_SYMPTOMS:
                reasons.append(Reason("glucose_low_symptoms", Level.URGENT, {"value": v}))
                act("eat_fast_sugar", "recheck_15min", "call_if_worse")
            else:
                reasons.append(Reason("glucose_low", Level.WATCH, {"value": v}))
                act("eat_fast_sugar", "recheck_15min")
        elif v >= g["urgent_high"]:
            reasons.append(Reason("glucose_very_high", Level.URGENT, {"value": v}))
            act("drink_water", "contact_clinic_now", "call_if_worse")
        elif v >= g["urgent_high_with_symptoms"] and sx & HYPER_SYMPTOMS:
            reasons.append(Reason("glucose_high_symptoms", Level.URGENT, {"value": v}))
            act("drink_water", "contact_clinic_now", "call_if_worse")
        elif v > high_cut:
            reasons.append(Reason("glucose_high", Level.WATCH, {"value": v, "context": ctx}))
            act("contact_clinic_today")

    # 3 ── Blood pressure
    if inp.sys is not None and inp.dia is not None:
        s_, d_ = inp.sys, inp.dia
        if s_ >= bp["urgent_sys"] or d_ >= bp["urgent_dia"]:
            reasons.append(Reason("bp_very_high", Level.URGENT, {"sys": s_, "dia": d_}))
            act("rest_recheck_bp", "contact_clinic_now", "call_if_worse")
            if sx & BP_EMERGENCY_SYMPTOMS:
                emergency = True
                act("call_emergency")
        elif (s_ >= bp["symptomatic_urgent_sys"] or d_ >= bp["symptomatic_urgent_dia"]) and sx & BP_SYMPTOMS:
            reasons.append(Reason("bp_high_symptoms", Level.URGENT, {"sys": s_, "dia": d_}))
            act("rest_recheck_bp", "contact_clinic_now", "call_if_worse")
        elif s_ >= bp["watch_sys"] or d_ >= bp["watch_dia"]:
            reasons.append(Reason("bp_high", Level.WATCH, {"sys": s_, "dia": d_}))
            act("rest_recheck_bp", "contact_clinic_today")
        elif s_ < bp["low_sys"] or d_ < bp["low_dia"]:
            if sx & LOW_BP_SYMPTOMS:
                reasons.append(Reason("bp_low_symptoms", Level.URGENT, {"sys": s_, "dia": d_}))
                act("contact_clinic_now", "call_if_worse")
            else:
                reasons.append(Reason("bp_low", Level.WATCH, {"sys": s_, "dia": d_}))
                act("contact_clinic_today")

    # 4 ── Non-red-flag symptoms (at least WATCH)
    other = sorted(sx & WATCH_SYMPTOMS)
    if other:
        reasons.append(Reason("symptoms", Level.WATCH, {"symptoms": other}))
        act("contact_clinic_today")
    if inp.free_text:
        reasons.append(Reason("free_text", Level.WATCH, {"text": inp.free_text[:300]}))
        act("contact_clinic_today")

    # 5 ── Adherence
    if inp.meds_taken is False:
        days = max(inp.missed_med_days, 1)
        lvl = Level.WATCH if days >= th["adherence"]["missed_days_watch"] else Level.NORMAL
        reasons.append(Reason("missed_meds", lvl, {"days": days}))

    # 6 ── Trends (need enough history so one noisy reading does not fire)
    if v is not None:
        series = inp.history_glucose + [v]
        t = _rise(series, tr["min_points"], tr["glucose_rise_mgdl"], g["fasting_watch_high"] * 0.9)
        if t:
            reasons.append(Reason("trend_rising", Level.WATCH, {"metric": "glucose", **t}))
        if len(series) >= 3 and all(x > g["post_meal_watch_high"] for x in series[-3:]):
            reasons.append(Reason("sustained_high", Level.WATCH, {"metric": "glucose", "n": 3}))
    if inp.sys is not None:
        series = inp.history_sys + [inp.sys]
        t = _rise(series, tr["min_points"], tr["sys_rise_mmhg"], bp["watch_sys"] * 0.9)
        if t:
            reasons.append(Reason("trend_rising", Level.WATCH, {"metric": "bp_sys", **t}))
        if len(series) >= 3 and all(x >= bp["watch_sys"] for x in series[-3:]):
            reasons.append(Reason("sustained_high", Level.WATCH, {"metric": "bp_sys", "n": 3}))

    level = max((r.level for r in reasons), default=Level.NORMAL)
    return TriageResult(level, reasons, actions, emergency, th["version"])


def _rise(series: list[float], min_points: int, delta: float, floor: float) -> dict | None:
    """Mean of last 3 vs mean of up to 4 before them; flag a meaningful rise
    that is also close to/above the target ceiling (so 90→116 doesn't fire)."""
    if len(series) < min_points:
        return None
    recent, base = series[-3:], series[-7:-3]
    if not base:
        return None
    r, b = mean(recent), mean(base)
    if r - b >= delta and r >= floor:
        return {"from": round(b), "to": round(r)}
    return None


def is_plausible_glucose(v: float, th: dict | None = None) -> bool:
    lo, hi = (th or load_thresholds())["glucose_mgdl"]["plausible"]
    return lo <= v <= hi


def is_plausible_bp(s: int, d: int, th: dict | None = None) -> bool:
    bp = (th or load_thresholds())["bp_mmhg"]
    return bp["plausible_sys"][0] <= s <= bp["plausible_sys"][1] and \
        bp["plausible_dia"][0] <= d <= bp["plausible_dia"][1] and s > d
