"""`ultralytics`-ийг import хийхэд `PIL.Image.open`-ийг сольдог. Дараа нь танихгүй файл таарвал
ажиллаж байхдаа package суулгах гэж оролдоно. Танихгүй хүний upload үүнд хүрэх ёсгүй.

Тусдаа interpreter-т ажиллуулна: сольсон эсэх нь тухайн process-д юуг түрүүлж import хийснээс
хамаарна."""

import json
import os
import subprocess
import sys
from pathlib import Path

PROBE = """
import json

from PIL import Image

pil_open = Image.open

from angel.ml.preprocess import InvalidImageError, load_image
from angel.ml.yolo import import_ultralytics

import_ultralytics()

import ultralytics.utils
from ultralytics.utils import checks


def refuse(*args, **kwargs):
    raise RuntimeError("tried to install a package")


checks.check_requirements = refuse  # алдаатай хувилбар энд ч юу ч суулгахгүй

try:
    load_image(b"not a picture" * 20, formats=("JPEG", "PNG", "WEBP"))
    outcome = "accepted"
except InvalidImageError:
    outcome = "invalid image"
except Exception as error:
    outcome = f"{type(error).__name__}: {error}"

print(
    json.dumps(
        {
            "autoinstall": ultralytics.utils.AUTOINSTALL,
            "pil_open_is_pillows": Image.open is pil_open,
            "unreadable_file": outcome,
        }
    )
)
"""


def test_loading_the_detector_library_leaves_uploads_alone(tmp_path: Path) -> None:
    env = {key: value for key, value in os.environ.items() if key != "YOLO_AUTOINSTALL"}
    env |= {"YOLO_CONFIG_DIR": str(tmp_path), "PIP_NO_INDEX": "1", "UV_OFFLINE": "1"}

    done = subprocess.run(  # noqa: S603 - өөрийн interpreter, тогтмол script
        [sys.executable, "-c", PROBE],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout.strip().splitlines()[-1]) == {
        "autoinstall": False,
        "pil_open_is_pillows": True,
        "unreadable_file": "invalid image",
    }
