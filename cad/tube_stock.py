"""Read common rectangular-tube stock orders without guessing thickness.

The requested old wall must match exactly one physically valid field. CAD
dimensions and section geometry must still prove this stock before any edit.
"""
from dataclasses import dataclass
import math
import re
from bom.reader import normalized


@dataclass(frozen=True)
class TubeStock:
    raw: str
    values: tuple
    wall_index: int
    wall_span: tuple

    @property
    def wall(self):return self.values[self.wall_index]

    @property
    def section(self):return tuple(v for i,v in enumerate(self.values[:3]) if i!=self.wall_index)

    @property
    def length(self):return self.values[3]

    def with_wall(self,value):
        if not math.isfinite(value) or not 0<value<min(self.section)/2:raise ValueError('Độ dày hộp mới không hợp lệ với kích thước ngoài')
        a,b=self.wall_span
        return self.raw[:a]+f'{value:g}'+self.raw[b:]


def parse(description,old_wall):
    if not isinstance(old_wall,(int,float)) or not math.isfinite(old_wall) or old_wall<=0:return None
    if not re.search(r'\bsat hop\b',normalized(description)):return None
    n=r'(\d+(?:[.,]\d+)?)';pattern=r'(?<![\d.,])'+r'\s*[x×]\s*'.join([n]*4)+r'(?![\d.,]|\s*[x×])'
    sizes=list(re.finditer(pattern,description))
    if len(sizes)!=1:return None
    size=sizes[0]
    if description[:size.start()].rstrip().endswith(('x','×')) or 'sat hop' not in normalized(description[:size.start()]):return None
    values=tuple(float(v.replace(',','.')) for v in size.groups())
    if not all(math.isfinite(v) and v>0 for v in values):return None
    candidates=[i for i in (0,2) if abs(values[i]-old_wall)<1e-6 and old_wall<min(v for j,v in enumerate(values[:3]) if j!=i)/2]
    if len(candidates)!=1:return None
    i=candidates[0];a,b=size.span(i+1)
    return TubeStock(size.group(0),values,i,(a-size.start(),b-size.start()))
