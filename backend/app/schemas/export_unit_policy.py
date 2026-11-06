from __future__ import annotations
import hashlib, json
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

MeasureKind = Literal['amount','quantity','count','ratio','exchange_rate','unit_price','text']
AmountUnit = Literal['yuan','qian','wan']
UNIT_DIVISORS = {'yuan': 1, 'qian': 1000, 'wan': 10000}

class ExportUnitRegion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    stable_id: str
    measure_kind: MeasureKind
    ratio_scale: Literal['fraction','percent_points'] | None = None
    unit: AmountUnit = 'yuan'
    divisor: int = 1

class ExportUnitPolicy(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id: UUID
    unit: AmountUnit
    divisor: int
    regions: list[ExportUnitRegion] = Field(default_factory=list)
    canonical_snapshot: str = ''
    canonical_digest: str = ''

    def compute_digest(self) -> 'ExportUnitPolicy':
        payload = {'unit': self.unit, 'divisor': self.divisor, 'regions': [r.model_dump(mode='json') for r in self.regions]}
        self.canonical_snapshot = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',',':'))
        self.canonical_digest = hashlib.sha256(self.canonical_snapshot.encode('utf-8')).hexdigest()
        return self

def build_policy(project_id: UUID, unit: AmountUnit, regions: list[ExportUnitRegion] | None = None) -> ExportUnitPolicy:
    return ExportUnitPolicy(
        project_id=project_id,
        unit=unit,
        divisor=UNIT_DIVISORS[unit],
        regions=regions or [],
    ).compute_digest()
