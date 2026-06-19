# G 类底稿（投资循环）— 设计文档

## 1. 架构总览 + componentType 路由表

```
wp_account_mapping.json (扩充 G 类 ~90 条)
  → WpClassificationService (_WP_CODE_OVERRIDE)
    → get_render_config (componentType 分发)
      → 前端 htmlRendererRegistry → 对应 Vue 组件
```

| wp_code 模式 | componentType | 说明 |
|-------------|--------------|------|
| G0A~G14A | `a-program-console` | 15 个程序表 |
| G0 | `confirmation-hub` | 函证路由 |
| G0-1~G0-5 | `d-form-table` | 函证辅助表 |
| G{n}-1（14个审定表） | `d-form-table` | 审定表回写 |
| G{n} 附注 sheet | `c-note-table` | disclosure_notes |
| G1-2/G1-3/G2-3/G4-3/G4-4/G4-5/G5-3/G6-3/G6-4/G7-3/G7-4/G7-5/G8-3/G10-3/G14-2 | `audit-sheet` | 含公式测算 |
| G1-4/G1-5/G2-2/G3-2/G3-3/G4-6/G4-7/G6-5/G7-6/G7-7/G8-4/G8-5/G9-2/G9-3/G10-2/G11-2/G11-3/G12-2/G13-2/G13-3/G14-3 | `audit-sheet` | 明细/分析/检查 |
| G1-6/G2-4/G3-4/G4-8/G5-4/G6-6/G7-8/G8-6/G9-4/G10-4/G11-4/G12-3/G13-4/G14-4 | `d-form-table` | 调整分录 |
| G5-2 | `d-form-table` | 简单明细 |

## 2. 数据模型

### 2.1 wp_account_mapping 扩充（~90 条）

**G0 函证组：** G0/G0-1~G0-5（6 条）
**G1 交易性金融资产：** G1/G1-1~G1-6（7 条）
**G2 应收利息：** G2/G2-1~G2-4（5 条）
**G3 应收股利：** G3/G3-1~G3-4（5 条）
**G4 债权投资：** G4/G4-1~G4-8（9 条）
**G5 长期应收款：** G5/G5-1~G5-4（5 条）
**G6 其他债权投资：** G6/G6-1~G6-6（7 条）
**G7 长期股权投资：** G7/G7-1~G7-8（9 条）
**G8 其他权益工具投资：** G8/G8-1~G8-6（7 条）
**G9 其他非流动金融资产：** G9/G9-1~G9-4（5 条）
**G10 交易性金融负债：** G10/G10-1~G10-4（5 条）
**G11 投资收益：** G11/G11-1~G11-4（5 条）
**G12 净敞口套期收益：** G12/G12-1~G12-3（4 条）
**G13 公允价值变动收益：** G13/G13-1~G13-4（5 条）
**G14 信用减值损失：** G14/G14-1~G14-4（5 条）

合计：~93 条

### 2.2 procedure_table_templates 扩展

G0A~G14A 共 15 个程序表，从各 xlsx 模板提取步骤。

### 2.3 auto_data_source resolvers

| source 名 | 用途 | 状态 |
|-----------|------|------|
| `risk_for_cycle` | G 程序表读取 B50 风险 | ✅ 已有 |
| `control_test_result_for_cycle` | G 程序表读取 C5 结论 | ✅ 已有 |
| `confirmation_summary_for_cycle` | G0 读取函证摘要 | ✅ 复用 cycle="G" |

## 3. 审定表标准字段

复用 D/E/F 通用结构（account_code/account_name/opening_balance/unadjusted_amount/aje_debit/aje_credit/rje_debit/rje_credit/audited_amount/prior_year_audited/variance_amount/variance_pct/variance_note）。

G1-1 特殊行：按金融资产分类（股票/债券/基金/衍生品）分行。
G7-1 特殊行：按被投资单位分行（成本法/权益法分组）。

## 4. 联动实现方案

- **审定表回写**：扩展 handler 正则 `^[D-N]\d+-1$` 覆盖 G1-1~G14-1
- **B50→G**：已就绪（risk_for_cycle cycle="G"）
- **C5→G**：已就绪（control_test_result_for_cycle cycle="G"）
- **G0→ConfirmationHub**：`_WP_CODE_OVERRIDE["G0"] = "confirmation-hub"`
- **G7-4 减值↔DCF**：通过 ref_index chip 跳转到 A3-8（非自动取数）
- **G13↔G1**：G13 公允价值变动收益通过 ref_index chip 跳转到 G1 交易性金融资产

## 5. address_registry 坐标注册

| wp_code | 关键坐标 | 用途 |
|---------|---------|------|
| G1-2/G1-3 | 公允价值合计/差额 | 金融资产明细 |
| G2-3 | 利息测算结论 | 利息计算验证 |
| G4-3/G4-4 | 摊余成本/实际利率 | 债权投资核心测算 |
| G4-5/G14-2 | ECL 三阶段结果 | 信用减值 |
| G5-3 | 现值合计 | 长期应收款折现 |
| G7-3/G7-4/G7-5 | 权益法/减值/收益 | 长期股权投资核心 |
| G8-3/G8-4 | 公允价值/OCI变动 | 权益工具投资 |

坐标文件：`backend/data/g_address_registry_seed.json`

## 6. 前端路由

复用现有底稿路由，G0 走 ConfirmationHub（cycle=G）。

## 7. 正确性属性

1. **wp_code 注册完整性**：G 类所有非导航 sheet 的 wp_code 存在于 wp_account_mapping
2. **_WP_CODE_OVERRIDE 覆盖率**：所有 G 类 wp_code 有对应映射
3. **审定表回写 round-trip**：G{n}-1 保存→trial_balance 查询值一致
4. **程序表模板完整性**：G{n}A 步骤数 ≥ xlsx 模板行数
5. **address_registry 坐标有效性**：坐标 sheet_name 存在于模板
6. **componentType 一致性**：程序表→a-program-console，审定表→d-form-table
7. **ECL 计算公式正确性**：G4-5/G14-2 三阶段模型输出合理
8. **实际利率法精度**：G4-3/G4-4 摊销计算误差 < 0.01 元

## 8. 错误处理

| 场景 | 处理 |
|------|------|
| 审定表回写失败 | WARNING 不阻断保存 |
| ECL 模型参数缺失 | 提示"请先设置信用损失参数" |
| 公允价值数据不可得 | 允许手动填写 |
| G7 减值 DCF 未完成 | 提示"请先完成减值测试" |

## 9. 测试策略

- 单元测试：wp_code 完整性 + componentType 映射 + 审定表 schema + 程序表 JSON
- 集成测试：审定表→trial_balance 回写（14 个审定表全部）
- E2E（≥3）：G1A 程序表联动 / G7-1 审定表回写 / G4-5 ECL audit-sheet 打开 / G0→ConfirmationHub
