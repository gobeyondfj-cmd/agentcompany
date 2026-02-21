"""Shell command execution tool."""

import asyncio

from agent_company_ai.tools.registry import tool


@tool(
    "shell",
    "Execute a shell command and return the output. Use for system tasks like git, npm, etc.",
    {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute",
            }
        },
        "required": ["command"],
    },
)
async def shell(command: str) -> str:
    # Block dangerous commands
    dangerous = ["rm -rf /", "mkfs", "dd if=", ":(){", "fork bomb"]
    cmd_lower = command.lower()
    for d in dangerous:
        if d in cmd_lower:
            return f"Error: Blocked dangerous command pattern: {d}"

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

        result_parts = []
        if stdout:
            out = stdout.decode("utf-8", errors="replace")
            if len(out) > 10_000:
                out = out[:10_000] + "\n... (truncated)"
            result_parts.append(out)
        if stderr:
            err = stderr.decode("utf-8", errors="replace")
            if len(err) > 5_000:
                err = err[:5_000] + "\n... (truncated)"
            result_parts.append(f"STDERR:\n{err}")

        exit_info = f"[Exit code: {proc.returncode}]"
        if result_parts:
            return "\n".join(result_parts) + f"\n{exit_info}"
        return f"Command completed. {exit_info}"
    except asyncio.TimeoutError:
        return "Error: Command timed out after 30 seconds."
    except Exception as e:
        return f"Error executing command: {e}"
