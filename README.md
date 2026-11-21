# Samwab API

Back end for Samwab Luxury, a vault for vintage luxury. Pieces are verified once,
stored near buyers, and can change owner without moving. This repository holds the
Django API. The front ends live in their own repository.

## Stack

| Tool | Version |
|---|---|
| Python | 3.13 |
| Django | 6.1 |
| Django REST Framework | 3.18 |
| API description | drf-spectacular (OpenAPI 3) |
| Sign-up and login | django-allauth 65 (headless API) |
| Password hashing | Argon2 |
| Tests | pytest, pytest-django |
| Code quality | Ruff (lint and format), mypy |

## Run it on your machine

You need Python 3.13 and Git. On Windows, use Git Bash.

```bash
python -m venv .venv
source .venv/Scripts/activate        # macOS and Linux: source .venv/bin/activate
python -m pip install -r requirements/dev.txt
cp .env.example .env                 # then set DJANGO_SECRET_KEY to any long random text
python manage.py migrate             # creates the local database (db.sqlite3)
python manage.py createsuperuser     # your own admin login: an email and a password
python manage.py runserver
```

Open http://127.0.0.1:8000/api/v1/health/ and you should see `{"status": "ok"}`.
Log in to the admin site at http://127.0.0.1:8000/admin/ with the email and password
you just chose.

Activate the virtual environment (`source .venv/Scripts/activate`) in every new
terminal window before you run `python` or `pip`.

The local database is a SQLite file for now. It is ignored by Git, so every
developer has their own. It moves to PostgreSQL in a later build.

Emails, such as sign-up codes, are printed in the terminal where `runserver` runs.
Nothing is sent from your machine.

## Checks to run before you push

```bash
python -m ruff check .          # lint
python -m ruff format .         # format
python -m mypy                  # type check
python manage.py check          # Django's own checks
python -m pytest                # tests
```

To run the lint and format checks automatically before every commit, run
`pre-commit install` once.

## Project structure

```
apps/                 our code, one folder per business area
  accounts/           users: the User model, its manager and its admin screens
  catalog/            brands, categories, designs, materials, capture protocols and
                      comparable sales; the catalog manager
    models/           one file per subject; import models from apps.catalog.models
  core/               shared building blocks used by every other app
    ids.py            new_uuid(): the ID every row gets
    models.py         BaseModel: id, created_at, updated_at
    money.py          Money: whole cents plus a currency
    policy.py         time limits and default rates
    exceptions.py     AppError: what services raise when a rule says no
    request_id.py     gives every request an ID
    logs.py           puts the request ID on log lines; JSON logs
    api/              views and URLs
      errors.py       the one error format
      pagination.py   the one way lists are paged
    tests/            tests for this app
configurations/       project wiring only
  settings/           base.py plus one file per environment
  urls.py             mounts each app's URLs under /api/v1/
requirements/         base.txt, dev.txt, prod.txt
.github/workflows/    CI: lint, types, checks and tests on every pull request
```

Inside an app, code is split by job:

- `models.py`: data only.
- `selectors.py`: reads.
- `services.py`: writes and business rules.
- `api/`: thin views that check input, call one service and return the result.

Files are added when an app needs them, so not every app has every file.

## Apps

| App | What it owns |
|---|---|
| `accounts` | Users. People log in with their email; there is no username. |
| `catalog` | What can be sold: brands, categories, named designs (such as the Kelly 28) and materials; the capture protocols staff follow for each category or design; comparable sales for fair prices. Staff run it in the admin site; the API only reads it. |
| `core` | Shared building blocks: IDs, `BaseModel`, `Money`, policy values, errors, paging, request IDs, the API description and the health endpoint. |

## Shared building blocks

Every app uses these, so learn them first. They live in `apps/core`.

| Use | Import | Rule |
|---|---|---|
| A new model | `from apps.core.models import BaseModel` | Every model extends `BaseModel`. It adds `id`, `created_at` and `updated_at`. |
| A new ID | `from apps.core.ids import new_uuid` | IDs are UUID version 7: they sort by creation time and cannot be guessed. |
| An amount of money | `from apps.core.money import Money` | Money is whole cents plus a currency. Never use floats or decimals. |
| A time limit or default rate | `from apps.core import policy` | Read the value from `policy`. Never type the number into your own code. |
| A business rule that says no | `from apps.core.exceptions import AppError` | Services raise `AppError` (or `NotFoundError`, `PermissionDeniedError`, `ConflictError`). They never build an HTTP response. |

