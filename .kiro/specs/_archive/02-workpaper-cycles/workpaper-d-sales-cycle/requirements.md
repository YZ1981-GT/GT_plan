# D 销售循环底稿优化 — Requirements

> **Spec**: workpaper-d-sales-cycle
> **档级**: 档 3 完整三件套
> **版本**: v1.1（2026-05-18 重写修复，对齐 README v1.3 + design.md + tasks.md）
> **状态**: Sprint 0 现状核验已通过（D5/D6/D7 错位真存在 / scenario+has_foreign_currency 字段已就绪 / cross_wp_references 现 135 条）

## 变更记录

| 版本 | 日期 | 摘要 | 触发原因 |
|------|------|------|---------|
| v1.0 | 2026-05-18 | 三件套起草初版 | README v1.3 A++ 评级达成，启动 spec 实施 |
| v1.1 | 2026-05-18 | 内容碎片化重写修复 | 文件因增量编辑碎裂错乱，按 README v1.3 + design.md 完整重写 |

## 依赖矩阵

| 上游 spec | 状态 | 本 spec 依赖 | Fallback |
|-----------|------|------------|---------|
| `workpaper-e1-cash-optimization` | UAT 待真人验收 | E1 9 个核心组件复用（CellAnnotationPanel / WorkpaperSidePanel / WorkpaperAuditNav / ProcedureControlPanel / useEditingLock / useFullscreen / ItemAnnotation / ItemAttachment / useUniverSheetNav）+ scenario 字段 + LLM API | E1 spec 不阻塞 D 实施，组件未就绪时按 D2 ADR 迁移到本 spec |
| `enterprise-linkage` | ✅ 已完成 | useEditingLock / cross-module event bus / 右键菜单跨模块跳转 | - |
| `global-linkage-bus` | ✅ 已完成 | LinkageGraphBuilder / stale_engine / 反向索引 | - |
| `audit-chain-generation` | ✅ 已完成 | wp_template_metadata 表 / chain_orchestrator | - |
| `template-library-coordination` | 63/64 completed | seed_load_history 表 / reseed 流程 | - |

---

## 一、为什么做（业务/技术根因）

### 1.1 业务痛点（基于 README v1.3 §一 5 类核心问题）

合伙人/审计助理打开 D 销售循环底稿时遇到 5 类核心问题：

1. **155 sheet 平铺无分组**：当前 8 主底稿 17 物理文件合并后 155 sheet 全部平铺加载，审计助理打开 D2 应收账款（27 sheet）后难以定位"我现在该填哪个 sheet"
2. **数据正确性错位**：F1 P0 数据错位（D5/D6/D7 三连 wp_code 错位）让任一项目 D 循环 prefill 取数全错
3. **大量数据空白**：D 循环 70 cell prefill 仅覆盖审定表+分析程序，明细表/检查表/截止测试 9+ sheet 完全空白需手工填
4. **场景裁剪缺失**：普通项目用不到 D4-22~D4-32 IPO 应对 14 sheet 但仍全量加载（与 E1 的 F4 IPO 应对同款问题）
5. **跨底稿联动缺失**：D2↔D0 函证回填、D4↔D2/D6/D7 收入勾稽、D 循环↔附注全部独立无联动

### 1.2 技术根因

1. **prefill_formula_mapping.json 第一段 D5/D6/D7 wp_code 错位**：致同 2025 修订版编码已重排但 JSON 第一段配置未同步（详见 README v1.3 §1.2 + Sprint 0 实测核验确认）
2. **chain_orchestrator 多文件合并去重逻辑缺失**：D2（3 文件）/ D4（8 文件）合并后含 6+ 重复 sheet（底稿目录×3 / 附注披露×3 / GT_Custom×3）；实测 chain_orchestrator.py 当前无 `_normalize_sheet_name` / `_merge_sheets_dedup`
3. **scenario 字段已存在但未驱动文件级裁剪**：chain 阶段加载 D 循环全部 17 文件，缺 `SCENARIO_TO_FILE_FILTER` 过滤逻辑
4. **prefill_engine 取数粒度不足**：当前仅支持审定表级 5 cell 取数，明细表（按客户/产品/区域）/ 截止测试（=LEDGER_DETAIL 自动抽样）需扩展
5. **cross_wp_references 现 135 条但 D 相关仅 27 条**：README v1.3 §3.6 实测 66 个真实索引号目标，**Sprint 0 修正后缺 ≥ 40 条登记**（不是 README 估算 54 条）

