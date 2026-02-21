"""CLI for AgentCompany - manage your AI agent company from the terminal."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree

app = typer.Typer(
    name="agentcompany",
    help="Spin up an AI agent company - a business run by AI agents, managed by you.",
    no_args_is_help=True,
)
console = Console()


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
):
    """Initialize a new AI agent company in the current directory."""
    from agentcompany.core.company import Company

    async def _init():
        company = await Company.init(name=name)
        return company

    company = _run(_init())
    console.print(Panel(
        f"[bold green]Company '{name}' initialized![/bold green]\n\n"
        f"Directory: {company.company_dir}\n"
        f"Config: {company.company_dir / 'config.yaml'}\n\n"
        f"Next steps:\n"
        f"  agentcompany hire ceo --name Alice\n"
        f"  agentcompany hire developer --name Bob\n"
        f"  agentcompany team",
        title="AgentCompany",
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
    from agentcompany.core.company import Company

    async def _hire():
        company = await Company.load()
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
    from agentcompany.core.company import Company

    async def _fire():
        company = await Company.load()
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
    from agentcompany.core.company import Company

    async def _team():
        company = await Company.load()
        agents = company.list_agents()
        await company.shutdown()
        return company.config.name, agents

    company_name, agents = _run(_team())

    if not agents:
        console.print("[yellow]No agents hired yet.[/yellow] Use 'agentcompany hire <role>' to get started.")
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
    from agentcompany.core.company import Company

    async def _assign():
        company = await Company.load()
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
    from agentcompany.core.company import Company

    async def _tasks():
        company = await Company.load()
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
    from agentcompany.core.company import Company

    async def _chat():
        company = await Company.load()
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
    from agentcompany.core.company import Company

    async def _broadcast():
        company = await Company.load()
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
    from agentcompany.core.company import Company

    async def _run_goal():
        company = await Company.load()

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
    from agentcompany.core.company import Company

    async def _status():
        company = await Company.load()
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
    from agentcompany.dashboard.server import run_dashboard

    console.print(f"[bold green]Starting dashboard at http://{host}:{port}[/bold green]")
    run_dashboard(host=host, port=port)


# ------------------------------------------------------------------
# roles
# ------------------------------------------------------------------


@app.command()
def roles():
    """List all available preset roles."""
    from agentcompany.config import list_available_roles

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
      agentcompany setup tech_startup --name "Acme AI"
      agentcompany setup saas --name "CloudCo" --provider anthropic
      agentcompany setup --list
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
                "\n[dim]Usage: agentcompany setup <preset> --name \"My Company\"[/dim]"
            )
        return

    if company_type not in COMPANY_PRESETS:
        console.print(f"[red]Unknown preset '{company_type}'.[/red] Use --list to see options.")
        raise typer.Exit(1)

    preset = COMPANY_PRESETS[company_type]
    from agentcompany.core.company import Company

    async def _setup():
        # Init company if not already
        from agentcompany.config import get_company_dir
        company_dir = get_company_dir()
        config_path = company_dir / "config.yaml"

        if config_path.exists():
            company = await Company.load()
            # Update name if different
            if company.config.name != company_name and company_name != "My AI Company":
                company.config.name = company_name
                from agentcompany.config import save_config
                save_config(company.config, config_path)
        else:
            company = await Company.init(name=company_name)

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

    console.print(f"\n[dim]Next: agentcompany run \"Your goal here\"[/dim]")
    console.print(f"[dim]Edit: agentcompany hire/fire/team to adjust the team[/dim]")


if __name__ == "__main__":
    app()
