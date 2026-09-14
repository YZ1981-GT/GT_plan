# L 类底稿（筹资循环）— 设计文档

## 1. 架构总览 + componentType 路由表

| wp_code 模式 | componentType | 说明 |
|-------------|--------------|------|
| L0A~L8A | `a-program-console` | 9 个程序表 |
| L0 | `confirmation-hub` | 函证路由（银行） |
| L0-1~L0-5 | `d-form-table` | 函证辅助表 |
| L{n}-1（8个审定表） | `d-form-table` | 审定表回写 |
| L{n} 附注 sheet | `c-note-table` | disclosure_notes |
| L1-3/L2-3/L3-3/L4-3/L4-4/L4-5/L5-3/L8-3/L8-5 | `audit-sheet` | 利息/摊销/汇兑公式 |
| L1-2/L1-4/L3-2/L4-2/L4-6/L5-2/L6-2/L7-2/L8-2/L8-4 | `audit-sheet` | 明细/分析 |
| L1-5/L3-5/L4-7/L6-3/L7-3/L8-4 | `audit-sheet` | 检查 |
| L3-4 | `d-form-table` | 一年内到期重分类 |
| L1-6/L2-4/L3-6/L4-8/L5-4/L6-4/L7-4/L8-6 | `d-form-table` | 调整分录 |

## 2. 数据模型

### 2.1 wp_account_mapping 扩充（~52 条）

**L0 函证：** L0/L0-1~L0-5（6 条）
**L1 短期借款：** L1/L1-1~L1-6（7 条）
**L2 应付利息：** L2/L2-1~L2-4（5 条）
**L3 长期借款：** L3/L3-1~L3-6（7 条）
**L4 应付债券：** L4/L4-1~L4-8（9 条）
**L5 长期应付款：** L5/L5-1~L5-4（5 条）
**L6 专项应付款：** L6/L6-1~L6-4（5 条）
**L7 其他非流动负债：** L7/L7-1~L7-4（5 条）
**L8 财务费用：** L8/L8-1~L8-6（7 条）

合计：~56 条

### 2.2 procedure_table_templates 扩展

L0A~L8A 共 9 个程序表。

### 2.3 auto_data_source resolvers

| source 名 | 用途 | 状态 |
|-----------|------|------|
| `risk_for_cycle` | L 程序表读取 B50 | ✅ |
| `control_test_result_for_cycle` | L 程序表读取 C13/C14 | ✅ |
| `confirmation_summary_for_cycle` | L0 函证摘要 | ✅ 复用 cycle="L" |

## 3. 审定表标准字段

复用通用结构。L4-1 特殊：按债券品种分行（面值/票面利率/到期日/摊余成本）。

## 4. 联动实现方案

- **审定表回写**：正则 `^L\d+-1$` 覆盖 L1-1~L8-1
- **L0→ConfirmationHub**：`_WP_CODE_OVERRIDE["L0"] = "confirmation-hub"`
- **L1/L3/L4→L8**：L8-3 利息测算通过 ref_index chip 汇总各借款利息
- **L4↔G4**：通过 ref_index 对称关联（发行方 vs 持有方）

## 5. address_registry 坐标注册

| wp_code | 关键坐标 | 用途 |
|---------|---------|------|
| L1-3 | 利息合计/差异 | 短期借款利息 |
| L3-3 | 利息合计/差异 | 长期借款利息 |
| L4-3/L4-4 | 实际利率/摊余成本 | 应付债券核心 |
| L8-3 | 利息费用合计 | 财务费用利息 |
| L8-5 | 汇兑损益合计 | 财务费用汇兑 |

坐标文件：`backend/data/l_address_registry_seed.json`

## 6. 前端路由

复用现有底稿路由，L0→ConfirmationHub（cycle=L）。

## 7. 正确性属性

1. **wp_code 注册完整性**：L 类所有 sheet 有 wp_code
2. **_WP_CODE_OVERRIDE 覆盖率**：100%
3. **审定表回写 round-trip**：L{n}-1 保存→查询一致
4. **程序表完整性**：步骤数 ≥ xlsx 模板
5. **实际利率法精度**：L4-4 期末摊余成本误差 < 0.01 元
6. **利息测算一致性**：L8-3 利息合计 ≈ L1-3 + L3-3 + L4-5 之和
7. **汇兑损益公式**：L8-5 = (期末汇率 - 记账汇率) × 外币余额

## 8. 错误处理

| 场景 | 处理 |
|------|------|
| 审定表回写失败 | WARNING 不阻断 |
| 实际利率无解 | 提示"请检查债券条款参数" |
| 汇率数据缺失 | 提示"请设置期末汇率" |
| 银行函证未回函 | L0 标记"未回函"状态 |

## 9. 测试策略

- 单元测试：wp_code + componentType + schema + 程序表 + 实际利率法
- 集成测试：审定表→trial_balance 回写（8 个）
- E2E（≥3）：L1A 程序表联动 / L4-4 摊销表 audit-sheet / L8-1 审定表回写 / L0→ConfirmationHub
