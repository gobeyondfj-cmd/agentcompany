"""CLI for Agent Company AI - manage your AI agent company from the terminal."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree

app = typer.Typer(
    name="agent-company-ai",
    help="Spin up an AI agent company - a business run by AI agents, managed by you.",
    no_args_is_help=True,
)
console = Console()

_selected_company: str = "default"


def _version_callback(value: bool):
    if value:
        from importlib.metadata import version
        console.print(f"agent-company-ai {version('agent-company-ai')}")
        raise typer.Exit()


@app.callback()
def main(
    company: str = typer.Option(
        "default",
        "--company",
        "-C",
        help="Company slug to operate on",
        envvar="AGENT_COMPANY_NAME",
    ),
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit",
        callback=_version_callback,
        is_eager=True,
    ),
):
    """Spin up an AI agent company - a business run by AI agents, managed by you."""
    global _selected_company
    _selected_company = company


def _run(coro):
    """Run an async function synchronously."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# Provider presets: maps user-facing name to (config provider, base_url, default_model, env_var)
PROVIDER_PRESETS = {
    "anthropic":     ("anthropic", None,                                     "claude-sonnet-4-5-20250929",              "ANTHROPIC_API_KEY"),
    "openai":        ("openai",   None,                                     "gpt-4o",                                  "OPENAI_API_KEY"),
    "deepseek":      ("openai",   "https://api.deepseek.com/v1",           "deepseek-r1",                             "DEEPSEEK_API_KEY"),
    "mimo":          ("openai",   "https://api.deepseek.com/v1",           "mimo-7b-rl",                              "DEEPSEEK_API_KEY"),
    "kimi":          ("openai",   "https://api.moonshot.cn/v1",            "kimi-k2-0711-preview",                    "MOONSHOT_API_KEY"),
    "qwen":          ("openai",   "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-max",                    "DASHSCOPE_API_KEY"),
    "minimax":       ("openai",   "https://api.minimaxi.chat/v1",        "MiniMax-M1",                              "MINIMAX_API_KEY"),
    "ollama":        ("openai",   "http://localhost:11434/v1",             "llama3.1",                                None),
    "together":      ("openai",   "https://api.together.xyz/v1",           "meta-llama/Llama-3.3-70B-Instruct-Turbo", "TOGETHER_API_KEY"),
    "groq":          ("openai",   "https://api.groq.com/openai/v1",       "llama-3.3-70b-versatile",                 "GROQ_API_KEY"),
    "openai-compat": ("openai",   None,                                    None,                                      None),
}


# ------------------------------------------------------------------
# Integration setup helpers
# ------------------------------------------------------------------


def _prompt_integrations(company_name: str) -> dict:
    """Interactively prompt for integration configuration.

    Returns a dict of integration overrides to merge into
    ``company.config.integrations``.
    """
    from agent_company_ai.config import (
        StripeConfig, EmailConfig, GumroadConfig,
        CalcomConfig, InvoiceConfig, LandingPageConfig,
    )

    console.print("\n[bold]Configure integrations (optional)[/bold]")
    console.print("  [cyan][1][/cyan] Stripe (payment links & subscriptions)")
    console.print("  [cyan][2][/cyan] Email (send invoices & notifications)")
    console.print("  [cyan][3][/cyan] Gumroad (sell digital products)")
    console.print("  [cyan][4][/cyan] Cal.com (paid bookings)")
    console.print("  [cyan][5][/cyan] Invoices (generate & send invoices)")
    console.print("  [cyan][6][/cyan] Landing Pages (auto-enabled, no key needed)")
    console.print("  [cyan][7][/cyan] All of the above")
    console.print("  [cyan][8][/cyan] Skip for now")

    raw = console.input("\nChoose integrations [comma-separated, e.g. 1,2,5]: ").strip()
    if not raw or raw == "8":
        return {}

    choices = {c.strip() for c in raw.split(",")}
    if "7" in choices:
        choices = {"1", "2", "3", "4", "5", "6"}

    overrides: dict = {}

    # --- Stripe ---
    if "1" in choices:
        key = console.input(
            "Stripe API key (or press Enter to use ${STRIPE_SECRET_KEY}): "
        ).strip() or "${STRIPE_SECRET_KEY}"
        overrides["stripe"] = StripeConfig(enabled=True, api_key=key)

    # --- Email ---
    if "2" in choices:
        console.print("  Email provider: [cyan][1][/cyan] Resend  [cyan][2][/cyan] SendGrid")
        ep = console.input("  Choose [1/2, default 1]: ").strip()
        email_provider = "sendgrid" if ep == "2" else "resend"
        default_env = "${SENDGRID_API_KEY}" if email_provider == "sendgrid" else "${RESEND_API_KEY}"
        email_key = console.input(
            f"  API key (or press Enter to use {default_env}): "
        ).strip() or default_env
        from_addr = console.input("  From address (e.g. hello@example.com): ").strip()
        overrides["email"] = EmailConfig(
            enabled=True,
            provider=email_provider,
            api_key=email_key,
            from_address=from_addr,
            from_name=company_name,
        )

    # --- Gumroad ---
    if "3" in choices:
        token = console.input(
            "Gumroad access token (or press Enter to use ${GUMROAD_ACCESS_TOKEN}): "
        ).strip() or "${GUMROAD_ACCESS_TOKEN}"
        overrides["gumroad"] = GumroadConfig(enabled=True, access_token=token)

    # --- Cal.com ---
    if "4" in choices:
        cal_key = console.input(
            "Cal.com API key (or press Enter to use ${CALCOM_API_KEY}): "
        ).strip() or "${CALCOM_API_KEY}"
        dur = console.input("  Default meeting duration in minutes [30]: ").strip()
        duration = int(dur) if dur.isdigit() else 30
        overrides["calcom"] = CalcomConfig(
            enabled=True, api_key=cal_key, default_duration=duration,
        )

    # --- Invoices ---
    if "5" in choices:
        payment_info = console.input(
            "Payment instructions (e.g. 'Pay via bank transfer to ...'): "
        ).strip()
        overrides["invoice"] = InvoiceConfig(
            enabled=True,
            company_name=company_name,
            payment_instructions=payment_info,
        )

    # --- Landing Pages ---
    if "6" in choices:
        overrides["landing_page"] = LandingPageConfig(enabled=True)

    return overrides


# ------------------------------------------------------------------
# init
# ------------------------------------------------------------------


