from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class RawResearchItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    item_id: str
    platform: str
    source_type: Literal[
        "official",
        "news",
        "review",
        "report",
        "ecommerce",
        "user_review",
        "test",
    ]
    source_title: str
    source_url: str
    publish_time: Optional[str] = None
    collected_time: str
    raw_content: str
    collection_method: Literal["mcp", "database", "manual", "cache"] = "manual"
