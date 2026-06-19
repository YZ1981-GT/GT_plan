# I 类底稿（无形资产循环）— 设计文档

## 1. 架构总览 + componentType 路由表

| wp_code 模式 | componentType | 说明 |
|-------------|--------------|------|
| I1A~I6A | `a-program-console` | 6 个程序表 |
| I{n}-1（6个审定表） | `d-form-table` | 审定表回写 |
| I{n} 附注 sheet | `c-note-table` | disclosure_notes |
| I1-2/I1-3/I1-4/I1-5/I3-2/I3-4/I3-5/I4-2/I5-2/I6-2/I6-5/I6-7 | `audit-sheet` | 含公式/大数据 |
| I1-6/I1-7/I2-4/I2-5/I4-3/I5-3/I6-4/I6-6 | `audit-sheet` | 分析/检查 |
| I2-3/I6-3 | `d-form-table` | 资本化条件检查 |
| I1-8/I2-6/I3-6/I4-4/I5-4/I6-8 | `d-form-table` | 调整分录 |
| I3-3 | `d-form-table` | 减值测试概要 |

## 2. 数据模型

### 2.1 wp_account_mapping 扩充（~42 条）

**I1 无形资产：** I1/I1-1~I1-8（9 条）
**I2 开发支出：** I2/I2-1~I2-6（7 条）
**I3 商誉：** I3/I3-1~I3-6（7 条）
**I4 长期待摊费用：** I4/I4-1~I4-4（5 条）
**I5 其他非流动资产：** I5/I5-1~I5-4（5 条）
**I6 研发费用：** I6/I6-1~I6-8（9 条）

合计：~42 条

### 2.2 procedure_table_templates 扩展

I1A~I6A 共 6 个程序表。

### 2.3 auto_data_source resolvers

| source 名 | 用途 | 状态 |
|-----------|------|------|
| `risk_for_cycle` | I 程序表读取 B50 | ✅ |
| `control_test_result_for_cycle` | I 程序表读取 C8/C9 | ✅ |
| `goodwill_dcf_result` | I3 读取 A3-8 DCF 结果 | 🔴 待联动 |

## 3. 审定表标准字段

复用通用结构。I1-1 特殊：按无形资产类别（土地/软件/专利/特许）分行+累计摊销/减值扣减。

## 4. 联动实现方案

- **审定表回写**：正则 `^I\d+-1$` 覆盖 I1-1~I6-1
- **B50→I / C8+C9→I**：已就绪
- **I3↔A3-8 DCF**：I3-4 通过 ref_index chip 跳转到 goodwill-impairment 底稿
- **I6→N5 加计扣除**：I6-7 测算结果通过 ref_index 关联 N5 所得税

## 5. address_registry 坐标注册

| wp_code | 关键坐标 | 用途 |
|---------|---------|------|
| I1-3 | 摊销合计/差异 | 摊销验证 |
| I1-4 | 减值结论 | 减值测试 |
| I3-4 | WACC/NPV/可收回金额 | DCF 核心 |
| I3-5 | 敏感性矩阵结论 | 敏感性分析 |
| I6-7 | 加计扣除金额 | 研发加计 |

坐标文件：`backend/data/i_address_registry_seed.json`

## 6. 前端路由

复用现有底稿路由。I 类无函证组无 ConfirmationHub 路由。

## 7. 正确性属性

1. **wp_code 注册完整性**：I 类所有 sheet 有 wp_code
2. **_WP_CODE_OVERRIDE 覆盖率**：100%
3. **审定表回写 round-trip**：I{n}-1 保存→查询一致
4. **程序表完整性**：步骤数 ≥ xlsx 模板
5. **DCF 公式正确性**：I3-4 NPV = Σ(FCF_t/(1+WACC)^t) + TV/(1+WACC)^n
6. **摊销测算精度**：I1-3 误差 < 0.01 元
7. **资本化条件逻辑**：I2-3 五条件全部为"是"时才可资本化

## 8. 错误处理

| 场景 | 处理 |
|------|------|
| DCF 参数缺失 | 提示"请设置 WACC/增长率" |
| 资本化条件不满足 | 自动标记"应费用化" |
| 摊销年限=0 | 校验拦截 |

## 9. 测试策略

- 单元测试：wp_code + componentType + schema + 程序表 + 资本化条件逻辑
- 集成测试：审定表→trial_balance 回写（6 个）
- E2E（≥3）：I1A 程序表联动 / I3-4 DCF audit-sheet / I6-3 资本化条件 d-form-table
