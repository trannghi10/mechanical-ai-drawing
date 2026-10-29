from pydantic import BaseModel
from typing import Optional


class BOMItem(BaseModel):

    part_id: str

    material: Optional[str] = None

    process: Optional[str] = None

    quantity: int = 1