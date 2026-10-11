"""All patient-facing and clinician-facing text.

Dialect templates are a first draft for engineering demo purposes. Before any
patient deployment they MUST be reviewed by native speakers of each dialect and
by clinicians (tone, gender agreement, medical wording).

Gendered 2nd-person verbs use {f}: "" for male patients, "ي" for female.
"""
from __future__ import annotations

DIALECTS = {
    "levantine": "شامي",
    "gulf": "خليجي",
    "egyptian": "مصري",
    "maghrebi": "مغاربي",
    "msa": "فصحى",
}

T: dict[str, dict[str, str]] = {
    "levantine": {
        "greet": "صباح الخير {name} 🌞\nأنا رفيق، مساعدك الصحي. يلا نعمل متابعة اليوم، بتاخد دقيقة.",
        "hello": "أهلين {name} 👋 أنا رفيق. خلينا نسجل قراءاتك.",
        "ask_glucose": "قديش قراءة السكر اليوم؟ اكتب{f} الرقم أو ابعت صورة الجهاز 📷",
        "ask_bp": "قديش قراءة الضغط؟ مثلاً: 130/85 (أو ابعت صورة الجهاز)",
        "ask_symptoms": "في شي عم يتعبك اليوم؟ (وجع، دوخة، ضيق نفس، غثيان...) أو اكتب{f} «لا»",
        "ask_meds": "أخدت{f} أدويتك اليوم؟ (إيه / لا)",
        "unclear": "ما فهمت عليك 🙏 ممكن تعيد{f}؟",
        "unclear_reading": "ما قدرت أقرا الرقم 🙏 اكتبو بالأرقام، مثلاً: {example}",
        "done_normal": "تمام الحمدلله 👏 قراءاتك منيحة اليوم. كمّل{f} على هالمنوال، وبنحكي بكرا.",
        "done_watch": "شكراً {name}. في شي بدنا نتابعو، وبعتنا التفاصيل للدكتور ليتواصل معك.{actions}",
        "done_urgent": "⚠️ {name}، اللي حكيتو مهم وبدو انتباه هلأ.{actions}\nبلّغنا الدكتور فوراً.",
        "med_reminder": "تذكير 💊 وقت دوا {med}. لما تخلص اكتب{f} «تم».",
        "nudge": "صباح النور {name}، لسا ما سجلنا قراءاتك اليوم. كمّل{f} وقت ما تكون جاهز 🌿",
    },
    "gulf": {
        "greet": "صباح الخير {name} 🌞\nمعك رفيق، مساعدك الصحي. نسوي متابعة اليوم، ما تاخذ إلا دقيقة.",
        "hello": "هلا {name} 👋 معك رفيق. خلنا نسجل قراءاتك.",
        "ask_glucose": "كم قراءة السكر اليوم؟ اكتب{f} الرقم أو أرسل{f} صورة الجهاز 📷",
        "ask_bp": "كم قراءة الضغط؟ مثلاً: 130/85 (أو أرسل{f} صورة الجهاز)",
        "ask_symptoms": "فيه شي يتعبك اليوم؟ (وجع، دوخة، ضيق نفس، غثيان...) أو اكتب{f} «لا»",
        "ask_meds": "أخذت{f} أدويتك اليوم؟ (إي / لا)",
        "unclear": "ما فهمت عليك 🙏 ممكن تعيد{f}؟",
        "unclear_reading": "ما قدرت أقرأ الرقم 🙏 اكتبه بالأرقام، مثلاً: {example}",
        "done_normal": "الحمد لله 👏 قراءاتك زينة اليوم. استمر{f}، ونكلمك باجر.",
        "done_watch": "شكراً {name}. فيه شي نبي نتابعه، وأرسلنا التفاصيل للدكتور عشان يتواصل معك.{actions}",
        "done_urgent": "⚠️ {name}، اللي ذكرته مهم ويحتاج انتباه الحين.{actions}\nأبلغنا الدكتور فوراً.",
        "med_reminder": "تذكير 💊 وقت دواء {med}. إذا خلصت اكتب{f} «تم».",
        "nudge": "صباح النور {name}، للحين ما سجلنا قراءاتك اليوم. كمّل{f} وقت ما تقدر 🌿",
    },
    "egyptian": {
        "greet": "صباح الخير يا {name} 🌞\nأنا رفيق، مساعدك الصحي. يلا نعمل متابعة النهارده، مش هتاخد دقيقة.",
        "hello": "أهلاً يا {name} 👋 أنا رفيق. يلا نسجل قراءاتك.",
        "ask_glucose": "قراءة السكر كام النهارده؟ اكتب{f} الرقم أو ابعت{f} صورة الجهاز 📷",
        "ask_bp": "قراءة الضغط كام؟ مثلاً: 130/85 (أو ابعت{f} صورة الجهاز)",
        "ask_symptoms": "فيه أي أعراض النهارده؟ (وجع، دوخة، ضيق نفس، غثيان...) أو اكتب{f} «لا»",
        "ask_meds": "أخدت{f} الدوا النهارده؟ (أيوه / لا)",
        "unclear": "مفهمتش 🙏 ممكن تعيد{f}؟",
        "unclear_reading": "مقدرتش أقرا الرقم 🙏 اكتبه بالأرقام، مثلاً: {example}",
        "done_normal": "الحمد لله 👏 قراءاتك كويسة النهارده. كمّل{f} كده، ونتكلم بكره.",
        "done_watch": "شكراً يا {name}. فيه حاجة محتاجين نتابعها، وبعتنا التفاصيل للدكتور عشان يتواصل معاك.{actions}",
        "done_urgent": "⚠️ يا {name}، اللي قلته مهم ومحتاج اهتمام حالاً.{actions}\nبلّغنا الدكتور فوراً.",
        "med_reminder": "تذكير 💊 ميعاد دوا {med}. لما تخلص اكتب{f} «تم».",
        "nudge": "صباح الخير يا {name}، لسه معملناش متابعة النهارده. كمّل{f} وقت ما تقدر 🌿",
    },
    "maghrebi": {
        "greet": "صباح الخير {name} 🌞\nأنا رفيق، المساعد الصحي ديالك. نديرو المتابعة ديال اليوم، غير دقيقة.",
        "hello": "مرحبا {name} 👋 أنا رفيق. يالله نسجلو القراءات ديالك.",
        "ask_glucose": "شحال خرج ليك السكر اليوم؟ كتب{f} الرقم أو صيفط{f} تصويرة ديال الجهاز 📷",
        "ask_bp": "شحال خرج ليك الضغط؟ مثلا: 130/85 (أو صيفط{f} تصويرة ديال الجهاز)",
        "ask_symptoms": "واش كاين شي حاجة كتعييك اليوم؟ (وجع، دوخة، ضيق نفس، غثيان...) أو كتب{f} «لا»",
        "ask_meds": "واش خديتي الدوا ديالك اليوم؟ (إيه / لا)",
        "unclear": "ما فهمتش 🙏 عاود{f} ليا من فضلك",
        "unclear_reading": "ما قدرتش نقرا الرقم 🙏 كتبو بالأرقام، مثلا: {example}",
        "done_normal": "الحمد لله 👏 القراءات ديالك زوينة اليوم. كمل{f} هكا، ونهضرو غدا.",
        "done_watch": "شكرا {name}. كاين شي حاجة خاصنا نتبعوها، وصيفطنا التفاصيل للطبيب باش يتواصل معاك.{actions}",
        "done_urgent": "⚠️ {name}، اللي قلتي مهم وخاصو اهتمام دابا.{actions}\nعلمنا الطبيب مباشرة.",
        "med_reminder": "تذكير 💊 وقت الدوا ديال {med}. ملي تسالي كتب{f} «تم».",
        "nudge": "صباح الخير {name}، باقي ما سجلناش القراءات ديال اليوم. كمل{f} ملي تقدر 🌿",
    },
    "msa": {
        "greet": "صباح الخير {name} 🌞\nأنا «رفيق»، مساعدك الصحي. لنُجرِ متابعة اليوم، تستغرق دقيقة.",
        "hello": "أهلًا {name} 👋 أنا «رفيق». لنسجّل قراءاتك.",
        "ask_glucose": "ما قراءة السكر اليوم؟ اكتب{f} الرقم أو أرسل{f} صورة الجهاز 📷",
        "ask_bp": "ما قراءة ضغط الدم؟ مثلًا: 130/85 (أو أرسل{f} صورة الجهاز)",
        "ask_symptoms": "هل لديك أي أعراض اليوم؟ (ألم، دوخة، ضيق نفس، غثيان...) أو اكتب{f} «لا»",
        "ask_meds": "هل تناولت{f} أدويتك اليوم؟ (نعم / لا)",
        "unclear": "لم أفهم رسالتك 🙏 هل يمكنك إعادتها؟",
        "unclear_reading": "لم أستطع قراءة الرقم 🙏 اكتبه بالأرقام، مثلًا: {example}",
        "done_normal": "الحمد لله 👏 قراءاتك جيدة اليوم. واصل{f} على ذلك، ونتحدث غدًا.",
        "done_watch": "شكرًا {name}. هناك أمر نريد متابعته، وقد أرسلنا التفاصيل إلى الطبيب ليتواصل معك.{actions}",
        "done_urgent": "⚠️ {name}، ما ذكرته مهم ويحتاج إلى اهتمام الآن.{actions}\nأبلغنا الطبيب فورًا.",
        "med_reminder": "تذكير 💊 حان موعد دواء {med}. بعد تناوله اكتب{f} «تم».",
        "nudge": "صباح الخير {name}، لم نسجّل قراءاتك اليوم بعد. أكمل{f} متى استطعت 🌿",
    },
}

