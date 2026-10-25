# M 循环双向回写管线 · 设计

## 总体策略

以 D 循环已交付的 7 条 contract（D1~D7）为参照，为 M1/M5/M8/M9 四条 entry 逐一走通 `template → instrumentation → contract → bundle → representation → evidence → bidirectional` 的完整 DAG。

**核心决策**：
- authority model = `projection_contract`（与 D 循环同型）
- 受管 sheet 优先级：审定表（`xx-1`）> 明细表（`xx-2`）> 其余
- M1 负债类（2232）与 M5/M8/M9 权益类（4101/4104/4103）在 TB 回写口径上**分两支**
- contract 从最小可行 sheet 开始（审定表 + 明细表），后续按需扩展

## 四条 entry 的受管 sheet 设计

### M1（应付股利，负债类 2232）

| sheet | 受管 | 角色 | 说明 |
|---|---|---|---|
| 底稿目录 | ❌ | 引用源 | 只被其他 sheet 引用，不含业务数据 |
| 应付股利实质性程序表M1 | ❌ | 程序表 | checklist 类，HTML 侧 host_inline 渲染 |
| **审定表M1-1** | ✅ | TB 回写 | 56r×12c / 92 公式 / 审定数回写 2232 |
| 附注披露信息（上市公司） | ❌ | 附注 | 由 formula_push 推送 |
| 附注披露信息（国有企业） | ❌ | 附注 | 由 formula_push 推送 |
| **明细表M1-2** | ✅ | 动态行 | 38r×27c / 141 公式 / 动态行数据区 |
| 调整分录汇总M1-3 | ❌ | AJE | 由 adj 模块管理 |
| 外币汇率测算表M1-4 | ❌ | 测算 | OO 兜底渲染 |
| 应付股利测算表M1-5 | ❌ | 测算 | OO 兜底渲染 |
| 应付股利检查表M1-6 | ❌ | 检查表 | checklist 类 |
| GT_Custom | ❌ | 系统 | OO 兜底 |

### M5（盈余公积，权益类 4101）

| sheet | 受管 | 角色 |
|---|---|---|
| **审定表M5-1** | ✅ | TB 回写（48r×12c / 59 公式 / 回写 4101） |
| **明细表M5-2** | ✅ | 动态行（38r×17c / 41 公式） |
| 其余 8 sheet | ❌ | 程序表/附注/AJE/检查表/GT_Custom |

### M8（一般风险准备，权益类 4104）

| sheet | 受管 | 角色 |
|---|---|---|
| **审定表M8-1** | ✅ | TB 回写（25r×12c / 84 公式 / 回写 4104） |
| **明细表M8-2** | ✅ | 动态行（24r×18c / 56 公式） |
| 其余 9 sheet | ❌ | 程序表(含 Q8A 修订前)/附注/AJE/测试表/「删除」sheet/GT_Custom |

### M9（其他综合收益，权益类 4103）

| sheet | 受管 | 角色 |
|---|---|---|
| **审定表M9-1** | ✅ | TB 回写（47r×12c / 41 公式 / 回写 4103） |
| **明细表M9-2** | ✅ | 动态行（46r×30c / 145 公式 / 宽表） |
| 其余 7 sheet | ❌ | 程序表/附注(国企 67r 最大)/AJE/核对表/GT_Custom |

## Contract JSON 结构设计（以 M5 为例）

```json
{
  "contract_id": "m5.surplus_reserve",
  "document_type": "xlsx",
  "schema_version": "contract-definition:v1",
  "semantic_version": "1.0.0",
  "review_status": "reviewed",
  "identity_carriers": ["hidden_sheet", "defined_name", "excel_table", "hidden_uuid_column"],
  "instrumentation_definition_sha256": "<现算>",
  "review": {
    "authority_root": "backend/wp_templates",
    "entry_id": "xlsx/gt-m5-surplus-reserve",
    "html_store": {
      "item_id": "M5-",
      "table": "checklist_responses",
      "row_identity_key": "rowId",
      "shape": "json_array_of_row_objects"
    },
    "reviewed_basis": "openpyxl 逐 sheet 直读权威模板 M/M5 盈余公积.xlsx"
  },
  "sheets": [
    {
      "excel_name": "审定表M5-1",
      "sheet_key": "m5-determination",
      "locator": { "anchor": "excel_table_sheet_association" },
      "tables": [{ /* 审定表结构：表头行+字段逐列声明 */ }]
    },
    {
      "excel_name": "明细表M5-2",
      "sheet_key": "m5-detail",
      "locator": { "anchor": "excel_table_sheet_association" },
      "tables": [{ /* 明细表结构：动态行+行身份 */ }]
    }
  ]
}
```

## BP 解除路径

```
BP-1: contract JSON × 4 → adapter 注册 × 4 → authority model → definition bundle × 4
  ↓
BP-2: ExcelEntryFinalizeGate.finalize_candidate() × 4 → published representation × 4
  ↓
BP-3: OO 9.4 探针 × 4 → EvidenceRecomputer.recompute() → verified × 4
  ↓
闭环: migration_state = bidirectional × 4
```

## 阶段划分

| 阶段 | 内容 | 产物 |
|---|---|---|
| Phase 1 | 逐 sheet openpyxl 精读 → 撰写 4 份 contract JSON | `backend/data/workpaper_sync_contracts/m{1,5,8,9}.*.json` |
| Phase 2 | adapter 注册 + definition DAG 发布 | adapter × 4 + bundle × 4 |
| Phase 3 | finalize_candidate × 4 | published representation × 4 |
| Phase 4 | OO 探针（需 OO 9.4 环境） | evidence verified × 4 |
| Phase 5 | 端到端闭环 + slice 更新 | `migration_state = bidirectional` × 4 |

## M1 特殊处理

🔴 M1 是 10 条里唯一的**负债类**（2232 应付股利），其余 9 条全是权益类（贷方）。影响：
- TB 回写的 `amount_kind` 可能需要区分（M1 = 负债侧 balance，M5/M8/M9 = 权益侧 balance）
- 四表取数的借贷方向与其余 9 条**相反**
- contract 的 `review.html_store.item_id` 前缀为 `M1-`，与 M10 不冲突（都以 `-` 收尾）

## M9 特殊处理

🔴 M9 是唯一 `dual_mode_carrier.kind == 'none'` 的 entry：
- 无模式切换开关（orphan 已删）
- 明细表 M9-2 是 46r×30c 的宽表（公式格 145，全域第二多）
- 附注（国企）67r 是 M 域最大 sheet

## 风险与降级

| 风险 | 影响 | 降级方案 |
|---|---|---|
| OO 9.4 环境不可用 | BP-3 无法解除 | Phase 4 标 `[ ]*`，Phase 1~3 先行 |
| 真库无业务载荷 | 闭环无法用真实数据验证 | 用合成数据做单元测试 + 集成测试 |
| M9 宽表字段过多 | contract 撰写工作量大 | M9 明细表先只覆盖核心列 |
| 模板更新 | contract sha256 漂移 | 本 spec 期间冻结模板（sha256 校验） |
