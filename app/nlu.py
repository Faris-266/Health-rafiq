"""Rule-based Arabic NLU (MSA + Levantine / Gulf / Egyptian / Maghrebi + Arabizi).

Why rules and not an LLM here? Symptom detection and number extraction feed the
triage engine. They must be deterministic, auditable and testable. An LLM can be
added later as a *fallback for unrecognised free text* (never to lower severity).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── Normalisation ───────────────────────────────────────────────────────────
_DIAC = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]")
_DIGITS = str.maketrans(
    {chr(0x660 + i): str(i) for i in range(10)} | {chr(0x6F0 + i): str(i) for i in range(10)}
)


def fold(t: str) -> str:
    """Letter-level folding (safe to apply to regex source too)."""
    t = _DIAC.sub("", t)
    t = re.sub("[إأآٱ]", "ا", t)
    return (t.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
             .replace("ڤ", "ف").replace("پ", "ب"))


_TOKEN = re.compile(r"[^\W_]+(?:[./:\-][^\W_]+)*")

# Arabizi (Arabic in Latin letters, digits for sounds: 3=ع 7=ح 5/kh=خ 2=ء 8/gh=غ 9=ق)
ARABIZI = {
    "sukkar": "سكر", "sokkar": "سكر", "sukar": "سكر", "sokar": "سكر", "sker": "سكر", "soukar": "سكر",
    "daghet": "ضغط", "daght": "ضغط", "dghat": "ضغط", "da8t": "ضغط", "d8t": "ضغط", "dgheti": "ضغط", "daghti": "ضغط",
    "aywa": "ايوه", "aywa": "ايوه", "aiwa": "ايوه", "ewa": "ايوه", "eywa": "ايوه", "aah": "اه", "ah": "اه", "ih": "اه",
    "na3am": "نعم", "naam": "نعم", "nam": "نعم", "tamam": "تمام", "tmam": "تمام", "tamaam": "تمام",
    "la": "لا", "la2": "لا", "laa": "لا", "mish": "مش", "mesh": "مش", "mish": "مش", "ma": "ما", "mafi": "مافي",
    "mafi": "مافي", "mfeesh": "مفيش", "mafeesh": "مفيش", "lsa": "لسا", "lissa": "لسا", "lessa": "لسا",
    "akhadt": "اخذت", "5adt": "اخذت", "a5adt": "اخذت", "akhadet": "اخذت", "5adet": "اخذت", "khdt": "اخذت", "khdit": "خذت",
    "nsit": "نسيت", "nseet": "نسيت", "nsyt": "نسيت", "dawa": "دواء", "dwa": "دواء", "dawaa": "دواء",
    "wja3": "وجع", "waja3": "وجع", "wag3": "وجع", "waga3": "وجع", "w3a": "وجع", "sadr": "صدر", "sader": "صدر",
    "sadri": "صدري", "sadry": "صدري", "alb": "قلب", "albi": "قلبي", "qalbi": "قلبي",
    "dokha": "دوخه", "dawkha": "دوخه", "dwakha": "دوخه", "dokhaa": "دوخه", "dayekh": "دايخ", "dayikh": "دايخ",
    "sod3": "صداع", "soda3": "صداع", "sda3": "صداع", "suda3": "صداع",
    "nafas": "نفس", "nafasi": "نفسي", "nfsi": "نفسي", "daye2": "ضايق", "dayi2": "ضايق", "dayeq": "ضايق",
    "alhamdulillah": "الحمدلله", "7amdulillah": "الحمدلله", "hamdulillah": "الحمدلله", "elhamdulillah": "الحمدلله",
    "kwayes": "كويس", "kwayyes": "كويس", "kwayys": "كويس", "mnih": "منيح", "mneeh": "منيح", "bkhair": "بخير",
    "ta3ban": "تعبان", "ta3bane": "تعبان", "t3ban": "تعبان", "t3ban": "تعبان",
    "ghathayan": "غثيان", "ghasayan": "غثيان", "tamam": "تمام", "ok": "ok",
    "fi": "في", "fe": "في", "fee": "في", "fil": "في",
    "bdi": "بدي", "bddi": "بدي", "badi": "بدي", "bede": "بدي",
    "moot": "اموت", "mout": "اموت", "amoot": "اموت", "amout": "اموت",
    "stop": "stop", "ayqaf": "ايقاف", "iyqaf": "ايقاف",
}

# ── Token sets (written in folded form) ─────────────────────────────────────
NEG = {fold(x) for x in {
    "لا", "لأ", "لاء", "ما", "مش", "مو", "موب", "مب", "لسا", "لسه", "لسع", "لم", "لن", "ولا", "بدون",
    "مافي", "ماعندي", "ماعندو", "مفيش", "مافيني", "ماني", "ماكو", "ماكوش",
    "no", "not", "nope", "none", "without", "never", "نسيت", "نسيتها", "فاتني",
}}
CUT = {fold(x) for x in {"بس", "لكن", "لاكن", "الا", "غير", "لكني", "بالاضافه", "but", "however", "except"}}
AFF = {fold(x) for x in {
    "نعم", "ايوه", "ايوا", "ايوة", "ايو", "اي", "ايه", "اه", "اها", "تمام", "اخذت", "اخذتها", "اخذته", "اخذتو",
    "اخدت", "اخدتها", "اخدته", "خذت", "خذتها", "خدت", "خدتها", "خديت", "خذيت", "شربت", "اكيد", "طبعا", "تم",
    "موافق", "موافقه", "اوافق", "yes", "y", "yep", "yeah", "ok", "okay", "sure", "done",
}}
WELL = {fold(x) for x in {
    "تمام", "الحمدلله", "الحمد", "بخير", "كويس", "كويسه", "منيح", "منيحه", "زي", "الفل", "زينه", "زين", "طيب",
    "طيبه", "ممتاز", "ماشي", "عادي", "ok", "okay", "fine", "good", "none", "nothing", "no", "ولا",
}}
STOP_WORDS = {fold(x) for x in {"ايقاف", "اوقف", "وقف", "توقف", "الغاء", "الغي", "stop", "unsubscribe", "ايقاف"}}
HELP_WORDS = {fold(x) for x in {"مساعده", "مساعدة", "help", "قائمه", "؟"}}


def prepare(text: str) -> str:
    """Normalise + transliterate known Arabizi tokens → one space-joined string."""
    t = (text or "").strip().translate(_DIGITS)
    t = t.replace("٫", ".").replace("٬", ",").replace("،", ",")
    t = fold(t).lower()
    t = re.sub(r"([^\W\d_])\1{2,}", r"\1", t)  # collapse letter elongation ("ايييوه"); NEVER digits ("111")
    toks = _TOKEN.findall(t)
    return " ".join(ARABIZI.get(tok, tok) for tok in toks)


def tokens(text: str) -> list[str]:
    return prepare(text).split()


def has_digits(text: str) -> bool:
    return bool(re.search(r"\d", prepare(text)))


# ── Numbers ─────────────────────────────────────────────────────────────────
_BP = re.compile(
    r"(?<![\d.])(\d{1,3}(?:\.\d)?)\s*(?:/|\\|-|علي|عل|over|و)\s*(\d{1,3}(?:\.\d)?)(?![\d])"
)
_TWO_NUMS = re.compile(r"(?<![\d.])(\d{2,3})\s+(\d{2,3})(?![\d])")


@dataclass
class BP:
    sys: int
    dia: int
    scaled: bool = False   # "12/8" interpreted as 120/80


def parse_bp(text: str, allow_loose: bool = True) -> BP | None:
    p = prepare(text)
    m = _BP.search(p)
    if not m and allow_loose:
        m = _TWO_NUMS.search(p)
    if not m:
        return None
    s, d = float(m.group(1)), float(m.group(2))
    scaled = False
    if s <= 30 and d <= 20:  # Levantine/Gulf shorthand: "12 على 8"
        s, d, scaled = s * 10, d * 10, True
    if s < d:  # patient said diastolic first → swap
        s, d = d, s
    return BP(int(round(s)), int(round(d)), scaled)


@dataclass
class Glucose:
    mgdl: float
    raw: float
    unit: str            # mg/dL | mmol/L
    context: str | None  # fasting | post_meal | random | None
    ambiguous: bool = False


_FASTING = re.compile(fold(r"صايم|صيام|ريق|fasting|قبل الاكل|قبل الفطور|الصبح"))
_POSTMEAL = re.compile(fold(r"بعد (?:ال)?(?:اكل|فطور|غدا|غداء|عشا|عشاء|وجبه|اكله)|ساعتين|post|after (?:meal|eating)"))
_RANDOM = re.compile(fold(r"عشوائي|random"))
_NUM = re.compile(r"(?<![\d./])\d+(?:\.\d+)?(?![\d/])")
_KEYED = re.compile(fold(r"(?:سكر\w*|قراءه|قراءتي|glucose|sugar|الجهاز|جهاز)\D{0,14}?(\d+(?:\.\d+)?)"))


def detect_glucose_context(text: str) -> str | None:
    p = prepare(text)
    if _POSTMEAL.search(p):
        return "post_meal"
    if _RANDOM.search(p):
        return "random"
    if _FASTING.search(p):
        return "fasting"
    return None


def parse_glucose(text: str) -> Glucose | None:
    p = prepare(text)
    p = _BP.sub(" ", p)  # don't mistake a blood-pressure pair for glucose
    keyed = _KEYED.search(p)
    if keyed:
        num = keyed.group(1)
    else:
        nums = _NUM.findall(p)
        if not nums:
            return None
        num = nums[0]
    val = float(num)
    explicit_mmol = "mmol" in p
    explicit_mg = "mg" in p
    ambiguous = False
    if explicit_mmol or (not explicit_mg and "." in num and val < 40) or (not explicit_mg and val <= 15):
        unit, mg = "mmol/L", round(val * 18.016)
    else:
        unit, mg = "mg/dL", val
        if not explicit_mg and 16 <= val < 20:
            ambiguous = True
    return Glucose(float(mg), val, unit, detect_glucose_context(text), ambiguous)


# ── Yes / No ────────────────────────────────────────────────────────────────
def parse_yes_no(text: str) -> bool | None:
    toks = tokens(text)
    affirmed = False
    negated = False
    for i, tok in enumerate(toks):
        if tok in AFF:
            if any(t in NEG for t in toks[max(0, i - 2):i]):
                negated = True      # "ما اخذت" = did NOT take it
            else:
                affirmed = True
        elif tok in NEG and not (i + 1 < len(toks) and toks[i + 1] in AFF):
            negated = True
    if affirmed and negated:
        return None  # "ايوه بس نسيت" — conflicting; ask again rather than guess
    if negated:
        return False
    if affirmed:
        return True
    return None


def is_stop(text: str) -> bool:
    return bool(set(tokens(text)) & STOP_WORDS)


def is_help(text: str) -> bool:
    return bool(set(tokens(text)) & HELP_WORDS) or text.strip() in {"?", "؟"}


# ── Symptoms ────────────────────────────────────────────────────────────────
_PAIN = r"(?:وجع|الم|الام|ضيق\w*|ثقل|ثقيل|حرقه|حرقان|حرق|وخز|طعنه|نغزه|ضغط علي)"
_CHEST = r"(?:ال)?(?:صدر|قلب)\w*"
_VERB = r"(?:ب|ك)?(?:يوجع|توجع|يعور|تعور|يضر|تضر|يحرق|تحرق|يالم|تالم|يضيق|تضيق|يوخز|توخز)\w*"

_LEX_SRC: dict[str, list[str]] = {
    "chest_pain": [
        rf"{_PAIN}\s*(?:في|ف|ب)?\s*{_CHEST}",
        rf"{_CHEST}\s+(?:عم\s+)?{_VERB}",
        rf"(?:عم\s+)?{_VERB}\s+{_CHEST}",
        r"chest (?:pain|tight\w*|pressure|hurts?)", r"douleur\w*\s+(?:a la |dans la |de la )?poitrine",
    ],
    "breathless": [
        r"ضيق\w*\s*(?:في|ب)?\s*(?:ال)?(?:نفس|تنفس)\w*",
        r"صعوب\w*\s*(?:في|ب)?\s*(?:ال)?(?:نفس|تنفس)\w*",
        r"(?:ما|مش|مو|لا)\s*(?:اقدر|بقدر|قادر|قادره|اعرف|بعرف|عم اقدر|عم بقدر)\s*(?:ا|ب)?(?:تنفس|اتنفس|نفس)",
        r"(?:اتنفس|تنفس)\s*(?:بصعوبه|بتعب|بالعافيه)",
        r"نفس[يه]?\s*(?:مقطوع|قصير|ضايق|تقيل|ثقيل|ضيق|عم يضيق|يضيق|بيضيق)",
        r"مخنوق\w*|خنقه|اختناق|لهاث",
        r"short(?:ness)? of breath|can'?t breathe|cannot breathe|difficulty breathing|essoufl\w*",
    ],
    "fainting": [
        r"\bاغم(?:ي|ا)\w*|اغماء", r"(?:فقد(?:ت|ان)|غبت عن)\s*(?:ال)?وعي", r"\bfaint(?:ed|ing)?\b|passed out|blacked out",
    ],
    "stroke_signs": [
        r"(?:ال)?(?:وجه|فم)\w*\s*(?:مايل|منحرف|مسحوب|ملتوي)\w*", r"(?:كلام|لساني|لسان)\s*(?:ثقيل|متلعثم|تقيل|مش واضح)",
        r"تلعثم", r"(?:ضعف|خدر|تنميل|شلل)\s*(?:مفاجئ|فجاه)", r"(?:نص|نصف|جانب)\s*(?:ال)?(?:وجه|جسم|جسمي)\s*(?:مخدر|مشلول|ضعيف|ميت)",
        r"\bسكته\b|\bجلطه\b", r"slurred speech|face droop\w*|\bstroke\b",
    ],
    "confusion": [
        r"تشوش|مشوش|تشويش|ارتباك|مرتبك|(?:مش|مو|ما)\s*مركز|لا اتذكر|(?:مش|ما)\s*عارف\s*(?:وين|مكاني)|هلوسه|خرفان",
        r"\bconfus\w*|disoriented",
    ],
    "seizure": [r"نوبه\s*(?:صرع|تشنج)|\bصرع\b|seizure|convulsion"],
    "vomiting_persistent": [
        r"(?:استفراغ|ترجيع|رجعت|ارجع)\s*(?:كتير|كثير|مستمر|متكرر|عده مرات|مرتين|ثلاث مرات|ما يوقف|مش راضي يوقف|كل شوي)",
        r"(?:كتير|كثير)\s*(?:استفراغ|ترجيع)",
        r"vomiting (?:a lot|repeatedly|constantly)",
    ],
    "self_harm": [
        r"اقتل نفسي|انتحر|ابي اموت|ابغي اموت|بدي اموت|عايز اموت|عاوز اموت|نفسي اموت|اذي نفسي|اؤذي نفسي|"
        r"كرهت حياتي|ما عاد بدي عيش|بدي انهي حياتي|اخلص من حياتي|بغيت نموت|بغيت نقتل",
        r"kill myself|suicid\w*|want to die|end my life",
    ],
    # ── watch-level ──
    "dizziness": [
        r"دوخ\w*|دوار|دايخ\w*|دايش|راسي\s*(?:يلف|عم يلف|يدور|بيلف|بيدور|كيدور|كيلف|يلف بي)|لف\w*\s*راسي|(?:كيدور|كيلف|كتدور)\s*(?:بيا|بي|ليا)?\s*(?:ال)?راس\w*|dizz\w*|vertige",
    ],
    "blurred_vision": [
        r"زغلل\w*|تزغلل|نظري\s*(?:مشوش|ضعيف|غبش|مش واضح|ضبابي)|رؤي\w*\s*(?:ضبابي\w*|مشوش\w*)|غشاوه|شايف\s*(?:ضبابي|زغلله)|blurr?\w*\s*vision|blurry",
    ],
    "headache": [r"صداع|راسي\s*(?:يوجع\w*|بيوجع\w*|عم يوجع\w*|يالمني|كيضر\w*)|(?:وجع|الم)\s*(?:في\s*)?(?:ال)?راس\w*|headache"],
    "thirst": [r"عطش\w*|ظما|ريقي ناشف|فمي\s*(?:ناشف|جاف)|thirst\w*"],
    "frequent_urination": [
        r"(?:كتر|كثر)\w*\s*(?:ال)?(?:تبول|حمام)|(?:اتبول|بتبول|بول)\s*(?:كتير|كثير)|تبول متكرر|(?:اروح|بروح)\s*(?:ال)?حمام\s*(?:كتير|كثير)",
        r"frequent urination",
    ],
    "fatigue": [r"تعب\w*|ارهاق|مرهق\w*|اجهاد|خمول|كسل|ضعف عام|مجهد\w*|عيان\w*|عييت|fatigue|\btired\b|exhausted"],
    "leg_swelling": [
        r"(?:تورم|ورم|انتفاخ|وذمه|ورمت)\s*(?:في|ب)?\s*(?:ال)?(?:رجل|رجلي|رجول|اقدام|قدم|قدمي|كاحل|كواحل|ساق|ساقي)\w*",
        r"(?:رجل|رجلي|رجول|قدم|قدمي|اقدام|ساق)\w*\s+(?:متورم\w*|ورمان\w*|ورمت|منفخ\w*|منتفخ\w*|تورمت)",
        r"swollen (?:feet|legs|ankles)",
    ],
    "foot_numbness": [
        r"تنميل|\bخدر\w*|بتنمل|عم تنمل|نمله",
        r"(?:تنميل|خدر|نمل|تخدير|حرقان)\s*(?:في|ب)?\s*(?:ال)?(?:رجل|رجلي|اقدام|قدم|قدمي|اصابع|يد|يدي|ايدي)\w*",
        r"(?:رجل|رجلي|قدم|قدمي|ايدي|يدي)\w*\s+(?:مخدر\w*|منمل\w*|بتنمل|عم تنمل|تنمل|نمل\w*)", r"numb(?:ness)? (?:in )?(?:my )?(?:feet|foot|hands)",
    ],
    "foot_wound": [
        r"(?:جرح|قرحه|التهاب|فقاعه|تقرح)\s*(?:في|ب)?\s*(?:ال)?(?:رجل|رجلي|قدم|قدمي|اصبع|اصبعي|كعب)\w*",
        r"foot (?:wound|ulcer|sore)",
    ],
    "nausea": [r"غثيان|غثي\w*|مغثي\w*|لوعه|تلوع\w*|nause\w*"],
    "vomiting": [r"استفراغ|استفرغ\w*|ترجيع|بترجع|عم ارجع|رجعت\s*(?:الاكل|كل شي|الدواء|الفطور)|vomit\w*"],
    "abdominal_pain": [r"(?:وجع|الم|مغص)\s*(?:في|ب)?\s*(?:ال)?(?:بطن|معده|معدتي|بطني)\w*|مغص|abdominal pain|stomach (?:ache|pain)"],
    "palpitations": [
        r"خفقان|دقات\s*(?:ال)?قلب\w*\s*(?:سريعه|عاليه|متسارعه|قويه)|قلبي\s*(?:يدق|بيدق|عم يدق|يخفق|يرفرف|يطق|بيطق)\w*|palpitation\w*",
    ],
    "shaking_sweating": [r"رجف\w*|ارتجاف|رعش\w*|ارتعاش|ترجف|عرق\s*بارد|تعرق|تعريق|عرقان\w*|sweat\w*|shak\w*|trembl\w*"],
    "fall": [r"وقعت|سقطت|طحت|انزلقت|\bfell\b|\bfall(?:en)?\b"],
    "cramps": [r"شد عضلي|كرامب|تشنج\w*|cramp\w*"],
}
LEXICON: dict[str, list[re.Pattern]] = {
    code: [re.compile(fold(p)) for p in pats] for code, pats in _LEX_SRC.items()
}


@dataclass
class SymptomResult:
    symptoms: set[str] = field(default_factory=set)
    negated: set[str] = field(default_factory=set)
    none_declared: bool = False
    unrecognised: bool = False   # patient wrote something we could not classify


def _token_spans(p: str) -> list[tuple[str, int, int]]:
    out, pos = [], 0
    for tok in p.split(" "):
        out.append((tok, pos, pos + len(tok)))
        pos += len(tok) + 1
    return out


def _is_negated(spans: list[tuple[str, int, int]], start: int) -> bool:
    idx = next((i for i, (_, s, e) in enumerate(spans) if e > start), 0)
    for i in range(idx - 1, max(idx - 5, -1), -1):
        tok = spans[i][0]
        if tok in CUT:
            return False
        if tok in NEG:
            return True
    return False


def analyze_symptoms(text: str) -> SymptomResult:
    p = prepare(text)
    res = SymptomResult()
    if not p:
        return res
    spans = _token_spans(p)
    for code, pats in LEXICON.items():
        for pat in pats:
            for m in pat.finditer(p):
                if _is_negated(spans, m.start()):
                    res.negated.add(code)
                else:
                    res.symptoms.add(code)
    res.negated -= res.symptoms
    toks = set(p.split())
    if not res.symptoms:
        res.none_declared = bool(toks & (NEG | WELL)) or bool(res.negated)
        # Long, non-empty, unclassified text ⇒ keep it for the clinician.
        if not res.none_declared and len(p.split()) >= 3:
            res.unrecognised = True
    return res
