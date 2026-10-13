"""Inventory: the leaf service. Holds items in memory."""

from fastapi import FastAPI, HTTPException

ITEMS = {
    "42": {"item_id": "42", "name": "mechanical keyboard", "stock": 7},
    "7": {"item_id": "7", "name": "usb-c cable", "stock": 120},
}

app = FastAPI(title="inventory")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/items/{item_id}")
def get_item(item_id: str) -> dict[str, object]:
    item = ITEMS.get(item_id)
    if item is None:
        raise HTTPException(404, f"item {item_id} not found")
    return {"item": item, "path": ["inventory"]}