```python
from apps.core.money import Money

price = Money(100_000)  # $1,000.00
commission = price.share(2_500)  # 25% -> Money(25_000)
owner_share = price - commission  # Money(75_000)
deposit, rest = price.split([1, 1])  # two parts that add up to the price
```

`Money` refuses negative amounts, floats and mixed currencies, so those mistakes
fail at once and never reach the database.

## API

| Method and path | Purpose | Login needed |
|---|---|---|
| `GET /api/v1/health/` | Says the API is running | No |
| `GET /api/v1/me/` | The logged-in user: profile, roles and onboarding steps | Yes |
| `PATCH /api/v1/me/` | Change her names, country, locale or timezone | Yes |
| `GET /api/v1/brands/` | Active brands, A to Z | No |
| `GET /api/v1/categories/` | Active categories in menu order | No |
| `GET /api/v1/product-models/` | Active named designs. Filters: `?brand=<slug>&category=<slug>` | No |
| `GET /api/v1/docs/` | A page to browse and try every endpoint | No |
| `GET /api/v1/schema/` | The OpenAPI file. Import it into Postman. Add `?format=json` for JSON | No |

Every endpoint needs a logged-in user unless the table says otherwise.

The docs and the OpenAPI file are built from the code, so they are always current.

### Users

- Everyone is a `User` (`apps/accounts/models.py`): buyers, owners, dealers and staff.
- People log in with their email address. Emails are stored in lowercase, so
  `Ada@Example.com` and `ada@example.com` are the same account.
- One account per person. Every account can buy, so there is no buyer role.
- Other roles are Django groups with these names: `owner`, `dealer`, `intake_staff`,
  `reviewer`, `catalog_editor`, `partner`, `support`, `finance`, `admin`
  (`apps/accounts/roles.py`). `owner` is added when Stripe enables her payouts,
  `dealer` when an admin approves her application, and staff roles by an admin in
  the admin site. Sign-up never grants a role.
- `signup_intent` records which sign-up page she used (`buyer`, `owner` or `dealer`).
  It only decides which onboarding she sees.
- Always get the model with `get_user_model()` or `settings.AUTH_USER_MODEL`, and
  create users with `User.objects.create_user(email, password)`.

### Sign-up and login (django-allauth)

Sign-up, login, logout, email codes and password reset are django-allauth's
headless API under `/_allauth/browser/v1/`. These endpoints use allauth's own
response and error format, not ours. allauth describes them at
http://127.0.0.1:8000/_allauth/openapi.html.

| Method and path | Purpose |
|---|---|
| `GET /_allauth/browser/v1/config` | Call once when the web app loads. It sets the `csrftoken` cookie |
| `POST /_allauth/browser/v1/auth/signup` | `{"email", "password", "intent"}`. `intent` is `buyer` (default), `owner` or `dealer` |
| `POST /_allauth/browser/v1/auth/email/verify` | `{"key": "123456"}`: the 6-digit code from the email. Logs her in |
| `POST /_allauth/browser/v1/auth/login` | `{"email", "password"}` |
| `GET /_allauth/browser/v1/auth/session` | Is she logged in? |
| `DELETE /_allauth/browser/v1/auth/session` | Log out |
| `POST /_allauth/browser/v1/auth/password/request` | `{"email"}`: sends a 6-digit reset code |
| `POST /_allauth/browser/v1/auth/password/reset` | `{"key", "password"}`: sets the new password |

How the web app uses them:

1. Every request that changes something sends the `X-CSRFToken` header with the
   value of the `csrftoken` cookie. Without it the answer is 403 `csrf_failed`.
2. Sign-up answers 401 with the `verify_email` flow pending. The account exists, but
   she is not logged in until she enters the code from her email.
3. After login or verification, call `GET /api/v1/me/`. Its `roles` and `next_steps`
   decide which screen to open: an empty `next_steps` means nothing is waiting.
4. Signing up with an email that already has an account gives the same answer as a
   new sign-up, and the owner of that email gets an "account already exists" email.
   Nobody can use sign-up or password reset to find out who has an account.
5. After 5 wrong passwords for one email, login is refused for 5 minutes
   (`too_many_login_attempts`). A login in the first 10 seconds after sign-up is also
   refused that way, because a fresh code can only be sent once every 10 seconds.