### 1.3 本 spec 边界（参考 README v1.3 §十四）

- ✅ **本 spec 做**：D 销售循环 8 主底稿优化（F1-F10 + F12 共 11 项必做修复）
- ❌ **本 spec 不做（独立 spec）**：
  - F11 / O1: 7 循环函证统一管理中心（D0+E0+F0+G0+H0+K0+L0+A17-5-5）
  - O2: D-N 全部 14 循环推广（等 D + E1 验证后启动）
  - O3-O7: ECL 高级模型 / 语音转文字 / 外部数据导入 / 边界判定 / 市场利率
  - O8: B/C/D-N 三层联动机制（统一规划 14 循环前置依赖）

---

## 二、范围边界（做/不做明确清单）

### 2.1 必做（F1-F10 + F12 共 11 项，13 天工时）

| 编号 | 优先级 | 修复项 | 工时 | README 锚点 |
|------|-------|-------|------|------------|
| **F1** | P0 | prefill_formula_mapping.json D5/D6/D7 三连错位修正 | 0.5 天 | §6.1 / §6.4 |
| **F2** | P0 | chain_orchestrator D2 三文件合并去重 | 1 天 | §6.1 / §6.4 |
| **F3** | P0 | D4 双总控台 + 修订前 sheet 过滤 | 0.5 天 | §6.1 |
| **F4** | P1 | scenario 字段驱动 D4 IPO 应对裁剪 | 1 天 | §6.2 / §6.4 |
| **F5** | P1 | D2/D4 主底稿单一编辑器 sheet 分组 | 2 天 | §6.2 / §6.4 |
| **F6** | P1 | D2 审定表 ↔ D0 函证双向回填 | 1 天 | §6.2 / §6.4 |
| **F7** | P1 | D4 营业收入勾稽（D2/D6/D7/E1）| 1.5 天 | §6.2 / §6.4 |
| **F8** | P1 | D 循环 B/C 类前置状态 + IPO 触发器 + cross_wp_references ≥ 40 条新增 | 1 天 | §6.2 / §6.4 |
| **F9** | P1 | D4 客户访谈 D 类弹窗 | 1 天 | §6.2 / §6.4 |
| **F10** | P2 | D 循环 prefill 扩展（明细+检查表 30 cell 待补）| 2 天 | §6.3 / §6.4 |
| **F12** | P2 | D2 业务模式分析自动建议 | 1.5 天 | §6.3 |
| **小计** | | | **13 天** | |

> P0 quickfix（F1+F2+F3 共 2 天）建议**单独立项**（不进 Sprint），实施前先修复

### 2.2 排除（O1-O8 独立 spec）

| 编号 | 描述 | 工时 | 触发条件 |
|------|------|------|---------|
| O1 | 7 循环函证统一管理中心 | 3 天 | 多客户反馈"看不到全项目函证完成率" |
| O2 | D-N 14 循环推广 | 14 × 5-10 天 | D + E1 全 UAT 通过 |
| O3 | D2-9/D2-10 ECL 高级模型 | 5 天 | 上市/IPO 项目专项需求 |
| O4 | D4-30/D4-31 客户访谈语音转文字 | 3 天 | LLM 能力增强后 |
| O5 | D4-13/D4-16/D4-32 ERP/电子口岸/资金流水外部导入 | 5 天 | 真实项目触发 |
| O6 | D6/D7 边界判定建议 | 3 天 | 新收入准则项目增多 |
| O7 | D5-4 公允价值市场利率自动取数 | 2 天 | 接入外部市场数据 API |
| O8 | B/C/D-N 三层联动机制 | 5 天 | E1+D 各自实现完后统一规划 |

---

## 三、功能需求（F1-F12 详细）

### F1: prefill_formula_mapping.json D5/D6/D7 三连 wp_code 错位修正（P0）

