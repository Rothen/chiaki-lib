"""Re-export of the compiled `chiaki_lib._native.core` submodule as a real package, so that
`chiaki_lib.core.common` and `chiaki_lib.core.log` can be imported like any other module."""

from . import (
    common,
    log,
)

__all__ = [
    "common",
    "log",
]
