import pytest
from app.triage import Level, TriageInput, evaluate


def lvl(**kw):
    return evaluate(TriageInput(**kw))


@pytest.mark.parametrize("g,ctx,expected", [
    (95, "fasting", Level.NORMAL), (130, "fasting", Level.NORMAL), (131, "fasting", Level.WATCH),
    (170, "post_meal", Level.NORMAL), (181, "post_meal", Level.WATCH),
    (69, "fasting", Level.WATCH), (70, "fasting", Level.NORMAL),
    (53, "fasting", Level.URGENT), (40, "fasting", Level.URGENT),
    (299, "fasting", Level.WATCH), (300, "fasting", Level.URGENT), (450, "random", Level.URGENT),
])
def test_glucose_levels(g, ctx, expected):
    assert lvl(glucose=g, glucose_context=ctx).level == expected


@pytest.mark.parametrize("s,d,expected", [
    (120, 80, Level.NORMAL), (139, 89, Level.NORMAL), (140, 85, Level.WATCH), (130, 90, Level.WATCH),
    (179, 109, Level.WATCH), (180, 100, Level.URGENT), (150, 110, Level.URGENT),
    (89, 70, Level.WATCH), (110, 59, Level.WATCH),
])
def test_bp_levels(s, d, expected):
    assert lvl(sys=s, dia=d).level == expected


def test_low_glucose_with_hypo_symptoms_is_urgent():
    assert lvl(glucose=62, symptoms={"shaking_sweating"}).level == Level.URGENT
    assert lvl(glucose=62).level == Level.WATCH


def test_severe_low_with_confusion_is_emergency():
    r = lvl(glucose=45, symptoms={"confusion"})
    assert r.emergency and "call_emergency" in r.actions


def test_high_glucose_plus_vomiting_is_urgent():
    assert lvl(glucose=270, symptoms={"vomiting"}).level == Level.URGENT
    assert lvl(glucose=270).level == Level.WATCH


def test_bp_160_with_headache_urgent():
    assert lvl(sys=165, dia=95, symptoms={"headache"}).level == Level.URGENT
    assert lvl(sys=165, dia=95).level == Level.WATCH


def test_crisis_bp_with_neuro_symptoms_is_emergency():
    r = lvl(sys=195, dia=115, symptoms={"blurred_vision"})
    assert r.level == Level.URGENT and r.emergency


@pytest.mark.parametrize("sym", ["chest_pain", "breathless", "fainting", "stroke_signs", "confusion", "seizure", "self_harm"])
def test_red_flags_always_urgent_even_with_perfect_vitals(sym):
    r = lvl(glucose=100, sys=118, dia=76, symptoms={sym})
    assert r.level == Level.URGENT and r.emergency


def test_watch_symptom_alone_is_watch():
    assert lvl(symptoms={"dizziness"}).level == Level.WATCH


def test_unclassified_free_text_is_never_dropped():
    r = lvl(free_text="وجع بظهري")
    assert r.level == Level.WATCH and "free_text" in r.codes


def test_missed_meds_escalates_after_two_days():
    assert lvl(meds_taken=False, missed_med_days=1).level == Level.NORMAL
    assert lvl(meds_taken=False, missed_med_days=2).level == Level.WATCH


def test_rising_trend_flagged_even_if_each_reading_is_borderline():
    r = lvl(glucose=135, history_glucose=[95, 98, 100, 96, 118, 126])
    assert "trend_rising" in r.codes


def test_trend_needs_enough_history():
    assert "trend_rising" not in lvl(glucose=135, history_glucose=[95, 130]).codes


def test_sustained_high_bp():
    r = lvl(sys=150, dia=92, history_sys=[148, 152])
    assert "sustained_high" in r.codes


def test_result_carries_rules_version():
    assert lvl(glucose=100).rules_version.endswith("DRAFT")
