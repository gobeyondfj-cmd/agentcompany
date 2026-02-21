"""Sandboxed Python code execution tool."""

import io
import contextlib
import traceback

from agent_company_ai.tools.registry import tool


@tool(
    "code_exec",
    "Execute Python code and return the output. Code runs in a restricted environment.",
    {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code to execute",
            }
        },
        "required": ["code"],
    },
)
def code_exec(code: str) -> str:
    stdout = io.StringIO()
    stderr = io.StringIO()

    # Restricted globals - no file/network access from code_exec
    restricted_globals = {
        "__builtins__": {
            "print": print,
            "len": len,
            "range": range,
            "enumerate": enumerate,
            "zip": zip,
            "map": map,
            "filter": filter,
            "sorted": sorted,
            "reversed": reversed,
            "list": list,
            "dict": dict,
            "set": set,
            "tuple": tuple,
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "abs": abs,
            "min": min,
            "max": max,
            "sum": sum,
            "round": round,
            "isinstance": isinstance,
            "type": type,
            "hasattr": hasattr,
            "getattr": getattr,
            "setattr": setattr,
            "None": None,
            "True": True,
            "False": False,
            "Exception": Exception,
            "ValueError": ValueError,
            "TypeError": TypeError,
            "KeyError": KeyError,
            "IndexError": IndexError,
        }
    }

    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exec(code, restricted_globals)  # noqa: S102

        output = stdout.getvalue()
        errors = stderr.getvalue()
        result_parts = []
        if output:
            result_parts.append(f"Output:\n{output}")
        if errors:
            result_parts.append(f"Stderr:\n{errors}")
        if not result_parts:
            result_parts.append("Code executed successfully (no output).")
        return "\n".join(result_parts)
    except Exception:
        return f"Execution error:\n{traceback.format_exc()}"
