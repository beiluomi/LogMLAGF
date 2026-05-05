"""LogHetero command-line interface (entry point: `loghetero`)."""

from __future__ import annotations

import sys

import typer
from rich.console import Console

from loghetero import __version__

app = typer.Typer(
    name="loghetero",
    help="LogHetero: HTGN-LM co-pretraining for APT detection on provenance graphs.",
    no_args_is_help=True,
    add_completion=False,
)

console = Console()


@app.command()
def hello() -> None:
    """Print version and environment info as a Phase 0 smoke check."""
    console.print(f"[bold cyan]LogHetero[/bold cyan] v{__version__}")
    console.print(f"Python: {sys.version.split()[0]}")
    try:
        import torch

        console.print(
            f"PyTorch: {torch.__version__} | " f"CUDA available: {torch.cuda.is_available()}"
        )
        if torch.cuda.is_available():
            console.print(f"  Device count: {torch.cuda.device_count()}")
            for i in range(torch.cuda.device_count()):
                console.print(f"  [{i}] {torch.cuda.get_device_name(i)}")
    except ImportError:
        console.print(
            "[yellow]PyTorch not installed (Phase 0 dev env)."
            " Run `make sync-ml` to install the ML stack.[/yellow]"
        )


@app.command()
def version() -> None:
    """Print the LogHetero package version."""
    console.print(__version__)


def main() -> None:
    """Entry point used by `python -m loghetero.cli`."""
    app()


if __name__ == "__main__":
    main()
