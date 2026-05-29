"""Phase 14 验收脚本：QC-19~26 规则覆盖率检查

断言 RuleRegistry 中 QC-19~26 全部注册到 submit_review/sign_off。
用法: python -m scripts.phase14.check_rule_coverage
"""
import sys
from app.services.gate_engine import rule_registry
from app.services.gate_rules_phase14 import register_phase14_rules
from app.models.phase14_enums import GateType

register_phase14_rules()

REQUIRED_RULES = ["QC-19", "QC-20", "QC-21", "QC-22", "QC-23", "QC-24", "QC-25", "QC-26"]
REQUIRED_GATES = [GateType.submit_review, GateType.sign_off]

fail = 0
for gate in REQUIRED_GATES:
    registered = [r.rule_code for r in rule_registry.get_rules(gate)]
    for rule in REQUIRED_RULES:
        if rule in registered:
            print(f"  [PASS] {gate}:{rule}")
        else:
            print(f"  [FAIL] {gate}:{rule} NOT REGISTERED")
            fail += 1

# 检查 CONSISTENCY-BLOCK 在 sign_off
sign_rules = [r.rule_code for r in rule_registry.get_rules(GateType.sign_off)]
if "CONSISTENCY-BLOCK" in sign_rules:
    print(f"  [PASS] sign_off:CONSISTENCY-BLOCK")
else:
    print(f"  [FAIL] sign_off:CONSISTENCY-BLOCK NOT REGISTERED")
    fail += 1

print(f"\n[RESULT] {'ALL PASS' if fail == 0 else f'{fail} FAILURES'}")
sys.exit(0 if fail == 0 else 1)
