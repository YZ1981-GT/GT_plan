# 货币资金 E1 底稿优化 - 设计文档

## 变更记录

| 版本 | 日期 | 摘要 |
|------|------|------|
| v1.0 | 2026-05-17 | 初始版本 |

---

## 架构决策(ADR)

### D1 三层裁剪优先级(组件选型 > 文件级 > sheet 级)

**决策**:三层裁剪机制按效率从高到低执行:

| 层级 | 机制 | 效率 | 触发时机 | 影响范围 |
|------|------|------|---------|---------|
| **L1 组件选型驱动**(最高效) | B/C/D/E 类 21 个 sheet 改为弹窗,按 scenario+按钮显示决定加载 | 根本不进 Univer | chain_orchestrator + 前端按钮条件 | 21 个 sheet 不解析 xlsx |
| **L2 文件级裁剪**(次高效) | F4 IPO 文件按 scenario 决定是否加载 | 整文件不解析 | chain_orchestrator | 8 个 sheet(F4 整组)|
| **L3 sheet 级裁剪**(最低效) | F1-6 修订前 / 双附注 / 双 E1-3 通过 useUniverSheetNav 过滤 | 已解析但 UI 隐藏 | 前端 | 3 个 sheet |

**核心机制**:**组件选型 > 文件级裁剪 > sheet 级裁剪**
- L1 最高效:不解析 xlsx 对应区域,内存零占用
- L2 次高效:整文件不加载(F4 整组省 8 sheet 解析+合并耗时 ~30%)
- L3 最低效:仍需解析+占内存,只是 Univer 不显示

**实现**:
- L1:`chain_orchestrator._step_generate_workpapers` 不为 B/C/D/E 类 sheet 写入 Univer xlsx;前端按钮条件显示/隐藏
- L2:`chain_orchestrator._step_generate_workpapers` 按 `Project.scenario` 决定 `template_files` 列表
- L3:`useUniverSheetNav.ts` 添加 sheet 名后缀过滤规则

**组件选型分流的 5 个好处**:
1. **裁剪更自然**:弹窗类按 scenario "不显示按钮"即可,无需操作 Univer sheet 列表
2. **附件管理天然集成**:D 类盘点弹窗直接内嵌附件上传区域
3. **程序状态联动**:C 类总控台用 el-table 渲染,每行加 el-tag 完成状态 + 点击跳转
4. **截止测试自动化**:E 类从 ledger 模块自动抽样填充 el-table
5. **附注关联**:F 类直接嵌入 DisclosureEditor 的只读预览,不重复渲染

### D2 prefill 与 Univer 内部公式职责边界

**决策**:prefill 只填**空数据行 cell**,绝不覆盖已有公式 cell。

**理由**:
- E1-1 内置 193 公式(54 cross_sheet + 95 arith + 26 IF + 12 SUM + 6 ref_dir)
- E1-2!B22 = `=SUM(B15:B21)` 合计公式,被 prefill 覆盖会破坏数据链路
- prefill 真正目标是 B15-B21 数据行(各币种期初余额)

**实现**:`prefill_engine.py` 写入前检查 `cell.value and str(cell.value).startswith("=")`→跳过。

### D3 scenario 字段枚举

**决策**:6 值枚举 normal/ipo/listed/transfer/restructure/fraud_response。

**实现**:Alembic 迁移 `ALTER TABLE projects ADD COLUMN scenario VARCHAR(20) NOT NULL DEFAULT 'normal'`。

### D4 procedure_status JSONB schema

**决策**:存储在 `wp.parsed_data.procedure_status`。

**schema**:
```json
{
  "procedure_status": {
    "e1a": {
      "R17": {"status": "approved", "filled_at": "...", "reviewed_at": "...", "approved_at": "..."},
      "R22": {"status": "filled", "filled_at": "..."}
    },
    "e26a": { ... }
  }
}
```

status 枚举:`pending` / `filled` / `reviewed` / `approved` / `not_applicable`

### D5 cross_wp_ref 28 条(CW-108~135)

**决策**:顺序编号,7 种 category。

**新增 category**:
- `completion_check`:完成度汇总(各循环函证→A17-5-5)
- `overlap_reference`:内容重叠互引(E26A↔S 类)

