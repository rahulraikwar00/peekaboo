from html import escape

from server.config import SITE_ROOT


def render_site_page(filename, **context):
    page = (SITE_ROOT / filename).read_text()
    for key, value in context.items():
        page = page.replace("{{ " + key + " }}", escape(str(value), quote=True))
    return page
