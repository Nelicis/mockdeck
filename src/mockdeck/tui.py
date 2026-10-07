"""Rich Terminal User Interface — Startup banner and live traffic logging."""

from __future__ import annotations
import datetime
from typing import Any
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

default_console = Console()

METHOD_COLORS = {
    "GET": "bold cyan",
    "POST": "bold green",
    "PUT": "bold yellow",
    "PATCH": "bold magenta",
    "DELETE": "bold red",
    "OPTIONS": "dim white",
}


def print_startup_banner(
    host: str,
    port: int,
    resources: dict[str, int],
    delay: str | int | float = 0,
    chaos: float = 0.0,
    read_only: bool = False,
    console: Console | None = None,
) -> None:
    """Renders the startup dashboard panel and resource endpoints table."""
    con = console or default_console
    url = f"http://{host}:{port}"

    delay_str = "disabled"
    if delay:
        delay_str = f"{delay}ms" if isinstance(delay, (int, float)) and delay > 0 else (str(delay) if str(delay) != "0" else "disabled")

    chaos_str = f"{int(chaos * 100)}%" if chaos > 0 else "disabled"
    mode_str = "Read-Only (Mutations Blocked)" if read_only else "Read / Write (Persistence Active)"

    # Config summary table
    config_table = Table.grid(padding=(0, 2))
    config_table.add_column("Key", style="bold dim")
    config_table.add_column("Val", style="bold white")
    config_table.add_row("Server Address:", f"[bold cyan]{url}[/bold cyan]")
    config_table.add_row("Access Mode:", mode_str)
    config_table.add_row("Latency Delay:", delay_str)
    config_table.add_row("Chaos Faults:", chaos_str)

    # Resources table
    res_table = Table(
        title="[bold]Discovered API Resources[/bold]",
        title_justify="left",
        show_header=True,
        header_style="bold magenta",
        expand=True,
    )
    res_table.add_column("Resource", style="cyan", no_wrap=True)
    res_table.add_column("Records", justify="right", style="green")
    res_table.add_column("Endpoint", style="dim underline")

    if resources:
        for res, count in sorted(resources.items()):
            res_table.add_row(res, f"{count} items", f"{url}/{res}")
    else:
        res_table.add_row("(empty)", "0 items", f"{url}/")

    panel = Panel(
        res_table,
        title="[bold yellow]mockdeck v0.1.0[/bold yellow] — Instant Mock REST API",
        subtitle="[dim]Press Ctrl+C to stop the server[/dim]",
        border_style="bright_blue",
    )

    con.print()
    con.print(config_table)
    con.print(panel)
    con.print()


def log_request(
    method: str,
    path: str,
    status: int,
    duration_ms: float,
    client_ip: str = "127.0.0.1",
    console: Console | None = None,
) -> None:
    """Prints a styled log line for an incoming HTTP request."""
    con = console or default_console
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")

    # Method badge
    method_style = METHOD_COLORS.get(method.upper(), "bold white")
    method_badge = f"[{method_style}]{method.upper():<7}[/{method_style}]"

    # Status badge
    if 200 <= status < 300:
        status_badge = f"[bold green]{status}[/bold green]"
    elif 300 <= status < 400:
        status_badge = f"[bold cyan]{status}[/bold cyan]"
    elif 400 <= status < 500:
        status_badge = f"[bold yellow]{status}[/bold yellow]"
    else:
        status_badge = f"[bold red]{status}[/bold red]"

    duration_str = f"[dim]{duration_ms:6.1f}ms[/dim]"
    path_str = f"[white]{path}[/white]"

    line = f"[dim]{timestamp}[/dim]  {method_badge} {status_badge}  {duration_str}  {path_str}"
    con.print(line, highlight=False)
