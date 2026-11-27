# `core`: нийтлэг суурь

Аль нэг хэсэгт хамаарахгүй, бүх давхарга ашигладаг код.

| Сэдэв | Файл |
| --- | --- |
| Тохиргоо | `config.py` (шинэ тохиргоо нэмбэл `.env.example`-ийг хамт шинэчилнэ) |
| Service угсрах, эрх шалгах | `deps.py` |
| Алдааны хэлбэр (RFC 7807) | `errors.py` |
| Нууц үг, token, 2FA | `security.py`, `passwords.py`, `totp.py`, `secret_box.py` |
| Хүсэлтийн хамгаалалт | `rate_limit.py`, `csrf.py`, `cookies.py`, `uploads.py`, `security_headers.py` |
| Имэйл, SMS | `mail.py`, `sms.py` |
| Хаяг, утас, мөнгө, цаг | `mongolia.py` (аймаг, дүүрэг), `phone.py`, `money.py`, `shop_time.py` |
| Log | `logging.py`, `request_context.py` |

Дэлгүүрийн дүрмийг энд биш, `services/`-д бичнэ.
