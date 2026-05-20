# D 销售循环底稿优化 — Design

> **Spec**: workpaper-d-sales-cycle  
> **版本**: v1.0（基于 requirements.md v1.0 起草）  
> **状态**: ADR 待 Sprint 1 实施前 review

## 变更记录

| 版本 | 日期 | 摘要 | 触发原因 |
|------|------|------|---------|
| v1.0 | 2026-05-18 | 三件套设计初版 | requirements.md v1.0 完成 |

## 一、架构总览

### 1.1 D 循环数据流（基于 README v1.3）

```
[chain_orchestrator]
   ├─ scenario=normal → 加载 13 文件（排除 D4-22~D4-32 IPO 应对）
   ├─ scenario=ipo    → 加载 17 文件（含 D4-22~D4-32）
   └─ B51-5 高风险   → 自动追加加载 D4-22A
        │
        ▼
[多文件合并去重 _merge_sheets_dedup]
   ├─ 归一化 sheet 名（中英文圆括号）
   └─ 保留首次出现（GT_Custom/底稿目录/修订前 类视为同名）
        │
        ▼
[prefill_engine F1 修正]
   ├─ D5 审定表 → =TB('1124', ...)（应收款项融资）
   ├─ D6 审定表 → =TB('1141', ...)（合同资产）
   └─ D7 审定表 → =TB('2205', ...)（合同负债）
        │
        ▼
[WorkpaperEditor F5 sheet 分组]
   ├─ useDSalesCycleSheetGroups 13 类规则
   └─ 历史遗留隐藏 / 附注披露只读
        │
        ▼
[联动层]
   ├─ F6 D0→D2 反向回填（CW-108）
   ├─ F7 D4 勾稽 4 条 VR
   ├─ F8 B/C 前置状态横幅
   └─ F9 D4-30/31 客户访谈 + LLM 摘要
```

### 1.2 复用 E1 spec 已建组件清单（不重复造轮子）

| 组件 | E1 spec 路径 | D 循环复用方式 |
|------|------------|--------------|
| `useUniverSheetNav.ts` | composables/ | 不改动，仅扩展 D 类规则 |
| `WorkpaperAuditNav.vue` | components/workpaper/ | 不改动，数据源切换为 D 总控台 |
| `WorkpaperSidePanel.vue` | components/workpaper/ | 不改动，9 Tab 直接复用 |
| `CellAnnotationPanel.vue` | components/workpaper/ | 不改动，A 类 sheet 共用 |
| `ItemAnnotation.vue` | components/workpaper/ | 不改动，B/C/D/E 类弹窗共用 |
| `ItemAttachment.vue` | components/workpaper/ | 不改动 |
| `ProcedureControlPanel.vue` | components/workpaper/ | 不改动，9 总控台共用 |
| `useEditingLock.ts` | composables/ | 不改动 |
| `useFullscreen.ts` | composables/ | 不改动 |

**新建组件仅 1 个**: `CustomerInterviewDialog.vue`（D4-30/31 客户访谈，D 循环专属）

---

## 二、架构决策记录（ADR）

### D1: F1 修复方式 — 一次性脚本 + git 备份

**决策**: 使用一次性 Python 脚本修复 prefill_formula_mapping.json 而非手工编辑 JSON

**理由**:
- 4 条 entry 同时修正避免 strReplace 误改
- 备份到 `_archive/` 提供 rollback 路径
- E2E SQL 验证可重复跑

**代码骨架**: 见 README v1.3 §6.4 F1 详细

**风险**: 第三段子明细（cells_count=2 那条 D5 审定表 D5-1）可能也错位，Sprint 0 实测显示该条只有"票据类_期末余额"和"应收账款类_期末余额"两个子科目（=TB('112401',...) 和 =TB('112402',...)），属于 D5 应收款项融资合理子科目，**不动**

### D2: F2 sheet 名归一化算法 — 三档判定

**决策**:
1. **GT_Custom 类** → 归一化为 `"GT_Custom"`（多文件版本以第一个为准）
2. **底稿目录类** → 归一化为 `"底稿目录"`
3. **其他 sheet** → 中英文圆括号统一 + 去空白

