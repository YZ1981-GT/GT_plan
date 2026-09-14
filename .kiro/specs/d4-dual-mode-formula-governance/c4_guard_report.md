# C4 行为守卫报告

## 覆盖的 Requirement

| Guard | Requirement | 说明 |
|-------|-------------|------|
| Guard 1 | Req 1.1 | C0 矩阵恰好 36 个 wp_code，无重复，D4-1..D4-36 连续 |
| Guard 2 | Req 2.2 | 同字段异值必产生冲突（禁 LWW）；不同字段自动合并 |
| Guard 3 | Req 3.2 | F-SHELL v2 白名单：eval/exec/URL/非法函数名均被拒绝 |
| Guard 4 | Req 4.1 | DAG 循环检测 + topological_sort 对循环图抛 ValueError |
| Guard 5 | Req 5.1 | D4 提取模块不复制科目 SQL，必须通过 four_table 服务 |

## UNVERIFIABLE 项（不在本文件中假绿）

- Playwright E2E 测试（需 start-dev.bat 环境）
- OO/OnlyOffice roundtrip（需外部服务）
- 权限隔离验证（需真实多用户环境）
- CAS save() baseVersion 缺失（C2 已知机制缺口）
- TB 发布显式确认端点（C3 已知机制缺口）

## 运行方式

```bash
# cwd=backend
python -m pytest .kiro/specs/d4-dual-mode-formula-governance/c4_guard_tests.py -v --tb=short
```

所有导入失败 → `pytest.skip()`，保证在完整后端环境下可运行。
