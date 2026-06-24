#!/usr/bin/env python3
"""Declarative style package loading for semantic diagrams."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STYLE_ROOT = ROOT / "styles"

HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
RGBA_RE = re.compile(
    r"^rgba\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(0|1|0?\.\d+)\s*\)$"
)


class StyleError(ValueError):
    """Raised when a diagram style package is missing or invalid."""


def _deep_get(data: dict[str, Any], path: str, default: Any = None) -> Any:
    cur: Any = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def _is_color(value: str) -> bool:
    return value == "none" or bool(HEX_RE.match(value) or RGBA_RE.match(value))


def _validate_color(name: str, value: object) -> None:
    if not isinstance(value, str) or not _is_color(value):
        raise StyleError(f"style color token {name!r} must be #RRGGBB, rgba(...), or none")


def _walk_color_tokens(prefix: str, value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _walk_color_tokens(f"{prefix}.{key}" if prefix else str(key), child)
        return
    _validate_color(prefix, value)


def validate_style_package(style: dict[str, Any], path: Path | None = None) -> None:
    where = f" in {path}" if path else ""
    if not isinstance(style.get("id"), str) or not style["id"].strip():
        raise StyleError(f"style package{where} requires non-empty id")
    if not isinstance(style.get("version"), str) or not style["version"].strip():
        raise StyleError(f"style package {style.get('id', '<unknown>')}{where} requires version")
    if not isinstance(style.get("tokens"), dict):
        raise StyleError(f"style package {style['id']}{where} requires tokens")
    if not isinstance(style.get("components"), dict):
        raise StyleError(f"style package {style['id']}{where} requires components")

    colors = _deep_get(style, "tokens.colors")
    if not isinstance(colors, dict):
        raise StyleError(f"style package {style['id']}{where} requires tokens.colors")
    for required in ("background", "text_primary", "text_secondary", "line_primary"):
        if required not in colors:
            raise StyleError(f"style package {style['id']}{where} missing color token {required}")
    _walk_color_tokens("tokens.colors", colors)

    metrics = style.get("metrics", {})
    if not isinstance(metrics, dict):
        raise StyleError(f"style package {style['id']}{where} metrics must be an object")
    for key, value in metrics.items():
        if not isinstance(value, (int, float)):
            raise StyleError(f"style package {style['id']}{where} metric {key} must be numeric")


def _style_path(style_ref: str, contract_path: Path | None = None) -> Path:
    if any(sep in style_ref for sep in ("/", "\\")) or style_ref.endswith(".json"):
        path = Path(style_ref)
        if path.is_absolute():
            return path
        base = contract_path.parent if contract_path else Path.cwd()
        return (base / path).resolve()
    return STYLE_ROOT / style_ref / "style.json"


def load_style_package(style_ref: object, contract_path: Path | None = None) -> dict[str, Any]:
    if not isinstance(style_ref, str) or not style_ref.strip():
        raise StyleError('contract must declare top-level "style"')
    path = _style_path(style_ref.strip(), contract_path)
    if not path.exists():
        raise StyleError(f"style package not found: {style_ref}")
    style = json.loads(path.read_text(encoding="utf-8-sig"))
    validate_style_package(style, path)
    out = copy.deepcopy(style)
    out["_path"] = str(path)
    return out


def style_id(style: dict[str, Any]) -> str:
    return str(style.get("id", "unknown"))


def metric(style: dict[str, Any], name: str, default: float | int) -> float | int:
    value = _deep_get(style, f"metrics.{name}", default)
    return value if isinstance(value, (int, float)) else default


def token(style: dict[str, Any], path: str, default: Any = None) -> Any:
    return _deep_get(style, path, default)


def color(style: dict[str, Any], value: object, default: str = "#64748B") -> str:
    if not isinstance(value, str) or not value:
        return default
    if _is_color(value):
        return value
    found = _deep_get(style, f"tokens.colors.{value}")
    if isinstance(found, str) and _is_color(found):
        return found
    return default


def paint(style: dict[str, Any], value: object, default: str = "#64748B") -> tuple[str, float | None]:
    raw = color(style, value, default)
    if raw == "none":
        return "none", None
    rgba = RGBA_RE.match(raw)
    if not rgba:
        return raw, None
    r, g, b = [max(0, min(255, int(v))) for v in rgba.groups()[:3]]
    opacity = max(0.0, min(1.0, float(rgba.group(4))))
    return f"#{r:02X}{g:02X}{b:02X}", opacity


def paint_attrs(
    style: dict[str, Any],
    attr: str,
    value: object,
    default: str = "#64748B",
    extra_opacity: float | None = None,
) -> str:
    paint_value, opacity = paint(style, value, default)
    attrs = [f'{attr}="{paint_value}"']
    opacities = [v for v in (opacity, extra_opacity) if v is not None]
    if opacities:
        final = 1.0
        for value in opacities:
            final *= float(value)
        attrs.append(f'{attr}-opacity="{final:.3g}"')
    return " ".join(attrs)


def kind_accent(style: dict[str, Any], kind: object) -> str:
    accents = _deep_get(style, "tokens.colors.accents", {})
    if isinstance(accents, dict):
        value = accents.get(str(kind or "object"), accents.get("object"))
        if isinstance(value, str):
            return color(style, value, "#64748B")
    return "#64748B"


def pale_for(style: dict[str, Any], accent: str) -> str:
    pale = _deep_get(style, "tokens.colors.pale", {})
    if isinstance(pale, dict) and accent in pale and isinstance(pale[accent], str):
        return color(style, pale[accent], "#F8FAFC")
    fallback = _deep_get(style, "components.icon.fill", "#F8FAFC")
    return color(style, fallback, "#F8FAFC")
