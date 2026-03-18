"""
Extract Tool
============
Localiza arquivos ZIP/RAR numa pasta, descompacta-os, recolhe todos os
ficheiros das pastas extraídas numa única pasta temporária e, por fim,
move arquivos de fonte (.ttf, .otf, .woff, .woff2, .eot, .fon) para a
pasta de destino escolhida. Além disso, varre todas as sub-pastas na
raiz de <origem> em busca de fontes avulsas.

Uso:
    uv run extract-tool run <origem> <destino>
    uv run extract-tool run ./downloads ./MinhasFontes
    uv run extract-tool run ./downloads ./MinhasFontes --install
    uv run extract-tool run ./downloads ./MinhasFontes --install-windows-wsl

Opções:
    --work-dir            Pasta intermédia onde os arquivos são extraídos/reunidos
                          (por defeito: <origem>/_extracted_tmp)
    --keep-work           Não apagar a pasta de trabalho após a conclusão
    --dry-run             Mostra o que seria feito sem mover nada
    --install             Instala as fontes no sistema operativo nativo após movê-las
    --install-windows-wsl Instala as fontes no Windows anfitrião a partir do WSL
                          (usa powershell.exe para copiar e registar sem precisar de Admin)
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
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
    help="Extrai ZIP/RAR e coleta arquivos de fonte (TTF, OTF…) para uma pasta destino.",
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()

# Extensões de arquivo de fonte suportadas
FONT_EXTENSIONS: frozenset[str] = frozenset({
    ".ttf",
    ".otf",
    ".woff",
    ".woff2",
    ".eot",
    ".fon",
})


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


def _move_font(src: Path, dest_dir: Path, dry_run: bool, console: Console) -> bool:
    """
    Move um arquivo de fonte para dest_dir.
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


def _install_fonts(font_dir: Path, dry_run: bool, console: Console) -> None:
    """
    Instala todas as fontes presentes em font_dir no sistema operativo.

    - Linux:   copia para ~/.local/share/fonts/ e executa fc-cache -fv
    - macOS:   copia para ~/Library/Fonts/
    - Windows: copia para C:\Windows\Fonts\ e registra no registro
    """
    system = platform.system()
    font_files = [f for f in font_dir.rglob("*") if f.is_file() and f.suffix.lower() in FONT_EXTENSIONS]

    if not font_files:
        console.print("[yellow]Nenhuma fonte encontrada para instalar.[/yellow]")
        return

    console.print(f"\n[bold]🖥  Instalando {len(font_files)} fonte(s) no sistema ({system})…[/bold]\n")

    if system == "Linux":
        install_dir = Path.home() / ".local" / "share" / "fonts"
        install_dir.mkdir(parents=True, exist_ok=True)
        installed = 0
        for font in font_files:
            target = install_dir / font.name
            if dry_run:
                console.print(f"  [dim][DRY-RUN][/dim] instalaria [cyan]{font.name}[/cyan] → [green]{target}[/green]")
                installed += 1
                continue
            try:
                shutil.copy2(font, target)
                console.print(f"  [bold green]✓[/bold green] [cyan]{font.name}[/cyan] → [green]{target}[/green]")
                installed += 1
            except Exception as exc:
                console.print(f"  [bold red]✗[/bold red] Falha ao instalar [cyan]{font.name}[/cyan]: {exc}")

        if not dry_run and installed:
            console.print("\n[dim]Atualizando cache de fontes (fc-cache -fv)…[/dim]")
            try:
                subprocess.run(["fc-cache", "-fv"], check=True, capture_output=True)
                console.print("[bold green]✓[/bold green] Cache de fontes atualizado.")
            except FileNotFoundError:
                console.print("[yellow]⚠  fc-cache não encontrado. Execute manualmente: fc-cache -fv[/yellow]")
            except subprocess.CalledProcessError as exc:
                console.print(f"[red]Erro ao atualizar cache: {exc}[/red]")

    elif system == "Darwin":  # macOS
        install_dir = Path.home() / "Library" / "Fonts"
        install_dir.mkdir(parents=True, exist_ok=True)
        installed = 0
        for font in font_files:
            target = install_dir / font.name
            if dry_run:
                console.print(f"  [dim][DRY-RUN][/dim] instalaria [cyan]{font.name}[/cyan] → [green]{target}[/green]")
                installed += 1
                continue
            try:
                shutil.copy2(font, target)
                console.print(f"  [bold green]✓[/bold green] [cyan]{font.name}[/cyan] → [green]{target}[/green]")
                installed += 1
            except Exception as exc:
                console.print(f"  [bold red]✗[/bold red] Falha ao instalar [cyan]{font.name}[/cyan]: {exc}")

    elif system == "Windows":
        import ctypes
        import winreg  # type: ignore[import]

        fonts_dir = Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts"
        reg_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
        installed = 0

        try:
            reg_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path, 0, winreg.KEY_SET_VALUE)
        except OSError:
            console.print(
                "[bold red]✗ Permissão negada ao registro do Windows.[/bold red] "
                "Execute o terminal como Administrador."
            )
            return

        for font in font_files:
            target = fonts_dir / font.name
            if dry_run:
                console.print(f"  [dim][DRY-RUN][/dim] instalaria [cyan]{font.name}[/cyan] → [green]{target}[/green]")
                installed += 1
                continue
            try:
                shutil.copy2(font, target)
                # Registrar no registro para que o Windows reconheça imediatamente
                winreg.SetValueEx(reg_key, font.stem, 0, winreg.REG_SZ, font.name)
                console.print(f"  [bold green]✓[/bold green] [cyan]{font.name}[/cyan] → [green]{target}[/green]")
                installed += 1
            except Exception as exc:
                console.print(f"  [bold red]✗[/bold red] Falha ao instalar [cyan]{font.name}[/cyan]: {exc}")

        winreg.CloseKey(reg_key)

        if not dry_run and installed:
            # Notificar o sistema sobre a mudança de fontes
            try:
                HWND_BROADCAST = 0xFFFF
                WM_FONTCHANGE = 0x001D
                ctypes.windll.user32.SendMessageW(HWND_BROADCAST, WM_FONTCHANGE, 0, 0)  # type: ignore[attr-defined]
                console.print("[bold green]✓[/bold green] Sistema notificado sobre novas fontes.")
            except Exception:
                pass

    else:
        console.print(f"[yellow]⚠  Sistema operativo '{system}' não suportado para instalação automática.[/yellow]")
        console.print("[dim]Copie os arquivos de fonte manualmente para a pasta de fontes do sistema.[/dim]")
        return

    label = "seriam instaladas" if dry_run else "instaladas"
    console.print(f"\n[bold green]✅ Fontes {label} com sucesso em {install_dir if system != 'Windows' else fonts_dir}[/bold green]")