**伪代码**:
```python
def _normalize_sheet_name(name: str) -> str:
    n = name.replace("（", "(").replace("）", ")")
    if "GT_Custom" in n:
        return "GT_Custom"
    if "底稿目录" in n:
        return "底稿目录"
    return re.sub(r"\s+", "", n.strip())
```

**理由**: 致同模板真实 sheet 名差异主要 3 类，简单 if 链优于复杂正则

### D3: F3 历史遗留 sheet 过滤 — sheet 名后缀匹配

**决策**: chain_orchestrator 加载 sheet 时按 sheet 名包含 `修订前` / `（原）` 自动过滤

**实现位置**: `chain_orchestrator._step_generate_workpapers` → 合并前过滤

**与 D2 关系**: D3 在归一化前过滤（先过滤"修订前"，再归一化去重）

### D4: F4 scenario 文件级裁剪 — SCENARIO_TO_FILE_FILTER 字典

**决策**: 用文件名关键字过滤而非 sheet 级过滤（与 E1 spec 一致）

**字典定义**:
```python
SCENARIO_TO_FILE_FILTER = {
    "normal": {
        "exclude_patterns": ["IPO", "上市", "新三板", "重组", "舞弊应对"]
    },
    "ipo": {},  # 加载全部
    "listed": {},
    "restructure": {},
    "fraud_response": {},
}
```

**理由**: 文件级裁剪比 sheet 级高效，文件命名已含场景标识

**B51-5 触发器**:
- 监听 `EventType.WORKPAPER_SAVED`
- 当 `wp_code='B51-5'` 且 `parsed_data.conclusion.fraud_risk_level=='high'`
- 自动追加加载 D4-22 至 D4-32 文件（即使 scenario=normal）

### D5: F5 sheet 分组规则 — useDSalesCycleSheetGroups composable

**决策**: 复用 E1 的 `useUniverSheetNav` 接口，新建 D 专属规则文件

**13 类规则**（按优先级排序，详见 README v1.3 §6.4 F5 详细）:
1. index（底稿目录/GT_Custom，hidden）
2. control_panel（D[0-7]A | D4-22A，priority 1）
3. verified（审定表）
4. detail（明细表非坏账）
5. bad_debt（坏账/减值/ECL）
6. analysis（分析/毛利/增长率/集中度）
7. cutoff（截止）
8. check（检查表）
9. related_party（关联方）
10. monitor（监盘）
11. interview（访谈）
12. note（附注披露，readonly）
13. adjustment（调整分录）
14. historical（修订前/（原），hidden）

### D6: F6 反向回填机制 — cross_wp_references CW-108

**决策**: 用 `category=data_flow_reverse` 标识反向数据流（区别于现有 `data_flow` 单向）

**完整 JSON 条目**:
```json
{
  "ref_id": "CW-108",
  "description": "D0-1 函证结果汇总 → 回填 D2-1 已函证金额（支持函证回函后实时更新）",
  "source_wp": "D0",
  "source_sheet": "函证结果汇总表D0-1",
  "source_cell": "已回函金额合计",
  "targets": [
    {
      "wp_code": "D2",
      "sheet": "应收账款审定表D2-1",
      "cell": "已函证金额",
      "formula": "=WP('D0','函证结果汇总表D0-1','已回函金额合计')"
    }
  ],
  "category": "data_flow_reverse",
  "severity": "warning",
  "trigger": "eventBus confirmation:received"
}
```

**前端响应**: `WorkpaperEditor` 订阅 `cross-ref:updated` 事件 + Univer Facade API 自动重算 D2-1 公式

### D7: F7 D4 勾稽 4 条 validation rules

**决策**: 复用 E1 spec ConsistencyGate 已有的 validation_rules.json 配置体系

**4 条 VR**:
| ID | 规则 | severity |
|----|------|----------|
| VR-D4-01 | 营业收入合计 = 主营业务收入 + 其他业务收入 | blocking |
| VR-D4-02 | 应收账款增长率 vs 营业收入增长率合理性 | warning |
| VR-D4-03 | 毛利率波动 < 5% | warning |
| VR-D4-04 | 合同负债期末 vs D7-1 审定数一致 | blocking |

**容差**: blocking 类 ABS(diff) < 1.0（小金额视为相等）；warning 类按业务规则定义

