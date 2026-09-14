# H0 冲突决议文档

> Task 0.2 产物 — 对照 `h0_d0_alignment.md` 与实际代码/xlsx 结构进行交叉验证。

## 1. overrides 映射验证（9 条）

| wp_code | 期望 componentType | `wp_code_overrides.json` 实际 | 状态 |
|---------|--------------------|-----------------------------|------|
| H0 | confirmation-hub | `confirmation-hub` | ✅ 一致 |
| H0A | a-program-console | `a-program-console` | ✅ 一致 |
| H0-1 | confirmation-summary | `confirmation-summary` | ✅ 一致 |
| H0-2 | confirmation-entity-verify | `confirmation-entity-verify` | ✅ 一致 |
| H0-3 | confirmation-followup | `confirmation-followup` | ✅ 一致 |
| H0-4 | confirmation-diff-reconcile | `confirmation-diff-reconcile` | ✅ 一致 |
| H0-5 | confirmation-alternative-h05 | `confirmation-alternative-h05` | ✅ 一致 |
| H0-6 | confirmation-reliability | `confirmation-reliability` | ✅ 一致 |
| H0-7 | confirmation-fraud-risk | `confirmation-fraud-risk` | ✅ 一致 |

**结论**：9 条 overrides 完整对齐设计文档，无冲突。

### 1.1 与 D0 对比差异（设计正确性确认）

| 对比项 | D0 | H0 | 差异原因 |
|--------|----|----|----------|
| hub 入口 | D0 无 hub override（走 account_package 自路由） | `"H0": "confirmation-hub"` 显式声明 | 后期模式改进，H0/E0/F0/G0 统一显式 |
| D0-4b diff-checklist | 有 | 无 | H0 xlsx 无此 sheet（确认设计正确） |
| D0-6 第二替代程序 | `confirmation-alternative-d06` | 无 | H0 仅 1 个替代程序（确认设计正确） |
| 编号映射 | D0-7→reliability, D0-8→fraud-risk | H0-6→reliability, H0-7→fraud-risk | 编号差异因 H0 少 D0-4b/D0-6 两 sheet |

## 2. account_package 验证

`H0_fixed_asset_confirmation` 包含 8 条 sheet 配置：

| sheet_name | sheet_type | 验证 |
|------------|-----------|------|
| 函证程序表H0A | control_panel | ✅ |
| 函证结果汇总表H0-1 | procedure | ✅ |
| 核实被函证单位信息H0-2 | grid_table | ✅ |
| 跟函函证过程控制H0-3 | grid_table | ✅ |
| 差异核对表H0-4 | grid_table | ✅ |
| 替代程序H0-5 | grid_table | ✅ |
| 邮件传真回函可靠性验证H0-6 | procedure | ✅ |
| 函证程序舞弊风险评价表H0-7 | grid_table | ✅ |

**注意**：底稿目录不在 account_package 的 sheets 中（由系统合成），总计 8 业务 sheet + 1 合成目录 = 9 sheet 与 xlsx 一致。

## 3. H0-5 列配置 vs xlsx 结构冲突分析

### 3.1 核心发现：xlsx 模板 H0-5 检查区域为空白

| 维度 | xlsx 实际 | 设计/代码 | 决议 |
|------|----------|----------|------|
| 检查过程区 rows 11-19 | **完全空白**（无列头/无数据行） | 4 区块动态定义（blockColumnConfigsH05.ts） | ✅ **设计正确** — 遵循 D0-5 模式由前端动态渲染 |
| 整体尺寸 | 35×29 | 4 区块各 ~15 列，动态行 | ✅ 动态渲染不受模板尺寸限制 |
| 公式 | 仅 6 个（底稿目录引用） | useH0FormulaEngine 提供 calcBlockTotal | ✅ D0-5 同模式（模板→前端公式引擎） |

### 3.2 与 D0-5 模板对比

| 对比项 | D0-5 模板（62×40） | H0-5 模板（35×29） |
|--------|-------------------|-------------------|
| 区块列头 | 模板预置完整列头+4行占位+合计行 | 模板为空白框架（rows 11-19） |
| 汇总区 | Row 11 有字段名（函证项目/年初余额/...） | 抽样参数区 rows 6-9（6 字段） |
| 区块数量 | 4 区块（合同负债/余额/收款/出库） | 4 区块（验收权属/余额证据/新增/抵押） |

**决议**：H0-5 模板更紧凑（致同模板仅给框架，具体列头由审计助理按需展开）。代码中 `blockColumnConfigsH05.ts` 已定义 4 区块完整列头，**与 D0-5 实现模式一致**（前端渲染动态区块，不依赖模板预置列头）。

### 3.3 blockColumnConfigsH05.ts 列定义决议