@app.command()
def init(
    name: str = typer.Option("My AI Company", "--name", "-n", help="Company name"),
    provider: str = typer.Option(None, "--provider", "-p", help="LLM provider (anthropic, openai, deepseek, mimo, kimi, qwen, minimax, ollama, together, groq, or openai-compat)"),
    api_key: str = typer.Option(None, "--api-key", "-k", help="API key for the chosen provider"),
    model: str = typer.Option(None, "--model", "-m", help="Model name (defaults per provider)"),
    base_url: str = typer.Option(None, "--base-url", "-b", help="Base URL for OpenAI-compatible endpoints"),
    skip_integrations: bool = typer.Option(False, "--skip-integrations", help="Skip integration setup prompts"),
):
    """Initialize a new AI agent company in the current directory."""
    from agent_company_ai.core.company import Company
    from agent_company_ai.config import save_config, LLMProviderConfig

    # Interactive provider selection when --provider not given
    chosen_provider = provider
    chosen_key = api_key
    chosen_model = model
    chosen_base_url = base_url

    # Fully non-interactive when all flags provided
    _fully_specified = chosen_provider is not None and chosen_key is not None

    if chosen_provider is None:
        console.print("\n[bold]Configure LLM provider[/bold]")
        console.print("  [cyan] [1][/cyan] Anthropic (default)")
        console.print("  [cyan] [2][/cyan] OpenAI")
        console.print("  [cyan] [3][/cyan] DeepSeek (DeepSeek-R1, etc.)")
        console.print("  [cyan] [4][/cyan] MiMo (DeepSeek MiMo reasoning)")
        console.print("  [cyan] [5][/cyan] Kimi (Moonshot AI)")
        console.print("  [cyan] [6][/cyan] Qwen (Alibaba Cloud)")
        console.print("  [cyan] [7][/cyan] MiniMax (MiniMax-M1)")
        console.print("  [cyan] [8][/cyan] Ollama (local, no API key needed)")
        console.print("  [cyan] [9][/cyan] Together AI (Llama, Mixtral, etc.)")
        console.print("  [cyan][10][/cyan] Groq (fast open-source inference)")
        console.print("  [cyan][11][/cyan] Other OpenAI-compatible endpoint")
        console.print("  [cyan][12][/cyan] Skip for now")
        choice = console.input("\nChoose provider [1-12]: ").strip()
        provider_map = {
            "1": "anthropic", "2": "openai", "3": "deepseek",
            "4": "mimo", "5": "kimi", "6": "qwen", "7": "minimax",
            "8": "ollama", "9": "together", "10": "groq",
            "11": "openai-compat",
        }
        if choice in ("12", ""):
            chosen_provider = None
        else:
            chosen_provider = provider_map.get(choice, "anthropic")

    if chosen_provider and chosen_provider in PROVIDER_PRESETS:
        preset = PROVIDER_PRESETS[chosen_provider]
        config_provider, preset_base_url, preset_model, env_var = preset

        # Base URL: use flag > preset > prompt (for openai-compat)
        if not chosen_base_url:
            if preset_base_url:
                chosen_base_url = preset_base_url
            elif chosen_provider == "openai-compat" and not _fully_specified:
                chosen_base_url = console.input("Base URL (e.g. http://localhost:8000/v1): ").strip()

        # API key: use flag > skip prompt if fully specified > prompt > env var placeholder
        if not chosen_key:
            if chosen_provider == "ollama":
                chosen_key = "ollama"  # Ollama doesn't need a real key
            elif env_var:
                chosen_key = console.input(
                    f"API key (or press Enter to use ${{{env_var}}}): "
                ).strip() or f"${{{env_var}}}"
            else:
                chosen_key = console.input("API key (or press Enter to skip): ").strip() or ""

        # Model: use flag > preset default (non-interactive) > prompt
        if not chosen_model:
            if _fully_specified and preset_model:
                chosen_model = preset_model
            elif preset_model:
                entered = console.input(
                    f"Model [{preset_model}]: "
                ).strip()
                chosen_model = entered or preset_model
            elif not _fully_specified:
                chosen_model = console.input("Model name: ").strip()

    # Prompt for integrations unless skipped
    integration_overrides: dict = {}
    if not _fully_specified and not skip_integrations:
        integration_overrides = _prompt_integrations(name)

    async def _init():
        company = await Company.init(name=name, company=_selected_company)
        company_dir = company.company_dir

        # Apply LLM config if a provider was selected
        if chosen_provider and chosen_provider in PROVIDER_PRESETS:
            config_provider = PROVIDER_PRESETS[chosen_provider][0]
            provider_config = LLMProviderConfig(
                api_key=chosen_key or "",
                model=chosen_model or "",
                base_url=chosen_base_url,
            )
            company.config.llm.default_provider = config_provider
            if config_provider == "anthropic":
                company.config.llm.anthropic = provider_config
            else:
                company.config.llm.openai = provider_config

        # Apply integration overrides
        for key, cfg in integration_overrides.items():
            setattr(company.config.integrations, key, cfg)

        save_config(company.config, company_dir / "config.yaml")

        await company.shutdown()
        return company_dir

    company_dir = _run(_init())

    # Build output message
    provider_line = ""
    if chosen_provider:
        display_provider = chosen_provider
        if chosen_base_url and chosen_provider not in ("anthropic", "openai"):
            display_provider = f"{chosen_provider} ({chosen_base_url})"
        provider_line = f"Provider: [cyan]{display_provider}[/cyan] (model: {chosen_model})\n"
    else:
        provider_line = "Provider: [yellow]not configured[/yellow] — edit config.yaml or re-run init\n"

    if integration_overrides:
        enabled_names = ", ".join(sorted(integration_overrides.keys()))
        integrations_line = f"Integrations: [cyan]{enabled_names}[/cyan]\n"
    else:
        integrations_line = "Integrations: [yellow]none[/yellow] — edit config.yaml or re-run init\n"

    console.print(Panel(
        f"[bold green]Company '{name}' initialized![/bold green]\n\n"
        f"Directory: {company_dir}\n"
        f"Config: {company_dir / 'config.yaml'}\n"
        f"{provider_line}"
        f"{integrations_line}\n"
        f"Next steps:\n"
        f"  agent-company-ai hire ceo --name Alice\n"
        f"  agent-company-ai hire developer --name Bob\n"
        f"  agent-company-ai team",
        title="Agent Company AI",
    ))


# ------------------------------------------------------------------
# hire
# ------------------------------------------------------------------


@app.command()
def hire(
    role: str = typer.Argument(help="Role to hire (e.g. ceo, developer, marketer)"),
    name: str = typer.Option(None, "--name", "-n", help="Agent name"),
    provider: str = typer.Option(None, "--provider", "-p", help="LLM provider override"),
    model: str = typer.Option(None, "--model", "-m", help="Model override"),
):
    """Hire a new AI agent with the given role."""
    from agent_company_ai.core.company import Company

    async def _hire():
        company = await Company.load(company=_selected_company)
        agent = await company.hire(role, agent_name=name, provider=provider, model=model)
        await company.shutdown()
        return agent

    agent = _run(_hire())
    console.print(f"[bold green]Hired {agent.name}[/bold green] as [cyan]{agent.role.title}[/cyan]")


# ------------------------------------------------------------------
# fire
# ------------------------------------------------------------------


@app.command()
def fire(
    name: str = typer.Argument(help="Name of the agent to fire"),
):
    """Remove an agent from the company."""
    from agent_company_ai.core.company import Company

    async def _fire():
        company = await Company.load(company=_selected_company)
        await company.fire(name)
        await company.shutdown()

    _run(_fire())
    console.print(f"[bold red]{name}[/bold red] has been fired.")


