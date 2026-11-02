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

# ── Breast-health lexicon (Arabic dialects, English, French/Darija). "صدر" is also used for "breast" in
#    many dialects, so it only counts as breast when combined with a breast-change word; pain + صدر
#    stays a CHEST-PAIN red flag on purpose (safety first).
_BR = r"(?:ال)?(?:ثدي|ثديي|ثدييه|نهد|صدر)\w*"
_LUMP = r"\b(?:ال)?(?:كتله|كتل|عقده|عقد|حبه|حبات|كره|كوره|تكتل|نتوء|بروز|ورم|قسوه|تصلب|تكيس|غده|سماكه|ثخانه|شي قاسي|شي صلب|شيء قاسي|منطقه قاسيه)"
_BREAST_SRC: dict[str, list[str]] = {
    "breast_lump": [
        rf"{_LUMP}\s*(?:جديد\w*|صغير\w*|قاسي\w*)?\s*(?:في|ف|ب|على|عند)?\s*{_BR}",
        rf"{_BR}\s*(?:فيه|فيها|في|عليه|عليها|ب|عندي|لقيت|حسيت)?\s*{_LUMP}",
        r"(?:lump|mass|knot|thickening|hard (?:spot|area)|bump)s?\s*(?:in|on|near|under)?\s*(?:my|the|her)?\s*(?:left|right)?\s*(?:breast|boob|chest)",
        r"(?:breast|boob)\s*(?:lump|mass|thickening)", r"found a lump",
        r"(?:boule|grosseur|masse|nodule)\s*(?:dans|au|du|a)?\s*(?:le |mon |ma )?(?:sein|poitrine)",
    ],
    "breast_shape_change": [
        rf"(?:تورم|انتفاخ|تضخم|كبر|صغر|تغير|تغيير|اختلاف)\w*\s*(?:في|ب|ف)?\s*(?:ال)?(?:حجم|شكل)\s*{_BR}",
        rf"{_BR}\s*(?:متورم\w*|منتفخ\w*|تورم\w*|كبر\w*|صغر\w*|تغير\w*|اختلف\w*|مختلف\w*)",
        rf"(?:تورم|انتفاخ)\s*(?:في|ب|ف)?\s*{_BR}",
        r"(?:breast|boob)s?\s*(?:swell\w*|swollen|larger|bigger|smaller|changed (?:in )?(?:size|shape)|shape change|asymmetr\w*)",
        r"one breast (?:is )?(?:bigger|larger|smaller|different)",
    ],
    "nipple_discharge": [
        r"(?:افراز\w*|سائل|دم|دماء|قيح|حليب|ماء)\s*(?:اصفر|اخضر|بني|دموي)?\s*(?:من|خارج من|يخرج من|بيطلع من|طالع من|ينزل من|نازل من|يسيل من)\s*(?:ال)?(?:حلم\w*|ثدي|نهد|صدر)\w*",
        r"(?:ال)?حلم\w*\s*(?:عم\s*)?(?:بتفرز|تفرز|بتنزل|تنزل|بتسيل|تسيل)",
        r"(?:ال)?حلم\w*\s*(?:فيها|فيه|يخرج منها|بيطلع منها|ينزل منها)\s*(?:سائل|دم|افراز\w*|قيح|حليب)",
        r"افرازات?\s*(?:من\s*)?(?:ال)?حلم",
        r"(?:nipple|breast)\s*(?:discharge|leak\w*|bleed\w*|oozing)", r"discharge (?:from|out of) (?:my )?(?:nipple|breast)",
        r"(?:blood|fluid|pus) (?:from|out of|coming from) (?:my )?(?:nipple|breast)", r"ecoulement\s*(?:du|par le|au)?\s*(?:mamelon|sein)",
    ],
    "nipple_retraction": [
        r"(?:ال)?حلم\w*\s*(?:غاطس\w*|غايص\w*|داخل\w*|منسحب\w*|مقلوب\w*|انسحب\w*|دخل\w*|انقلب\w*|متراجع\w*|راجع\w*|رجع\w*)(?:\s*(?:لجوا|لجوه|لورا|للداخل|لداخل))?",
        r"nipple\s*(?:is |has |have |been |got )*(?:turn\w*|pull\w*|inverted|retract\w*|sunken)", r"inverted nipple",
    ],
    "breast_skin_change": [
        rf"(?:جلد|بشره)\s*{_BR}\s*(?:\w+\s*)?(?:متجعد|مجعد|محمر|احمر\w*|متقشر|يقشر|سميك|خشن|مشدود|داكن)",
        rf"(?:تجعد|تغضن|غمازه|حفره|احمرار|حمره|تقشر|قشور|طفح|تسلخ|قرحه|التهاب)\s*(?:في|ب|ف|على)?\s*(?:جلد\s*)?(?:ال)?(?:ثدي|ثديي|نهد|صدر|حلم)\w*",
        r"قشره\s*(?:ال)?برتقال\w*",
        rf"{_BR}\s*(?:محمر\w*|احمر\w*|متقشر\w*|فيه حفره|فيه غمازه|فيها حفره|متجعد\w*)",
        r"(?:dimpl\w*|puckering|orange[- ]peel|redness|red patch|scaly|scaling|flaky|rash|thickened skin|skin changes?)\s*(?:on|of|in|around)?\s*(?:my|the)?\s*(?:breast|nipple)",
        r"breast (?:skin|is red|looks red|redness)", r"peau d ?orange",
    ],
    "axillary_lump": [
        rf"{_LUMP}\s*(?:في|ف|ب|تحت)?\s*(?:ال)?(?:ابط|ابطي|اباط|ابطين|ذراع|دراع)\w*",
        rf"تحت\s*(?:ال)?(?:ابط|ذراع|دراع)\w*\s*(?:فيه\s*)?{_LUMP}",
        r"(?:تورم|انتفاخ)\s*(?:غدد|عقد)\s*(?:في|ب|ف|تحت)?\s*(?:ال)?(?:ابط|ذراع)\w*",
        r"(?:lump|swelling|swollen (?:gland|lymph node)s?|knot)\s*(?:in|under)\s*(?:my )?(?:armpit|underarm|arm pit)",
        r"armpit\s*(?:lump|swelling)", r"swollen (?:gland|lymph node)s? (?:in|under) (?:my )?(?:armpit|arm)",
    ],
    "breast_pain": [
        r"(?:وجع|الم|الام|حساسيه|ثقل|حرقان|نغزات?)\s*(?:في|ب|ف)?\s*(?:ال)?(?:ثدي|ثديي|نهد)\w*",
        r"(?:ال)?(?:ثدي|ثديي|نهد)\w*\s*(?:يوجع\w*|بيوجع\w*|يؤلم\w*|بيألم\w*|يالم\w*|وجع\w*)",
        r"breast\s*(?:pain|tender\w*|ache|aching|sore\w*)", r"(?:painful|sore|tender) breast",
    ],
    "fever": [r"حرار\w*|سخون\w*|\bحمي\b|\bحمى\b|\bfever\b|temperature (?:of )?\d+"],
}
BREAST_CODES = {"breast_lump", "breast_shape_change", "nipple_discharge", "nipple_retraction", "breast_skin_change", "axillary_lump", "breast_pain"}
_LEX_SRC.update(_BREAST_SRC)

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