# Dialect-neutral simple Arabic (needs clinical sign-off — these are clinical instructions).
SHARED = {
    "welcome_consent": (
        "مرحبًا {name}، أنا «رفيق»، مساعد صحي من {clinic}. أساعدك في تسجيل قراءات السكر/الضغط وتذكيرك بأدويتك، "
        "وأرسل أي قراءة غير طبيعية إلى طبيبك.\n"
        "⚠️ لست بديلًا عن الطبيب ولا أصلح للحالات الطارئة.\n"
        "بياناتك سرية وتُستخدم فقط لمتابعتك.\n"
        "للموافقة اكتب «نعم»، وللإيقاف في أي وقت اكتب «إيقاف»."
    ),
    "consent_ok": "شكرًا ✅ تم تفعيل المتابعة. لإيقافها في أي وقت اكتب «إيقاف».",
    "consent_reask": "هل توافق على المتابعة؟ اكتب «نعم» للموافقة أو «إيقاف» لعدم الموافقة.",
    "stopped": "تم إيقاف الرسائل. لن نرسل لك شيئًا بعد الآن. يمكنك مراجعة المركز الصحي لإعادة التفعيل.",
    "not_registered": "رقمك غير مسجل في البرنامج. يرجى مراجعة المركز الصحي للتسجيل.",
    "audio_unsupported": "وصلتني رسالتك الصوتية 🎤 لكن لا أستطيع سماعها حاليًا. هل يمكنك كتابة الرقم أو الرد نصيًا؟",
    "ocr_confirm": "قرأت من الصورة: {value}\nهل هذا صحيح؟ (نعم / لا)",
    "ocr_fail": "لم أستطع قراءة الصورة بوضوح 🙏 اكتب الرقم من فضلك.",
    "image_idle": "وصلتني الصورة 📷 لتسجيل قراءة، أرسل «ابدأ» أولًا.",
    "implausible": "الرقم ({value}) يبدو غير معتاد. أعد القياس ثم اكتب القراءة مرة أخرى 🙏",
    "ack_saved": "تم تسجيل ✅",
    "help": "أنا «رفيق». أرسل قراءاتك عند الطلب، واكتب «إيقاف» لإيقاف الرسائل. في الحالات الطارئة اتصل بالإسعاف على {emergency}.",
    "followup_urgent": "هل أنت بخير الآن؟ هل وصلت إلى المساعدة؟ اكتب لي ردًا من فضلك 🙏",
    "reminder_missed_ack": "لا بأس. إذا كان الدواء ما زال مناسبًا لوقته فتناوله، ولا تضاعف الجرعة. واسأل طبيبك أو الصيدلي عند الشك.",
    "reminder_ok_ack": "ممتاز ✅",
    "self_harm": (
        "أنا آسف أنك تمر بهذا الشعور 💙 سلامتك أهم شيء. من فضلك لا تبقَ وحدك: تواصل الآن مع شخص قريب تثق به، "
        "أو اتصل بالطوارئ على {emergency}. أبلغنا طبيبك ليتواصل معك."
    ),
    # clinical action lines
    "act_eat_fast_sugar": "تناول 15 غرامًا من السكر السريع الآن (نصف كوب عصير أو 3 ملاعق صغيرة سكر).",
    "act_recheck_15min": "أعد قياس السكر بعد 15 دقيقة.",
    "act_call_if_worse": "إذا ساءت حالتك أو لم تتحسن، اتصل بالإسعاف على {emergency}.",
    "act_call_emergency": "اتصل بالإسعاف الآن على {emergency} أو اطلب من شخص قريب مساعدتك.",
    "act_crisis_support": "لست وحدك. تواصل مع شخص تثق به الآن.",
    "act_drink_water": "اشرب ماءً.",
    "act_contact_clinic_now": "سيتواصل معك الطبيب قريبًا؛ إن لم يحدث ذلك فاتصل بالمركز الصحي الآن.",
    "act_contact_clinic_today": "سيتابع معك الطبيب اليوم.",
    "act_rest_recheck_bp": "اجلس واسترح 5 دقائق ثم أعد قياس الضغط.",
}

