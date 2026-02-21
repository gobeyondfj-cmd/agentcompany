"""Company - the top-level orchestrator for the AI agent company."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Callable, Awaitable

from agent_company_ai.config import (
    CompanyConfig,
    load_config,
    save_config,
    get_company_dir,
    maybe_migrate_legacy_layout,
    AgentConfig,
)
from agent_company_ai.core.agent import Agent
from agent_company_ai.core.cost_tracker import CostTracker
from agent_company_ai.core.message_bus import MessageBus, BusMessage
from agent_company_ai.core.role import load_role
from agent_company_ai.core.task import Task, TaskBoard, TaskStatus
from agent_company_ai.llm.router import LLMRouter
from agent_company_ai.storage.database import Database, get_database
from agent_company_ai.tools.file_io import set_workspace, set_output_dir
from agent_company_ai.tools.wallet_tools import set_wallet_manager
from agent_company_ai.wallet.manager import WalletManager

logger = logging.getLogger("agent_company_ai.company")


class Company:
    """A virtual company staffed by AI agents.

    The Company manages agents, tasks, and communication. It supports
    both interactive use (assign individual tasks) and autonomous mode
    (CEO breaks down a goal and delegates automatically).
    """

    def __init__(
        self,
        config: CompanyConfig,
        company_dir: Path,
        db: Database,
    ):
        self.config = config
        self.company_dir = company_dir
        self.db = db
        self.bus = MessageBus()
        self.task_board = TaskBoard()
        self.router = LLMRouter(config.llm)
        self.cost_tracker = CostTracker()
        self.agents: dict[str, Agent] = {}
        self._running = False
        self._stop_requested = False
        self._on_event: Callable[[str, dict], Awaitable[None]] | None = None

        # Set workspace for file tools
        workspace = company_dir.parent
        set_workspace(workspace)

        # Set output directory for deliverables
        self.output_dir = company_dir / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        set_output_dir(self.output_dir)

        # Wallet manager
        self.wallet_dir = company_dir / "wallet"
        self.wallet_manager = WalletManager(self.wallet_dir, db)
        if config.wallet.enabled and self.wallet_manager.has_wallet():
            set_wallet_manager(self.wallet_manager)

        # Global message listener for persistence
        self.bus.set_global_listener(self._on_bus_message)

    @classmethod
    async def load(cls, base_path: Path | None = None, company: str = "default") -> Company:
        """Load an existing company from a .agent-company-ai directory."""
        maybe_migrate_legacy_layout(base_path)
        company_dir = get_company_dir(company, base_path)
        config_path = company_dir / "config.yaml"

        if not config_path.exists():
            raise FileNotFoundError(
                f"No company found at {company_dir}. Run 'agent-company-ai init' first."
            )

        config = load_config(config_path)
        db = get_database(company_dir)
        await db.connect()

        company = cls(config=config, company_dir=company_dir, db=db)

        # Restore agents from config
        for agent_cfg in config.agents:
            try:
                await company._add_agent_from_config(agent_cfg)
            except Exception as e:
                logger.warning(f"Failed to restore agent {agent_cfg.name}: {e}")

        # Register wallet in DB if it exists
        if company.wallet_manager.has_wallet():
            await company.wallet_manager.register_wallet_in_db()

        return company

    @classmethod
    async def init(cls, base_path: Path | None = None, name: str = "My AI Company", company: str = "default") -> Company:
        """Initialize a new company in the given directory."""
        maybe_migrate_legacy_layout(base_path)
        company_dir = get_company_dir(company, base_path)
        config_path = company_dir / "config.yaml"

        config = CompanyConfig(name=name)
        save_config(config, config_path)

        db = get_database(company_dir)
        await db.connect()

        return cls(config=config, company_dir=company_dir, db=db)

    def set_event_handler(self, handler: Callable[[str, dict], Awaitable[None]]) -> None:
        """Set a callback for company events (used by dashboard)."""
        self._on_event = handler

    async def _emit(self, event: str, data: dict) -> None:
        if self._on_event:
            await self._on_event(event, data)

    async def _on_bus_message(self, msg: BusMessage) -> None:
        """Persist messages and emit events."""
        await self.db.execute(
            "INSERT INTO messages (id, from_agent, to_agent, content, topic, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                uuid.uuid4().hex[:12],
                msg.from_agent,
                msg.to_agent,
                msg.content,
                msg.topic,
                msg.timestamp.isoformat(),
            ),
        )
        await self._emit("message", {
            "from": msg.from_agent,
            "to": msg.to_agent,
            "content": msg.content,
            "topic": msg.topic,
        })

    # ------------------------------------------------------------------
    # Agent management
    # ------------------------------------------------------------------

    async def hire(
        self,
        role_name: str,
        agent_name: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> Agent:
        """Hire a new agent with the given role."""
        role = load_role(role_name)
        name = agent_name or role.title.replace(" ", "")

        if name in self.agents:
            raise ValueError(f"Agent '{name}' already exists.")

        agent_config = AgentConfig(
            name=name,
            role=role_name,
            provider=provider,
            model=model,
        )

        agent = await self._add_agent_from_config(agent_config)

        # Persist to config
        self.config.agents.append(agent_config)
        save_config(self.config, self.company_dir / "config.yaml")

        # Persist to DB
        await self.db.execute(
            "INSERT OR REPLACE INTO agents (id, name, role, provider, model, status) "
            "VALUES (?, ?, ?, ?, ?, 'active')",
            (name, name, role_name, provider or "", model or ""),
        )

        await self._emit("agent.hired", {"name": name, "role": role_name})
        logger.info(f"Hired {name} as {role.title}")
        return agent

    async def _add_agent_from_config(self, cfg: AgentConfig) -> Agent:
        """Internal: create an Agent instance from config.

        The LLM provider is resolved lazily -- if the provider isn't
        configured yet (e.g. no API key), the agent is still created so
        the org chart and team roster work. The provider will be resolved
        on the first actual LLM call.
        """
        role = load_role(cfg.role)
        try:
            provider = self.router.get_provider(
                provider_name=cfg.provider,
                model_override=cfg.model,
            )
        except (ValueError, KeyError):
            provider = None  # type: ignore[assignment]
            logger.debug(f"Provider not yet available for {cfg.name}, will resolve later")

        team_members = [
            f"{a.name} ({a.role})" for a in self.config.agents if a.name != cfg.name
        ]
        profit_engine_dna = self.config.profit_engine.format_dna()
        agent = Agent(
            name=cfg.name,
            role=role,
            provider=provider,
            message_bus=self.bus,
            db=self.db,
            company_name=self.config.name,
            team_members=team_members,
            cost_tracker=self.cost_tracker,
            profit_engine_dna=profit_engine_dna,
        )
        self.agents[cfg.name] = agent
        return agent

    async def fire(self, agent_name: str) -> None:
        """Remove an agent from the company."""
        if agent_name not in self.agents:
            raise ValueError(f"No agent named '{agent_name}'.")

        self.agents[agent_name].shutdown()
        del self.agents[agent_name]

        self.config.agents = [a for a in self.config.agents if a.name != agent_name]
        save_config(self.config, self.company_dir / "config.yaml")

        await self.db.execute(
            "UPDATE agents SET status = 'fired' WHERE name = ?", (agent_name,)
        )
        await self._emit("agent.fired", {"name": agent_name})

    def get_agent(self, name: str) -> Agent | None:
        return self.agents.get(name)

    def get_agent_by_role(self, role_name: str) -> Agent | None:
        for agent in self.agents.values():
            if agent.role.name == role_name:
                return agent
        return None

    def list_agents(self) -> list[dict]:
        return [
            {
                "name": a.name,
                "role": a.role.name,
                "title": a.role.title,
                "reports_to": a.role.reports_to,
            }
            for a in self.agents.values()
        ]

    # ------------------------------------------------------------------
    # Org chart
    # ------------------------------------------------------------------

    def get_org_chart(self) -> dict:
        """Build an org chart tree structure.

        Returns a tree rooted at 'owner' with agents as nodes.
        """
        agents = self.list_agents()
        nodes: dict[str, dict] = {
            "owner": {
                "name": "You (Owner)",
                "role": "owner",
                "title": "Company Owner",
                "children": [],
            }
        }

        # Create nodes for all agents
        for a in agents:
            nodes[a["name"]] = {**a, "children": []}

        # Build tree
        for a in agents:
            parent_key = a["reports_to"]
            if parent_key == "owner":
                nodes["owner"]["children"].append(nodes[a["name"]])
            else:
                # Find parent by role name
                parent = next(
                    (ag for ag in agents if ag["role"] == parent_key),
                    None,
                )
                if parent and parent["name"] in nodes:
                    nodes[parent["name"]]["children"].append(nodes[a["name"]])
                else:
                    # Orphan - attach to owner
                    nodes["owner"]["children"].append(nodes[a["name"]])

        return nodes["owner"]

    # ------------------------------------------------------------------
    # Task management
    # ------------------------------------------------------------------

    async def assign(
        self,
        description: str,
        assignee: str | None = None,
    ) -> Task:
        """Create a task and optionally assign it to an agent."""
        task = Task.create(description=description, assignee=assignee)
        self.task_board.add(task)

        # Persist
        await self.db.execute(
            "INSERT INTO tasks (id, description, assignee_id, status, priority) "
            "VALUES (?, ?, ?, ?, ?)",
            (task.id, task.description, task.assignee, task.status.value, task.priority),
        )

        await self._emit("task.created", task.to_dict())

        # If assigned, start processing
        if assignee and assignee in self.agents:
            asyncio.create_task(self._run_task(task))

        return task

    async def _persist_task(self, task: Task) -> None:
        """Insert a task into the database so FOREIGN KEY constraints are met."""
        await self.db.execute(
            "INSERT OR IGNORE INTO tasks (id, description, assignee_id, status, priority, parent_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (task.id, task.description, task.assignee, task.status.value, task.priority, task.parent_id),
        )

    async def _run_task(self, task: Task) -> str:
        """Run a task with its assigned agent."""
        agent = self.agents.get(task.assignee or "")
        if not agent:
            task.fail(f"No agent named '{task.assignee}'")
            return task.result or ""

        await self._emit("task.started", task.to_dict())
        max_iter = self.config.autonomous.max_agent_iterations
        result = await agent.think(task, max_iterations=max_iter)

        # Emit cost update
        await self._emit("cost.updated", self.cost_tracker.summary())

        # Update DB
        artifacts_json = json.dumps(task.artifacts)
        await self.db.execute(
            "UPDATE tasks SET status = ?, result = ?, artifacts_json = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (task.status.value, task.result, artifacts_json, task.id),
        )
        await self._emit("task.updated", task.to_dict())

        # Process any delegated subtasks
        for subtask in task.subtasks:
            if not subtask.is_terminal:
                await self._handle_delegation(subtask)

        return result

    async def _handle_delegation(self, subtask: Task) -> None:
        """Find the right agent for a delegated subtask and run it."""
        # Try to find agent by matching role from the delegation
        # The subtask doesn't have an assignee yet - find from bus history
        for msg in reversed(self.bus.get_history(limit=20, topic="task.delegate")):
            try:
                data = json.loads(msg.content)
                if data.get("task_id") == subtask.id:
                    to_role = data["to_role"]
                    agent = self.get_agent_by_role(to_role)
                    if agent:
                        subtask.assign(agent.name)
                        self.task_board.add(subtask)
                        await self._persist_task(subtask)
                        await self._run_task(subtask)
                        return
            except (json.JSONDecodeError, KeyError):
                continue

        subtask.fail("No agent available for delegation.")

    # ------------------------------------------------------------------
    # Autonomous mode
    # ------------------------------------------------------------------

    async def run_goal(self, goal: str) -> None:
        """Autonomous mode: give the CEO a goal and let the company run.

        The system runs in **cycles**:
          1. CEO plans/re-plans by breaking the goal into tasks
          2. Agents execute delegated tasks in parallel waves
          3. CEO reviews progress and decides: DONE, FAILED, or CONTINUE
          4. If CONTINUE, loop back to step 1 with updated context

        Configurable via ``autonomous`` section in config:
          - ``max_cycles``: how many plan-execute-review loops (default 5)
          - ``max_waves_per_cycle``: delegation waves per cycle (default 10)
          - ``max_total_tasks``: hard cap on total tasks (default 50)
          - ``max_time_seconds``: wall-clock timeout, 0=unlimited (default 3600)
        """
        limits = self.config.autonomous
        self._running = True
        self._stop_requested = False
        start_time = time.monotonic()

        # Persist goal
        goal_id = uuid.uuid4().hex[:12]
        await self.db.execute(
            "INSERT INTO goals (id, description, status) VALUES (?, ?, 'active')",
            (goal_id, goal),
        )

        # Find the CEO
        ceo = self.get_agent_by_role("ceo")
        if not ceo:
            raise ValueError(
                "No CEO agent found. Hire a CEO first: agent-company-ai hire ceo"
            )

        logger.info(f"Starting autonomous mode with goal: {goal}")
        logger.info(
            f"Limits: {limits.max_cycles} cycles, "
            f"{limits.max_waves_per_cycle} waves/cycle, "
            f"{limits.max_total_tasks} max tasks, "
            f"{limits.max_time_seconds}s timeout"
        )
        await self._emit("goal.started", {"id": goal_id, "description": goal})

        final_status = "completed"
        cycle_results: list[str] = []
        cycle = 0

        for cycle in range(limits.max_cycles):
            # --- Check stop conditions ---
            if self._stop_requested:
                logger.info("Stop requested by user.")
                final_status = "cancelled"
                break

            elapsed = time.monotonic() - start_time
            if limits.max_time_seconds > 0 and elapsed >= limits.max_time_seconds:
                logger.warning(f"Time limit reached ({limits.max_time_seconds}s).")
                final_status = "failed"
                break

            total_tasks = len(self.task_board.list_all())
            if total_tasks >= limits.max_total_tasks:
                logger.warning(f"Task limit reached ({limits.max_total_tasks}).")
                final_status = "failed"
                break

            if limits.max_cost_usd > 0 and self.cost_tracker.total_cost >= limits.max_cost_usd:
                logger.warning(
                    f"Cost limit reached (${self.cost_tracker.total_cost:.4f} >= "
                    f"${limits.max_cost_usd:.4f})."
                )
                final_status = "failed"
                break

            logger.info(f"=== Cycle {cycle + 1}/{limits.max_cycles} ===")
            await self._emit("goal.cycle", {
                "id": goal_id,
                "cycle": cycle + 1,
                "elapsed_seconds": int(elapsed),
            })

            # --- Step 1: CEO plans (or re-plans) ---
            profit_context = ""
            profit_dna = self.config.profit_engine.format_dna()
            if profit_dna:
                profit_context = (
                    f"\n\nBUSINESS MODEL CONTEXT:\n"
                    f"All planning and review must align with the company's business DNA.\n"
                    f"{profit_dna}\n"
                )

            progress_context = ""
            if cycle > 0:
                progress_context = (
                    f"\n\nPROGRESS SO FAR (cycle {cycle + 1}):\n"
                    f"{self._build_goal_summary()}\n\n"
                    f"Based on the progress above, decide:\n"
                    f"- If the goal is ACHIEVED, report status 'done' with a summary.\n"
                    f"- If the goal CANNOT be achieved, report status 'failed' with the reason.\n"
                    f"- If more work is needed, delegate the REMAINING tasks and report "
                    f"status 'done' with your updated plan.\n"
                )

            plan_task = Task.create(
                description=(
                    f"COMPANY GOAL: {goal}\n\n"
                    f"As CEO, analyze this goal and break it down into concrete tasks "
                    f"for your team. Delegate each task to the appropriate team member "
                    f"using the delegate_task tool. Consider what each department needs "
                    f"to do. After delegating all tasks, report a summary of the plan."
                    f"{profit_context}"
                    f"{progress_context}"
                ),
                assignee=ceo.name,
            )
            self.task_board.add(plan_task)
            await self._persist_task(plan_task)
            await self._run_task(plan_task)
            cycle_results.append(plan_task.result or "")

            # --- Step 2: Execute delegated tasks in waves ---
            for wave in range(limits.max_waves_per_cycle):
                if self._stop_requested:
                    break

                pending = [
                    t for t in self.task_board.list_all()
                    if not t.is_terminal and t.assignee and t.id != plan_task.id
                ]
                if not pending:
                    break

                # Check time again
                elapsed = time.monotonic() - start_time
                if limits.max_time_seconds > 0 and elapsed >= limits.max_time_seconds:
                    break

                logger.info(f"  Wave {wave + 1}: {len(pending)} tasks")
                tasks_to_run = [
                    self._run_task(t) for t in pending
                    if t.status != TaskStatus.IN_PROGRESS
                ]
                if tasks_to_run:
                    await asyncio.gather(*tasks_to_run, return_exceptions=True)

            # --- Step 3: CEO review - ask if goal is met ---
            review_task = Task.create(
                description=(
                    f"GOAL REVIEW (cycle {cycle + 1})\n\n"
                    f"Original goal: {goal}\n\n"
                    f"Current progress:\n{self._build_goal_summary()}\n\n"
                    f"As CEO, evaluate whether the company goal has been achieved.\n"
                    f"- If ACHIEVED: report_result with status='done' and a final summary.\n"
                    f"- If NOT YET achieved but POSSIBLE: report_result with status='failed' "
                    f"and describe what still needs to be done. (The company will run another cycle.)\n"
                    f"- If IMPOSSIBLE to achieve: report_result with status='failed' and "
                    f"explain why.\n"
                    f"{profit_context}"
                ),
                assignee=ceo.name,
            )
            self.task_board.add(review_task)
            await self._persist_task(review_task)
            await self._run_task(review_task)

            # --- Step 4: Decide whether to continue ---
            if review_task.status == TaskStatus.DONE:
                logger.info("CEO reports goal achieved.")
                final_status = "completed"
                break
            else:
                # CEO says not done yet - continue to next cycle
                logger.info(f"CEO says more work needed: {(review_task.result or '')[:100]}")
                # Check if this is the last cycle
                if cycle == limits.max_cycles - 1:
                    logger.warning("Max cycles reached. Stopping.")
                    final_status = "failed"

        # --- Finalize ---
        await self.db.execute(
            "UPDATE goals SET status = ?, completed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (final_status, goal_id),
        )

        self._running = False
        summary = self._build_goal_summary()
        elapsed = time.monotonic() - start_time
        await self._emit("goal.completed", {
            "id": goal_id,
            "status": final_status,
            "summary": summary,
            "elapsed_seconds": int(elapsed),
            "cycles": min(cycle + 1, limits.max_cycles),
        })
        logger.info(f"Goal {final_status} after {int(elapsed)}s: {goal}")

    def request_stop(self) -> None:
        """Request the autonomous loop to stop after the current wave."""
        self._stop_requested = True
        logger.info("Stop requested. Will halt after current wave completes.")

    def _build_goal_summary(self) -> str:
        """Build a summary of all task outcomes."""
        tasks = self.task_board.list_all()
        lines = [f"Completed {sum(1 for t in tasks if t.status == TaskStatus.DONE)}/{len(tasks)} tasks:\n"]
        for t in tasks:
            status_icon = {
                TaskStatus.DONE: "[DONE]",
                TaskStatus.FAILED: "[FAIL]",
                TaskStatus.IN_PROGRESS: "[....]",
                TaskStatus.PENDING: "[WAIT]",
            }.get(t.status, "[????]")
            assignee = t.assignee or "unassigned"
            lines.append(f"  {status_icon} ({assignee}) {t.description[:80]}")
            if t.result:
                lines.append(f"          Result: {t.result[:120]}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Chat & broadcast
    # ------------------------------------------------------------------

    async def chat(self, agent_name: str, message: str) -> str:
        """Chat directly with an agent."""
        agent = self.agents.get(agent_name)
        if not agent:
            raise ValueError(f"No agent named '{agent_name}'.")
        return await agent.chat(message)

    async def broadcast(self, message: str) -> None:
        """Send a message to all agents."""
        await self.bus.send(
            from_agent=None,
            to_agent=None,
            content=message,
            topic="broadcast",
        )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict:
        return {
            "name": self.config.name,
            "agents": len(self.agents),
            "tasks": self.task_board.summary(),
            "running": self._running,
            "cost": self.cost_tracker.summary(),
            "output_dir": str(self.output_dir),
        }

    async def get_artifacts(self, task_id: str | None = None) -> list[dict]:
        """Query the artifacts table, optionally filtered by task_id."""
        if task_id:
            return await self.db.fetch_all(
                "SELECT * FROM artifacts WHERE task_id = ? ORDER BY created_at", (task_id,)
            )
        return await self.db.fetch_all("SELECT * FROM artifacts ORDER BY created_at")

    async def shutdown(self) -> None:
        """Clean shutdown."""
        for agent in self.agents.values():
            agent.shutdown()
        await self.db.close()
