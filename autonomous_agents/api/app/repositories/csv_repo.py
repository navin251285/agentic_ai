"""CsvInventoryRepository — THE ONLY CODE THAT TOUCHES FILES.

- products/orders/runtime: written to a temp file, then os.replace (atomic).
- events: append-only, flushed after each write.
- Write failures (e.g. file locked by Excel on Windows) are logged and never raised.
"""

import contextlib
import csv
import json
import logging
import os
from collections import deque
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app.domain.models import Event, Order, PersistedState, Product, Runtime
from app.repositories.base import InventoryRepository, ScenarioNotFound

log = logging.getLogger(__name__)

# utf-8-sig: Excel on Windows shows "·" in shop_time correctly; the BOM is only written at file start.
ENCODING = "utf-8-sig"

PRODUCT_FIELDS = list(Product.model_fields)
ORDER_FIELDS = list(Order.model_fields)
EVENT_FIELDS = list(Event.model_fields)


def _to_row(model: BaseModel) -> dict[str, str]:
    return {k: "" if v is None else str(v) for k, v in model.model_dump(mode="json").items()}


def _from_row(model_cls: type[BaseModel], row: dict[str, str]) -> BaseModel:
    # Blank cells mean "not set"; let the model's defaults/None apply.
    return model_cls.model_validate({k: v for k, v in row.items() if k is not None and v != ""})