CHIP_EXAMPLES = {"glucose": "120", "bp": "130/85"}


def _f(gender: str) -> str:
    return "ي" if gender == "f" else ""


def tr(key: str, dialect: str, gender: str = "m", **kw) -> str:
    table = T.get(dialect) or T["msa"]
    tpl = table.get(key) or T["msa"].get(key) or SHARED[key]
    kw.setdefault("f", _f(gender))
    kw.setdefault("name", "")
    return tpl.format(**kw)


def shared(key: str, **kw) -> str:
    return SHARED[key].format(**kw)


def actions_block(actions: list[str], emergency_no: str) -> str:
    lines = []
    for a in actions:
        tpl = SHARED.get(f"act_{a}")
        if tpl:
            lines.append("• " + tpl.format(emergency=emergency_no))
    return ("\n" + "\n".join(lines)) if lines else ""


# ── Clinician-facing text ───────────────────────────────────────────────────
SYMPTOM_NAMES = {
    "chest_pain": ("chest pain", "ألم في الصدر"), "breathless": ("shortness of breath", "ضيق نفس"),
    "fainting": ("fainting / loss of consciousness", "إغماء"), "stroke_signs": ("possible stroke signs", "علامات جلطة دماغية محتملة"),
    "confusion": ("confusion", "تشوش ذهني"), "seizure": ("seizure", "نوبة تشنج"),
    "vomiting_persistent": ("persistent vomiting", "قيء متكرر"), "self_harm": ("self-harm / suicidal statement", "أفكار إيذاء النفس"),
    "dizziness": ("dizziness", "دوخة"), "blurred_vision": ("blurred vision", "زغللة"), "headache": ("headache", "صداع"),
    "thirst": ("excessive thirst", "عطش شديد"), "frequent_urination": ("frequent urination", "تبول متكرر"),
    "fatigue": ("fatigue", "تعب"), "leg_swelling": ("leg swelling", "تورم الساقين"),
    "foot_numbness": ("numbness/tingling", "تنميل"), "foot_wound": ("foot wound", "جرح في القدم"),
    "nausea": ("nausea", "غثيان"), "vomiting": ("vomiting", "قيء"), "abdominal_pain": ("abdominal pain", "ألم بطن"),
    "palpitations": ("palpitations", "خفقان"), "shaking_sweating": ("shaking/sweating", "رجفة وتعرق"),
    "fall": ("fall", "سقوط"), "cramps": ("cramps", "تشنج عضلي"),
}


