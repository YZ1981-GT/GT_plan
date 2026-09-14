# N 类底稿（税费循环）— 设计文档

## 1. 架构总览 + componentType 路由表

| wp_code 模式 | componentType | 说明 |
|-------------|--------------|------|
| N1A~N5A | `a-program-console` | 5 个程序表 |
| N{n}-1（5个审定表） | `d-form-table` | 审定表回写 |
| N{n} 附注 sheet | `c-note-table` | disclosure_notes |
| N1-3/N2-2/N2-3/N3-3/N4-3/N5-3/N5-4/N5-5/N5-7 | `audit-sheet` | 暂时性差异/税费计算/调增调减 |
| N1-2/N1-5/N2-5/N3-2/N3-5/N4-2/N5-2 | `audit-sheet` | 明细/分析 |
| N1-4/N2-4/N3-4/N5-6 | `d-form-table` | 确认条件/检查/联动 |
| N1-6/N2-6/N3-6/N4-4/N5-8 | `d-form-table` | 调整分录 |

## 2. 数据模型

### 2.1 wp_account_mapping 扩充（~32 条）

**N1 递延所得税资产：** N1/N1-1~N1-6（7 条）
**N2 应交税费：** N2/N2-1~N2-6（7 条）
**N3 递延所得税负债：** N3/N3-1~N3-6（7 条）
**N4 税金及附加：** N4/N4-1~N4-4（5 条）
**N5 所得税费用：** N5/N5-1~N5-8（9 条）

合计：~35 条

### 2.2 procedure_table_templates 扩展

N1A~N5A 共 5 个程序表。

### 2.3 auto_data_source resolvers

| source 名 | 用途 | 状态 |
|-----------|------|------|
| `risk_for_cycle` | N 程序表读取 B50 | ✅ |
| `control_test_result_for_cycle` | N 程序表读取 C12 | ✅ |
| `temporary_differences_summary` | N1/N3 暂时性差异汇总 | 🔴 需新增 |
| `income_tax_calculation` | N5 所得税计算基础数据 | 🔴 需新增 |

新增 resolvers：
```python
@auto_resolver("temporary_differences_summary")
async def _resolve_temp_diff(db, project_id, year, **kw):
    """遍历 trial_balance 全部资产负债科目，计算账面 vs 计税基础差异"""
    return {
        "deductible_differences": [...],  # 可抵扣
        "taxable_differences": [...],      # 应纳税
        "total_dta": ...,
        "total_dtl": ...,
    }

@auto_resolver("income_tax_calculation")
async def _resolve_income_tax(db, project_id, year, **kw):
    """提供所得税计算基础：利润总额 + 已知调增调减项"""
    return {
        "profit_before_tax": ...,
        "tax_rate": 0.25,
        "known_adjustments": [...],
    }
```

## 3. 审定表标准字段

复用通用结构。N2-1 特殊：按税种分行（增值税/企业所得税/个税/城建/教育附加/房产/土地等）。
N5-1 特殊：当期所得税费用+递延所得税费用=所得税费用合计。

## 4. 联动实现方案

- **审定表回写**：正则 `^N\d+-1$` 覆盖 N1-1~N5-1
- **B50→N / C12→N**：已就绪
- **N5→N1/N3**：N5-6 递延所得税联动读取 N1/N3 当期变动
- **I6-7→N5-7**：研发加计扣除通过 ref_index 关联
- **N1/N3→全科目**：暂时性差异需从各科目账面/计税基础推算

## 5. address_registry 坐标注册

| wp_code | 关键坐标 | 用途 |
|---------|---------|------|
| N1-3 | 可抵扣差异合计/DTA | 递延税资产 |
| N2-3 | 应缴增值税/差异 | 增值税核对 |
| N3-3 | 应纳税差异合计/DTL | 递延税负债 |
| N5-3 | 应纳税所得额/当期所得税 | 所得税计算核心 |
| N5-4 | 调增合计/调减合计 | 纳税调整 |
| N5-5 | 有效税率/差异解释 | 税率分析 |

坐标文件：`backend/data/n_address_registry_seed.json`

## 6. 前端路由

复用现有底稿路由。N 类无函证组。

## 7. 正确性属性

1. **wp_code 注册完整性**：N 类所有 sheet 有 wp_code
2. **_WP_CODE_OVERRIDE 覆盖率**：100%
3. **审定表回写 round-trip**：N{n}-1 保存→查询一致
4. **程序表完整性**：步骤数 ≥ xlsx 模板
5. **所得税计算公式**：N5-3 应纳税所得额 = 利润总额 + 调增 - 调减
6. **暂时性差异平衡**：N1-3 DTA 合计 = Σ(可抵扣差异 × 税率)
7. **有效税率合理性**：N5-5 有效税率在 0%~50% 范围内
8. **增值税核对**：N2-3 应缴 = 销项 - 进项 - 转出

## 8. 错误处理

| 场景 | 处理 |
|------|------|
| 审定表回写失败 | WARNING 不阻断 |
| 利润总额未审定 | N5 提示"请先完成损益类科目审定" |
| 税率未设置 | 默认 25%，可手动修改 |
| 暂时性差异科目缺失 | 仅计算已有数据科目 |

## 9. 测试策略

- 单元测试：wp_code + componentType + schema + 程序表 + 所得税计算逻辑
- 集成测试：审定表→trial_balance 回写（5 个）+ temporary_differences 计算
- E2E（≥3）：N1A 程序表联动 / N5-3 所得税计算 audit-sheet / N1-3 暂时性差异 audit-sheet