def _install_fonts_windows_from_wsl(font_dir: Path, dry_run: bool, console: Console) -> None:
    """
    Instala fontes no Windows anfitrião a partir do WSL.

    Estratégia (sem necessidade de privilégios de Administrador):
      1. Resolve o caminho Windows de %LOCALAPPDATA% via `powershell.exe`.
      2. Converte-o para um caminho WSL via `wslpath`.
      3. Copia os arquivos de fonte para <LOCALAPPDATA>\Microsoft\Windows\Fonts.
      4. Regista cada fonte em HKCU via um script PowerShell inline.
      5. Envia WM_FONTCHANGE a todas as janelas via PowerShell.
    """
    font_files = [
        f for f in font_dir.rglob("*")
        if f.is_file() and f.suffix.lower() in FONT_EXTENSIONS
    ]

    if not font_files:
        console.print("[yellow]Nenhuma fonte encontrada para instalar no Windows.[/yellow]")
        return

    console.print(
        f"\n[bold]🪟  Instalando {len(font_files)} fonte(s) no Windows (via WSL interop)…[/bold]\n"
    )

    # --- 1. Obter %LOCALAPPDATA% do Windows via powershell.exe ---
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             "[System.Environment]::GetFolderPath('LocalApplicationData')"],
            capture_output=True, text=True, check=True,
        )
        win_local_app_data = result.stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        console.print(
            f"[bold red]✗[/bold red] Não foi possível chamar powershell.exe: {exc}\n"
            "[dim]Verifique se o WSL interop está activado (WSLInterop=true).[/dim]"
        )
        return

    # --- 2. Converter para caminho WSL via wslpath ---
    try:
        wsl_result = subprocess.run(
            ["wslpath", win_local_app_data],
            capture_output=True, text=True, check=True,
        )
        local_app_data = Path(wsl_result.stdout.strip())
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        console.print(f"[bold red]✗[/bold red] Erro ao converter caminho com wslpath: {exc}")
        return

    win_fonts_dir = local_app_data / "Microsoft" / "Windows" / "Fonts"
    win_fonts_dir.mkdir(parents=True, exist_ok=True)

    # --- 3. Copiar fontes ---
    installed: list[str] = []
    for font in font_files:
        target = win_fonts_dir / font.name
        if dry_run:
            console.print(
                f"  [dim][DRY-RUN][/dim] instalaria [cyan]{font.name}[/cyan] "
                f"→ [green]{win_fonts_dir / font.name}[/green]"
            )
            installed.append(font.name)
            continue
        try:
            shutil.copy2(font, target)
            console.print(
                f"  [bold green]✓[/bold green] [cyan]{font.name}[/cyan] "
                f"→ [green]{target}[/green]"
            )
            installed.append(font.name)
        except Exception as exc:
            console.print(f"  [bold red]✗[/bold red] Falha ao copiar [cyan]{font.name}[/cyan]: {exc}")

    if not installed:
        return

    if dry_run:
        console.print(
            f"\n[bold green]✅ {len(installed)} fonte(s) seriam instaladas no Windows.[/bold green]"
        )
        return

    # --- 4. Registar em HKCU e notificar o Windows via PowerShell ---
    # Monta um script PS que regista todas as fontes e envia WM_FONTCHANGE
    reg_lines = "\n".join(
        f'  Set-ItemProperty -Path $regPath -Name "{f}" -Value "{f}"'
        for f in installed
    )
    ps_script = f"""
$regPath = 'HKCU:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Fonts'
If (-not (Test-Path $regPath)) {{ New-Item -Path $regPath -Force | Out-Null }}
{reg_lines}
$code = @'
[System.Runtime.InteropServices.DllImport("user32.dll")]
public static extern int SendMessage(int hWnd, int Msg, int wParam, int lParam);
'@
$user32 = Add-Type -MemberDefinition $code -Name 'User32' -Namespace 'Win32' -PassThru
$user32::SendMessage(0xFFFF, 0x001D, 0, 0) | Out-Null
"""

    try:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps_script],
            check=True, capture_output=True,
        )
        console.print("[bold green]✓[/bold green] Fontes registadas no Windows e sistema notificado.")
    except subprocess.CalledProcessError as exc:
        console.print(
            f"[yellow]⚠  Fontes copiadas, mas falha no registo: {exc.stderr.decode(errors='replace').strip()}[/yellow]"
        )

    console.print(
        f"\n[bold green]✅ {len(installed)}/{len(font_files)} fonte(s) instaladas em "
        f"{win_fonts_dir}[/bold green]"
    )


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
    install: Annotated[
        bool,
        typer.Option(
            "--install",
            help="Instala as fontes no sistema nativo após movê-las para o destino.",
        ),
    ] = False,
    install_windows_wsl: Annotated[
        bool,
        typer.Option(
            "--install-windows-wsl",
            help="(WSL) Instala as fontes no Windows anfitrião via powershell.exe, sem precisar de Admin.",
        ),
    ] = False,
) -> None:
    """
    [bold]Extrai[/bold] arquivos ZIP/RAR de [yellow]<origem>[/yellow] e move as
    fontes ([cyan].ttf, .otf, .woff, .woff2, .eot, .fon[/cyan]) para [green]<destino>[/green].
    Com [bold]--install[/bold] instala no sistema nativo; com [bold]--install-windows-wsl[/bold]
    instala no Windows anfitrião a partir do WSL (sem Admin).
    """
    console.print(
        Panel.fit(
            "[bold cyan]Extract Tool[/bold cyan] — extrator de fontes TTF/OTF",
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
    # 4. Mover arquivos de fonte para a pasta de destino
    # ------------------------------------------------------------------
    font_files = [f for f in all_files if f.suffix.lower() in FONT_EXTENSIONS]

    if not font_files:
        console.print("\n[yellow]Nenhum arquivo de fonte encontrado nos conteúdos extraídos.[/yellow]")
    else:
        console.print(f"\n[bold]🔤 Arquivos de fonte encontrados:[/bold] {len(font_files)}\n")
        moved = 0
        for font in font_files:
            if _move_font(font, destino, dry_run, console):
                moved += 1

        console.print(
            f"\n[bold green]✅ {moved}/{len(font_files)} arquivo(s) de fonte "
            f"{'seriam movidos' if dry_run else 'movidos'} para:[/bold green] [green]{destino}[/green]"
        )

    # ------------------------------------------------------------------
    # 5. Varrer sub-pastas na raiz de <origem> em busca de fontes avulsas
    # ------------------------------------------------------------------
    root_subdirs = [p for p in origem.iterdir() if p.is_dir() and p != work]

    if root_subdirs:
        console.print(
            f"\n[bold]🔍 A varrer {len(root_subdirs)} sub-pasta(s) na raiz de origem "
            "em busca de arquivos de fonte…[/bold]\n"
        )

        extra_fonts: list[Path] = [
            f
            for subdir in root_subdirs
            for f in subdir.rglob("*")
            if f.is_file() and f.suffix.lower() in FONT_EXTENSIONS
        ]

        if not extra_fonts:
            console.print(
                "[yellow]Nenhum arquivo de fonte encontrado nas sub-pastas da origem.[/yellow]"
            )
        else:
            console.print(
                f"[bold]🔤 Arquivos de fonte encontrados nas sub-pastas:[/bold] {len(extra_fonts)}\n"
            )
            extra_moved = 0
            for font in extra_fonts:
                if _move_font(font, destino, dry_run, console):
                    extra_moved += 1

            console.print(
                f"\n[bold green]✅ {extra_moved}/{len(extra_fonts)} arquivo(s) de fonte extra(s) "
                f"{'seriam movidos' if dry_run else 'movidos'} para:[/bold green] "
                f"[green]{destino}[/green]"
            )

    # ------------------------------------------------------------------
    # 6. Instalar fontes (opcional)
    # ------------------------------------------------------------------
    if install:
        _install_fonts(destino, dry_run, console)

    if install_windows_wsl:
        _install_fonts_windows_from_wsl(destino, dry_run, console)

    # ------------------------------------------------------------------
    # 7. Limpeza da pasta de trabalho (opcional)
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
