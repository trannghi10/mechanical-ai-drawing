from pydantic import BaseModel
from typing import Optional, List


class MaterialChange(BaseModel):

    old: Optional[str] = None

    new: str


class DimensionChange(BaseModel):

    delta: Optional[float] = None

    absolute: Optional[float] = None


class PartChange(BaseModel):

    part_id: str

    material: Optional[MaterialChange] = None

    length: Optional[DimensionChange] = None

    width: Optional[DimensionChange] = None

    height: Optional[DimensionChange] = None


class ChangePlan(BaseModel):

    description: str

    changes: List[PartChange]

    affected_parts: List[str] = []

    warnings: List[str] = []