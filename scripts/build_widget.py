#!/usr/bin/env python3
"""Build script for the Peekaboo chat widget.

Bundles widget.html, styles.css, and pboo.js into a single minified
pboo.bundle.js file so the widget loads via a single HTTP request.
"""
import re
from pathlib import Path

WIDGET_DIR = Path(__file__).parent.parent / "server" / "widget"


def read_file(name: str) -> str:
    return (WIDGET_DIR / name).read_text()


def minify_css(css: str) -> str:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    css = re.sub(r"\s+", " ", css)
    css = re.sub(r"([{}:;,])\s*", r"\1", css)
    css = re.sub(r"\s*([{}:;,])", r"\1", css)
    return css.strip()


def strip_js_comments(js: str) -> str:
    """Remove // and /* */ comments while leaving string literals intact.

    A naive regex like ``re.sub(r"//.*?\n", ...)`` treats the ``//`` inside a
    literal such as ``"http://localhost:8000/widget/"`` as a comment start and
    chops the rest of the line, which breaks the bundle. Track quotes so that
    ``//`` and ``/*`` are only treated as comments outside strings.
    """
    out: list[str] = []
    i = 0
    n = len(js)
    while i < n:
        ch = js[i]
        nxt = js[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "/":
            while i < n and js[i] != "\n":
                i += 1
            continue
        if ch == "/" and nxt == "*":
            i += 2
            while i + 1 < n and not (js[i] == "*" and js[i + 1] == "/"):
                i += 1
            i += 2
            continue
        if ch in "\"'`":
            quote = ch
            out.append(ch)
            i += 1
            while i < n:
                ch = js[i]
                out.append(ch)
                if ch == "\\" and i + 1 < n:
                    i += 1
                    out.append(js[i])
                elif ch == quote:
                    i += 1
                    break
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def minify_js(js: str) -> str:
    js = strip_js_comments(js)
    js = re.sub(r"\n\s*\n", "\n", js)
    js = re.sub(r"\s+", " ", js)
    js = re.sub(r"(;)\s*", r"\1", js)
    js = re.sub(r"\s*(;)\s*", r"\1 ", js)
    js = re.sub(r"\s*(\{)\s*", r"\1", js)
    js = re.sub(r"\s*(\})\s*", r"\1", js)
    js = re.sub(r"\s*(\))\s*", r"\1", js)
    js = re.sub(r"\s*(\()\s*", r"\1", js)
    js = re.sub(r"\s*(\,)\s*", r"\1", js)
    js = re.sub(r"\s*(\=)\s*", r"\1", js)
    js = re.sub(r"\s*(\+)\s*", r"\1", js)
    js = re.sub(r"\s*(\.)\s*", r"\1", js)
    js = re.sub(r"(?<!.)\s+", " ", js)
    lines = js.split("\n")
    js = "\n".join(lines)
    for _ in range(3):
        js = js.replace("  ", " ")
    return js.strip()


def build():
    html = read_file("widget.html")
    css = read_file("styles.css")
    js = read_file("pboo.js")

    markup = html.strip()
    minified_css = minify_css(css)

    bundle = f"/* Peekaboo chat widget */\n"
    bundle += f"const WIDGET_MARKUP = {repr(markup)};\n"
    bundle += f"const WIDGET_STYLES = {repr(minified_css)};\n\n"

    for line in js.split("\n"):
        stripped = line.strip()
        if stripped.startswith("fetch(new URL(\"widget.html\""):
            continue
        if stripped.startswith("fetch(new URL(\"styles.css\""):
            continue
        if "markupResponse" in stripped or "stylesResponse" in stripped:
            continue
        if stripped.startswith("if (!markupResponse.ok"):
            continue
        if stripped.startswith("createWidget(") and "await markupResponse" in stripped:
            bundle += "  createWidget(siteId, WIDGET_MARKUP, WIDGET_STYLES);\n"
            continue
        if "await markupResponse.text()" in stripped or "await stylesResponse.text()" in stripped:
            continue
        if stripped.startswith("async function loadWidget"):
            bundle += "function loadWidget(siteId) {\n"
            continue
        bundle += line + "\n"

    output = minify_js(bundle)
    output_path = WIDGET_DIR / "pboo.bundle.js"
    output_path.write_text(output)
    print(f"Built {output_path} ({len(output)} bytes)")


if __name__ == "__main__":
    build()
