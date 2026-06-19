# H 类底稿（固定资产循环）— 设计文档

## 1. 架构总览 + componentType 路由表

| wp_code 模式 | componentType | 说明 |
|-------------|--------------|------|
| H0A~H10A | `a-program-console` | 11 个程序表 |
| H0 | `confirmation-hub` | 函证路由 |
| H0-1~H0-5 | `d-form-table` | 函证辅助表 |
| H{n}-1（10个审定表） | `d-form-table` | 审定表回写 |
| H{n} 附注 sheet | `c-note-table` | disclosure_notes |
| H1-2/H1-3/H1-4/H1-5/H2-2/H2-3/H2-4/H3-2/H3-3/H3-4/H5-3/H7-3/H8-3/H8-4/H9-3/H9-4 | `audit-sheet` | 含公式测算 |
| H1-6/H1-7/H2-5/H3-5/H4-3/H6-3/H8-5/H9-5/H10-3 | `audit-sheet` | 分析/检查/减值 |
| H4-2/H5-2/H6-2/H7-2/H8-2/H9-2/H10-2 | `audit-sheet` | 明细（含公式） |
| H1-8/H2-6/H3-6/H4-4/H5-4/H6-4/H7-4/H8-6/H9-6/H10-4 | `d-form-table` | 调整分录 |
| H11-2/H11-3 | `d-form-table` | 简单明细/检查 |

## 2. 数据模型

### 2.1 wp_account_mapping 扩充（~65 条）

**H0 函证：** H0/H0-1~H0-5（6 条）
**H1 固定资产：** H1/H1-1~H1-8（9 条）
**H2 在建工程：** H2/H2-1~H2-6（7 条）
**H3 投资性房地产：** H3/H3-1~H3-6（7 条）
**H4 工程物资：** H4/H4-1~H4-4（5 条）
**H5 油气资产：** H5/H5-1~H5-4（5 条）
**H6 固定资产清理：** H6/H6-1~H6-4（5 条）
**H7 生产性生物资产：** H7/H7-1~H7-4（5 条）
**H8 使用权资产：** H8/H8-1~H8-6（7 条）
**H9 租赁负债：** H9/H9-1~H9-6（7 条）
**H10 资产处置损益：** H10/H10-1~H10-4（5 条）

合计：~68 条

### 2.2 procedure_table_templates 扩展

H0A~H10A 共 11 个程序表。

### 2.3 auto_data_source resolvers

| source 名 | 用途 | 状态 |
|-----------|------|------|
| `risk_for_cycle` | H 程序表读取 B50 | ✅ 已有 |
| `control_test_result_for_cycle` | H 程序表读取 C6/C7 | ✅ 已有 |
| `confirmation_summary_for_cycle` | H0 函证摘要 | ✅ 复用 cycle="H" |

## 3. 审定表标准字段

复用 D/E/F/G 通用结构。
H1-1 特殊：按资产类别（房屋/设备/运输/电子/其他）分行+累计折旧/减值准备扣减行。
H8-1/H9-1 特殊：按租赁合同分行。

## 4. 联动实现方案

- **审定表回写**：正则 `^H\d+-1$` 覆盖 H1-1~H10-1
- **B50→H / C6+C7→H**：已就绪
- **H0→ConfirmationHub**：`_WP_CODE_OVERRIDE["H0"] = "confirmation-hub"`
- **H8↔H9 CAS21 联动**：通过 ref_index chip 互相跳转（使用权资产原值=租赁负债+预付+直接费用）
- **H5/H7 适用性**：applicable_when: industry IN ['oil_gas'] / ['agriculture','forestry','livestock','fishery']

## 5. address_registry 坐标注册

| wp_code | 关键坐标 | 用途 |
|---------|---------|------|
| H1-3 | 折旧测算合计/差异 | 折旧验证 |
| H1-5 | 减值结论 | 减值测试 |
| H2-3 | 资本化利息/资本化率 | 利息资本化 |
| H3-3 | 公允价值结论 | 投资性房地产 |
| H8-4 | 使用权资产原值 | CAS21 还原 |
| H9-3/H9-4 | 现值/摊销表 | CAS21 租赁 |

坐标文件：`backend/data/h_address_registry_seed.json`

## 6. 前端路由

复用现有底稿路由，H0→ConfirmationHub（cycle=H）。

## 7. 正确性属性

1. **wp_code 注册完整性**：H 类所有 sheet 有 wp_code
2. **_WP_CODE_OVERRIDE 覆盖率**：100%
3. **审定表回写 round-trip**：H{n}-1 保存→查询一致
4. **程序表完整性**：步骤数 ≥ xlsx 模板
5. **CAS21 配对一致性**：H8 使用权资产原值 = H9 租赁负债初始 + 调整项
6. **折旧测算精度**：H1-3 计算结果误差 < 0.01 元
7. **利息资本化公式**：H2-3 资本化金额 = 累计支出 × 加权利率
8. **行业适用性**：非油气企业 H5 为不适用

## 8. 错误处理

| 场景 | 处理 |
|------|------|
| 审定表回写失败 | WARNING 不阻断 |
| 折旧参数缺失 | 提示"请先设置折旧政策" |
| CAS21 租赁合同未录入 | H8/H9 提示"请先完成租赁合同台账" |
| H5/H7 不适用 | 自动灰显 |

## 9. 测试策略

- 单元测试：wp_code + componentType + schema + 程序表
- 集成测试：审定表→trial_balance 回写（10 个）
- E2E（≥3）：H1A 程序表联动 / H1-1 审定表回写 / H9-3 租赁负债现值 audit-sheet / H0→ConfirmationHub
