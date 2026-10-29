from pathlib import Path
from typing import Any, Dict, List, Optional
import hashlib
import shutil
import tempfile
import ezdxf

from cad.converter import converter_path, DWGConverter
from cad.entities import extract_entities, extract_all_blocks

CACHE_ROOT=Path(__file__).resolve().parents[1]/'storage'/'cache_dxf'


class DXFReader:
    """Lớp đọc toàn diện cho bản vẽ CAD, tự động hỗ trợ cả định dạng DWG và DXF.
    Cho phép đọc toàn bộ thực thể CAD, block definitions, block instances, layers và layout.
    """

    def __init__(self, file_path: str):
        self.file_path = Path(file_path).resolve()

        if not self.file_path.exists():
            raise FileNotFoundError(f"File không tồn tại: {self.file_path}")

        self._dxf_path = self._resolve_dxf_path()
        self._doc = None
        self._native_cells=None

    def _with_native_tables(self,records):
        if any(record['type']=='ACAD_TABLE' for record in records):
            if self._native_cells is None:
                from cad.table_data import table_cells
                self._native_cells=table_cells(self._dxf_path)
            for record in records:
                if record['type']=='ACAD_TABLE':
                    record['cells']=self._native_cells.get(record['handle'],[])
                    record['cell_status']='native_cell_values' if record['cells'] else 'unavailable_encoding'
        return records

    def _resolve_dxf_path(self) -> Path:
        """Nếu là file DWG, tự động chuyển đổi sang DXF qua ODAFileConverter hoặc tìm bản DXF đã chuyển đổi."""
        suffix = self.file_path.suffix.lower()
        if suffix == ".dxf":
            return self.file_path

        if suffix == ".dwg":
            # Uploads commonly share the name original.dwg. Names/mtime alone
            # cannot identify their content, nor can a neighboring original.dxf.
            fingerprint=hashlib.sha256(self.file_path.read_bytes()).hexdigest()
            cache_dir=CACHE_ROOT/fingerprint
            cache_dir.mkdir(parents=True,exist_ok=True)
            cached_dxf=cache_dir/'original.dxf'
            if cached_dxf.is_file() and cached_dxf.stat().st_size:return cached_dxf
            c_path = converter_path()
            if not c_path:
                raise RuntimeError(
                    f"Cần ODAFileConverter để đọc file DWG '{self.file_path.name}'. "
                    "Hãy cấu hình ODA_CONVERTER trong .env hoặc cài đặt ODA File Converter."
                )

            # Convert just the requested file, without scanning a network CAD
            # directory or accidentally taking another document's output.
            with tempfile.TemporaryDirectory(dir=cache_dir,prefix='convert-') as temp:
                task=Path(temp);input_dir=task/'input';output_dir=task/'output';input_dir.mkdir()
                copied=input_dir/'original.dwg';shutil.copyfile(self.file_path,copied)
                if hashlib.sha256(copied.read_bytes()).hexdigest()!=fingerprint:
                    raise RuntimeError('Nguồn DWG thay đổi trong lúc đọc; hãy thử lại.')
                DWGConverter(c_path).convert_dwg_to_dxf(str(input_dir),str(output_dir))
                output=next((p for p in output_dir.glob('*') if p.name.lower()=='original.dxf'),None)
                if output is None or not output.stat().st_size:
                    raise RuntimeError(f"Chuyển đổi DWG '{self.file_path.name}' không tạo được DXF.")
                output.replace(cached_dxf)
            return cached_dxf

        raise ValueError(f"Định dạng file không được hỗ trợ: {suffix}. Chỉ nhận .dwg hoặc .dxf.")

    def load(self):
        """Nạp tài liệu CAD Drawing."""
        if self._doc is None:
            self._doc = ezdxf.readfile(self._dxf_path)
        return self._doc

    def get_modelspace(self):
        """Trả về Modelspace layout của bản vẽ."""
        return self.load().modelspace()

    def get_layouts(self) -> List[str]:
        """Trả về danh sách tên tất cả các Layout trong bản vẽ (gồm Model và các Paperspace)."""
        doc = self.load()
        return [layout.name for layout in doc.layouts]

    def get_layers(self) -> List[str]:
        """Trả về danh sách tên các Layer."""
        doc = self.load()
        return [layer.dxf.name for layer in doc.layers]

    def get_layer_details(self) -> List[Dict[str, Any]]:
        """Trả về thông tin chi tiết từng Layer."""
        doc = self.load()
        details = []
        for layer in doc.layers:
            details.append({
                "name": layer.dxf.name,
                "color": getattr(layer.dxf, "color", 7),
                "is_locked": bool(getattr(layer, "is_locked", lambda: False)()),
                "is_off": bool(getattr(layer, "is_off", lambda: False)()),
            })
        return details

    def get_blocks(self) -> List[str]:
        """Trả về danh sách tên tất cả các Block trong bản vẽ (bao gồm cả block hệ thống)."""
        doc = self.load()
        return [block.name for block in doc.blocks]

    def get_block_names(self, include_system: bool = False) -> List[str]:
        """Trả về danh sách tên các Block người dùng tự định nghĩa (loại bỏ block hệ thống *...)."""
        doc = self.load()
        return [
            block.name for block in doc.blocks
            if include_system or not block.name.startswith("*")
        ]

    def get_block(self, block_name: str):
        """Lấy đối tượng Block theo tên."""
        doc = self.load()
        block = doc.blocks.get(block_name)
        if block is None:
            raise KeyError(f"Block '{block_name}' không tồn tại trong bản vẽ.")
        return block

    def get_block_entities(self, block_name: str) -> List[Dict[str, Any]]:
        """Trích xuất danh sách tất cả các thực thể hình học, text, kích thước bên trong một Block."""
        block = self.get_block(block_name)
        return self._with_native_tables(extract_entities(block))

    def get_all_blocks(self, include_system: bool = False) -> Dict[str, Dict[str, Any]]:
        """Đọc toàn bộ block definitions trong bản vẽ kèm chi tiết thực thể bên trong từng block."""
        blocks=extract_all_blocks(self.load(), include_system=include_system)
        for block in blocks.values():self._with_native_tables(block['entities'])
        return blocks

    def get_modelspace_entities(self) -> List[Dict[str, Any]]:
        """Đọc toàn bộ thực thể CAD trong Modelspace (đường thẳng, polyline, đường tròn, text, kích thước, insert...)."""
        return self._with_native_tables(extract_entities(self.get_modelspace()))

    def get_all_entities(self, include_blocks: bool = True) -> Dict[str, Any]:
        """Đọc toàn bộ thực thể CAD trên toàn bộ bản vẽ:
        - modelspace: các thực thể trong modelspace
        - layouts: các thực thể trong từng paperspace layout
        - blocks: chi tiết các thực thể bên trong từng block definition (nếu include_blocks=True)
        """
        doc = self.load()
        result = {
            "modelspace": self.get_modelspace_entities(),
            "layouts": {},
        }
        for layout in doc.layouts:
            if layout.name != "Model":
                result["layouts"][layout.name] = self._with_native_tables(extract_entities(layout))

        if include_blocks:
            # Anonymous blocks contain real geometry (including TABLE mirrors
            # and dimensions); an all-entities inventory must retain them.
            result["blocks"] = self.get_all_blocks(include_system=True)

        return result

    def get_summary(self) -> Dict[str, Any]:
        """Tóm tắt tổng quan bản vẽ: số lượng layers, blocks, và thống kê từng loại đối tượng CAD."""
        doc = self.load()
        msp_entities = self.get_modelspace_entities()
        type_counts = {}
        for ent in msp_entities:
            t = ent["type"]
            type_counts[t] = type_counts.get(t, 0) + 1

        blocks = self.get_block_names()
        return {
            "file": self.file_path.name,
            "dxf_version": doc.dxfversion,
            "layers_count": len(doc.layers),
            "blocks_count": len(blocks),
            "all_block_definitions_count":len(doc.blocks),
            "modelspace_entities_count": len(msp_entities),
            "entity_types": type_counts,
            "layouts": [l.name for l in doc.layouts],
        }


# Alias CADReader để sử dụng tự nhiên cho cả DWG và DXF
CADReader = DXFReader
