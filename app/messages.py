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
    "en": "English",
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
        "ask_intake_age": "لنُكمل ملفك الصحي بأسئلة قصيرة تساعدنا على تخصيص خطة فحصك. كم عمرك؟ (أو اكتب{f} سنة ميلادك)",
        "ask_intake_family": "هل أُصيبت أمك أو أختك أو ابنتك بسرطان الثدي أو المبيض؟ (نعم / لا / لا أعرف)",
        "ask_intake_atypia": "هل أجريت{f} خزعة من الثدي أظهرت خلايا غير طبيعية، أو أخبرك طبيب أنك أكثر عرضة للإصابة؟ (نعم / لا / لا أعرف)",
        "ask_intake_gene": "هل أخبرك طبيب أنك تحمل{f} تغيرًا جينيًا مثل BRCA1 أو BRCA2؟ (نعم / لا / لا أعرف)",
        "ask_intake_radiation": "هل تلقيت{f} علاجًا إشعاعيًا للصدر في أي وقت (مثل علاج الغدد اللمفاوية)؟ (نعم / لا / لا أعرف)",
        "ask_intake_mammo": "متى كان آخر تصوير ماموغرام لك؟ (مثلًا: مارس 2024، أو «قبل سنتين»، أو «لم أجرِ تصويرًا»، أو «لا أذكر»)",
        "intake_bad_age": "أرسل{f} عمرك رقمًا (مثل 45) أو سنة ميلادك (مثل 1981) من فضلك.",
        "intake_minor": "هذه الخدمة مخصصة لمن بلغن 18 عامًا فأكثر. يُرجى مراجعة الطبيب لأي استفسار.",
        "intake_bad_when": "لم أفهم التاريخ 🙏 اكتب{f} الشهر والسنة (مثل: مارس 2024)، أو «لم أجرِ تصويرًا»، أو «لا أذكر».",
        "intake_unclear_yn": "أجب{f} بـ «نعم» أو «لا» أو «لا أعرف» من فضلك.",
        "intake_done_not_yet": "شكرًا لك 🌸 تبدأ فحوصات الماموغرام الدورية عادةً في سن لاحقة. الأهم الآن أن تعرف{f} شكل ثدييك ومظهرهما الطبيعي وأن تخبرني بأي تغيير. سأتواصل معك شهريًا.",
        "intake_done_up_to_date": "شكرًا لك 🌸 فحصك الأخير حديث، وموعد الفحص القادم في حدود {due}. سأتواصل معك شهريًا.",
        "intake_done_due_soon": "شكرًا لك 🌸 موعد فحص الماموغرام القادم في حدود {due}. سأذكّرك به، وسأتواصل معك شهريًا.",
        "intake_done_due": "شكرًا لك 🌸 حان موعد فحص الماموغرام. يُرجى حجز موعد في المركز الصحي، وسأذكّرك وأتابع معك.",
        "intake_done_overdue": "شكرًا لك 🌸 تأخر موعد فحص الماموغرام. يُرجى حجز موعد في المركز الصحي في أقرب وقت، وسأذكّرك وأتابع معك.",
        "intake_done_specialist_plan": "شكرًا لك 🌸 إجاباتك تعني أنك قد تحتاج{f} إلى خطة فحص خاصة بك. أبلغنا طبيب المركز ليراجعها ويتواصل معك.",
        "intake_done_individualised": "شكرًا لك 🌸 بعد هذا العمر يُحدَّد الفحص حسب كل حالة، وسيوجّهك طبيبك. أخبرني بأي تغيير في الثدي.",
        "intake_done_unknown": "شكرًا لك 🌸 سأتواصل معك شهريًا، وأخبرني فورًا بأي تغيير في الثدي.",
        "ask_breast_checked": "المتابعة الشهرية 🌸 هل فحصت{f} ثدييك هذا الشهر بالنظر واللمس، مع منطقة تحت الإبط؟ (نعم / لا)",
        "breast_checked_no": "لا بأس. الأمر يستغرق دقائق: انظر{f} في المرآة، ثم تحسّس{f} كل ثدي ومنطقة الإبط بحثًا عن أي شيء جديد (كتلة، سماكة، تغيّر في الجلد أو الحلمة). افعل{f} ذلك اليوم إن أمكن.",
        "ask_breast_symptoms": "هل لاحظت{f} أي تغيير في الثدي أو تحت الإبط؟ (كتلة أو سماكة، إفرازات أو انسحاب الحلمة، تجعّد أو احمرار الجلد، تغيّر الحجم أو الشكل، ألم جديد) — أو اكتب{f} «لا».",
        "ask_breast_detail": "هل يمكنك وصف التغيير؟ (مثلًا: كتلة في الثدي الأيسر، أو إفرازات من الحلمة)",
        "done_breast_normal": "شكرًا لك 🌸 لا يوجد في ما ذكرته ما يستدعي متابعة عاجلة. تذكّر{f}: هذا لا يغني عن الفحص الدوري ولا عن فحص الطبيب، وإن لاحظت{f} أي تغيير لاحقًا فأخبرني فورًا.{screening}",
        "done_breast_watch": "شكرًا لأنك أخبرتني. سنطلب من العيادة متابعة الأمر.{actions}",
        "done_breast_urgent": "شكرًا لأنك أخبرتني، ولا تنتظر{f}. معظم تغيرات الثدي ليست سرطانًا، لكنها تحتاج إلى فحص قريب.{actions}",
        "screening_reminder": "تذكير 🌸 حان موعد فحص الماموغرام الدوري. يُرجى حجز موعد في المركز الصحي. هل حجزت{f}؟ (نعم / لا)",
        "screening_booked_ack": "ممتاز، شكرًا لك 🌸",
        "screening_nobook_ack": "لا بأس. احجز{f} حين تستطيع؛ يمكن للعيادة مساعدتك. سأذكّرك مجددًا لاحقًا.",
        "referral_chase": "مرحبًا {name}، هل تم ترتيب موعدك في العيادة؟ (نعم / لا)",
        "referral_booked_ack": "شكرًا لك. نتمنى لك الخير 🌸",
        "referral_nobook_ack": "شكرًا لإخبارنا. سنطلب من العيادة الاتصال بك في أقرب وقت.",
        "scr_due": "\nتذكير: حان موعد فحص الماموغرام، يُرجى حجزه.",
        "scr_overdue": "\nتأخر موعد فحص الماموغرام؛ يُرجى حجزه قريبًا.",
        "scr_due_soon": "\nموعد فحص الماموغرام القادم في حدود {due}.",
    },
}