class CsvInventoryRepository(InventoryRepository):
    def __init__(
        self, data_dir: Path, default_scenario: str = "normal_day", runtime_defaults: dict | None = None
    ):
        self.data_dir = Path(data_dir)
        self.scenarios_dir = self.data_dir / "scenarios"
        self.products_path = self.data_dir / "products.csv"
        self.orders_path = self.data_dir / "orders.csv"
        self.events_path = self.data_dir / "events.csv"
        self.runtime_path = self.data_dir / "runtime.json"
        self.default_scenario = default_scenario
        self.runtime_defaults = runtime_defaults or {}
        self._pending_events: deque[Event] = deque()

    # ---- load -------------------------------------------------------------

    def load(self) -> PersistedState:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        runtime = self._load_runtime_model()
        products = self._load_products()
        if products is None:
            log.info("products.csv missing or unreadable; starting from scenario %r", self.default_scenario)
            products = self.load_scenario(self.default_scenario)
            self.save_products(products)
        orders = self._read_models(self.orders_path, Order)
        events = self.read_events(runtime.run_id)
        return PersistedState(products=products, orders=orders, runtime=runtime, events=events)

    def _load_runtime_model(self) -> Runtime:
        merged = {**self.runtime_defaults, **self.load_runtime()}
        try:
            return Runtime.model_validate(merged)
        except ValidationError as e:
            log.warning("runtime.json is invalid, using defaults: %s", e)
            return Runtime.model_validate(self.runtime_defaults)

    def _load_products(self) -> list[Product] | None:
        if not self.products_path.exists():
            return None
        try:
            products = self._read_products_file(self.products_path)
            if not products:
                raise ValueError("no products")
        except OSError as e:
            log.warning("Could not read %s: %s", self.products_path.name, e)
            return None
        except ValueError as e:
            self._quarantine_products(e)
            return None
        return products

    def _quarantine_products(self, reason: Exception) -> None:
        """Keep an invalid products.csv for inspection instead of silently overwriting it."""
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        bad = self.products_path.with_name(f"{self.products_path.name}.bad-{stamp}")
        n = 1
        while bad.exists():
            bad = self.products_path.with_name(f"{self.products_path.name}.bad-{stamp}-{n}")
            n += 1
        try:
            self.products_path.rename(bad)
        except OSError as e:
            log.warning("products.csv is INVALID (%s) and could not be renamed: %s", reason, e)
            return
        log.warning(
            "products.csv is INVALID and was moved to %s. Starting from scenario %r. Reason: %s",
            bad.name,
            self.default_scenario,
            reason,
        )

    def _read_products_file(self, path: Path) -> list[Product]:
        """Strict: any bad row makes the whole file invalid (a half-loaded shop is worse than none)."""
        with path.open(newline="", encoding=ENCODING) as f:
            products = [_from_row(Product, row) for row in csv.DictReader(f)]
        ids = [p.id for p in products]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate product ids in {path.name}")
        return products

    def _read_models(self, path: Path, model_cls: type[BaseModel]) -> list:
        """Lenient: bad rows are skipped with a warning."""
        if not path.exists():
            return []
        items = []
        try:
            with path.open(newline="", encoding=ENCODING) as f:
                for line_no, row in enumerate(csv.DictReader(f), start=2):
                    try:
                        items.append(_from_row(model_cls, row))
                    except ValidationError as e:
                        log.warning("Skipping bad row %d in %s: %s", line_no, path.name, e.errors()[0]["msg"])
        except OSError as e:
            log.warning("Could not read %s: %s", path.name, e)
        return items

    # ---- products / orders / runtime (atomic rewrite) ---------------------

    def save_products(self, products: list[Product]) -> bool:
        return self._write_csv_atomic(self.products_path, PRODUCT_FIELDS, products)

    def save_orders(self, orders: list[Order]) -> bool:
        return self._write_csv_atomic(self.orders_path, ORDER_FIELDS, orders)

    def save_runtime(self, runtime: dict) -> bool:
        text = json.dumps(runtime, indent=2)
        return self._write_atomic(self.runtime_path, lambda f: f.write(text + "\n"), encoding="utf-8")

    def load_runtime(self) -> dict:
        if not self.runtime_path.exists():
            return {}
        try:
            data = json.loads(self.runtime_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            log.warning("Could not read runtime.json, using defaults: %s", e)
            return {}
        return data if isinstance(data, dict) else {}

    def _write_csv_atomic(self, path: Path, fields: list[str], models: list[BaseModel]) -> bool:
        def write(f):
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(_to_row(m) for m in models)

        return self._write_atomic(path, write, encoding=ENCODING, newline="")

    def _write_atomic(self, path: Path, write, encoding: str, newline: str | None = None) -> bool:
        tmp = path.with_name(path.name + ".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tmp.open("w", encoding=encoding, newline=newline) as f:
                write(f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except OSError as e:
            log.warning("Could not save %s (will retry on next save): %s", path.name, e)
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
            return False
        self._flush_pending_events()
        return True

    # ---- events (append-only) ---------------------------------------------

    def append_event(self, event: Event) -> bool:
        self._pending_events.append(event)
        return self._flush_pending_events()

    @property
    def pending_event_count(self) -> int:
        return len(self._pending_events)

    def _flush_pending_events(self) -> bool:
        if not self._pending_events:
            return True
        try:
            self.events_path.parent.mkdir(parents=True, exist_ok=True)
            new_file = not self.events_path.exists() or self.events_path.stat().st_size == 0
            with self.events_path.open("a", newline="", encoding=ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=EVENT_FIELDS)
                if new_file:
                    writer.writeheader()
                while self._pending_events:
                    writer.writerow(_to_row(self._pending_events[0]))
                    f.flush()
                    self._pending_events.popleft()
        except OSError as e:
            log.warning(
                "Could not append to events.csv, %d event(s) queued: %s", len(self._pending_events), e
            )
            return False
        return True

    def read_events(self, run_id: int) -> list[Event]:
        return [e for e in self._read_models(self.events_path, Event) if e.run_id == run_id]

    # ---- scenarios --------------------------------------------------------

    def list_scenarios(self) -> list[str]:
        if not self.scenarios_dir.is_dir():
            return []
        return sorted(p.stem for p in self.scenarios_dir.glob("*.csv"))

    def load_scenario(self, name: str) -> list[Product]:
        # Only names that exist in scenarios/ are allowed (no paths).
        if name not in self.list_scenarios():
            raise ScenarioNotFound(name)
        return self._read_products_file(self.scenarios_dir / f"{name}.csv")
