"""Gateway: the only service reachable from outside the lab network."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response
from pydantic import BaseModel

from chaosnet_lab.relay import Hop, relay


class OrderRequest(BaseModel):
    item_id: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    app.state.hop = Hop.from_env("gateway->orders")
    async with httpx.AsyncClient() as client:
        app.state.client = client
        yield


app = FastAPI(title="gateway", lifespan=lifespan)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/orders")
async def create_order(order: OrderRequest, request: Request) -> Response:
    state = request.app.state
    return await relay(
        state.client, state.hop, "POST", "/orders", service="gateway", json=order.model_dump()
    )