T["en"] = {
    "greet": "Good morning {name} 🌞\nI'm Rafiq, your health companion. Let's do today's check-in; it takes a minute.",
    "hello": "Hello {name} 👋 I'm Rafiq. Let's get started.",
    "ask_glucose": "What's your blood sugar reading today? Type the number or send a photo of the meter 📷",
    "ask_bp": "What's your blood pressure? e.g. 130/85 (or send a photo of the monitor)",
    "ask_symptoms": "Any symptoms today? (pain, dizziness, shortness of breath, nausea…) or type “no”",
    "ask_meds": "Did you take your medication today? (yes / no)",
    "unclear": "I didn't catch that 🙏 could you say it again?",
    "unclear_reading": "I couldn't read the number 🙏 please type it in digits, e.g. {example}",
    "done_normal": "Great 👏 your readings look good today. Keep it up; talk tomorrow.",
    "done_watch": "Thank you {name}. There's something we'd like to follow up, and I've sent the details to your doctor.{actions}",
    "done_urgent": "⚠️ {name}, what you told me needs attention now.{actions}\nI've alerted your doctor right away.",
    "med_reminder": "Reminder 💊 time for your {med}. Reply “done” once you've taken it.",
    "nudge": "Good morning {name}, we haven't logged your check-in yet today. Continue whenever you're ready 🌿",
    "ask_intake_age": "Let's complete your health profile with a few short questions so we can personalise your screening plan. How old are you? (or type your birth year)",
    "ask_intake_family": "Has your mother, sister or daughter ever had breast or ovarian cancer? (yes / no / I don't know)",
    "ask_intake_atypia": "Have you ever had a breast biopsy showing abnormal cells, or been told by a doctor that you're at higher risk of breast cancer? (yes / no / I don't know)",
    "ask_intake_gene": "Have you been told you carry a BRCA1, BRCA2 or similar gene change? (yes / no / I don't know)",
    "ask_intake_radiation": "Have you ever had radiation treatment to the chest (for example for lymphoma)? (yes / no / I don't know)",
    "ask_intake_mammo": "When was your last mammogram? (e.g. “March 2024”, “2 years ago”, “never”, or “I don't remember”)",
    "intake_bad_age": "Please send your age as a number (e.g. 45) or your birth year (e.g. 1981).",
    "intake_minor": "This service is for adults aged 18 and over. Please speak to a doctor if you have any concerns.",
    "intake_bad_when": "I didn't understand that date 🙏 please write the month and year (e.g. March 2024), “never”, or “I don't remember”.",
    "intake_unclear_yn": "Please answer “yes”, “no” or “I don't know”.",
    "intake_done_not_yet": "Thank you 🌸 Routine mammograms usually start at a later age. What matters most now is knowing how your breasts normally look and feel, and telling me about any change. I'll check in monthly.",
    "intake_done_up_to_date": "Thank you 🌸 Your last screening is recent; your next one is due around {due}. I'll check in monthly.",
    "intake_done_due_soon": "Thank you 🌸 Your next mammogram is due around {due}. I'll remind you, and I'll check in monthly.",
    "intake_done_due": "Thank you 🌸 A screening mammogram is due now. Please book it at your clinic. I'll remind you and help track it.",
    "intake_done_overdue": "Thank you 🌸 Your screening mammogram is overdue. Please book it at your clinic as soon as you can. I'll remind you and help track it.",
    "intake_done_specialist_plan": "Thank you 🌸 Your answers mean you may need a personalised screening plan. I've asked your clinic's doctor to review it and contact you.",
    "intake_done_individualised": "Thank you 🌸 At this age screening is decided case by case, and your doctor will guide you. Tell me about any breast change.",
    "intake_done_unknown": "Thank you 🌸 I'll check in monthly. Tell me right away about any change in your breasts.",
    "ask_breast_checked": "Monthly check-in 🌸 Did you check your breasts this month, looking and feeling, including under the arms? (yes / no)",
    "breast_checked_no": "No problem. It takes a few minutes: look in a mirror, then feel each breast and under each arm for anything new (a lump, thickening, skin or nipple change). Do it today if you can.",
    "ask_breast_symptoms": "Have you noticed any change in your breasts or underarms? (a lump or thickening, nipple discharge or turning inward, skin dimpling or redness, change in size or shape, new pain) or type “no”.",
    "ask_breast_detail": "Could you describe the change? (for example: a lump in the left breast, or nipple discharge)",
    "done_breast_normal": "Thank you 🌸 Nothing you told me needs urgent follow-up. Remember: this doesn't replace regular screening or a doctor's examination, and if you notice any change later, tell me straight away.{screening}",
    "done_breast_watch": "Thank you for telling me. I'll ask your clinic to follow this up.{actions}",
    "done_breast_urgent": "Thank you for telling me, and please don't wait. Most breast changes are not cancer, but this needs to be checked soon.{actions}",
    "screening_reminder": "Reminder 🌸 your routine screening mammogram is due. Please book it at your clinic. Have you booked? (yes / no)",
    "screening_booked_ack": "Great, thank you 🌸",
    "screening_nobook_ack": "No problem. Please book when you can; your clinic can help. I'll remind you again later.",
    "referral_chase": "Hello {name}, has your clinic appointment been arranged? (yes / no)",
    "referral_booked_ack": "Thank you. Wishing you well 🌸",
    "referral_nobook_ack": "Thanks for letting us know. I'll ask the clinic to call you as soon as possible.",
    "scr_due": "\nReminder: your screening mammogram is due; please book it.",
    "scr_overdue": "\nYour screening mammogram is overdue; please book it soon.",
    "scr_due_soon": "\nYour next mammogram is due around {due}.",
}