# ── Intake parsing: age / birth year, "when was your last mammogram?", yes / no / don't know ──
from datetime import date, timedelta  # noqa: E402

_UNKNOWN = [fold(x) for x in (
    "ما اعرف", "لا اعرف", "ما بعرف", "مش عارف", "مش عارفه", "ما ادري", "مدري", "مش متاكد", "مش متأكد", "ما اتذكر", "ما اذكر",
    "ما بتذكر", "ما بذكر", "مش فاكر", "مش فاكره", "ما اتذكر", "ما فاكر",
    "don t know", "dont know", "do not know", "not sure", "unsure", "no idea", "don t remember", "dont remember", "can t remember", "forgot")]
_WHEN_UNKNOWN = _UNKNOWN + [fold("نسيت"), fold("نسيتها")]
_NEVER = [fold(x) for x in (
    "ابدا", "أبدا", "مطلقا", "ما عملت", "ما اعملت", "ما سويت", "ما عمل", "ولا مره", "اول مره", "لسا ما", "لسه ما", "لم افعل",
    "لم اجر", "لم اجري", "ما اجريت", "ما اجري", "ما قمت", "لم اقم", "لا يوجد", "مافي", "ما في",
    "never", "not yet", "haven t", "have not", "didn t", "did not")]

_MONTHS = {fold(k): v for k, v in {
    "كانون الثاني": 1, "شباط": 2, "اذار": 3, "آذار": 3, "نيسان": 4, "ايار": 5, "أيار": 5, "حزيران": 6, "تموز": 7, "اب": 8, "آب": 8,
    "ايلول": 9, "أيلول": 9, "تشرين الاول": 10, "تشرين الأول": 10, "تشرين الثاني": 11, "كانون الاول": 12, "كانون الأول": 12,
    "يناير": 1, "فبراير": 2, "مارس": 3, "ابريل": 4, "أبريل": 4, "مايو": 5, "يونيو": 6, "يوليو": 7, "اغسطس": 8, "أغسطس": 8,
    "سبتمبر": 9, "اكتوبر": 10, "أكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8, "september": 9,
    "october": 10, "november": 11, "december": 12, "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12}.items()}
_NUM_WORDS = {fold(k): v for k, v in {"سنه": 1, "سنتين": 2, "سنتان": 2, "شهر": 1, "شهرين": 2, "اسبوع": 1, "اسبوعين": 2,
                                      "a": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}.items()}


def parse_birth_year(text: str, this_year: int) -> int | None:
    """'45' → this_year-45 (age) ; '1981' → 1981 (birth year). Returns None if neither."""
    for n in re.findall(r"\d+", prepare(text)):
        v = int(n)
        if 1900 <= v <= this_year:
            return v
        if 10 <= v <= 120:
            return this_year - v
    return None


def _shift(today: date, years: int = 0, months: int = 0, days: int = 0) -> date:
    m = today.month - 1 - months - years * 12
    y, mo = today.year + m // 12, m % 12 + 1
    return (date(y, mo, min(today.day, 28)) - timedelta(days=days))


def parse_when(text: str, today: date) -> tuple[str, date | None]:
    """→ ('date', d) | ('never', None) | ('unknown', None) | ('bad', None)."""
    p = prepare(text)
    if not p:
        return "bad", None
    if any(u in p for u in _WHEN_UNKNOWN):
        return "unknown", None
    if p in ("لا", "no") or any(n in p for n in _NEVER):
        return "never", None
    # relative: "قبل سنتين", "قبل 3 سنين", "6 months ago", "last year"
    m = re.search(r"(?:قبل|من|منذ)\s*(\d+|سنه|سنتين|سنتان|شهر|شهرين|اسبوع|اسبوعين)\s*(سنه|سنين|سنوات|شهر|اشهر|شهور|اسبوع|اسابيع)?", p)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else _NUM_WORDS[m.group(1)]
        unit = m.group(2) or m.group(1)
        if "سن" in unit:
            return "date", _shift(today, years=n)
        if "شهر" in unit or "اشهر" in unit or "شهور" in unit:
            return "date", _shift(today, months=n)
        return "date", today - timedelta(weeks=n)
    m = re.search(r"(\d+|a|one|two|three|four|five)\s*(year|month|week)s?\s*ago", p)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else _NUM_WORDS[m.group(1)]
        return "date", (_shift(today, years=n) if m.group(2) == "year" else _shift(today, months=n) if m.group(2) == "month" else today - timedelta(weeks=n))
    if "last year" in p or "العام الماضي" in p or fold("السنه الماضيه") in p or fold("السنة الماضية") in p:
        return "date", _shift(today, years=1)
    year = re.search(r"\b(19\d{2}|20\d{2})\b", p)
    month = next((v for k, v in sorted(_MONTHS.items(), key=lambda kv: -len(kv[0])) if re.search(rf"(?<![\w]){re.escape(k)}(?![\w])", p)), None)
    m2 = re.search(r"\b(\d{1,2})[/\-.](19\d{2}|20\d{2})\b", p)
    try:
        if m2:
            d = date(int(m2.group(2)), int(m2.group(1)), 15)
        elif year and month:
            d = date(int(year.group(1)), month, 15)
        elif year:
            d = date(int(year.group(1)), 7, 1)      # year only → mid-year (flagged as approximate by the caller)
        else:
            return "bad", None
    except ValueError:
        return "bad", None
    return ("bad", None) if d > today else ("date", d)


def parse_yes_no_unknown(text: str):
    """→ True | False | 'unknown' | None (unclear)."""
    p = prepare(text)
    if any(u in p for u in _UNKNOWN):
        return "unknown"
    return parse_yes_no(text)
