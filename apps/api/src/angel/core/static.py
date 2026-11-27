from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope


class MediaFiles(StaticFiles):
    """Барааны зургийн static файл: browser, CDN нэг өдөр cache хийж болно.

    Одоогийн production тохиргоонд ч API эдгээрийг өөрөө өгдөг (вэб `/media`-г дамжуулна). Дараа нь
    ижил key-тэй файлуудыг object storage/CDN руу шилжүүлж болно.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=86400"
        return response
