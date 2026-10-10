import pytest
from app import nlu


@pytest.mark.parametrize("text,expected", [
    ("وجع في صدري", "chest_pain"), ("عندي ألم في الصدر", "chest_pain"), ("صدري بيوجعني", "chest_pain"),
    ("wja3 fi sadri", "chest_pain"), ("chest pain", "chest_pain"),
    ("مش قادر اتنفس", "breathless"), ("نفسي ضايق", "breathless"), ("ضيق في التنفس", "breathless"),
    ("اغمي علي الصبح", "fainting"), ("وجهي مايل", "stroke_signs"),
    ("بدي اموت", "self_harm"), ("ابغى اموت", "self_harm"), ("bdi moot", "self_harm"),
    ("دوخة", "dizziness"), ("دايخ", "dizziness"), ("كيدور بيا الراس", "dizziness"), ("راسي بيلف", "dizziness"),
    ("زغللة بعيوني", "blurred_vision"), ("صداع قوي", "headache"), ("راسي بيوجعني", "headache"),
    ("غثيان", "nausea"), ("خفقان", "palpitations"), ("رجلي متورمة", "leg_swelling"), ("تنميل في رجلي", "foot_numbness"),
    ("جرح في قدمي", "foot_wound"), ("عطشان كتير", "thirst"),
])
def test_symptom_detected(text, expected):
    assert expected in nlu.analyze_symptoms(text).symptoms


@pytest.mark.parametrize("text,code", [
    ("ما عندي وجع صدر", "chest_pain"), ("مافي ضيق نفس", "breathless"), ("بدون دوخة", "dizziness"),
    ("ما عندي ضيق نفس ولا دوخة", "dizziness"), ("مش تعبان", "fatigue"), ("no chest pain", "chest_pain"),
])
def test_negated_symptom_not_flagged(text, code):
    r = nlu.analyze_symptoms(text)
    assert code not in r.symptoms and r.none_declared


def test_negation_does_not_hide_a_later_real_symptom():
    r = nlu.analyze_symptoms("ما عندي دوخة بس وجع صدر")
    assert "chest_pain" in r.symptoms and "dizziness" not in r.symptoms


def test_negator_inside_phrase_is_not_a_negation():
    assert "breathless" in nlu.analyze_symptoms("مش قادر اتنفس").symptoms
    assert "breathless" in nlu.analyze_symptoms("ما اقدر اتنفس").symptoms


@pytest.mark.parametrize("text", ["لا", "ما في شي الحمدلله", "تمام", "bkhair alhamdulillah", "مافي شي", "no"])
def test_none_declared(text):
    r = nlu.analyze_symptoms(text)
    assert not r.symptoms and r.none_declared


def test_unrecognised_text_is_kept_not_ignored():
    r = nlu.analyze_symptoms("عندي وجع بظهري من امس")
    assert r.unrecognised and not r.symptoms


@pytest.mark.parametrize("text,mgdl", [
    ("١٢٠", 120), ("120", 120), ("قراءة السكر 95", 95), ("sukkar 95", 95), ("سكري 6.5", 117), ("8", 144), ("250 mg", 250),
])
def test_glucose_numbers(text, mgdl):
    assert nlu.parse_glucose(text).mgdl == pytest.approx(mgdl, abs=1)


def test_glucose_context_detection():
    assert nlu.parse_glucose("180 بعد الأكل").context == "post_meal"
    assert nlu.parse_glucose("90 صايم").context == "fasting"


def test_glucose_ambiguous_unit_is_flagged():
    assert nlu.parse_glucose("17").ambiguous


@pytest.mark.parametrize("text,sd", [
    ("130/85", (130, 85)), ("١٣٠ على ٨٥", (130, 85)), ("12 على 8", (120, 80)), ("ضغطي 140 90", (140, 90)),
    ("daghet 150/95", (150, 95)), ("85/130", (130, 85)),
])
def test_bp_numbers(text, sd):
    b = nlu.parse_bp(text)
    assert (b.sys, b.dia) == sd


def test_glucose_ignores_bp_pair():
    assert nlu.parse_glucose("130/85 و سكر 110").mgdl == 110


@pytest.mark.parametrize("text,expected", [
    ("ايوه", True), ("أخذتها", True), ("aywa", True), ("tamam", True), ("نعم", True),
    ("لا", False), ("ما اخذت", False), ("نسيت", False), ("la2", False), ("لسا", False), ("مش اخذت", False),
    ("ايوه بس نسيت", None), ("؟؟", None), ("", None),
])
def test_yes_no(text, expected):
    assert nlu.parse_yes_no(text) is expected


def test_stop_detection():
    assert nlu.is_stop("إيقاف") and nlu.is_stop("stop") and not nlu.is_stop("تمام")


@pytest.mark.parametrize("text,mg", [("111", 111), ("5000", 5000), ("222", 222), ("333", 333), ("١١١", 111), ("سكري 100", 100)])
def test_repeated_digits_are_never_collapsed(text, mg):
    """Regression: elongation-collapse once turned 111 into 11 (→ misread as mmol/L)."""
    assert nlu.parse_glucose(text).mgdl == mg


def test_letter_elongation_still_collapses():
    assert nlu.parse_yes_no("ايييييوه") is True
