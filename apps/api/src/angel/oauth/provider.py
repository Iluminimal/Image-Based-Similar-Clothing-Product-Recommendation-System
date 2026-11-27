from dataclasses import dataclass
from typing import Protocol


class OAuthError(Exception):
    """Provider-ийн хариунд итгэх эсвэл түүнийг ашиглах боломжгүй үеийн алдаа. `reason` бол login
    хуудасны таньдаг кодуудын нэг ("google_failed", "google_unverified"). Өөр юу ч харуулахгүй."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(detail or reason)
        self.reason = reason


@dataclass(frozen=True)
class OAuthProfile:
    subject: str
    email: str
    email_verified: bool
    name: str | None
    # Provider ашиглаж болохуйц зураг өгсөн бол хэрэглэгчийн зургийн https URL.
    picture: str | None = None


class OAuthProvider(Protocol):
    name: str

    def authorization_url(
        self, *, state: str, nonce: str, code_challenge: str, login_hint: str | None
    ) -> str:
        """Нэвтрэхийн тулд browser-ийг илгээх хаяг."""
        ...

    async def exchange(self, *, code: str, code_verifier: str, nonce: str) -> OAuthProfile:
        """Authorization code-оор хэн нэвтэрснийг тогтооно. `OAuthError` шидэж болно."""
        ...
