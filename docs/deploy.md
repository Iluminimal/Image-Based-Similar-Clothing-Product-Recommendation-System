# Deploying Angel

One server (a VPS, any provider) running Docker Compose: **Caddy** (automatic HTTPS) -> **web** (Next.js) -> **api** (FastAPI)
-> **Postgres + pgvector**, **Redis**. Only Caddy listens on the internet (80/443); everything else is on the compose network.
The images build for `linux/amd64` and `linux/arm64`. Files: `infra/docker-compose.prod.yml`, `infra/Caddyfile`,
`apps/api/Dockerfile`, `apps/web/Dockerfile`, `.env.prod.example`. (`infra/docker-compose.dev.yml` is for development only.)

## Before you start

Read [`production-checklist.md`](production-checklist.md) first: it lists open problems to fix before launch, and what only
you can provide (accounts, legal text, your own products).

* A server with Docker and the Compose plugin, **4 GB RAM or more** (the model needs about 2 GB; add swap on a 4 GB machine) and
  **~15 GB disk** (images, the catalogue's thumbnails are 1.3 GB, the model cache ~1 GB).
* A domain whose A/AAAA record points at the server, ports 80 and 443 open (Caddy gets and renews the certificate itself).
* Accounts you need to fill in `.env.prod`: **QPay** merchant (`QPAY_*`; the sandbox is refused in production), **Twilio** (SMS codes),
  an **SMTP** provider (order and code emails), a **Google OAuth client** (redirect URI `https://<domain>/api/v1/auth/google/callback`).
  The API refuses to start with `APP_ENV=prod` if any of the development stand-ins (`PAYMENTS_MODE=offline`, `OAUTH_MODE=fake`,
  `SMS_MODE=console`, `MAIL_MODE=console`, `EMBEDDER=fake`, `LOCALIZER=fake`, `OTP_DEV_CODE`) is set (`core/config.py`).
* The code on the server (`git clone`). **Everything the build needs must be committed**, including `apps/web/messages/` (the translations).

## First deploy

```bash
cp .env.prod.example .env.prod      # fill in every CHANGE_ME: SITE_ADDRESS, SITE_URL, secrets, QPay, Twilio, SMTP, Google
openssl rand -hex 24                # POSTGRES_PASSWORD (it goes into a URL: no special characters)
openssl rand -base64 48             # JWT_SECRET
make deploy-check                   # names every empty/CHANGE_ME/forbidden value (never prints a value)

docker compose -f infra/docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -f infra/docker-compose.prod.yml --env-file .env.prod ps
docker compose -f infra/docker-compose.prod.yml --env-file .env.prod logs -f api
```

Order: Postgres and Redis -> `migrate` (`alembic upgrade head`, runs once) -> `api` (loads the model; `/readyz` is red until it is
loaded, **the first start downloads ~1 GB** into the `hf-cache` volume and can take minutes) -> `web` -> `caddy`. Open
`https://<domain>/`. The API's own probes are `/healthz` (alive) and `/readyz` (database, Redis, model); they are not published, check
them inside the container: `docker compose ... exec api python -c "import urllib.request as u; print(u.urlopen('http://127.0.0.1:8000/readyz').read())"`.

`SITE_URL`, `NEXT_PUBLIC_*` and the API's address are **baked into the web bundle at build time**: after changing `SITE_URL` run the
`up -d --build` again. The same goes for `SHOP_TIMEZONE` (default `Asia/Ulaanbaatar`): it sets where a day begins in the
dashboard, the CSV reports and the warehouse board, and which date the web calls today.

## The catalogue and the first admin

A new database is empty. Two ways to fill it:

1. **Move this machine's clean database** (fast, recommended). On the development machine:
   ```bash
   docker exec angel-postgres-1 pg_dump -U angel -d angel -Fc > angel.dump
   tar czf media.tgz -C data/media .
   ```
   On the server (after the first `up`, so the schema exists; the dump replaces it):
   ```bash
   docker compose -f infra/docker-compose.prod.yml --env-file .env.prod stop api
   docker compose -f infra/docker-compose.prod.yml --env-file .env.prod exec -T postgres \
     sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' < angel.dump
   docker run --rm -v angel-prod_media:/media -v "$PWD:/in:ro" alpine tar xzf /in/media.tgz -C /media
   docker compose -f infra/docker-compose.prod.yml --env-file .env.prod start api
   ```
   Run `make clean-test-data KEEP=<your email>` on the development machine first so that no test accounts, orders or products travel
   (it is a dry run until you add `ARGS=--yes`).
2. **Ingest the dataset on the server** (slow on a CPU): copy the Kaggle `styles.csv` and `images/` to the server, then
   `docker compose ... run --rm -v /path/to/fashion:/dataset:ro -e DATASET_DIR=/dataset api python scripts/ingest.py`.

The first administrator (the password is read from the environment, not the command line):

```bash
docker compose -f infra/docker-compose.prod.yml --env-file .env.prod run --rm \
  -e ADMIN_PASSWORD='<10+ characters>' api python -m angel.cli.admin create-admin --email you@example.com
```

Warehouse staff: `create-warehouse` with the same arguments. Then sign in at `/login` and use `/admin`.

In production every member of staff **must** set up two-factor sign-in before the back office opens (an authenticator app on
their phone). Have them do it straight after the account is created, and keep their recovery codes safe. Keep `JWT_SECRET`
stable: the two-factor secrets are encrypted with it, so changing it means `python -m angel.cli.admin reset-2fa --email ...`
for each of them.

## QPay

Set `QPAY_CALLBACK_BASE_URL` (the compose file sets it to `SITE_URL`): QPay calls `https://<domain>/api/v1/webhooks/qpay` after a
payment, so the site must be reachable from the internet. If a notification is lost the shopper can press "Check payment" on the
order. Verify the credentials with `docker compose ... run --rm api python scripts/qpay_smoke.py` (it creates and cancels a 100 MNT invoice).

## Backup and restore

```bash
make backup DIR=/var/backups/angel          # pg_dump (custom format) + the media volume; keeps the last 14 of each (KEEP=n)
# cron:  0 3 * * *  cd /opt/angel && scripts/backup.sh /var/backups/angel
```

To restore, **stop the API first**, from the folder that holds the backup:

```bash
dc() { docker compose -f /opt/angel/infra/docker-compose.prod.yml --env-file /opt/angel/.env.prod "$@"; }
dc stop api
dc exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' < db-<stamp>.dump
docker run --rm -v angel-prod_media:/media -v "$PWD:/in:ro" alpine tar xzf /in/media-<stamp>.tgz -C /media
dc start api
```

The restore re-creates the database's `vector` type. An API left running keeps the old one in its connections, so a photo
search fails with a 500 (`cache lookup failed for type ...`) **while `/readyz` stays green**. Stopping it also means
nothing is written while the data is being replaced. Copy the backups off the server. Redis holds only cache and
rate-limit counters (nothing to back up).

## Email delivery

Notification emails wait in the database and are retried for about 35 hours (`docs/accounts.md`, "The email outbox"), so a short
SMTP outage loses nothing. **Watch for `email_gave_up` in the logs**, and after fixing the provider:

```bash
docker compose -f infra/docker-compose.prod.yml --env-file .env.prod exec api python -m angel.cli.outbox status
docker compose -f infra/docker-compose.prod.yml --env-file .env.prod exec api python -m angel.cli.outbox retry
```

Old personal data is removed hourly by the API itself; the periods are the `*_RETENTION_*` settings (names and defaults in
`.env.example`; add a line to `.env.prod` to change one). Confirm them, and how long order records must be kept, against current
law before launch. Database backups keep what was deleted until they rotate out.

## Updating and rolling back

```bash
git pull
make deploy-check
TAG=$(git rev-parse --short HEAD) docker compose -f infra/docker-compose.prod.yml --env-file .env.prod up -d --build
```

The `migrate` service runs the new migrations before `api` restarts. To roll back the code, check out the previous commit and run
the same command with its tag (images are tagged `angel-api:<TAG>`, `angel-web:<TAG>`; the previous ones stay on the machine). Migrations
are not rolled back automatically: take a `make backup` first when a release has a migration.

## Operating notes

* **Logs**: structured JSON on stdout (`docker compose ... logs -f api`); CSP violations are logged as `csp_violation`. If a policy
  problem blocks a page in production, `CSP_MODE=report-only` (on the `web` service) turns the policy into reports while you fix it.
* **Security**: only Caddy publishes ports; Postgres and Redis are not reachable from outside. Cookies are `Secure`, the API trusts
  `X-Forwarded-For` only because it sits behind Caddy and the web server (`TRUST_PROXY_HEADERS=true` is set by the compose file). Keep
  `.env.prod` readable by you only (`chmod 600`) and out of git.
* **One API process**: the model is loaded once per process and inference runs in a thread pool; do not add `--workers`. To scale,
  run more servers behind a load balancer.
* **Resources**: `docker stats`. The `api` container is the heavy one (model in memory).
* **Smoke test locally** before a real deploy: set `SITE_ADDRESS=localhost`, `SITE_URL=https://localhost` and dummy non-sandbox values in a
  throw-away `.env.prod` (use host names ending in `.invalid` for QPay and SMTP, so nothing leaves the machine),
  `up -d --build`, then `curl -k https://localhost/`. Caddy listens on ports 80 and 443 on every network interface while
  it runs. Clean up with `down -v`, which **deletes every volume, the database included: never run it on the real
  server.** (This is how the files were checked.)
