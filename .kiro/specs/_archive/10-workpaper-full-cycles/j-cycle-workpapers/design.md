# J 类底稿（职工薪酬循环）— 设计文档

## 1. 架构总览 + componentType 路由表

| wp_code 模式 | componentType | 说明 |
|-------------|--------------|------|
| J1A~J3A | `a-program-console` | 3 个程序表 |
| J{n}-1（3个审定表） | `d-form-table` | 审定表回写 |
| J{n} 附注 sheet | `c-note-table` | disclosure_notes |
| J1-2/J1-3/J1-4/J2-5/J3-4/J3-5 | `audit-sheet` | 含公式测算 |
| J1-5/J1-6/J1-7/J2-2/J3-2 | `audit-sheet` | 分析/检查/明细 |
| J2-3/J2-4/J3-3 | `d-form-table` | 结构化检查 |
| J1-8/J2-6/J3-6 | `d-form-table` | 调整分录 |

## 2. 数据模型

### 2.1 wp_account_mapping 扩充（~24 条）

**J1 应付职工薪酬：** J1/J1-1~J1-8（9 条）
**J2 设定受益计划：** J2/J2-1~J2-6（7 条）
**J3 股份支付：** J3/J3-1~J3-6（7 条）

合计：~23 条

### 2.2 procedure_table_templates 扩展

J1A~J3A 共 3 个程序表。

### 2.3 auto_data_source resolvers

| source 名 | 用途 | 状态 |
|-----------|------|------|
| `risk_for_cycle` | J 程序表读取 B50 | ✅ |
| `control_test_result_for_cycle` | J 程序表读取 C10 | ✅ |
| `accounting_estimate_b51` | J2 精算假设读取 B51 | ✅ 复用 F2 跌价 |

## 3. 审定表标准字段

复用通用结构。J1-1 特殊：按薪酬类别分行（工资/奖金/社保/公积金/福利/辞退福利）。

## 4. 联动实现方案

- **审定表回写**：正则 `^J\d+-1$` 覆盖 J1-1~J3-1
- **B50→J / C10→J**：已就绪
- **J2→B51**：复用 `accounting_estimate_b51` resolver（精算假设=会计估计）
- **J3→M4**：通过 ref_index chip 关联（非自动取数）

## 5. address_registry 坐标注册

| wp_code | 关键坐标 | 用途 |
|---------|---------|------|
| J1-3 | 工资测算合计/差异 | 工资验证 |
| J1-4 | 社保测算合计 | 社保验证 |
| J2-5 | DBO现值/计划资产 | 精算重算 |
| J3-4 | 期权公允价值 | 期权定价 |
| J3-5 | 当期费用分摊 | 等待期费用 |

坐标文件：`backend/data/j_address_registry_seed.json`

## 6. 前端路由

复用现有底稿路由。J 类无函证组。

## 7. 正确性属性

1. **wp_code 注册完整性**：J 类所有 sheet 有 wp_code
2. **_WP_CODE_OVERRIDE 覆盖率**：100%
3. **审定表回写 round-trip**：J{n}-1 保存→查询一致
4. **程序表完整性**：步骤数 ≥ xlsx 模板
5. **工资测算逻辑**：J1-3 合计 = Σ(人数×平均工资×月份)
6. **精算假设合理性**：J2-3 折现率在合理范围内（0%~15%）
7. **期权定价非负**：J3-4 Black-Scholes 输出 ≥ 0

## 8. 错误处理

| 场景 | 处理 |
|------|------|
| 审定表回写失败 | WARNING 不阻断 |
| B51 精算评估未完成 | J2 提示"请先完成 B51 评估" |
| 期权参数缺失 | 提示"请设置行权价/波动率/无风险利率" |

## 9. 测试策略

- 单元测试：wp_code + componentType + schema + 程序表
- 集成测试：审定表→trial_balance 回写（3 个）
- E2E（≥3）：J1A 程序表联动 / J2-3 精算假设 d-form-table / J3-4 期权定价 audit-sheet
