"""Generated SVG placeholder card — never a broken image (constraint C2).

Title set in large type on the card surface, correct aspect per kind.
Pure string templating: no imaging dependency, nothing to disk-cache.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

_SIZES = {"poster": (600, 900), "backdrop": (1280, 720)}


def _wrap(title: str, per_line: int) -> list[str]:
    words = title.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > per_line and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:6] or ["Untitled"]


def build_svg(title: str, kind: str = "poster") -> str:
    width, height = _SIZES.get(kind, _SIZES["poster"])
    per_line = 12 if kind == "poster" else 24
    lines = _wrap(title.strip() or "Untitled", per_line)

    longest = max(len(line) for line in lines)
    font_size = max(28, min(64, int(width * 1.6 / max(longest, 1))))
    line_height = int(font_size * 1.25)
    block_height = line_height * len(lines)
    start_y = (height - block_height) // 2 + font_size

    tspans = "".join(
        f'<tspan x="{width // 2}" y="{start_y + i * line_height}">{escape(line)}</tspan>'
        for i, line in enumerate(lines)
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
        f'<rect width="{width}" height="{height}" fill="#231A38"/>'
        f'<rect x="4" y="4" width="{width - 8}" height="{height - 8}" '
        f'fill="none" stroke="#362B52" stroke-width="2"/>'
        f'<text fill="#EFE9DF" font-family="Archivo, Arial Narrow, sans-serif" '
        f'font-size="{font_size}" font-weight="700" text-anchor="middle">{tspans}</text>'
        f"</svg>"
    )
