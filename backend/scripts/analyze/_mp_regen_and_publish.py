import sys, json, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
out_dir = pathlib.Path(__file__).resolve().parents[2] / "data" / "workpaper_sync_contracts"
for mn, fn in [
    ("app.services.workpaper_sync.phase5_m1_dividends_payable", "m1.dividends_payable.json"),
    ("app.services.workpaper_sync.phase5_m5_surplus_reserve", "m5.surplus_reserve.json"),
    ("app.services.workpaper_sync.phase5_m8_general_risk_reserve", "m8.general_risk_reserve.json"),
    ("app.services.workpaper_sync.phase5_m9_other_comprehensive_income", "m9.other_comprehensive_income.json"),
]:
    mod = __import__(mn, fromlist=["build_contract_payload"])
    p = mod.build_contract_payload()
    (out_dir / fn).write_text(json.dumps(p, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  {fn}: regenerated")
print("All contracts regenerated with clean template sha256")