### D8: F8 cross_wp_references ≥ 40 条新增 — 按 README §3.6 实测清单分组

**决策**: 不凭空设计，按 README v1.3 §3.6 实测的 66 真实索引号目标清单（已有 26 条 + 待补 ≥ 40 条）逐条登记

**编号区间**: CW-108 ~ CW-147（39 条，避开现有 CW-001~CW-107 + CW-133）

**README §3.6 真实分组（参照实施）**:
| 分组 | 来源 | 目标 | 待补条数 |
|------|------|------|---------|
| **D0 内部联动** | D0-1 函证结果汇总 | D0-3 跟函过程 / D0-4 差异调节 / D2-1 已函证金额（CW-108 反向）| 6 条 |
| **D 循环跨底稿** | D2/D4 主底稿 | D6 合同资产 / D7 合同负债 / G14 信用减值 / E1 销售现金 | 12 条 |
| **D → A 跨循环** | D2/D4 数据 | A1-1 财报支持 / A1-15 KAM / A1-16 重大错报 / A5-1 CFS | 9 条 |
| **D → T1 IPE 模板** | D4-13 ERP 核对 / D4-16 电子口岸 | T1 IPE 完整性 | 6 条 |
| **D → 附注 / 报表** | D2-1/D4-1/D6-1/D7-1 | disclosure_notes 五、3 应收 / 八、5 等 | 6 条 |
| **总计** | | | **39 条** |

**记录字段示例**:
```json
{
  "ref_id": "CW-115",
  "description": "D2A 程序 R28 → A23-1 合伙人复核（财报）应收账款行",
  "source_wp": "D2",
  "source_sheet": "应收账款实质性程序表D2A",
  "source_cell": "R28 索引号列",
  "targets": [
    {
      "wp_code": "A23-1",
      "sheet": "项目合伙人复核（财报）A23-1",
      "cell": "应收账款复核行",
      "formula": "=WP('D2','应收账款实质性程序表D2A','R28')"
    }
  ],
  "category": "review_traceback",
  "severity": "info"
}
```

**Sprint 0 偏差修正**: README v1.3 §3.6 估算"待补 54 条"是基于"已有 12 条"假设，Sprint 0 grep 实测已有 26 条（CW-07/CW-21~38/CW-89~91/CW-100/CW-105~107/CW-133），实际待补 40 条

### D9: F9 CustomerInterviewDialog.vue — 唯一新建组件

**决策**: 新建 D 循环专属组件（其他 8 组件全部复用 E1 spec）

**组件设计**:
- `<el-dialog fullscreen>` 顶部审计上下文（认定/风险/程序编号）
- `<el-form>` 主体（客户/访谈方式/录音附件/访谈记录/发现问题）
- 底部 sticky footer（LLM 摘要 / 保存 / 取消）

**LLM API**:
```
POST /api/projects/{pid}/workpapers/{wid}/ai/interview-summary
Body: { transcript: string, audio_recording_uuid?: string }
Response: { summary: string, issues_found: string[], risk_alerts: string[] }
```

**复用 wp_ai_service**: `analytical_review` + `mask_context` 脱敏

### D10: F10 prefill 扩展 30 cell — 实施前 Sprint 0 表样核验

**决策**: 不在 design.md 写死具体 cell 坐标，Sprint 0 现状核验阶段用 openpyxl 提取真实表样 + 行结构后定义 cell 级映射

**铁律**: "不能脱离表样格式空谈公式设计"（用户偏好硬约束）

**待补分布**（按 README v1.3 §4.2 D2-1 28 行三类标注 + §6.4 F10 待补分布表）:
- D2-2 明细表: 10 cell（=AUX 按客户）
- D2-3 坏账明细: 5 cell（=LEDGER 本期计提 + =PREV）
- D4-2 主营业务收入明细: 8 cell（=LEDGER 按月）
- D4-13 ERP 核对: 3 cell（=LEDGER）
- D4-17/18 截止测试: 4 cell（=LEDGER_DETAIL 自动抽样）
- **总计**: 30 cell（70 现有 → 100 cell 目标）

