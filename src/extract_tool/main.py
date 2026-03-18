"""
Extract Tool
============
Localiza arquivos ZIP/RAR numa pasta, descompacta-os, recolhe todos os
ficheiros das pastas extraídas numa única pasta temporária e, por fim,
move apenas os ficheiros .ttf para a pasta de destino escolhida.

Uso:
    uv run extract-tool run <origem> <destino>
    uv run extract-tool run ./downloads ./MinhasFontes

Opções:
    --work-dir   Pasta intermédia onde os arquivos são extraídos/reunidos
                 (por defeito: <origem>/_extracted_tmp)
    --keep-work  Não apagar a pasta de trabalho após a conclusão
    --dry-run    Mostra o que seria feito sem mover nada
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Annotated, Optional

import rarfile
import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)
from rich.table import Table
from rich import print as rprint

app = typer.Typer(
    name="extract-tool",
    help="Extrai ZIP/RAR e coleta arquivos .ttf para uma pasta destino.",
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_archive(path: Path) -> bool:
    """Retorna True se o arquivo for ZIP ou RAR."""
    return path.suffix.lower() in {".zip", ".rar"}


def _extract_archive(archive_path: Path, dest_dir: Path, console: Console) -> bool:
    """
    Extrai um arquivo ZIP ou RAR para dest_dir.
    Retorna True em caso de sucesso.
    """
    suffix = archive_path.suffix.lower()
    try:
        if suffix == ".zip":
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(dest_dir)
        elif suffix == ".rar":
            with rarfile.RarFile(archive_path, "r") as rf:
                rf.extractall(dest_dir)
        return True
    except Exception as exc:
        console.print(
            f"  [bold red]✗[/bold red] Erro ao extrair [yellow]{archive_path.name}[/yellow]: {exc}"
        )
        return False


def _collect_files(root: Path) -> list[Path]:
    """Retorna todos os ficheiros (recursivamente) dentro de root."""
    return [p for p in root.rglob("*") if p.is_file()]


def _move_ttf(src: Path, dest_dir: Path, dry_run: bool, console: Console) -> bool:
    """
    Move um ficheiro TTF para dest_dir.
    Se já existir um ficheiro com o mesmo nome, adiciona sufixo numérico.
    Retorna True se o movimento foi efectuado (ou seria efectuado em dry-run).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / src.name

    # Resolve conflitos de nome
    counter = 1
    while target.exists():
        target = dest_dir / f"{src.stem}_{counter}{src.suffix}"
        counter += 1

    if dry_run:
        console.print(
            f"  [dim][DRY-RUN][/dim] [cyan]{src.name}[/cyan] → [green]{target}[/green]"
        )
        return True

    try:
        shutil.move(str(src), target)
        console.print(
            f"  [bold green]✓[/bold green] [cyan]{src.name}[/cyan] → [green]{target}[/green]"
        )
        return True
    except Exception as exc:
        console.print(
            f"  [bold red]✗[/bold red] Falha ao mover [cyan]{src.name}[/cyan]: {exc}"
        )
        return False


# ---------------------------------------------------------------------------
# Comando principal
# ---------------------------------------------------------------------------

