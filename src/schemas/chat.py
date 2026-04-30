from enum import Enum

from pydantic import BaseModel, Field


class ChatMode(str, Enum):
    COMPANION = "companion"
    PLANNING = "planning"


class ChatStreamRequest(BaseModel):
    user_message: str = Field(..., min_length=1, max_length=4000)
    user_id: str = Field(default="default_user", min_length=1, max_length=255)
    mode: ChatMode = Field(default=ChatMode.COMPANION)
