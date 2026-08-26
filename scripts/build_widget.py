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


def minify_js(js: str) -> str:
    js = re.sub(r"//.*?\n", "\n", js)
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.DOTALL)
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
