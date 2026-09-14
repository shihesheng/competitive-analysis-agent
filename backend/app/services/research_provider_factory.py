from __future__ import annotations

from typing import List

from app.schemas.research import RawResearchItem
from app.services.research_provider import ResearchProvider


class PendingExternalResearchProvider(ResearchProvider):
    """Placeholder until the MCP collection layer is connected."""

    def collect(self, state: dict) -> List[RawResearchItem]:
        del state
        return []


class ResearchProviderFactory:
    """Return the current external research provider.

    The old built-in collection implementation has been removed. Until MCP tools are wired in,
    ResearchAgent receives an empty external research set and downstream agents
    expose the missing official specs, reviews and realtime prices as pending.
    """

    @staticmethod
    def create() -> ResearchProvider:
        return PendingExternalResearchProvider()