def _sym(codes: list[str], lang: str) -> str:
    i = 0 if lang == "en" else 1
    return ", ".join(SYMPTOM_NAMES.get(c, (c, c))[i] for c in codes)


def reason_text(r: dict, lang: str) -> str:
    c, d = r["code"], r.get("data", {})
    en = lang == "en"
    if c == "red_flag_symptom":
        n = _sym([d["symptom"]], lang)
        return f"Red-flag symptom: {n}" if en else f"عَرَض خطير: {n}"
    if c == "glucose_low_severe":
        return f"Severe low glucose {d['value']:.0f} mg/dL" if en else f"هبوط شديد في السكر {d['value']:.0f} ملغ/دل"
    if c == "glucose_low":
        return f"Low glucose {d['value']:.0f} mg/dL" if en else f"انخفاض السكر {d['value']:.0f} ملغ/دل"
    if c == "glucose_low_symptoms":
        return f"Low glucose {d['value']:.0f} mg/dL with hypoglycaemia symptoms" if en else f"انخفاض السكر {d['value']:.0f} مع أعراض هبوط"
    if c == "glucose_very_high":
        return f"Very high glucose {d['value']:.0f} mg/dL" if en else f"ارتفاع شديد في السكر {d['value']:.0f} ملغ/دل"
    if c == "glucose_high_symptoms":
        return f"High glucose {d['value']:.0f} mg/dL with GI/breathing symptoms" if en else f"ارتفاع السكر {d['value']:.0f} مع أعراض هضمية/تنفسية"
    if c == "glucose_high":
        ctx = d.get("context", "fasting").replace("_", "-")
        return f"Glucose {d['value']:.0f} mg/dL above {ctx} target" if en else f"السكر {d['value']:.0f} فوق الهدف"
    if c == "bp_very_high":
        return f"Very high BP {d['sys']}/{d['dia']}" if en else f"ضغط مرتفع جدًا {d['sys']}/{d['dia']}"
    if c == "bp_high_symptoms":
        return f"High BP {d['sys']}/{d['dia']} with symptoms" if en else f"ضغط مرتفع {d['sys']}/{d['dia']} مع أعراض"
    if c == "bp_high":
        return f"BP above target {d['sys']}/{d['dia']}" if en else f"الضغط فوق الهدف {d['sys']}/{d['dia']}"
    if c == "bp_low_symptoms":
        return f"Low BP {d['sys']}/{d['dia']} with dizziness/fainting" if en else f"ضغط منخفض {d['sys']}/{d['dia']} مع دوخة/إغماء"
    if c == "bp_low":
        return f"Low BP {d['sys']}/{d['dia']}" if en else f"ضغط منخفض {d['sys']}/{d['dia']}"
    if c == "symptoms":
        return f"Symptoms: {_sym(d['symptoms'], lang)}" if en else f"أعراض: {_sym(d['symptoms'], lang)}"
    if c == "free_text":
        return f"Unclassified complaint (verbatim): “{d['text']}”" if en else f"شكوى غير مصنّفة (بنصّها): «{d['text']}»"
    if c == "missed_meds":
        return f"Missed medication ({d['days']} day(s) in a row)" if en else f"نسيان الدواء ({d['days']} يوم متتالٍ)"
    if c == "trend_rising":
        m = {"glucose": ("glucose", "السكر"), "bp_sys": ("systolic BP", "الضغط الانقباضي")}[d["metric"]]
        return (f"Rising {m[0]} trend: {d['from']} → {d['to']}" if en else f"اتجاه صاعد في {m[1]}: {d['from']} ← {d['to']}")
    if c == "sustained_high":
        m = {"glucose": ("glucose", "السكر"), "bp_sys": ("systolic BP", "الضغط")}[d["metric"]]
        return f"{m[0][0].upper() + m[0][1:]} above target for {d['n']} readings in a row" if en else f"{m[1]} فوق الهدف في {d['n']} قراءات متتالية"
    if c == "no_contact":
        return f"No completed check-in for {d['days']} days" if en else f"لا توجد متابعة مكتملة منذ {d['days']} أيام"
    if c == "no_response_after_urgent":
        return "No reply after urgent safety message" if en else "لا رد بعد رسالة السلامة العاجلة"
    return c


def clinician_summary(patient: dict, level_label: str, reasons: list[dict], hist: dict, lang: str) -> str:
    """Short, prioritised summary: who, how urgent, why, recent trend."""
    head_en = {"urgent": "URGENT", "watch": "WATCH", "normal": "OK"}[level_label]
    head_ar = {"urgent": "عاجل", "watch": "مراقبة", "normal": "طبيعي"}[level_label]
    head = head_en if lang == "en" else head_ar
    lines = [f"[{head}] {patient['name']}"]
    shown = [r for r in reasons if r["level"] > 0] or reasons
    shown = sorted(shown, key=lambda r: -r["level"])
    for r in shown:
        lines.append("• " + reason_text(r, lang))
    if hist.get("glucose"):
        lines.append(("Last glucose: " if lang == "en" else "آخر قراءات السكر: ") + ", ".join(f"{x:.0f}" for x in hist["glucose"][-7:]))
    if hist.get("bp"):
        lines.append(("Last BP: " if lang == "en" else "آخر قراءات الضغط: ") + ", ".join(hist["bp"][-5:]))
    return "\n".join(lines)
