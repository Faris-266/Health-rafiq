# Rafiq (رفيق) — Arabic AI triage & chronic-disease monitoring

A WhatsApp-first agent that runs a daily check-in in colloquial Arabic (Levantine, Gulf, Egyptian,
Maghrebi, MSA, plus Arabizi), collects glucose / blood pressure / symptoms / medication adherence,
sends medication reminders, and routes abnormal results to the attending physician.

> **Not a medical device. Not clinically approved.** The thresholds in `app/thresholds.json` are
> guideline-style defaults for demonstration. Dialect texts and emergency numbers need native-speaker
> and clinical review before any patient sees them. See *Before real patients*.

## Run it

**Try it in 2 minutes (SQLite, synthetic demo data, no WhatsApp needed):**
```bash
pip install -r requirements.txt
RAFIQ_DEMO_SEED=1 python -m uvicorn app.main:app      # Windows PowerShell: $env:RAFIQ_DEMO_SEED=1
# open http://localhost:8000  → sign in with a demo account (shown on the login page)
pytest -q                                              # 228 tests; also runs on real PostgreSQL if `pgserver` is installed
```

**Production-style (PostgreSQL + Docker):**
```bash
cp .env.example .env        # set DB password, RAFIQ_ADMIN_PASSWORD, WHATSAPP_APP_SECRET; keep RAFIQ_DEMO_SEED=0
docker compose up --build   # Postgres + app; first admin is created from RAFIQ_ADMIN_USER/PASSWORD
```
Without Docker: set `DATABASE_URL=postgresql://user:pass@host:5432/rafiq`; tables are created automatically.
Create/reset users from the shell: `python -m app.manage create-user --username me --name "Me" --role admin`.

## Who sees what

| Role | Opens | Can do |
|---|---|---|
| **Admin** | `/admin` (and `/dashboard`) | Users (create, disable, reset password), clinicians, enroll patients, audit log, system status, read-only clinical rules |
| **Clinician** | `/dashboard` | Alert queue, patient trends, acknowledge/resolve, enroll patients, patient simulator, **only for their own patients** |
| **Patient** | `/patient` | Their own readings, medications, status; web chat with Rafiq (same safety engine as WhatsApp); dialect preference |

Demo accounts (only when `RAFIQ_DEMO_SEED=1`; password `Rafiq-demo-1`): `demo-admin`, `demo-lina`, `demo-omar`, `demo-patient1…6`.
Dark/light theme and Arabic (RTL)/English toggles are in every page header and remember your choice.

## Architecture

```
 WhatsApp ──► /webhook/whatsapp ─► Engine.handle_inbound ─┐        ┌─► Clinician dashboard (alerts, trends)
 (Meta Cloud API, HMAC-verified,   │  1 opt-out            │        │
  de-duplicated)                   │  2 RED-FLAG screen    ├─► DB ──┤
 Simulator ──► /api/sim/send ──────┘  3 consent gate       │        └─► WhatsApp/SMS alert to physician
                                      4 check-in machine ──┘
 Scheduler (tick/min): daily check-in · med reminders · nudges · urgent follow-up · silent-patient alert
```

| File | Role |
|---|---|
| `app/triage.py` + `thresholds.json` | **Deterministic** rules → normal / watch / urgent. No LLM. Versioned; every alert stores the rules version. |
| `app/nlu.py` | Arabic normalisation, Arabizi, Arabic-Indic digits, "12 على 8", mmol/L↔mg/dL, negation-aware multi-dialect symptom lexicon |
| `app/conversation.py` | State machine, consent, escalation, WhatsApp 24h-window logic, partial-data preservation |
| `app/messages.py` | Dialect templates (gender-aware), clinician summaries (EN/AR) |
| `app/scheduler.py` | Time-driven behaviour; `tick(engine, now)` is testable |
| `app/channels.py`, `media.py` | WhatsApp Cloud API; optional voice-note STT and meter-photo reading |
| `app/main.py` | Staff API (role-scoped), auth routes, page guards, security headers, WhatsApp webhook |
| `app/auth.py` | scrypt passwords, revocable server-side sessions, login lockout, role guards, per-clinician patient scoping |
| `app/routes_admin.py`, `routes_patient.py` | Admin console API; patient-portal API (a patient can only reach their own record) |
| `app/db.py` | One SQL dialect for SQLite and PostgreSQL |
| `app/manage.py` | CLI: create users, reset passwords |
| `app/pages/`, `app/static/` | Login, dashboard, admin, patient pages; shared CSS/JS (theme, i18n) |

## Safety design (the part judges and clinicians will probe)

