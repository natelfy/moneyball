from pydantic import BaseModel, Field, field_validator
from typing import Optional

class HitterStat(BaseModel):
    player_name: str = Field(..., description="Nom complet du joueur")
    team: str = Field(..., description="Équipe de la CCBL")
    games_played: int = Field(default=0, ge=0)
    at_bats: int = Field(default=0, ge=0)
    hits: int = Field(default=0, ge=0)
    home_runs: int = Field(default=0, ge=0)
    strikeouts: int = Field(default=0, ge=0)
    walks: int = Field(default=0, ge=0)
    
    @field_validator('player_name', 'team')
    def strip_strings(cls, v: str) -> str:
        return v.strip()