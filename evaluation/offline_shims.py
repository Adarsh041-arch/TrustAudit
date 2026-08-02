"""Pre-import shim: stub out heavy/calling deps so we can run V1 graph offline.

Used by measure_v1_baseline.py when GOOGLE_API_KEY is not set.
Stubs out langchain_google_genai so app.vlm can be imported without
real credentials.
"""
from __future__ import annotations

import sys
import types


def install_offline_shims() -> None:
    if "langchain_google_genai" in sys.modules:
        return

    mod = types.ModuleType("langchain_google_genai")

    class _StubChat:
        def __init__(self, *args, **kwargs):
            self._args = args
            self._kwargs = kwargs

        def invoke(self, messages):
            class _R:
                content = "{}"
            return _R()

    mod.ChatGoogleGenerativeAI = _StubChat  # type: ignore[attr-defined]
    sys.modules["langchain_google_genai"] = mod
