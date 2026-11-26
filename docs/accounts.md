# Accounts: phone, email, codes and devices

Who people are and how they get back in. The session mechanics (access and refresh tokens, cookies, CSRF, the guest cart merge)
are in [`commerce.md`](commerce.md); this page covers the sign-in methods and what a signed-in person can change.

## The model

An account has **a phone number, an email, or both**. Either can be added, changed or removed later, as long as one remains
(the database refuses an account with neither: `ck_users_contact_present`).

| Column | Meaning |
| --- | --- |
| `users.email` | lower-case, unique, **nullable** (an account made with a phone number has none until it adds one) |
| `users.phone` | E.164 (`+14155552671`), unique, nullable, checked by `ck_users_phone_e164`. Whatever the person types is normalised first (`core/phone.py`, the `phonenumbers` package; numbers without a country code are read in `DEFAULT_PHONE_REGION`) |
| `email_verified_at`, `phone_verified_at` | set when a code sent to it was confirmed (Google also vouches for an email). Unverified emails still sign in with a password; nothing is blocked on verification |
| `password_hash` | nullable: accounts that use codes or Google have none |

Code that needs "a name for the account" in logs, failure counters or event actors uses `User.identifier` (email, else phone).
Phone-only customers give an **email at checkout** (`contact_email` in `POST /checkout`, required only when the account has none)
because order updates are emailed; it is stored on the order, not on the account.

## One-time codes

Six digits, sent by SMS (phone) or email. They power sign-in, adding or changing a phone or email, confirming an email and
resetting a password. Table `otp_challenges`; `services/accounts/otp.py`.

* Only an HMAC of the code is stored (keyed by `JWT_SECRET`, bound to the purpose and the destination), so a database leak does
  not reveal live codes, and a code for one purpose or number is useless for another.
* Good for `OTP_TTL_SECONDS` (5 min), `OTP_MAX_ATTEMPTS` wrong guesses (5), once. Asking for a new code retires the old one.
* A new code can be asked for after `OTP_RESEND_SECONDS` (60) and at most `OTP_MAX_SENDS_PER_HOUR` (5) per destination; the route
  adds a per-address limit (`RATE_LIMIT_OTP_SEND`, `RATE_LIMIT_OTP_VERIFY`). The checks live in the **database**, not Redis, so
  they fail closed.
* A wrong guess is counted even though the request fails (the verify transaction commits before the error is raised).
* Asking for a code never reveals whether an account exists: sign-in and sign-up are one step, and "forgot password" answers
  `202` for unknown accounts too (it records the challenge, so even the cooldown looks the same, but sends nothing).

### SMS

`core/sms.py` is an interface like `Mailer` and `PaymentGateway`: `SMS_MODE=console` (default) writes the message to the API log,
so in development **read the code from the `make api` output** (`"event": "sms_sent"`); `SMS_MODE=twilio` sends it through Twilio
(`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`). `APP_ENV=prod` refuses the console sender and a fixed code.

### Email

Email subjects and bodies, SMS texts and API error messages are written in Mongolian (the web app shows its own localized
message per error `type`). A Mongolian SMS is encoded as UCS-2, so one message holds 70 characters instead of 160: the code
text is kept short.