# ------------------------------------------------------------------
# team
# ------------------------------------------------------------------


@app.command()
def team():
    """Show all agents in the company."""
    from agent_company_ai.core.company import Company

    async def _team():
        company = await Company.load(company=_selected_company)
        agents = company.list_agents()
        await company.shutdown()
        return company.config.name, agents

    company_name, agents = _run(_team())

    if not agents:
        console.print("[yellow]No agents hired yet.[/yellow] Use 'agent-company-ai hire <role>' to get started.")
        return

    table = Table(title=f"{company_name} - Team")
    table.add_column("Name", style="bold")
    table.add_column("Role", style="cyan")
    table.add_column("Title")
    table.add_column("Reports To", style="dim")

    for a in agents:
        table.add_row(a["name"], a["role"], a["title"], a["reports_to"])

    console.print(table)


# ------------------------------------------------------------------
# assign
# ------------------------------------------------------------------


@app.command()
def assign(
    task: str = typer.Argument(help="Task description"),
    to: str = typer.Option(None, "--to", "-t", help="Agent name to assign to"),
):
    """Assign a task to an agent (or let the company decide)."""
    from agent_company_ai.core.company import Company

    async def _assign():
        company = await Company.load(company=_selected_company)
        t = await company.assign(task, assignee=to)
        # Wait for task to complete if assigned
        if to:
            max_wait = 300  # 5 minutes
            waited = 0
            while not t.is_terminal and waited < max_wait:
                await asyncio.sleep(1)
                waited += 1
        await company.shutdown()
        return t

    with console.status(f"Working on task..."):
        t = _run(_assign())

    if t.is_terminal:
        color = "green" if t.status.value == "done" else "red"
        console.print(Panel(
            f"[bold]{t.description}[/bold]\n\n"
            f"Status: [{color}]{t.status.value}[/{color}]\n"
            f"Assignee: {t.assignee or 'unassigned'}\n"
            f"Result: {t.result or 'N/A'}",
            title=f"Task {t.id}",
        ))
    else:
        console.print(f"Task [bold]{t.id}[/bold] created (status: {t.status.value})")


# ------------------------------------------------------------------
# tasks
# ------------------------------------------------------------------


@app.command()
def tasks():
    """Show the task board."""
    from agent_company_ai.core.company import Company

    async def _tasks():
        company = await Company.load(company=_selected_company)
        all_tasks = company.task_board.list_all()
        await company.shutdown()
        return all_tasks

    all_tasks = _run(_tasks())

    if not all_tasks:
        console.print("[yellow]No tasks yet.[/yellow]")
        return

    table = Table(title="Task Board")
    table.add_column("ID", style="dim")
    table.add_column("Description")
    table.add_column("Assignee", style="cyan")
    table.add_column("Status")
    table.add_column("Subtasks", justify="right")

    status_colors = {
        "done": "green", "failed": "red", "cancelled": "dim red",
        "in_progress": "yellow", "pending": "dim", "assigned": "blue",
        "review": "magenta",
    }

    for t in all_tasks:
        d = t.to_dict()
        color = status_colors.get(d["status"], "white")
        table.add_row(
            d["id"],
            d["description"][:60],
            d["assignee"] or "-",
            f"[{color}]{d['status']}[/{color}]",
            f"{d['subtasks_done']}/{d['subtask_count']}" if d["subtask_count"] else "-",
        )

    console.print(table)


# ------------------------------------------------------------------
# chat
# ------------------------------------------------------------------


@app.command()
def chat(
    agent_name: str = typer.Argument(help="Name of the agent to chat with"),
):
    """Start an interactive chat with an agent."""
    from agent_company_ai.core.company import Company

    async def _chat():
        company = await Company.load(company=_selected_company)
        agent = company.get_agent(agent_name)
        if not agent:
            console.print(f"[red]No agent named '{agent_name}'.[/red]")
            return

        console.print(f"[bold]Chatting with {agent_name} ({agent.role.title})[/bold]")
        console.print("[dim]Type 'exit' to end the conversation.[/dim]\n")

        while True:
            try:
                user_input = console.input("[bold blue]You>[/bold blue] ")
            except (EOFError, KeyboardInterrupt):
                break

            if user_input.strip().lower() in ("exit", "quit", "bye"):
                break

            with console.status("Thinking..."):
                reply = await company.chat(agent_name, user_input)

            console.print(f"[bold green]{agent_name}>[/bold green] {reply}\n")

        await company.shutdown()
        console.print("[dim]Chat ended.[/dim]")

    _run(_chat())


# ------------------------------------------------------------------
# broadcast
# ------------------------------------------------------------------


@app.command()
def broadcast(
    message: str = typer.Argument(help="Message to send to all agents"),
):
    """Send a message to all agents."""
    from agent_company_ai.core.company import Company

    async def _broadcast():
        company = await Company.load(company=_selected_company)
        await company.broadcast(message)
        await company.shutdown()

    _run(_broadcast())
    console.print(f"[green]Broadcast sent to all agents.[/green]")


# ------------------------------------------------------------------
# run (autonomous mode)
# ------------------------------------------------------------------


@app.command()
def run(
    goal: str = typer.Argument(help="The company goal to achieve"),
    max_cycles: int = typer.Option(None, "--cycles", "-c", help="Max CEO review cycles (default: from config)"),
    max_time: int = typer.Option(None, "--timeout", "-T", help="Wall-clock timeout in seconds (default: from config)"),
    max_tasks: int = typer.Option(None, "--max-tasks", help="Max total tasks to create (default: from config)"),
):
    """Run the company autonomously toward a goal. The CEO will delegate.

    The CEO breaks the goal into tasks and delegates to agents. After each
    cycle of work, the CEO reviews progress and decides whether to continue.
    Stops when: goal achieved, max cycles reached, timeout, or task limit hit.
    Press Ctrl+C to stop gracefully.
    """
    from agent_company_ai.core.company import Company

    async def _run_goal():
        company = await Company.load(company=_selected_company)

        # Apply CLI overrides to config
        if max_cycles is not None:
            company.config.autonomous.max_cycles = max_cycles
        if max_time is not None:
            company.config.autonomous.max_time_seconds = max_time
        if max_tasks is not None:
            company.config.autonomous.max_total_tasks = max_tasks

        limits = company.config.autonomous
        console.print(Panel(
            f"[bold]Goal:[/bold] {goal}\n\n"
            f"The CEO will plan, delegate, and review in cycles.\n"
            f"Limits: {limits.max_cycles} cycles, "
            f"{limits.max_time_seconds}s timeout, "
            f"{limits.max_total_tasks} max tasks\n\n"
            f"[dim]Press Ctrl+C to stop gracefully.[/dim]",
            title="Autonomous Mode",
            border_style="green",
        ))

        try:
            await company.run_goal(goal)
        except KeyboardInterrupt:
            company.request_stop()
            console.print("\n[yellow]Stop requested. Finishing current wave...[/yellow]")

        summary = company._build_goal_summary()
        scorecard = company._build_quality_scorecard()
        await company.shutdown()
        return summary, scorecard

    with console.status("[bold green]Company is running autonomously..."):
        summary, scorecard = _run(_run_goal())

    console.print(Panel(summary, title="Goal Summary"))

    # Show deliverable quality scorecard
    sc = scorecard
    total = sc["total_deliverables"]
    if total > 0:
        quality_line = (
            f"[bold]{total}[/bold] deliverables: "
            f"[green]{sc['substantial']} substantial[/green], "
            f"[yellow]{sc['partial']} partial[/yellow], "
            f"[red]{sc['thin']} thin[/red], "
            f"[dim]{sc['empty']} empty[/dim]"
        )
        console.print(Panel(quality_line, title="Deliverable Quality"))