**D2-1 审定表 prefill ~30 cell 缺口**（README §4.2 实测）:
| 段位 | 行数 | 当前 prefill | 缺口 | 公式类型 |
|------|------|-----------|------|---------|
| 段 1 应收原值（R7-R10）| 4 | 0 | 4 | =TB('1122','期初/期末/未审')+=ADJ |
| 段 2 单项坏账（R11-R13）| 3 | 0 | 3 | =SUMIF('明细表D2-3'!...) |
| 段 3 组合坏账（R14-R23）| 10 | 0 | 10 | =SUMIF 5 子组合 × 期初+期末 |
| 段 4 合计（R24-R26）| 3 | 0 | 3 | =SUM 段 1-3 |
| 段 5 坏账明细（R27-R36）| 10 | 5 | 5 | =LEDGER 本期 + =PREV |
| 段 6 净额（R37-R47）| 11 | 0 | 11 | =段 4 - 段 5 |
| **D2-1 缺口** | | | **~30 cell** | |

**Sprint 0 必做**: 跑 openpyxl 脚本提取 D2-2/D2-3/D4-2/D4-13/D4-17 真实表样后才能定义具体 cell 坐标

### D11: 测试 fixture 模板复用

**决策**: 5 个新单测文件全部复用 `test_eqcr_gate_approve.py` 同款 fixture（参照 R5 复盘规约）

**模板**:
```python
@pytest_asyncio.fixture
async def db_session():
    _engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(_engine, class_=AsyncSession)
    async with async_session() as session:
        yield session
    await _engine.dispose()
```

### D12: F8 cross_wp_ref reload 机制

**决策**: cross_wp_references.json 修改后调 `LinkageGraphBuilder.build()` 触发 stale_engine.reload_graph + invalidate_reverse_index（global-linkage-bus spec 已有）

**触发方式**: 实施过程中通过 `GET /api/linkage-bus/graph?rebuild=true` 手动触发；生产部署后 Alembic 迁移末尾自动调

### D13: 公式取数粒度规约（D 循环特殊用法）

**决策**: D 循环复用 E1 spec 的 10 种公式语法（不新增），按"业务取数粒度"差异化使用

**D 循环典型用法**（详见 README v1.3 §2.0.0b）:
- =AUX('1122','客户','C001','期末余额') → 按客户取数
- =LEDGER('5001','credit','2026-01~2026-12') → 按月汇总
- =LEDGER_DETAIL('5001','2026-12-26~2027-01-05','>100000') → 截止测试自动抽样

### D14: D 循环每主底稿"审计导航图"首屏（README §2.0.0d）

**决策**: 复用 E1 spec 已建 `WorkpaperAuditNav.vue` 组件，D 循环 8 主底稿打开时**第一个看到的不是 Univer 表格而是导航图面板**

**5 区块内容**（按 README §2.0.0d 同款）:
1. **审计目标卡片**（来自 XxA R7-R13 的 5/6 项认定，D4 多 OE 发生）
2. **风险评估摘要**（来自 B23-1/B51-5/C2/C2-2 前置底稿）
3. **程序执行进度流程图**（XxA 程序状态可视化，D 循环 9 总控台共用）
4. **关键风险提示**（LLM 辅助识别）：
   - 收入增长率 > 应收增长率 2 倍 → 收入虚增风险
   - 毛利率突变 > 5% → 成本配比异常
   - 单一客户占比 > 30% → 客户集中度风险
   - D2-9 ECL 计提率与上年差异 > 50% → 会计估计变更
   - D4 截止测试发现跨期 → 收入确认期间错误
5. **底稿间关系图**（D 循环 8 主底稿 + B/C 前置 + A21~A28 复核全景）

**实施要点**: D 循环不新建组件，仅扩展 `WorkpaperAuditNav.vue` 的数据源 prop，按 wp_code 路由到 D 循环数据加载逻辑

### D15: design.md ADR D1-D14 与 README §十二 ADR-1~5 双向映射

**决策**: design.md ADR 编号体系（D1-D14，按 F-N 修复项一对一展开）与 README §十二 ADR 编号体系（ADR-1~5，按架构决策抽象层归类）**并存**，双向映射如下：

