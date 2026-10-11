"""Command line interface for TraceHub.

Subcommands are registered here; each domain (knowledge base, database, ...)
lives in its own Typer sub-application.
"""

from __future__ import annotations

import typer

from tracehub_core import __version__
from tracehub_core.config import settings
from tracehub_core.logging import configure_logging

app = typer.Typer(
    name="tracehub",
    help="TraceHub - salt okunur DevOps teshis asistani.",
    no_args_is_help=True,
    add_completion=False,
)


def _register_subcommands() -> None:
    """Attach domain sub-apps.

    Imported lazily so that ``tracehub_core`` never depends on higher level
    packages at import time.
    """
    from tracehub_kb.cli import app as kb_app

    app.add_typer(kb_app)


_register_subcommands()


@app.callback()
def main() -> None:
    """Initialise logging before any subcommand runs."""
    configure_logging()


@app.command()
def version() -> None:
    """Surum bilgisini gosterir."""
    typer.echo(f"TraceHub {__version__}")


@app.command()
def info() -> None:
    """Etkin yapilandirmayi ozetler (sir icermez)."""
    typer.echo(f"Ortam            : {settings.env}")
    typer.echo(f"Log seviyesi     : {settings.log_level}")
    typer.echo(f"Veritabani       : {_mask_dsn(settings.database_url)}")
    typer.echo(f"LLM saglayici    : {settings.llm.provider} ({settings.llm.model})")
    typer.echo(f"Embedding        : {settings.embedding.provider} ({settings.embedding.model})")
    typer.echo(f"Bilgi tabani     : {settings.kb.resolved_root()}")


def _mask_dsn(dsn: str) -> str:
    """Hide credentials in a database URL before printing it."""
    if "@" not in dsn:
        return dsn
    scheme_sep = "://"
    if scheme_sep not in dsn:
        return "***"
    scheme, rest = dsn.split(scheme_sep, 1)
    _, host = rest.rsplit("@", 1)
    return f"{scheme}{scheme_sep}***@{host}"
