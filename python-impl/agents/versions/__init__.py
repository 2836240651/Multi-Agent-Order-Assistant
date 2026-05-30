"""agents/versions：三版本独立 build 函数（v1/v2/v3）。W5 落地。"""
from .v1 import build_v1
from .v2 import build_v2
from .v3 import build_v3

GRAPHS = {"v1": build_v1, "v2": build_v2, "v3": build_v3}

__all__ = ["GRAPHS", "build_v1", "build_v2", "build_v3"]