`next_steps` values: `accept_terms`, `identity_check`, `payout_account`,
`dealer_application`, `await_dealer_decision`. Until the builds that record terms,
ID checks, payout accounts and dealer applications are done, every step of the
onboarding she chose is listed until the matching role is granted.

### Catalog

The store's menus and filters read three public lists. They need no login.

- `GET /api/v1/brands/`: `id`, `name`, `slug`, A to Z by slug.
- `GET /api/v1/categories/`: `id`, `parent_id`, `name`, `slug`, `attribute_schema`.
  Lowest `sort_order` first, then by slug. `parent_id` puts a category under
  another one, so the web app builds the menu tree itself.
- `GET /api/v1/product-models/`: `id`, `brand_id`, `category_id`, `name`, `slug`,
  `era_from`, `era_to`, by slug. `?brand=hermes&category=bags` filters by slugs.
  An unknown slug gives an empty list; a badly formed one (`?brand=Hermès!`) gives
  400 `validation_error`.

Only active rows are shown. A design is hidden when it, its brand or its category
is retired.

Staff run the catalog in the admin site (`/admin/catalog/`):

- They add, rename, reorder (the `sort_order` column in the category list) and
  retire rows. Brands, categories and designs are retired, never deleted, so the
  pieces and history that point at them stay. A material added by mistake can be
  deleted.
- A slug is filled in from the name when the row is created and never changes
  afterwards, because the web app's links use it.
- The admin checks the rules before saving: a category cannot sit under its own
  children, `attribute_schema` is a JSON object, `flaw_types` is a list of codes
  such as `["pilling", "missing_stone"]`, an HS code is 6 to 10 digits, and a
  design's years run from 1800 to next year, first year before last.
- **Capture protocols** (`/admin/catalog/captureprotocol/`) list the photos and
  readings staff take of a piece, in order: for example a macro photo of the heat
  stamp, or a scale reading. A protocol is a category's default, or belongs to one
  design. Staff add a protocol (it starts as a draft, numbered v1, v2 and so on), add
  its shots, then use the "Activate" action. Activating retires the version it
  replaces. An active protocol's shots are locked, because evidence taken under it
  must keep matching it: to change it, use "Make a new draft version", which copies
  the shots. Only drafts can be deleted. A photo uses a phone, macro lens, microscope
  or loupe; a reading uses an XRF analyser, diamond tester or scale. In code,
  `selectors.active_protocol_for(category=..., product_model=...)` gives the
  protocol that applies: the design's own if it has one, otherwise the category's.
- **Comparable sales** (`/admin/catalog/comparablesale/`) record what similar
  pieces sold for, in whole US cents (convert other currencies on the sale date).
  The design, when given, must match the brand and category. They feed the
  fair-price explainer and the low-bid check in later builds.
- A category records the staff member who last changed it (`updated_by`). Every
  change becomes an audit event in build 07, and the `catalog_editor` role gets
  its permissions there too. Until then, only superusers can use these screens.

### Errors

Every error has the same shape, with the content type `application/problem+json`:

```json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "code": "validation_error",
  "detail": "One or more fields are invalid.",
  "instance": "/api/v1/me/",
  "errors": [
    {"field": "address.city", "code": "required", "message": "This field is required."}
  ],
  "request_id": "0193a1b2c3d47e5f8a1b2c3d4e5f6a7b"
}
```

- `code` never changes for a given error, so the front end decides what to do from `code`.
- `detail` and `message` are written for people and may be reworded.
- `instance` is the path of the request that failed.
- `errors` appears only when single fields are wrong. `field` is `null` when the
  problem is with the request as a whole. Items in a list show their position: `lines.1.price`.

| Status | `code` | When |
|---|---|---|
| 400 | `validation_error` | One or more fields are wrong |
| 400 | `parse_error` | The body is not valid JSON |
| 401 | `not_authenticated` | Not logged in |
| 403 | `permission_denied` | Logged in, but not allowed |
| 403 | `csrf_failed` | The `X-CSRFToken` header is missing or wrong |
| 404 | `not_found` | No such address or object |
| 405 | `method_not_allowed` | Wrong HTTP method |
| 409 | `conflict` | The request clashes with the current state |
| 415 | `unsupported_media_type` | The body is not sent as JSON |
| 422 | a rule's own code, such as `bid_too_low` | A business rule said no |
| 429 | `throttled` | Too many requests. See the `Retry-After` header |
| 500 | `server_error` | Our fault. The cause is in the logs, never in the response |

