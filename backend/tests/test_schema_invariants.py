import ast
import pytest
from pathlib import Path
from pydantic import ValidationError

_SCHEMA = Path(__file__).resolve().parents[1] / 'app' / 'schemas' / 'display_preferences.py'

def _src():
    return _SCHEMA.read_text(encoding='utf-8')

class TestSchemaInvariants:
    def test_strict_types_imported(self):
        s = _src()
        assert 'StrictBool' in s
        assert 'StrictInt' in s

    def test_no_unset_sentinel(self):
        s = _src()
        non_comment = [l for l in s.splitlines() if not l.strip().startswith('#')]
        joined = '\n'.join(non_comment)
        assert '_UNSET = object()' not in joined
        assert '_UNSET' not in joined

    def test_patch_uses_model_fields_set(self):
        assert 'model_fields_set' in _src()

    def test_patch_uses_exclude_unset(self):
        s = _src()
        assert 'exclude_unset=True' in s
        assert 'exclude_none' not in s

    def test_extra_forbid_on_patch(self):
        assert 'forbid' in _src()

    def test_highlight_threshold_precision(self):
        from app.schemas.display_preferences import DisplayPreferencesPatch
        with pytest.raises(ValidationError):
            DisplayPreferencesPatch.model_validate({'base_revision': 0, 'highlight_threshold': 0.12345})

    def test_fixed_columns_64kib(self):
        from app.schemas.display_preferences import DisplayPreferencesPatch
        big = {f'p-{i:03d}': {'columns': [f'c-{j:03d}-' + 'x' * 88 for j in range(20)]} for i in range(100)}
        with pytest.raises(ValidationError):
            DisplayPreferencesPatch.model_validate({'base_revision': 0, 'fixed_columns': big})

    def test_non_nullable_font_size(self):
        from app.schemas.display_preferences import DisplayPreferencesPatch
        with pytest.raises(ValidationError):
            DisplayPreferencesPatch.model_validate({'base_revision': 0, 'font_size': None})

    def test_nullable_amount_unit_override(self):
        from app.schemas.display_preferences import DisplayPreferencesPatch
        p = DisplayPreferencesPatch.model_validate({'base_revision': 0, 'amount_unit_override': None})
        assert p.business_fields_dict() == {'amount_unit_override': None}