SHARED_EN = {
    "welcome_registered_official": (
        "Welcome {name} 👋 You're registered in Rafiq, {programme}: an official service of {clinic}.\n"
        "This message comes from our official service. We will never ask for your password or any payment.{contact}\n"
        "If you didn't create this account, reply “stop” and tell the clinic."),
    "welcome_registered": (
        "Welcome {name} 👋 You're registered in Rafiq, {programme}, run by {clinic}.\n"
        "We will never ask for your password or any payment.{contact}\nIf you didn't create this account, reply “stop” and tell the clinic."),
    "welcome_registered_demo": "Welcome {name} 👋 This is a DEMONSTRATION system with fictional data. It is not an official service.",
    "verify_code": "{clinic} (Rafiq) verification code: {code}. It expires in 15 minutes. We never ask for your password; if you didn't request this, ignore it.",
    "welcome_consent": (
        "Hello {name}, I'm Rafiq, a health companion from {clinic}. {what}\n"
        "⚠️ I'm not a doctor and can't diagnose anything or handle emergencies.\n"
        "Your information is confidential and used only for your care.\n"
        "Reply “yes” to agree, or “stop” at any time to opt out."
    ),
    "consent_ok": "Thank you ✅ You're set up. Reply “stop” at any time to stop messages.",
    "consent_reask": "Do you agree to take part? Reply “yes” to agree, or “stop” to decline.",
    "stopped": "Messages stopped. We won't send you anything more. Visit your clinic to turn them back on.",
    "not_registered": "This number isn't registered in the programme. Please visit your health centre to register.",
    "audio_unsupported": "I received your voice message 🎤 but can't listen to it yet. Could you type your reply?",
    "ocr_confirm": "I read from the photo: {value}\nIs that correct? (yes / no)",
    "ocr_fail": "I couldn't read the photo clearly 🙏 please type the number.",
    "image_idle": "I received the photo 📷 To record a reading, send “start” first.",
    "implausible": "That number ({value}) looks unusual. Please measure again and send the new reading 🙏",
    "ack_saved": "Saved ✅",
    "help": "I'm Rafiq. Reply to my questions, or type “stop” to stop messages. In an emergency call the ambulance on {emergency}.",
    "followup_urgent": "Are you okay now? Did you get help? Please reply 🙏",
    "reminder_missed_ack": "No problem. If it's still the right time for it, take it, but don't double the dose. Ask your doctor or pharmacist if unsure.",
    "reminder_ok_ack": "Great ✅",
    "self_harm": (
        "I'm sorry you're feeling this way 💙 Your safety matters most. Please don't stay alone: reach out now to someone you trust, "
        "or call emergency services on {emergency}. I've let your clinic know so they can contact you."
    ),
    "act_eat_fast_sugar": "Take 15 g of fast sugar now (half a cup of juice or 3 teaspoons of sugar).",
    "act_recheck_15min": "Re-check your sugar in 15 minutes.",
    "act_call_if_worse": "If you feel worse or don't improve, call the ambulance on {emergency}.",
    "act_call_emergency": "Call the ambulance now on {emergency}, or ask someone nearby to help you.",
    "act_crisis_support": "You're not alone. Reach out to someone you trust now.",
    "act_drink_water": "Drink some water.",
    "act_contact_clinic_now": "Your doctor will contact you soon; if not, call your health centre now.",
    "act_contact_clinic_today": "Your doctor will follow up today.",
    "act_rest_recheck_bp": "Sit and rest for 5 minutes, then re-check your blood pressure.",
    "act_see_clinic_prompt": "Your clinic will contact you within {days} working days to arrange a breast examination. If you haven't heard from them by {date}, please call the clinic.",
    "act_see_clinic_routine": "Please book a clinic visit within the next few weeks; your clinic has been informed.",
    "act_same_day_care": "A red, warm or very painful breast with fever should be seen today. Please go to your clinic or urgent care today.",
}