### D6 CFS 勾稽容差

**决策**:`max(1.0, 重要性水平 × 0.001)`,三档判定。

**实现**:复用 ConsistencyGate 规则注册接口,注册 3 条规则。

### D7 conclusion_cell metadata 修正

**决策**:F3 完成状态联动用**业务核心 cell**(E1-1!R18 合计行 + R46 审计结论),不用 metadata.conclusion_cell(E1-14:A50)。

### D8 cell_ref 物理坐标 vs 语义行匹配

**决策**:prefill_engine 先尝试物理坐标(B15/E15),坐标为空时退回语义行匹配(兜底)。

### D9 审计导航图数据来源

**决策**:
- 5 项认定:从 E1A R7-R13 静态文本(模板自带)
- 风险评估:从 B23-2/B51-3/C3 的 parsed_data.conclusion 字段
- 程序进度:从 parsed_data.procedure_status 实时计算
- 关键风险:LLM 基于 E1-1 数据异常检测(变动率>30%)

### D10 LLM prompt 模板配置化

**决策**:存储在 `wp_template_metadata.llm_prompts` JSONB 字段。

**schema**:
```json
{
  "llm_prompts": {
    "audit_conclusion": "你是审计助理,基于以下{wp_name}审定表数据生成审计说明:\n数据:{data}\n要求:1.说明变动原因 2.标注异常项 3.给出结论建议",
    "variance_analysis": "分析以下科目变动率超过{threshold}%的原因:\n数据:{variance_items}",
    "check_conclusion": "基于以下检查清单结果生成检查结论:\n已验证:{verified_count}/{total_count}\n异常项:{issues}",
    "cutoff_conclusion": "基于以下截止测试结果生成结论:\n抽样笔数:{sample_count}\n跨期项:{cross_period_count}"
  }
}
```

### D11 通用总控台架构(D-N 89 个底稿可复用)

**决策**:E1A 总控台的 UI 组件(ProcedureControlPanel.vue)设计为通用组件,接受 `wp_code` + `procedure_sheet_name` 参数,可直接用于 D2A/F2A/H1A 等。

**通用接口**:
```typescript
interface ProcedureControlPanelProps {
  wpCode: string           // 'E1' / 'D2' / 'F2' / 'H1'
  procedureSheetName: string  // '货币资金实质性程序表E1A'
  projectId: string
  scenario: ProjectScenario
}
```

### D12 风险导向审计逻辑主线(最高设计原则)

**决策**:所有 UI 设计必须体现完整审计逻辑链路,贯穿 6 环节:审计目标→风险识别→程序设计→程序执行→证据获取→结论形成。

**实施约束**:
- 每个 sheet/弹窗顶部必须显示该 sheet 在审计逻辑链路中的角色(认定+风险等级+程序编号)
- 审计导航图必须按"目标→风险→程序→执行"4 步可视化(SVG 流程图)
- 组件选型分流不能丢失专业内容(模板原作者的判断不得删除)→ **锚定 F0.2 保持模板专业内容**
- D-N 通用架构(F0.3)是此原则的具体落实——保证可推广性 → **锚定 F0.3 D-N 通用架构**

**F0 设计原则映射表**(4 条原则全部映射到具体 ADR):

| F0 原则 | 对应 ADR | 落实位置 |
|---------|---------|---------|
| F0.1 风险导向审计逻辑主线 | **D12**(本 ADR)| WorkpaperAuditNav + 弹窗顶部审计上下文 |
| F0.2 保持模板专业内容 | D12 + D11 | 组件选型分流不丢内容 + 通用 ProcedureControlPanel |
| F0.3 D-N 通用架构(可推广性)| D11 | ProcedureControlPanel.vue 通用接口 |
| F0.4 预设公式实施铁律 | **D18**| Sprint 0 表样核验 → cell 映射 → JSON |

**8 个审计环节 × sheet 类型映射**(指导组件选型 + UI 上下文显示):

