# Mongolian glossary

One word per idea, in the web messages (`apps/web/messages/mn/*.json`), the API's Mongolian texts (errors, emails, SMS) and the
admin. `apps/web/src/i18n/glossary.test.ts` and `apps/api/tests/core/test_glossary.py` fail if a retired form comes back or an
English word is left in a Mongolian message (brands and standards such as Angel, Google, QPay, JPEG, MB are allowed).

| Idea | Use | Not |
| --- | --- | --- |
| Bag (cart) | Сагс | Тэрэг |
| Checkout / place the order | Захиалах | Төлбөр хийх (that is the payment step) |
| Wishlist | **Хадгалсан бараа** | Хүслийн жагсаалт |
| Search by photo | **Зургаар хайх** | Харагдацаар хайлт |
| Warehouse worker (the role) | **Агуулахын ажилтан** | |
| Quantity left, stock filters and alerts | **үлдэгдэл** | нөөц (kept only in «нөөц код», a recovery code) |
| Units sold but not yet shipped | **захиалагдсан** | захиалгад барьсан |
| Number counted in the warehouse | **агуулахад байгаа тоо** | тавиур дээрх тоо |
| Subtotal (goods without delivery) | **Барааны дүн** | Дэд дүн |
| Profile page | **Миний мэдээлэл** | Профайл |
| Authenticator app | **баталгаажуулагч апп** | Authenticator апп |
| A signed-in session | say **төхөөрөмж** («бусад төхөөрөмжөөс таныг гаргалаа») | нэвтрэлт дууслаа |
| Activity log (staff changes) | **Үйлдлийн журнал** | Лог |
| Overdue to ship | **Илгээх хугацаа хэтэрсэн** | Хоцорсон |
| Shipping queue | **Илгээх дараалал** | |
| Complete the look | **Хослуулах бараа** | Look |
| Quick add (card) | **Түргэн нэмэх** | |
| Buy again | **Дахин захиалах** | |
| Security activity (account) | **Аюулгүй байдлын үйлдэл** | Аюулгүйн лог |
| New device | **Шинэ төхөөрөмж** | |
| Product | Бараа | Бүтээгдэхүүн (except in code comments) |
| Customer | Хэрэглэгч | Үйлчлүүлэгч |
| Order status | Төлбөр хүлээгдэж байна · Төлөгдсөн · Илгээсэн · Хүргэгдсэн · Цуцлагдсан · **Төлбөр буцаагдсан** | Мөнгө буцаасан; plain «Буцаагдсан» (reads as returned goods) |
| Refund (action / event) | **Төлбөр буцаах** · Төлбөр буцаагдсан | Буцаан олгох, Мөнгө буцаах |
| Review | Сэтгэгдэл | Тойм |
| Sign in / out | Нэвтрэх / Гарах | Логин |
| Suspend an account | Түр хаах · сэргээх | Блоклох |
| Tracking number | **Илгээмжийн дугаар** | Хяналтын дугаар |
| Delivery address | **Хүргэлтийн хаяг** | Хүргэх хаяг |
| Usage / occasion (product attribute) | **Зориулалт** | Хэрэглээ |
| Next page | **Дараагийн** | Дараах |

## How to write

- Use everyday words. Instructions end in **-на уу / -үү** ("Нэр оруулна уу"), buttons are short verbs ("Хадгалах", "Болих").
  Marketing copy on the home page may be warmer (-аарай).
- An error says what happened and what to do next.
- Do not show technical words (session, slug, idempotency, model) to shoppers or staff.
- Never glue a case ending to a placeholder that holds a name or free text: it cannot fit every value. Write
  «Сагснаас хасах: {name}», not «{name}-ийг сагснаас хасах». Ordinals after a number («{number}-р хувцас») are fine.
- For "if this wasn't you" write «Хэрэв та өөрөө хийгээгүй бол», not «Хэрэв энэ та биш бол».
- A sign-in code SMS must stay within 70 characters: Cyrillic text is sent 70 characters to a segment, so one more
  character doubles the cost.