| design.md ADR | 对应需求 | README §十二 ADR | 映射关系 |
|---------------|---------|-----------------|---------|
| D1 | F1 修复方式 | - | 实施细节级 |
| D2 | F2 归一化算法 | ADR-2 chain_orchestrator 多文件合并 | D2 是 ADR-2 的具体实现 |
| D3 | F3 历史遗留过滤 | ADR-2 同款 | D3 是 ADR-2 的扩展规则 |
| D4 | F4 SCENARIO_TO_FILE_FILTER | ADR-3 双总控台切换机制 | D4 是 ADR-3 的具体配置 |
| D5 | F5 13 类规则 | ADR-4 5 类组件分流 | D5 是 ADR-4 的 D 循环实例化 |
| D6 | F6 反向回填 | - | 实施细节级 |
| D7 | F7 4 条 VR | - | 实施细节级 |
| D8 | F8 ≥ 40 条新增 | - | 实施细节级 |
| D9 | F9 唯一新建组件 | ADR-1 复用 E1 9 组件 | D9 与 ADR-1 互补（D9 = "唯一新建" / ADR-1 = "9 复用"）|
| D10 | F10 prefill 表样核验 | ADR-5 prefill 不覆盖检查表 | D10 是 ADR-5 的实施铁律细化 |
| D11 | 测试 fixture 模板 | - | 测试基础设施级 |
| D12 | F8 reload 机制 | - | 实施细节级 |
| D13 | 公式取数粒度 | - | 实施规约级 |
| D14 | 审计导航图首屏 | - | UAT #20-21 验收，复用 E1 WorkpaperAuditNav |

**理由**: 两套体系各有职责——README ADR 是"架构层为什么这么决策"（5 个抽象决策），design.md ADR 是"实施层每个修复点怎么决策"（14 个具体修复）；保留双编号避免任一方信息丢失。

**铁律**: 实施时如发现 design D-N 与 README ADR-N 冲突，**以 README §十二 为准**（架构层优先），design.md 只能在 README ADR 范围内细化不能违反

---

## 三、数据结构定义

### 3.1 数据库 schema（不改 ORM）

本 spec 不新增 ORM 字段，全部改动在 JSON 配置层：
- `prefill_formula_mapping.json`（4 条修正 + 30 条新增 = +30 cell 净增）
- `cross_wp_references.json`（+≥ 40 条 / CW-108~CW-147）
- `validation_rules.json`（+4 条 VR-D4-01~04）

### 3.2 wp.parsed_data JSONB schema 扩展（D 循环）

**5 类弹窗 schema** 见 README v1.3 §2.0.1a，本 spec 实施时按此模板写入：
- C 类（D2A/D4A/D4-22A 程序状态）：`procedure_status[wp_code][R_NN] = {status, completed_at, ...}`
- B 类（检查表 D2-7/D4-14 等）：`{check_date, items[], conclusion, attachments}`
- D 类（D1-10 监盘 / D4-30 访谈）：`{count_date, items[], signatures, attachments}`
- E 类（D4-17/18 截止测试）：`{cutoff_date, days_before, items[], total_sampled, conclusion}`

### 3.3 SCENARIO_TO_FILE_FILTER 字典定义位置

**位置**: `backend/app/services/chain_orchestrator.py` 模块级常量

**类型**: `dict[str, dict[str, list[str]]]`

---

## 四、Property 测试设计

| Property | 描述 | Coverage 目标 |
|---------|------|--------------|
| **P1** | scenario 文件加载幂等 | scenario ∈ {normal,ipo,listed,restructure,fraud_response}，加载文件集合稳定 |
| **P2** | sheet 名归一化幂等 | normalize(normalize(name)) == normalize(name) |
| **P3** | F1 取数科目集合不重不漏 | {1124, 1141, 2205} 严格匹配 D5/D6/D7 |
| **P4** | cross_wp_ref ref_id 唯一性 | 任两条 ref_id 不重复 |
| **P5** | B/C 前置 → D sign-off 阻断 | 完成度=0 → wp 不能 sign-off（gate_engine 集成）|

**max_examples**: P1/P2/P3/P4 = 50（P0 关键属性，参照 template-library spec 规约）；P5 = 20

---

## 五、风险与缓解

