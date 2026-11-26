# Accounts, cart, checkout and orders

Everything is under `/api/v1`; errors are RFC 7807 problems (`application/problem+json`) like the rest of the API.
Interactive docs: `/api/v1/docs`. The browser side is described in `docs/frontend.md`.

## Running it

```bash
make infra && make migrate && make api     # .env needs PAYMENTS_MODE=offline (copied from .env.example)
make web
make e2e                                   # whole flow in Chromium (see docs/e2e.md)
make test                                  # API integration tests need make infra
```

## Sessions

| | |
| --- | --- |
| Access token | HS256 JWT, 15 min, claims `sub`, `jti`, `iat`, `exp`, `typ`. Sent as `Authorization: Bearer`; the web app keeps it in memory. |
| Refresh token | 256 random bits, only its SHA-256 is stored. Cookie `lk_refresh`: `HttpOnly; SameSite=Lax; Path=/api/v1/auth` (+ `Secure` when `APP_ENV=prod`), 30 days. |
| Rotation | Every refresh issues a new token. See "A refresh whose answer is lost" below; a used token presented after 10 s revokes the whole login (`family_id`). |
| `lk_session` | A non-secret marker cookie (`1`) next to the refresh cookie, so the web app's edge proxy can redirect signed-out visitors. Grants nothing. |
| Passwords | argon2id, 10 to 128 characters, no composition rules. Unknown emails cost the same time as wrong passwords; failed logins are also limited per email (5 per 5 min, counted on failure, reset on success). |
| CSRF | Bearer endpoints are immune. Endpoints that act on a cookie (auth, cart) refuse a browser request whose `Origin` is not in `CORS_ORIGINS`, on top of `SameSite=Lax`. |

Endpoints: `POST /auth/register|login|refresh|logout`, `GET /auth/me`. Register and login return the access token in
the body and set the cookies; both merge the guest cart.

**A refresh whose answer is lost.** The server may rotate a token while the browser never receives the new one: a page that
redirects in the browser while its first refresh is in flight (a product address without its slug), a dropped connection, two
tabs at once. So for 10 s a token that was **just rotated** is accepted again and gets another new one, as long as the login has
not moved on (no later token of it has been used). The window is measured from the first rotation and does not slide. As soon as
one of two such tokens is used the other is retired: presenting it is refused, and after 10 s treated as theft. An older token is
always refused, and nothing revives a signed-out login. The cost: someone who steals a token within those 10 s can get a session,
which is detected at the next reuse (the same trade-off as the grace period of Auth0 and Okta). Refresh and sign-out take one
advisory lock per login, so a sign-out cannot miss a token that is being issued.

### Your account (profile, password, deletion)

All three need a bearer token. Changes to how an account is signed in to, and deleting it, also need the current password
or, for an account without one, a fresh code (`accounts.md`). `GET /auth/me` and the session responses carry `avatar_url`, `has_password` and `providers`
(e.g. `["google"]`).

| Endpoint | What it does |
| --- | --- |
| `PATCH /auth/me` `{full_name}` | rename |
| `PUT /auth/password` `{current_password?, new_password}` | set or change the password. An account with a password must send the current one (wrong: **403**, not 401, because the person is signed in; counted against the same per-email failure limit as login). A Google-only account sends a fresh confirmation code instead. Every other login ends (all refresh tokens revoked) and this browser gets a new session |
| `DELETE /auth/me` `{confirm, password?}` | anonymizes the account: email becomes `deleted-<id>@deleted.invalid`, name "Deleted user", password, photo, Google link, addresses, wishlist, cart and refresh tokens removed, `is_active = false`. Orders stay (`orders.user_id` is `RESTRICT`, and the shop keeps its records) with their own address and price snapshots. The typed email (or phone number, for an account with no email) must match; a password, or a fresh confirmation code for an account without one, is required. Staff are refused (no lock-out), and so is an account with an unfinished order (`409 open-orders`). The address can be registered again |

The web app's `/account/profile` page uses them. Google's profile photo (https URLs only, up to 500 characters) is stored in
`users.avatar_url` and refreshed at each Google sign-in; without one the header shows initials.

## Sign in with Google

Authorization code flow with PKCE, run by the API; the browser only follows redirects, so it works without scripts and no
token ever appears in a URL.

