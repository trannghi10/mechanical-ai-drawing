from pydantic import BaseModel
from typing import List

from .part import Part
from .bom import BOMItem


class DrawingModel(BaseModel):

    drawing_id: str

    file_name: str

    parts: List[Part] = []

    bom: List[BOMItem] = []

    layers: List[str] = []

    blocks: List[str] = []