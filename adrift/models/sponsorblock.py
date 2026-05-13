from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ActionType = Literal["skip", "mute", "blackout"]
Category = Literal[
    "sponsor", "selfpromo", "interaction", "intro", "outro", "preview", "hook", "filler"
]


class SponsorSegment(BaseModel):
    """https://wiki.sponsor.ajay.app/w/API_Docs#GET_/api/skipSegments"""

    segment: tuple[float, float]
    uuid: str = Field(alias="UUID")
    category: Category
    video_duration: float = Field(alias="videoDuration")
    action_type: ActionType = Field(alias="actionType")
    locked: int
    votes: int
    description: str = ""

    model_config = ConfigDict(populate_by_name=True)
