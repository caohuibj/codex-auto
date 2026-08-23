"""Token and estimated-cost accounting hooks."""

from __future__ import annotations

from decimal import Decimal

from codex_auto.config import CostConfig
from codex_auto.models import UsageRecord

_MILLION = Decimal(1_000_000)


class CostLedger:
    def __init__(self, config: CostConfig) -> None:
        self.config = config
        self.records: list[UsageRecord] = []
        self.total = Decimal("0")

    def record(self, usage: UsageRecord) -> UsageRecord:
        price = self.config.models.get(usage.model)
        cost: Decimal | None = None
        if price is not None:
            uncached = max(0, usage.input_tokens - usage.cached_input_tokens)
            cost = (
                Decimal(uncached) * Decimal(price.input_per_million)
                + Decimal(usage.cached_input_tokens) * Decimal(price.cached_input_per_million)
                + Decimal(usage.output_tokens) * Decimal(price.output_per_million)
            ) / _MILLION
            self.total += cost
        enriched = usage.model_copy(
            update={"estimated_cost_usd": None if cost is None else format(cost, "f")}
        )
        self.records.append(enriched)
        return enriched

    @property
    def total_usd(self) -> str:
        return format(self.total, "f")