**业务价值**：任一项目按 wp_code 索引 D5/D6/D7 底稿审定表时 prefill 取数正确（当前 entry 内容已业务对齐，但 wp_code 标签与 wp_name 错位 → 按 wp_code 索引时取错数）

**Sprint 0 实测确认**（基线，2026-05-18 跑 `_sprint0_d_baseline.py`）：
- prefill_formula_mapping 总条目：**122 条**（N_prefill_total）
- 错位 entry 数：**3 条**（N_d_audited_entries=3，每个 wp_code 各 1 条审定表 entry，非之前估算的 4 条）
- entry 的 wp_name 和 formula 已业务对齐，**错位的是 wp_code 标签**：

| 当前 wp_code | wp_name（已对）| formula 取数（已对）| 应改为 wp_code |
|--------------|-------------|------------------|-------------|
| D5 | 合同资产审定表 | `=TB('1141',...)` | **D6**（合同资产对应 D6）|
| D6 | 合同负债审定表 | `=TB('2205',...)` | **D7**（合同负债对应 D7）|
| D7 | 应收款项融资审定表 | `=TB('1124',...)` | **D5**（应收款项融资对应 D5）|

**修复方式**：交换 wp_code 标签（不动 wp_name / formula / cells），让 wp_code 与 wp_name 业务一致。修复后按 `wp_code='D5'` 查询能拿到"应收款项融资审定表"的 prefill。

**验收标准**：
1. 修复后 wp_code='D5' entry 的 wp_name='应收款项融资审定表'，formula 取数 = 1124
2. 修复后 wp_code='D6' entry 的 wp_name='合同资产审定表'，formula 取数 = 1141
3. 修复后 wp_code='D7' entry 的 wp_name='合同负债审定表'，formula 取数 = 2205
4. backup 文件存于 `backend/data/_archive/prefill_formula_mapping.<YYYYMMDD>.json`
5. reseed 后陕西华氏 D5/D6/D7 底稿按 wp_code 索引 prefill 取数正确
6. 第二段分析程序 3 条（D5/D6/D7 各 1 条 cells_count=2）**已业务对齐，不动**
7. 第三段子明细 D5-1（wp_code=D5 wp_name='应收款项融资子科目明细' cells_count=2）**已业务对齐，不动**

### F2: chain_orchestrator D2 三文件合并去重（P0）

**业务价值**：D2（3 文件 27 sheet）合并后含 6+ 重复 sheet（底稿目录×3 / 附注披露×3 / GT_Custom×3），去重后剩 21 sheet

**验收标准**：
1. `_normalize_sheet_name(name)` 函数对中英文圆括号 `(...)` vs `（...）` 归一化
2. 底稿目录 / GT_Custom / 修订前 / （原）类按归一化后保留首次出现
3. D2 27 sheet → 21 sheet（陕西华氏实测）
4. D4 48 sheet → 47 sheet（去 1 修订前）
5. 不影响其他底稿（E1/H1/F2 等）合并逻辑

### F3: D4 双总控台 + 修订前 sheet 过滤（P0）

**业务价值**：D4-审定文件 sheet 3 = "主营业务收入审计程序表 D4A（修订前）" 历史遗留，应过滤

**验收标准**：
1. chain_orchestrator 按 sheet 名包含 `修订前` / `（原）` 自动过滤
2. D6/D7 同款历史遗留 sheet（D7A 原 / D8A 原）一并过滤
3. 普通项目 D4 sheet 数从 48 → 47

### F4: scenario 字段驱动 D4 IPO 应对裁剪（P1）

**Sprint 0 实测确认**：`Project.scenario` 字段已存在（E1 spec 已落地，core.py:108）

**业务价值**：普通项目 scenario=normal 不加载 D4-22~D4-32 IPO 应对 14 sheet

**验收标准**：
1. `SCENARIO_TO_FILE_FILTER` 字典定义 normal / ipo / listed / restructure / fraud_response 5 档
2. normal 排除文件名含 IPO/上市/新三板/重组/舞弊应对 关键字的文件
3. ipo / listed / restructure / fraud_response 加载全部 17 文件
4. B51-5 评估高风险后自动触发 D4-22A IPO 应对加载（event_handlers）
5. 陕西华氏 scenario=normal → D 循环加载 13 文件（不加载 D4-22 至 D4-32）

