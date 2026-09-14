from abc import ABC, abstractmethod
from typing import List

from app.schemas.research import RawResearchItem


class ResearchProvider(ABC):
    @abstractmethod
    def collect(self, state: dict) -> List[RawResearchItem]:
        pass
