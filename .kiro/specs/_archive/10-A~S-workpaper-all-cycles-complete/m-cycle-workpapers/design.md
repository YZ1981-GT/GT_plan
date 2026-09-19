# M 类底稿（股东权益循环）— 设计文档

## 1. 架构总览 + componentType 路由表

| wp_code 模式 | componentType | 说明 |
|-------------|--------------|------|
| M1A~M10A | `a-program-console` | 10 个程序表 |
| M{n}-1（10个审定表） | `d-form-table` | 审定表回写 |
| M{n} 附注 sheet | `c-note-table` | disclosure_notes |
| M6-2/M6-5 | `audit-sheet` | 勾稽表/损益联动（含公式） |
| M2-2/M4-2/M4-3/M9-2/M9-4/M9-5 | `audit-sheet` | 明细/变动/分析 |
| M1-2/M3-2/M5-2/M7-2/M8-2/M10-2 | `audit-sheet` | 明细 |
| M2-3/M2-4/M2-5/M3-3/M4-4/M5-3/M6-3/M6-4/M7-3/M8-3/M9-3/M10-3 | `d-form-table` | 验资/检查/分类 |
| M4-5 | `d-form-table` | 股份支付联动 |
| M1-3/M1-4/M3-4/M4-6/M5-4/M6-6/M7-4/M8-4/M9-6/M10-4 | `d-form-table` | 调整分录/分配决议 |

## 2. 数据模型

### 2.1 wp_account_mapping 扩充（~50 条）

**M1 应付股利：** M1/M1-1~M1-4（5 条）
**M2 实收资本：** M2/M2-1~M2-6（7 条）
**M3 库存股：** M3/M3-1~M3-4（5 条）
**M4 资本公积：** M4/M4-1~M4-6（7 条）
**M5 盈余公积：** M5/M5-1~M5-4（5 条）
**M6 未分配利润：** M6/M6-1~M6-6（7 条）
**M7 专项储备：** M7/M7-1~M7-4（5 条）
**M8 一般风险准备：** M8/M8-1~M8-4（5 条）
**M9 其他综合收益：** M9/M9-1~M9-6（7 条）
**M10 其他权益工具：** M10/M10-1~M10-4（5 条）

合计：~58 条

### 2.2 procedure_table_templates 扩展

M1A~M10A 共 10 个程序表。

### 2.3 auto_data_source resolvers

| source 名 | 用途 | 状态 |
|-----------|------|------|
| `risk_for_cycle` | M 程序表读取 B50 | ✅ |
| `control_test_result_for_cycle` | M 程序表读取 C1（企业层面） | ✅ |
| `income_statement_total` | M6 未分配利润读取损益合计 | 🔴 需新增 |

新增 resolver：
```python
@auto_resolver("income_statement_total")
async def _resolve_income_total(db, project_id, year, **kw):
    """汇总 D~N 损益类科目 audited_amount 得到本年净利润"""
    # SELECT SUM(audited_amount) FROM trial_balance
    # WHERE project_id=X AND year=Y AND standard_account_code LIKE '5%' OR '6%'
    return {"net_income": ..., "total_revenue": ..., "total_expense": ...}
```

## 3. 审定表标准字段

复用通用结构。M2-1 特殊：按股东分行（持股比例/出资方式/认缴/实缴）。
M6-1 特殊：单行（期初+净利润-提取-分配=期末），公式型。

## 4. 联动实现方案

- **审定表回写**：正则 `^M\d+-1$` 覆盖 M1-1~M10-1
- **C1→M**：复用 control_test_result_for_cycle（无独立 C 类，读 C1）
- **M6→损益合计**：`income_statement_total` resolver 汇总 D~N 审定额
- **M4→J3**：通过 ref_index chip 关联股份支付
- **M9→G8**：通过 ref_index 关联 OCI 来源（其他权益工具投资）
- **M8 适用性**：applicable_when: industry IN ['banking','insurance','securities']

## 5. address_registry 坐标注册

| wp_code | 关键坐标 | 用途 |
|---------|---------|------|
| M6-2 | 期初/净利润/分配/期末 | 未分配利润勾稽 |
| M6-5 | 损益合计/净利润核对 | 损益联动验证 |
| M2-2 | 股东出资明细 | 实收资本 |
| M9-2 | OCI 变动明细 | 其他综合收益 |

坐标文件：`backend/data/m_address_registry_seed.json`

## 6. 前端路由

复用现有底稿路由。M 类无函证组。

## 7. 正确性属性

1. **wp_code 注册完整性**：M 类所有 sheet 有 wp_code
2. **_WP_CODE_OVERRIDE 覆盖率**：100%
3. **审定表回写 round-trip**：M{n}-1 保存→查询一致
4. **程序表完整性**：步骤数 ≥ xlsx 模板
5. **未分配利润勾稽**：M6-2 期末 = 期初 + 净利润 - 提取盈余 - 分配
6. **损益联动一致性**：M6-5 净利润 = Σ(D~N 损益科目 audited_amount)
7. **权益变动表平衡**：全部 M 科目期初+变动=期末

## 8. 错误处理

| 场景 | 处理 |
|------|------|
| 审定表回写失败 | WARNING 不阻断 |
| 损益合计未完成 | M6 提示"部分损益科目审定未完成" |
| M8 不适用 | 自动灰显 |
| 验资报告缺失 | M2-3 标记"未获取" |

## 9. 测试策略

- 单元测试：wp_code + componentType + schema + 程序表
- 集成测试：审定表→trial_balance 回写（10 个）+ income_statement_total 汇总
- E2E（≥3）：M2A 程序表联动 / M6-1 审定表回写 / M6-2 勾稽表 audit-sheet / M9-3 OCI 分类
