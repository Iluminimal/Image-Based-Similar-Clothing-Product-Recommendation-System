"""Cookie ашигладаг endpoint-уудыг cross-site хүсэлтээс хамгаална.

Bearer token ашигладаг endpoint-д CSRF-ийн аюул байхгүй, учир нь browser тэр header-ийг өөрөө
хавсаргадаггүй. Харин refresh болон зочны сагсны cookie автоматаар дагалддаг. Тиймээс тэдгээрээр юм
өөрчлөх хүсэлт заавал манай сайтаас ирсэн байх ёстой.

SameSite=Lax ихэнх тохиолдлыг хаадаг. Энэ шалгалт бол хоёр дахь хамгаалалт: `Origin` нь манайх биш
browser хүсэлтийг татгалзана. Browser биш client (curl, серверийн код) эдгээр header-ийг илгээдэггүй
тул зөвшөөрнө: халдагч тэднийг ашиглан хохирогчийн cookie-г илгээж чадахгүй.
"""

from fastapi import Request

from angel.core.config import Settings
from angel.core.errors import FORBIDDEN_ORIGIN_TYPE, ProblemError

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _forbidden() -> ProblemError:
    return ProblemError(
        403,
        "Хүсэлтийг хүлээж авсангүй",
        "Аюулгүй байдлын үүднээс энэ хүсэлтийг хаалаа. Хуудсаа дахин ачаалаад оролдоно уу.",
        type_=FORBIDDEN_ORIGIN_TYPE,
    )


async def require_same_origin(request: Request) -> None:
    if request.method in _SAFE_METHODS:
        return
    settings: Settings = request.app.state.settings
    origin = request.headers.get("origin")
    if origin is not None:
        if origin not in settings.cors_origins:
            raise _forbidden()
        return
    # Origin header байхгүй бол (хуучин browser-ийн same-origin хүсэлт) Fetch Metadata header-ээс
    # шалгана.
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise _forbidden()
