"""Enhance 270 basic fine rules with cycle-appropriate audit checks.

A类(完成阶段): 完整性+签署+日期合理性
B类(风险评估): 完整性+风险等级+应对措施
C类(控制测试): 完整性+偏差记录+结论
D-N函证(X0): 函证回函率+差异+替代程序
S类(特定项目): 完整性+结论+文档化
"""
import json
from pathlib import Path

rules_dir = Path(__file__).resolve().parent.parent / "data" / "wp_fine_rules"

# Generic checks by cycle type
A_CHECKS = [
    {"id": "{code}-CHK-01", "type": "completeness", "severity": "warning", "description": "底稿已填写完整（非空白）"},
    {"id": "{code}-CHK-02", "type": "check", "severity": "warning", "description": "编制人和复核人已签署"},
    {"id": "{code}-CHK-03", "type": "check", "severity": "info", "description": "编制日期在审计期间内"},
]

B_CHECKS = [
    {"id": "{code}-CHK-01", "type": "completeness", "severity": "warning", "description": "风险评估表已填写完整"},
    {"id": "{code}-CHK-02", "type": "check", "severity": "warning", "description": "风险等级已标注（高/中/低）"},
    {"id": "{code}-CHK-03", "type": "check", "severity": "info", "description": "应对措施已记录"},
]

C_CHECKS = [
    {"id": "{code}-CHK-01", "type": "completeness", "severity": "warning", "description": "控制测试表已填写完整"},
    {"id": "{code}-CHK-02", "type": "check", "severity": "warning", "description": "测试样本量和结果已记录"},
    {"id": "{code}-CHK-03", "type": "check", "severity": "warning", "description": "控制偏差已记录并评价"},
    {"id": "{code}-CHK-04", "type": "check", "severity": "info", "description": "控制有效性结论已填写"},
]

CONFIRM_CHECKS = [
    {"id": "{code}-CHK-01", "type": "confirmation", "severity": "warning", "description": "函证发函记录完整"},
    {"id": "{code}-CHK-02", "type": "confirmation", "severity": "warning", "description": "回函率统计已记录"},
    {"id": "{code}-CHK-03", "type": "check", "severity": "warning", "description": "差异事项已跟进处理"},
    {"id": "{code}-CHK-04", "type": "check", "severity": "info", "description": "未回函项目已执行替代程序"},
]

S_CHECKS = [
    {"id": "{code}-CHK-01", "type": "completeness", "severity": "warning", "description": "底稿已填写完整"},
    {"id": "{code}-CHK-02", "type": "check", "severity": "warning", "description": "审计结论已记录"},
    {"id": "{code}-CHK-03", "type": "check", "severity": "info", "description": "支持性文档已附"},
]

DEFAULT_CHECKS = [
    {"id": "{code}-CHK-01", "type": "completeness", "severity": "warning", "description": "底稿已填写完整"},
    {"id": "{code}-CHK-02", "type": "check", "severity": "info", "description": "编制人已签署"},
]

upgraded = 0
for fp in sorted(rules_dir.glob("*.json")):
    data = json.loads(fp.read_text(encoding="utf-8"))
    sr = data.get("sheet_rules", [])
    checks = data.get("audit_checks", [])
    has_layout = any(r.get("layout") for r in sr)
    
    # Only process basic files (no layout, <4 checks)
    if has_layout or len(checks) >= 4:
        continue
    
    code = data.get("wp_code", "")
    cycle = data.get("cycle", code[0] if code else "?")
    
    # Determine which checks to add
    is_confirm = code.endswith("0") and cycle in "DEFGHKLM"
    
    if is_confirm:
        template = CONFIRM_CHECKS
    elif cycle == "A":
        template = A_CHECKS
    elif cycle == "B":
        template = B_CHECKS
    elif cycle == "C":
        template = C_CHECKS
    elif cycle == "S" or cycle == "T":
        template = S_CHECKS
    else:
        template = DEFAULT_CHECKS
    
    # Build new checks with code substitution
    existing_ids = {c.get("id", c.get("code", "")) for c in checks}
    new_checks = list(checks)  # keep existing
    
    for tmpl in template:
        chk = dict(tmpl)
        chk["id"] = chk["id"].replace("{code}", code)
        if chk["id"] not in existing_ids:
            new_checks.append(chk)
    
    if len(new_checks) > len(checks):
        data["audit_checks"] = new_checks
        fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        upgraded += 1

print(f"Enhanced {upgraded} basic files with cycle-appropriate checks")
