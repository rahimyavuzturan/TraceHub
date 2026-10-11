"""Knowledge base CLI commands (``tracehub kb ...``)."""

from __future__ import annotations

from pathlib import Path

import typer

from tracehub_core import messages
from tracehub_core.config import settings
from tracehub_kb.loader import load_directory

app = typer.Typer(
    name="kb",
    help="Bilgi tabani komutlari.",
    no_args_is_help=True,
    add_completion=False,
)


@app.command()
def validate(
    root: Path = typer.Option(  # noqa: B008 - Typer option factory
        None,
        "--root",
        help="Bilgi tabani klasoru (varsayilan: ayarlardaki knowledge/).",
    ),
) -> None:
    """Dokumanlarin frontmatter yapisini dogrular."""
    target = root or settings.kb.resolved_root()
    result = load_directory(target)

    for error in result.errors:
        typer.secho(error.format(root=target), fg=typer.colors.RED, err=True)

    if result.errors:
        typer.secho(
            messages.KB_VALIDATION_FAILED.format(count=len(result.errors)),
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    typer.secho(
        messages.KB_VALIDATION_OK.format(count=len(result.documents)),
        fg=typer.colors.GREEN,
    )


@app.command("list")
def list_documents(
    root: Path = typer.Option(  # noqa: B008 - Typer option factory
        None,
        "--root",
        help="Bilgi tabani klasoru.",
    ),
    doc_type: str = typer.Option(None, "--type", help="Tipe gore filtrele."),
) -> None:
    """Dogrulanmis dokumanlari listeler."""
    target = root or settings.kb.resolved_root()
    result = load_directory(target)

    documents = [
        document
        for document in result.documents
        if doc_type is None or document.doc_type.value == doc_type
    ]
    for document in documents:
        aliases = ", ".join(document.frontmatter.aliases) or "-"
        typer.echo(f"{document.doc_type.value:9} {document.slug:28} {document.title}")
        typer.echo(f"{'':9} takma adlar: {aliases}")

    typer.echo(f"\nToplam: {len(documents)} dokuman")
    if result.errors:
        typer.secho(
            f"Uyari: {len(result.errors)} dokuman hatali, listede yok. "
            "'tracehub kb validate' calistirin.",
            fg=typer.colors.YELLOW,
            err=True,
        )
