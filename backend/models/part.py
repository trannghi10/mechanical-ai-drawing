from pydantic import BaseModel
from typing import Optional, List


class Part(BaseModel):

    id: str

    name: Optional[str] = None

    material: Optional[str] = None

    process: Optional[str] = None

    quantity: Optional[int] = None

    length: Optional[float] = None

    width: Optional[float] = None

    height: Optional[float] = None

    layer: Optional[str] = None

    block_name: Optional[str] = None

    entity_ids: List[str] = []