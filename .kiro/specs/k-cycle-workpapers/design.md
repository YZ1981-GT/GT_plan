# K 类底稿（管理循环）— 设计文档

## 1. 架构总览 + componentType 路由表

| wp_code 模式 | componentType | 说明 |
|-------------|--------------|------|
| K0A~K13A | `a-program-console` | 14 个程序表 |
| K0 | `confirmation-hub` | 函证路由 |
| K0-1~K0-5 | `d-form-table` | 函证辅助表 |
| K{n}-1（13个审定表） | `d-form-table` | 审定表回写 |
| K{n} 附注 sheet | `c-note-table` | disclosure_notes |
| K1-2/K1-3/K3-2/K3-3/K8-2/K8-3/K9-2/K9-3/K5-4/K8-4/K8-5/K9-4/K9-5 | `audit-sheet` | 含公式/大数据明细 |
| K1-5/K2-3/K3-4/K3-5/K4-3/K5-2/K6-2/K7-2/K7-3/K10-2/K10-3/K11-2/K11-3/K12-2/K12-3/K13-2/K13-3 | `audit-sheet` | 分析/检查/明细 |
| K1-4/K5-3/K5-5/K6-3 | `d-form-table` | 坏账/或有事项/分类条件 |
| K1-6/K2-4/K3-6/K4-4/K5-6/K6-4/K7-4/K8-6/K9-6/K10-4/K11-4/K12-4/K13-4 | `d-form-table` | 调整分录 |

## 2. 数据模型

### 2.1 wp_account_mapping 扩充（~75 条）

**K0 函证：** K0/K0-1~K0-5（6 条）
**K1 其他应收款：** K1/K1-1~K1-6（7 条）
**K2 其他流动资产：** K2/K2-1~K2-4（5 条）
**K3 其他应付款：** K3/K3-1~K3-6（7 条）
**K4 其他流动负债：** K4/K4-1~K4-4（5 条）
**K5 预计负债：** K5/K5-1~K5-6（7 条）
**K6 持有待售：** K6/K6-1~K6-4（5 条）
**K7 递延收益：** K7/K7-1~K7-4（5 条）
**K8 销售费用：** K8/K8-1~K8-6（7 条）
**K9 管理费用：** K9/K9-1~K9-6（7 条）
**K10 其他收益：** K10/K10-1~K10-4（5 条）
**K11 资产减值损失：** K11/K11-1~K11-4（5 条）
**K12 营业外收入：** K12/K12-1~K12-4（5 条）
**K13 营业外支出：** K13/K13-1~K13-4（5 条）

合计：~76 条

### 2.2 procedure_table_templates 扩展

K0A~K13A 共 14 个程序表。

### 2.3 auto_data_source resolvers

| source 名 | 用途 | 状态 |
|-----------|------|------|
| `risk_for_cycle` | K 程序表读取 B50 | ✅ |
| `control_test_result_for_cycle` | K 程序表读取 C11 | ✅ |
| `confirmation_summary_for_cycle` | K0 函证摘要 | ✅ 复用 cycle="K" |
| `ledger_detail_for_account` | K8/K9 费用明细从 tb_ledger 取数 | 🔴 需新增/复用 |

新增 resolver：
```python
@auto_resolver("ledger_detail_for_account")
async def _resolve_ledger_detail(db, project_id, year, account_code, **kw):
    """从 tb_ledger 获取指定科目的明细发生额（费用类科目用）"""
    # SELECT account_code, account_name, debit_amount, credit_amount
    # FROM tb_ledger WHERE project_id=X AND year=Y AND account_code LIKE 'prefix%'
    return [...]
```

## 3. 审定表标准字段

复用通用结构。K8-1/K9-1 特殊：损益类，取发生额而非余额。

## 4. 联动实现方案

- **审定表回写**：正则 `^K\d+-1$` 覆盖 K1-1~K13-1
- **K0→ConfirmationHub**：`_WP_CODE_OVERRIDE["K0"] = "confirmation-hub"`
- **K8/K9→tb_ledger**：通过 `ledger_detail_for_account` 自动获取费用明细
- **K5→A5-3**：或有事项通过 ref_index chip 跳转
- **K7↔K10**：递延收益与其他收益互相关联

## 5. address_registry 坐标注册

| wp_code | 关键坐标 | 用途 |
|---------|---------|------|
| K1-2/K1-3 | 合计/账龄 | 其他应收款 |
| K3-2/K3-3 | 合计/账龄 | 其他应付款 |
| K5-4 | 最佳估计数 | 预计负债 |
| K8-2/K8-3 | 费用合计/趋势 | 销售费用 |
| K9-2/K9-3 | 费用合计/趋势 | 管理费用 |

坐标文件：`backend/data/k_address_registry_seed.json`

## 6. 前端路由

复用现有底稿路由，K0→ConfirmationHub（cycle=K）。

## 7. 正确性属性

1. **wp_code 注册完整性**：K 类所有 sheet 有 wp_code
2. **_WP_CODE_OVERRIDE 覆盖率**：100%
3. **审定表回写 round-trip**：K{n}-1 保存→查询一致
4. **程序表完整性**：步骤数 ≥ xlsx 模板
5. **费用取数正确性**：K8/K9 明细合计 = trial_balance 该科目发生额
6. **或有事项逻辑**：K5-3 三级可能性判断→K5-4 仅"很可能"才计提
7. **损益类方向**：K8~K13 审定表取发生额（非期末余额）

## 8. 错误处理

| 场景 | 处理 |
|------|------|
| 审定表回写失败 | WARNING 不阻断 |
| tb_ledger 无数据 | K8/K9 明细显示空+提示"请先导入序时账" |
| 或有事项法律意见缺失 | K5-5 提示"请上传律师函回函" |

## 9. 测试策略

- 单元测试：wp_code + componentType + schema + 程序表 + 费用取数逻辑
- 集成测试：审定表→trial_balance 回写（13 个）+ K8/K9 tb_ledger 取数
- E2E（≥3）：K1A 程序表联动 / K5-3 或有事项 d-form-table / K9-2 费用明细 audit-sheet / K0→ConfirmationHub
