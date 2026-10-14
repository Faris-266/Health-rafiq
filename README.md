# Rafiq (رفيق): early detection of breast cancer, in Arabic and English

Rafiq helps women keep up with **screening**, notice **breast changes** early, and, most importantly,
**get seen**: it tracks every concern until the woman has actually reached a clinician.
It speaks Levantine, Gulf, Egyptian, Maghrebi, standard Arabic (plus Arabizi) and English, on WhatsApp and on the web.
The original chronic-disease pack (diabetes / hypertension monitoring) still works alongside it.

> **Not a medical device. Not clinically approved. It never diagnoses and never tells a woman she is "fine".**
> The screening ages/intervals and referral timelines in `app/breast_policy.json` are demonstration defaults:
> your national programme and a responsible clinician must set and sign them off before any patient use.

## Why this design
Screening saves lives only if (1) women are screened on time, (2) changes are reported early, and
(3) an abnormal finding leads to a visit. Programmes lose most women at step 3, so Rafiq is built around **closing the loop**.

| Step | What Rafiq does |
|---|---|
| **Intake (once, in chat)** | Age, family history (1st-degree), biopsy with atypia, known gene change, chest radiation, last mammogram → *average* or *elevated* pathway. Unknown answers never raise or lower risk silently. No made-up risk score. |
| **Screening schedule** | Tracks due / overdue per policy; reminds every 30 days (quiet for 45 days after she says she booked). Elevated-risk women are never given a guessed schedule: a clinician sets it. |
| **Monthly breast-awareness check-in** | "Did you check?" → "Any change?" Recognises lump, nipple discharge/inversion, skin dimpling/redness, shape change, underarm lump, pain, in dialect, English and French/Darija; negation-aware. |
| **Any time, any state** | A breast change mentioned *anywhere* (even mid-check-in or before consent) is handled immediately: calm, honest message ("most changes are not cancer, but this needs checking soon"), urgent alert to the clinician, and a **referral** created. |
| **Referral tracker** | Every referral has *contact-by* and *visit-by* dates and a status (new → contacted → booked → seen → closed + outcome). The patient is chased at +3 days; staff get an alert if no one contacted her by day 2 or she isn't seen by day 14; passed appointments without an outcome are flagged. |
| **Screening log** | Staff record results with BI-RADS: 0/4/5 → urgent referral, 3 → 6-month recheck, 1-2 → routine. Closing a referral as "further tests/treatment" hands her to a clinician-led plan. |
| **Honest messaging** | The "all good" message always says it doesn't replace screening or a doctor's exam. Chest pain / breathlessness / fainting etc. remain **emergency red flags** and are never confused with breast issues. |

**Dashboard KPIs:** screening coverage, due/overdue screenings, open and **overdue referrals**, median days from report to being seen.

## Run it
**Try it in 2 minutes (SQLite, synthetic data, no WhatsApp):**
```bash
pip install -r requirements.txt
RAFIQ_DEMO_SEED=1 python -m uvicorn app.main:app      # PowerShell: $env:RAFIQ_DEMO_SEED=1
# open http://localhost:8000
pytest -q                                              # ~390 tests; also runs on real PostgreSQL if `pgserver` is installed
```
Demo accounts (password `Rafiq-demo-1`; shown on the login page): `demo-admin`, `demo-lina`, `demo-omar`, `demo-patient1…8`.
Demo clinic code for the sign-up page: `DEMOLINA`. Try patient 5 (`demo-patient5`, intake pending) or create a new account at `/register`.

**Real deployment (PostgreSQL + Docker):**
```bash
cp .env.example .env     # set DB password, RAFIQ_ADMIN_PASSWORD, WHATSAPP_APP_SECRET; keep RAFIQ_DEMO_SEED=0
docker compose up --build
```
Create/reset users: `python -m app.manage create-user --username me --name "Me" --role admin`.

## Accounts
| Who | How they get an account | Sees |
|---|---|---|
| **Patient** | Self-registers at `/register` (adults 18+, explicit consent, optional **clinic code** that assigns her to a clinician) or is enrolled by staff | Her own screening status, referral progress, guide, chat, preferences; **download or permanently delete her data** |
| **Clinician** | Created by an admin | Alerts, referrals, patients, screening log: **only their own patients** |
| **Admin** | First admin via env/CLI | Users, clinicians + clinic codes, assigning patients, audit log, system status |