| 审计环节 | 对应 sheet 类型 | 逻辑角色 | UI 体现 |
|---------|---------------|---------|---------|
| 目标设定 | E1A 总控台(C 类)| "做什么"——25 项程序+5 认定映射 | ProcedureControlPanel 顶部 5 认定卡片 |
| 风险识别 | B23-2/B51-3/C3(前置)| "为什么做"——风险驱动程序范围 | 前置状态横幅 + 风险等级 badge |
| 程序执行-数据获取 | E1-1/E1-2/E1-3/E1-4(A 类 Univer)| "怎么做"——取数+计算+汇总 | Univer + prefill 公式 |
| 程序执行-检查验证 | E1-10/E1-11/E1-18/E1-19(B 类清单)| "验证什么"——逐项核对 | el-form 弹窗 + 逐项批注 |
| 程序执行-监盘确认 | E1-7/E1-8/E1-9(D 类盘点)| "看到什么"——实物验证 | 结构化表单 + 双人签字 + 附件 |
| 程序执行-截止/抽样 | E1-21/E1-22/E1-23(E1 类)| "测试什么"——截止正确性 | el-table 数据驱动 + 详情弹窗 |
| 证据获取 | E0 函证 + 附件(全类)| "证据在哪"——第三方确认 | 附件管理 + ItemAttachment |
| 结论形成 | E1-1 R40-R46 + E1A 完成标记 | "结论是什么"——审计判断 | LLM 审计说明按钮 + 完成状态联动 |

### D13 全屏弹窗交互细节

**决策**:全屏模式 4 条交互规则统一执行:

1. **不保留左侧导航**:全屏 = 聚焦单一任务,导航在退出全屏后恢复
2. **底部 sticky footer**:固定"保存"+"取消"按钮,避免长表格滚动找不到操作
3. **返回时自动刷新 Univer**:从全屏弹窗返回(保存或取消)时,自动刷新可能受影响的 Univer sheet(如 D 类盘点保存 → E1-2 现金明细自动重算)
4. **ESC 两步退出**:ESC 键先退出全屏,再次 ESC 关闭弹窗(防误操作)

**实现**:
- A 类 Univer:复用 useFullscreen composable
- B/C/D/E 类弹窗:el-dialog `fullscreen` 属性 + `:close-on-press-escape="false"`(自定义两步退出逻辑)

### D14 复核模板与 E1 双向溯源

**决策**:5 层复核体系(L1-L5 + 专委会/IT/税务)与 E1 通过 ReviewRecord 双向绑定。

**ReviewRecord 字段**:
```python
class ReviewRecord:
    source_wp: str          # 'A23-1' 等复核模板
    source_sheet: str       # '复核记录'
    target_wp: str          # 'E1'
    target_sheet: str       # '货币资金审定表E1-1'
    target_cell: str        # 'R41' 或 None(整 sheet 级)
    review_layer: str       # 'L1'/'L2'/'L3'/'L4'/'L5'/'committee'/'it'/'tax'
    status: str             # 'open'/'resolved'/'closed'
```

**双向溯源**:
- 正向:A21~A25 复核表行 → router.push 跳转 E1(target_sheet/target_cell 高亮)
- 反向:E1 编辑器 → "复核状态 badge"(L1✅/L2⏳/L3❌)→ 点击展开复核进度面板

**LLM 复核问题一键生成**:
- 合伙人打开 A23-1 时,LLM 基于 E1 当前数据自动生成"建议关注问题清单"
- 输入:E1-1 数据 + 异常项(变动率>30%) + B51-3 风险评估
- 输出:结构化问题列表(每条问题关联具体 cell)
- 用户确认后批量创建 ReviewRecord 记录

**B51-3 → E26A 自动触发链路**:
- 触发条件:B51-3 舞弊风险评估结论 = "高"
- 触发动作:LinkageBus 监听 B51-3 conclusion 变更 → 通过 CW-125(category=trigger)推 E26A
- 系统行为:自动设置 wp.parsed_data.procedure_categories 加入 "IPO 应对" → F4 文件级加载 → E26A + E1-26~E1-32 显示
- 用户提示:E1 编辑器 toast"舞弊风险评估为高,已自动启用 IPO 应对程序(E26A)"

### D15 货币资金生态圈跨循环联动

**决策**:E1 与 24 个相关底稿(B/C/D0/E0/F0/G0/H0/K0/L0/A5-1/A17-5-5/S 类)通过 cross_wp_references.json 28 条 + LinkageBus 反向索引联动。

