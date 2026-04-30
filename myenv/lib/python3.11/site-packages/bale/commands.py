from __future__ import annotations
from typing import Union

class Command:
    __slots__ = (
        "_callback",
        "name",
        "usage",
        "params"
    )