### F5: D2/D4 主底稿单一编辑器 sheet 分组（P1）

**业务价值**：D2/D4 多文件合并到单一编辑器后 sheet 列表分组导航（参照 E1 useUniverSheetNav）

**验收标准**：
1. 新建 `useDSalesCycleSheetGroups.ts` composable，定义 13 类规则（index / control_panel / verified / detail / bad_debt / analysis / cutoff / check / related_party / monitor / interview / note / adjustment / historical）
2. 历史遗留类（修订前 / （原））hidden 默认隐藏
3. 附注披露类 readonly
4. UniverSheetNav 组件复用（不新建）
5. D2 审计助理可在 21 sheet 中按业务分组快速跳转

### F6: D2 审定表 ↔ D0 函证双向回填（P1）

**业务价值**：D0-1 函证结果汇总自动回填 D2-1 已函证金额（当前 CW-21 单向，缺反向）

**验收标准**：
1. 新增 `cross_wp_references CW-108`（source_wp=D0, target_wp=D2, category=data_flow_reverse）
2. eventBus `confirmation:received` 触发 stale 传播链路
3. D2-1 编辑器订阅 `cross-ref:updated` 事件自动刷新公式
4. 后端 confirmation_service.apply_confirmation_result 末尾追加 emit `EventType.CONFIRMATION_RECEIVED`

### F7: D4 营业收入勾稽（P1）

**业务价值**：营业收入 = 应收 + 合同资产 + 合同负债减少 + 现金（4 条 validation rule）

**验收标准**：
1. 新增 4 条 validation_rules（VR-D4-01~04）含 blocking/warning 严重程度
   - VR-D4-01：营业收入合计 = 主营业务收入 + 其他业务收入（blocking, ABS(diff) < 1.0）
   - VR-D4-02：应收账款增长率 vs 营业收入增长率合理性（warning）
   - VR-D4-03：毛利率波动 < 5%（warning）
   - VR-D4-04：合同负债期末 vs D7-1 审定数一致（blocking）
2. ConsistencyGate 集成 D4 勾稽校验
3. VR-D4-01/04 blocking 阻断签字；VR-D4-02/03 warning 显示告警

### F8: D 循环 B/C 类前置状态 + IPO 触发器 + cross_wp_references ≥ 40 条新增（P1）

**Sprint 0 实测**：当前 cross_wp_references 总 135 条，D 相关 26 条；README §3.6 实测 66 真实索引号目标 → 待补 **≥ 40 条**（不是 README v1.3 估算 54 条；Sprint 0 grep 实测修正）

**验收标准**：
1. cross_wp_references 新增 ≥ 40 条 D 循环条目（CW-108~CW-147），按 design D8 分组：
   - D0 内部联动 6 条
   - D 循环跨底稿（D2/D4 → D6/D7/G14/E1）12 条
   - D → A 跨循环（A1-1/A1-15/A1-16/A5-1）9 条
   - D → T1 IPE 模板 6 条
   - D → 附注 / 报表 6 条
2. WorkpaperEditor 顶部"前置状态横幅"显示 B23-1/C2/B51-5 完成情况
3. B51-5 高风险评估 → 自动触发 D4-22A 加载

### F9: D4 客户访谈 D 类弹窗（P1）

**业务价值**：D4-30/D4-31 客户访谈支持现场访谈 + 录音附件 + LLM 摘要

**验收标准**：
1. 新建 `CustomerInterviewDialog.vue` 组件 fullscreen 模式
2. 表单字段：客户 / 访谈方式 / 录音附件 / 访谈记录 / 发现问题 / 双人签字
3. LLM 摘要 API：`POST /api/projects/{pid}/workpapers/{wid}/ai/interview-summary`（复用 wp_ai_service.analytical_review + mask_context 脱敏）
4. 录音附件存储在 attachment_service，关联 object_type=workpaper_item

### F10: D 循环 prefill 扩展（P2）

**业务价值**：当前 70 cell → 100 cell 覆盖明细表 + 检查表 + 截止测试

