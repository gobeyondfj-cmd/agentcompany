"""FastAPI web dashboard for Agent Company AI."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from agent_company_ai.core.company import Company

logger = logging.getLogger("agent_company_ai.dashboard")

STATIC_DIR = Path(__file__).parent / "static"

_app = FastAPI(title="Agent Company AI Dashboard")
_company: Company | None = None
_company_slug: str = "default"
_websockets: list[WebSocket] = []


async def _broadcast_ws(event: str, data: dict) -> None:
    """Send an event to all connected WebSocket clients."""
    payload = json.dumps({"event": event, "data": data})
    disconnected = []
    for ws in _websockets:
        try:
            await ws.send_text(payload)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        _websockets.remove(ws)


async def _event_handler(event: str, data: dict) -> None:
    """Bridge company events to WebSocket clients."""
    await _broadcast_ws(event, data)


@_app.on_event("startup")
async def startup():
    global _company
    _company = await Company.load(company=_company_slug)
    _company.set_event_handler(_event_handler)
    logger.info(f"Dashboard started for '{_company.config.name}'")


@_app.on_event("shutdown")
async def shutdown():
    if _company:
        await _company.shutdown()


# ------------------------------------------------------------------
# API routes
# ------------------------------------------------------------------


@_app.get("/")
async def index():
    return HTMLResponse((STATIC_DIR / "index.html").read_text())


@_app.get("/style.css")
async def style():
    from fastapi.responses import Response
    return Response(
        content=(STATIC_DIR / "style.css").read_text(),
        media_type="text/css",
    )


@_app.get("/app.js")
async def app_js():
    from fastapi.responses import Response
    return Response(
        content=(STATIC_DIR / "app.js").read_text(),
        media_type="application/javascript",
    )


@_app.get("/api/status")
async def api_status():
    return _company.status() if _company else {}


@_app.get("/api/agents")
async def api_agents():
    return _company.list_agents() if _company else []


@_app.get("/api/org-chart")
async def api_org_chart():
    return _company.get_org_chart() if _company else {}


@_app.get("/api/tasks")
async def api_tasks():
    if not _company:
        return []
    return [t.to_dict() for t in _company.task_board.list_all()]


@_app.post("/api/tasks")
async def api_create_task(body: dict):
    if not _company:
        return {"error": "Company not loaded"}
    task = await _company.assign(
        description=body["description"],
        assignee=body.get("assignee"),
    )
    return task.to_dict()


@_app.post("/api/chat/{agent_name}")
async def api_chat(agent_name: str, body: dict):
    if not _company:
        return {"error": "Company not loaded"}
    try:
        reply = await _company.chat(agent_name, body["message"])
        return {"reply": reply}
    except ValueError as e:
        return {"error": str(e)}


@_app.post("/api/goal")
async def api_run_goal(body: dict):
    if not _company:
        return {"error": "Company not loaded"}
    goal = body.get("goal", "")
    asyncio.create_task(_company.run_goal(goal))
    return {"status": "started", "goal": goal}


@_app.post("/api/stop")
async def api_stop():
    if not _company:
        return {"error": "Company not loaded"}
    _company.request_stop()
    return {"status": "stop_requested"}


@_app.post("/api/hire")
async def api_hire(body: dict):
    if not _company:
        return {"error": "Company not loaded"}
    try:
        agent = await _company.hire(
            role_name=body["role"],
            agent_name=body.get("name"),
            provider=body.get("provider"),
        )
        return {"name": agent.name, "role": agent.role.name, "title": agent.role.title}
    except Exception as e:
        return {"error": str(e)}


@_app.get("/api/cost")
async def api_cost():
    if not _company:
        return {}
    return _company.cost_tracker.summary()


@_app.get("/api/cost/recent")
async def api_cost_recent():
    if not _company:
        return []
    return _company.cost_tracker.recent(limit=50)


@_app.get("/api/messages")
async def api_messages():
    if not _company:
        return []
    history = _company.bus.get_history(limit=100)
    return [
        {
            "from": m.from_agent,
            "to": m.to_agent,
            "content": m.content,
            "topic": m.topic,
            "timestamp": m.timestamp.isoformat(),
        }
        for m in history
    ]


@_app.get("/api/artifacts")
async def api_artifacts(task_id: str | None = Query(None)):
    if not _company:
        return []
    return await _company.get_artifacts(task_id=task_id)


@_app.get("/api/artifacts/{artifact_id}")
async def api_artifact(artifact_id: str):
    if not _company:
        return {"error": "Company not loaded"}
    row = await _company.db.fetch_one(
        "SELECT * FROM artifacts WHERE id = ?", (artifact_id,)
    )
    if row is None:
        return {"error": "Artifact not found"}
    return row


@_app.get("/api/output-dir")
async def api_output_dir():
    if not _company:
        return {"error": "Company not loaded"}
    return {"output_dir": str(_company.output_dir)}


# ------------------------------------------------------------------
# ProfitEngine API
# ------------------------------------------------------------------


@_app.get("/api/profit-engine")
async def api_profit_engine():
    """Return the current ProfitEngine configuration."""
    if not _company:
        return {"error": "Company not loaded"}
    pe = _company.config.profit_engine
    return pe.model_dump()


@_app.post("/api/profit-engine")
async def api_profit_engine_update(body: dict):
    """Update ProfitEngine fields and save to config.yaml."""
    if not _company:
        return {"error": "Company not loaded"}

    from agent_company_ai.config import save_config

    pe = _company.config.profit_engine
    valid_fields = {
        "enabled", "mission", "revenue_streams", "target_customers",
        "pricing_model", "competitive_edge", "key_metrics",
        "cost_priorities", "additional_context",
    }
    for key, value in body.items():
        if key in valid_fields:
            setattr(pe, key, value)

    save_config(_company.config, _company.company_dir / "config.yaml")
    return pe.model_dump()


@_app.get("/api/profit-engine/templates")
async def api_profit_engine_templates():
    """List all ProfitEngine templates with their full content."""
    from agent_company_ai.config import list_profit_engine_templates, load_profit_engine_template

    result = []
    for name in list_profit_engine_templates():
        tmpl = load_profit_engine_template(name)
        result.append(tmpl)
    return result


# ------------------------------------------------------------------
# Wallet API (read-only)
# ------------------------------------------------------------------


@_app.get("/api/wallet/balance")
async def api_wallet_balance(chain: str | None = Query(None)):
    if not _company:
        return {"error": "Company not loaded"}
    return _company.wallet_manager.get_balance(chain_name=chain)


@_app.get("/api/wallet/address")
async def api_wallet_address():
    if not _company:
        return {"error": "Company not loaded"}
    addr = _company.wallet_manager.address
    if addr is None:
        return {"address": None, "error": "No wallet found"}
    return {"address": addr}


@_app.get("/api/wallet/payments")
async def api_wallet_payments(status: str | None = Query(None)):
    if not _company:
        return {"error": "Company not loaded"}
    return await _company.wallet_manager.list_payments(status=status)


# ------------------------------------------------------------------
# WebSocket
# ------------------------------------------------------------------


@_app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _websockets.append(ws)
    try:
        while True:
            data = await ws.receive_text()
            # Client can send commands via WS too
            try:
                msg = json.loads(data)
                if msg.get("action") == "chat" and _company:
                    reply = await _company.chat(msg["agent"], msg["message"])
                    await ws.send_text(json.dumps({
                        "event": "chat.reply",
                        "data": {"agent": msg["agent"], "reply": reply},
                    }))
            except (json.JSONDecodeError, KeyError):
                pass
    except WebSocketDisconnect:
        _websockets.remove(ws)


# ------------------------------------------------------------------
# Runner
# ------------------------------------------------------------------


def run_dashboard(host: str = "127.0.0.1", port: int = 8420, company: str = "default") -> None:
    global _company_slug
    _company_slug = company
    uvicorn.run(_app, host=host, port=port, log_level="info")