1. The button on `/login` and `/register` is a link to `GET /api/v1/auth/google/start?next=/where/to/return`. The API sets a
   signed ten-minute cookie `lk_oauth` (`HttpOnly; SameSite=Lax; Path=/api/v1/auth/google`) holding the `state`, a `nonce`,
   the PKCE verifier and the return path, and redirects to Google.
2. Google redirects to `GET /api/v1/auth/google/callback` **on the web origin** (Next proxies `/api/v1` to the API, so the
   cookies below are first-party). The API compares `state` with the cookie, exchanges the code with the client secret and
   verifier, checks the ID token's issuer, audience, expiry and nonce, and requires a verified email. (The token's signature
   is not checked: it comes straight from Google's token endpoint over TLS, which Google's documentation accepts.)
3. Staff are refused here (`google_failed`) and their account is left as it is. For everyone else it finds the user by `(google, sub)`; otherwise by email; otherwise creates one. Then it issues the normal session
   (`lk_refresh`, `lk_session`), merges the guest cart, clears `lk_oauth`, and redirects to `next`. The web app's
   `AuthBootstrap` trades the refresh cookie for an access token on load, like after any reload.
4. Every failure is a redirect to `/login?error=<code>` (`google_denied`, `google_failed`, `google_unverified`,
   `account_disabled`), never a JSON page and never a reason. The login page maps known codes to a sentence and ignores
   the rest.