**关键链路**:
- E0 函证 → E1-3 银行存款明细(data_flow,函证回函余额自动回填)
- E1-1!R18 合计 → A5-1 CFS 期末现金等价物(data_flow,勾稽校验)
- E0/D0/F0/G0/H0/K0/L0 → A17-5-5 函证总检(completion_check,7 个循环统一汇总)
- E26A ↔ S33-8/S34-15/S34-37(overlap_reference,内容重叠互引避免重复工作)

### D16 程序分类勾选驱动机制(F1.8 锚定)

**决策**:E1A 程序分类列改为 el-checkbox,用户勾选驱动 sheet 显隐(运行时调整,优先于 scenario 默认)。

**数据流**:
```
[scenario=normal 默认] → procedure_categories 默认 ["常规★"]
                                ↓
                     [用户勾选"IPO 应对"]
                                ↓
                     [procedure_categories 加 "IPO 应对"]
                                ↓
              [LinkageBus 触发 → 加载 F4 文件 → E26A 显示]
```

**优先级**:用户勾选 > scenario 默认(用户主动权高于项目默认设置)

**实现**:ProcedureControlPanel.vue 程序分类列用 el-checkbox-group + change 事件触发 chain_orchestrator.refresh_workpaper

### D17 E1-1 双对称区显隐机制(F1.7 锚定)

**决策**:Univer Facade API 隐藏行,不删除数据。

**实现**:
```typescript
// has_foreign_currency=false 时
workbook.getActiveSheet().setRowVisible([R7..R21], false)
// 切换 has_foreign_currency=true 时
workbook.getActiveSheet().setRowVisible([R7..R21], true)
```

**理由**:
- 隐藏行不删数据,scenario 切换可恢复
- 公式引用不破坏(R8/R9/R10 等内部公式仍然存在)
- 上下区独立结构,数据互不污染

### D18 预设公式实施铁律(F0.4 锚定)

**决策**:预设公式必须在实施阶段最后阶段基于表样格式确认后才增加,不能凭空设计。

**实施流程**(锁定 5 步):
```
Sprint 0 → 1. openpyxl 提取每个 sheet 的表头列项目 + 行结构
                          ↓
            2. 输出 cell 级映射基线(列名×行业务项→cell 坐标矩阵)
                          ↓
            3. 基于表样格式逐 cell 设计公式(锚定具体表头列名+行结构)
                          ↓
            4. 写入 prefill_formula_mapping.json 新条目
                          ↓
            5. 单测验证(覆盖每条新增公式)
```

**禁令**:
- 禁止脱离表样格式空谈公式设计
- 禁止凭印象推测 cell 坐标(必须 openpyxl 实测核验)
- 禁止覆盖已有公式 cell(D2 铁律)

**理由**:致同 E1-2 的 B22 是 SUM 合计公式,B22-1 是 cross_sheet 引用,只有 B15-B21 是数据行——表样格式核验是公式设计的前提。

### D19 数据刷新 eventBus 订阅架构(F4.3 锚定)

**决策**:6 种刷新场景通过 eventBus 事件订阅 + 工具栏手动按钮触发,不轮询。

**事件订阅清单**:

| 事件名 | 触发源 | 刷新内容 |
|--------|-------|---------|
| `trial-balance:updated` | TrialBalance 模块保存 | E1-1 prefill 13 cell 重取 |
| `adjustment:saved` | Adjustments 模块保存 | E1-1 AJE/RJE cell 重取 |
| `project:updated` | Project 设置修改 | 所有 sheet R3-R4 表头重填 |
| `confirmation:received` | E0 函证回函 | E1-3 标"已函证"+ E1-6 余额调节 |
| `prior-year:imported` | 上年数据导入 | E1-1 PREV 公式重取 |
| `manual-refresh` | 工具栏"🔄 刷新取数"按钮 | 以上全部 + 异常检测 |

**实现**:
- `useWorkpaperRefresh.ts` composable 统一订阅 6 事件
- prefill_engine 提供幂等 `refresh_cells(wp_id, cell_scope)` API
- 部分刷新优先(只重取受影响 cell),全量刷新作兜底

**理由**:eventBus 比轮询低延迟+无空查询;6 场景独立可调试,故障定位精确。