# ------------------------------------------------------------------
# status
# ------------------------------------------------------------------


@app.command()
def status():
    """Show company overview and status."""
    from agent_company_ai.core.company import Company

    async def _status():
        company = await Company.load(company=_selected_company)
        s = company.status()
        agents = company.list_agents()
        org = company.get_org_chart()
        await company.shutdown()
        return s, agents, org

    s, agents, org = _run(_status())

    task_counts = s['tasks']
    if task_counts:
        task_parts = [f"{v} {k}" for k, v in task_counts.items()]
        task_display = ", ".join(task_parts)
    else:
        task_display = "No tasks yet"

    console.print(Panel(
        f"[bold]{s['name']}[/bold]\n\n"
        f"Agents: {s['agents']}\n"
        f"Tasks: {task_display}\n"
        f"Running: {'Yes' if s['running'] else 'No'}\n"
        f"Output: {s.get('output_dir', 'N/A')}",
        title="Company Status",
    ))

    if agents:
        # Print org chart as a tree
        tree = Tree(f"[bold]{org['name']}[/bold] ({org.get('title', '')})")
        _build_tree(tree, org)
        console.print(tree)


def _build_tree(tree_node: Tree, org_node: dict) -> None:
    """Recursively build a Rich Tree from the org chart."""
    for child in org_node.get("children", []):
        label = f"[cyan]{child['name']}[/cyan] - {child.get('title', child.get('role', ''))}"
        branch = tree_node.add(label)
        _build_tree(branch, child)


# ------------------------------------------------------------------
# output
# ------------------------------------------------------------------


@app.command()
def output(
    task_id: str = typer.Option(None, "--task", "-t", help="Filter by task ID"),
    open_dir: bool = typer.Option(False, "--open", "-o", help="Open output directory in file manager"),
):
    """List deliverables produced by agents, or open the output directory."""
    from agent_company_ai.core.company import Company

    async def _output():
        company = await Company.load(company=_selected_company)
        artifacts = await company.get_artifacts(task_id=task_id)
        output_dir = str(company.output_dir)
        await company.shutdown()
        return artifacts, output_dir

    artifacts, output_dir = _run(_output())

    if open_dir:
        import platform
        import subprocess
        system = platform.system()
        if system == "Darwin":
            subprocess.Popen(["open", output_dir])
        elif system == "Windows":
            subprocess.Popen(["explorer", output_dir])
        else:
            subprocess.Popen(["xdg-open", output_dir])
        console.print(f"[green]Opened {output_dir}[/green]")
        return

    if not artifacts:
        console.print("[yellow]No deliverables yet.[/yellow]")
        return

    table = Table(title="Deliverables")
    table.add_column("Task ID", style="dim")
    table.add_column("Agent", style="cyan")
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("Created", style="dim")

    for a in artifacts:
        table.add_row(
            a.get("task_id", "-"),
            a.get("agent_id", "-"),
            a.get("name", "-"),
            a.get("artifact_type", "-"),
            a.get("created_at", "-"),
        )

    console.print(table)


# ------------------------------------------------------------------
# revenue
# ------------------------------------------------------------------


@app.command()
def revenue(
    days: int = typer.Option(30, "--days", "-d", help="Number of days to look back"),
):
    """Show company revenue summary."""
    from agent_company_ai.storage.database import get_database
    from agent_company_ai.config import get_company_dir, maybe_migrate_legacy_layout

    maybe_migrate_legacy_layout()
    company_dir = get_company_dir(company=_selected_company, create=False)
    if not (company_dir / "config.yaml").exists():
        console.print("[red]No company found.[/red] Run 'agent-company-ai init' first.")
        raise typer.Exit(1)

    async def _revenue():
        db = get_database(company_dir)
        await db.connect()

        # All-time total
        row = await db.fetch_one(
            "SELECT COALESCE(SUM(amount_cents), 0) AS total FROM revenue "
            "WHERE status = 'confirmed'"
        )
        all_time = row["total"] if row else 0

        # Period total
        row = await db.fetch_one(
            "SELECT COALESCE(SUM(amount_cents), 0) AS total FROM revenue "
            "WHERE status = 'confirmed' AND created_at >= datetime('now', ?)",
            (f"-{days} days",),
        )
        period = row["total"] if row else 0

        # Last 7 days
        row = await db.fetch_one(
            "SELECT COALESCE(SUM(amount_cents), 0) AS total FROM revenue "
            "WHERE status = 'confirmed' AND created_at >= datetime('now', '-7 days')"
        )
        week = row["total"] if row else 0

        # By source
        sources = await db.fetch_all(
            "SELECT source, COALESCE(SUM(amount_cents), 0) AS total, COUNT(*) AS cnt "
            "FROM revenue WHERE status = 'confirmed' "
            "AND created_at >= datetime('now', ?) "
            "GROUP BY source ORDER BY total DESC",
            (f"-{days} days",),
        )

        await db.close()
        return all_time, period, week, sources

    all_time, period, week, sources = _run(_revenue())

    # Summary panel
    console.print(Panel(
        f"[bold]All-time:[/bold]     ${all_time / 100:.2f}\n"
        f"[bold]Last {days} days:[/bold] ${period / 100:.2f}\n"
        f"[bold]Last 7 days:[/bold]  ${week / 100:.2f}",
        title="Revenue Summary",
        border_style="green",
    ))

    # By source table
    if sources:
        table = Table(title=f"Revenue by Source (last {days} days)")
        table.add_column("Source", style="cyan")
        table.add_column("Amount", justify="right", style="bold")
        table.add_column("Transactions", justify="right")
        for s in sources:
            table.add_row(s["source"], f"${s['total'] / 100:.2f}", str(s["cnt"]))
        console.print(table)
    else:
        console.print("[dim]No revenue recorded yet.[/dim]")


# ------------------------------------------------------------------
# dashboard
# ------------------------------------------------------------------


@app.command()
def dashboard(
    port: int = typer.Option(8420, "--port", "-p", help="Port to serve on"),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
):
    """Launch the web dashboard."""
    from agent_company_ai.dashboard.server import run_dashboard

    console.print(f"[bold green]Starting dashboard at http://{host}:{port}[/bold green]")
    run_dashboard(host=host, port=port, company=_selected_company)


# ------------------------------------------------------------------
# roles
# ------------------------------------------------------------------


