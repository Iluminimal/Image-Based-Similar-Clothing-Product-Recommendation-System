# Production checklist

What has to be true before the shop takes a real order. `docs/deploy.md` says **how** to deploy; this says what is still
missing.

## 1. The code

The audit of November 2026 found eleven problems. Ten were real and are **fixed**, each with a test that failed before the
fix:

* an upload that is not a picture could make the server install a package from the internet while running (this had also
  happened on a development machine, during the API tests);
* checkout did not fit a phone, and the dashboard could become much wider than one;
* the header search found nothing for Mongolian words, and missed some swapped letters;
* reports counted days in UTC, CSV amounts read 100 times too large, and the orders CSV stopped at 10,000 rows;
* "Add to Bag" said nothing while offline and sent the request later;
* the English order page named the delivery methods differently from checkout.

The eleventh was **withdrawn**: the audit said the Bag shows its skeleton for about 20 seconds when the API is down. That
was not measured. Measured, the error and "Try again" appear after 7.5 seconds, the normal time for three retries.

### Known limits that remain

* **Mongolian search** knows the words in `apps/api/src/angel/services/catalog/garment_words.py` (every type name the
  Mongolian site shows, and common synonyms). The list was not reviewed by a shopper: **read it through** and add the words
  your customers use. Other Mongolian words are ignored, and the page says so.
* **Swapped letters** are repaired in one word per search, for Latin words of four letters or more.
* **Phone layout** is measured as page width in a desktop browser at 390 px. It was not tried on a real phone.
* The **CSV** files have a UTF-8 byte order mark and protect against formulas, but were not opened in Excel itself.

## 2. Accounts and secrets (yours to provide)

Put them in `.env.prod` (`chmod 600`, never in git), then run `make deploy-check`.

- [ ] **Domain** with DNS pointing at the server: `SITE_ADDRESS`, `SITE_URL`.
- [ ] **Secrets:** `POSTGRES_PASSWORD`, `JWT_SECRET` (commands in `deploy.md`). Keep a safe copy of `JWT_SECRET`: staff
      two-factor secrets are encrypted with it.
- [ ] **QPay merchant:** `QPAY_BASE_URL` (not the sandbox), `QPAY_CLIENT_ID`, `QPAY_CLIENT_SECRET`, `QPAY_INVOICE_CODE`.
      Run `scripts/qpay_smoke.py`, then pay one small real order, refund it from the admin panel, and confirm both in
      QPay's own records.
- [ ] **Twilio:** `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`. Send a real code to a number on each
      mobile operator your customers use.
- [ ] **SMTP:** `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `MAIL_FROM`. Set up SPF, DKIM and DMARC for
      the sending domain, and check that a message reaches an inbox rather than spam.
- [ ] **Google sign-in:** `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, redirect URI
      `https://<domain>/api/v1/auth/google/callback`.
- [ ] `OTP_DEV_CODE` is **empty**. (With `APP_ENV=prod` the API refuses to start with it, or with any fake, offline,
      console or sandbox setting.)

None of QPay, Twilio, SMTP or Google has been tried against the real service.

## 3. The shop itself

- [ ] **Replace the demo catalogue.** The products come from a research dataset, and their prices and stock are generated.
      Selling needs your own products, and showing the dataset's photos in public needs its licence checked.
- [ ] Real store address, delivery methods, fees and delivery times match what you can actually do.

## 4. Legal (you or a lawyer)

[`data-inventory.md`](data-inventory.md) (in Mongolian) lists what personal data the shop handles and ends with the
questions to answer. Give it to whoever writes the texts.

- [ ] **The site has no privacy policy and no terms of service page.** Both need text from you or a lawyer; the pages can
      then be added.
- [ ] **Return window:** the default is 14 days (`RETURN_WINDOW_DAYS`). Confirm it, and who pays return delivery, against
      current law.
- [ ] **How long data is kept:** `OTP_RETENTION_HOURS` (24), `REFRESH_TOKEN_RETENTION_DAYS` (30),
      `SECURITY_EVENT_RETENTION_DAYS` (180), `EMAIL_SENT_RETENTION_DAYS` (7), `EMAIL_FAILED_RETENTION_DAYS` (30), and how
      long order records **must** be kept.

These settings are listed in `.env.example`, not in `.env.prod.example`. Add a line to `.env.prod` to change one.

## 5. Running it

- [ ] Create the first administrator and warehouse accounts, set up two-factor sign-in at once, store the recovery codes.
- [ ] **Watch the logs.** The app writes JSON logs and sends no alerts of its own, so set up an alert on these events:

      | Event | Meaning |
      | --- | --- |
      | `refund_failed_will_retry`, `refund_retry_failed` | a customer's money has not gone back yet |
      | `payment_setup_failed`, `payment_reconcile_failed` | payments are not being created or checked |
      | `email_gave_up` | an email was dropped after all retries (`deploy.md`, "Email delivery") |
      | `email_failed`, `outbox_failed`, `sms_failed` | messages are not going out |
      | `order_expiry_failed`, `housekeeping_failed` | a background job is failing |
      | `readiness_probe_failed` | the database, Redis or the model is unavailable |
      | `unhandled_exception` | a request failed with a 500; `/readyz` can stay green meanwhile |

- [ ] An outside check that the site is up.
- [ ] **Backups:** schedule `make backup` (cron line in `deploy.md`), **copy the files off the server**, and rehearse a
      restore on the server, **with the API stopped** as `deploy.md` shows.

### What has been rehearsed

On the development machine (Apple Silicon, Docker with 4 GB of memory), the whole production Compose stack was run once
with a throw-away `.env.prod` and `APP_ENV=prod`, then removed:

* Both images build for `linux/arm64` (API 2.9 GB, web 315 MB). `make deploy-check` passes with the throw-away values,
  every service starts and those with a health check become healthy, `https://localhost/` answers with the security headers, and the shop's time zone
  works inside the Linux image. The API used about 1 GB of memory when idle.
* With the **real** FashionCLIP and YOLO models and the development catalogue's 41,885 products (only the product and
  category tables were copied, with a few pictures): three product photos each found their own product first, and
  Mongolian searches worked. A text file, a HEIC header, a truncated JPEG and an empty file all got 422, nothing was
  installed in the container, and the log had no errors up to that point.
* The detector gives identical labels, scores and boxes on 12 pictures with and without the upload fix. Its labels can
  be wrong on pictures of a single item (a handbag read as "vest"); the photos tried still found their product.
* `make backup` ran, and its database dump and picture archive restored damaged data exactly. Restoring while the API
  was running made the next photo search fail with a 500, although `/readyz` stayed green. `deploy.md` now stops the API
  first; those commands were run as written, and photo searches worked afterwards.

**Not** rehearsed: a real server and domain, a Let's Encrypt certificate, and every outside service (section 2).