# Dialect-neutral simple Arabic (needs clinical sign-off — these are clinical instructions).
SHARED = {
    "welcome_registered_official": (
        "مرحبًا {name} 👋 تم تسجيلك في «رفيق»، {programme}، وهو خدمة رسمية من {clinic}.\n"
        "هذه الرسالة صادرة من خدمتنا الرسمية. لن نطلب منك أبدًا كلمة المرور أو أي مبلغ مالي.{contact}\n"
        "إن لم تُنشئ هذا الحساب بنفسك فردّ بكلمة «إيقاف» وأبلغ العيادة."),
    "welcome_registered": (
        "مرحبًا {name} 👋 تم تسجيلك في «رفيق»، {programme}، لدى {clinic}.\n"
        "لن نطلب منك أبدًا كلمة المرور أو أي مبلغ مالي.{contact}\nإن لم تُنشئ هذا الحساب بنفسك فردّ بكلمة «إيقاف» وأبلغ العيادة."),
    "welcome_registered_demo": "مرحبًا {name} 👋 هذا نظام تجريبي ببيانات وهمية، وليس خدمة رسمية.",
    "verify_code": "رمز التحقق من {clinic} (رفيق): {code}. ينتهي خلال 15 دقيقة. لن نطلب منك كلمة المرور أبدًا؛ إن لم تطلبه فتجاهل الرسالة.",
    "welcome_consent": (
        "مرحبًا {name}، أنا «رفيق»، مساعد صحي من {clinic}. {what}\n"
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
    "act_see_clinic_prompt": "ستتواصل معك العيادة خلال {days} أيام عمل لترتيب فحص سريري للثدي. وإن لم يصلك اتصال حتى {date} فيُرجى الاتصال بالعيادة.",
    "act_see_clinic_routine": "يُرجى حجز زيارة للعيادة خلال الأسابيع القادمة؛ وقد أبلغنا العيادة.",
    "act_same_day_care": "احمرار الثدي مع حرارة أو ألم شديد يحتاج إلى فحص اليوم نفسه. يُرجى التوجه إلى العيادة أو الطوارئ اليوم.",
}

CHIP_EXAMPLES = {"glucose": "120", "bp": "130/85"}


def _f(gender: str) -> str:
    return "ي" if gender == "f" else ""


def _lang(dialect: str) -> str:
    return "en" if dialect == "en" else "ar"


_DEFAULTS = {"programme": "", "what": "", "code": "", "contact": "", "name": "", "actions": "", "screening": "", "due": "", "days": "", "date": "", "example": "", "value": "", "med": ""}


def tr(key: str, dialect: str, gender: str = "m", **kw) -> str:
    if dialect == "en":
        tpl = T["en"].get(key) or SHARED_EN[key]
        kw.setdefault("f", "")
    else:
        table = T.get(dialect) or T["msa"]
        tpl = table.get(key) or T["msa"].get(key) or SHARED[key]
        kw.setdefault("f", _f(gender))
    for k, v in _DEFAULTS.items():
        kw.setdefault(k, v)
    return tpl.format(**kw)


def shared(key: str, lang: str = "ar", **kw) -> str:
    for k, v in _DEFAULTS.items():
        kw.setdefault(k, v)
    return (SHARED_EN if lang == "en" else SHARED)[key].format(**kw)


def actions_block(actions: list[str], emergency_no: str, lang: str = "ar", **kw) -> str:
    src = SHARED_EN if lang == "en" else SHARED
    lines = []
    for a in actions:
        tpl = src.get(f"act_{a}")
        if tpl:
            lines.append("• " + tpl.format(emergency=emergency_no, days=kw.get("days", ""), date=kw.get("date", "")))
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
    "breast_lump": ("breast lump / thickening", "كتلة أو سماكة في الثدي"), "breast_shape_change": ("change in breast size/shape", "تغيّر حجم أو شكل الثدي"),
    "nipple_discharge": ("nipple discharge", "إفرازات من الحلمة"), "nipple_retraction": ("nipple retraction / inversion", "انسحاب الحلمة"),
    "breast_skin_change": ("breast skin change (dimpling/redness/scaling)", "تغيّر جلد الثدي (تجعّد/احمرار/تقشّر)"),
    "axillary_lump": ("underarm lump / swollen nodes", "كتلة أو تورّم تحت الإبط"), "breast_pain": ("breast pain", "ألم في الثدي"), "fever": ("fever", "حرارة"),
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
    if c == "breast_concern":
        n = _sym(d["symptoms"], lang)
        return f"Breast change reported: {n}. Needs prompt clinical breast examination" if en else f"تغيّر في الثدي: {n}. يحتاج فحصًا سريريًا عاجلًا"
    if c == "breast_infection_signs":
        return "Red/inflamed breast with fever: same-day assessment" if en else "احمرار/التهاب في الثدي مع حرارة: تقييم في اليوم نفسه"
    if c == "breast_pain":
        return "Breast pain (isolated, no other change reported)" if en else "ألم في الثدي (دون تغيّر آخر)"
    if c == "elevated_risk":
        return "Patient is on the ELEVATED-risk pathway" if en else "المريضة ضمن مسار الخطورة المرتفعة"
    if c == "elevated_risk_review":
        return "Intake: elevated-risk history; an individual screening plan is needed" if en else "نتيجة الاستبيان: تاريخ مرتفع الخطورة؛ تلزم خطة فحص فردية"
    if c == "referral_unanswered":
        return f"Referral #{d['referral']}: patient not yet contacted (contact was due {d['due']})" if en else f"إحالة رقم {d['referral']}: لم يتم التواصل مع المريضة (الموعد {d['due']})"
    if c == "referral_overdue":
        return f"Referral #{d['referral']} OVERDUE: not yet seen (visit due {d['due']}, status {d['status']})" if en else f"إحالة رقم {d['referral']} متأخرة: لم تُفحص بعد (الموعد {d['due']}، الحالة {d['status']})"
    if c == "referral_no_booking":
        return f"Referral #{d['referral']}: patient says she has NOT got an appointment" if en else f"إحالة رقم {d['referral']}: تفيد المريضة بأنها لم تحصل على موعد"
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
