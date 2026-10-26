"""Lab customer API: the lesson 13 mock, with every third /orders call slowed by ERP_SLOW_MS (invented, lab only)."""
import asyncio
import itertools
import os

from customer_api import app  # the lesson 13 mock, copied into the image next to this file

SLOW_MS = int(os.environ.get("ERP_SLOW_MS", "0"))
orders_calls = itertools.count(1)


@app.middleware("http")
async def every_third_orders_call_waits(request, call_next):
    if request.url.path == "/orders" and SLOW_MS and next(orders_calls) % 3 == 0:
        await asyncio.sleep(SLOW_MS / 1000)  # the customer's system is slow on this call
    return await call_next(request)