* **Collect and route, never diagnose.** Severity comes from physician-reviewable rules, not model judgement.
* **Red-flag screen on every message, in every state, even before consent** (chest pain, breathlessness,
  fainting, stroke signs, confusion, seizure, persistent vomiting, self-harm). Negation-aware
  ("ما عندي وجع صدر" doesn't fire; "ما عندي دوخة بس وجع صدر" does).
* **Dangerous numbers escalate immediately** — a glucose of 45 interrupts the questionnaire.
* **Nothing is silently dropped:** unclassified complaints are forwarded verbatim to the doctor; abandoned
  check-ins keep partial readings; silent patients (3 days) raise an alert.
* **Safety follow-up** 30 min after an urgent message; clinician alerted immediately (alert is also in the queue).
* **Photo readings are confirmed by the patient** before storage. Implausible values prompt a re-measure.
* **Over-triage bias:** a false alarm costs a call.
* **Audit log** of sign-ins (and failures), patient-record views, acknowledgements, user changes, consent and opt-outs.

## Web security (what is built in)
* Passwords hashed with scrypt; temporary passwords are random, shown once, and must be changed at first login.
* Sessions are random tokens in `HttpOnly; SameSite=Lax` cookies (add `Secure` via `RAFIQ_COOKIE_SECURE=1`); only a hash is stored, so logout, disabling a user or a password reset revokes access immediately.
* 5 failed logins → 5-minute lockout; identical error for unknown users and wrong passwords.
* Clinicians cannot see other clinicians' patients (404, not 403); patients cannot call staff APIs; every endpoint is role-checked and tested.
* Cross-origin state-changing requests are rejected; CSP, `X-Frame-Options`, `nosniff` headers; API responses are `no-store`.
* The WhatsApp webhook is authenticated by Meta's HMAC signature, not by cookie.
* Still to add for production: HTTPS (reverse proxy), SSO/2-factor for staff, Redis-backed rate limiting if you run several workers, backups, field-level encryption of phone numbers.

## WhatsApp setup

1. Create a Meta app → WhatsApp → get a phone number ID and a permanent token.
2. Webhook URL `https://<host>/webhook/whatsapp`, verify token = `WHATSAPP_VERIFY_TOKEN`, subscribe to `messages`.
   Set `WHATSAPP_APP_SECRET` so signatures are checked.
3. Create and get approved (language `ar`) these templates — business-initiated messages outside the 24h window
   *must* use templates:
   * `rafiq_welcome` (1 var: name) — consent request, include a quick-reply button "نعم".
   * `rafiq_daily_checkin` (1 var: name) — greeting with quick-reply button "ابدأ".
   * `rafiq_med_reminder` (2 vars: name, medication).
   * `rafiq_clinician_alert` (3 vars: patient, level, summary).
4. Check Meta's current WhatsApp Business policy on health data for your use case and region.

## Before real patients (do not skip)

| Area | What's needed |
|---|---|
| Clinical | Physician committee signs off `thresholds.json` (glucose context, BP targets per patient, pregnancy, elderly, children…) and the action texts; define on-call coverage so *someone* receives urgent alerts 24/7 |
| Language | Native-speaker + clinician review of every dialect string; user-test with low-literacy and elderly users; benchmark STT on your dialect recordings |
| Privacy | National law (Saudi PDPL, UAE health-data law, Jordan PDPL…): consent wording, data residency, retention, DPIA. Encrypt at rest (managed Postgres, encrypted disks), SSO/2-factor for staff, field-level encryption for phone numbers, retention and deletion policy |
| Reliability | Run the scheduler as a separate singleton job, add alerting on webhook/send failures and on "urgent alert not acknowledged in N minutes → escalate to next clinician" |
| Compliance | Medical-device classification (SaMD) review with the local regulator; clinical safety case; incident process |
| Not covered by tests | `media.py` (STT / photo reading) and live WhatsApp sends need your credentials; test with real devices |

## Extending

* **New dialect:** add a block to `messages.T`, symptom phrases to `nlu._LEX_SRC`, tests in `tests/test_nlu.py`.
* **New condition (e.g. asthma, CKD):** add a step + measurement parser, rules in `triage.evaluate`, thresholds in JSON.
* **Other channels:** implement `Channel.send` (SMS, Telegram, hospital gateway).
* **Bluetooth devices / FHIR:** write readings into `readings`; map alerts to FHIR `Observation`/`Flag` for HIS/EMR integration.
* **LLM use that is safe:** only as a fallback to *classify unrecognised free text upward* (never to lower severity), or to draft clinician summaries — always behind the deterministic rules.

## Pilot metrics (already queryable)
Medication adherence (7d), check-in completion, time from urgent alert → acknowledgement (`/api/overview`),
reduction in routine visits and avoided ER visits (join with clinic data).
