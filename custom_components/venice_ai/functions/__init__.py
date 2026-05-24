"""Venice AI custom functions package."""
from __future__ import annotations

from .base import Function
from .bash import BashFunction
from .composite import CompositeFunction
from .file import EditFileFunction, ReadFileFunction, WriteFileFunction
from .native import NativeFunction
from .script import ScriptFunction
from .sqlite import SqliteFunction
from .template import TemplateFunction
from .web import RestFunction, ScrapeFunction
from ..exceptions import FunctionNotFound

FUNCTIONS: dict[str, Function] = {
    "native": NativeFunction(),
    "template": TemplateFunction(),
    "script": ScriptFunction(),
    "rest": RestFunction(),
    "scrape": ScrapeFunction(),
    "bash": BashFunction(),
    "read_file": ReadFileFunction(),
    "write_file": WriteFileFunction(),
    "edit_file": EditFileFunction(),
    "sqlite": SqliteFunction(),
    "composite": CompositeFunction(),
}


def get_function(function_type: str) -> Function:
    """Return the Function instance for the given type string."""
    if function_type not in FUNCTIONS:
        raise FunctionNotFound(function_type)
    return FUNCTIONS[function_type]


__all__ = [
    "Function",
    "FUNCTIONS",
    "get_function",
    "NativeFunction",
    "TemplateFunction",
    "ScriptFunction",
    "RestFunction",
    "ScrapeFunction",
    "BashFunction",
    "ReadFileFunction",
    "WriteFileFunction",
    "EditFileFunction",
    "SqliteFunction",
    "CompositeFunction",
]
