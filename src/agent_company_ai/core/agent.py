"""Agent - an AI employee in the company."""

from __future__ import annotations

import json
import logging
import uuid
from typing import TYPE_CHECKING

from agent_company_ai.core.role import Role
from agent_company_ai.core.task import Task
from agent_company_ai.core.message_bus import MessageBus
from agent_company_ai.core.cost_tracker import CostTracker
from agent_company_ai.llm.base import LLMMessage, BaseLLMProvider, ToolDefinition
from agent_company_ai.tools.registry import ToolRegistry
from agent_company_ai.tools.file_io import copy_to_output
from agent_company_ai.tools.wallet_tools import set_current_agent

if TYPE_CHECKING:
    from agent_company_ai.storage.database import Database

logger = logging.getLogger("agent_company_ai.agent")


class Agent:
    """A single AI agent with a role, tools, and LLM backend."""

    def __init__(
        self,
        name: str,
        role: Role,
        provider: BaseLLMProvider | None,
        message_bus: MessageBus,
        db: Database,
        company_name: str = "My AI Company",
        team_members: list[str] | None = None,
        cost_tracker: CostTracker | None = None,
        profit_engine_dna: str = "",
    ):
        self.name = name
        self.role = role
        self.provider = provider
        self.bus = message_bus
        self.db = db
        self.company_name = company_name
        self._cost_tracker = cost_tracker
        self._conversation: list[LLMMessage] = []
        self._system_prompt = role.build_system_prompt(
            company_name=company_name,
            team_members=team_members or [],
            profit_engine_dna=profit_engine_dna,
        )
        self._tool_registry = ToolRegistry.get()

        # Register on message bus
        self._inbox = message_bus.register_agent(name)

    @property
    def tool_definitions(self) -> list[ToolDefinition]:
        """Get LLM-formatted tool definitions for this agent's allowed tools."""
        tools = self._tool_registry.get_tools(self.role.default_tools)
        # Add delegation tool if agent can delegate
        defs = [t.to_definition() for t in tools]
        if self.role.can_delegate_to:
            defs.append(ToolDefinition(
                name="delegate_task",
                description=(
                    f"Delegate a task to another agent. You can delegate to: "
                    f"{', '.join(self.role.can_delegate_to)}. "
                    f"Provide the agent's role name and a clear task description."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "to_role": {
                            "type": "string",
                            "description": "The role of the agent to delegate to",
                            "enum": self.role.can_delegate_to,
                        },
                        "task_description": {
                            "type": "string",
                            "description": "Clear description of the task to delegate",
                        },
                    },
                    "required": ["to_role", "task_description"],
                },
            ))
        # Add report tool
        defs.append(ToolDefinition(
            name="report_result",
            description="Report the final result of your current task back to the company.",
            parameters={
                "type": "object",
                "properties": {
                    "result": {
                        "type": "string",
                        "description": "The result or deliverable of the task",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["done", "failed"],
                        "description": "Whether the task succeeded or failed",
                    },
                },
                "required": ["result", "status"],
            },
        ))
        return defs

    async def think(self, task: Task) -> str:
        """Process a task: reason, use tools, and produce a result."""
        if self.provider is None:
            task.fail("LLM provider not configured. Set an API key in .agent-company-ai/config.yaml")
            return task.result or ""
        task.start()
        logger.info(f"[{self.name}] Starting task: {task.description}")

        # Set current agent for tool attribution (e.g. wallet payment requests)
        set_current_agent(self.name)

        # Build messages
        messages = [
            LLMMessage(role="system", content=self._system_prompt),
            LLMMessage(
                role="user",
                content=(
                    f"You have been assigned the following task:\n\n"
                    f"**Task:** {task.description}\n\n"
                    f"Use your tools to complete this task. When finished, use the "
                    f"report_result tool to submit your result."
                ),
            ),
        ]

        max_iterations = 15
        for iteration in range(max_iterations):
            try:
                response = await self.provider.complete(
                    messages=messages,
                    tools=self.tool_definitions,
                )
            except Exception as e:
                logger.error(f"[{self.name}] LLM error: {e}")
                task.fail(str(e))
                return f"Error: {e}"

            # Track cost
            self._track_usage(response.usage)

            # If the model produced text, log it
            if response.content:
                logger.info(f"[{self.name}] thinks: {response.content[:200]}")
                messages.append(LLMMessage(role="assistant", content=response.content))

            # No tool calls - we're done
            if not response.tool_calls:
                result = response.content or "No result produced."
                task.complete(result)
                return result

            # Process tool calls
            # Add the assistant message with tool_calls
            messages.append(LLMMessage(
                role="assistant",
                content=response.content or "",
                tool_calls=[
                    {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                    for tc in response.tool_calls
                ],
            ))

            for tc in response.tool_calls:
                tool_result = await self._execute_tool(tc.name, tc.arguments, task)

                # Check if task is now terminal (report_result was called)
                if task.is_terminal:
                    return task.result or "Task completed."

                messages.append(LLMMessage(
                    role="tool",
                    content=tool_result,
                    tool_call_id=tc.id,
                ))

        # Ran out of iterations
        task.fail("Exceeded maximum iterations without completing.")
        return "Failed: exceeded maximum iterations."

    async def _execute_tool(self, tool_name: str, arguments: dict, task: Task) -> str:
        """Execute a tool call and return the result string."""
        logger.info(f"[{self.name}] calling tool: {tool_name}({arguments})")

        if tool_name == "report_result":
            result = arguments.get("result", "")
            status = arguments.get("status", "done")
            if status == "done":
                task.complete(result)
                await self._register_artifact(task, "result", "text", content=result)
            else:
                task.fail(result)
            await self.bus.send(
                from_agent=self.name,
                to_agent=None,
                content=f"Task completed ({status}): {result[:200]}",
                topic="task.completed",
            )
            return f"Result reported: {status}"

        if tool_name == "delegate_task":
            to_role = arguments.get("to_role", "")
            desc = arguments.get("task_description", "")
            subtask = task.add_subtask(description=desc)
            await self.bus.send(
                from_agent=self.name,
                to_agent=None,
                content=json.dumps({
                    "action": "delegate",
                    "from": self.name,
                    "to_role": to_role,
                    "task_id": subtask.id,
                    "description": desc,
                }),
                topic="task.delegate",
            )
            return f"Task delegated to {to_role}: {desc} (subtask {subtask.id})"

        # Regular tool
        tool = self._tool_registry.get_tool(tool_name)
        if tool is None:
            return f"Error: Unknown tool '{tool_name}'"

        try:
            result = await tool.execute(**arguments)
        except Exception as e:
            return f"Tool error: {e}"

        # Track file artifacts produced by write_file
        if tool_name == "write_file" and not result.startswith("Error"):
            file_path = arguments.get("path", "")
            dest = copy_to_output(file_path, task.id)
            if dest:
                artifact_type = self._infer_artifact_type(file_path)
                await self._register_artifact(
                    task, file_path, artifact_type, content=str(dest),
                )

        return result

    async def _register_artifact(
        self, task: Task, name: str, artifact_type: str, content: str | None = None,
    ) -> dict:
        """Insert an artifact into the DB and append to task.artifacts."""
        artifact_id = uuid.uuid4().hex[:12]
        artifact = {
            "id": artifact_id,
            "task_id": task.id,
            "agent_id": self.name,
            "name": name,
            "artifact_type": artifact_type,
            "content": content,
        }
        task.artifacts.append(artifact)
        await self.db.execute(
            "INSERT INTO artifacts (id, task_id, agent_id, name, content, artifact_type) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (artifact_id, task.id, self.name, name, content, artifact_type),
        )
        return artifact

    @staticmethod
    def _infer_artifact_type(path: str) -> str:
        """Map a file extension to an artifact type."""
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        code_exts = {"py", "js", "ts", "jsx", "tsx", "java", "c", "cpp", "go", "rs", "rb", "sh", "html", "css"}
        data_exts = {"json", "csv", "xml", "yaml", "yml", "toml", "sql", "tsv"}
        if ext in code_exts:
            return "code"
        if ext in data_exts:
            return "data"
        return "file"

    async def chat(self, message: str) -> str:
        """Direct conversation with the human owner."""
        if self.provider is None:
            return "Error: LLM provider not configured. Set an API key in .agent-company-ai/config.yaml"
        if not self._conversation:
            self._conversation.append(
                LLMMessage(role="system", content=self._system_prompt)
            )

        self._conversation.append(LLMMessage(role="user", content=message))

        try:
            response = await self.provider.complete(
                messages=self._conversation,
                tools=self.tool_definitions,
            )
        except Exception as e:
            return f"Error: {e}"

        self._track_usage(response.usage)
        reply = response.content or "(no response)"
        self._conversation.append(LLMMessage(role="assistant", content=reply))
        return reply

    async def process_inbox(self) -> list[str]:
        """Process any pending messages in the agent's inbox."""
        results = []
        while not self._inbox.empty():
            msg = self._inbox.get_nowait()
            logger.info(f"[{self.name}] received message from {msg.from_agent}: {msg.content[:100]}")
            results.append(f"From {msg.from_agent}: {msg.content}")
        return results

    def _track_usage(self, usage: dict | None) -> None:
        """Feed LLM usage data into the cost tracker."""
        if not usage or not self._cost_tracker:
            return
        self._cost_tracker.record(
            agent=self.name,
            model=self.provider.model,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
        )

    def shutdown(self) -> None:
        self.bus.unregister_agent(self.name)