| 区块 | key | 凭证列 | 证据列 | 冲突? |
|------|-----|--------|--------|-------|
| ① | acceptance_ownership | 5 列（日期/编号/内容/科目/金额） | 验收单 4 列 + 权属 3 列 + 索引+异常 | ❌ 无冲突 |
| ② | balance_evidence | 同上 | 采购合同 3 列 + 发票 2 列 + 付款 2 列 + 索引+异常 | ❌ 无冲突 |
| ③ | new_asset_check | 同上 | 请购 2 列 + 验收 3 列 + 转固 2 列 + 索引+异常 | ❌ 无冲突 |
| ④ | mortgage_lease | 同上 | 抵押 3 列 + 融资租赁 3 列 + 权证 1 列 + 索引+异常 | ❌ 无冲突 |

**与 `h0_d0_alignment.md` Section 4 对照**：

- `h0_d0_alignment.md` 中 ① 检查证据列列出 "验收单日期编号/资产名称/规格型号/数量 | 权属证书编号/权属人/取得日期"
- `blockColumnConfigsH05.ts` 实现：`accept_date_no / asset_name / asset_spec / asset_qty | title_cert_no / title_owner / title_date`
- **完全一致**，无冲突

其余三区块同样对齐。

### 3.4 H0-5 编制说明内嵌内容对照

xlsx rows 28-35 "编制说明"提到的替代程序：
1. ① 检查本期付款、期后收货或回收
2. ② 检查原始凭证：合同、订货单、发票或收据、银行回单、支票存根等
3. ③ 对回函可能性不高的、余额重大的，发函同时执行替代程序

这与设计文档的四区块主题（权属验收/余额证据/新增资产/抵押担保）完全一致 — ①②③ 对应 block1~block3 的审计逻辑，block4（抵押担保）为 H 循环特有的额外程序。

## 4. F0-5 模式适用性确认

### 4.1 F0-5 薄壳模式

```
alternativeF05/
  GtConfirmationAlternativeF05.vue   # 薄壳（~300 行）
  blockColumnConfigsF05.ts           # 4 区块列配置
  alternativeF05Types.ts             # _format: alternative-f05-v1
  composables/useAlternativeF05Data.ts
```

### 4.2 H0-5 实现对照

```
alternativeH05/
  GtConfirmationAlternativeH05.vue   # ✅ 已创建
  blockColumnConfigsH05.ts           # ✅ 已创建（4 区块完整列定义）
  alternativeH05Types.ts             # ✅ 已创建
  composables/
    useAlternativeH05Data.ts         # 待实现（Phase 3）
    useH0FormulaEngine.ts            # 待实现（Phase 2）
    useH0ImportExport.ts             # 待实现（Phase 5）
```

**结论**：H0-5 完全遵循 F0-5 已验证的薄壳模式。复用 D0-5 的 Dashboard/Master/CheckBlock 壳组件，仅替换列配置。

## 5. D0-4b 等效确认（无需）

| 检查项 | 结论 |
|--------|------|
| H0 xlsx 是否有差异检查表示例 sheet | ❌ 无（确认 xlsx 仅 9 sheet） |
| 是否需要 `confirmation-diff-checklist` | ❌ 不需要 |
| G0 是否有同样情况 | ✅ G0 也无 D0-4b（模式一致） |

## 6. 遗留事项与风险

| # | 事项 | 严重程度 | 处理计划 |
|---|------|---------|----------|
| 1 | `H0.yaml` render schema 仍为草稿（d-form-* 而非 confirmation-*） | P1 | Phase 1 task 1.1 人工审核修正 |
| 2 | VALID_COMPONENT_TYPES 尚未包含 `confirmation-alternative-h05` | P1 | Phase 1 task 1.1 注册 |
| 3 | htmlRendererRegistry 尚未包含 h05 → GtConfirmationAlternativeH05 | P1 | Phase 1 task 1.1 注册 |
| 4 | RENDERER_DISPATCH 尚未包含 h05 render 策略 | P1 | Phase 5 task 5.1 |
| 5 | H0-5 模板空白区域列头由前端完全定义 — 导入导出模板需匹配前端列头 | 低 | Phase 5 import/export 对齐 blockColumnConfigsH05 |

## 7. 总结

| 检查维度 | 结果 |
|----------|------|
| 9 条 overrides 映射 | ✅ 完全一致 |
| account_package 注册 | ✅ 8 sheet + 合成目录 |
| H0-5 四区块列定义 vs xlsx | ✅ 无冲突（xlsx 为空白框架，前端动态渲染） |
| H0-5 四区块列定义 vs alignment 文档 | ✅ 完全一致 |
| F0-5 薄壳模式适用性 | ✅ 完全适用 |
| D0-4b 等效需求 | ✅ 确认不需要（H0 无此 sheet） |
| 跨循环共享组件零修改原则 | ✅ 不需要修改 alternativeD05/ 源码 |

**整体结论**：H0 配置层与 D0 架构完全对齐，无冲突。`blockColumnConfigsH05.ts` 四区块列定义与 xlsx 模板结构/alignment 文档一致。可安全进入 Phase 1+ 开发。
