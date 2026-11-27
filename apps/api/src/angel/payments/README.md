# `payments`: төлбөрийн gateway

Service-үүд зөвхөн `gateway.py`-ийн интерфейсийг мэднэ.

- `qpay_gateway.py` — QPay (QR төлбөр).
- `offline.py` — жинхэнэ мөнгө авдаггүй туршилтын gateway (хөгжүүлэлт, тест). Production-д хориотой.
- `factory.py` — тохиргооноос хамаарч нэгийг нь сонгоно.

Төлбөрийг захиалгатай тулгах дүрэм бүх provider-т ижил: `services/commerce/payments.py`.

**Шинэ provider нэмэх:** интерфейсийг хэрэгжүүлж, `factory.py` ба тохиргоонд нэмнэ. Provider нь
мэдэгдэл (webhook) илгээдэг бол түүнд тусдаа route хэрэгтэй. Мэдэгдэлд шууд итгэхгүй: төлбөрийг
provider-оос асууж баталгаажуулна.
