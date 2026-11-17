# Regal HMS – Python Backend (FastAPI + MongoDB)

Complete end-to-end backend for the **Regal Plastic Surgery Centre** frontend (React + Vite).

Implements the contract in `docs/BACKEND.md` of the frontend repo so that setting  
`VITE_USE_MOCK=false` makes the app talk to this server with no screen changes.

## Stack

- **FastAPI** – async HTTP API
- **MongoDB** (Motor) – document store
- **Argon2** – password hashing
- **pyotp** – TOTP / MFA
- Cookie-based **httpOnly sessions** (30 min idle, sliding)
- Trusted-device cookie (30 days) to skip MFA

## Quick start

```bash
# 1. MongoDB (local or Docker)
docker run -d --name regal-mongo -p 27017:27017 mongo:7

# 2. Python env
cd regal-hms-backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Config
cp .env.example .env
# edit SECRET_KEY if you like

# 4. Seed demo data
python seed.py

# 5. Run
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs  
Health: http://localhost:8000/api/health

## Frontend connection

In the frontend project:

```bash
cp .env.example .env
# set:
VITE_USE_MOCK=false
# optional: VITE_API_URL=http://localhost:8000/api
```

Vite already proxies `/api` → `http://localhost:8000` (see `vite.config.js`).

## Demo accounts

All use password: **`Password1!`**

| Email                    | Role            |
|--------------------------|-----------------|
| director@regal.example   | Medical Director|
| amadi@regal.example      | Surgeon         |
| bello@regal.example      | Surgeon         |
| joy@regal.example        | Nurse (aftercare head) |
| chioma@regal.example     | Nurse (clinic)  |
| adaeze@regal.example     | Pharmacist      |
| amina@regal.example      | Front desk      |
| tunde@regal.example      | Finance         |
| funke@regal.example      | HR              |
| emeka@regal.example      | Lab nurse       |

**MFA secret for all demo accounts** (add to any authenticator app):

```
JBSWY3DPEHPK3PXP
```

Login flow: email + password → MFA code (or enrolment on first use) → session cookie.

## Implemented endpoints

| Area            | Prefix / routes                                      | Status |
|-----------------|------------------------------------------------------|--------|
| Auth            | `/api/auth/*` (login, MFA, enrol, reset, activate…) | Full   |
| Staff           | `/api/staff`, accounts, invite, unlock…             | Full   |
| Patients        | `/api/patients`, allergies, conditions              | Full   |
| Appointments    | `/api/appointments`                                 | Full   |
| Dashboard       | `/api/dashboard`, `/api/badges`                     | Full   |
| Laboratory      | `/api/lab-requests`, take, release, status machine  | Core   |

### Still to expand (structure ready)

- Consultations, surgical plans, surgeries, aftercare (observation flags, discharge rules)
- Pharmacy (stock, FEFO, prescriptions, dispensing)
- Billing (quotations → invoices → payments / receipts)
- Tasks & messaging
- Department reports

The permission matrix, session model, error shape (`{ "message": "…" }`), ID formats and most business rules from `BACKEND.md` are already enforced in the implemented modules. Extend the same patterns for the remaining areas.

## Project layout

```
regal-hms-backend/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── dependencies.py          # get_current_user (session cookie)
│   ├── core/security.py
│   ├── models/
│   ├── routers/                 # auth, staff, patients, …
│   └── utils/permissions.py
├── seed.py
├── requirements.txt
└── .env.example
```

## Security notes (production)

- Change `SECRET_KEY` and use a strong random value.
- Set `ENVIRONMENT=production` so cookies get the `Secure` flag.
- Put the API behind HTTPS.
- Rate-limit `/auth/login` and MFA endpoints at the reverse proxy.
- Replace the demo MFA secret; never ship real TOTP secrets in seed data.
- Add an email provider for invite / reset links (currently printed to the console).
- Consider an audit-log retention policy and backup strategy for MongoDB.

## Licence / disclaimer

Demo system only. Not a certified medical device or clinical record system. Replace placeholder clinical rules (lab ranges, observation thresholds, discount limits, etc.) with the centre’s own protocols before any real use.
