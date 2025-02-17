# pylint: disable=missing-module-docstring, unused-argument
from typing import Literal, TypeAlias

from cv2.typing import MatLike
from PIL import Image

_OutputType: TypeAlias = Literal["string"]

def image_to_string(
    image: str | Image.Image | MatLike,
    lang: str = ...,
    config: str = ...,
    nice: int = ...,
    output_type: _OutputType = ...,
    timeout: int = ...,
) -> str: ...
