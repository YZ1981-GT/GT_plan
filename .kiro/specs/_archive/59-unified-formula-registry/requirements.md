# 需求：统一公式注册表（Unified Formula Registry）

> 本 spec 对应评估报告的 **Step 1**：收敛公式注册碎片，建立全平台公式的单一目录。

## 背景

平台 6 个公式域的注册入口分散在 5 张表 + 1 个 JSON 文件 + 1 个 JSON 字段，3 套独立的执行器各自维护函数列表和语法正则。Step 0（`formula-settings-wiring-closure`）已修复 4 处接线断裂并建立了生产接线守卫，但底层碎片仍在。

### 现状碎片化清单

| 存储后端 | 域 | 执行字段 |
|---------|---|---------|
| `report_config` 列 | report | formula, aje_formula, rje_formula |
| `wp_formula` 表 + `prefill_formula_mapping.json` | wp | expression |
| `formula_setting` 表 (domain=note\|cross_check\|tb_detail) | note, cross_check, tb_detail | formula\|left_ref+right_ref\|formula |
| `consol_note_formula` 表 + `formula_setting` | consol_note | formula |
| `disclosure_notes.table_data._user_formulas` | note（物化目标） | — |

执行器碎片：
- **L1 内核** `formula_engine.execute()`：AST 递归下降，`FunctionRegistry` 注册 14 函数（不含 LEDGER/TB_AUX 等底稿专用函数）
- **L2 编排层** `evaluate_formula_result()`：regex 预替换 → L1（报表 + 表间审核共用）
- **底稿预填充** `prefill_engine.py`：独立 regex 执行器（支持 `LEDGER/LEDGER_DETAIL/TB_AUX/COUNT_LEDGER`，完全不经 L1）
- **前端语法高亮** `formulaSyntaxParser.ts`：Step 0 已对齐到 16 函数，但尚未与后端运行时共享定义

## R1 公式目录（Formula Catalog）

> 全平台所有公式位的单一可查询目录。

- R1.1 新增 `GET /api/formula-catalog?project_id=…&domain=…`，返回本项目有效公式的扁平列表（跨 6 域一次返回）。每项包含：`addr_id`（ACNR 地址）、`domain`、`formula_text`、`layer`（全局/本项目/预设）、`function_refs`（引用的函数清单）、`target_label`。
- R1.2 目录构建复用既有 `effective_slots()`，不引入新存储。
- R1.3 `GET /api/formula-catalog/stats` 返回按域和按层级的公式计数摘要，供公式管理看板消费。

## R2 函数注册表统一（FunctionRegistry Convergence）

> 消灭 L1 内核与 prefill_engine 的函数列表分歧。

- R2.1 `formula_engine._REGISTRY` 新增 `LEDGER`(3 参)、`LEDGER_DETAIL`(3 参)、`TB_AUX`(3 参)、`COUNT_LEDGER`(3 参) 四个底稿专用函数的 **handler 占位**（底稿路径取数逻辑不变，但函数名注册后，`validate_formula` 和 `formulaSyntaxParser.ts` 不再报「未知函数」）。
- R2.2 `prefill_engine.py` 的 `_FORMULA_RE` 改从 `_REGISTRY.known_function_names()` 派生，不再维护独立的函数名列表。
- R2.3 `formula_grammar.FORMULA_ARITY` 改从 `_REGISTRY` 的 metadata 派生（单一真源）。
- R2.4 前端 `formulaSyntaxParser.ts` 改从后端 `GET /api/formula-functions` 取函数定义，前端零硬编码（可渐进：先加端点，前端按需消费）。

## R3 公式位命名规范化（Slot Key Normalization）

- R3.1 建立公式位命名规范文档（`docs/reference/formula-slot-key-spec.md`），覆盖 6 域的 slot_key 格式、与 ACNR addr_id 的映射关系。
- R3.2 `formula_catalog` 的 addr_id 与 ACNR 地址坐标一致（report 域 = `report:{type}:{code}`，wp 域 = `wp:{code}/{sheet}/{cell}`，note 域 = `note:{section}`，tb 域 = `tb:{account}`）。

## R4 依赖图接入目录

- R4.1 `dependencies.py` 的 `formula_dependencies()` 改从 `formula_catalog` 取公式文本（当前直接调 `effective_slots`，改为经目录保证口径一致）。
- R4.2 新增 `GET /api/formula-catalog/{addr_id}/dependencies`（与现有 `/formula-settings/dependencies` 共用 service，路由别名）。

## R5 验收

- R5.1 后端测试：catalog 端点按 6 域全覆盖 + stats 聚合正确 + 函数注册表统一无遗漏
- R5.2 前端测试：formulaSyntaxParser 动态取函数清单（mock 端点）
- R5.3 生产接线守卫扩展：`test_production_wiring.py::WIRED_FUNCTIONS` 新增 catalog 相关函数
