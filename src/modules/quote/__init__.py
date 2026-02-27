"""自动报价模块。"""

from .cost_table import CostRecord, CostTableRepository
from .engine import AutoQuoteEngine
from .models import QuoteRequest, QuoteResult
from .providers import (
    IQuoteProvider,
    QuoteProviderError,
    RemoteQuoteProvider,
    RuleTableQuoteProvider,
)
from .setup import QuoteSetupService

__all__ = [
    "AutoQuoteEngine",
    "CostRecord",
    "CostTableRepository",
    "IQuoteProvider",
    "QuoteProviderError",
    "QuoteRequest",
    "QuoteResult",
    "QuoteSetupService",
    "RemoteQuoteProvider",
    "RuleTableQuoteProvider",
]
