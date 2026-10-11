"""Output shaping for tool results.

Raw JSON dumps waste the model's context window and hide the signal. Every tool
returns summarised text, and when we cut something off we say so in Turkish so
the model knows the picture is incomplete.
"""

from __future__ import annotations

from typing import Final

DEFAULT_MAX_CHARS: Final = 4000
DEFAULT_MAX_LINES: Final = 200

_TRUNCATION_NOTE: Final = (
    "\n\n[... çıktı kırpıldı: toplam {total} {unit}, ilk {shown} {unit} gösteriliyor. "
    "Daha dar bir zaman aralığı veya filtre ile tekrar sorgulayın.]"
)


def summarize_output(
    text: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    max_lines: int = DEFAULT_MAX_LINES,
) -> str:
    """Trim a tool output and state explicitly that it was trimmed.

    Line limit is applied first (keeps whole lines readable), then the
    character limit as a hard ceiling.
    """
    lines = text.splitlines()
    if len(lines) > max_lines:
        kept = lines[:max_lines]
        body = "\n".join(kept)
        body += _TRUNCATION_NOTE.format(total=len(lines), shown=max_lines, unit="satır")
    else:
        body = text

    if len(body) > max_chars:
        body = body[:max_chars].rstrip()
        body += _TRUNCATION_NOTE.format(total=len(text), shown=max_chars, unit="karakter")

    return body


def format_table(rows: list[dict[str, object]], columns: list[str]) -> str:
    """Render rows as a compact pipe-separated table.

    Cheaper for the model to read than JSON and keeps column alignment stable.
    """
    if not rows:
        return "(sonuç yok)"

    widths = {column: len(column) for column in columns}
    rendered: list[list[str]] = []
    for row in rows:
        cells = [_cell(row.get(column)) for column in columns]
        for column, cell in zip(columns, cells, strict=True):
            widths[column] = max(widths[column], len(cell))
        rendered.append(cells)

    header = " | ".join(column.ljust(widths[column]) for column in columns)
    separator = "-+-".join("-" * widths[column] for column in columns)
    body = [
        " | ".join(cell.ljust(widths[column]) for column, cell in zip(columns, cells, strict=True))
        for cells in rendered
    ]
    return "\n".join([header, separator, *body])


def _cell(value: object) -> str:
    if value is None:
        return "-"
    return str(value).replace("\n", " ").strip()
