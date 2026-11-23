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
| Piece attribute rules | jsonschema 4.26 (JSON Schema draft 2020-12) |
| Tests | pytest, pytest-django |
| Code quality | Ruff (lint and format), mypy |

## Contents

1. [Set up your machine](#set-up-your-machine) (first time only, about 15 minutes)
2. [Run the app](#run-the-app)
3. [Try it](#try-it): the admin site, staff roles and the audit log, sign-up from the command line
4. [Everyday commands](#everyday-commands)
5. [How we write code](#how-we-write-code): layers, test-driven development, test rules
6. [Checks to run before you push](#checks-to-run-before-you-push)
7. [Git and build scripts](#git-and-build-scripts)
8. [When something goes wrong](#when-something-goes-wrong)
9. Reference: [project structure](#project-structure), [apps](#apps), [shared building blocks](#shared-building-blocks), [API](#api), [staff roles and the audit log](#staff-roles-and-the-audit-log), [safe retries](#safe-retries-the-idempotency-key-header), [deploying to Render](#deploying-to-render-and-neon), [settings](#settings-and-environment-variables), [build history](#build-history)

## Set up your machine

Do this once per computer. Every command below is typed in a terminal: on Windows
use **Git Bash** (it comes with Git), on macOS or Linux use the normal terminal.

### 1. Install the tools

| Tool | Why | Get it |
|---|---|---|
| Git | Get the code, save your work | https://git-scm.com/downloads (on Windows this also installs Git Bash) |
| Python 3.13 | Runs the app | https://www.python.org/downloads/ (choose 3.13.x). On Windows, tick **"Add python.exe to PATH"** in the installer |
| A code editor | Read and change the code | VS Code is what the team uses: https://code.visualstudio.com/ |

Check them. Each command should print a version:

```bash
git --version
py -3.13 --version        # Windows
python3.13 --version      # macOS and Linux
```

You do not need to install a database, Docker or Redis yet. The local database is
a single file that Django creates for you.

### 2. Get the code

```bash
cd ~/Desktop
git clone https://github.com/SamwabLuxury/samwab-luxury-backend.git samwab
cd samwab
git checkout dev                           # all work starts from dev (GitHub's default branch)
```

### 3. Make the virtual environment

A virtual environment (`.venv`) keeps this project's packages apart from the rest
of your computer. Create it once, inside the project folder:

```bash
py -3.13 -m venv .venv            # Windows
python3.13 -m venv .venv          # macOS and Linux
```

Then **activate it**. Do this in every new terminal window, before any `python` or
`pip` command:

```bash
source .venv/Scripts/activate     # Windows (Git Bash)
source .venv/bin/activate         # macOS and Linux
```

Your prompt now starts with `(.venv)`. Check that it is the right Python:

```bash
python --version                  # must say Python 3.13.x
```

### 4. Install the packages

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements/dev.txt
```

`requirements/base.txt` is what the app needs everywhere; `dev.txt` adds the test
and code-quality tools; `prod.txt` adds the web server used on servers. Versions are
pinned, so everyone gets exactly the same packages.

### 5. Create your `.env` file

The app reads its secret settings from a file called `.env`, which Git ignores.

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Open `.env` in your editor and replace `change-me` with the long text the second
command printed. Nothing else is needed on your machine.

### 6. Create the database and your admin login

```bash
python manage.py migrate            # creates db.sqlite3 with every table
python manage.py createsuperuser    # asks for your email and a password
```

The superuser is your own login for the admin site. Use your real email; there is
no username.

### 7. Turn on the pre-commit checks (optional, recommended)

```bash
pre-commit install
```

From now on, every `git commit` first runs the linter and formatter on the files
you changed, so badly formatted code never reaches a commit.

## Run the app

```bash
cd ~/Desktop/samwab
source .venv/Scripts/activate       # macOS and Linux: source .venv/bin/activate
python manage.py runserver
```

Leave that terminal open; the app runs until you press `Ctrl+C`. Open a second
terminal for anything else (and activate the virtual environment there too).

| Open | What you see |
|---|---|
| http://127.0.0.1:8000/api/v1/health/ | `{"status": "ok"}`: the API is running |
| http://127.0.0.1:8000/admin/ | The admin site. Log in with your superuser email and password |
| http://127.0.0.1:8000/api/v1/docs/ | Every endpoint of our API, with a "Try it out" button |
| http://127.0.0.1:8000/_allauth/openapi.html | The sign-up and login endpoints (django-allauth) |
| http://127.0.0.1:8000/api/v1/schema/ | The OpenAPI file. Import it into Postman |

On your machine:

- `manage.py` uses `configurations.settings.local`: debug pages are on and DRF's
  browsable pages are shown.
- Emails, such as sign-up codes, are **printed in the `runserver` terminal**.
  Nothing is sent.
- The database is the file `db.sqlite3`. It is yours alone; Git ignores it.
  It moves to PostgreSQL (Neon) in build 01.

## Try it

### The catalog, in the admin site

1. Open http://127.0.0.1:8000/admin/catalog/brand/add/, type `Hermès` and save.
   The slug (`hermes`) fills itself in.
2. Add a category (`Bags`) and a design (`Kelly 28`, brand Hermès, category Bags).
3. Open http://127.0.0.1:8000/api/v1/brands/ and
   http://127.0.0.1:8000/api/v1/product-models/?brand=hermes to see them in the API.

### Photos of a piece

1. Open a piece in the admin site (http://127.0.0.1:8000/admin/pieces/piece/).
2. In **Photos** at the bottom, choose a JPEG, PNG or WebP file, pick its kind
   (listing photo, condition photo or flaw close-up) and save.
3. The photo shows as a small preview. Its file is in the `media/pieces/` folder,
   under a new name, with its location data removed.

### List a piece for sale

Log in to the admin site as a superuser (only admins list pieces for now).

1. The piece must be house stock in the vault with at least one listing photo.
   On your machine, put it in the vault from `python manage.py shell`:
   ```python
   from apps.inventory.pieces.models import Piece

   Piece.objects.filter(title="Kelly 28, Gold Togo").update(custody_status="in_vault")
   ```
   (On the live system, custody events will do this; this shortcut is for trying it out.)
2. Open http://127.0.0.1:8000/admin/listings/listing/add/, pick the piece, choose
   **From the vault**, type the price in cents (`1250000` is $12,500.00) and save.
3. On the list page, tick it, choose **Publish the selected drafts** and press **Go**.
4. Open http://127.0.0.1:8000/api/v1/listings/ to see it in the browse API.

### Staff roles and the audit log

1. Open http://127.0.0.1:8000/admin/audit/auditevent/. Every change you just made
   is there: who, what, which row, the old and new values, your IP address and the
   request ID. Nothing on this screen can be changed or deleted.
2. Add a staff member: http://127.0.0.1:8000/admin/accounts/user/add/, any email and
   password. On the next page tick **Staff status**, add the group `catalog_editor`
   and save. The audit log now shows `accounts.user.changed` with the role given.
3. Log in as that person in a private browser window. They see the catalog screens
   only. Add them to `intake_staff` instead and they see pieces, with the catalog
   read only.

### Add a delivery address

Log in at http://127.0.0.1:8000/admin/ first (the API uses the same login), then
open http://127.0.0.1:8000/api/v1/me/addresses/. At the bottom of the page, send:

```json
{"recipient_name": "Adaeze Obi", "line1": "12 Admiralty Way", "city": "Lagos", "country": "NG"}
```

The answer has `"is_default": true` (your first address). In the database the name
and street are unreadable; only the city is plain:

```bash
python manage.py shell -c "from django.db import connection; c = connection.cursor(); c.execute('SELECT recipient_name_enc, line1_enc, city FROM addresses'); print(c.fetchall())"
```

### Check the Stripe sandbox keys

1. In the Stripe dashboard, check the **Sandbox** banner, open **Developers** →
   **API keys** and copy the **secret key** (`sk_test_...`).
2. Add it to your `.env` (never to Git or chat):
   ```
   STRIPE_SECRET_KEY=sk_test_...
   ```
3. Run `python manage.py check_payments`. It makes a $1.00 test payment and
   cancels it, then says `Payments are working with stripe.` In the dashboard,
   **Payments** shows the cancelled $1.00. It refuses live keys.

### Buy a piece, end to end (Stripe sandbox)

You need a live listing (above) and your sandbox key in `.env`. The buyer must be
a different account from the admin (an admin cannot buy the house's own stock).

1. Sign up and log in a buyer with the commands in the next section, "Sign up and
   log in from the command line" (steps 1 to 3). Keep that terminal: `API`,
   `TOKEN` and `cookies.txt` are used below.
2. Copy a listing's `id` from `curl -s $API/api/v1/listings/`, then buy it:
   ```bash
   curl -s -b cookies.txt -H "X-CSRFToken: $TOKEN" -H "Idempotency-Key: try-1" \
     -H "Content-Type: application/json" \
     -d '{"listing_id": "<the listing id>", "payment_option": "pay_in_full", "delivery_choice": "keep_in_vault"}' \
     $API/api/v1/orders/
   ```
   The answer has the order (`pending_payment`, `pay_by` 15 minutes ahead) and a
   `payment` whose `client_secret` starts with the Stripe payment's id (`pi_...`).
   Sending it again with the same `Idempotency-Key` gives the same answer.
3. Pay it as a buyer would, with Stripe's test card, in the Stripe sandbox's
   **Workbench → Shell**:
   ```
   stripe payment_intents confirm pi_... -d payment_method=pm_card_visa -d return_url=https://example.com
   ```
   (`return_url` is needed because the payment accepts every method switched on in
   the dashboard, and some of those leave the page.)
4. Stripe cannot reach your machine, so ask it: `python manage.py reconcile_payments`.
   `curl -s -b cookies.txt $API/api/v1/orders/` now shows `paid`, and the listing
   is `sold`. (On the live site the webhook does this by itself.)

To see a decline, confirm with `-d payment_method=pm_card_chargeDeclined` instead:
the order stays `pending_payment` and the admin shows the reason on its payment.

### Sign up and log in from the command line

The web app does exactly this. Run it in a second terminal while `runserver` is
running (Git Bash on Windows includes `curl`):

```bash
API=http://127.0.0.1:8000

# 1. Get the CSRF cookie. The web app calls this once when it loads.
curl -s -c cookies.txt $API/_allauth/browser/v1/config > /dev/null
TOKEN=$(grep csrftoken cookies.txt | awk '{print $7}')

# 2. Sign up. The answer is 401 with "verify_email" pending: that is expected.
curl -s -b cookies.txt -c cookies.txt -H "X-CSRFToken: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "correct-horse-battery-9"}' \
  $API/_allauth/browser/v1/auth/signup

# 3. Find the 6-digit code in the runserver terminal, then:
curl -s -b cookies.txt -c cookies.txt -H "X-CSRFToken: $TOKEN" \
  -H "Content-Type: application/json" -d '{"key": "123456"}' \
  $API/_allauth/browser/v1/auth/email/verify

# 4. You are logged in. See your own account:
curl -s -b cookies.txt $API/api/v1/me/
```

Delete `cookies.txt` when you are done. Section [Sign-up and login](#sign-up-and-login-django-allauth)
explains every endpoint.

## Everyday commands

Run these with the virtual environment active, from the project folder.

| Task | Command |
|---|---|
| Start the app | `python manage.py runserver` |
| Start it on another port | `python manage.py runserver 8001` |
| Run every test | `python -m pytest` |
| Run one test file | `python -m pytest apps/inventory/catalog/tests/test_api.py` |
| Run one test | `python -m pytest apps/inventory/catalog/tests/test_api.py::test_brands_are_public_and_match_the_contract` |
| Run tests whose name matches | `python -m pytest -k slug` |
| Run only the tests that failed last time | `python -m pytest --lf` |
| Stop at the first failure, show prints | `python -m pytest -x -s` |
| Tests with coverage | `python -m pytest --cov --cov-report=term-missing` |
| Make migrations after changing a model | `python manage.py makemigrations` |
| Apply migrations | `python manage.py migrate` |
| See which migrations are applied | `python manage.py showmigrations` |
| A Python shell with the app loaded | `python manage.py shell` |
| Start the local database again from empty | Stop `runserver`, delete `db.sqlite3`, then `python manage.py migrate` and `python manage.py createsuperuser` |
| Update packages after a pull | `python -m pip install -r requirements/dev.txt` |
| Delete idempotency keys older than 24 hours | `python manage.py delete_expired_idempotency_keys` (the scheduler runs it from build 09) |

Tests use their own settings (`configurations.settings.test`) and a fresh, empty
database every run. They never touch your `db.sqlite3`.

## How we write code

### Where code goes

Each business area is one app under `apps/`. Inside an app, code is split by job,
and each layer only calls the layers below it:

```
api/views.py      thin: check the input, call one selector or service, return the result
api/serializers.py  the shape of the JSON in and out; no business rules
services.py       every write and every business rule (raises AppError when a rule says no)
selectors.py      every read the API needs (what the public may see, in which order)
models.py         tables, database constraints and simple field checks in clean()
```

Rules:

- No business logic in views, serializers, `save()` or signals. If you are writing
  an `if` about a business rule in a view, it belongs in a service.
- Apps talk to each other only through their services and selectors.
- A rule the database can enforce (unique, check) is also a database constraint,
  so no code path can break it.
- Money is always `Money` (whole cents). Time limits and rates come from `policy`.
- Staff write through services too: the admin's `save_model`, `delete_model`,
  `save_formset` and actions call them.
- Every staff change records an audit event in the same transaction, from the
  service (see [Staff roles and the audit log](#staff-roles-and-the-audit-log)).

### Test-driven development (TDD)

We write the test **before** the code. Every change follows the same loop:

1. **Red.** Write a test that describes one behaviour, run it, and watch it fail.
   A test you have never seen fail proves nothing.
2. **Green.** Write the simplest code that makes it pass. Run the whole suite.
3. **Refactor.** Clean up the code and the test while everything stays green.
4. Repeat for the next behaviour, then the edge cases.

A real example from the catalog:

```python
# 1. Red: apps/inventory/catalog/tests/test_api.py. Fails: there is no /api/v1/brands/ yet.
def test_brands_are_in_alphabetical_order_and_leave_out_retired_ones(client):
    for name in ("Hermès", "Chanel", "Rolex"):
        make_brand(name)
    make_brand("Ancienne Maison", is_active=False)

    rows = client.get("/api/v1/brands/").json()["results"]

    assert [row["slug"] for row in rows] == ["chanel", "hermes", "rolex"]


# 2. Green: the selector decides what the public sees, the view stays thin.
def public_brands():
    return Brand.objects.filter(is_active=True)
```

Write the test so its name reads as a sentence about the behaviour
(`test_a_slug_cannot_change_after_it_is_created`), and lay out its body in three
parts separated by blank lines: set up, act, check.

### Test rules

- Tests live next to the code: `apps/<app>/tests/test_<subject>.py`.
- Make rows with the app's helpers, such as `make_brand()` or `make_protocol()` in
  `apps/inventory/catalog/tests/helpers.py`. They fill in sensible defaults, so a test only
  names what it cares about. Add a helper when you add a model.
- Mark tests that use the database with `pytestmark = pytest.mark.django_db`.
- Outside services (Stripe, the model service, email, couriers) are replaced with
  fakes. Tests never call the internet.
- Every endpoint is tested for: success, not logged in, wrong role, someone else's
  object, invalid input, not found, and the same request twice.
- Think through the edge cases that apply: empty, missing, too long, wrong type,
  non-English text, zero, negative and very large amounts; an illegal status
  change; the same action twice; a deadline exactly on time; two requests at once;
  page boundaries; database constraints.
- Every bug gets a test that fails without the fix.
- Coverage of `apps/` is 100%. A line no test reaches is either untested behaviour
  (write the test) or dead code (delete it).

## Checks to run before you push

These are exactly what CI (`.github/workflows/ci.yml`) and every build script run.
All of them must pass.

CI runs on GitHub at every push to `dev` or `main` and on every pull request, in two
jobs: **Checks and tests (SQLite)** runs everything below, and **Tests (PostgreSQL
18, as in production)** applies the migrations and runs every test again on
PostgreSQL. See the runs at
https://github.com/SamwabLuxury/samwab-luxury-backend/actions.

```bash
python -m ruff check .                                       # lint
python -m ruff format --check .                              # format (run without --check to fix)
python -m mypy                                               # type check
python manage.py check                                       # Django's own checks
python manage.py makemigrations --check --dry-run            # a model change without a migration
python manage.py spectacular --validate --fail-on-warn > /dev/null   # the API description builds
python -m pytest --cov --cov-report=term-missing             # tests and coverage
```

To run the tests on PostgreSQL on your own machine too (optional; needs a PostgreSQL
server you can reach), point `DATABASE_URL` at an empty database:

```bash
DATABASE_URL=postgres://user:password@localhost:5432/samwab python -m pytest
```

Without `DATABASE_URL`, tests use SQLite.

## Git and build scripts

### Branches

The code lives at https://github.com/SamwabLuxury/samwab-luxury-backend.

- `dev`: GitHub's default branch. All work merges here, and CI checks every push.
- `main`: what is deployed. A feature goes to `main` only when it is finished and CI
  is green on `dev`. From build 01, Render deploys `main` automatically, and only
  after CI passes on it.
- `feature/<short-name>`: one branch per task or build, made from `dev`.

Always start from an up-to-date `dev`:

```bash
git checkout dev
git pull
git checkout -b feature/b14-pieces       # one feature per branch
# ... write the test, write the code, run the checks ...
git add .
git commit -m "Build 14: pieces"
git checkout dev
git merge --no-ff feature/b14-pieces -m "Merge build 14: pieces"
git branch -d feature/b14-pieces
git push                                 # then check CI turns green on GitHub
```

To release what is on `dev` (only when CI is green on `dev`):

```bash
git checkout main
git pull
git merge --no-ff dev -m "Release: <what is in it>"
git push                                 # Render deploys main once CI passes
git checkout dev
```

Never commit `.env`, `db.sqlite3` or `.venv`. `.gitignore` already leaves them out.

### Build scripts

The lead engineer receives each build as one script, run from Git Bash:

```bash
cd ~/Desktop/samwab && git checkout dev && git pull && git status --short    # must print nothing
bash ~/Downloads/build_<number>_<name>.sh
```

The script:

1. stops before changing anything if there are uncommitted changes, you are not
   on `dev`, your `dev` is not the same as GitHub's, the venv is missing or not
   Python 3.13, or a file it replaces is not the version it expects;
2. creates `feature/b<number>-<name>` and writes the files;
3. installs packages and runs every check above;
4. applies migrations to your local database only after everything passed;
5. stops with nothing committed, and prints the commit, merge and push commands.
   Run them straight away, before switching branches: uncommitted files follow you
   to the next branch.

On any failure, or `Ctrl+C`, it puts everything back as it found it: the files,
the branch and the database file. The full log is saved in `~/samwab-build-logs/`.

## When something goes wrong

| What you see | Why | Fix |
|---|---|---|
| A build script stops with "Your dev is not the same as GitHub's" | Someone pushed to `dev`, or you have commits not pushed yet | `git pull` (or `git push`), then run the script again |
| `git push` is rejected ("fetch first", "non-fast-forward") | GitHub's `dev` has commits you do not have | `git pull`, then `git push` again |
| A red cross on GitHub's Actions page | A check failed on GitHub | Open the run, open the red job, read the failing step; run the same command on your machine |
| `server does not support SSL, but SSL was required` | The production settings insist on an encrypted database connection, and this database has none (only a local or CI database; Neon is always encrypted) | For a local or CI database only, add `?sslmode=disable` to the end of `DATABASE_URL`; never for Neon |
| Tests pass on your machine but fail in the PostgreSQL job | Something works on SQLite only (row locks, database rules) | Run the tests with `DATABASE_URL` set (see Checks to run before you push), or ask the lead |
| `ModuleNotFoundError: No module named 'django'` | The virtual environment is not active, or packages are not installed | `source .venv/Scripts/activate`, then `python -m pip install -r requirements/dev.txt` |
| No `(.venv)` at the start of the prompt | New terminal window | Activate it again (step 3) |
| `python --version` is not 3.13 | The venv was made with another Python | Delete `.venv`, then repeat steps 3 and 4 with `py -3.13` (Windows) or `python3.13` |
| `pip` installed packages but Django still cannot be found | `pip` belonged to another Python | Always use `python -m pip ...` with the venv active |
| `ImproperlyConfigured: Set the DJANGO_SECRET_KEY environment variable` | No `.env` file, or no key in it | Step 5 |
| `You have unapplied migration(s)` or `no such table` | Someone added a model since your last `migrate` | `python manage.py migrate` |
| `Error: That port is already in use.` | `runserver` is already running somewhere | Stop the other one with `Ctrl+C`, or use `python manage.py runserver 8001` |
| The admin login page says the email or password is wrong | Only staff can use the admin; or a typo | `python manage.py createsuperuser` makes a new staff login |
| A staff member logs in and sees "You don't have permission to view or edit anything" | **Staff status** is ticked but they hold no role | Add them to a role group (`catalog_editor`, `intake_staff`) on their user page |
| A role's permissions you changed by hand in the admin are back as before | Role permissions come from code and are set again on every `migrate` | Change `apps/<app>/permissions.py` in a pull request instead |
| `AuditEventIsFinalError` | Code tried to change or delete an audit event | Audit events are never changed. Record a new event instead |
| `400` with `idempotency_key_missing` or `idempotency_key_invalid` | A create request without a good `Idempotency-Key` header | Send a new random key (a UUID) in `Idempotency-Key` |
| `422` with `idempotency_key_reused` | The same key was sent with a different body or to another address | Make a new key for each new action; reuse a key only to retry the same request |
| `409` with `idempotency_key_in_progress` | The first request with that key is still running | Wait a moment and send it again: you will get its answer |
| `NotSupportedError: FOR UPDATE cannot be applied to the nullable side of an outer join` (PostgreSQL only) | A row lock on a query that joins optional related rows | Lock only the main table: `select_for_update(of=("self",))` |
| `403` with `"code": "csrf_failed"` | A request that changes something was sent without the `X-CSRFToken` header | Call `/_allauth/browser/v1/config` first and send the `csrftoken` cookie's value in `X-CSRFToken` |
| `400` with `too_many_login_attempts` | 5 wrong passwords for that email, or a login in the first 10 seconds after sign-up | Wait 5 minutes (or 10 seconds after sign-up) |
| Saving a piece says `attributes: ... is a required property` or similar | The attributes break the category's or design's schema | Fix the attributes as the message says, or change the schema in the catalog |
| Saving a category says `Not a valid JSON Schema` | A mistake in `attribute_schema` | Check the schema; the message says which part is wrong |
| No sign-up code arrives | Emails are not sent from your machine | Look in the `runserver` terminal |
| A build script says `You have uncommitted changes` | `git status` shows changed files | Commit them, or ask the lead before discarding anything |
| A build script says a file `is not the version from the last build` | That file was edited by hand | Send that file to the lead engineer; the next script will keep your change |
| Uploading a photo says `Upload a JPEG, PNG or WebP image.` | The file is another format (HEIC from an iPhone, GIF, PDF) or not an image | Export it as JPEG first (on an iPhone: Settings, Camera, Formats, Most Compatible) |
| Uploading a photo says it is too large | Over 20 MB, or more pixels than Pillow's safety limit | Resize it before uploading; 3000 pixels on the long side is plenty |
| `To use another picture, delete this photo and add a new one.` | A saved photo's file is never replaced, so the audit log always matches the file | Tick **Delete** on that row and add the new picture in an empty row |
| A photo's preview is a broken image | The file is missing from `media/` (another machine's database, or a deleted folder) | Delete that photo row and upload it again |
| Publishing a listing says it is not ready | Something on the piece is missing; the message lists every reason | Add a listing photo on the piece page, or put the piece in the vault, then publish again |
| `This piece already has an open listing.` | The piece has a draft or live listing | Open that listing and change its price, or withdraw it first |
| `Consigned pieces are listed by their owners` | Staff can list house stock only for now | Choose a house stock piece |
| A listing is not in `GET /api/v1/listings/` | It is a draft or withdrawn, or its piece was found not authentic | Publish it (admin action); check the piece's verification status |
| `ImproperlyConfigured: Set DJANGO_FIELD_ENCRYPTION_KEYS` (Render deploy) | The live site has no encryption key, or has the local-only one | Add `DJANGO_FIELD_ENCRYPTION_KEYS` in Render (see Deploying), then deploy again |
| `core.E001 ... is not a valid Fernet key` | The key was mistyped, or made some other way | Make one with the Fernet command in "Encrypted columns" |
| `EncryptionKeyError: A stored value cannot be decrypted` | The key that wrote the data is no longer in `DJANGO_FIELD_ENCRYPTION_KEYS` | Put the old key back (after the new one), run `reencrypt_fields`, then remove it |
| `FieldError: 'line1' is encrypted, so it cannot be filtered` | A query filters on an encrypted column | Filter on a plain column (city, country) instead |
| `payments.W001 STRIPE_SECRET_KEY is not set` | No Stripe key in `.env` (a warning; everything else works) | Add the sandbox keys (Try it, "Check the Stripe sandbox keys") |
| `check_payments` says "This is a live key" | `.env` has `sk_live_...` | Use the sandbox key, `sk_test_...` |
| `check_payments` says "The payment service could not complete this" | Wrong or rolled key, or no internet | Copy the secret key again from the sandbox's API keys page |
| `ImproperlyConfigured: Set STRIPE_SECRET_KEY ... and STRIPE_WEBHOOK_SECRET` (Render deploy) | A Stripe value is missing in Render | Add both (see Deploying), then deploy again |
| Stripe shows webhook deliveries failing with 400 | `STRIPE_WEBHOOK_SECRET` is not this endpoint's secret | Reveal the endpoint's secret in Stripe and update it in Render |
| `POST /api/v1/orders/` says `idempotency_key_missing` | No `Idempotency-Key` header | Send a new key (any unique text, such as a UUID) per purchase; reuse it only to retry the same request |
| `listing_unavailable` when buying | The listing is sold or withdrawn, or another buyer's 15-minute hold is running (`reserved_until` in browse) | Wait for the hold to end, or choose another piece |
| `cannot_buy_own_listing` | You are logged in as the seller (the house account) | Log in as a buyer account |
| An order stays `pending_payment` after paying in the sandbox | On your machine Stripe cannot send the webhook | Run `python manage.py reconcile_payments` |
| `listing_held` when withdrawing a listing | A buyer's checkout holds it | Wait up to 15 minutes, or run `python manage.py expire_orders` after the hold ends |
| Stripe's webhook deliveries show 500 | Acting on the event failed; the error is in the admin (Stripe events, `last_error`) | Fix the cause; Stripe retries, and the next delivery is acted on |
| `ModuleNotFoundError: No module named 'apps.core'` (or `apps.orders`, ...) | Code or a branch from before build T1 uses the old paths | Use the new path: `apps.platform.core`, `apps.shop.orders` (see Project structure). Old branches: merge `dev` into them first |
| Old folders such as `apps/core/` still show in VS Code after T1 | Python's `__pycache__` folders stayed behind | The T1 script removes them; if one is left, delete it (it holds no code) |
| A test fails only on your machine | Usually an old database or old packages | Re-install packages (step 4); tests never use `db.sqlite3`, so check for local changes with `git status` |

## Project structure

```
apps/                 our code: apps grouped by area; each folder inside a group is one Django app
  platform/           shared building blocks every app uses
    core/             IDs, BaseModel, Money, policy (time limits), errors, state machines,
                      encrypted fields, request IDs, logs, the API basics
      api/            errors.py (the one error format), pagination.py (the one way lists are paged)
    audit/            the audit log: one append-only row for every staff change
    idempotency/      Idempotency-Key handling: a create request sent twice runs once
  users/              people
    accounts/         the User model, sign-up and login (django-allauth), roles and permissions
    addresses/        delivery addresses, with the name, street and phone encrypted
  inventory/          what Samwab holds
    catalog/          brands, categories, designs, materials, capture protocols, comparable sales
      models/         one file per subject; import models from apps.inventory.catalog.models
    pieces/           one row per physical object: materials, photos, custody and verification
      photos.py       checks an uploaded photo and removes its hidden data before it is saved
      api/serializers.py  the public view of a piece (no serial codes, costs or owners)
  shop/               selling
    listings/         a piece for sale, its price history and the public browse API
    orders/           buying a piece, the 15-minute hold, and what happens when payments change
  money/              money
    payments/         the payment provider interface, Stripe, the webhook, payments and refunds
      providers/      base.py (the interface), stripe.py, fake.py (tests only)
  conftest.py         test setup shared by every app
configurations/       project wiring only
  settings/           base.py plus one file per environment
  urls.py             mounts each app's URLs under /api/v1/
templates/            email wording (allauth)
requirements/         base.txt, dev.txt, prod.txt
.github/workflows/    CI: lint, types, checks and tests on every pull request
```

Groups are only folders: each app keeps its short name (its label: `catalog`,
`orders`), which is what the database, migrations, permissions, admin addresses and
the audit log use, so moving an app between groups changes no data. A new app goes
in the group of its area, with `name = "apps.<group>.<app>"` in its `apps.py`; an app
used by several areas (payments, for instance) gets a group of its own.

A typical app (`apps/inventory/catalog/`) holds `models/` (or `models.py`), `enums.py`,
`exceptions.py`, `selectors.py`, `services.py`, `admin.py`, `api/` (views,
serializers, URLs), `migrations/` and `tests/`. What each layer does is in
[Where code goes](#where-code-goes). Files are added when an app needs them, so
not every app has every file.

Other files at the top of the repository:

| File | What it is |
|---|---|
| `manage.py` | Django's command line: `runserver`, `migrate`, `shell` and so on |
| `pyproject.toml` | Settings for Ruff, mypy, pytest and coverage |
| `.pre-commit-config.yaml` | The checks `pre-commit install` runs before each commit |
| `.env.example` | Every environment variable, with notes. Copy it to `.env` |
| `.editorconfig`, `.gitattributes` | Same indentation and line endings on every editor and computer |
| `templates/` | Our own templates; today the wording of allauth's emails |

## Apps

| App | What it owns |
|---|---|
| `accounts` | Users. People log in with their email; there is no username. Roles are Django groups, and each staff role's admin permissions are set from code. |
| `idempotency` | The `Idempotency-Key` header (`idempotency_keys`): a create request sent twice does its work once, and the retry gets the first answer. Views use it with `@idempotent`. |
| `audit` | The audit log (`audit_events`): who changed what, when and from where. Rows are only ever added. Other apps write to it from their services. |
| `catalog` | What can be sold: brands, categories, named designs (such as the Kelly 28) and materials; the capture protocols staff follow for each category or design; comparable sales for fair prices. Staff run it in the admin site; the API only reads it. |
| `orders` | Orders: a buyer buying one listed piece, paid in full; the 15-minute checkout hold, cancelling, and acting on what the payment provider confirms. |
| `payments` | The only app that talks to a payment provider. Stripe today, behind an interface so another provider can be added; Stripe webhooks are checked and stored here. |
| `addresses` | Delivery addresses a person keeps on their account. The name, street lines and phone are encrypted in the database. |
| `listings` | Listings: a piece offered for sale at an asking price, with its price history. Staff list house stock in the admin site; buyers browse live listings through the public API. |
| `pieces` | Pieces: one row per physical object Samwab holds, sells or has checked, with its materials, its photos, its custody status (where it is) and its verification status (is it authentic). Staff register pieces in the admin site. |
| `core` | Shared building blocks: IDs, `BaseModel`, `Money`, policy values, errors, paging, request IDs, the API description and the health endpoint. |

## Shared building blocks

Every app uses these, so learn them first. They live in `apps/platform/core`.

| Use | Import | Rule |
|---|---|---|
| A new model | `from apps.platform.core.models import BaseModel` | Every model extends `BaseModel`. It adds `id`, `created_at` and `updated_at`. |
| A new ID | `from apps.platform.core.ids import new_uuid` | IDs are UUID version 7: they sort by creation time and cannot be guessed. |
| An amount of money | `from apps.platform.core.money import Money` | Money is whole cents plus a currency. Never use floats or decimals. |
| A time limit or default rate | `from apps.platform.core import policy` | Read the value from `policy`. Never type the number into your own code. |
| A business rule that says no | `from apps.platform.core.exceptions import AppError` | Services raise `AppError` (or `NotFoundError`, `PermissionDeniedError`, `ConflictError`). They never build an HTTP response. |
| A secret column (an address, a phone number) | `from apps.platform.core.fields import EncryptedTextField` | Name its column `<name>_enc` (`db_column`). It is encrypted in the database and read back as plain text; it cannot be filtered or sorted on (only `__isnull`). Keys: `DJANGO_FIELD_ENCRYPTION_KEYS` (see "Encrypted columns"). |
| A status that changes | `from apps.platform.core.state_machine import StateMachine` | One table of allowed moves per status, next to its model (see `apps/inventory/pieces/state.py`). Services call `MACHINE.check(current, target)` before changing it; a refused move is 409 `illegal_transition`. |
| Rules for flexible JSON data | `from apps.platform.core.json_schema import attribute_errors, schema_errors` | Categories and designs describe piece attributes as JSON Schema (draft 2020-12). `schema_errors` checks a schema; `attribute_errors` lists every problem in some data, with where it is. |
| A list in another order | `from apps.platform.core.api.pagination import ordered_by` | `pagination_class = ordered_by("slug")`. The first field must be unique per row (see Lists and paging). |
| A change made by staff | `from apps.platform.audit import services as audit` | In the service, inside its transaction: `before = audit.snapshot(row)`, make the change, then `audit.record_saved(row, before=before, by=staff)`. For other actions, `audit.record("retired", row, by=staff, changes=...)`. |
| A create endpoint (order, bid, listing, refund, payout) | `from apps.platform.idempotency.api import idempotent` | Put `@idempotent` on the view's `post`. It requires the `Idempotency-Key` header, replays the first answer on a retry and adds the header to the API description. |
| A new staff screen | `apps/<app>/permissions.py` | Say which roles may `add`, `change`, `delete` or `view` each model, and connect it in the app's `ready()` (see `apps/inventory/catalog/apps.py`). |

```python
from apps.platform.core.money import Money

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
| `GET /api/v1/me/addresses/` | My delivery addresses, newest first | Yes |
| `POST /api/v1/me/addresses/` | Add a delivery address | Yes |
| `GET /api/v1/orders/` | My orders (`?role=seller` for my sales, `?status=`) | Yes |
| `POST /api/v1/orders/` | Buy a piece (needs an `Idempotency-Key` header) | Yes |
| `GET /api/v1/orders/{id}/` | One of my orders | Yes |
| `POST /api/v1/orders/{id}/cancel/` | Cancel before paying | Yes |
| `POST /webhooks/stripe/` | Stripe sends payment events here (checked by signature) | No (Stripe's signature) |
| `GET /api/v1/listings/` | Live listings, newest first. Filters: `q`, `brand`, `category`, `condition_min`, `price_max` | No |
| `GET /api/v1/listings/{id}/` | One live listing | No |
| `GET /api/v1/docs/` | A page to browse and try every endpoint | No |
| `GET /api/v1/schema/` | The OpenAPI file. Import it into Postman. Add `?format=json` for JSON | No |

Every endpoint needs a logged-in user unless the table says otherwise.

The docs and the OpenAPI file are built from the code, so they are always current.

### Users

- Everyone is a `User` (`apps/users/accounts/models.py`): buyers, owners, dealers and staff.
- People log in with their email address. Emails are stored in lowercase, so
  `Ada@Example.com` and `ada@example.com` are the same account.
- One account per person. Every account can buy, so there is no buyer role.
- Other roles are Django groups with these names: `owner`, `dealer`, `intake_staff`,
  `reviewer`, `catalog_editor`, `partner`, `support`, `finance`, `admin`
  (`apps/users/accounts/roles.py`). `owner` is added when Stripe enables her payouts,
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
- `attribute_schema` on a category or design must be a valid JSON Schema
  (draft 2020-12), because every piece in it is checked against it. For example, a
  category for bags could require a width:
  `{"type": "object", "properties": {"width_cm": {"type": "number", "minimum": 1}}, "required": ["width_cm"]}`.
- A category records the staff member who last changed it (`updated_by`). Every
  change becomes an audit event in build 07, and the `catalog_editor` role gets
  its permissions there too. Until then, only superusers can use these screens.

### Pieces

A piece is one physical object. Staff register pieces in the admin site
(`/admin/pieces/piece/`); there is no public piece endpoint yet (browse and
listings add it).

- **Where it came from.** `source` is `house_stock` (Samwab owns it: the owner must
  be a house account, a user with `is_house_account` ticked) or `consigned` (an
  owner sells it through Samwab: the owner must be a person, not a house account).
  Only house stock has an `acquisition_cost_minor`.
- **What it is.** Brand, category and, when known, the design (product model).
  The design must belong to that brand and category. A blank department is taken
  from the design, and a blank HS code from the category.
- **Attributes** (measurements, metal, hardware) are JSON, checked against the
  category's schema and the design's schema. Every problem is listed with where it
  is, such as `width_cm: 0 is less than the minimum of 1`.
- **Materials** are added in the list at the bottom of the piece page. A material
  that a piece uses can no longer be deleted.
- `serial_or_date_code` is for staff only and will never be shown to the public.
- Pieces are never deleted.
- **Photos** are added in the Photos list on the piece page (JPEG, PNG or WebP, up
  to 20 MB). Each one is checked and cleaned before it is saved: it is turned
  upright, its hidden data (where and when it was taken, the camera) is removed,
  and it is stored under a new name in `pieces/<piece id>/`. A saved photo's
  picture is never replaced: delete it and add a new one. Its kind and order can
  change. New photos go last. A piece with photos cannot be deleted.

Two statuses, shown in the admin but never edited there:

| Status | Values | Moves |
|---|---|---|
| `custody_status` (where it is) | `with_owner`, `in_transit`, `at_intake`, `in_vault`, `with_buyer` | `with_owner` → `in_transit` → `at_intake` → `in_vault` → `in_transit` → `with_buyer` |
| `verification_status` (is it authentic) | `unverified`, `verified`, `not_authentic` | `unverified` → `verified` or `not_authentic`, decided once |

The moves are in `apps/inventory/pieces/state.py`, and only `services.move_custody` and
`services.set_verification` change a status. They lock the row and read the status
from the database first, so two people acting at once cannot skip a step. Custody
events (build 16), the ownership ledger (build 17) and authentication checks
(build 28) will call them. Returns and moves between vaults add their moves when
their rules are settled.

### Addresses

A person's own delivery addresses. Login is required; each person sees only their own.

- `GET /api/v1/me/addresses/`: newest first, paged with `cursor`.
- `POST /api/v1/me/addresses/`: `recipient_name` (up to 160 characters), `line1`
  (200) and `city` are required, with `country` (two letters; `ng` becomes `NG`).
  Optional: `label` (such as Home, 40), `line2` (200), `region`, `postal_code`,
  `phone` (digits, spaces and `+ ( ) -`), `is_default`. Answers 201 with the address.
  An empty `line2` or `phone` comes back as `null`.
- The first address becomes the default. Sending `"is_default": true` makes the new
  one the default and the old one not; each person has at most one (the database
  enforces it).
- At most 20 addresses per account: the 21st is 422 `address_limit_reached`.
- Bad fields are 400 `validation_error` naming each field.

Changing and deleting addresses are not in the contract yet.

### Encrypted columns

The recipient's name, the street lines and the phone are stored encrypted
(columns ending `_enc`, decision D5); city, region, postal code and country stay
plain, because delivery and tax rules read them. In code they read as plain text.
They never appear in the audit log, and `str(address)` shows only the label and city.

- Encryption is Fernet from the `cryptography` package, with keys in
  `DJANGO_FIELD_ENCRYPTION_KEYS` (comma separated), separate from `SECRET_KEY`.
  The **first** key encrypts; **every** key decrypts.
- Make a key:
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- On your machine no key is needed: without one, a public local-only key is used.
  Production refuses to start without its own key, or with the local one.
- **Losing every key loses the addresses.** Keep the live key in a password manager
  as well as in Render.
- **To change keys:** put the new key first (`new,old`), deploy, run
  `python manage.py reencrypt_fields` (Render's Shell), then remove the old key.
- `manage.py check` reports a missing or malformed key as `core.E001`.
- Encrypted columns cannot be filtered, searched or sorted on; Django raises
  `FieldError`. Only `__isnull` works.

### Payments

All payment calls go through **one interface**, `apps/money/payments/providers/base.py`
(`PaymentProvider`): `create_payment`, `get_payment`, `cancel_payment` and
`read_webhook`. Orders never import Stripe. Another provider (Paystack, say) is one
new class beside `stripe.py` and a value of `DJANGO_PAYMENT_PROVIDER`.

- **Stripe** (`providers/stripe.py`, package `stripe` 17.1.0, Stripe API version
  `2026-11-18`): payments are PaymentIntents with automatic payment methods. The
  web app confirms them in the browser with Stripe Elements and the payment's
  `client_secret`. Every create sends our idempotency key, so a retry never
  charges twice. A Stripe failure becomes 502 `payment_provider_error`; Stripe's
  own message is logged with its request id, never shown.
- **Fake** (`providers/fake.py`): payments in memory. Tests use it
  (`DJANGO_PAYMENT_PROVIDER=fake` in the test settings), so tests never call Stripe.
- `python manage.py check_payments`: a $1.00 test payment, then cancelled. Refuses
  live keys.
- `manage.py check` warns `payments.W001` while a Stripe key is missing.

**Webhook** `POST /webhooks/stripe/` (no login, no CSRF token): the
`Stripe-Signature` header is checked against the raw body with
`STRIPE_WEBHOOK_SECRET` (Stripe's library; signatures older than 5 minutes are
refused). A good event is stored once in `stripe_events` by its id (`evt_...`), so
a repeated delivery changes nothing, and the answer is 200 `{"received": true}` at
once. A failed check is 400 `webhook_signature_invalid` and stores nothing.
Events are only stored for now; orders (build E5) act on them. Superusers can read
them in the admin site (Stripe events).

### Orders

A buyer buys one piece from one live listing, paid in full (house stock).
**An order's status changes only on our server, from what Stripe confirms, never
from what the browser says.**

- `POST /api/v1/orders/` with an `Idempotency-Key` header and `listing_id`,
  `payment_option` (`pay_in_full`; `reserve` is 422 `reservation_not_available`
  until reservations exist), `delivery_choice` (`keep_in_vault`, or
  `buyer_courier` with `shipping_address_id`, one of your addresses; it is copied
  onto the order, encrypted), optional `acquisition_source` and `known_before`.
  Answers 201 with `order` and `payment` (`client_secret` for Stripe Elements in
  the browser). The price comes from the listing; anything else sent is ignored.
- `GET /api/v1/orders/` (yours as buyer; `?role=seller` for your sales;
  `?status=paid`), `GET /api/v1/orders/{id}/` (404 if you are neither buyer nor
  seller), `POST /api/v1/orders/{id}/cancel/` (buyer only, while waiting).
- The order shows `item`, `tax` (0 until Stripe Tax), `total`, `amount_due`,
  `pay_by` (the hold) and a `timeline`. The seller sees `seller_share` and
  `commission` instead of `tax` and `amount_due`.

**What goes wrong, and what happens** (each has a test):

| Case | What happens |
|---|---|
| The same request twice (double click, retry) | Same `Idempotency-Key`: the first answer again; one order, one payment |
| Two buyers, same piece, same moment | The listing row is locked; one gets the order, the other 409 `listing_unavailable` (tested with two real connections on PostgreSQL) |
| Card declined | The order stays `pending_payment`; the reason is kept on the payment (admin); the buyer tries another card on the same payment |
| Stripe unreachable when ordering | 502 `payment_provider_error`; nothing is saved |
| Paying twice | One order has one Stripe payment, made with the order's own key; a paid payment cannot be paid again; a listing has one waiting order at most |
| Webhook missed or late | `python manage.py reconcile_payments` asks Stripe about every waiting order |
| The same event twice, late, or out of order | Every event makes us ask Stripe for the payment's current state, and orders only move forward: a late failure never undoes a payment |
| The amount paid is not the order total | Not accepted: logged as an error, the payment shows `amount_mismatch` |
| The buyer walks away | After 15 minutes (`CHECKOUT_HOLD` in `apps/platform/core/policy.py`) the order is cancelled (`hold_expired`) and its payment cancelled: when the next buyer comes, or by `python manage.py expire_orders` |
| Money arrives after the order closed (or after the listing was withdrawn) | Refunded in full at once (`missed_deadline`); the order becomes `refunded`; finance sees a warning in the logs |
| Cancelling just as the payment succeeds | The order ends `paid` and the cancel answers 409 `order_already_paid` |

Statuses (`apps/shop/orders/state.py`): `pending_payment` → `paid` or `cancelled`;
`cancelled` → `refunded`. A paid order marks its listing `sold`. While an order
waits, the listing shows `reserved_until` (the hold) in browse, and staff cannot
withdraw it (409 `listing_held`). Orders, payments and refunds are read-only in
the admin site (superusers). Not yet: the piece's owner does not change (the
ownership ledger comes later), and delivery, intake and returns are later builds.

**Webhook processing:** every Stripe payment event makes us read the payment from
Stripe and act on it inside the webhook request. If acting fails, the event keeps
the error (`last_error`, `attempts`) and the webhook answers 500, so Stripe sends
it again. `client_secret` values are removed before events are stored.

### Listings

A listing offers one piece for sale at an asking price. This build lists
**house stock** only; consigned listings (an owner selling through Samwab) come
with the owner onboarding builds.

**Browse (public, no login):**

- `GET /api/v1/listings/`: live listings, newest first, paged with `cursor`.
  Filters, all optional:
  - `q`: words; every word must appear in the title, brand or design (`?q=kelly gold`).
  - `brand` and `category`: slugs. A category also shows the categories under it,
    so `?category=jewellery` includes bracelets.
  - `condition_min`: the lowest condition to show (`new`, `excellent`,
    `very_good`, `good`, `fair`). Pieces not yet graded are left out when it is set.
  - `price_max`: the highest asking price, in cents.

  An unknown slug gives an empty list; a bad value (`?condition_min=mint`,
  `?price_max=-1`) gives 400 `validation_error` naming the field.
- `GET /api/v1/listings/{id}/`: one live listing. Drafts, withdrawn listings and
  unknown ids are 404.

Each listing has `id`, `piece` (the public view: title, description, brand,
category, design, size, year, attributes, condition, statuses and `media`, the
photos in order with a full `url` and `alt` text), `fulfilment`, `ask`
(`{"amount": 1250000, "currency": "USD"}`, in cents), `status`, `reservable` and
`reserved_until` (always `false` and `null` until reservations exist),
`verification_label` (`verified`, `verification_pending`, or
`buyer_authenticates` for jewellery the buyer checks), `published_at` and
`expires_at`. Never returned: serial or date codes, the floor price, costs and the
owner.

A piece found not authentic disappears from browse at once, even if its listing
is still live.

**In the admin site** (`/admin/listings/listing/`, superusers only for now):

- **Draft**: pick the piece, choose where it ships from (from the vault, or from
  the owner's home), type the price in cents. The seller is filled in: the piece's
  owner, Samwab's house account for house stock. A piece has at most one open
  listing (draft or live) at a time; the database enforces it.
- **Publish** (action on the list page): refused, with every reason listed, until
  the piece has at least one listing photo, is in the vault (for "from the vault")
  and has not been found not authentic.
- **Change the price** on an open listing's page. Every change is kept in its
  **price history** (`listing_price_changes`) with who made it.
- **Withdraw** (action): takes it off sale for good. To sell it again, draft a new
  listing. The piece and where it ships from cannot change after drafting, for the
  same reason.
- Listings are never deleted. Every draft, publish, price change and withdrawal is
  an audit event.

Status moves (`apps/shop/listings/state.py`): `draft` → `live` or `withdrawn`;
`live` → `withdrawn`. Orders (build E5) will add `live` → `sold`.

### Staff roles and the audit log

**Roles.** A staff member needs **Staff status** (to open the admin site) and one
or more role groups (to see anything there). What each role may do is written in
code, in `apps/<app>/permissions.py`, and set again after every `migrate`, so a
role's permissions are always what the reviewed code says:

| Role | Admin screens |
|---|---|
| `catalog_editor` | The whole catalog: brands, categories and designs (add, change, retire; never delete), materials, capture protocols and shots, comparable sales (add, change, delete) |
| `intake_staff` | Pieces and their materials (add and change; pieces are never deleted), and the catalog read only, to pick a brand, category, design and materials |
| the other roles | Nothing yet: their screens come with their builds |

A superuser can do everything and is the only one who reads the audit log for now.
Which other roles get which screens is still being agreed with the client.

**Audit log** (`audit_events`, admin: `/admin/audit/auditevent/`). One row for every
change staff make, written in the same transaction as the change, so there is never
a change without its row or a row without its change.

| Column | What it holds |
|---|---|
| `actor` | Who made the change (empty for a change the system makes itself) |
| `action` | `<app>.<model>.<verb>`, such as `catalog.brand.retired` or `pieces.piece.custody_moved` |
| `object_type`, `object_id` | The row it happened to, such as `pieces.piece` and the piece's id |
| `changes` | `{"field": {"from": old, "to": new}}`: only what changed. A new row has only `to`, a deleted row only `from` |
| `ip_address`, `request_id` | From the request, when there was one. The request ID matches the `X-Request-ID` header and the logs |
| `occurred_at` | When, in UTC |

What is recorded today:

- **Catalog:** every add, change, retire, bring back and delete, protocol steps
  (`created`, `activated`, `retired`, `drafted`, `deleted`) and each shot added,
  changed or removed.
- **Pieces:** `created`, `changed`, `custody_moved`, `verification_set`, and
  `materials_changed` (the materials before and after, by name).
- **Accounts:** a person added or changed in the admin, including roles (groups) and
  permissions given or taken. Passwords and login times are never recorded.
- Saving without changing anything records nothing. A refused change records nothing.
- Encrypted columns (names ending in `_enc`) never go into `changes`.

Rows are never changed or deleted: Django refuses (`AuditEventIsFinalError`), and on
PostgreSQL a database trigger refuses too, even for hand-written SQL. A person with
audit history cannot be deleted (people are anonymised instead). The IP address is
the connection's own address; behind the hosting provider's proxy that is decided
when the app is deployed.

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
| 409 | `illegal_transition` | A status change that is not allowed from the current status |
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
`pagination_class = ordered_by("slug")` (`apps/platform/core/api/pagination.py`). The cursor
stands on the first field only, so that field must be unique per row. When the
display order is not unique, a selector adds a unique `position` value to sort on
(see `apps/inventory/catalog/selectors.py`); otherwise the previous page can skip rows.

### Safe retries: the Idempotency-Key header

Phones lose signal and people double-click. So every request that creates an
order, bid, listing, refund or payout carries an `Idempotency-Key` header: a new
random value (a UUID is best) for each action the person takes. If the app is not
sure the request arrived, it sends **the same request with the same key** again.

| What happens | Answer |
|---|---|
| First request with a key | Runs normally |
| Same key, same body, after the first finished | The first answer again (same status and body), with `Idempotent-Replayed: true`. Nothing runs twice |
| Same key while the first is still running | `409 idempotency_key_in_progress`. Wait and retry |
| Same key, different body or address | `422 idempotency_key_reused`. Make a new key |
| No key, or a bad one | `400 idempotency_key_missing` or `idempotency_key_invalid` (1 to 255 letters, digits or symbols, no spaces; `"quoted"` is fine) |
| The first request failed (an error, or a `5xx`) | The key is freed, because nothing was saved: send it again |

Keys belong to the logged-in person and last 24 hours; after that the same key
counts as new. The rules follow the IETF draft *The Idempotency-Key HTTP Header
Field* and Stripe's practice.

For developers: put `@idempotent` (`apps/platform/idempotency/api.py`) on the view's
`post`. The view's work and the stored answer are saved in one transaction, so a
crash never leaves an answer without its work, or work without its answer. No
endpoint uses it yet: listings, bids and orders will.

### Request IDs

Every response has an `X-Request-ID` header, and errors repeat it as `request_id`.
Every log line written while handling the request carries the same ID. When
something goes wrong, ask for that ID and search the logs for it. A caller may
send its own `X-Request-ID` (8 to 64 letters, digits, `.`, `_` or `-`).

Logs are plain text on your machine and one JSON object per line on servers.

## Deploying to Render and Neon

The live API runs on **Render** (web service `samwab-luxury-backend`, region
Virginia, US East) and its database on **Neon** (PostgreSQL 18, AWS US East,
N. Virginia). Render deploys the `main` branch by itself, but only after both CI
jobs pass on it ("After CI Checks Pass"). Your own machine still uses SQLite.

To release: get CI green on `dev`, then merge `dev` into `main` and push (see
Branches). Render builds and starts the new version a few minutes later.

**Render settings** (Dashboard, the service, Settings):

| Setting | Value |
|---|---|
| Branch | `main` |
| Language | Python 3 (the version comes from `.python-version`: the latest 3.13) |
| Build command | `pip install -r requirements/prod.txt && python manage.py collectstatic --no-input && DATABASE_URL="$DIRECT_DATABASE_URL" python manage.py migrate --no-input` |
| Start command | `gunicorn configurations.wsgi:application` |
| Health check path | `/api/v1/health/` |
| Pre-deploy command | Empty (the free plan has none; migrations run in the build command) |
| Auto-deploy | After CI Checks Pass |

**Render environment variables:**

| Variable | Value |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `configurations.settings.production` |
| `DJANGO_SECRET_KEY` | Press **Generate** |
| `STRIPE_SECRET_KEY` | The sandbox's secret key, `sk_test_...` (Stripe: Developers → API keys) |
| `STRIPE_WEBHOOK_SECRET` | The `whsec_...` signing secret of the webhook below |
| `DJANGO_FIELD_ENCRYPTION_KEYS` | A key from `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`, run on your machine. Also keep it in a password manager: without it the addresses cannot be read. Never use Render's **Generate** here (it is not a Fernet key) |
| `DATABASE_URL` | Neon's **pooled** connection string (the host contains `-pooler`): the running app uses it |
| `DIRECT_DATABASE_URL` | Neon's **direct** connection string (no `-pooler`): only migrations use it |
| `WEB_CONCURRENCY` | `2` (Gunicorn's number of workers) |
| `DJANGO_EMAIL_TO_LOGS` | `true` until an email service is chosen: emails, such as sign-up codes, are written to Render's **Logs** instead of sent. Remove it and set the `DJANGO_EMAIL_*` variables when the email service exists |
| `DJANGO_FRONTEND_URL` | The web app's address, when it has one |

**Stripe webhook** (once, in the Stripe sandbox): **Developers** → **Webhooks** →
**Create an event destination** → **Your account** → payload **Snapshot** → events
`payment_intent.succeeded`, `payment_intent.payment_failed`,
`payment_intent.canceled` → **Webhook endpoint** → URL
`https://<your Render address>/webhooks/stripe/`. Then **Reveal** the signing
secret (`whsec_...`) and put it in Render as `STRIPE_WEBHOOK_SECRET`. The live site
refuses to start without both Stripe values.

Render sets `RENDER_EXTERNAL_HOSTNAME` itself (for example
`samwab-luxury-backnd.onrender.com`); the app accepts that address and trusts it
for forms. Add a custom domain with `DJANGO_ALLOWED_HOSTS` and
`DJANGO_CSRF_TRUSTED_ORIGINS`.

**After the first deploy:**

- Check https://samwab-luxury-backnd.onrender.com/api/v1/health/ answers `{"status": "ok"}`.
- Make your admin login: Render's **Shell** tab is not on the free plan, so run it
  from your machine once, against Neon's **direct** string (never commit it):
  ```bash
  DJANGO_SETTINGS_MODULE=configurations.settings.production \
  DJANGO_SECRET_KEY=any-long-text DATABASE_URL='<Neon direct connection string>' \
  python manage.py createsuperuser
  ```
  (Production settings need the PostgreSQL driver, which `requirements/dev.txt` installs.)
- Then open `/admin/` on the Render address.

CI rehearses all of this on every push: the PostgreSQL job runs Django's
deployment checklist (`check --deploy`), `collectstatic`, `migrate`, starts
Gunicorn with the production settings and loads the health check, the admin
login page and the admin's CSS.

Free Render instances sleep after a while without visitors; the first request
afterwards takes longer.

**Photos on the live site: not yet.** Render's disk is wiped on every deploy and
the live site does not serve the `media/` folder, so photos uploaded there now
would be lost. Upload photos on your machine only until a cloud bucket (S3 or
Cloudflare R2) is chosen and set up (a later build).

## Settings and environment variables

Pick the settings file with `DJANGO_SETTINGS_MODULE`. `manage.py` uses
`configurations.settings.local`. Tests use `configurations.settings.test`.
Servers use `configurations.settings.production` (or `staging`).

| Variable | Needed in | Meaning |
|---|---|---|
| `DJANGO_SECRET_KEY` | everywhere | Long random text used for signing |
| `DJANGO_PAYMENT_PROVIDER` | optional | `stripe` (default) or `fake` (tests). The live site always uses `stripe` |
| `STRIPE_SECRET_KEY` | staging, production; locally for `check_payments` | Stripe's secret key: `sk_test_...` in the sandbox |
| `STRIPE_WEBHOOK_SECRET` | staging, production | The webhook's signing secret, `whsec_...` |
| `DJANGO_FIELD_ENCRYPTION_KEYS` | staging, production (optional locally) | Keys for encrypted columns, comma separated; the first encrypts. See "Encrypted columns" |
| `DATABASE_URL` | staging, production; optional in tests | The database. Production: Neon's pooled string. Tests: set it to run on PostgreSQL |
| `DIRECT_DATABASE_URL` | Render's build command | Neon's direct string, used only by `migrate` |
| `DJANGO_ALLOWED_HOSTS` | optional | Extra host names the API answers to, comma separated (Render's own is added automatically) |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | optional | Extra addresses allowed to send forms, comma separated (Render's own is added automatically) |
| `DJANGO_EMAIL_TO_LOGS` | production, until an email service exists | `true` writes emails to the logs instead of sending them |
| `DJANGO_FRONTEND_URL` | staging, production | The web app's address, used for links in emails. Default `http://localhost:3000` |
| `DJANGO_DEFAULT_FROM_EMAIL` | staging, production | Sender of every email, such as `Samwab <no-reply@samwab.com>` |
| `DJANGO_EMAIL_HOST`, `DJANGO_EMAIL_PORT`, `DJANGO_EMAIL_USER`, `DJANGO_EMAIL_PASSWORD`, `DJANGO_EMAIL_USE_TLS` | staging, production | The email provider's SMTP details. Port defaults to 587 and TLS to on |
| `RENDER_EXTERNAL_HOSTNAME`, `PORT`, `WEB_CONCURRENCY` | Render | Set by Render (the last by you): the public host name, the port Gunicorn listens on, the number of workers |

Secrets never go into Git. `.env` is ignored, and `.env.example` lists every variable.
On your own machine, only `DJANGO_SECRET_KEY` is needed.

## Build status

The README is updated in every build.


Last build: T1, apps grouped by area.

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
| 13a | 21 Nov 2026 | Full README: setup from scratch, run, try it, everyday commands, how we write code and TDD, checks, Git and build scripts, troubleshooting |
| 14 | 21 Nov 2026 | Pieces: `pieces` and `piece_materials`; custody and verification state machines; attribute checks against JSON Schema; piece screens in the admin site; `StateMachine` and JSON Schema helpers in core |
| 07 | 21 Nov 2026 | Audit and staff roles: `audit_events` (append-only, with a PostgreSQL trigger) written by every catalog, piece and account change staff make; admin permissions for `catalog_editor` and `intake_staff`, set from code after every `migrate`; the caller's IP address for the audit log |
| 08 | 21 Nov 2026 | Idempotency: `idempotency_keys` and the `@idempotent` decorator (`Idempotency-Key` required, first answer replayed for 24 hours, 400/409/422 as in the IETF draft), a command to delete expired keys |
| 08a | 22 Nov 2026 | Tidy-up: code on GitHub (`dev` default, `main` for deploys); CI also runs every test on PostgreSQL 18; tests use `DATABASE_URL` when set; build scripts end with `git push` |
| 01 | 22 Nov 2026 | Production deploy: Neon PostgreSQL from `DATABASE_URL` (Neon's Django settings), Render's address allowed automatically, WhiteNoise for static files, `.python-version`, emails to the logs until an email service exists; CI rehearses Render's build and start |
| 01a | 22 Nov 2026 | CI fix: the deploy rehearsal tells production settings that the throwaway CI database is unencrypted (`sslmode=disable`, CI only) |
| E1 | 23 Nov 2026 | Photos for pieces: the `media` table; uploads in the piece's admin page, checked and cleaned with Pillow (upright, hidden location data removed, new file name, JPEG/PNG/WebP only, 20 MB limit); audited; `intake_staff` may manage photos; `pieces.models` split into one file per subject |
| E2 | 23 Nov 2026 | Listings: `listings` and `listing_price_changes` for house stock; draft, publish (refused until the piece has a listing photo and is in the vault), change the price and withdraw in the admin site, all audited; public `GET /api/v1/listings/` (filters `q`, `brand`, `category`, `condition_min`, `price_max`) and `GET /api/v1/listings/{id}/` |
| E3 | 23 Nov 2026 | Addresses: `addresses` with the name, street lines and phone encrypted (`EncryptedTextField`, Fernet keys in `DJANGO_FIELD_ENCRYPTION_KEYS`, start-up check `core.E001`, `reencrypt_fields` command); `GET`/`POST /api/v1/me/addresses/` with one default per person and at most 20 |
| E4 | 23 Nov 2026 | Payments: the payment provider interface with Stripe (`stripe` 17.1.0) and an in-memory fake for tests; `POST /webhooks/stripe/` (signature checked, `stripe_events` stored once by id); `check_payments` command; the live site requires the Stripe keys |
| E5 | 23 Nov 2026 | Orders paid in full: `orders`, `payments` and `refunds` tables; `POST`/`GET /api/v1/orders/`, `/{id}/`, `/{id}/cancel/`; the 15-minute checkout hold; webhook events acted on (state read from Stripe); late money refunded; `expire_orders` and `reconcile_payments`; browse shows the hold; Stripe's own logging quieter; allauth's admin section renamed |
| T1 | 23 Nov 2026 | Tidy-up: apps grouped into folders by area (`platform/`, `users/`, `inventory/`, `shop/`, `money/`); app labels, tables, migrations, URLs and the API description unchanged |

Builds run in the order the roadmap sets, so numbers can skip: builds 12 to 14 came
before 06 to 11 to start on what buyers see, then 07, 08, the 08a tidy-up and build 01 (production deploy).
E builds (E1, E2, ...) are the e-commerce builds for the client demo.
