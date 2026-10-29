"""Dataset truth is explicitly separate from extracted or synthetic observations."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

GROUPS = {
    'fasteners': 'Bulông, vít, đai ốc, vòng đệm',
    'shafts_gears': 'Trục, bạc, chốt, bánh răng',
    'plates': 'Tấm thép, bản mã, chi tiết cắt laser',
    'welded_frames': 'Khung thép, kết cấu hàn',
    'fixtures': 'Giá đỡ, đồ gá, cụm bắt vít',
    'metal_furniture': 'Bàn, ghế, nội thất kim loại',
    'hardware': 'Tay nắm, bản lề, khóa, phụ kiện',
    'machine_assemblies': 'Cụm máy, truyền động, lắp ráp',
    'piping': 'Ống, mặt bích, phụ kiện đường ống',
    'mixed_layouts': 'Hồ sơ hỗn hợp nhiều bản vẽ, nhiều layout',
}
Group = Literal['fasteners','shafts_gears','plates','welded_frames','fixtures','metal_furniture','hardware','machine_assemblies','piping','mixed_layouts','unclassified']
Hash = str


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class Review(Strict):
    status: Literal['pending','approved','rejected'] = 'pending'
    reviewer: str | None = None
    reviewed_at: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    note: str = ''

    @model_validator(mode='after')
    def approval_is_attributed(self):
        if self.status != 'pending' and (not self.reviewer or not self.reviewed_at or not self.evidence_ids):
            raise ValueError('Review đã quyết định cần người kiểm tra, thời điểm và bằng chứng.')
        return self


class Rights(Strict):
    status: Literal['pending','publisher_declared','internal_evaluation','restricted'] = 'pending'
    license_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    evaluation: bool = False
    training: bool = False
    redistribution: bool = False
    note: str = ''

    @model_validator(mode='after')
    def permissions_require_evidence(self):
        if any((self.evaluation,self.training,self.redistribution)):
            if self.status not in ('publisher_declared','internal_evaluation') or not self.evidence_ids:
                raise ValueError('Quyền sử dụng cần bằng chứng nguồn.')
        if self.status == 'publisher_declared' and not self.license_id:
            raise ValueError('Cần ghi giấy phép do nguồn công bố.')
        if self.status == 'internal_evaluation' and (self.training or self.redistribution):
            raise ValueError('Cho đọc nội bộ không đồng nghĩa cho huấn luyện hoặc chia sẻ.')
        return self


class Asset(Strict):
    id: str = Field(pattern=r'^[a-zA-Z0-9_.-]+$')
    path: str
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    bytes: int = Field(gt=0)
    format: Literal['DWG','DXF','STEP','PNG','JSON','TEXT']
    role: Literal['original','before','after','image','source_labels','parameters','source_metadata','native_dxf','verification','license']
    storage: Literal['dataset','document'] = 'dataset'
    document_id: str | None = Field(default=None, pattern=r'^[0-9a-f]{32}$')
    download_url: str | None = None
    validation: Literal['downloaded','signature_checked','parsed','native_opened','native_roundtrip'] = 'downloaded'

    @model_validator(mode='after')
    def document_reference_is_explicit(self):
        if self.storage == 'document' and not self.document_id: raise ValueError('Thiếu document ID nội bộ.')
        return self


class Evidence(Strict):
    id: str
    asset_id: str
    kind: Literal['native_ref','image_box','source_metadata','engineering_report','license']
    ref: str | None = None
    box: list[float] | None = Field(default=None, min_length=4, max_length=4)
    note: str = ''

    @model_validator(mode='after')
    def grounded(self):
        if self.kind == 'native_ref' and not self.ref: raise ValueError('Bằng chứng native cần handle/instance path.')
        if self.kind == 'image_box':
            if not self.box or not (0 <= self.box[0] < self.box[2] <= 1 and 0 <= self.box[1] < self.box[3] <= 1):
                raise ValueError('Khung ảnh phải có tọa độ chuẩn hóa 0..1 hợp lệ.')
        return self


class Label(Strict):
    id: str
    kind: Literal['view','dimension','part_identity','bom','joint','datum','process','packaging','annotation']
    value: str
    evidence_ids: list[str] = Field(min_length=1)
    review: Review = Field(default_factory=Review)


class Relationship(Strict):
    id: str
    kind: Literal['SAME_PART_AS','PROJECTS_TO','MEASURED_BY','MEMBER_OF','MATES_WITH','COAXIAL_WITH','PARALLEL_TO','PERPENDICULAR_TO','CLEARANCE_WITH','DEPENDS_ON','PRODUCED_FROM','PACKED_IN']
    source_label_id: str
    target_label_id: str
    evidence_ids: list[str] = Field(min_length=1)
    review: Review = Field(default_factory=Review)


class EditCase(Strict):
    id: str
    request_vi: str = Field(min_length=1)
    before_asset_id: str
    after_asset_id: str | None = None
    expected_outcome: Literal['edit','clarify','unsupported']
    target_refs: list[str] = Field(default_factory=list)
    fixed_refs: list[str] = Field(default_factory=list)
    affected_refs: list[str] = Field(default_factory=list)
    preserve_refs: list[str] = Field(default_factory=list)
    expected_checks: list[str] = Field(default_factory=list)
    review: Review = Field(default_factory=Review)
    native_roundtrip: Literal['pending','passed','failed','not_applicable'] = 'pending'
    verification_asset_ids: list[str] = Field(default_factory=list)


class Record(Strict):
    schema_version: Literal[1] = 1
    id: str = Field(pattern=r'^[a-zA-Z0-9_.-]+$')
    title: str
    source_id: str
    source_url: str
    source_revision: str | None = None
    upstream_ids: list[str] = Field(default_factory=list)
    lineage_id: str
    leakage_group: str
    split: Literal['unassigned','train','validation','test'] = 'unassigned'
    origin: Literal['company','external_cad','generated','unknown']
    group: Group = 'unclassified'
    group_review: Review = Field(default_factory=Review)
    rights: Rights = Field(default_factory=Rights)
    assets: list[Asset] = Field(min_length=1)
    evidence: list[Evidence] = Field(default_factory=list)
    labels: list[Label] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    edit_cases: list[EditCase] = Field(default_factory=list)
    dossier_review: Review = Field(default_factory=Review)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def references_exist(self):
        assets={a.id:a for a in self.assets};evidence={e.id:e for e in self.evidence};labels={l.id:l for l in self.labels}
        for values in (self.assets,self.evidence,self.labels,self.relationships,self.edit_cases):
            if len({v.id for v in values}) != len(values): raise ValueError('ID trùng trong hồ sơ.')
        if not any(a.role == 'original' and a.format in ('DWG','DXF','STEP') for a in self.assets):
            raise ValueError('Hồ sơ cần CAD gốc; ảnh hoặc text không được tính thành CAD.')
        if any(e.asset_id not in assets for e in self.evidence): raise ValueError('Bằng chứng trỏ tới file không tồn tại.')
        uses=[self.group_review,self.dossier_review]
        for value in [*self.labels,*self.relationships]:
            if not set(value.evidence_ids)<=evidence.keys(): raise ValueError('Nhãn/quan hệ viện dẫn bằng chứng ngoài hồ sơ.')
            uses.append(value.review)
        if not set(self.rights.evidence_ids)<=evidence.keys(): raise ValueError('Bằng chứng giấy phép không tồn tại.')
        for relation in self.relationships:
            if relation.source_label_id not in labels or relation.target_label_id not in labels: raise ValueError('Quan hệ thiếu đầu nguồn/đích đã định danh.')
        for case in self.edit_cases:
            before=assets.get(case.before_asset_id);after=assets.get(case.after_asset_id)
            if not before or before.format not in ('DWG','DXF','STEP'): raise ValueError('Ca sửa thiếu CAD trước sửa.')
            if case.after_asset_id and (not after or after.role != 'after'): raise ValueError('Ca sửa thiếu file after đúng vai trò.')
            if not set(case.verification_asset_ids)<=assets.keys(): raise ValueError('Thiếu file kiểm chứng.')
            if case.native_roundtrip == 'passed':
                if not after or after.format != 'DWG' or after.validation != 'native_roundtrip' or not case.verification_asset_ids:
                    raise ValueError('Lưu/mở DWG cần file after DWG và báo cáo kiểm chứng; STEP/PNG không thay thế.')
            if case.expected_outcome == 'edit' and case.review.status == 'approved' and (not after or not case.target_refs or not case.expected_checks):
                raise ValueError('Đáp án sửa được duyệt cần file sau sửa, đối tượng và phép kiểm.')
            uses.append(case.review)
        if any(not set(review.evidence_ids)<=evidence.keys() for review in uses): raise ValueError('Review viện dẫn bằng chứng ngoài hồ sơ.')
        for review in uses:
            if review.status != 'pending' and not any(evidence[e].kind=='engineering_report' for e in review.evidence_ids):
                raise ValueError('Nghiệm thu cần báo cáo kỹ sư; giấy phép hoặc nhãn máy sinh không thay thế.')
        return self
