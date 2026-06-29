from pydantic import BaseModel
from typing import Optional, Dict, Any


class OnboardingRequest(BaseModel):
    sobriety_status: Optional[str] = None
    framework_orientation: Optional[str] = None
    trigger_map: Optional[Dict[str, Any]] = None
    their_why: Optional[str] = None


class OnboardingResponse(BaseModel):
    message: str
