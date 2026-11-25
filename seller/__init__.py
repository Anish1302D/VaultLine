"""VaultLine Seller Package.

Five-layer zero-trust architecture for guardrail-first autonomous selling.
"""
from .engine import (
    EngineConfig,
    NegotiationEngine,
    NegotiationState,
)
from .facts import (
    AlternativeFact,
    CategoryPolicy,
    FactObject,
    LineItemFact,
    ProductFact,
    StoreFacts,
)
from .guard import (
    BuyerIntent,
    ManipulationFlag,
    RequestedItem,
)
from .validator import (
    OutputValidator,
    ValidationReport,
)

__all__ = [
    "ProductFact",
    "CategoryPolicy",
    "AlternativeFact",
    "LineItemFact",
    "FactObject",
    "StoreFacts",
    "BuyerIntent",
    "RequestedItem",
    "ManipulationFlag",
    "EngineConfig",
    "NegotiationState",
    "NegotiationEngine",
    "OutputValidator",
    "ValidationReport",
]
