#!/usr/bin/env python3
"""Claude hook shim for the shared commit-message validator."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".loswf"
    / "tools"
    / "loswf_commit_message.py"
)


def _load():
    spec = importlib.util.spec_from_file_location(
        "loswf_commit_message_shared", MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_MODULE = _load()
globals().update(
    {
        name: getattr(_MODULE, name)
        for name in dir(_MODULE)
        if not name.startswith("__")
    }
)


if __name__ == "__main__":
    sys.exit(_MODULE.main())