`core/mail.py` follows the same pattern. `MAIL_MODE=smtp` (the `.env.example` default) delivers through SMTP with `SmtpMailer`;
`MAIL_MODE=console` only logs (the code default, so tests never open a socket). In development `make infra` starts
[Mailpit](https://mailpit.axllent.org), a local mail catcher: every email the API sends (codes, welcome, order updates) lands in
<http://localhost:8025> and never leaves the machine, so it costs nothing and needs no account. In production point
`SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_STARTTLS=true` and `MAIL_FROM` at a real provider;
`APP_ENV=prod` refuses `MAIL_MODE=console`.

A failed SMTP send is handled by what the email is for.

* **A one-time code** is sent at once, while the person waits: if it cannot be delivered the answer is `503`
  (`email-unavailable`) so they know to retry. Codes are never written to the outbox, so no code is stored as text.
* **Every other email** (welcome, order status, payment confirmation, cancellations and returns, security notices) goes through
  the outbox below. No request waits for SMTP.

### The email outbox

`queue_email` writes the message to `email_outbox` **in the same transaction as the change it reports** (`services/system/outbox.py`):
a rolled-back change sends nothing, and a committed one cannot be forgotten, even if the server stops right after. A worker in
the API process looks for due messages every `OUTBOX_POLL_SECONDS` (5). It claims up to 8 with `FOR UPDATE SKIP LOCKED` plus a
5-minute lease, so several API processes can run, no transaction is open during the SMTP call, and a message whose worker died
is picked up again. One send is cut off after 30 s (the SMTP timeout applies to each reply, not to the whole message), so a
batch always finishes inside its lease.

A failed send is retried after 1 min, 5 min, 15 min, 1 h, 3 h, 6 h and 24 h (8 attempts, about 35 hours), then marked `failed`
and logged as `email_gave_up`. The text is erased as soon as a message is sent. Delivery is **at least once**: if the process
stops after the SMTP server accepted a message and before that was recorded, it is sent twice.

```bash
make outbox          # how many are pending, sent and failed; failed ones with masked addresses and no text
make outbox-retry    # after fixing SMTP: queue the failed ones again
```

## Keeping and deleting data

`services/system/housekeeping.py` runs about a minute after the API starts and then every `HOUSEKEEPING_INTERVAL_SECONDS` (1 hour),
deleting in batches of 1 000. The periods are shop policy chosen for this project, **not checked against Mongolian law**:

| Data | Deleted | Setting |
| --- | --- | --- |
| One-time code records (address or number) | after 24 hours (the send limit only looks back one hour) | `OTP_RETENTION_HOURS` |
| Refresh tokens (device and IP) | 30 days after they expire. The first row of a login that is still alive stays: it says when you signed in | `REFRESH_TOKEN_RETENTION_DAYS` |
| Security activity | after 180 days | `SECURITY_EVENT_RETENTION_DAYS` |
| Sent / failed outbox messages | after 7 / 30 days (a waiting one is never deleted) | `EMAIL_SENT_RETENTION_DAYS`, `EMAIL_FAILED_RETENTION_DAYS` |
| Abandoned guest bags | after 30 days (`OrderExpirer`) | `CART_GUEST_TTL_DAYS` |

Orders and the staff activity log are not deleted.

**Deleting an account** keeps the anonymised `users` row (orders point at it), so nothing cascades. It removes, in the same
transaction: addresses, saved items, the bag, the Google link, every login, the security activity, one-time code records for the
account and for its email and phone, finished outbox messages to its addresses (a waiting one, such as a refund notice, is
still delivered), and what the person typed in a cancellation or return request (the reason category stays). **What stays:** each
order with the email, name, address and phone given for it, and reviews, shown without the name. Whether the law requires keeping
those, and for how long, **needs to be checked before launch**. Migration `e4b8f2a6c173` applied the same clean-up to accounts
deleted earlier.

### Trying real SMS for free

Sending to real phones costs money, so development uses `SMS_MODE=console`. To see one real text on your own phone, a
[Twilio trial](https://www.twilio.com/docs/usage/trials) account gives free credit but only sends to phone numbers you have
verified in the Twilio console (messages start with "Sent from a Twilio Trial account"). Set `SMS_MODE=twilio` and the three
`TWILIO_*` values in your untracked `.env`, then sign in with that number. Check in the console that your country is supported.

`OTP_DEV_CODE=000000` makes every code that value. It exists for the end-to-end tests and demos, and is refused in production.

## Endpoints (`/api/v1/auth`)

Everything here is under the same-origin check and `no-store`.

| Endpoint | What it does |
| --- | --- |
| `POST /reauth/request` | a code to the account's email (else phone) that confirms a sensitive change on an account **without a password** (see below). Does nothing for accounts with one |
| `GET /2fa`, `POST /2fa/setup` `{password}`, `POST /2fa/enable` `{code}` | staff two-factor sign-in (see "Staff sign-in") |
| `POST /otp/request` `{destination}` | send a sign-in code to a phone number or email. Always `202` for a valid destination. `422` invalid, `429` too soon, `503` SMS or email failed |
| `POST /otp/verify` `{destination, code}` | sign in, **creating the account on first use**; merges the guest cart; `is_new_user` tells the page to ask for a name. `400` wrong/expired, `429` too many guesses |
| `POST /password/forgot` `{destination}` | `202` always; a code goes to the account's phone or email |
| `POST /password/reset` `{destination, code, new_password}` | sets the password, ends **every** login, signs this browser in |
| `POST /email/verify/request`, `/email/verify/confirm` `{code}` | confirm the email the account already has |
| `POST /phone/request` `{phone, current_password?}`, `POST /phone/confirm` `{phone, code}` | add or replace the phone: the code goes to the **new** number, and only the person who asked can use it. `409 phone-taken` if another account has it |
| `DELETE /phone` `{current_password?}` | remove it; `409 last-sign-in-method` if there is no email |
| `POST /email/request`, `POST /email/confirm`, `DELETE /email` | the same for the email. Removing the email also removes the password (it needs the email to be used) |
| `GET /sessions` | the open logins: device ("Chrome on macOS"), address, when it began and was last used, and which is this browser |
| `DELETE /sessions/{id}` | sign one device out (`404` if it is not yours or already over); if it is this browser the cookies are cleared |
| `POST /sessions/revoke-others` | sign out everywhere except this browser |

A signed-in session alone never changes how an account is signed in to, and never deletes it (the "step-up" rule of the
OWASP Authentication cheat sheet). An account **with a password** sends `current_password` (`password` when deleting; wrong:
`403`, counted against the same per-account failure limit as login). An account **without one** (codes or Google only) sends
`reauth_code`, a fresh one-time code from `POST /reauth/request` (purpose `reauth`, single use); without it the answer is `403
reauth-required`. This covers setting a first password, adding, replacing and removing the phone or email, and deleting.

`DELETE /me` also answers `409 open-orders` (with `count`) while the account has an order that is `pending`, `paid` or
`shipped`: the owner could no longer follow it or get help with it. The check is repeated inside the deleting transaction under
the same per-user lock checkout takes.

## Staff sign-in

Administrators and warehouse workers sign in with **their password only**:

* No one-time codes: `POST /otp/request` for a staff address answers the usual `202` but sends nothing, and `/otp/verify` fails
  like a wrong code even if the code is right (for example a fixed development code). Nothing on the account is touched.
* No Google: the callback ends on `/login?error=google_failed`, links nothing and keeps the password.
* No wishlist or address book (`403`, like the bag and checkout), and the web app shows them only their profile.
* A password reset by code works **only for staff who have two-factor sign-in on**; it changes the password but signs nobody in
  (`403 sign-in-required`), so the second factor is still needed. The daily failed-login count is not cleared for staff.
  Without two-factor sign-in the way back in is the server command (`make create-admin EMAIL=...`).

### Two-factor sign-in (TOTP)

RFC 6238 codes (SHA-1, 6 digits, 30 s) from any authenticator app (`core/totp.py`).

* **Set up** on `/account/profile`: password, scan the QR (an SVG data URI made on the server with `segno`; the secret never goes
  to a third party), enter the first code. Ten single-use recovery codes are shown **once**. Every other login ends.
* **Signing in** then needs `totp_code` with the password: `401 totp-required` (only after a correct password) or `401
  totp-invalid`. A wrong code counts against the login failure limits. Each TOTP time step and each recovery code works once
  (the user row is locked while it is checked). One step of clock drift either way is allowed.
* **Storage.** The secret is encrypted with AES-GCM under a key derived from `JWT_SECRET` (`core/secret_box.py`); recovery codes
  are stored as hashes. So two-factor sign-in needs a **configured** `JWT_SECRET` (setup answers `503 totp-unavailable`
  otherwise), and **changing `JWT_SECRET` means running `make reset-2fa` for every member of staff**.
* **Required or not.** `STAFF_2FA_REQUIRED=true` (always on when `APP_ENV=prod`) closes the back-office API with `403
  totp-setup-required` until it is set up; `/admin` shows the setup screen instead. In development it is optional.
* **Lost phone.** Use a recovery code, or `make reset-2fa EMAIL=...` on the server (also ends every login). There is no way to
  turn it off from the web, so a stolen session cannot remove it.
* **Enrol new staff right away.** Until someone enrols, whoever knows the password can enrol their own app. The owner is emailed
  when it is turned on.

### Rules worth knowing

* **Email codes and old passwords.** If someone signs in with an email code and the address was never verified, a password on
  that account is **removed** and its other logins end: whoever registered an unverified address first might not own it, and the
  code proves who does (the same rule as signing in with Google, see `commerce.md`). The owner is emailed when this happens.
  It never applies to staff, who cannot sign in with a code.
* **Devices.** `refresh_tokens` records the User-Agent and address of the request that created each login (copied along when a
  token rotates). `describe_device` turns the header into a short label. Revoking a login revokes its whole token family.
* **Security activity.** `security_events` (migration `a9d3e5f7b126`) gets one row per sign-in (`login`, with the method
  `password`, `otp` or `google`), failed password attempt on an account that exists (`login_failed`; an unknown email leaves nothing),
  `new_device`, `password_changed`, `password_reset`, `sessions_revoked`, `email_changed`, `phone_changed` and `two_factor_enabled`, written in the same
  transaction as the action so a refused action leaves no row. `GET /auth/security-events` returns your last 30, newest first, with the
  device label and the address with its last part hidden (`203.0.113.x`). The profile shows them under **Security activity**.
* **New device.** A sign-in whose User-Agent is not familiar is a `new_device`: an email to the owner with the device and the
  time is queued with the sign-in (`AuthService.queue_notice`). Familiar means a stored refresh token or a **successful** `login`
  event with that User-Agent, so a device is remembered as long as security activity is kept. The one sign-in that is never
  "new" is the one that creates the account: the caller says so (`first_sign_in`), instead of guessing from rows that are
  cleaned up. Phone-only accounts get the event but no message.
* **Notices.** Changing or resetting the password tells the owner's email; changing the email tells the **old** address, so someone who
  took over an account cannot move it quietly.
* **Daily limit.** On top of 5 failures per 5 minutes per email there is `RATE_LIMIT_LOGIN_EMAIL_DAILY` (20 per day): the next attempt is a
  429 even with the right password, and the owner gets one email when the limit is reached. A successful sign-in does not reset the daily
  count; changing or resetting the password does.
* **Weak passwords.** Length (10 to 128) stays the schema's rule; `core/passwords.py` also refuses, with `urn:angel:problem:weak-password`
  and a `reason` (`common`, `repeated`, `contains_identity`), a password in `core/common_passwords.txt` or a common word with a few
  characters added (`password1234`, not `password-horse-battery-staple`), one made of one or two characters, and one that contains
  the owner's name or the email's local part. There is deliberately no call to a breach service: no part of a password leaves the
  server. On a reset the check runs *before* the code is spent. The web mirrors the first two rules in `password-strength.ts` for the
  strength meter; the API decides.
* **Staff sessions.** An administrator's or warehouse worker's refresh token lives `STAFF_REFRESH_TTL_HOURS` (12) after its last use,
  and each rotation starts the window again (an idle timeout, not an absolute one).
* **Deleting an account** anonymises it as before; the typed confirmation is now the email, or the phone number if there is no email
  (`DeleteAccountRequest.confirm`), and the phone and verification times are cleared.

## The web app

* `/login`: a **Phone | Email** tab bar (a sliding thumb, CSS only). Phone: country picker and number (formatted as typed by
  `libphonenumber-js`, sent in international format) -> six boxes (`OtpInput`: paste, browser autofill via
  `autocomplete="one-time-code"`, Backspace and arrows, shake on a wrong code) -> for a new account, "What should we call you?".
  Email: the password form, with "Email me a code instead". `?method=email` opens that tab.
* `/forgot-password`: destination, then code and new password.
* `/account/profile`: **How you sign in** shows the phone number and email with their verified state and Add / Change / Verify /
  Remove dialogs (two steps: where, then the code; the password when there is one). **Your devices** lists the logins and signs
  them out.
* Checkout asks phone-only customers for an email.

Tests: `apps/api/tests/accounts/` (`test_otp_api.py`, `test_account_contact_api.py`, `test_sessions_api.py`), the component tests
beside the code, and `apps/web/e2e/phone.spec.ts` (needs the API to run with `OTP_DEV_CODE=000000`, see [`e2e.md`](e2e.md)).
