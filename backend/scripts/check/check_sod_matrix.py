"""Phase 14 验收脚本：SoD 互斥矩阵验证

遍历 CONFLICT_MATRIX 所有组合，断言冲突场景返回 403。
用法: python -m scripts.phase14.check_sod_matrix
"""
import sys
from app.services.sod_guard_service import CONFLICT_MATRIX, POLICY_CODES

fail = 0

print("=== SoD Conflict Matrix Verification ===\n")

# 验证矩阵完整性
expected_pairs = 6  # 3 pairs × 2 directions
if len(CONFLICT_MATRIX) == expected_pairs:
    print(f"  [PASS] CONFLICT_MATRIX has {expected_pairs} entries (3 pairs × 2 directions)")
else:
    print(f"  [FAIL] CONFLICT_MATRIX has {len(CONFLICT_MATRIX)} entries, expected {expected_pairs}")
    fail += 1

# 验证每个冲突对都有 policy_code
for key, desc in CONFLICT_MATRIX.items():
    if key in POLICY_CODES:
        print(f"  [PASS] {key[0]}↔{key[1]}: '{desc}' → {POLICY_CODES[key]}")
    else:
        print(f"  [FAIL] {key[0]}↔{key[1]}: missing policy_code")
        fail += 1

# 验证非冲突场景
non_conflict_pairs = [
    ("reviewer", "partner_approver"),
    ("qc_reviewer", "reviewer"),
    ("qc_reviewer", "partner_approver"),
]
for pair in non_conflict_pairs:
    if pair not in CONFLICT_MATRIX:
        print(f"  [PASS] {pair[0]}↔{pair[1]}: correctly NOT in conflict matrix")
    else:
        print(f"  [FAIL] {pair[0]}↔{pair[1]}: should NOT be in conflict matrix")
        fail += 1

print(f"\n[RESULT] {'ALL PASS ✓' if fail == 0 else f'{fail} FAILURES ✗'}")
sys.exit(0 if fail == 0 else 1)