### Lists and paging

Every list is paged the same way: 25 rows per page, newest first unless the
endpoint says otherwise (the catalog lists are A to Z or in menu order).

```json
{"next": "cD0yMDI2LTEx...", "previous": null, "results": []}
```

`next` and `previous` are cursors, not links. To get the next page, send the same
request again with `?cursor=<next>`. Stop when `next` is `null`. Ask for a different
size with `?page_size=50` (100 at most), and send it again with every page.
There are no page numbers.

For developers: a list in another order uses
`pagination_class = ordered_by("slug")` (`apps/core/api/pagination.py`). The cursor
stands on the first field only, so that field must be unique per row. When the
display order is not unique, a selector adds a unique `position` value to sort on
(see `apps/catalog/selectors.py`); otherwise the previous page can skip rows.

### Request IDs

Every response has an `X-Request-ID` header, and errors repeat it as `request_id`.
Every log line written while handling the request carries the same ID. When
something goes wrong, ask for that ID and search the logs for it. A caller may
send its own `X-Request-ID` (8 to 64 letters, digits, `.`, `_` or `-`).

Logs are plain text on your machine and one JSON object per line on servers.

## Settings and environment variables

Pick the settings file with `DJANGO_SETTINGS_MODULE`. `manage.py` uses
`configurations.settings.local`. Tests use `configurations.settings.test`.
Servers use `configurations.settings.production` (or `staging`).

| Variable | Needed in | Meaning |
|---|---|---|
| `DJANGO_SECRET_KEY` | everywhere | Long random text used for signing |
| `DJANGO_ALLOWED_HOSTS` | staging, production | Host names the API answers to, comma separated |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | staging, production | Front-end addresses allowed to send forms, comma separated |
| `DJANGO_FRONTEND_URL` | staging, production | The web app's address, used for links in emails. Default `http://localhost:3000` |
| `DJANGO_DEFAULT_FROM_EMAIL` | staging, production | Sender of every email, such as `Samwab <no-reply@samwab.com>` |
| `DJANGO_EMAIL_HOST`, `DJANGO_EMAIL_PORT`, `DJANGO_EMAIL_USER`, `DJANGO_EMAIL_PASSWORD`, `DJANGO_EMAIL_USE_TLS` | staging, production | The email provider's SMTP details. Port defaults to 587 and TLS to on |

Secrets never go into Git. `.env` is ignored, and `.env.example` lists every variable.

## Branches

- `main`: production.
- `dev`: deployed first. All work merges here.
- `feature/...`: one branch per build, merged into `dev` by pull request.

## Build status

Last build: 13, catalog B (capture protocols and shots, comparable sales).

## Build history

One line per build, newest last. Each build is one feature, merged into `dev`.

| Build | Date | What it added |
|---|---|---|
| 00 | 14 Nov 2026 | Project skeleton: settings per environment, requirements, Ruff, mypy, pytest, CI, health endpoint |
| 02 | 14 Nov 2026 | Core types: UUID version 7 IDs, `BaseModel`, `Money`, policy values |
| 03 | 14 Nov 2026 | API basics: one error format, cursor paging, request IDs, JSON logs, API docs |
| 04 | 14 Nov 2026 | Custom user: email login, lowercase emails, first migration, admin screens |
| 05 | 17 Nov 2026 | Sign-up and login with django-allauth, 6-digit email codes, password reset, `GET`/`PATCH /api/v1/me/`, role groups, `signup_intent`, Argon2, JSON CSRF errors, 422 for business rules, bare paging cursors |
| 12 | 21 Nov 2026 | Catalog A: `brands`, `categories`, `product_models`, `materials`; public lists `GET /api/v1/brands/`, `/categories/`, `/product-models/`; the catalog manager in the admin site |
| 13 | 21 Nov 2026 | Catalog B: `capture_protocols` and `capture_shots` (draft, active, retired versions), `comparable_sales`; their admin screens; `catalog.models` split into one file per subject |

Builds run in the order the roadmap sets, so numbers can skip: builds 12 and 13 came
before 06 to 11 to start on what buyers see. Build 01 (PostgreSQL on Neon) runs just before build 09.