Admins can **choose a user's password themselves** (optionally without a forced change) or let the system generate a temporary one (shown once; it is the "current password" the user enters at first sign-in).
**Forgot password:** the login page sends a 6-digit code by WhatsApp or email (needs `RAFIQ_VERIFY` ≠ none); otherwise an admin resets it (`/admin` → Users) or `python -m app.manage reset-password --username NAME`.

Sign-up verification (`RAFIQ_VERIFY`): a 6-digit code (15 min, 5 attempts, resend cooldown) via **WhatsApp template** or **email (SMTP)**;
`none` is for trials only and the admin page warns about it. Login works with email, phone or username.
If a patient has no clinician (self-registered without a code), urgent alerts go to `RAFIQ_ONCALL_PHONE`, and the admin page flags them.

## WhatsApp
Create these approved templates (language `ar`/`en`); business-initiated messages outside the 24h window **must** use templates.
Keep the wording **discreet**: many women share phones, so don't name the condition in notification text.
`rafiq_welcome`, `rafiq_monthly_checkin`, `rafiq_daily_checkin`, `rafiq_health_reminder` (screening reminder), `rafiq_health_followup`
(referral chase), `rafiq_clinician_alert`, `rafiq_verify`, `rafiq_med_reminder`. Set `WHATSAPP_APP_SECRET` so webhook signatures are verified.

## Architecture
```
WhatsApp ─► /webhook ─► Engine.handle_inbound ─ 1 opt-out ─ 2 emergency red flags ─ 3 BREAST-CONCERN screen ─ 4 consent ─ 5 state machine
Web chat ─► /api/me/chat ─┘                                                                       │
Scheduler (tick/min): monthly check-in · screening reminders · referral chase · overdue-referral alerts · daily chronic check-ins
DB (SQLite or PostgreSQL) ─► Staff dashboard · Admin console · Patient portal · clinician alerts (WhatsApp)
```
Key files: `breast.py` (pure logic) · `breast_ops.py` (screenings/referrals/KPIs) · `breast_flow.py` (conversation) · `breast_policy.json` ·
`nlu.py` (multi-dialect understanding) · `messages.py` (all text, AR dialects + EN) · `scheduler.py` · `auth.py` · `routes_*.py` · `pages/` + `static/`.

## Security and privacy built in
Scrypt passwords · revocable server-side sessions (HttpOnly, SameSite) · login lockout · role checks on every endpoint, clinicians scoped to their patients
(404, not 403) · CSRF origin check, CSP and security headers · HMAC-verified webhook · audit log (sign-ins, record views, referral changes, exports) ·
**patient data export and permanent deletion** · health data minimised (birth *year*, not date) · sign-up rate limiting.
Still needed for production: HTTPS, 2-factor/SSO for staff, encrypted storage and backups, a retention policy, Redis-backed rate limits if you run several workers.

## Before real patients (do not skip)
| Area | What's needed |
|---|---|
| Clinical | A breast-screening lead signs off `breast_policy.json` (start age, interval, who is *elevated risk*, referral deadlines) and every patient-facing clinical sentence; define who answers urgent alerts 24/7 and who sees women within 14 days. The system tracks the visit, **the clinic must provide it**. |
| Language | Native-speaker + clinician review of all texts; user-test with women of different ages and literacy. Breast prompts currently use standard Arabic for all Arabic dialects (English is complete); add dialect versions in `messages.T`. |
| Privacy | National health-data law (PDPL etc.), consent wording, data residency, retention, DPIA; women-only staff options and discreet notifications. |
| Regulatory | Software-as-medical-device assessment with your regulator; clinical safety case; incident process. |
| Evidence | Self-checks do not replace mammography and have not shown a mortality benefit by themselves; Rafiq frames them as *awareness* and never as a substitute for screening. Measure outcomes (coverage, time to being seen, stage at diagnosis) in a pilot before scaling. |
| Not covered by tests | Live WhatsApp/SMTP sends, voice notes, photo reading: need your credentials and real devices. |

## Extending
New dialect: `messages.T` + `nlu._BREAST_SRC` + tests · new screening type or BI-RADS rule: `breast_policy.json` + `breast.py` ·
other channels: implement `Channel.send` · hospital systems: map `screenings`/`referrals` to FHIR `DiagnosticReport` / `ServiceRequest`.
