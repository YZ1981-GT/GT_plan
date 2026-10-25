"""Probe: how do mapping entries with applicable_when (and the S bundle parents) look today?

Prints per-entry: wp_code, trigger, applies_when, must_have, account_codes, applicable_when.
Then simulates match_workpapers with/without the proposed 4th path for an IPO project and a plain one.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[4]
MAPPING = ROOT / "backend" / "data" / "wp_account_mapping.json"
ALT = ROOT / "backend" / "app" / "data" / "wp_account_mapping.json"

print("mapping path:", MAPPING, "exists=", MAPPING.exists())
print("alt path (design §1.3.2 code uses this):", ALT, "exists=", ALT.exists())

raw = json.loads(MAPPING.read_bytes().decode("utf-8"))
data = raw["mappings"] if isinstance(raw, dict) else raw
print("top-level type:", type(raw).__name__, "keys:", list(raw)[:5] if isinstance(raw, dict) else "-")
print("entries:", len(data))

aw = [m for m in data if m.get("applicable_when")]
print("entries with applicable_when:", len(aw))
print("applicable_when key sets:", Counter(tuple(sorted(m["applicable_when"])) for m in aw))
print("trigger values among them:", Counter(m.get("trigger") for m in aw))
print("with account_codes among them:", sum(1 for m in aw if m.get("account_codes")))
vals = Counter(v for m in aw for vs in m["applicable_when"].values() for v in vs)
print("declared values:", dict(vals))
print()
print("--- applicable_when entries (wp_code | trigger | applies_when | must_have | n_acc | aw) ---")
for m in aw:
    print(
        f"{m.get('wp_code')!s:10} | {m.get('trigger')!s:12} | {m.get('applies_when')!s:14} | "
        f"{m.get('must_have')!s:5} | {len(m.get('account_codes') or [])} | {m['applicable_when']}"
    )

print()
print("--- S parents / S1 S8 S9 S10 S17 entries ---")
for m in data:
    code = m.get("wp_code", "")
    if code in {"S1", "S8", "S9", "S10", "S17", "S32", "S33", "S34", "S35", "S20", "S15", "S6"} or code.startswith(("S17-", "S9-", "S10-")):
        print(
            f"{code!s:10} | trigger={m.get('trigger')!s:12} | applies_when={m.get('applies_when')!s:14} | "
            f"must_have={m.get('must_have')!s:5} | acc={m.get('account_codes')} | aw={m.get('applicable_when')} | "
            f"linked={m.get('linked_workpapers')}"
        )

# --- simulate generation -----------------------------------------------------
sys.path.insert(0, str(ROOT / "backend"))
from app.services.wp_generation_matching import match_workpapers  # noqa: E402

plain_flags: dict[str, bool] = {}
ipo_flags = {"biz_ipo": True}


def proposed(mappings, tb, flags):
    _KEY = {"business_category": "biz_", "industry": "ind_"}
    prim: set[str] = set()
    subs: dict[str, list[str]] = {}
    for m in mappings:
        wp_code = m.get("wp_code", "")
        if not wp_code:
            continue
        primary = wp_code.split("-")[0] if "-" in wp_code else wp_code
        acc = m.get("account_codes", [])
        if acc and any(a in tb for a in acc):
            hit = True
        elif m.get("trigger") == "must_have":
            hit = True
        elif m.get("trigger") == "conditional":
            hit = bool(m.get("applies_when") and flags.get(m.get("applies_when")))
        elif m.get("applicable_when"):
            hit = False
            for key, values in m["applicable_when"].items():
                prefix = _KEY.get(key, f"{key}_")
                if any(flags.get(f"{prefix}{v}") for v in values):
                    hit = True
                    break
        else:
            hit = False
        if hit:
            prim.add(primary)
            if wp_code != primary:
                subs.setdefault(primary, []).append(wp_code)
    return prim, subs


tb: set[str] = set()
cur_plain, _ = match_workpapers(data, tb, plain_flags)
cur_ipo, _ = match_workpapers(data, tb, ipo_flags)
new_plain, _ = proposed(data, tb, plain_flags)
new_ipo, new_ipo_subs = proposed(data, tb, ipo_flags)
S = lambda s: sorted(c for c in s if c.startswith("S"))  # noqa: E731
print()
print("current plain  S codes:", S(cur_plain))
print("current ipo    S codes:", S(cur_ipo))
print("proposed plain S codes:", S(new_plain))
print("proposed ipo   S codes:", S(new_ipo))
print("proposed ipo adds:", sorted(new_ipo - cur_ipo))
print("S34 subtables matched (ipo):", len(new_ipo_subs.get("S34", [])))