**Existing password accounts.** If Google's verified email belongs to an account made with a password, Google is linked to
it and **its password is removed**. Nobody verifies the email of a password account here, so whoever registered an address
first may not own it; after linking, the real owner signs in with Google and a squatter's password no longer works. Accounts
that only use Google have no password (`users.password_hash` is null), so password login fails for them exactly like an
unknown email. Identities live in `oauth_identities` (`provider`, Google's stable `sub`, unique together): the `sub`, not
the email, identifies the person.

**Set it up** (the button is hidden until both values exist):

1. [Google Cloud Console](https://console.cloud.google.com/) > create a project.
2. APIs & Services > OAuth consent screen: User type External, publishing status Testing, add your own Google account
   under Test users (only they can sign in until the app is published).
3. Credentials > Create credentials > OAuth client ID > **Web application**. Authorized redirect URI:
   `http://localhost:3000/api/v1/auth/google/callback` (add the real domain's callback for production). No JavaScript
   origin is needed.
4. Put the client ID and secret in `.env` as `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`, run `make migrate` (new
   `oauth_identities` table, nullable `password_hash`), restart `make api`, open `/login`.

`OAUTH_MODE=fake` replaces Google with an in-process stand-in for tests and CI: "signing in" skips the consent screen and
`login_hint` chooses the email (`unverified:<email>` yields an unverified one, `<email>;picture=https://...` gives it a photo). `APP_ENV=prod` refuses it. Limits:
`RATE_LIMIT_OAUTH` (default 30 per 5 minutes per address).

## Reviews

Only people who have **received** a product can review it: an order of theirs that is `delivered` (a pickup order:
collected) must contain it. A refunded or cancelled order does not count; a return that is still open does. While the order is
`paid` or `shipped` the API says `viewer.awaiting_delivery` and the page says the review opens once it arrives. Reviews written
before this rule stay and can still be edited. One review per person per product (a unique constraint), with a 1 to 5
rating, an optional headline (120 characters) and text (2 000), shown as first name and last initial ("Ada L."), never an
email.

| Endpoint | |
| --- | --- |
| `GET /products/{id}/reviews` | Published reviews (`sort` newest / highest / lowest, paged) with the average and the count per star. Signed in, it also says whether you bought the product and returns **your own review even if it is hidden** (`viewer`); that response is `no-store` |
| `POST /products/{id}/reviews` | 201; 403 `review-not-allowed` if you have not received it; 409 `review-exists` if you already reviewed it. Rate limited (`RATE_LIMIT_REVIEW`, 20 per hour) |
| `PATCH` / `DELETE /reviews/{id}` | Your own only (someone else's is a 404, not a 403, so ids reveal nothing) |
| `/admin/reviews…` | Moderation: `docs/admin.md` |

`products.rating_average` and `rating_count` are **kept in step with the published reviews in the same transaction**, with
the product row locked first (the lock checkout and stock changes use), so concurrent reviews cannot overwrite each other's
recount (tested by posting four at the same moment). They come back in `ProductOut`, so product cards show stars and
`aggregateRating` goes into the product page's JSON-LD without another query, and only once there is a published review (an
empty rating is not valid structured data). When an account is deleted its reviews stay, shown as "Deleted user".

On the product page the first page of reviews is rendered on the server (for the first paint and crawlers) and the browser
immediately fetches a current copy, so a new or hidden review shows at once even though the page itself may be up to a minute
old (Next's cache). The rating on cards and in the page header, which come from the product record, can lag by that minute (and a product page nobody has opened for a while may show its old copy once before it refreshes).

## Cart, wishlist, addresses

* **Cart** (`/cart`, `/cart/items`, `/cart/items/{id}`): one per user, or per guest through the `lk_cart` cookie (random id,
  hash stored). Lines show the *current* price and stock (`max_quantity`, `issue`: `out_of_stock` | `low_stock`); the cart
  is never rejected for a stale line, checkout is. Adds and changes are checked against stock and `CART_MAX_QUANTITY`
  (409 `insufficient-stock` with `available`). Sizes are validated per category.
* **Merge on login:** same product and size add up, never beyond stock; a line already over a limit is kept and flagged.
* **Wishlist** (`/wishlist`, `PUT|DELETE /wishlist/{product_id}`): idempotent, accounts only.
* **Addresses** (`/addresses`): up to 10, exactly one default (partial unique index), other people's ids are 404.

**Price when added.** `cart_items.price_cents_at_add` is the unit price when the line first went in (adding more of it keeps it;
older lines are null). A line whose current price differs shows "Price changed / dropped: it was X when you added it".

**Buy again.** `POST /orders/{number}/reorder` (your own order; 404 otherwise, 403 for staff) puts each line back with the same size
and quantity, limited by the stock now and the bag limits, in one transaction. The reply has the cart, how many lines went in, and
`skipped: [{name, reason}]` with `unavailable`, `out_of_stock`, `size`, `bag_full` or `reduced` (a smaller quantity went in).

## Checkout and orders

`POST /checkout` (header `Idempotency-Key`) turns the cart into a **pending order that holds the stock**:

1. a per-user advisory lock serialises one shopper's checkouts;
2. that shopper's older unpaid orders have their payment cancelled at the provider (outside any transaction), then
   their stock is released; if one turns out to have been paid, the request fails with 409 `payment-in-progress`;
3. in one transaction: product rows are locked in id order, the cart is re-validated, stock is decremented, the order is
   written with a **snapshot** of name, price, size, image and the shipping address;
4. the payment is created (outside the transaction) and stored. A replay with the same key resumes at whatever is missing.

**Consent to the total.** The page sends `expected_total_cents`, the total on the button when it was pressed. If the server
computes something else (a price or tariff changed) the answer is `409 price-changed` with the new `total_cents` and no order
is made. It is checked before an older invoice is cancelled (so a refused request leaves that QR payable) and again with the
product rows locked. The field is optional in the API; the web app always sends it.

**One key, one request.** The order stores a hash of the address, shipping method and contact email. The same
`Idempotency-Key` with different ones answers `422 idempotency-key-reused`; the page makes a new key whenever they change.

Totals are computed on the server (standard shipping free from `FREE_SHIPPING_THRESHOLD_CENTS`, express never). The cart
is cleared (only the lines that were bought) when the payment succeeds. Unpaid orders are cancelled after
`ORDER_PENDING_TTL_MINUTES` by a background task that is safe to run in several processes. `GET /orders` and
`GET /orders/{number}` are owner-only.

### The life of an order

`pending` (stock held, awaiting payment) → `paid` → `shipped` → `delivered`; `pending` → `cancelled` (expired, replaced by a
newer checkout, cancelled by an administrator, payment cancelled); `paid`, `shipped` or `delivered` → `refunded`. A paid order
is never "cancelled": its money goes back and it becomes `refunded`. A payment that arrives for an order that is already
cancelled is refunded automatically. The administrator's actions are in `docs/admin.md`; the state is a CHECK constraint on
`orders.status`. A **store pickup** order uses the same states under other names: `shipped` is *ready for pickup* (no carrier or
tracking number; the email gives `PICKUP_ADDRESS`) and `delivered` is *collected*.

Each change is recorded in **`order_events`** in the same transaction as the change (`placed`, `paid`, `shipped`, `delivered`,
`cancelled`, `refunded`, the six request events below, and administrators' `note`). `OrderOut` carries `shipped_at`,
`delivered_at`, `refunded_at`, `carrier`, `tracking_number` and a **safe timeline**: every type but `note`, and from their data
only the carrier and tracking number of a shipment, the reason a cancel happened and the kind of a decided or withdrawn request.
Notes, staff names, refund reasons and amounts never reach the customer's API.

The customer's order page (`/account/orders/{number}`) shows a progress stepper (Placed, Paid, Shipped, Delivered, or ending
in Cancelled / Refunded; a pickup order says Ready for pickup and Collected), the tracking number, the lines, and the history; once delivered, each line has a "Write a review"
link. The customer is emailed when the order ships (carrier and tracking number), is delivered, is cancelled and is refunded.
These messages are queued with the change and retried if the mail server is down (`docs/accounts.md`, "The email outbox").

### Cancelling and returning (customer requests)

Always the **whole order**. A request only asks: no money or stock moves until a member of staff decides.

| | Cancel | Return |
| --- | --- | --- |
| When | `paid`, not yet shipped | within `RETURN_WINDOW_DAYS` (14) of `delivered_at` (a pickup order: when collected) |
| Path | `requested` → `completed` (approving refunds at once and restocks) | `requested` → `approved` → `received` → `completed` |
| Other ends | `declined`, `withdrawn` | `declined` (also from `approved`, if the goods never come), `withdrawn` |
| While open | the order **cannot be shipped** (409 `order-request-open`) | the customer sees where to send the goods (`PICKUP_ADDRESS`) once approved |

Rules (`services/commerce/request_rules.py`): one open request per order (also a partial unique index on `order_requests`);
after a **declined** request the same kind cannot be asked again (a withdrawn one can; a declined cancel does not take away the
later return); only a request not yet decided can be withdrawn. The API works this out and sends `available_request`,
`return_deadline` and `return_address` with the customer's order, so the web does not repeat the rules.

| Endpoint | |
| --- | --- |
| `POST /orders/{n}/requests` `{kind, reason, details?}` | the owner; reasons depend on the kind, `other` needs `details`. 409 `order-request-not-allowed` or `order-request-open`. Rate limited (`RATE_LIMIT_ORDER_REQUEST`, 10 per hour) |
| `POST /orders/{n}/requests/{id}/withdraw` | the owner, while `requested` |

Every change locks the order row (like fulfilment), so asking to cancel and shipping at the same moment can never both succeed.
Events: `cancel_requested`, `return_requested`, `request_approved`, `request_declined`, `request_withdrawn`, `return_received`
(the refund itself is the usual `refunded`). The customer is emailed when a request arrives, is approved or declined, when the
returned goods arrive and when the money goes back. An account with an open request cannot be deleted. Staff actions are in
`docs/admin.md`.

**Before launch:** 14 days is a shop policy chosen for this project. It was not checked against Mongolian consumer law; check the
current text (legalinfo.mn). A claim about faulty goods outside the window can still be settled by an administrator's refund.

## Payments

Prices are stored in **togrog minor units** (togrog x 100, `price_cents`; 87,900 ₮ = `8790000`) and the shop prices in one
currency only, `CURRENCY=MNT`, like Amazon or Apple price each market in its local currency: there is no conversion, the
amount shown is the amount charged. The payment provider is behind `PaymentGateway` (`payments/`); settlement
(`services/commerce/payments.py`) is the only place that turns a confirmed payment into an order change, and it applies
each payment exactly once (the provider's payment id is stored in `payment_events` in the same transaction).

**Paid money is never stranded.** A notification can be lost, so the shop does not rely on it alone:

* Whenever cancelling an invoice reports that it was already **paid** (the expiry sweep, the customer's or the
  administrator's cancel, a new checkout replacing the old order), the API asks the provider and settles the payment there and
  then (`PaymentSettlement.reconcile`). With QPay, a refused invoice deletion is re-checked before the invoice is treated as
  closed. A lost notification is therefore noticed at the latest when the order's time runs out
  (`ORDER_PENDING_TTL_MINUTES`) or when the customer presses "check my payment"; QPay is not polled in between.
* Money that has to go back (payment after cancellation, wrong amount) is first recorded as `payments.status =
  'refund_pending'` and only then sent to the provider. If that fails the debt stays recorded: the webhook answers 503, a repeat
  notification or a "check my payment" tries again at once, and the sweep retries every `REFUND_RETRY_MINUTES`. The customer's
  order page says the money is on its way (`refund_pending`) and the administrator sees it on the payment record.
* **Limit:** if the provider made a refund but its answer was lost, the retries may keep failing because there is nothing left
  to refund. The payment then stays `refund_pending` (errors are logged as `refund_failed_will_retry`) and has to be checked in
  the provider's own dashboard.
* The sweep goes through **all** overdue orders in batches, so ones it cannot close never block the ones behind them.

`PAYMENTS_MODE=offline` (default in `.env.example`): no provider. `POST /checkout/orders/{number}/simulate-payment` marks
an order paid through the same settlement code; it answers 404 with a real gateway, and the API refuses to start with
offline mode when `APP_ENV=prod`. This is what the web app's test-payment button calls (there is no card form). Offline charges in the shop currency.

`PAYMENTS_MODE=qpay`: QPay Merchant API v2 (`payments/qpay_gateway.py`, https://developer.qpay.mn). Needs
`QPAY_CLIENT_ID`, `QPAY_CLIENT_SECRET` and `QPAY_INVOICE_CODE` (the sandbox's public test values are `TEST_MERCHANT`,
`123456`, `TEST_INVOICE`; prod refuses the sandbox URL). The flow:

1. `POST /checkout` reserves the stock, then creates one QPay invoice per order for exactly the order total (`charge_currency`
   and `charge_minor` on the payment equal the order's; a gateway that charges another currency is refused as misconfigured).
   Invoice creation is serialised per order (advisory lock), because QPay rejects a second invoice with the same number.
   The response carries the QR image, QPay short link and bank-app deep links (`payment.qpay`).
2. The customer scans the QR (or opens their bank app on a phone) and pays.
3. QPay calls `GET|POST /webhooks/qpay?order=…`. The notification is **not signed**, so it is only a trigger: the API asks
   QPay (`payment/check`) and settles only what QPay confirms. Forged calls change nothing.
4. While the QR is on screen the page reads the order status from **our own API** (`GET /orders/{number}`, every 3 seconds,
   paused in a hidden tab) and moves to the confirmation page as soon as the status is `paid`. This never calls QPay (QPay
   discourages frequent polling); it only picks up what step 3 settled.
5. The callback must be reachable from the internet (`QPAY_CALLBACK_BASE_URL`; locally a cloudflared/ngrok tunnel). Without
   it the status stays `pending`, so the customer presses "check my payment": `POST /checkout/orders/{number}/check-payment`
   asks QPay once and settles what it confirms; the page also does that once when the customer returns from their bank app.
   Nothing in the browser asks QPay on a timer.

A payment for a different amount or currency than the invoiced one, or one that arrives after the order was cancelled
(expired or replaced by a newer checkout), is refunded automatically (refund, falling back to QPay's cancel for non-card
payments). Unpaid invoices are deleted when their order expires. **The sandbox flow (token, invoice with QR and bank
links, check, cancel) was run against `merchant-sandbox.qpay.mn`; paying an invoice needs QPay's test tools.**

## Turning QPay on

1. **Credentials.** Sandbox: the public test values `QPAY_CLIENT_ID=TEST_MERCHANT`, `QPAY_CLIENT_SECRET=123456`,
   `QPAY_INVOICE_CODE=TEST_INVOICE`, `QPAY_BASE_URL=https://merchant-sandbox.qpay.mn`. Production: your own merchant values
   from QPay (contract with QPay), `QPAY_BASE_URL=https://merchant.qpay.mn`. Never commit them.
2. **Check them first:** `make qpay-check` (`scripts/qpay_smoke.py`) reads `QPAY_*` from `.env` and, over the real network,
   gets a token, creates a 100 MNT test invoice, checks that the QR, short url and bank links come back, confirms
   `payment/check` reports it unpaid and cancels it. Nothing is charged. It refuses `APP_ENV=prod`. It works while
   `PAYMENTS_MODE` is still `offline`. (Run against the public sandbox: token, invoice with QR and 23 bank links, check and
   cancel all succeeded.)
3. **Switch:** `PAYMENTS_MODE=qpay`, restart `make api` (no `payments_disabled` warning should appear).
4. **Callback (optional locally):** QPay calls `QPAY_CALLBACK_BASE_URL/api/v1/webhooks/qpay`, so it must be reachable from the
   internet: `cloudflared tunnel --url http://localhost:8000` and put its https address in `QPAY_CALLBACK_BASE_URL`. Without a
   tunnel the "I've paid, check payment" button does the same `payment/check`.
5. **Paying in the sandbox** needs QPay's own sandbox test tools or test account; a real bank app cannot pay a sandbox invoice.
6. **Production:** HTTPS domain, `APP_ENV=prod` (the API refuses to start with offline mode, the sandbox url or missing
   credentials), the callback on the public domain.

The gateway discards its token and fetches a new one from `/v2/auth/token`, once, when QPay answers 401 or 403, as QPay's
guide asks; a second rejection is reported as a provider error.

## Resuming, cancelling and emails

An order that waits for payment (`pending`) carries `expires_at` (creation time + `ORDER_PENDING_TTL_MINUTES`) and, with QPay,
the same `qpay` block as the checkout response, so the QR, bank links and a countdown can be shown again from the order page,
the confirmation page or after a reload: the payment is never lost. `POST /orders/{number}/cancel` lets the customer cancel
an unpaid order (409 `invalid-order-transition` otherwise): the QPay invoice is closed first, and if the customer paid in the
meantime the cancel is refused and the payment settles normally; then the stock is released (`cancel_reason = "customer"`).
Replaying a checkout `Idempotency-Key` whose order has expired or been cancelled answers 409 `attempt-expired`.

Emails (through the outbox; `docs/accounts.md`): the payment confirmation lists the items, delivery method, address, phone and total; an
order that expires unpaid sends a short "nothing was charged, your Bag is unchanged" notice (`services/commerce/order_text.py`).

## Delivery addresses and shipping

The shop delivers inside Mongolia only. An address (`/addresses`) is `region` (one of the 21 aimags or Ulaanbaatar,
`core/mongolia.py`), `city` (a district of Ulaanbaatar, chosen from the nine, or a soum), `khoroo` (khoroo or bag), `line1`
(street, building, apartment), `line2` (entrance, floor, door code), an optional 5-digit `postal_code` and a required
Mongolian phone (stored as E.164 `+976…`, so a courier can call). `country` is always `MN`. The web form lists the same data
(`features/account/mongolia.ts`; change both together).

The delivery zone follows the region: Ulaanbaatar is `ub`, every aimag is `rural` (`services/commerce/shipping.py`).
`GET /checkout/shipping-methods?zone=ub|rural` lists what is offered: `standard` (5,000 ₮ in Ulaanbaatar, 10,000 ₮ in the
aimags, free from 150,000 ₮), `express` (Ulaanbaatar only, same day, 12,000 ₮) and `pickup` (free, at `PICKUP_ADDRESS`).
`POST /checkout` rejects a method the address's zone does not offer (422 `shipping-unavailable`). Prices and the free
threshold are settings (`SHIPPING_*`, `FREE_SHIPPING_THRESHOLD_CENTS`).

## Known limits

* Stock is per product, not per size (the dataset has none). Listing and similar-product caches (60 s to 5 min) can show
  "in stock" briefly after the last unit was reserved.
* Google is the only external sign-in provider.
* Registration reveals whether an email exists (409); it is rate limited, and the alternative would need email verification.
* Emails go out only when `MAIL_MODE=smtp` is set up with a real provider (development uses Mailpit or the log). Bounces are not
  processed, and a message the mail server accepted is not tracked further.
* Refunds are always for the full amount, at the locked rate; returns are for the whole order, with no partial returns,
  exchanges or shipping labels. There are no discount codes or tax. Refunds go
  through whatever `PaymentGateway` is configured (offline in development); QPay refunds were not run in the sandbox.
* Reviews have no photos, "helpful" votes or replies, and cannot be reported by customers (only hidden by an administrator).