@app.command()
def run(
    origem: Annotated[
        Path,
        typer.Argument(
            help="Pasta de origem onde estão os arquivos ZIP/RAR.",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ],
    destino: Annotated[
        Path,
        typer.Argument(
            help="Pasta de destino onde os arquivos .ttf serão copiados.",
            resolve_path=True,
        ),
    ],
    work_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--work-dir",
            help="Pasta intermédia de extração (padrão: <origem>/_extracted_tmp).",
            resolve_path=True,
        ),
    ] = None,
    keep_work: Annotated[
        bool,
        typer.Option("--keep-work", help="Não apagar a pasta de trabalho no final."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Simula as operações sem mover arquivos."),
    ] = False,
) -> None:
    """
    [bold]Extrai[/bold] arquivos ZIP/RAR de [yellow]<origem>[/yellow] e move os
    [cyan].ttf[/cyan] encontrados para [green]<destino>[/green].
    """
    console.print(
        Panel.fit(
            "[bold cyan]Extract Tool[/bold cyan] — extrator de fontes TTF",
            subtitle="v0.1.0",
        )
    )

    # Pasta de trabalho
    work = work_dir or (origem / "_extracted_tmp")
    work.mkdir(parents=True, exist_ok=True)

    if dry_run:
        console.print("[bold yellow]⚠  Modo DRY-RUN activo — nenhum ficheiro será movido.[/bold yellow]\n")

    # ------------------------------------------------------------------
    # 1. Localizar arquivos compactados
    # ------------------------------------------------------------------
    archives = [p for p in origem.iterdir() if p.is_file() and _is_archive(p)]

    if not archives:
        console.print("[red]Nenhum arquivo ZIP ou RAR encontrado em:[/red]", origem)
        raise typer.Exit(1)

    console.print(f"\n[bold]📦 Arquivos encontrados:[/bold] {len(archives)}\n")

    # ------------------------------------------------------------------
    # 2. Extrair cada arquivo
    # ------------------------------------------------------------------
    extracted_ok: list[Path] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Extraindo arquivos…", total=len(archives))

        for archive in archives:
            extract_dest = work / archive.stem
            extract_dest.mkdir(parents=True, exist_ok=True)
            progress.update(task, description=f"Extraindo [yellow]{archive.name}[/yellow]…")

            if _extract_archive(archive, extract_dest, console):
                extracted_ok.append(extract_dest)

            progress.advance(task)

    console.print(f"\n[bold]📂 Extraídos com sucesso:[/bold] {len(extracted_ok)}/{len(archives)}\n")

    # ------------------------------------------------------------------
    # 3. Reunir todos os ficheiros numa única pasta intermédia
    # ------------------------------------------------------------------
    flat_dir = work / "_flat"
    flat_dir.mkdir(parents=True, exist_ok=True)

    all_files = _collect_files(work / "." )
    # Excluir ficheiros que já estão em _flat para evitar duplicação em re-execuções
    all_files = [f for f in all_files if flat_dir not in f.parents and f.parent != flat_dir]

    console.print(f"[bold]🗂  Total de ficheiros extraídos:[/bold] {len(all_files)}\n")

    # Contagem por extensão
    ext_count: dict[str, int] = {}
    for f in all_files:
        ext = f.suffix.lower() or "(sem extensão)"
        ext_count[ext] = ext_count.get(ext, 0) + 1

    table = Table(title="Ficheiros por tipo", show_lines=False, style="dim")
    table.add_column("Extensão", style="cyan")
    table.add_column("Quantidade", justify="right", style="bold")
    for ext, count in sorted(ext_count.items(), key=lambda x: -x[1]):
        table.add_row(ext, str(count))
    console.print(table)

    # ------------------------------------------------------------------
    # 4. Mover apenas .ttf para a pasta de destino
    # ------------------------------------------------------------------
    ttf_files = [f for f in all_files if f.suffix.lower() == ".ttf"]

    if not ttf_files:
        console.print("\n[yellow]Nenhum arquivo .ttf encontrado nos conteúdos extraídos.[/yellow]")
    else:
        console.print(f"\n[bold]🔤 Arquivos .ttf encontrados:[/bold] {len(ttf_files)}\n")
        moved = 0
        for ttf in ttf_files:
            if _move_ttf(ttf, destino, dry_run, console):
                moved += 1

        console.print(
            f"\n[bold green]✅ {moved}/{len(ttf_files)} arquivo(s) .ttf "
            f"{'seriam movidos' if dry_run else 'movidos'} para:[/bold green] [green]{destino}[/green]"
        )

    # ------------------------------------------------------------------
    # 5. Limpeza da pasta de trabalho (opcional)
    # ------------------------------------------------------------------
    if not keep_work and not dry_run:
        shutil.rmtree(work, ignore_errors=True)
        console.print(f"\n[dim]Pasta de trabalho removida: {work}[/dim]")
    elif keep_work:
        console.print(f"\n[dim]Pasta de trabalho mantida em: {work}[/dim]")

    console.print("\n[bold cyan]Concluído![/bold cyan] 🎉\n")


# ---------------------------------------------------------------------------
# Ponto de entrada directo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
