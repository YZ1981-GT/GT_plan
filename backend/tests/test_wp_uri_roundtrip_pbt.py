# Feature: custom-workpaper-formula-binding, Property 2: URI / formula_ref 往返
"""WP 域 formula_ref ↔ uri 往返一致。"""
from __future__ import annotations

from hypothesis import given, settings, strategies as st

from app.services.address_registry import formula_ref_to_uri, uri_to_formula_ref

wp_code_st = st.sampled_from(["CUST-01", "D11", "E11", "FAKE99"])
cell_st = st.sampled_from(["B5", "C12", "A1", "Z99"])


@settings(max_examples=5)
@given(wp_code=wp_code_st, cell=cell_st)
def test_wp_formula_ref_uri_roundtrip(wp_code: str, cell: str):
    ref = f"WP('{wp_code}','{cell}')"
    uri = formula_ref_to_uri(ref)
    assert uri is not None
    assert uri.startswith("wp://")
    assert f"/{cell}" in uri or uri.endswith(f"#{cell}")
    back = uri_to_formula_ref(uri)
    assert back == ref
