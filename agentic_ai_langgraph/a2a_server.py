"""Serve an A2A agent on localhost for the protocol lessons, and send it messages (a2a-sdk 1.x).

The server runs in a background thread on a free port, so a lesson can start several agents and stop them at its end.

    from a2a_server import serve, stop, send_text
    base, server = serve("orders-agent", "Order status.", [("order_status", "Order status", "status of one order")], executor)
    task = await send_text(base, "Where is order 1003?")
    stop(server)
"""
import socket
import threading
import time

import httpx
import uvicorn
from starlette.applications import Starlette

from a2a.client import A2ACardResolver, create_client
from a2a.helpers import new_text_message
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill, SendMessageConfiguration, SendMessageRequest, a2a_pb2


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(name: str, description: str, skills: list[tuple[str, str, str]], executor, version: str = "1.0.0"):
    """Start an agent with its card. Returns its base address and the server to stop later."""
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    card = AgentCard(
        name=name, description=description, version=version,
        supported_interfaces=[AgentInterface(url=base + "/", protocol_binding="JSONRPC", protocol_version="1.0")],
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text"], default_output_modes=["text"],
        skills=[AgentSkill(id=i, name=n, description=d, tags=[i]) for i, n, d in skills])
    handler = DefaultRequestHandler(agent_executor=executor, task_store=InMemoryTaskStore(), agent_card=card)
    app = Starlette(routes=create_agent_card_routes(card) + create_jsonrpc_routes(handler, rpc_url="/"))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    return base, server


def stop(server) -> None:
    server.should_exit = True


async def _send(base: str, text: str, task_id: str | None):
    async with httpx.AsyncClient() as http:
        card = await A2ACardResolver(http, base).get_agent_card()
        client = await create_client(card)
        msg = new_text_message(text, role=a2a_pb2.Role.ROLE_USER, task_id=task_id)
        request = SendMessageRequest(message=msg, configuration=SendMessageConfiguration(return_immediately=False))
        events = [event async for event in client.send_message(request)]
        await client.close()
        return events


async def send_text(base: str, text: str, task_id: str | None = None) -> list:
    """Send one text message to an agent and return the events it sent back. Use it with await in a notebook."""
    return await _send(base, text, task_id)
