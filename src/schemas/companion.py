from pydantic import BaseModel, Field


class ProactiveOutreachRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=255)
    trigger_reason: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Why the proactive message is being generated.",
    )
