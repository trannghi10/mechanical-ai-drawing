"""Shared bounded rectangle API request schema."""
from pydantic import BaseModel,ConfigDict,Field

class RectangleStretchRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    inspection_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    polyline_handle:str=Field(pattern=r'^[0-9A-F]{1,16}$')
    dimension_handle:str=Field(pattern=r'^[0-9A-F]{1,16}$')
    target_width_mm:float=Field(gt=0)
    source_hash:str=Field(pattern=r'^[a-f0-9]{64}$')


