"""自动报价模块。"""

from .cost_table import CostRecord, CostTableRepository
from .engine import AutoQuoteEngine
from .models import QuoteRequest, QuoteResult
from .providers import (
    ApiCostMarkupQuoteProvider,
    CostTableMarkupQuoteProvider,
    IQuoteProvider,
    QuoteProviderError,
    RemoteQuoteProvider,
    RuleTableQuoteProvider,
)
from .setup import QuoteSetupService

__all__ = [
    "ApiCostMarkupQuoteProvider",
    "AutoQuoteEngine",
    "CostRecord",
    "CostTableMarkupQuoteProvider",
    "CostTableRepository",
    "IQuoteProvider",
    "QuoteProviderError",
    "QuoteRequest",
    "QuoteResult",
    "QuoteSetupService",
    "RemoteQuoteProvider",
    "RuleTableQuoteProvider",
]
