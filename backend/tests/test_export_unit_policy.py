import pytest
from uuid import uuid4
from app.schemas.export_unit_policy import build_policy, UNIT_DIVISORS, ExportUnitRegion

class TestExportUnitPolicy:
    @pytest.mark.parametrize('unit,divisor', [('yuan',1),('qian',1000),('wan',10000)])
    def test_three_units_with_correct_divisor(self, unit, divisor):
        p = build_policy(uuid4(), unit)
        assert p.unit == unit
        assert p.divisor == divisor
        assert p.canonical_digest
        assert len(p.canonical_digest) == 64

    def test_digest_is_stable(self):
        pid = uuid4()
        p1 = build_policy(pid, 'wan')
        p2 = build_policy(pid, 'wan')
        assert p1.canonical_digest == p2.canonical_digest
        assert p1.canonical_snapshot == p2.canonical_snapshot

    def test_different_units_produce_different_digests(self):
        pid = uuid4()
        digests = {build_policy(pid, u).canonical_digest for u in ('yuan','qian','wan')}
        assert len(digests) == 3

    def test_regions_included_in_digest(self):
        pid = uuid4()
        r = ExportUnitRegion(stable_id='test', measure_kind='amount')
        p1 = build_policy(pid, 'yuan')
        p2 = build_policy(pid, 'yuan', [r])
        assert p1.canonical_digest != p2.canonical_digest
