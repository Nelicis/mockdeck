"""Command Line Interface for mockdeck — Init and Serve commands."""

from __future__ import annotations
import argparse
import json
import os
import sys
from typing import Sequence

from rich.console import Console
from rich.panel import Panel

from mockdeck import __version__
from mockdeck.server import create_server
from mockdeck.store import DataStore
from mockdeck.tui import log_request, print_startup_banner

console = Console()

STARTER_DATA = {
    "users": [
        {"id": 1, "name": "Alice Johnson", "email": "alice@example.com", "role": "admin"},
        {"id": 2, "name": "Bob Smith", "email": "bob@example.com", "role": "editor"},
        {"id": 3, "name": "Charlie Brown", "email": "charlie@example.com", "role": "viewer"},
    ],
    "posts": [
        {"id": 1, "title": "Getting Started with mockdeck", "userId": 1, "published": True},
        {"id": 2, "title": "Building Modern REST APIs", "userId": 2, "published": True},
        {"id": 3, "title": "Draft Article", "userId": 1, "published": False},
    ],
    "products": [
        {"id": 1, "name": "Wireless Mouse", "price": 29.99, "inStock": True},
        {"id": 2, "name": "Mechanical Keyboard", "price": 89.99, "inStock": True},
        {"id": 3, "name": "4K Monitor", "price": 349.99, "inStock": False},
    ],
}


def cmd_init(args: argparse.Namespace) -> int:
    """Creates a starter mock JSON dataset."""
    target_path = os.path.abspath(args.file)
    if os.path.exists(target_path):
        console.print(f"[bold red]Error:[/bold red] File already exists: [yellow]{target_path}[/yellow]")
        console.print("[dim]Use a different filename or delete the existing file first.[/dim]")
        return 1

    try:
        dir_name = os.path.dirname(target_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(STARTER_DATA, f, indent=2, ensure_ascii=False)

        panel = Panel(
            f"[bold green]Success![/bold green] Starter dataset created at:\n"
            f"[cyan]{target_path}[/cyan]\n\n"
            f"[bold]To start serving your mock API, run:[/bold]\n"
            f"  [yellow]mockdeck serve {os.path.basename(target_path)}[/yellow]",
            title="mockdeck init",
            border_style="green",
        )
        console.print(panel)
        return 0
    except OSError as e:
        console.print(f"[bold red]File Error:[/bold red] {e}")
        return 1


def cmd_serve(args: argparse.Namespace) -> int:
    """Runs the mock REST server."""
    file_path = os.path.abspath(args.file)
    if not os.path.exists(file_path):
        console.print(f"[bold red]Error:[/bold red] Database file not found: [yellow]{file_path}[/yellow]")
        console.print("[dim]Create a starter database by running: [yellow]mockdeck init[/yellow][/dim]")
        return 1

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            if not isinstance(loaded, dict):
                console.print(f"[bold red]Error:[/bold red] Top-level JSON structure in {file_path} must be an object.")
                return 1
    except json.JSONDecodeError as e:
        console.print(f"[bold red]JSON Syntax Error:[/bold red] {file_path}")
        console.print(f"[yellow]Line {e.lineno}, Column {e.colno}:[/yellow] {e.msg}")
        return 1
    except OSError as e:
        console.print(f"[bold red]Read Error:[/bold red] {e}")
        return 1

    store = DataStore(
        filepath=file_path,
        read_only=args.read_only,
        no_save=args.no_save,
    )

    on_req = None if args.quiet else log_request

    try:
        server = create_server(
            store=store,
            host=args.host,
            port=args.port,
            delay=args.delay,
            chaos=args.chaos,
            on_request=on_req,
        )
    except OSError as e:
        # Error 48 / 98 / 10048 address already in use
        console.print(f"[bold red]Error:[/bold red] Could not bind to port {args.port} ({e})")
        console.print(f"[yellow]Suggestion:[/yellow] Try running on another port: [cyan]mockdeck serve --port {args.port + 1}[/cyan]")
        return 1

    resources = store.get_resources()
    print_startup_banner(
        host=args.host,
        port=args.port,
        resources=resources,
        delay=args.delay,
        chaos=args.chaos,
        read_only=args.read_only,
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[dim]Stopping mockdeck server...[/dim]")
    finally:
        server.shutdown()
        server.server_close()

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mockdeck",
        description="Instant Mock REST API Server CLI from JSON files",
    )
    parser.add_argument("-v", "--version", action="version", version=f"mockdeck {__version__}")
    subparsers = parser.add_subparsers(dest="subcommand")

    # init command
    init_parser = subparsers.add_parser("init", help="Create a starter db.json mock dataset")
    init_parser.add_argument("file", nargs="?", default="db.json", help="Path for new JSON file (default: db.json)")

    # serve command
    serve_parser = subparsers.add_parser("serve", help="Start the mock REST API server")
    serve_parser.add_argument("file", nargs="?", default="db.json", help="Path to JSON database file (default: db.json)")
    serve_parser.add_argument("-p", "--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    serve_parser.add_argument("-H", "--host", default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    serve_parser.add_argument("--delay", default="0", help="Simulate latency in ms or range (e.g. 250 or 100-500)")
    serve_parser.add_argument("--chaos", type=float, default=0.0, help="Chaos failure rate between 0.0 and 1.0 (default: 0.0)")
    serve_parser.add_argument("--read-only", action="store_true", help="Disable mutating HTTP methods (POST, PUT, PATCH, DELETE)")
    serve_parser.add_argument("--no-save", action="store_true", help="Memory-only mode; do not write changes back to disk")
    serve_parser.add_argument("--quiet", action="store_true", help="Suppress live request logging stream")

    return parser


def main(args: Sequence[str] | None = None) -> int:
    parser = build_parser()
    if args is None:
        args = sys.argv[1:]

    if len(args) == 0:
        parser.print_help()
        return 0

    parsed = parser.parse_args(args)
    if parsed.subcommand == "init":
        return cmd_init(parsed)
    elif parsed.subcommand == "serve":
        return cmd_serve(parsed)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