### D20 parsed_data 5 类 sheet 标准 schema(F7 锚定)

**决策**:B/C/D/E1/E2 五类 sheet 在 `wp.parsed_data` 中遵循统一 schema 骨架,见 requirements F7.1。

**5 类 schema 顶层 key 命名规则**:
- C 类总控台:`procedure_status.{e1a|e26a}.{R17~R44}` → status/timestamp
- B 类检查清单:`{sheet_key}.{check_date, items[], conclusion, attachments}`
- D 类盘点:`{sheet_key}.{count_date, items[], total, signatures}`
- E1 类截止测试(系统驱动):`{sheet_key}.{cutoff_date, auto_sampled:true, items[]}`
- E2 类人工驱动:`{sheet_key}.{items[]}` 简单结构

**全局顶层 key**(与 5 类 schema 平级):
- `procedure_categories: string[]`(F1.8 用户勾选驱动,默认 `["常规★"]`,可加 `"备选"` / `"IPO 应对"`)
- `user_formulas: dict<cell_ref, formula>`(F2.3 用户自定义公式覆盖)

**完整 parsed_data 顶层结构示例**:
```json
{
  "procedure_status": { "e1a": {...}, "e26a": {...} },
  "procedure_categories": ["常规★", "IPO 应对"],
  "user_formulas": { "B15": "=TB('1001','custom')" },
  "e1_7": { "count_date": "...", "items": [...] },
  "e1_10": { "check_date": "...", "items": [...] },
  "e1_21": { "auto_sampled": true, "items": [...] }
}
```

**统一字段**(跨类共享):
- `items[]`:明细行数组
- `conclusion`:结论文本
- `attachments[]`:附件 UUID 数组(关联 attachment_service)
- `signatures{}`:签字对象(关联 signature_service)
- `status`:pending/in_progress/completed/not_applicable
- `ai_generated/confirmed_by/confirmed_at`:LLM 生成标记

**ORM 校验**:
- TD-4 登记需为 `wp.parsed_data` 加 JSONSchema 校验(独立 spec)
- 当前阶段:服务层 Pydantic model 校验(无 DB 级强制)

---

## 数据流图(完整版,含 B/C 前置 + A5-1 勾稽 + 复核闭环)

```
┌─── 风险评估前置 ───────────────────────────────────────────┐
│ B23-2(控制了解) ──→ C3(控制测试) ──→ C3-2(控制偏差)       │
│        ↓                ↓                  ↓                │
│ B51-3(舞弊风险) ────────┴─── 影响 scenario+程序裁剪范围 ───┤
└────────────────────────────────────────────────────────────┘
                           ↓
[Project.scenario] ──→ [chain_orchestrator 文件级裁剪]
                              ↓
[4 xlsx 文件] ──→ [Univer 9 sheet(A 类)] + [弹窗 21 sheet(parsed_data)]
                              ↓
┌─── 数据填充 ──────────────────────────────────────────────┐
│ [tb_balance/tb_ledger/tb_aux_balance/tb_aux_ledger]      │
│        ↓                                                   │
│ [prefill_engine 10 种公式:TB/LEDGER/AUX/LEDGER_DETAIL/   │
│  COUNT_LEDGER/ADJ/PREV/WP/NOTE/TB_SUM]                   │
│        ↓                                                   │
│ [E1-2/E1-3 数据行] ──→ [Univer 内部 193 公式自动汇总]    │
│        ↓                                                   │
│ [E1-1 审定表]                                             │
└────────────────────────────────────────────────────────────┘
                           ↓
┌─── 跨底稿数据流 ───────────────────────────────────────────┐
│ [E0 函证] ←──→ [E1-3 银行明细] ←──→ [E1-6 余额调节]     │
│       ↓                                                    │
│ [E1-1!R18] ──→ [ConsistencyGate] ←── [CFS 现金等价物]   │
│                                          ↓                 │
│                                    [A5-1 现金流量表]      │
└────────────────────────────────────────────────────────────┘
                           ↓
┌─── 程序执行进度 ───────────────────────────────────────────┐
│ [E1A procedure_status (filled→reviewed→approved)]         │
│        ↓                                                   │
│ [WorkpaperAuditNav 进度流程图 + 5 认定卡片]               │
└────────────────────────────────────────────────────────────┘
                           ↓
┌─── 复核闭环 ──────────────────────────────────────────────┐
│ [A21-1 L1 现场复核] ──→ [ReviewRecord] ──→ [E1 sheet/cell]│
│ [A22-1 L2 经理复核] ──→ [E1 复核状态 badge L1✅/L2⏳/L3❌] │
│ [A23-1 L3 合伙人] ──→ [LLM 复核问题一键生成]              │
│ [A24-1 L4 QC]     ──→ [独立复核记录]                      │
│ [A25-1 L5 质控]   ──→ [制度合规检查]                      │
│        ↓                                                   │
│ [A17-5-5 函证完成度总检](D0/E0/F0/G0/H0/K0/L0 汇总)     │
└────────────────────────────────────────────────────────────┘
                           ↓
┌─── LLM 辅助 ──────────────────────────────────────────────┐
│ [wp_ai_service + mask_context 脱敏]                       │
│        ↓                                                   │
│ [4 种 prompt:审计说明/差异分析/检查结论/截止结论]         │
│        ↓                                                   │
│ [AiContentConfirmDialog 确认]                             │
│        ↓                                                   │
│ [E1-1 R41 审计说明 / 各 sheet conclusion 字段]           │
└────────────────────────────────────────────────────────────┘
```