@app.command()
def roles():
    """List all available preset roles."""
    from agent_company_ai.config import list_available_roles

    available = list_available_roles()
    console.print("[bold]Available roles:[/bold]")
    for r in available:
        console.print(f"  [cyan]{r}[/cyan]")


# ------------------------------------------------------------------
# setup (batch create company with org chart)
# ------------------------------------------------------------------

# Preset company templates: maps a company type to a list of (role, name) pairs.
# Order matters - first agent in each group is the leader, rest are reports.
COMPANY_PRESETS: dict[str, dict] = {
    "tech_startup": {
        "description": "Tech Startup - small team building a software product",
        "agents": [
            ("ceo", "Alex"),
            ("cto", "Jordan"),
            ("developer", "Sam"),
            ("developer", "Riley"),
            ("marketer", "Morgan"),
            ("project_manager", "Casey"),
        ],
    },
    "agency": {
        "description": "Digital Agency - client services, marketing, and creative",
        "agents": [
            ("ceo", "Alex"),
            ("marketer", "Morgan"),
            ("developer", "Sam"),
            ("sales", "Taylor"),
            ("project_manager", "Casey"),
            ("support", "Jamie"),
        ],
    },
    "ecommerce": {
        "description": "E-commerce Business - online store with full ops",
        "agents": [
            ("ceo", "Alex"),
            ("cto", "Jordan"),
            ("developer", "Sam"),
            ("marketer", "Morgan"),
            ("sales", "Taylor"),
            ("support", "Jamie"),
            ("finance", "Drew"),
        ],
    },
    "saas": {
        "description": "SaaS Company - subscription software business",
        "agents": [
            ("ceo", "Alex"),
            ("cto", "Jordan"),
            ("developer", "Sam"),
            ("developer", "Riley"),
            ("marketer", "Morgan"),
            ("sales", "Taylor"),
            ("support", "Jamie"),
            ("finance", "Drew"),
            ("project_manager", "Casey"),
        ],
    },
    "consulting": {
        "description": "Consulting Firm - strategy and professional services",
        "agents": [
            ("ceo", "Alex"),
            ("project_manager", "Casey"),
            ("marketer", "Morgan"),
            ("sales", "Taylor"),
            ("finance", "Drew"),
            ("hr", "Avery"),
        ],
    },
    "content": {
        "description": "Content / Media Company - publishing and content creation",
        "agents": [
            ("ceo", "Alex"),
            ("marketer", "Morgan"),
            ("developer", "Sam"),
            ("project_manager", "Casey"),
            ("support", "Jamie"),
        ],
    },
    "full": {
        "description": "Full Company - all departments staffed",
        "agents": [
            ("ceo", "Alex"),
            ("cto", "Jordan"),
            ("developer", "Sam"),
            ("developer", "Riley"),
            ("marketer", "Morgan"),
            ("sales", "Taylor"),
            ("support", "Jamie"),
            ("finance", "Drew"),
            ("hr", "Avery"),
            ("project_manager", "Casey"),
        ],
    },
}


@app.command()
def setup(
    company_type: str = typer.Argument(
        None,
        help="Company type: tech_startup, agency, ecommerce, saas, consulting, content, full",
    ),
    company_name: str = typer.Option("My AI Company", "--name", "-n", help="Company name"),
    provider: str = typer.Option(None, "--provider", "-p", help="LLM provider for all agents"),
    api_key: str = typer.Option(None, "--api-key", "-k", help="API key (enables non-interactive init)"),
    model: str = typer.Option(None, "--model", "-m", help="Model for all agents"),
    list_presets: bool = typer.Option(False, "--list", "-l", help="List available presets"),
):
    """Set up a full company with agents in one command.

    Initializes the company (if needed) and batch-hires a team based on a
    preset template. Each preset is a sensible org chart for that business type.

    Examples:
      agent-company-ai setup tech_startup --name "Acme AI"
      agent-company-ai setup saas --name "CloudCo" --provider anthropic --api-key sk-ant-...
      agent-company-ai setup --list
    """
    if list_presets or company_type is None:
        console.print("[bold]Available company presets:[/bold]\n")
        table = Table()
        table.add_column("Preset", style="cyan bold")
        table.add_column("Description")
        table.add_column("Team Size", justify="right")
        table.add_column("Roles")
        for key, preset in COMPANY_PRESETS.items():
            roles_list = [r for r, _ in preset["agents"]]
            unique_roles = sorted(set(roles_list))
            table.add_row(
                key,
                preset["description"],
                str(len(preset["agents"])),
                ", ".join(unique_roles),
            )
        console.print(table)
        if company_type is None:
            console.print(
                "\n[dim]Usage: agent-company-ai setup <preset> --name \"My Company\"[/dim]"
            )
        return

    if company_type not in COMPANY_PRESETS:
        console.print(f"[red]Unknown preset '{company_type}'.[/red] Use --list to see options.")
        raise typer.Exit(1)

    preset = COMPANY_PRESETS[company_type]
    from agent_company_ai.core.company import Company

    async def _setup():
        # Init company if not already
        from agent_company_ai.config import get_company_dir, save_config, LLMProviderConfig
        company_dir = get_company_dir(company=_selected_company)
        config_path = company_dir / "config.yaml"

        if config_path.exists():
            company = await Company.load(company=_selected_company)
            # Update name if different
            if company.config.name != company_name and company_name != "My AI Company":
                company.config.name = company_name
                save_config(company.config, config_path)
        else:
            company = await Company.init(name=company_name, company=_selected_company)
            # Apply LLM config if api_key provided (non-interactive init)
            if api_key and provider:
                full_preset = PROVIDER_PRESETS.get(provider, ("openai", None, None, None))
                cfg_provider, cfg_base_url, cfg_default_model = full_preset[0], full_preset[1], full_preset[2]
                provider_config = LLMProviderConfig(
                    api_key=api_key,
                    model=model or cfg_default_model or "",
                    base_url=cfg_base_url,
                )
                company.config.llm.default_provider = cfg_provider
                if cfg_provider == "anthropic":
                    company.config.llm.anthropic = provider_config
                else:
                    company.config.llm.openai = provider_config
                save_config(company.config, config_path)
                # Rebuild router with new config
                from agent_company_ai.llm.router import LLMRouter
                company.router = LLMRouter(company.config.llm)

        hired = []
        skipped = []
        for role_name, agent_name in preset["agents"]:
            if agent_name in company.agents:
                skipped.append((agent_name, role_name))
                continue
            try:
                await company.hire(
                    role_name=role_name,
                    agent_name=agent_name,
                    provider=provider,
                    model=model,
                )
                hired.append((agent_name, role_name))
            except Exception as e:
                console.print(f"  [yellow]Warning:[/yellow] Could not hire {agent_name} ({role_name}): {e}")

        agents = company.list_agents()
        org = company.get_org_chart()
        await company.shutdown()
        return hired, skipped, agents, org

    with console.status(f"Setting up {company_name} ({preset['description']})..."):
        hired, skipped, agents, org = _run(_setup())

    # Show results
    console.print(Panel(
        f"[bold green]{company_name}[/bold green] — {preset['description']}",
        title="Company Setup Complete",
        border_style="green",
    ))

    if hired:
        console.print(f"\n[bold green]Hired {len(hired)} agents:[/bold green]")
        for name, role in hired:
            console.print(f"  [green]+[/green] [bold]{name}[/bold] as [cyan]{role}[/cyan]")

    if skipped:
        console.print(f"\n[dim]Skipped {len(skipped)} (already exist):[/dim]")
        for name, role in skipped:
            console.print(f"  [dim]  {name} ({role})[/dim]")

    # Print org chart
    console.print()
    tree = Tree(f"[bold]{org['name']}[/bold] ({org.get('title', '')})")
    _build_tree(tree, org)
    console.print(tree)

    console.print(f"\n[dim]Next: agent-company-ai run \"Your goal here\"[/dim]")
    console.print(f"[dim]Edit: agent-company-ai hire/fire/team to adjust the team[/dim]")


