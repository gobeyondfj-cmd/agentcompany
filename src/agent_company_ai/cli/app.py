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


@app.callback()
def main(
    company: str = typer.Option(
        "default",
        "--company",
        "-C",
        help="Company slug to operate on",
        envvar="AGENT_COMPANY_NAME",
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
):
    """Initialize a new AI agent company in the current directory."""
    from agent_company_ai.core.company import Company
    from agent_company_ai.config import save_config, LLMProviderConfig

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

    # Interactive provider selection when --provider not given
    chosen_provider = provider
    chosen_key = api_key
    chosen_model = model
    chosen_base_url = base_url

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
            elif chosen_provider == "openai-compat":
                chosen_base_url = console.input("Base URL (e.g. http://localhost:8000/v1): ").strip()

        # API key: use flag > prompt > env var placeholder
        if not chosen_key:
            if chosen_provider == "ollama":
                chosen_key = "ollama"  # Ollama doesn't need a real key
            elif env_var:
                chosen_key = console.input(
                    f"API key (or press Enter to use ${{{env_var}}}): "
                ).strip() or f"${{{env_var}}}"
            else:
                chosen_key = console.input("API key (or press Enter to skip): ").strip() or ""

        # Model: use flag > prompt with preset default
        if not chosen_model:
            if preset_model:
                entered = console.input(
                    f"Model [{preset_model}]: "
                ).strip()
                chosen_model = entered or preset_model
            else:
                chosen_model = console.input("Model name: ").strip()

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

    console.print(Panel(
        f"[bold green]Company '{name}' initialized![/bold green]\n\n"
        f"Directory: {company_dir}\n"
        f"Config: {company_dir / 'config.yaml'}\n"
        f"{provider_line}\n"
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
        "done": "green", "failed": "red", "in_progress": "yellow",
        "pending": "dim", "assigned": "blue", "review": "magenta",
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
        await company.shutdown()
        return summary

    with console.status("[bold green]Company is running autonomously..."):
        summary = _run(_run_goal())

    console.print(Panel(summary, title="Goal Summary"))


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

    console.print(Panel(
        f"[bold]{s['name']}[/bold]\n\n"
        f"Agents: {s['agents']}\n"
        f"Tasks: {s['tasks']}\n"
        f"Running: {'Yes' if s['running'] else 'No'}",
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
    model: str = typer.Option(None, "--model", "-m", help="Model for all agents"),
    list_presets: bool = typer.Option(False, "--list", "-l", help="List available presets"),
):
    """Set up a full company with agents in one command.

    Initializes the company (if needed) and batch-hires a team based on a
    preset template. Each preset is a sensible org chart for that business type.

    Examples:
      agent-company-ai setup tech_startup --name "Acme AI"
      agent-company-ai setup saas --name "CloudCo" --provider anthropic
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
        from agent_company_ai.config import get_company_dir
        company_dir = get_company_dir(company=_selected_company)
        config_path = company_dir / "config.yaml"

        if config_path.exists():
            company = await Company.load(company=_selected_company)
            # Update name if different
            if company.config.name != company_name and company_name != "My AI Company":
                company.config.name = company_name
                from agent_company_ai.config import save_config
                save_config(company.config, config_path)
        else:
            company = await Company.init(name=company_name, company=_selected_company)

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


if __name__ == "__main__":
    app()
