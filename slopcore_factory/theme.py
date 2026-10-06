"""Theme loading.

A theme is a small JSON preset (palette, type, treatment) plus the vendored web
fonts it needs. One theme ships today, ``broadside``, extracted verbatim from
``please-continue-video``.
"""

from __future__ import annotations

import json
from pathlib import Path

from .errors import ConfigError
from .logging_setup import get_logger
from .models import Theme

log = get_logger("theme")

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
FONTS_DIR = TEMPLATES_DIR / "fonts"


def load_theme(name: str = "broadside") -> Theme:
    """Load ``theme_<name>.json`` from the packaged templates."""
    path = TEMPLATES_DIR / f"theme_{name}.json"
    if not path.exists():
        raise ConfigError(f"unknown theme: {name} ({path})")
    data = json.loads(path.read_text(encoding="utf-8"))
    scrim = data.get("scrim", {})
    fonts = {str(k): str(v) for k, v in data.get("fonts", {}).items()}
    for filename in fonts.values():
        if not (FONTS_DIR / filename).exists():
            raise ConfigError(f"theme {name} references missing font: {filename}")
    theme = Theme(
        name=data["name"],
        bg=data["bg"],
        accent=data["accent"],
        cream=data["cream"],
        font_display=data["font_display"],
        font_body=data["font_body"],
        font_mono=data["font_mono"],
        fonts={k: v for k, v in data.get("fonts", {}).items()},
        grain_opacity=float(data.get("grain_opacity", 0.06)),
        scrim_top=scrim.get("top", "rgba(17, 17, 17, 0)"),
        scrim_bottom=scrim.get("bottom", "rgba(17, 17, 17, 0.72)"),
        scrim_stop=scrim.get("stop", "38%"),
        line_size=float(data.get("line_size", 5.6)),
        word_size=float(data.get("word_size", 12.0)),
        letter_spacing=float(data.get("letter_spacing", -0.02)),
    )
    log.info("loaded theme %r", theme.name)
    return theme


def font_css(theme: Theme) -> str:
    """``@font-face`` rules referencing the vendored fonts by relative path."""
    lines: list[str] = []
    for weight, filename in theme.fonts.items():
        if weight.startswith("mono"):
            family, css_weight = theme.font_mono, weight.replace("mono", "") or "500"
        else:
            family, css_weight = theme.font_display, weight
        lines.append(
            f'      @font-face {{ font-family: "{family}"; font-weight: {css_weight}; '
            f'src: url("assets/fonts/{filename}") format("woff2"); }}'
        )
    return "\n".join(lines)


def resolve_font_path(theme: Theme, filename: str) -> Path:
    return FONTS_DIR / filename
