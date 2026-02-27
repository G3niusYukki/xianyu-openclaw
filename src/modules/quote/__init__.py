"""自动报价模块。"""

from .cost_table import CostTableRecord, CostTableRepository
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
    "CostTableRecord",
    "CostTableRepository",
    "IQuoteProvider",
    "QuoteProviderError",
    "QuoteRequest",
    "QuoteResult",
    "QuoteSetupService",
    "RemoteQuoteProvider",
    "RuleTableQuoteProvider",
]