| 风险 | 影响 | 概率 | 缓解 |
|------|------|------|------|
| F1 修正影响其他 spec 已有数据 | 高 | 低 | 备份 + Sprint 0 核验确认仅 4 条 entry 错位 |
| F4 scenario 字段改 ORM 后向不兼容 | 中 | 极低 | 字段已存在（E1 spec 已落地，Sprint 0 已确认）|
| F5 useDSalesCycleSheetGroups 与 E1 useUniverSheetNav 冲突 | 低 | 低 | 各自独立 composable，按底稿类型路由 |
| F8 ≥ 40 条 cross_wp_ref 手工编写易错 | 中 | 中 | 实施时逐条核验 + Property 测试 P4 唯一性卡点 |
| F10 prefill 扩展 30 cell 表样格式核验耗时 | 中 | 中 | Sprint 0 强制先做表样实测（用户偏好铁律）|

---

## 六、实施前置条件（启动 Sprint 1 必备）

1. ✅ E1 spec 全量 UAT 通过（依赖矩阵确认）
2. ✅ P0 quickfix（F1+F2+F3 共 2 天）单独立项完成
3. ✅ Sprint 0 现状核验通过（已完成 2026-05-18）
4. ⏳ 三件套 design.md / tasks.md 完成 review
5. ⏳ E1 9 个核心组件源码确认 commit hash 锁定

---

## 七、与 README v1.3 §6.4 schema/API/code 骨架对照

design.md 是"为什么这么设计"，README §6.4 是"具体怎么写代码"；二者关系：

| design ADR | README 锚点 |
|-----------|------------|
| D1 F1 修复方式 | §6.4 F1 详细（一次性脚本 + E2E SQL）|
| D2 F2 归一化算法 | §6.4 F2 详细（chain_orchestrator 修改点）|
| D4 F4 scenario | §6.4 F4 详细（ORM 字段 + Alembic + 触发逻辑）|
| D5 F5 13 类规则 | §6.4 F5 详细（useDSalesCycleSheetGroups 完整代码）|
| D6 F6 反向回填 | §6.4 F6 详细（CW-108 完整 JSON）|
| D7 F7 4 条 VR | §6.4 F7 详细（validation_rules JSON）|
| D8 F8 ≥ 40 条 | §6.4 F8 详细（CW-115 字段示例）|
| D9 F9 CustomerInterviewDialog | §6.4 F9 详细（完整 Vue 组件）|
| D10 F10 30 cell | §6.4 F10 详细（待补分布表）|

## 八、与 README v1.3 §十二 ADR + §十四 范围边界双向引用

### 8.1 README §十二 ADR-1~5 双向引用

详见上方 D14 ADR 双向映射表。下表是 design.md → README ADR 的反向追溯（实施时遇争议查表）：

| README ADR | 涉及 design D-N | 实施铁律 |
|-----------|----------------|---------|
| **ADR-1** 复用 E1 9 组件 | D9 唯一新建 + 全部 D1-D13 复用清单 | 不重复造轮子 |
| **ADR-2** 多文件合并策略 | D2 归一化 + D3 历史遗留过滤 | 同款 wp_code 前缀合并 |
| **ADR-3** 双总控台切换 | D4 SCENARIO_TO_FILE_FILTER | scenario 字段驱动 |
| **ADR-4** 5 类组件分流 | D5 13 类规则 | 按 sheet 内容特征不按编号 |
| **ADR-5** prefill 不覆盖检查表 | D10 表样核验铁律 | B 检查清单/D 访谈/关联方判断不强行 prefill |

### 8.2 README §十四 范围边界（做/不做）→ requirements §二 引用

requirements.md §2.1 必做 F1-F12 / §2.2 排除 O1-O8 完整对应 README §十四 范围边界 12 项做 + 8 项不做清单。

**关键不做项**（独立 spec）:
- O1 / F11: 7 循环函证统一管理中心（D0+E0+F0+G0+H0+K0+L0+A17-5-5）
- O8: B/C/D-N 三层联动机制（统一规划 14 循环前置依赖）
- D 实施方案推广到 E/F/G/H/I/J/K/L/M/N 11 循环

---

> **本 design.md 配套**: requirements.md（需求）+ tasks.md（实施计划）  
> **代码骨架**: 见 README v1.3 §6.4（详细实施代码）  
> **架构决策**: 双向参照 README v1.3 §十二（ADR-1~5）+ §十四（范围边界）  
> **下一步**: 起草 tasks.md 完整 Sprint 拆解