---

## 新建文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `WorkpaperAuditNav.vue` | 前端组件 | 审计导航图面板(首屏) |
| `ProcedureControlPanel.vue` | 前端组件 | 通用总控台面板(E1A/E26A/D2A 等) |
| `ItemAnnotation.vue` | 前端组件 | 逐项批注组件 |
| `ItemAttachment.vue` | 前端组件 | 逐项附件组件 |
| `useProcedureStatus.ts` | 前端 composable | 程序完成状态三档计算 |
| `usePrerequisiteStatus.ts` | 前端 composable | B/C 前置条件状态查询 |
| `wp_e1_scenario_20260518.py` | Alembic 迁移 | scenario + has_foreign_currency 字段 |

---

## 修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `chain_orchestrator.py` | _step_generate_workpapers 按 scenario 裁剪 template_files + 调 fill_header_cells |
| `prefill_engine.py` | 新增 5 种公式类型 + 不覆盖公式 cell 逻辑 + fill_header_cells + user_formulas 优先级 |
| `prefill_formula_mapping.json` | 新增 E1-2/E1-3/E1-4 明细表条目 |
| `cross_wp_references.json` | 新增 CW-108~135 共 28 条 |
| `wp_template_metadata_dn_seed.json` | E1 条目新增 header_cells + llm_prompts 字段 |
| `WorkpaperEditor.vue` | 集成 WorkpaperAuditNav + 弹窗入口按钮 + 前置横幅 + 复核 badge |
| `useUniverSheetNav.ts` | scenarioFilter 参数 + A 类 9 sheet 过滤 |
| `consistency_gate.py` | 注册 3 条 E1↔CFS 规则 |
| `wp_ai_service.py` | 新增 generate_audit_conclusion / generate_variance_analysis / generate_check_conclusion / generate_cutoff_conclusion / generate_review_questions / generate_review_reply 6 个方法 |
| `ReviewRecord` 模型 | 新增 target_sheet + target_cell + review_layer 字段 |
| `FormulaManagerDialog.vue` | 新增"用户自定义公式"Tab + 蓝绿背景区分 |
| `signature_service` | D 类盘点双人签字 + B 类检查清单单人签字接入 |
| `eventBus.ts` | 新增 6 个事件类型(trial-balance:updated / adjustment:saved / project:updated / confirmation:received / prior-year:imported / manual-refresh)|
| `apiPaths.ts` | 新增 workpapers.validateFormula(F2.3 公式校验)+ workpapers.procedureCategories(F1.8 用户勾选持久化)2 个端点路径 |
| `audit_log_service.py` | 完成状态变更(filled→reviewed→approved)记录到审计日志 |
| `wp_template_metadata` ORM 模型 | 新增 header_cells JSONB 字段 + llm_prompts JSONB 字段(F4.2 + F6.3 锚定)|