# ------------------------------------------------------------------
# companies
# ------------------------------------------------------------------


@app.command()
def companies():
    """List all companies in this directory."""
    from agent_company_ai.config import (
        list_companies,
        get_company_dir,
        load_config,
        maybe_migrate_legacy_layout,
    )

    maybe_migrate_legacy_layout()
    slugs = list_companies()

    if not slugs:
        console.print("[yellow]No companies found.[/yellow] Use 'agent-company-ai init' to create one.")
        return

    table = Table(title="Companies")
    table.add_column("Name", style="bold")
    table.add_column("Slug", style="cyan")
    table.add_column("Directory", style="dim")
    table.add_column("Agents", justify="right")

    for slug in slugs:
        company_dir = get_company_dir(company=slug, create=False)
        config_path = company_dir / "config.yaml"
        try:
            cfg = load_config(config_path)
            agent_count = str(len(cfg.agents))
            name = cfg.name
        except Exception:
            name = slug
            agent_count = "?"
        table.add_row(name, slug, str(company_dir), agent_count)

    console.print(table)


# ------------------------------------------------------------------
# destroy
# ------------------------------------------------------------------


@app.command()
def destroy(
    company: str = typer.Option(
        None,
        "--company",
        help="Company slug to destroy (overrides global -C, defaults to selected company)",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Permanently delete a company and all its data."""
    import shutil
    from agent_company_ai.config import get_company_dir, load_config, maybe_migrate_legacy_layout

    target = company or _selected_company
    maybe_migrate_legacy_layout()
    company_dir = get_company_dir(company=target, create=False)

    if not company_dir.exists():
        console.print(f"[red]No company found at {company_dir}[/red]")
        raise typer.Exit(1)

    # Show what will be deleted
    config_path = company_dir / "config.yaml"
    company_name = target
    agent_count = 0
    if config_path.exists():
        try:
            cfg = load_config(config_path)
            company_name = cfg.name
            agent_count = len(cfg.agents)
        except Exception:
            pass

    console.print(f"\n[bold red]This will permanently delete:[/bold red]")
    console.print(f"  Company: [bold]{company_name}[/bold] (slug: {target})")
    console.print(f"  Agents:  {agent_count}")
    console.print(f"  Path:    {company_dir}\n")

    if not yes:
        typer.confirm("Are you sure?", abort=True)

    # Gracefully shut down the company if possible
    async def _shutdown():
        try:
            from agent_company_ai.core.company import Company
            co = await Company.load(company=target)
            await co.shutdown()
        except Exception:
            pass  # DB might be corrupted — that's fine, we're deleting anyway

    _run(_shutdown())

    shutil.rmtree(company_dir)
    console.print(f"[bold green]Company '{company_name}' destroyed.[/bold green]")


# ------------------------------------------------------------------
# profit-engine sub-commands
# ------------------------------------------------------------------

profit_engine_app = typer.Typer(
    name="profit-engine",
    help="Configure the company's business model DNA (ProfitEngine).",
    no_args_is_help=True,
)
app.add_typer(profit_engine_app, name="profit-engine")


@profit_engine_app.command("templates")
def pe_templates():
    """List available ProfitEngine preset templates."""
    from agent_company_ai.config import list_profit_engine_templates, load_profit_engine_template

    names = list_profit_engine_templates()
    if not names:
        console.print("[yellow]No templates found.[/yellow]")
        return

    table = Table(title="ProfitEngine Templates")
    table.add_column("Name", style="cyan bold")
    table.add_column("Display Name")
    table.add_column("Description")

    for name in names:
        tmpl = load_profit_engine_template(name)
        table.add_row(name, tmpl.get("display_name", name), tmpl.get("description", ""))

    console.print(table)


@profit_engine_app.command("setup")
def pe_setup(
    template: str = typer.Option(None, "--template", "-t", help="Start from a preset template (saas, ecommerce, marketplace, agency, consulting, content)"),
):
    """Interactive wizard to configure the company's business model DNA.

    Optionally start from a preset template, then customize each field.
    The result is saved to config.yaml under the profit_engine section.
    """
    from agent_company_ai.config import (
        load_config, save_config, get_company_dir,
        load_profit_engine_template, list_profit_engine_templates,
        ProfitEngineConfig, maybe_migrate_legacy_layout,
    )

    maybe_migrate_legacy_layout()
    company_dir = get_company_dir(company=_selected_company, create=False)
    config_path = company_dir / "config.yaml"
    if not config_path.exists():
        console.print("[red]No company found.[/red] Run 'agent-company-ai init' first.")
        raise typer.Exit(1)

    config = load_config(config_path)

    # Template selection
    defaults: dict[str, str] = {}
    if template is None:
        available = list_profit_engine_templates()
        console.print("\n[bold]Choose a business model template (or skip for blank):[/bold]")
        for i, name in enumerate(available, 1):
            tmpl = load_profit_engine_template(name)
            console.print(f"  [cyan][{i}][/cyan] {tmpl.get('display_name', name)}")
        console.print(f"  [cyan][{len(available) + 1}][/cyan] Start from scratch")
        choice = console.input(f"\nSelect [1-{len(available) + 1}]: ").strip()
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(available):
                template = available[idx]
        except (ValueError, IndexError):
            pass

    if template:
        try:
            tmpl = load_profit_engine_template(template)
            defaults = {k: tmpl.get(k, "") for k in [
                "mission", "revenue_streams", "target_customers",
                "pricing_model", "competitive_edge", "key_metrics",
                "cost_priorities", "additional_context",
            ]}
            console.print(f"\n[green]Loaded template: {tmpl.get('display_name', template)}[/green]")
        except FileNotFoundError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)

    # Field-by-field customization
    fields = [
        ("mission", "Mission", "What is the company's core purpose?"),
        ("revenue_streams", "Revenue Streams", "How does the company make money?"),
        ("target_customers", "Target Customers", "Who are the ideal customers?"),
        ("pricing_model", "Pricing Model", "How is the product/service priced?"),
        ("competitive_edge", "Competitive Edge", "What sets the company apart?"),
        ("key_metrics", "Key Metrics", "What metrics define success?"),
        ("cost_priorities", "Cost Priorities", "Where should money be spent first?"),
        ("additional_context", "Additional Context", "Any other business context?"),
    ]

    console.print("\n[bold]Customize each field[/bold] (press Enter to keep the default):\n")
    values: dict[str, str] = {}
    for field_key, label, hint in fields:
        default = defaults.get(field_key, "")
        if default:
            console.print(f"  [bold]{label}[/bold] [dim]({hint})[/dim]")
            console.print(f"  [dim]Default: {default[:100]}{'...' if len(default) > 100 else ''}[/dim]")
            entered = console.input("  > ").strip()
            values[field_key] = entered if entered else default
        else:
            console.print(f"  [bold]{label}[/bold] [dim]({hint})[/dim]")
            values[field_key] = console.input("  > ").strip()

    # Save
    config.profit_engine = ProfitEngineConfig(enabled=True, **values)
    save_config(config, config_path)

    console.print(Panel(
        config.profit_engine.format_dna() or "[dim]No DNA configured (all fields empty).[/dim]",
        title="ProfitEngine DNA Saved",
        border_style="green",
    ))
    console.print("[green]Business DNA will now be injected into all agent prompts.[/green]")


@profit_engine_app.command("show")
def pe_show():
    """Display the current business model DNA."""
    from agent_company_ai.config import load_config, get_company_dir, maybe_migrate_legacy_layout

    maybe_migrate_legacy_layout()
    company_dir = get_company_dir(company=_selected_company, create=False)
    config_path = company_dir / "config.yaml"
    if not config_path.exists():
        console.print("[red]No company found.[/red] Run 'agent-company-ai init' first.")
        raise typer.Exit(1)

    config = load_config(config_path)
    pe = config.profit_engine

    if not pe.enabled:
        console.print("[yellow]ProfitEngine is disabled.[/yellow] Run 'agent-company-ai profit-engine setup' to configure.")
        return

    dna = pe.format_dna()
    if not dna:
        console.print("[yellow]ProfitEngine is enabled but all fields are empty.[/yellow]")
        return

    console.print(Panel(dna, title="ProfitEngine — Business DNA", border_style="cyan"))

    # Also show raw field values
    table = Table(title="Field Values")
    table.add_column("Field", style="bold")
    table.add_column("Value")
    for field_name in [
        "mission", "revenue_streams", "target_customers", "pricing_model",
        "competitive_edge", "key_metrics", "cost_priorities", "additional_context",
    ]:
        val = getattr(pe, field_name, "")
        table.add_row(field_name, val[:120] + ("..." if len(val) > 120 else "") if val else "[dim]empty[/dim]")
    console.print(table)


@profit_engine_app.command("edit")
def pe_edit(
    field: str = typer.Argument(help="Field to edit: mission, revenue_streams, target_customers, pricing_model, competitive_edge, key_metrics, cost_priorities, additional_context"),
):
    """Edit a single ProfitEngine field."""
    from agent_company_ai.config import load_config, save_config, get_company_dir, maybe_migrate_legacy_layout

    valid_fields = [
        "mission", "revenue_streams", "target_customers", "pricing_model",
        "competitive_edge", "key_metrics", "cost_priorities", "additional_context",
    ]
    if field not in valid_fields:
        console.print(f"[red]Unknown field '{field}'.[/red] Valid fields: {', '.join(valid_fields)}")
        raise typer.Exit(1)

    maybe_migrate_legacy_layout()
    company_dir = get_company_dir(company=_selected_company, create=False)
    config_path = company_dir / "config.yaml"
    if not config_path.exists():
        console.print("[red]No company found.[/red] Run 'agent-company-ai init' first.")
        raise typer.Exit(1)

    config = load_config(config_path)
    current = getattr(config.profit_engine, field, "")

    console.print(f"[bold]Editing: {field}[/bold]")
    if current:
        console.print(f"[dim]Current: {current}[/dim]")
    new_value = console.input("> ").strip()

    if not new_value:
        console.print("[yellow]No change (empty input).[/yellow]")
        return

    setattr(config.profit_engine, field, new_value)
    if not config.profit_engine.enabled:
        config.profit_engine.enabled = True
    save_config(config, config_path)
    console.print(f"[green]{field} updated.[/green]")


@profit_engine_app.command("disable")
def pe_disable():
    """Disable ProfitEngine — removes DNA from all agent prompts."""
    from agent_company_ai.config import load_config, save_config, get_company_dir, maybe_migrate_legacy_layout

    maybe_migrate_legacy_layout()
    company_dir = get_company_dir(company=_selected_company, create=False)
    config_path = company_dir / "config.yaml"
    if not config_path.exists():
        console.print("[red]No company found.[/red]")
        raise typer.Exit(1)

    config = load_config(config_path)
    config.profit_engine.enabled = False
    save_config(config, config_path)
    console.print("[green]ProfitEngine disabled.[/green] Business DNA will no longer be injected into agent prompts.")
    console.print("[dim]Your configuration is preserved — run 'profit-engine setup' or set enabled=True to re-enable.[/dim]")


# ------------------------------------------------------------------
# wallet sub-commands
# ------------------------------------------------------------------

wallet_app = typer.Typer(
    name="wallet",
    help="Manage the company blockchain wallet.",
    no_args_is_help=True,
)
app.add_typer(wallet_app, name="wallet")


@wallet_app.command("create")
def wallet_create():
    """Generate a new Ethereum wallet with encrypted keystore."""
    from agent_company_ai.core.company import Company
    from agent_company_ai.config import save_config

    password = console.input("[bold]Set wallet password: [/bold]", password=True)
    confirm = console.input("[bold]Confirm password: [/bold]", password=True)
    if password != confirm:
        console.print("[red]Passwords do not match.[/red]")
        raise typer.Exit(1)

    async def _create():
        company = await Company.load(company=_selected_company)
        if company.wallet_manager.has_wallet():
            console.print("[yellow]Wallet already exists.[/yellow]")
            addr = company.wallet_manager.address
            await company.shutdown()
            return addr, False

        addr = company.wallet_manager.create(password)
        company.config.wallet.enabled = True
        save_config(company.config, company.company_dir / "config.yaml")
        await company.wallet_manager.register_wallet_in_db()
        await company.shutdown()
        return addr, True

    addr, created = _run(_create())

    if created:
        console.print(Panel(
            f"[bold green]Wallet created![/bold green]\n\n"
            f"Address: [cyan]{addr}[/cyan]\n\n"
            f"[dim]Your keystore is encrypted with your password.\n"
            f"This address works on Ethereum, Base, Arbitrum, and Polygon.\n"
            f"Fund it to start transacting.[/dim]",
            title="Blockchain Wallet",
        ))
    else:
        console.print(f"Wallet address: [cyan]{addr}[/cyan]")


@wallet_app.command("balance")
def wallet_balance(
    chain: str = typer.Option(None, "--chain", "-c", help="Chain name (ethereum, base, arbitrum, polygon)"),
):
    """Show native token balances across all supported chains."""
    from agent_company_ai.core.company import Company

    async def _balance():
        company = await Company.load(company=_selected_company)
        result = company.wallet_manager.get_balance(chain_name=chain)
        await company.shutdown()
        return result

    result = _run(_balance())

    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        raise typer.Exit(1)

    if chain:
        # Single chain
        info = result[chain]
        if info.get("error"):
            console.print(f"[yellow]{chain}:[/yellow] error - {info['error']}")
        else:
            console.print(f"[bold]{chain}:[/bold] {info['balance']} {info['symbol']}")
    else:
        # All chains table
        table = Table(title="Wallet Balances")
        table.add_column("Chain", style="cyan")
        table.add_column("Balance", justify="right")
        table.add_column("Symbol")
        table.add_column("Status", style="dim")

        for name, info in result.items():
            err = info.get("error")
            table.add_row(
                name,
                info["balance"],
                info["symbol"],
                f"[red]{err}[/red]" if err else "[green]OK[/green]",
            )
        console.print(table)


@wallet_app.command("address")
def wallet_address():
    """Show the company wallet address."""
    from agent_company_ai.core.company import Company

    async def _address():
        company = await Company.load(company=_selected_company)
        addr = company.wallet_manager.address
        await company.shutdown()
        return addr

    addr = _run(_address())
    if addr is None:
        console.print("[yellow]No wallet found.[/yellow] Run 'agent-company-ai wallet create' first.")
        raise typer.Exit(1)

    console.print(Panel(
        f"[cyan]{addr}[/cyan]\n\n"
        f"[dim]Same address on Ethereum, Base, Arbitrum, and Polygon.[/dim]",
        title="Wallet Address",
    ))


@wallet_app.command("send")
def wallet_send(
    amount: str = typer.Argument(help="Amount to send (e.g. 0.01)"),
    to: str = typer.Option(..., "--to", "-t", help="Recipient address (0x...)"),
    chain: str = typer.Option("ethereum", "--chain", "-c", help="Chain to send on"),
):
    """Send native tokens (human-initiated). Requires password confirmation."""
    from agent_company_ai.core.company import Company
    from agent_company_ai.wallet.chains import get_chain

    chain_info = get_chain(chain)

    console.print(f"\n[bold]Send {amount} {chain_info.native_symbol} on {chain}[/bold]")
    console.print(f"  To: {to}")
    console.print(f"  Explorer: {chain_info.explorer_url}\n")

    typer.confirm("Confirm this transaction?", abort=True)
    password = console.input("[bold]Wallet password: [/bold]", password=True)

    async def _send():
        company = await Company.load(company=_selected_company)
        from agent_company_ai.wallet.keystore import decrypt_key
        try:
            key = decrypt_key(company.wallet_dir, password)
            tx_hash = company.wallet_manager.provider.send_transaction(
                private_key=key,
                to_address=to,
                amount_ether=amount,
                chain_name=chain,
            )
        except Exception as e:
            await company.shutdown()
            raise e
        await company.shutdown()
        return tx_hash

    try:
        tx_hash = _run(_send())
        console.print(Panel(
            f"[bold green]Transaction sent![/bold green]\n\n"
            f"Tx: [cyan]{tx_hash}[/cyan]\n"
            f"Explorer: {chain_info.explorer_url}/tx/{tx_hash}",
            title="Transaction Sent",
        ))
    except Exception as e:
        console.print(f"[red]Transaction failed: {e}[/red]")
        raise typer.Exit(1)


@wallet_app.command("payments")
def wallet_payments(
    status: str = typer.Option(None, "--status", "-s", help="Filter by status (pending, approved, rejected, sent, failed)"),
):
    """Show the payment approval queue."""
    from agent_company_ai.core.company import Company

    async def _payments():
        company = await Company.load(company=_selected_company)
        payments = await company.wallet_manager.list_payments(status=status)
        await company.shutdown()
        return payments

    payments = _run(_payments())

    if not payments:
        console.print("[dim]No payments in queue.[/dim]")
        return

    table = Table(title="Payment Queue")
    table.add_column("ID", style="dim")
    table.add_column("Amount", justify="right")
    table.add_column("Token")
    table.add_column("Chain", style="cyan")
    table.add_column("To", style="dim")
    table.add_column("Status")
    table.add_column("Requested By")
    table.add_column("Reason")

    status_colors = {
        "pending": "yellow", "approved": "blue", "rejected": "red",
        "sent": "green", "failed": "red",
    }

    for p in payments:
        color = status_colors.get(p["status"], "white")
        table.add_row(
            p["id"],
            p["amount"],
            p["token"],
            p["chain"],
            p["to_address"][:12] + "...",
            f"[{color}]{p['status']}[/{color}]",
            p.get("requested_by", "-") or "-",
            (p.get("reason", "") or "")[:40],
        )

    console.print(table)


@wallet_app.command("approve")
def wallet_approve(
    payment_id: str = typer.Argument(help="Payment ID to approve"),
):
    """Approve and send a pending payment."""
    from agent_company_ai.core.company import Company

    async def _get_payment():
        company = await Company.load(company=_selected_company)
        payment = await company.wallet_manager.get_payment(payment_id)
        return company, payment

    company_inst, payment = _run(_get_payment())

    if payment is None:
        console.print(f"[red]Payment {payment_id} not found.[/red]")
        raise typer.Exit(1)

    if payment["status"] != "pending":
        console.print(f"[yellow]Payment is '{payment['status']}', not pending.[/yellow]")
        raise typer.Exit(1)

    console.print(Panel(
        f"Amount:  [bold]{payment['amount']} {payment['token']}[/bold]\n"
        f"Chain:   {payment['chain']}\n"
        f"To:      {payment['to_address']}\n"
        f"Reason:  {payment.get('reason', 'N/A')}\n"
        f"By:      {payment.get('requested_by', 'N/A')}",
        title=f"Payment {payment_id}",
    ))

    typer.confirm("Approve and send this payment?", abort=True)
    password = console.input("[bold]Wallet password: [/bold]", password=True)

    async def _approve():
        # Reuse the loaded company
        tx_hash = await company_inst.wallet_manager.approve_and_send(payment_id, password)
        await company_inst.shutdown()
        return tx_hash

    try:
        tx_hash = _run(_approve())
        from agent_company_ai.wallet.chains import get_chain
        chain_info = get_chain(payment["chain"])
        console.print(Panel(
            f"[bold green]Payment approved and sent![/bold green]\n\n"
            f"Tx: [cyan]{tx_hash}[/cyan]\n"
            f"Explorer: {chain_info.explorer_url}/tx/{tx_hash}",
            title="Payment Sent",
        ))
    except Exception as e:
        console.print(f"[red]Failed: {e}[/red]")
        _run(company_inst.shutdown())
        raise typer.Exit(1)


@wallet_app.command("reject")
def wallet_reject(
    payment_id: str = typer.Argument(help="Payment ID to reject"),
):
    """Reject a pending payment."""
    from agent_company_ai.core.company import Company

    async def _reject():
        company = await Company.load(company=_selected_company)
        await company.wallet_manager.reject_payment(payment_id)
        await company.shutdown()

    try:
        _run(_reject())
        console.print(f"[bold]Payment {payment_id} rejected.[/bold]")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
