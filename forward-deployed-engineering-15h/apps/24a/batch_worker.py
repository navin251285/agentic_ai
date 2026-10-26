"""Basket Bazaar batch worker, one of two nodes (lesson 24a). INVENTED data, lab only.

It owns the parts whose number is even (node a) or odd (node b). For each order it owns, it asks the
customer API (with a fixed number of calls in flight) and upserts one result per (order_id, run_id)
into batch.db. Run it again with the same BATCH_RUN_ID and it skips the orders already done."""
import argparse, csv, hashlib, json, os, sqlite3, time, zlib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

ap = argparse.ArgumentParser()
ap.add_argument("--node", choices=["a", "b"], required=True)
NODE = ap.parse_args().node
RUN_ID = os.environ["BATCH_RUN_ID"]
PARTS = int(os.environ.get("BATCH_PARTS", "4"))
CONCURRENCY = int(os.environ.get("BATCH_CONCURRENCY", "1"))  # calls in flight on this node
ERP = os.environ.get("ERP_URL", "http://erp:8000")
INPUT, DATA = Path("/input/orders.csv"), Path("/data")
QTY_LIMIT = 20  # rules-only labelling: a line this big is probably a typing error
RETRYABLE = {429, 502, 503, 504}
RETRIES = Counter()
UPSERT = """INSERT INTO results (order_id, run_id, part, label, node) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (order_id, run_id) DO UPDATE SET label = excluded.label, node = excluded.node"""


def part_of(order_id: str) -> int:
    return zlib.crc32(order_id.encode()) % PARTS  # the same answer in every process; Python's hash() is not


def owners() -> dict[str, list[int]]:
    return {"a": [p for p in range(PARTS) if p % 2 == 0], "b": [p for p in range(PARTS) if p % 2 == 1]}


def write_json(path: Path, data: dict) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")  # one temp file per process: two nodes never share it
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    os.replace(tmp, path)  # atomic: a reader sees the old file or the new one, never half of one


def write_manifest(order_ids: list[str], lines: int) -> None:
    write_json(DATA / "manifest.json", {
        "run_id": RUN_ID, "input_file": "orders_clean.csv",
        "input_sha256": hashlib.sha256(INPUT.read_bytes()).hexdigest(),
        "input_lines": lines, "unique_orders": len(order_ids), "parts": PARTS,
        "owners": owners(), "planned_per_part": {str(p): n for p, n in sorted(Counter(part_of(o) for o in order_ids).items())},
    })  # same content from both nodes: no timestamps, so a second write changes nothing


def label(order: dict) -> str:  # rules only: no model call in this batch
    return "check_qty" if any(line["qty"] > QTY_LIMIT for line in order["lines"]) else "ok"


def should_try_again(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE
    return isinstance(exc, httpx.TransportError)


def wait_policy(state) -> float:
    exc = state.outcome.exception()
    if isinstance(exc, httpx.HTTPStatusError) and "Retry-After" in exc.response.headers:
        return float(exc.response.headers["Retry-After"])
    return wait_exponential_jitter(initial=0.2, max=2)(state)


@retry(retry=retry_if_exception(should_try_again), wait=wait_policy, stop=stop_after_attempt(5),
       before_sleep=lambda state: RETRIES.update(["retry"]), reraise=True)
def get_order(client: httpx.Client, order_id: str) -> dict:
    response = client.get(f"/orders/{order_id}")
    response.raise_for_status()
    return response.json()


def main() -> None:
    lines = list(csv.DictReader(INPUT.open(newline="")))
    orders_seen = sorted({row["order_id"] for row in lines})
    write_manifest(orders_seen, len(lines))
    mine = set(owners()[NODE])
    owned = [o for o in orders_seen if part_of(o) in mine]
    db = sqlite3.connect(DATA / "batch.db", timeout=30)  # default journal: the notebook can read the file while it runs
    db.execute("""CREATE TABLE IF NOT EXISTS results (order_id TEXT NOT NULL, run_id TEXT NOT NULL,
                  part INTEGER NOT NULL, label TEXT NOT NULL, node TEXT NOT NULL,
                  PRIMARY KEY (order_id, run_id))""")
    done = {r[0] for r in db.execute("SELECT order_id FROM results WHERE run_id = ?", (RUN_ID,))}
    todo = [o for o in owned if o not in done]  # a restart skips what is already written
    progress = {"node": NODE, "concurrency": CONCURRENCY, "owned": len(owned),
                "skipped_at_start": len(owned) - len(todo), "written_this_start": 0, "state": "running"}
    write_json(DATA / f"progress-{NODE}.json", progress)
    with httpx.Client(base_url=ERP, timeout=5) as client, ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = {pool.submit(get_order, client, o): o for o in todo}
        for n, future in enumerate(as_completed(futures), 1):
            order_id = futures[future]
            order = future.result()  # raises if the API still refuses after the retries: the node stops
            db.execute(UPSERT, (order_id, RUN_ID, part_of(order_id), label(order), NODE))
            db.commit()  # one order at a time: a crash loses at most the calls still in flight
            progress["written_this_start"] = n
            if n % 10 == 0:
                write_json(DATA / f"progress-{NODE}.json", {**progress, "retries": RETRIES["retry"]})
    progress.update(state="done", retries=RETRIES["retry"])
    write_json(DATA / f"progress-{NODE}.json", progress)
    db.close()


if __name__ == "__main__":
    main()
