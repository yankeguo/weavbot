"""Interactive provider configuration wizard for the onboard command."""

from __future__ import annotations

from typing import Any

import httpx
import typer
from rich.console import Console
from rich.table import Table

from weavbot.config.schema import Config

MODELS_DEV_URL = "https://models.dev/api.json"

_NPM_TO_MODE: dict[str, str] = {
    "@ai-sdk/anthropic": "anthropic",
    "@ai-sdk/openai": "openai",
    "@ai-sdk/openai-compatible": "openai",
}


def _fetch_providers(console: Console) -> dict[str, Any] | None:
    """Fetch the models.dev provider catalogue. Returns None on failure."""
    with console.status("[dim]Fetching providers from models.dev...[/dim]", spinner="dots"):
        try:
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                resp = client.get(MODELS_DEV_URL)
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            console.print(f"[red]Failed to fetch provider list:[/red] {exc}")
            console.print("[dim]You can configure providers manually with --set instead.[/dim]")
            return None


def _compatible_providers(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Filter and sort providers compatible with weavbot's openai/anthropic modes."""
    results: list[dict[str, Any]] = []
    for key, data in raw.items():
        npm = data.get("npm", "")
        if npm not in _NPM_TO_MODE:
            continue
        models = data.get("models") or {}
        tool_models = {mid: m for mid, m in models.items() if m.get("tool_call")}
        if not tool_models:
            continue
        results.append(
            {
                "key": key,
                "id": data.get("id", key),
                "name": data.get("name", key),
                "npm": npm,
                "api": data.get("api"),
                "doc": data.get("doc"),
                "models": tool_models,
            }
        )
    results.sort(key=lambda p: p["name"].lower())
    return results


def _format_limit(value: int | None) -> str:
    if value is None:
        return "-"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.0f}K"
    return str(value)


def _prompt_number(prompt_text: str, max_val: int) -> int | None:
    """Prompt for a 1-based number. Returns None if user wants to cancel."""
    while True:
        raw = typer.prompt(prompt_text, default="")
        if not raw:
            return None
        try:
            n = int(raw)
        except ValueError:
            typer.echo(f"Please enter a number between 1 and {max_val}.")
            continue
        if 1 <= n <= max_val:
            return n
        typer.echo(f"Please enter a number between 1 and {max_val}.")


def _select_provider(providers: list[dict[str, Any]], console: Console) -> dict[str, Any] | None:
    """Display provider list, support search and selection. Returns chosen provider or None."""
    filtered = providers

    while True:
        table = Table(title="Available Providers", show_lines=False)
        table.add_column("#", style="dim", width=4, justify="right")
        table.add_column("ID", style="cyan")
        table.add_column("Name")
        table.add_column("Mode", style="green")
        table.add_column("Models", justify="right")

        for idx, p in enumerate(filtered, 1):
            mode = _NPM_TO_MODE.get(p["npm"], "?")
            table.add_row(
                str(idx),
                p["id"],
                p["name"],
                mode,
                str(len(p["models"])),
            )

        console.print()
        console.print(table)
        console.print("[dim]Enter a number to select, text to search, or empty to cancel.[/dim]")

        raw = typer.prompt("Provider", default="")
        if not raw:
            return None

        # Try number selection
        try:
            n = int(raw)
            if 1 <= n <= len(filtered):
                return filtered[n - 1]
        except ValueError:
            pass

        # Text search — filter and loop
        query = raw.lower()
        filtered = [p for p in providers if query in p["name"].lower() or query in p["id"].lower()]
        if not filtered:
            console.print(f"[yellow]No providers matching '{raw}'. Showing all.[/yellow]")
            filtered = providers
        elif len(filtered) == 1:
            return filtered[0]


def _select_model(provider: dict[str, Any], console: Console) -> tuple[str, dict[str, Any]] | None:
    """Display model list for a provider. Returns (model_id, model_data) or None."""
    models = provider["models"]
    entries = list(models.items())
    entries.sort(key=lambda e: e[1].get("name", e[0]).lower())

    table = Table(title=f"Models — {provider['name']}", show_lines=False)
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Context", justify="right")
    table.add_column("Max Output", justify="right")
    table.add_column("Reasoning", justify="center")

    for idx, (mid, mdata) in enumerate(entries, 1):
        limit = mdata.get("limit") or {}
        table.add_row(
            str(idx),
            mdata.get("id", mid),
            mdata.get("name", mid),
            _format_limit(limit.get("context")),
            _format_limit(limit.get("output")),
            "✓" if mdata.get("reasoning") else "",
        )

    console.print()
    console.print(table)

    choice = _prompt_number(f"Model [1-{len(entries)}]", len(entries))
    if choice is None:
        return None

    mid, mdata = entries[choice - 1]
    model_id = mdata.get("id", mid)
    return model_id, mdata


def interactive_provider_setup(config: Config, console: Console) -> Config:
    """Run the interactive provider setup wizard.

    Returns the (possibly modified) config. If the user cancels at any step
    the original config is returned unchanged.
    """
    console.print("\n[bold]Interactive Provider Setup[/bold]")

    raw = _fetch_providers(console)
    if raw is None:
        return config

    providers = _compatible_providers(raw)
    if not providers:
        console.print("[red]No compatible providers found.[/red]")
        return config

    # Step 1: select provider
    provider = _select_provider(providers, console)
    if provider is None:
        console.print("[dim]Setup cancelled.[/dim]")
        return config

    # Step 2: select model
    result = _select_model(provider, console)
    if result is None:
        console.print("[dim]Setup cancelled.[/dim]")
        return config
    model_id, model_data = result

    # Step 3: API key
    console.print()
    if provider.get("doc"):
        console.print(f"[dim]Docs: {provider['doc']}[/dim]")
    api_key: str = typer.prompt("API Key", hide_input=True)
    if not api_key.strip():
        console.print("[dim]Setup cancelled.[/dim]")
        return config
    api_key = api_key.strip()

    # Derive configuration values
    provider_id: str = provider["id"]
    mode = _NPM_TO_MODE[provider["npm"]]
    api_base: str | None = provider.get("api") or None
    limit = model_data.get("limit") or {}
    max_tokens: int = limit.get("output", 8192)

    # Summary
    console.print()
    console.print("[bold]Configuration summary:[/bold]")
    console.print(f"  Provider:   [cyan]{provider_id}[/cyan] ({provider['name']})")
    console.print(f"  Mode:       [green]{mode}[/green]")
    if api_base:
        console.print(f"  API Base:   {api_base}")
    console.print(f"  Model:      [cyan]{model_id}[/cyan]")
    console.print(f"  Max Tokens: {max_tokens}")
    console.print(f"  API Key:    {api_key[:8]}{'*' * max(0, len(api_key) - 8)}")

    if not typer.confirm("\nApply this configuration?", default=True):
        console.print("[dim]Setup cancelled.[/dim]")
        return config

    # Apply to config
    data = config.model_dump(by_alias=True)

    data.setdefault("providers", {})[provider_id] = {
        "mode": mode,
        "apiKey": api_key,
        **({"apiBase": api_base} if api_base else {}),
    }

    defaults = data.setdefault("agents", {}).setdefault("defaults", {})
    defaults["provider"] = provider_id
    defaults["model"] = model_id
    defaults["maxTokens"] = max_tokens

    config = Config.model_validate(data)

    console.print(f"[green]✓[/green] Provider [cyan]{provider_id}[/cyan] configured")
    return config
