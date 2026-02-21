"""File I/O tools for reading and writing files in the workspace."""

import shutil
from pathlib import Path

from agent_company_ai.tools.registry import tool

# Workspace root is set at runtime by the Company
_workspace: Path | None = None

# Output directory for deliverables, set at runtime by the Company
_output_dir: Path | None = None


def set_workspace(path: Path) -> None:
    global _workspace
    _workspace = path


def set_output_dir(path: Path) -> None:
    global _output_dir
    _output_dir = path


def copy_to_output(relative_path: str, task_id: str) -> Path | None:
    """Copy a workspace file into output/task-<id>/, returning the dest path."""
    if _workspace is None or _output_dir is None:
        return None
    src = (_workspace / relative_path).resolve()
    if not src.exists() or not src.is_file():
        return None
    dest_dir = _output_dir / f"task-{task_id}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    # Handle name collisions with counter suffix
    counter = 1
    while dest.exists():
        dest = dest_dir / f"{src.stem}_{counter}{src.suffix}"
        counter += 1
    shutil.copy2(str(src), str(dest))
    return dest


def _resolve(filepath: str) -> Path:
    if _workspace is None:
        raise RuntimeError("Workspace not set. Initialize the company first.")
    resolved = (_workspace / filepath).resolve()
    # Prevent path traversal outside workspace
    if not str(resolved).startswith(str(_workspace.resolve())):
        raise PermissionError(f"Access denied: {filepath} is outside the workspace")
    return resolved


@tool(
    "read_file",
    "Read the contents of a file in the workspace.",
    {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path to the file within the workspace",
            }
        },
        "required": ["path"],
    },
)
def read_file(path: str) -> str:
    target = _resolve(path)
    if not target.exists():
        return f"Error: File not found: {path}"
    if not target.is_file():
        return f"Error: Not a file: {path}"
    try:
        content = target.read_text(encoding="utf-8")
        if len(content) > 50_000:
            return content[:50_000] + f"\n\n... (truncated, total {len(content)} chars)"
        return content
    except Exception as e:
        return f"Error reading file: {e}"


@tool(
    "write_file",
    "Write content to a file in the workspace. Creates directories as needed.",
    {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path to the file within the workspace",
            },
            "content": {
                "type": "string",
                "description": "The content to write to the file",
            },
        },
        "required": ["path", "content"],
    },
)
def write_file(path: str, content: str) -> str:
    target = _resolve(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} chars to {path}"
    except Exception as e:
        return f"Error writing file: {e}"


@tool(
    "list_files",
    "List files and directories in a workspace path.",
    {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative directory path (default: workspace root)",
            }
        },
        "required": [],
    },
)
def list_files(path: str = ".") -> str:
    target = _resolve(path)
    if not target.exists():
        return f"Error: Path not found: {path}"
    if not target.is_dir():
        return f"Error: Not a directory: {path}"
    try:
        entries = sorted(target.iterdir())
        lines = []
        for entry in entries[:100]:
            rel = entry.relative_to(_workspace)
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"  {rel}{suffix}")
        result = f"Contents of {path}/:\n" + "\n".join(lines)
        if len(entries) > 100:
            result += f"\n  ... and {len(entries) - 100} more"
        return result
    except Exception as e:
        return f"Error listing files: {e}"
