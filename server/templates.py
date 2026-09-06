"""Minimal Jinja-like template renderer for the dashboard.

Supports:
  - {{ var }} → context value (escaped)
  - {% raw NAME %} ... {% endraw %} → unescaped block named NAME
  - {% for x in items %} ... {% endfor %}
  - {% if cond %} ... {% endif %}

Kept dependency-free; full Jinja is overkill for the small set of pages
the dashboard needs. Blocks let the route handler inject rendered lists
without losing HTML escaping for variables.
"""

import re
from html import escape

from server.config import SITE_ROOT

_BLOCK_RE = re.compile(r"{%\s*raw\s+(\w+)\s*%}(.*?){%\s*endraw\s*%}", re.DOTALL)
_FOR_RE = re.compile(
    r"{%\s*for\s+(\w+)\s+in\s+(\w+)\s*%}(.*?){%\s*endfor\s*%}", re.DOTALL
)
_IF_RE = re.compile(
    r"{%\s*if\s+(\w+)\s*%}(.*?){%\s*endif\s*%}", re.DOTALL
)


def _substitute_vars(text: str, context: dict) -> str:
    def repl(match):
        key = match.group(1)
        if key not in context:
            return ""
        return escape(str(context[key]))
    return re.sub(r"{{\s*(\w+)\s*}}", repl, text)


def _render_loops(text: str, context: dict) -> str:
    def repl(match):
        var, items_name, body = match.group(1), match.group(2), match.group(3)
        items = context.get(items_name)
        if not items:
            return ""
        out = []
        for item in items:
            item_ctx = dict(context)
            item_ctx[var] = item
            out.append(_substitute_vars(body, item_ctx))
        return "".join(out)
    return _FOR_RE.sub(repl, text)


def _render_ifs(text: str, context: dict) -> str:
    def repl(match):
        key, body = match.group(1), match.group(2)
        return body if context.get(key) else ""
    return _IF_RE.sub(repl, text)


def _render_blocks(text: str, context: dict) -> str:
    def repl(match):
        key, body = match.group(1), match.group(2)
        value = context.get(key)
        if value is None:
            return ""
        return str(value)
    return _BLOCK_RE.sub(repl, text)


def render_site_page(filename, **context) -> str:
    page = (SITE_ROOT / filename).read_text()
    page = _render_blocks(page, context)
    page = _render_loops(page, context)
    page = _render_ifs(page, context)
    page = _substitute_vars(page, context)
    return page
