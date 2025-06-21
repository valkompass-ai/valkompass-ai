import numpy as np
from pydantic import BaseModel, ConfigDict, field_validator


class Party(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    abbreviation: str  # Primary key (C, M, S, SD, etc.)
    full_name: str  # Full party name from parties.json
    embedding: np.ndarray | None = None  # Future: aggregated position embedding

    @field_validator("abbreviation")
    @classmethod
    def validate_abbreviation(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("abbreviation cannot be empty")
        return v.strip()

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("full_name cannot be empty")
        return v.strip()
