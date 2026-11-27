"""Орчны хувьсагчаас уншдаг бүх тохиргоо.

`APP_ENV=prod` үед туршилтын горим (fake, offline, console) сонгосон эсвэл нууц утга дутуу бол апп
асахгүй. Шинэ тохиргоо нэмбэл `.env.example`-ийг хамт шинэчилнэ.
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    # API-г үргэлж apps/api folder-оос асаана (Makefile-ийг үзнэ үү). Repo-ийн үндсэн .env-ийг API
    # болон docker compose хоёул уншдаг. apps/api/.env заавал биш: түүнд бичсэн утга үндсэн
    # .env-ийнхийг дарна.
    model_config = SettingsConfigDict(
        env_file=("../../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["dev", "test", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = True

    api_v1_prefix: str = "/api/v1"
    # Орчны хувьсагчид таслалаар тусгаарлана: CORS_ORIGINS=http://localhost:3000,https://shop.example
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    database_url: str = "postgresql+asyncpg://angel:angel@localhost:5433/angel"
    redis_url: str = "redis://localhost:6379/0"

    # Барааны жижиг зураг (thumbnail). LocalStorage энд бичиж, API `media_url_path` хаягаар өгнө.
    # Харьцангуй замыг apps/api folder-оос тооцно (API үргэлж тэндээс ажилладаг).
    media_dir: Path = Path("../../data/media")
    media_url_path: str = "/media"
    media_base_url: str = "http://localhost:8000/media"

    # FashionCLIP. `embedding_resize_mode` болон model revision өөрчлөгдвөл embedding-ийн утга
    # өөрчлөгдөнө. Тиймээс аль нэгийг солибол бүх барааг дахин embed хийх ёстой (ingest үүнийг
    # анзаарна).
    # `fake` бол CI-ийн end-to-end тестэд зориулсан хиймэл model. Юу ч татахгүй, хувцас таньдаггүй
    # тул production-д хориотой.
    embedder: Literal["fashion-clip", "fake"] = "fashion-clip"
    embedding_device: Literal["auto", "mps", "cpu", "cuda"] = "auto"
    embedding_fp16: bool = False
    embedding_resize_mode: Literal["crop", "pad"] = "pad"

    # Хувцасны хэсэг олох хэрэгсэл (localizer):
    # - `yolo`: Fashionpedia дээр fine-tune хийсэн YOLOv8m. Зураг дээрх хувцас, гутал, цүнхийг тусад
    #   нь олно. Хэрэглэгчийн сонгосон хэсгээр хайна.
    # - `whole`: хэсэг олохгүй, бүтэн зургаар хайна (detector-ийг харьцуулах суурь).
    # - `fake`: CI-ийн end-to-end тестэд зориулсан. Зургийг дээд, доод хоёр хуваагаад "олсон" гэж
    #   үзнэ. Production-д хориотой.
    localizer: Literal["yolo", "whole", "fake"] = "yolo"
    localizer_device: Literal["auto", "mps", "cpu", "cuda"] = "auto"
    # Detection-ийн итгэлийн доод хязгаар, нэг зурагт буцаах хэсгийн дээд тоо, хайрцгийн хамгийн
    # бага талбай (зургийн хувиар), хайрцгийг томруулах хувь.
    yolo_confidence: float = Field(default=0.25, gt=0.0, lt=1.0)
    yolo_max_regions: int = Field(default=5, ge=1, le=20)
    yolo_min_area: float = Field(default=0.01, ge=0.0, lt=1.0)
    yolo_padding: float = Field(default=0.05, ge=0.0, le=0.5)

    # --- хайлт ----------------------------------------------------------------------------
    # Оруулсан файлыг хэмжээ, зарласан төрөл, жинхэнэ формат, pixel-ийн тоогоор нь шалгана
    # (decompression bomb-оос хамгаална).
    max_upload_bytes: int = 8 * 1024 * 1024
    max_upload_pixels: int = 25_000_000
    # Клиент `limit` зааж өгөөгүй үед буцаах үр дүнгийн тоо.
    search_default_limit: int = 24
    # Hybrid хайлтад текстийн embedding-ийн жин (зургийн жин нь 1-ээс үүнийг хассантай тэнцүү).
    # Хэмжилтийн дүн docs/search-api.md-д: 0.5 үед өнгө бараг өөрчлөгддөггүй, ~0.75-аас их бол
    # хувцасны төрөл алдагдана.
    hybrid_text_weight: float = 0.65
    # Зургаар хайхад хэдэн zero-shot ангиллын таамаг буцаах вэ.
    detected_categories: int = 3

    # Redis cache. Key бүрд embedding version ордог тул дахин embed хийхэд хуучин cache
    # ашиглагдахгүй.
    text_embedding_cache_ttl_seconds: int = 24 * 3600
    similar_cache_ttl_seconds: int = 300
    catalog_filters_cache_ttl_seconds: int = 600

    # Rate limit-ийг client бүрт "<хүсэлтийн тоо>/<хугацаа секундээр>" гэж бичнэ. Тогтмол цонхоор
    # тоолж, Redis-д хадгална.
    rate_limit_enabled: bool = True
    rate_limit_prefix: str = "rl"
    rate_limit_image: str = "20/60"
    # Камерын live preview секундэд 2-3 кадр илгээдэг. Үүнийг хайлтаас тусад нь тоолно: тэгэхгүй бол
    # live preview хайлтын хязгаарыг дуусгана.
    rate_limit_detect: str = "300/60"
    rate_limit_text: str = "60/60"
    rate_limit_similar: str = "120/60"
    # Итгэж болох reverse proxy-ийн ард байвал client-ийн хаягийг X-Forwarded-For-ийн эхний утгаас
    # авна.
    trust_proxy_headers: bool = False

    # --- нэвтрэлт -------------------------------------------------------------------------
    # Access token-ы гарын үсгийн түлхүүр (HS256). Prod орчинд заавал өгнө (32+ тэмдэгт). Бусад
    # орчинд хоосон бол процесс асах бүрд шинэ түлхүүр үүсэх тул restart хийхэд бүх хэрэглэгч гарна.
    jwt_secret: str = ""
    access_token_ttl_seconds: int = 15 * 60
    refresh_token_ttl_days: int = 30
    # Админ, агуулахын ажилтан энэ хугацаанд идэвхгүй байвал нэвтрэлт нь дуусна (ердийн
    # хэрэглэгчийнхээс богино).
    staff_refresh_ttl_hours: int = 12
    # Refresh болон зочны сагсны cookie. Prod орчинд Secure заавал асаалттай. Dev орчин энгийн http
    # дээр ажиллана.
    cookie_secure: bool = False
    rate_limit_register: str = "5/3600"
    rate_limit_login: str = "10/300"
    rate_limit_login_email: str = "5/300"
    # Нэг email-д өдрийн хязгаар бас бий. Энэ нь нууц үгийг удаанаар таах оролдлогыг зогсооно.
    # Хязгаарт хүрвэл account-ын эзэнд мэдэгдэнэ.
    rate_limit_login_email_daily: str = "20/86400"
    rate_limit_refresh: str = "60/60"
    rate_limit_admin: str = "120/60"
    rate_limit_oauth: str = "30/300"
    rate_limit_review: str = "20/3600"
    rate_limit_order_request: str = "10/3600"
    # Нэг client-ээс код авах, оруулах оролдлогын хязгаар. Нэг утас эсвэл email-ийн хязгаарыг
    # `otp_resend_seconds`, `otp_max_sends_per_hour`, `otp_max_attempts` тогтооно.
    rate_limit_otp_send: str = "10/600"
    rate_limit_otp_verify: str = "30/600"
    # Төлбөр шалгах хүсэлтийн хязгаар ("Төлбөрөө шалгах" товч, QPay-ийн мэдэгдэл). Шалгах бүрд
    # provider руу хүсэлт явдаг.
    rate_limit_payment_check: str = "30/60"
    # Browser-ийн CSP зөрчлийн мэдээллийн хязгаар. Нэвтрэлтгүй endpoint тул хэт олон мэдээлэл
    # log-ийг дүүргэхээс сэргийлнэ.
    rate_limit_csp_report: str = "30/60"

    # --- нэг удаагийн код (утас/email-ээр нэвтрэх, баталгаажуулах, солих, нууц үг сэргээх) -
    otp_ttl_seconds: int = 300
    otp_max_attempts: int = 5
    otp_resend_seconds: int = 60
    otp_max_sends_per_hour: int = 5
    # End-to-end тест, demo-д зориулсан: утга өгвөл бүх код энэ утгатай болно. Prod орчинд хориотой.
    # Хоосон бол код санамсаргүй гарна.
    otp_dev_code: str = ""
    # True бол ажилтан хоёр шатлалт нэвтрэлт тохируулах хүртэл back-office-ийн API-г ашиглаж
    # чадахгүй. `APP_ENV=prod` үед үргэлж True.
    staff_2fa_required: bool = False
    # Улсын кодгүй бичсэн дугаарыг энэ улсынх гэж үзнэ (ISO 3166 alpha-2).
    default_phone_region: str = "MN"
    # `console`: SMS-г API log-д бичнэ (хөгжүүлэлт). `twilio`: Twilio-оор илгээнэ.
    sms_mode: Literal["console", "twilio"] = "console"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    # `console`: имэйлийг API log-д бичнэ. `smtp`: SMTP серверээр илгээнэ (dev-д Mailpit,
    # `make infra`; UI http://localhost:8025).
    mail_mode: Literal["console", "smtp"] = "console"
    smtp_host: str = ""
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = False
    mail_from: str = ""

    # --- Google-ээр нэвтрэх ---------------------------------------------------------------
    # `google`: жинхэнэ урсгал (client id, secret хэрэгтэй). `fake`: тест, CI-д зориулсан хиймэл
    # хувилбар. Google руу хандалгүй, `login_hint`-д заасан хүнийг нэвтрүүлнэ. Prod орчинд хориотой.
    oauth_mode: Literal["google", "fake"] = "google"
    google_client_id: str = ""
    google_client_secret: str = ""
    # Энэ хаягийг Google console-д бүртгэнэ. Энэ нь вэбийн хаяг, харин Next /api/v1-ийг API руу
    # дамжуулна. Тиймээс callback-ийн тавьсан session cookie first-party болно.
    google_redirect_uri: str = "http://localhost:3000/api/v1/auth/google/callback"
    # Callback дууссаны дараа browser-ийг энэ сайт руу буцаана (амжилтгүй бол /login руу).
    web_base_url: str = "http://localhost:3000"

    # --- сагс ба checkout -----------------------------------------------------------------
    cart_max_quantity: int = 10
    cart_max_lines: int = 50
    cart_guest_ttl_days: int = 30
    # Дэлгүүрийн үндсэн (ба цорын ганц) валют. Үнэ бүгд бага нэгжээр (төгрөг x 100) хадгалагдана.
    currency: str = "MNT"
    # Хүргэлтийн үнэ (төгрөг x 100): Улаанбаатарт энгийн, шуурхай (өдөртөө), орон нутагт энгийн.
    shipping_standard_ub_cents: int = 500_000
    shipping_express_ub_cents: int = 1_200_000
    shipping_standard_rural_cents: int = 1_000_000
    # Энэ дүнгээс дээш бол энгийн хүргэлт үнэгүй (шуурхай хүргэлтэд үйлчлэхгүй).
    free_shipping_threshold_cents: int = 15_000_000
    # Дэлгүүрээс авах цэг: checkout-д харагдана, үнэгүй.
    pickup_address: str = "Улаанбаатар, Сүхбаатар дүүрэг, 1-р хороо, Бага тойруу 1"
    # Захиалга үүсэхэд барааг нөөцөлнө; төлөхгүй бол энэ хугацааны дараа бараа чөлөөлөгдөнө.
    order_pending_ttl_minutes: int = 30
    order_sweep_interval_seconds: int = 60
    # Төлбөр буцаалт амжилтгүй болбол sweep энэ хугацааны дараа дахин оролдоно. Ингэснээр provider
    # руу минут тутам хандахгүй. Харин шинэ мэдэгдэл ирэх эсвэл "Төлбөрөө шалгах" дарахад хүлээлгүй
    # оролдоно.
    refund_retry_minutes: int = 15
    # Үлдэгдэл нь энэ тоо ба түүнээс бага барааг самбарууд "үлдэгдэл багатай" гэж тооцно.
    low_stock_threshold: int = 5
    # Төлөгдсөнөөс хойш энэ цагаас удаан илгээгдээгүй захиалгыг агуулахын самбар
    # "хугацаа хэтэрсэн" гэж тэмдэглэнэ.
    ship_sla_hours: int = 24
    # Хүргэгдсэнээс (дэлгүүрээс авснаас) хойш буцаах хүсэлт гаргах хоног. Дэлгүүрийн бодлого:
    # нийтлэхээс өмнө хэрэглэгчийн эрхийн хууль тогтоомжтой тулгана.
    return_window_days: int = Field(default=14, ge=1, le=365)
    # Dashboard, тайлан, агуулахын самбар дээрх "өнөөдөр" хаанаас эхлэхийг энэ цагийн бүс тогтооно
    # (IANA нэр).
    shop_timezone: str = "Asia/Ulaanbaatar"

    # --- мэдэгдлийн имэйлийн дараалал ба хуучин өгөгдөл --------------------------------------
    # Outbox-ийн worker энэ хугацаа тутам шинэ болон дахин оролдох имэйлийг хайна.
    outbox_poll_seconds: float = Field(default=5, gt=0)
    # Хуучин өгөгдөл цэвэрлэгч хэдий хугацаа тутам ажиллах вэ. Доорх хадгалах хугацаануудыг дэлгүүр
    # өөрөө тогтооно.
    housekeeping_interval_seconds: int = Field(default=3600, ge=60)
    # Нэг удаагийн кодын бичлэгийг хэдэн цаг хадгалах вэ. Илгээх хязгаар сүүлийн 1 цагийг тоолдог
    # тул 2-оос бага байж болохгүй.
    otp_retention_hours: int = Field(default=24, ge=2)
    # Хугацаа нь дууссан refresh token-ыг хэдэн хоног хадгалах вэ (IP, төхөөрөмжийн мэдээлэл
    # агуулдаг).
    refresh_token_retention_days: int = Field(default=30, ge=1)
    # Аюулгүй байдлын үйл явдлыг хэдэн хоног хадгалах вэ. Танил төхөөрөмжийг ч ийм хугацаанд санана.
    security_event_retention_days: int = Field(default=180, ge=30)
    email_sent_retention_days: int = Field(default=7, ge=1)
    email_failed_retention_days: int = Field(default=30, ge=1)

    # --- төлбөр ---------------------------------------------------------------------------
    # `qpay`: QPay-ийн QR төлбөр (dev-д sandbox). `offline`: QPay-гүйгээр бүх урсгалыг турших хиймэл
    # gateway (апп дотроо ажиллана). Prod орчинд хориотой.
    payments_mode: Literal["qpay", "offline"] = "qpay"
    qpay_base_url: str = "https://merchant-sandbox.qpay.mn"
    qpay_client_id: str = ""
    qpay_client_secret: str = ""
    qpay_invoice_code: str = ""
    # QPay төлбөрийн дараа энэ хаягаар API руу мэдэгдэнэ: интернетээс хандах боломжтой байх ёстой
    # (локалд ngrok/cloudflared tunnel). Мэдэгдэл ирэхгүй бол худалдан авагч "Төлбөрөө шалгах"-аар
    # баталгаажуулна.
    qpay_callback_base_url: str = "http://localhost:8000"

    # Kaggle dataset-ийн байрлал (styles.csv + images/). Зөвхөн ingestion-д хэрэгтэй.
    dataset_dir: Path | None = None

    # /readyz дахь нэг dependency шалгалтын дээд хугацаа.
    readiness_timeout_seconds: float = 2.0
    # Cache, rate limit-ийн Redis дуудлага богино timeout-той: Redis удаашрахад хайлт удаашрах
    # ёсгүй.
    redis_op_timeout_seconds: float = 0.5

    @property
    def google_enabled(self) -> bool:
        return self.oauth_mode == "fake" or bool(
            self.google_client_id and self.google_client_secret
        )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("otp_dev_code")
    @classmethod
    def _dev_code_shape(cls, value: str) -> str:
        if value and not (len(value) == 6 and value.isdigit()):
            raise ValueError("OTP_DEV_CODE must be six digits")
        return value

    @field_validator("shop_timezone")
    @classmethod
    def _known_time_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError(f"SHOP_TIMEZONE is not a known time zone: {value!r}") from error
        return value

    @property
    def shop_zone(self) -> ZoneInfo:
        return ZoneInfo(self.shop_timezone)

    @field_validator("default_phone_region")
    @classmethod
    def _region_shape(cls, value: str) -> str:
        if len(value) != 2 or not value.isalpha():
            raise ValueError("DEFAULT_PHONE_REGION must be a two-letter country code")
        return value.upper()

    @model_validator(mode="after")
    def _check_production(self) -> "Settings":
        if self.jwt_secret and len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        if self.mail_mode == "smtp" and not (self.smtp_host and self.mail_from):
            raise ValueError("SMTP_HOST and MAIL_FROM are required when MAIL_MODE=smtp")
        if self.app_env == "prod":
            if not self.jwt_secret:
                raise ValueError("JWT_SECRET is required when APP_ENV=prod")
            if self.embedder != "fashion-clip":
                raise ValueError("EMBEDDER=fake is not allowed when APP_ENV=prod")
            if self.localizer == "fake":
                raise ValueError("LOCALIZER=fake is not allowed when APP_ENV=prod")
            if self.payments_mode != "qpay":
                raise ValueError("PAYMENTS_MODE=offline is not allowed when APP_ENV=prod")
            if self.oauth_mode != "google":
                raise ValueError("OAUTH_MODE=fake is not allowed when APP_ENV=prod")
            if self.otp_dev_code:
                raise ValueError("OTP_DEV_CODE is not allowed when APP_ENV=prod")
            if self.sms_mode != "twilio":
                raise ValueError("SMS_MODE=console is not allowed when APP_ENV=prod")
            if not (self.twilio_account_sid and self.twilio_auth_token and self.twilio_from_number):
                raise ValueError(
                    "TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER are required "
                    "when SMS_MODE=twilio"
                )
            if not (self.qpay_client_id and self.qpay_client_secret and self.qpay_invoice_code):
                raise ValueError(
                    "QPAY_CLIENT_ID, QPAY_CLIENT_SECRET and QPAY_INVOICE_CODE are required in prod"
                )
            if "sandbox" in self.qpay_base_url:
                raise ValueError("QPAY_BASE_URL must not point at the QPay sandbox in prod")
            if self.mail_mode != "smtp":
                raise ValueError("MAIL_MODE=console is not allowed when APP_ENV=prod")
            self.cookie_secure = True
            self.staff_2fa_required = True
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