**验收标准**（Sprint 0 表样核验后定义具体 cell 坐标）：
1. D2-2 明细表 +10 cell（=AUX 按客户）
2. D2-3 坏账明细 +5 cell（=LEDGER 本期计提 + =PREV）
3. D4-2 主营业务收入明细 +8 cell（=LEDGER 按月）
4. D4-13 ERP 核对 +3 cell（=LEDGER）
5. D4-17/D4-18 截止测试 +4 cell（=LEDGER_DETAIL 自动抽样）
6. **总计 30 cell**（70 现有 → 100 cell 目标）

### F12: D2 业务模式分析自动建议（P2）

**业务价值**：D2-13 业务模式分析基于序时账自动判断 + LLM 建议分类

**验收标准**：
1. 后端 API `POST /api/projects/{pid}/workpapers/D2/business-pattern-analysis` 返回客户付款周期分布 + LLM 分类建议
2. D2-13 弹窗显示分析结果 + 用户确认/修改

---

## 四、非功能需求

### 4.1 性能

| 指标 | 目标 |
|------|------|
| chain 生成 D 循环 8 主底稿（普通项目）| < 30s（当前未测）|
| D2 单底稿打开（27 sheet 合并 + prefill）| < 5s |
| D4 双总控台切换 | < 200ms |
| F8 cross_wp_ref stale 传播 | < 500ms（参照 E1 spec 基线）|

### 4.2 兼容性

- 兼容现有 chain_orchestrator 流程（不破坏 E/F/G/H/I/J/K/L/M/N 11 其他循环）
- 兼容 enterprise-linkage spec 已落地的 useEditingLock / event bus
- 不引入新前端依赖（复用 E1 spec 的 9 个组件，仅新建 1 个 CustomerInterviewDialog.vue）

### 4.3 可观测性

- F1 reseed 写入 `seed_load_history` 表（与 template-library spec 一致）
- F4 scenario 裁剪日志记录 `chain_executions.scenario_filter_summary` 字段
- F8 stale 传播写 `linkage_audit_log`（global-linkage-bus 已有）

---

## 五、测试矩阵

### 5.1 单测（pytest）

| 测试文件 | 覆盖 |
|---------|------|
| `test_d_prefill_d567_fix.py` | F1 D5/D6/D7 取数科目正确 |
| `test_d2_merge_dedup.py` | F2 三文件合并去重 |
| `test_d_scenario_filter.py` | F4 scenario 裁剪 |
| `test_d_cross_wp_refs.py` | F8 ≥ 40 条新增条目格式 + 反向回填 |
| `test_d4_validation_rules.py` | F7 VR-D4-01~04 |

### 5.2 属性测试（hypothesis）

| Property | 描述 | max_examples |
|---------|------|--------------|
| **P1** | scenario ∈ {normal,ipo,listed,restructure,fraud_response} → 对应文件加载集合幂等 | 50 |
| **P2** | sheet 名 normalize 后 GT_Custom / 底稿目录 / 修订前 三类必去重 | 50 |
| **P3** | F1 修正后 D5/D6/D7 prefill 取数科目编码集合 = {1124, 1141, 2205}（不重不漏）| 50 |
| **P4** | cross_wp_references 任两条 ref_id 不重复 | 50 |
| **P5** | D 循环 B/C 前置完成度 = 0 → D 循环 wp 不能 sign-off | 20 |

### 5.3 集成测试

| 测试文件 | 覆盖 |
|---------|------|
| `test_d_cycle_full_chain.py` | 陕西华氏 D 循环 8 主底稿 chain 生成 + scenario=normal 应有 13 文件 |
| `test_d2_d0_confirmation_callback.py` | F6 D0 函证回函 → D2 审定表 stale 传播 |
| `test_d4_ipo_trigger.py` | F4 B51-5 高风险 → 自动加载 D4-22A IPO 应对 |

### 5.4 UAT（21 项手动验收清单）

详见 tasks.md 末尾 UAT 章节（21 项，含 D14 审计导航图新增 2 项），上线门槛 ≥ 18 项 ✓ pass + 关键 P0 项（#1, #2, #3）必须 ✓ pass。

---

## 六、成功判据汇总

