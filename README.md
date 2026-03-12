# Berit Shalvah Financial Services — Loan Management System

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Odoo](https://img.shields.io/badge/Odoo-19.0-purple)
![Django](https://img.shields.io/badge/Django-5.0-green)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue)
![Redis](https://img.shields.io/badge/Redis-7-red)
![License](https://img.shields.io/badge/License-LGPL--3-orange)

A full-stack loan management platform for **Berit Shalvah Financial Services Ltd** (Kenya).  
The system combines an **Odoo 19 back-office** (loan origination, approvals, repayments, reporting) with a **Django client portal** (self-service applications, document uploads, repayment tracking), all wired together through a REST/XML-RPC integration layer and served behind an **Nginx** reverse proxy.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Technology Stack](#technology-stack)
3. [Repository Structure](#repository-structure)
4. [Odoo Module — `berit_loan`](#odoo-module--berit_loan)
   - [Models](#models)
   - [Business Rules](#business-rules)
   - [Scheduled Jobs (Crons)](#scheduled-jobs-crons)
   - [Security & Roles](#security--roles)
   - [Reports](#reports)
5. [Django Client Portal](#django-client-portal)
   - [Apps](#apps)
   - [Odoo Sync Layer](#odoo-sync-layer)
   - [Celery Tasks](#celery-tasks)
6. [Nginx Reverse Proxy](#nginx-reverse-proxy)
7. [Prerequisites](#prerequisites)
8. [Local Development Setup (Bare Metal)](#local-development-setup-bare-metal)
9. [Docker Setup](#docker-setup)
10. [Environment Variables](#environment-variables)
11. [Database Setup](#database-setup)
12. [Running the System](#running-the-system)
13. [Deployment (Production)](#deployment-production)
14. [API Integration Reference](#api-integration-reference)
15. [Loan Business Rules Reference](#loan-business-rules-reference)
16. [Troubleshooting](#troubleshooting)
17. [Contributing](#contributing)
18. [License](#license)

---

## Architecture Overview

```
                        ┌─────────────────────────────────────────┐
                        │              NGINX  :80 / :443           │
                        │  /web, /odoo  →  Odoo     :8069          │
                        │  /websocket   →  Odoo gevent  :8072      │
                        │  /longpolling →  Odoo gevent  :8072      │
                        │  /portal, /admin, /api  →  Django :8000  │
                        └────────────┬──────────────┬─────────────┘
                                     │              │
              ┌──────────────────────┘              └──────────────────────┐
              ▼                                                             ▼
   ┌──────────────────────┐                               ┌────────────────────────┐
   │    Odoo 19 Backend   │                               │   Django 5 Portal      │
   │    Port 8069 / 8072  │◄──── XML-RPC / REST ─────────│   Port 8000            │
   │                      │                               │                        │
   │  berit_loan module   │                               │  apps/accounts         │
   │  - Loan Applications │                               │  apps/loans            │
   │  - Repayment Sched.  │                               │  apps/documents        │
   │  - Collateral        │                               │  apps/dashboard        │
   │  - Guarantors        │                               │                        │
   │  - Documents         │                               │  Celery Worker         │
   │  - Interest Configs  │                               │  Celery Beat           │
   └──────────┬───────────┘                               └──────────┬─────────────┘
              │                                                       │
              └──────────────────────┬────────────────────────────────┘
                                     ▼
                        ┌────────────────────────┐
                        │   PostgreSQL  :5432     │
                        │   DB: berit_odoo        │
                        │   DB: berit_portal      │
                        └────────────┬────────────┘
                                     │
                        ┌────────────▼────────────┐
                        │   Redis  :6379           │
                        │   Celery broker/backend  │
                        └─────────────────────────┘
```

---

## Technology Stack

| Layer | Technology | Version |
|---|---|---|
| ERP / Back-office | Odoo | 19.0 |
| Client Portal | Django | 5.0 |
| Task Queue | Celery + django-celery-beat | 5.3+ |
| Database (Odoo) | PostgreSQL | 16 |
| Database (Portal) | PostgreSQL | 16 |
| Cache / Broker | Redis | 7 |
| Reverse Proxy | Nginx | alpine |
| Container Runtime | Docker + Docker Compose | v3.8 |
| PDF Generation | WeasyPrint | 60+ |
| Real-time | Odoo gevent WebSocket | port 8072 |

---

## Repository Structure

```
berit-shalvah/
│
├── odoo/                          # Odoo installation configuration
│   ├── odoo.conf                  # Odoo server config (workers, ports, DB)
│   ├── Dockerfile                 # Odoo container image
│   └── addons/
│       └── berit_loan/            # Custom Odoo module
│           ├── __manifest__.py
│           ├── models/
│           │   ├── loan_application.py
│           │   ├── repayment_schedule.py
│           │   ├── collateral.py
│           │   ├── guarantor.py
│           │   ├── loan_document.py
│           │   └── interest_rate_config.py
│           ├── views/
│           ├── reports/
│           ├── security/
│           ├── data/
│           │   ├── ir_cron.xml
│           │   ├── interest_rates.xml
│           │   └── loan_sequence.xml
│           ├── wizards/
│           └── demo/
│
├── django_portal/                 # Django client portal
│   ├── config/                    # Django project settings
│   │   ├── settings/
│   │   │   ├── base.py
│   │   │   ├── development.py
│   │   │   └── production.py
│   │   ├── celery.py
│   │   └── urls.py
│   ├── apps/
│   │   ├── accounts/              # Custom user model, auth, KYC
│   │   ├── loans/                 # Loan applications + Odoo sync
│   │   │   ├── models.py
│   │   │   ├── odoo_sync.py       # XML-RPC bridge to Odoo
│   │   │   ├── tasks.py           # Celery async tasks
│   │   │   └── sync/              # Enhanced bidirectional sync
│   │   ├── documents/             # Document upload & verification
│   │   └── dashboard/             # Client dashboard views
│   ├── templates/                 # Jinja2 / Django templates
│   ├── static/                    # CSS, JS, images
│   ├── Dockerfile
│   ├── Dockerfile.celery
│   ├── Dockerfile.celerybeat
│   └── requirements.txt
│
├── nginx/
│   ├── nginx.conf                 # Bare-metal config (localhost upstreams)
│   └── nginx.docker.conf          # Docker config (service-name upstreams)
│
├── scripts/
│   ├── setup.sh                   # First-time Docker setup
│   ├── setup_local.sh             # First-time bare-metal setup
│   ├── backup.sh                  # Database backup script
│   └── deploy.sh                  # Production deploy script
│
├── docker-compose.yml             # Development Docker Compose
├── docker-compose.prod.yml        # Production Docker Compose
├── start_system.sh                # Simple bare-metal start script
├── start_system_improved.sh       # Full bare-metal start with health checks
├── .env.example                   # Environment variable template
└── README.md
```

---

## Odoo Module — `berit_loan`

The `berit_loan` Odoo module is the authoritative source of truth for all loan data.

### Models

#### `berit.loan.application`
The core model representing a loan application through its full lifecycle.

| Field | Type | Description |
|---|---|---|
| `name` | Char | Auto-generated reference (e.g. `BSL-00001`) |
| `applicant_id` | Many2one → `res.partner` | Loan applicant |
| `loan_amount` | Float | Requested amount in KES |
| `loan_duration` | Integer | Duration in months |
| `interest_rate` | Float (computed) | Monthly rate derived from amount tier |
| `monthly_repayment` | Float (computed) | Principal + interest per month |
| `total_repayable` | Float (computed) | Full repayment amount |
| `legal_fee` | Float (computed) | 2.5% of loan amount |
| `state` | Selection | `draft → submitted → under_review → approved → active → closed / defaulted / rejected` |
| `collateral_ids` | One2many | Linked collateral records |
| `guarantor_ids` | One2many | Linked guarantors |
| `repayment_ids` | One2many | Repayment schedule lines |
| `document_ids` | One2many | Supporting documents |
| `crb_clearance` | Boolean | CRB clearance status |
| `kyc_verified` | Boolean | KYC verification status |
| `django_application_id` | Char | Foreign key back to Django portal UUID |

**State transitions:**
```
draft ──► submitted ──► under_review ──► approved ──► active ──► closed
                                    └──► rejected         └──► defaulted
```

---

#### `berit.repayment.schedule`
One record per installment. Generated automatically when a loan is approved.

| Field | Type | Description |
|---|---|---|
| `loan_id` | Many2one | Parent loan |
| `due_date` | Date | Installment due date |
| `principal_amount` | Float | Principal portion |
| `interest_amount` | Float | Interest portion |
| `total_due` | Float (computed) | Principal + interest |
| `amount_paid` | Float | Amount actually paid |
| `status` | Selection | `pending / paid / overdue / partially_paid` |
| `days_overdue` | Integer (computed) | Days past due date |
| `penalty_amount` | Float (computed) | 1% of total due per day overdue |
| `payment_method` | Selection | `cash / bank_transfer / mpesa / cheque / other` |

---

#### `berit.collateral`
Assets pledged as security against a loan.

| Field | Type | Description |
|---|---|---|
| `loan_id` | Many2one | Parent loan |
| `collateral_type` | Selection | `land / vehicle / building / equipment / other` |
| `description` | Text | Detailed description |
| `estimated_value` | Float | Market value in KES |
| `verified` | Boolean | Officer verification flag |

**Rule:** Total collateral value must be at least **1.5× the loan amount**.

---

#### `berit.guarantor`
Individuals who guarantee a loan applicant.

| Field | Type | Description |
|---|---|---|
| `loan_id` | Many2one | Parent loan |
| `partner_id` | Many2one → `res.partner` | Guarantor contact |
| `relationship` | Char | Relationship to applicant |
| `id_number` | Char | National ID number |
| `phone` | Char | Contact phone |
| `employment_status` | Selection | `employed / self_employed / business_owner` |
| `monthly_income` | Float | KES per month |
| `verified` | Boolean | Officer verification flag |

---

#### `berit.loan.document`
KYC, financial, and legal documents attached to a loan.

| Field | Type | Description |
|---|---|---|
| `loan_id` | Many2one | Parent loan |
| `document_type` | Selection | `id / kra_pin / crb / payslip / bank_statement / mpesa_statement / guarantor_letter / collateral_proof / valuation_report / other` |
| `file` | Binary | Document file |
| `filename` | Char | Original filename |
| `verified` | Boolean | Officer verification flag |
| `expiry_date` | Date | Document expiry (for IDs, CRBs) |
| `is_expired` | Boolean (computed) | Auto-flag based on expiry_date |

---

#### `berit.interest.rate.config`
Configurable interest rate tiers (editable by admin without code changes).

| Field | Type | Description |
|---|---|---|
| `name` | Char | Tier label |
| `min_amount` | Float | Lower bound (KES) |
| `max_amount` | Float | Upper bound (KES, 0 = unlimited) |
| `monthly_rate` | Float | Monthly interest rate (%) |
| `active` | Boolean | Whether tier is active |

---

### Business Rules

#### Interest Rate Tiers (Monthly)

| Loan Amount (KES) | Monthly Rate |
|---|---|
| 1 – 99,999 | 20.0% |
| 100,000 – 399,999 | 17.5% |
| 400,000 – 599,999 | 15.0% |
| 600,000 – 799,999 | 10.0% |
| 800,000 – 999,999 | 7.5% |
| 1,000,000+ | 5.0% |

#### Fees
- **Legal fee:** 2.5% of loan amount (one-time, client-paid at disbursement)
- **Penalty:** 1% of total installment due per day overdue

#### Collateral
- Minimum required value: **1.5× loan amount**
- Collateral must be verified by a loan officer before approval

#### Loan Duration Limits
- **First-time borrowers:** 1–3 months
- **Returning borrowers:** 1–12 months

---

### Scheduled Jobs (Crons)

| Job | Model | Method | Schedule | Description |
|---|---|---|---|---|
| Mark Overdue Repayments | `berit.repayment.schedule` | `mark_overdue_payments()` | Daily | Marks pending installments past due date as `overdue`; triggers loan default after 30 days |
| Check Document Expiry | `berit.loan.document` | `check_all_documents_expiry()` | Daily | Flags documents whose `expiry_date` has passed |
| Send Repayment Reminders | `berit.repayment.schedule` | `send_due_soon_reminders()` | Daily | Sends email reminders for installments due within 7 days |
| Weekly Portfolio Summary | `berit.loan.application` | `send_portfolio_summary()` | Weekly | Portfolio summary email (disabled until implemented) |

> **Note:** Cron `code` fields must only contain a single `model.method()` call.
> All logic (imports, queries) lives in the Python model method — not in the XML.

---

### Security & Roles

Defined in `security/security.xml` and `security/ir.model.access.csv`.

| Role | Permissions |
|---|---|
| `berit_loan.group_loan_officer` | Read/write loan applications, repayments, documents |
| `berit_loan.group_loan_manager` | Full CRUD + approval/rejection + config |
| `berit_loan.group_loan_admin` | Full access including interest rate config |

---

### Reports

| Report | Template | Description |
|---|---|---|
| Loan Agreement | `reports/loan_agreement_report.xml` | Formal loan agreement PDF with all terms, collateral, guarantor details |

---

## Django Client Portal

The Django portal is the **client-facing** interface. Clients register, submit loan applications, upload documents, and track repayment schedules. All data is bidirectionally synced to Odoo via XML-RPC.

### Apps

#### `apps/accounts`
Custom user model extending `AbstractBaseUser`.

- **User types:** `client`, `admin`, `staff`
- Registration with email verification
- KYC document upload at onboarding
- Profile management
- Django Allauth integration for social auth

Key models:
- `CustomUser` — email-based auth with `user_type`, `phone`, `id_number`, `odoo_partner_id`
- `UserDocument` — KYC documents per user (ID copy, KRA PIN, passport photo, etc.)

---

#### `apps/loans`
Loan application lifecycle from the client's perspective.

Key models:
- `LoanApplication` — mirrors Odoo's `berit.loan.application`, linked via `odoo_loan_id`
- `LoanDocument` — documents attached to a specific loan application
- `RepaymentSchedule` — synced copy of Odoo's repayment schedule for display

Key views:
- `LoanApplicationWizard` — multi-step application form (amount → purpose → employment → documents → review)
- `LoanListView` — client's loan history with status badges
- `LoanDetailView` — full loan detail with repayment schedule and document list

Key management commands:
```bash
# Sync all loans from Odoo to Django
python manage.py sync_loans

# Push a specific Django application to Odoo
python manage.py push_to_odoo --loan-id <uuid>

# Test Odoo connectivity
python manage.py test_odoo

# Fix partner name mismatches
python manage.py fix_odoo_partner_names
```

---

#### `apps/documents`
Centralised document management.

- Upload with file-type validation (PDF, JPG, PNG, max 10MB)
- Document status tracking: `pending / verified / rejected / expired`
- Admin verification workflow
- Auto-expiry detection

---

#### `apps/dashboard`
Client dashboard landing page.

- Loan summary cards (active loans, total outstanding, next payment due)
- Recent activity feed
- Quick action buttons (apply, upload docs, view schedule)

---

### Odoo Sync Layer

**File:** `apps/loans/odoo_sync.py`

Communicates with Odoo via the standard XML-RPC API using Python's built-in `xmlrpc.client`.

```
Django Portal  ──XML-RPC──►  Odoo
                             /xmlrpc/2/common  (authenticate)
                             /xmlrpc/2/object  (CRUD operations)
```

**Document type mapping** (Django → Odoo):

| Django value | Odoo value |
|---|---|
| `id_copy` | `id` |
| `kra_pin` | `kra_pin` |
| `passport_photo` | `id` |
| `proof_of_address` | `other` |
| `bank_statement` | `bank_statement` |
| `mpesa_statement` | `mpesa_statement` |
| `payslip` | `payslip` |
| `business_license` | `other` |

**Key sync operations:**

| Function | Direction | Description |
|---|---|---|
| `sync_application_to_odoo(application)` | Django → Odoo | Creates/updates loan application in Odoo |
| `sync_documents_to_odoo(application)` | Django → Odoo | Pushes base64-encoded documents |
| `sync_repayment_schedule(application)` | Odoo → Django | Pulls repayment lines from Odoo |
| `sync_loan_status(application)` | Odoo → Django | Pulls status updates from Odoo |

---

### Celery Tasks

**Broker:** Redis (`REDIS_URL` env var)  
**Scheduler:** `django-celery-beat` with `DatabaseScheduler`

| Task | App | Description |
|---|---|---|
| `sync_loan_to_odoo` | loans | Async push of new/updated loan to Odoo |
| `sync_all_loans` | loans | Full reconciliation sweep (periodic) |
| `send_payment_reminder` | loans | Email reminder for upcoming installment |
| `process_document_upload` | documents | Virus scan + compress + push to Odoo |
| `send_welcome_email` | accounts | Triggered on new user registration |

Start workers:
```bash
# Worker
celery -A config worker --loglevel=info

# Beat scheduler
celery -A config beat --loglevel=info \
    --scheduler django_celery_beat.schedulers:DatabaseScheduler

# Monitor (Flower)
celery -A config flower --port=5555
```

---

## Nginx Reverse Proxy

Two config files are provided:

| File | Use case | Upstream hostnames |
|---|---|---|
| `nginx/nginx.conf` | Bare-metal / systemd | `localhost` |
| `nginx/nginx.docker.conf` | Docker Compose | `odoo`, `django` (service names) |

**Routing table:**

| Path | Upstream | Notes |
|---|---|---|
| `/websocket` | `odoo:8072` | WebSocket upgrade headers, 1h timeout |
| `/longpolling` | `odoo:8072` | Long-poll, 1h timeout |
| `/web` | `odoo:8069` | Odoo backend UI |
| `/web/static/` | `odoo:8069` | Cached 90 days |
| `/odoo` | `odoo:8069` | Odoo alternate prefix |
| `/api/jsonrpc` | `odoo:8069` | Rate limited: 30 req/min |
| `/portal` | `django:8000` | Client portal |
| `/admin` | `django:8000` | Django admin |
| `/accounts/login` | `django:8000` | Rate limited: 5 req/min |
| `/static/` | filesystem | Django static files |
| `/media/` | filesystem | Django media files |
| `/health` | `django:8000` | Health check endpoint |
| `/` | — | 301 → `/portal/` |

---

## Prerequisites

### Bare Metal
- Python **3.10+**
- PostgreSQL **16**
- Redis **7**
- Nginx
- Node.js 18+ (for Odoo asset bundling)
- `wkhtmltopdf` (for Odoo PDF reports)

### Docker
- Docker **24+**
- Docker Compose **v2** (plugin) or `docker-compose` **v1.29+**

---

## Local Development Setup (Bare Metal)

### 1. Clone the repository
```bash
git clone https://github.com/Kemboi14/Berit-shalvah.git
cd Berit-shalvah
```

### 2. Create PostgreSQL databases
```bash
sudo -u postgres psql << 'SQL'
CREATE USER berit_user WITH PASSWORD 'berit123';
CREATE DATABASE berit_odoo  OWNER berit_user TEMPLATE template0 ENCODING 'UTF8';
CREATE DATABASE berit_portal OWNER berit_user TEMPLATE template0 ENCODING 'UTF8';
GRANT ALL PRIVILEGES ON DATABASE berit_odoo   TO berit_user;
GRANT ALL PRIVILEGES ON DATABASE berit_portal TO berit_user;
SQL
```

### 3. Set up the Odoo virtual environment
```bash
python3 -m venv odoo_env
source odoo_env/bin/activate
pip install -r /home/nick/odoo-19/requirements.txt
deactivate
```

### 4. Set up the Django virtual environment
```bash
python3 -m venv django_env
source django_env/bin/activate
pip install -r django_portal/requirements.txt
deactivate
```

### 5. Configure environment variables
```bash
cp .env.example .env
# Edit .env with your values (see Environment Variables section)
nano .env
```

### 6. Run Django migrations
```bash
source django_env/bin/activate
cd django_portal
export DJANGO_SETTINGS_MODULE=config.settings.development
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
cd ..
deactivate
```

### 7. Apply Nginx config
```bash
sudo cp nginx/nginx.conf /etc/nginx/nginx.conf
sudo nginx -t
sudo systemctl reload nginx
```

### 8. Start everything
```bash
chmod +x start_system_improved.sh
./start_system_improved.sh
```

Or with debug output:
```bash
./start_system_improved.sh --debug
```

---

## Docker Setup

### Development
```bash
cp .env.example .env
# Edit .env
docker-compose up --build
```

### First-time initialisation (run once after `up`)
```bash
# Install the Odoo module
docker-compose exec odoo odoo \
    --addons-path=/opt/odoo/addons,/mnt/extra-addons \
    -d berit_odoo -i berit_loan --stop-after-init

# Run Django migrations
docker-compose exec django python manage.py migrate

# Create Django admin user
docker-compose exec django python manage.py createsuperuser

# Collect static files
docker-compose exec django python manage.py collectstatic --noinput
```

### Using the setup script (does all the above automatically)
```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

### Production
```bash
docker-compose -f docker-compose.prod.yml up --build -d
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the values below.

```bash
# ── PostgreSQL ──────────────────────────────────────────────────────────────
POSTGRES_USER=berit_user
POSTGRES_PASSWORD=your_secure_password_here
POSTGRES_DB=berit_odoo
ODOO_DB=berit_odoo
PORTAL_DB=berit_portal

# ── Odoo ────────────────────────────────────────────────────────────────────
ODOO_MASTER_PASSWORD=your_odoo_master_password_here

# ── Django ──────────────────────────────────────────────────────────────────
SECRET_KEY=your_django_secret_key_here_50+_chars
DEBUG=True                          # Set False in production
ALLOWED_HOSTS=localhost,127.0.0.1   # Comma-separated, add your domain in prod

# ── Redis / Celery ───────────────────────────────────────────────────────────
REDIS_URL=redis://localhost:6379/0

# ── Email (SMTP) ─────────────────────────────────────────────────────────────
EMAIL_HOST=smtp.gmail.com
EMAIL_HOST_USER=your_email@gmail.com
EMAIL_HOST_PASSWORD=your_gmail_app_password
EMAIL_PORT=587
EMAIL_USE_TLS=True

# ── Portal ───────────────────────────────────────────────────────────────────
PORTAL_BASE_URL=http://localhost:8000
```

> **Security:** Never commit `.env` to version control. It is already listed in `.gitignore`.  
> For Gmail, use an [App Password](https://support.google.com/accounts/answer/185833), not your account password.

---

## Database Setup

Two separate PostgreSQL databases are used:

| Database | Purpose | Owner |
|---|---|---|
| `berit_odoo` | All Odoo data (loans, partners, accounting) | `berit_user` |
| `berit_portal` | Django portal (users, sessions, Celery results) | `berit_user` |

### Backup
```bash
chmod +x scripts/backup.sh
./scripts/backup.sh
# Backups are saved to ./backups/
```

### Restore
```bash
# Odoo
pg_restore -U berit_user -d berit_odoo backups/berit_odoo_YYYYMMDD.dump

# Portal
pg_restore -U berit_user -d berit_portal backups/berit_portal_YYYYMMDD.dump
```

---

## Running the System

### Start all services (recommended)
```bash
./start_system_improved.sh
```

### Start with options
```bash
./start_system_improved.sh --debug       # Verbose Odoo + Django output
./start_system_improved.sh --no-celery   # Skip Celery (useful for debugging)
./start_system_improved.sh --no-odoo     # Skip Odoo (portal-only mode)
```

### Access URLs after startup

| Service | URL | Credentials |
|---|---|---|
| Client Portal | http://localhost/portal | Register as new client |
| Django Admin | http://localhost/admin | Superuser created during setup |
| Odoo Backend | http://localhost/web | admin / (set in .env) |
| Odoo Direct | http://localhost:8069/web | Same as above |
| Celery Flower | http://localhost:5555 | (no auth in dev) |

### Check port bindings
```bash
ss -tlnp | grep -E '80|8069|8072|8000|5432|6379'
```

### View logs
```bash
# All services (startup script log)
tail -f logs/startup_*.log

# Odoo
tail -f /var/log/odoo/odoo.log

# Celery worker
tail -f logs/celery_worker.log

# Celery beat
tail -f logs/celery_beat.log

# Nginx
sudo tail -f /var/log/nginx/error.log
```

---

## Deployment (Production)

### 1. Server requirements
- Ubuntu 22.04 LTS or RHEL 9 / Fedora 38+
- 4 vCPU, 8 GB RAM minimum
- 50 GB SSD

### 2. SSL certificate
```bash
mkdir -p nginx/ssl
# Place your certificate files:
#   nginx/ssl/cert.pem
#   nginx/ssl/key.pem
# Or use Let's Encrypt:
sudo certbot certonly --nginx -d yourdomain.com
```

### 3. Update nginx config for SSL
Uncomment the SSL server block at the bottom of `nginx/nginx.conf` (or `nginx.docker.conf`) and update:
```
server_name yourdomain.com www.yourdomain.com;
ssl_certificate     /etc/nginx/ssl/cert.pem;
ssl_certificate_key /etc/nginx/ssl/key.pem;
```

### 4. Update environment
```bash
# In .env
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
PORTAL_BASE_URL=https://yourdomain.com
```

### 5. Deploy with Docker Compose
```bash
docker-compose -f docker-compose.prod.yml pull
docker-compose -f docker-compose.prod.yml up -d --build
```

### 6. Update `web.base.url` in Odoo
Log in to Odoo → Settings → Technical → System Parameters → `web.base.url`  
Set to `https://yourdomain.com`

### Production Odoo config (`odoo.conf`)
```ini
workers = 4
gevent_port = 8072
limit_time_cpu = 600
limit_time_real = 1200
proxy_mode = True
log_level = warn
```

---

## API Integration Reference

### Odoo XML-RPC endpoints

| Endpoint | Purpose |
|---|---|
| `/xmlrpc/2/common` | Authentication (`authenticate`) |
| `/xmlrpc/2/object` | Model CRUD (`execute_kw`) |

### Authenticate
```python
import xmlrpc.client

url = "http://localhost:8069"
db, username, password = "berit_odoo", "admin", "admin"

common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
uid = common.authenticate(db, username, password, {})
```

### Read loan applications
```python
models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

loans = models.execute_kw(db, uid, password,
    "berit.loan.application", "search_read",
    [[["state", "=", "active"]]],
    {"fields": ["name", "loan_amount", "state", "applicant_id"]}
)
```

### Create a loan application
```python
loan_id = models.execute_kw(db, uid, password,
    "berit.loan.application", "create",
    [{
        "applicant_id": partner_id,
        "loan_amount": 150000.0,
        "loan_duration": 6,
        "loan_purpose": "Business expansion",
    }]
)
```

### Django portal REST endpoints (internal)

| Method | URL | Description |
|---|---|---|
| `GET` | `/portal/` | Portal home / redirect |
| `GET/POST` | `/portal/loans/apply/` | Start loan application wizard |
| `GET` | `/portal/loans/` | List client's loan applications |
| `GET` | `/portal/loans/<uuid>/` | Loan detail + repayment schedule |
| `POST` | `/portal/documents/upload/` | Upload a document |
| `GET` | `/portal/dashboard/` | Client dashboard |
| `GET` | `/health/` | Health check (returns 200 OK) |
| `POST` | `/api/webhook/odoo/` | Odoo → Django status webhook |

---

## Loan Business Rules Reference

### Application Flow
```
1. Client registers on portal → KYC documents uploaded
2. Client submits loan application (amount, duration, purpose, employment)
3. Documents uploaded (ID, KRA PIN, payslips, bank statements)
4. Application synced to Odoo via XML-RPC
5. Loan officer reviews in Odoo:
   a. Verifies collateral (must be ≥ 1.5× loan amount)
   b. Verifies guarantor(s)
   c. Checks CRB clearance
   d. Approves / rejects
6. On approval → repayment schedule auto-generated in Odoo
7. Schedule synced back to Django portal
8. Daily crons: mark overdue, send reminders, check document expiry
9. On full repayment → loan marked closed
10. If >30 days overdue → loan marked defaulted
```

### Repayment Calculation
```
Monthly Repayment = (Loan Amount × Monthly Rate) + (Loan Amount / Duration)
Total Repayable   = Monthly Repayment × Duration
Legal Fee         = Loan Amount × 2.5%
Penalty           = Total Installment Due × 1% × Days Overdue
```

---

## Troubleshooting

### WebSocket error: "Couldn't bind the websocket. Is the connection opened on the evented port (8072)?"
Odoo's gevent worker is not running or Nginx is not routing to it.

```bash
# Verify gevent port in odoo.conf
grep -E "gevent_port|workers" odoo/odoo.conf
# Must have: workers >= 2 AND gevent_port = 8072

# Verify Nginx routes /websocket to port 8072
grep -A5 "location /websocket" nginx/nginx.conf

# Restart with explicit gevent port
python odoo-bin --config=odoo/odoo.conf --gevent-port=8072
```

### `ParseError: forbidden opcode(s) IMPORT_NAME, IMPORT_FROM` in cron XML
Odoo cron `code` fields run in a sandboxed interpreter that blocks `import` statements.

**Fix:** Move all logic into a model method and call only `model.method_name()` in the XML.

```xml
<!-- WRONG -->
<field name="code">
from dateutil.relativedelta import relativedelta
...
</field>

<!-- CORRECT -->
<field name="code">model.send_due_soon_reminders()</field>
```

### `relation "ir_module_module" does not exist` warning for `berit_portal`
The `berit_portal` database exists in PostgreSQL but has never had Odoo installed into it.
This is harmless — Odoo's cron poller tries all known databases.

```bash
# To silence it permanently, drop the empty database:
dropdb -U berit_user berit_portal
# Then recreate it properly (Django only uses it, not Odoo):
createdb -U berit_user berit_portal
```

### Django portal `502 Bad Gateway`
Django is not running or crashed.

```bash
# Check if Django process is alive
ps aux | grep "manage.py runserver"

# Check Django logs
tail -50 logs/startup_*.log

# Restart manually
source django_env/bin/activate
cd django_portal
python manage.py runserver 0.0.0.0:8000
```

### Celery tasks not running
```bash
# Check Redis is up
redis-cli ping   # Should return PONG

# Check worker is running
ps aux | grep celery

# Check beat is running
tail -f logs/celery_beat.log

# Restart worker
celery -A config worker --loglevel=info
```

### Odoo module upgrade fails
```bash
# Upgrade from command line (safer than UI for debugging)
source odoo_env/bin/activate
python /home/nick/odoo-19/odoo-bin \
    --config=odoo/odoo.conf \
    -d berit_odoo \
    -u berit_loan \
    --stop-after-init
```

### Permission denied on startup script
```bash
chmod +x start_system_improved.sh start_system.sh
```

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Make your changes following the existing code style
4. Test thoroughly (including module upgrade in Odoo)
5. Commit with a descriptive message: `git commit -m "feat: add loan top-up workflow"`
6. Push and open a Pull Request against `master`

### Code conventions
- **Python:** PEP 8, 4-space indent, double quotes for strings
- **Odoo models:** one file per model, `@api.depends` on all computed fields
- **Django:** class-based views preferred, model methods for business logic
- **Cron code fields:** single `model.method()` call only — no imports, no multi-line code
- **Commits:** use conventional commits (`feat:`, `fix:`, `docs:`, `chore:`)

---

## License

This project is licensed under the **GNU Lesser General Public License v3 (LGPL-3)**.  
See the [LICENSE](https://www.gnu.org/licenses/lgpl-3.0.html) for full terms.

---

**Berit Shalvah Financial Services Ltd**  
📍 Kenya  
🌐 https://beritshalvah.co.ke  
📧 info@beritshalvah.co.ke