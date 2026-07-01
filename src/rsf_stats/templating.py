"""Shared Jinja2 templates instance + i18n-aware render helper."""

from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .translations import LANGS, translate

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


THEMES = ("dark", "light")


def current_lang(request: Request) -> str:
    """Resolve the UI language from `?lang=` then the `lang` cookie (default en)."""
    lang = request.query_params.get("lang") or request.cookies.get("lang") or "en"
    return lang if lang in LANGS else "en"


def current_theme(request: Request) -> str:
    """Resolve the theme from `?theme=` then the `theme` cookie (default dark)."""
    theme = request.query_params.get("theme") or request.cookies.get("theme") or "dark"
    return theme if theme in THEMES else "dark"


def render(request: Request, name: str, context: dict, *, status_code: int = 200) -> HTMLResponse:
    """Render a template with `t()`, `lang` and `theme` injected, persisting choices."""
    lang = current_lang(request)
    theme = current_theme(request)
    ctx = {
        **context,
        "lang": lang,
        "theme": theme,
        "t": lambda key: translate(key, lang),
    }
    response = templates.TemplateResponse(request, name, ctx, status_code=status_code)
    if request.query_params.get("lang") in LANGS:
        response.set_cookie("lang", lang, max_age=31536000, samesite="lax")
    if request.query_params.get("theme") in THEMES:
        response.set_cookie("theme", theme, max_age=31536000, samesite="lax")
    return response