| 类别 | 验收项 | 量化指标 |
|------|-------|---------|
| **数据正确性（P0）**| F1 D5/D6/D7 取数 | 取数科目集合 = {1124, 1141, 2205} |
| | F2 D2 合并去重 | 27 → 21 sheet |
| | F3 修订前过滤 | D4 48 → 47 sheet |
| **场景裁剪（P1）**| F4 scenario=normal | D 循环加载 13 文件（不含 D4-22~D4-32）|
| **联动（P1）**| F6 D0 反向回填 | confirmation 事件触发 D2-1 stale |
| | F7 D4 勾稽 | 4 条 VR + 2 条 blocking 阻断签字 |
| | F8 cross_wp_ref | ≥ 40 条新增（CW-108~CW-147）— Sprint 0 修正基线 |
| **UI 体验（P1）**| F5 sheet 分组 | 13 类规则全覆盖 D 主底稿 |
| | F9 客户访谈 | D 类弹窗 + 录音附件 + LLM 摘要 |
| **prefill 扩展（P2）**| F10 prefill 数 | 70 → 100 cell |
| **业务智能（P2）**| F12 D2 业务模式 | LLM 建议 + 用户确认/修改 |

---

## 七、术语表

| 术语 | 定义 |
|------|------|
| **D 循环** | 销售循环（D0 函证 / D1 应收票据 / D2 应收账款 / D3 预收账款 / D4 营业收入 / D5 应收款项融资 / D6 合同资产 / D7 合同负债 共 8 主底稿）|
| **scenario** | 项目场景：normal / ipo / listed / restructure / fraud_response 5 档（E1 spec D1 ADR 定义）|
| **prefill_formula_mapping** | 底稿单元格预填充公式配置（backend/data/prefill_formula_mapping.json，当前 122 条）|
| **cross_wp_references** | 跨底稿引用配置（backend/data/cross_wp_references.json，当前 135 条总 / D 相关 26 条）|
| **总控台** | 致同模板 R17+ 程序行结构的 sheet（D0A / D1A / D2A / D3A / D4A / D4-22A / D5A / D6A / D7A 共 9 个）|
| **F-N 修复项** | 本 spec 编号体系（F1-F12 必做 / O1-O8 独立 spec）|

---

## 附录 A：Sprint 0 现状核验结果（2026-05-18 实测）

| 核验项 | 实测结果 | 评估 |
|-------|---------|------|
| D5/D6/D7 错位 | 真存在（wp_code 标签与 wp_name 业务错位）| ✅ F1 修复方向修正：改 wp_code 不改 formula |
| Project.scenario 字段 | 存在（E1 spec 已建，core.py:108）| ✅ F4 可直接复用 |
| Project.has_foreign_currency 字段 | 存在 | ✅ |
| **prefill_formula_mapping 总条目** | **122 条**（N_prefill_total）| ✅ |
| **D5/D6/D7 审定表错位 entry** | **3 条**（N_d_audited_entries，非早期估算 4 条）| ✅ F1 修复目标修正：3 个 wp_code 交换 |
| **cross_wp_references 总条目** | **135 条**（N_cwr_total）| ✅ |
| **cross_wp_references D 相关** | **26 条**（N_cwr_d_count，非早期估算 27 条）| ✅ F8 基线修正 |
| **F8 待补条数** | **≥ 40 条**（66 真实目标 - 26 已有 = 40，非早期估算 39 / 54）| ✅ F8 工作量+1 |
| chain_orchestrator 现状 | 已支持多文件合并但无 `_normalize_sheet_name` / `_merge_sheets_dedup` | ✅ F2 需新增两个函数 |

**核验脚本**：`backend/scripts/_sprint0_d_baseline.py`（用完即删）；如需重跑确认基线，执行 `python backend/scripts/_sprint0_d_baseline.py`

---

> **本 requirements.md 配套文档**：design.md（架构决策）+ tasks.md（实施计划）
> **README v1.3 锚点**：§一 痛点 / §二 真实结构 / §三 总控台拆解 / §四 公式拓扑 / §六 修复建议 / §6.4 schema/API/code 骨架
> **下一步**：Sprint 0 ✅ → 等启动条件全部就绪后启动 Sprint 1 编码任务
