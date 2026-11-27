"""API-ийн хариу бүрд аюулгүй байдлын header (CSP, nosniff, frame хориг, HTTPS дээр HSTS) нэмнэ."""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_HEADERS = {
    # API зөвхөн JSON, зураг буцаадаг. Browser-ийг агуулгын төрлийг өөрөө таахыг зөвшөөрөхгүй.
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    # API-ийн хариуг хэзээ ч frame-д оруулахгүй.
    "X-Frame-Options": "DENY",
    # Өөр сайт манай зураг, JSON-ийг шууд ашиглахаас сэргийлнэ (вэб өөрийн origin-оос авдаг).
    "Cross-Origin-Resource-Policy": "same-site",
    "Permissions-Policy": (
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), microphone=(), "
        "payment=(), usb=()"
    ),
}
# API нь JSON, зураг л буцаадаг: script, style, frame хэрэггүй.
_CSP = "default-src 'none'; frame-ancestors 'none'"
# Зөвхөн HTTPS дээр (Secure cookie-тэй адил): http дээрх dev орчинд browser үүнийг тооцохгүй.
_HSTS = "max-age=63072000; includeSubDomains"


class SecurityHeadersMiddleware:
    def __init__(
        self, app: ASGIApp, *, hsts: bool = False, docs_paths: tuple[str, ...] = ()
    ) -> None:
        """`docs_paths` дахь Swagger UI-д CSP тавихгүй (тэр CDN-ээс script, style ачаалдаг)."""
        self.app = app
        self._hsts = hsts
        self._docs_paths = docs_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_docs = scope["path"] in self._docs_paths

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in _HEADERS.items():
                    headers.setdefault(name, value)
                if not is_docs:
                    headers.setdefault("Content-Security-Policy", _CSP)
                if self._hsts:
                    headers.setdefault("Strict-Transport-Security", _HSTS)
            await send(message)

        await self.app(scope, receive, send_with_headers)
