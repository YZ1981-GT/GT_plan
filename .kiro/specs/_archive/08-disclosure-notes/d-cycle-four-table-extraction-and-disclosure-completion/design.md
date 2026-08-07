# Design Document

## Overview

本设计把 D 循环的取数链路从「硬编码科目码前缀」切换到「语义驱动 + 逐项目动态定位」，并收口披露/附注侧 4 个结构缺口与 1 组联动。

核心判断三条：

1. **不新建定位机制**。`four_table/semantic_account_resolver.py` 与 `four_table/d_cycle_specs.py` 已存在且质量达标（后者含 7 个 spec、备抵槽、否决词、逐项 DB 实证注释），本 spec 是它的**第一个消费者**。已实证 G/H/E1/M8 共 28 个策略在用同一套件，D 类是最后一块空白（D·F·I·J·K·L·N 目前均为 0，本 spec 只做 D）。
2. **取数改造是加法式的**。render 输出的既有扁平键（`tb_values` / `adjudication_prefill` / `project_context.tb_amount`）**逐字不变**，新增 `tb_source_codes`（含 `slots`/`conflicts`/`unmapped_candidates`/`chart_available`）与 `parent_check`。理由：这些扁平键已被 7 个前端 composable 广泛消费，而 `html_data` 在 TS 里是 `any` —— 改键名不会编译报错，只会静默读到 `undefined`。
3. **披露→附注侧只做定点修补**。14 个主章节的行集与列结构已由前序 spec 三向对齐（源 xlsx ↔ 模板 headers ↔ 同步 columns），本 spec 不重做；只做母公司章禁删守卫（原「孤儿重复章处置」已按实证撤回）、D4 分解信息表动态列、D3/D7 账龄边界、三个组件金额控件。

### 与既有 spec 的边界

| 议题 | 归属 | 本 spec 的动作 |
|---|---|---|
| `report_config` 的 `BS-006 listed_standalone` 用整个 `1231` | `report-config-account-code-integrity` | 检出并写入 `conflicts`，如实告警；不改数据 |
| `report_config` 的 `IMP-002` 用点号 `TB('1231.02')` 恒空 | 同上 | 同上 |
| `report_config` 的 `IMP-004` formula 四准则全 NULL | 同上 | D6 备抵改由 spec 兜底码 + 反解承载，不依赖该行 |
| `account_mapping` 的 `1231.05 → 1231-02` `auto_fuzzy` 错映射 | 数据治理 | 取数侧叠名称过滤兜住 |
| 附注 14 主章节行集/列结构 | 已完成（前序 spec） | 不动 |
| D0 函证循环取数 | 无（源模板无披露 sheet） | 只修 3 处贴错标签的预设 sheet 名 |

## Architecture

### 取数链路（改造后）

> **方案已修正**：不换解析器，而是把 D1 已建好的 `report_line_accounts` 范式推广到 D2~D7。
> 理由见 requirements.md Requirement 1 的方向修正说明。

```
四表入库
   │
   ├─ tb_balance（客户原始码，点号体系，含方向列）
   ├─ trial_balance（标准码，横杠体系，只有一级总额+期末）
   ├─ account_chart（client 表 / standard 表，两套编码体系并存）
   └─ account_mapping（原始码 → 标准码）
   │
   ▼
render 策略 _dN_xxx.py
   │
   ├─(1) codes = await resolve_d_cycle_account_codes(ctx, wp_code)
   │        ← 新增 d_cycle_extraction/d_account_resolver.py（D1 薄壳的参数化推广）
   │        内部委托既有共享件 report_line_accounts.resolve_report_line_accounts：
   │          报表行 row_code → report_config.formula（按 applicable_standard）
   │            → 标准码 → split_gross_provision 拆原值/备抵
   │            → account_mapping 反解 → 本项目原始码
   │          任一环失败 fail-open 回退兜底码，resolved_from 标注实际来源
   │        D1 继续走自己的 d1_account_resolver（零回归红线，口径同源）
   │
   ├─(2) 备抵侧无条件叠名称过滤（filter_provision_codes）
   │        补第三种污染成因：反解成功但 account_mapping 有 auto_fuzzy 错映射
   │        （1231.05 坏账准备_长期应收款 → 1231-02，既有 use_provision_name_filter 拦不住）
   │
   ├─(4) rows = await tb_query.fetch_tb_subtree(db, pid, year, prefixes)
   │        已内建：get_active_filter 四参 async / 宽取子树含父行 / fail-open+rollback
   │        另计 tb_rows_count（命中行数）供「有科目但四表无数据」态
   │
   ├─(5) leaf_aggregation.resolve_leaf_totals(rows, prefix)  ← 同步纯函数，不 await
   │        双符号约定各算一遍，取与**父额**勾稽成立的那一种
   │        🔴 不得先 select_leaves —— 父行是符号约定的判定依据
   │
   ├─(6) parent_check.build_parent_check(accounts, tb_rows, trial_rows, slot_keys)
   │        三口径：叶子和 / 父行 / trial_balance；found=False 的槽不产生该键
   │
   └─(7) 载荷输出
            html_data.project_context.tb_source_codes  ← 新增（含 slots/conflicts）
            html_data.project_context.parent_check     ← 新增
            html_data.tb_values / adjudication_prefill ← 既有键逐字不变
```

### 前端消费链路

```
render-config
   │
   ▼
宿主 GtDNxxx.vue
   ├─ 必须显式传 :html-data 给审定表子组件（守卫扫模板断言）
   │
   ▼
DNTabAdjudication.vue
   ├─ useDNAdjudication({ tbValuesSeed, adjudicationPrefill })
   │     手工优先 / 只覆盖命中行 / 无数据且无手工值显式写 0
   ├─ 「从四表库带入未审数」按钮
   └─ WpFourTableSourcePanel（平台共享件）
         props 名必须与其 defineProps 一致（守卫动态抽取比对）
         「本项目无此科目」→ info tag（非 danger）
         conflicts 非空 → 告警条
```

### 披露→附注链路（既有，本 spec 只补缺口）

```
DNTabDisclosure*.vue
   ├─ 账龄档位 ← composables/disclosureAgingLabels.ts（D3/D7 本次接入）
   ├─ 金额控件 ← WpAmountInput（D2/D5/D6/D7 本次收敛）
   ├─ D4 分解信息 ← 动态列 + {slot}_{seq} 稳定键 + 持久化单调计数器
   │
   ▼ buildDNSyncPayload(variant)
   ├─ sub_table_data = { 表名: [业务键行] }
   ├─ _sub_table_columns（group / flat 显式表态，seed 与推送两侧都要加）
   ├─ _row_scope（多段共享表才需要，D 类主章节各自独占，不涉及）
   └─ _removed_table_keys（条件表清理，与本次推送键求差集）
   │
   ▼ POST /disclosure-notes/sync-from-workpaper
   └─ 定位键 (project_id, year, note_section)
         孤儿重复章守卫：禁任何 dXNoteSectionMap 指向孤儿章号
```

## Components and Interfaces

### 后端新增/修改

| 组件 | 类型 | 职责 |
|---|---|---|
| `four_table/d_cycle_specs.py` | 修改 | 备抵槽 `names` 全名化 + `subject_keywords`；**当前不接线**，文件头须写明实证理由（防后续会话重复迁移） |
| `four_table/d_provision_filter.py` | 新增 | `filter_provision_codes(codes, name_by_code, subject_keywords)` 纯函数，返回 `FilterResult(kept, dropped, warnings, applied)`。补既有 `use_provision_name_filter` 拦不住的第三种成因 |
| `d_cycle_extraction/d_account_resolver.py` | 新增 | D1 薄壳的参数化推广：D2~D7 的 `ReportLineAccountSpec` + 统一返回类型 `DCycleAccountCodes` + `resolve_d_cycle_account_codes(ctx, wp_code)`。D1 不动 |
| `four_table/d_cycle_extraction.py` | 新增 | 7 个 render 共用的取数**编排**（只串联，不重造查询/聚合）。已实证平台工具链完备：`resolve_semantic_accounts` / `resolver.to_original_codes` / `tb_query.fetch_tb_subtree` / `tb_query.fetch_trial_balance_amounts` / `leaf_aggregation.resolve_leaf_totals` / `parent_check.build_parent_check` / `resolver.build_conflicts` 全部已有，本件唯一新增逻辑是把 Task 2 的名称过滤插进「反解 → 查库」之间，以及构造 `tb_source_codes` 载荷 |
| `_d1_notes_receivable.py` ~ `_d7_contract_liabilities.py` | 修改 | 删硬编码前缀，改委托上述编排件；既有输出键逐字保留 |
| `scripts/fix/fix_d_cycle_prefill_presets.py` | 新增 | 幂等脚本：4 处 sheet 名 + D4 期初 + D5 PLACEHOLDER + 6 个明细块 + 12 张披露 sheet 块 + `WP()` 联动；含 round-trip 自检 |
| `scripts/fix/cleanup_d_cycle_orphan_note_sections.py` | 新增 | 孤儿重复章处置，默认 dry-run，`--apply --confirm` 双确认，per-note savepoint |
| `scripts/diagnose/verify_d_cycle_extraction_live.py` | 新增 | 真实库直跑 7 循环 × 全部项目，只读，输出逐槽 `resolved_from` / 金额 / `parent_check.diff` |

### 前端新增/修改

| 组件 | 类型 | 职责 |
|---|---|---|
| `composables/dCycleAccountScope.ts` | 新增 | 循环科目视图单一真源，委托平台共享工厂 `composables/shared/cycleAccountScope.ts`；提供 `isAccountAbsent()` 区分「无此科目」与「余额为 0」 |
| `DNTabAdjudication.vue` ×7 | 修改 | 加「从四表库带入未审数」+ 挂 `WpFourTableSourcePanel` |
| `GtDNxxx.vue` ×7 | 修改 | 补 `:html-data` 透传 |
| `d4RevenueSegmentColumns.ts` | 新增 | D4 分解信息动态列模型：`{slot}_{seq}` 稳定键 + 单调计数器 + 旧列迁移 |
| `D3TabDisclosureListed/Soe.vue` `D7TabDisclosure.vue` | 修改 | 接 `disclosureAgingLabels` + 「按账龄段生成」 |
| `D2DisclosureNoteBody.vue` `D5TabDisclosure.vue` `D6TabDisclosure.vue` `D7TabDisclosure.vue` | 修改 | 金额控件换 `WpAmountInput`（43 + 14 + 3 + 4 = 64 处） |
| `composables/d3DetailSeed.ts` `composables/d4SegmentSeed.ts` | 新增 | 客户子科目联动 seed 纯函数 |

## Data Models

### 语义规格（既有结构，本 spec 只改槽的 names）

```python
# four_table/d_cycle_specs.py（改造后的备抵槽形态）
D1_SPEC = SemanticAccountSpec(
    row_code="BS-005",
    slots=(
        _gross("gross", ("应收票据",), ("1121",), "应收票据"),
        _provision(
            "provision",
            # 🔴 全名 + 两种分隔符写法；禁裸「坏账准备」（会命中一级科目 1231）
            ("坏账准备-应收票据", "坏账准备_应收票据"),
            ("1231-01",),
            "坏账准备-应收票据",
            subject_keywords=("应收票据", "票据"),   # 新增：反解后名称过滤用
        ),
    ),
)
```

### render 载荷（新增部分）

```jsonc
// html_data.project_context.tb_source_codes
{
  "slots": {
    "gross": {
      "found": true,
      "resolved_from": "account_chart_client",   // 或 account_chart_standard / report_config / fallback / none
      "codes": ["1121"],                          // 定位到的标准/科目表码
      "query_codes": ["1121", "1121.01", "1121.02", "1121.03"],  // 反解后用于查 tb_balance 的原始码
      "label": "应收票据",
      "amount": 20209198.18,
      "tb_rows_count": 4                          // 该槽前缀在 tb_balance 的命中行数（含父行）
    },
    "provision": {
      "found": true,
      "resolved_from": "fallback",
      "codes": ["1231-01"],
      "query_codes": ["1231.01"],
      "dropped": [                                // 名称过滤剔除的行（供溯源展示）
        { "code": "1231.05", "name": "坏账准备_长期应收款",
          "reason": "名称不含本循环主体关键词（应收票据/票据）" }
      ],
      "warnings": [],                             // 保留但需人工确认（当前只有 name_missing）
      "label": "坏账准备-应收票据",
      "amount": 0.0,
      "tb_rows_count": 2
    }
  },
  // 向后兼容的扁平投影（既有消费方读它，不得移除）
  "gross": ["1121"], "gross_standard": ["1121"],
  "provision": ["1231.01"], "provision_standard": ["1231-01"],
  "provision_exact": true,
  "resolved_from": "account_chart_client",
  "conflicts": [
    ["provision", "1231", "1231-01"]   // [槽键, 报表公式给的码, 按名/兜底定位到的实际码]
  ],
  "unmapped_candidates": [],
  "chart_available": true
}

// html_data.project_context.parent_check
{
  "leaf_sum": 20209198.18,
  "parent_amount": 20209198.18,
  "trial_balance_amount": 20209198.18,
  "diff_parent": 0.0,
  "diff_tb": 0.0
}
```

### 「本项目无此科目」态的表达

```jsonc
// D6 合同资产在全库任何项目的实际形态（tb_balance 中 1141/1142 均 0 行）
{
  "slots": {
    "gross":     { "found": false, "resolved_from": "none", "codes": [], "amount": null },
    "provision": { "found": false, "resolved_from": "none", "codes": [], "amount": null }
  },
  "chart_available": true
}
```

- `amount: null` ⇒ 前端渲染「本项目无此科目」info tag，审定表该行留空
- `amount: 0` ⇒ 渲染 `0.00`（或按 `displayPrefs.showZero` 显示 `-`）
- 键不存在 ⇒ 未取数

### D4 分解信息动态列模型

```typescript
// d4RevenueSegmentColumns.ts
interface D4Segment {
  key: string;      // 稳定键 seg_1 / seg_2 …（禁用中文 label 作键）
  label: string;    // 本项目实际板块名（批发 / 零售 / 物流 …）
  seq: number;      // 取自持久化单调计数器，禁复用已删除序号
}
interface D4SegmentState {
  segments: D4Segment[];
  nextSeq: number;  // 持久化，next = max(现有最大 seq, 已存计数器) + 1
  legacy: Array<{ label: string; note: string }>;  // 未匹配上的旧列，保留待人工归并
}
```

### 「孤儿重复章」清单 —— 立项判断已被实证推翻，改为母公司章禁删守卫

🔴 **原设计（保留备查，不得实现）**：曾计划建 `scripts/fix/cleanup_d_cycle_orphan_note_sections.py`
删除下列 5 章，判据为「`_aligned_by` 为空 + 全部子表 `columns` 长度为 0 + 表名命中泄漏特征」：

```python
# ❌ 已撤回。这 5 章是母公司附注章的正当子节，删除 = 删掉母公司附注。
_WITHDRAWN_ORPHAN_SECTIONS = {
    "listed": ["十六、应收票据", "十六、应收账款", "十六、营业收入与营业成本"],
    "soe":    ["十二、应收账款", "十二、营业收入与营业成本"],
}
```

**推翻依据（2026-08-06 逐章核 `parent_section_id`）**：

| 章号 | `parent_section_id` | `scope` | tables | 结论 |
|---|---|---|---|---|
| 十六、应收票据 / 应收账款 / 营业收入与营业成本 | `chapter-16-mu-gong-si-cai-wu-bao-biao-zhu-yao-xiang-mu-zhu-shi` | `consolidated_only` | 14 / 17 / 6 | 母公司章子节 |
| 十二、应收账款 / 营业收入与营业成本 | `chapter-12-mu-gong-si-cai-wu-bao-biao-de-zhu-yao-xiang-mu-fu-zhu` | `consolidated_only` | 13 / 5 | 母公司章子节 |

**判据自证失效**：同章另 7 个子节（listed 其他应收款 21 表 / 长期股权投资 3 表 / 投资收益 1 表；
soe 其他应收款 19 表 / 长期股权投资 3 表 / 投资收益 1 表 / 现金流量表补充资料 1 表）形态
**完全相同**（`_aligned_by=None` + `columns` 全 0）却不在清单里 ⇒ 那两条判据描述的其实是
「母公司章 93 张表 100% 无列元数据」这一**已登记的平台事实**（归 A spec
`parent-company-note-chapter-and-sourcing`），不是孤儿特征。

**按原判据（含第三条表名泄漏）实跑的真实结果**：listed 命中 **23 章**、soe 命中 **0 章**，
与清单**零重叠**。23 章全部在「三、重要会计政策」与「十四、日后事项」章下
（如 `三、现金流量表项目注` 9 表全名 `项  目`、`三、套期` 16 表全空名、`三、分部报告`），
属 C spec `note-template-columns-and-legacy-snapshot-closure` 的「listed 163 张 / 53 章
非科目章节无对应披露 sheet」那一批 —— **本 spec 范围外**。

### 母公司章禁指向守卫（Task 22 的实际交付物）

```python
# backend/tests/services/test_note_d_orphan_sections.py
PARENT_COMPANY_CHAPTERS = {
    "listed": "chapter-16-mu-gong-si-cai-wu-bao-biao-zhu-yao-xiang-mu-zhu-shi",
    "soe":    "chapter-12-mu-gong-si-cai-wu-bao-biao-de-zhu-yao-xiang-mu-fu-zhu",
}
# 与 D 类同名的母公司子节（本 spec 关心的那 5 个 + 完整子节集合作反向自检）
PROTECTED_SECTIONS = {
    "listed": ["十六、应收票据", "十六、应收账款", "十六、营业收入与营业成本"],
    "soe":    ["十二、应收账款", "十二、营业收入与营业成本"],
}
```

守卫做三件事：① 断言这 5 章的 `parent_section_id` 仍是母公司章（形态漂移即打红，防被
误当孤儿删掉）② 断言全部 `*NoteSectionMap.ts` 不指向 `十六、`/`十二、` 任何章号
（D 类 7 个 map 应指向 `五、4`/`八、4` 等合并章）③ 断言**不存在** `cleanup_*orphan*note*`
类删除脚本（反向锁死，防后续会话照原 design 实现）。

## Correctness Properties

### Property 1: 科目解析结果被真实消费而非仅被赋值

对 D2~D7 六个 render 源码，`resolve_d_cycle_account_codes` 的返回值变量必须被后续读取（`.` 或 `[` 访问，或整体传入下游函数），赋值数与读取数均 ≥ 1。判据须变量名无关（先抓 `(\w+)\s*=\s*await resolve_d_cycle_account_codes` 再数该变量被读次数）。D1 因走 `resolve_d1_account_codes` 单独同款断言。

**Validates: Requirements 1.1, 1.2**

### Property 34: 语义规格保留但不接线且理由在册

`four_table/d_cycle_specs.py` 的模块 docstring 必须包含「当前不接线」及其实证理由；同时断言全库 `backend/app/**` 中除测试外**无任何** `d_cycle_specs` 的生产消费方。反向自检：若某天接线了，该断言会打红，提示同步更新 docstring 与本 Property。

**Validates: Requirements 2.6**

### Property 2: render 内不残留硬编码科目码作为查询条件

7 个 D render 源码经 `stripComments()` 后，不得出现形如 `LIKE '1121%'`、`startswith("1122")`、`ACCOUNT_PREFIX = "2205"` 的字面量科目码用于查询；字面量仅允许出现在传给 spec 的兜底码位置或 docstring 中。

**Validates: Requirements 1.2, 5.5**

### Property 3: 叶子聚合口径与父额勾稽

对真实库每个（项目, 年度, 循环）组合，若 `gross` 槽 `found=True` 且父科目行存在，则 `parent_check.diff_parent` 的绝对值 ≤ 0.01。

**Validates: Requirements 1.3, 1.5**

### Property 4: NULL 余额不污染聚合且数据行数如实记录

构造含 `closing_balance=None` 的原始行，经 `to_leaf_rows` 归一后聚合结果必须是数值而非 None；且 `tb_rows_count` 等于该槽前缀命中的原始行数。反向自检：绕过 `to_leaf_rows` 直接对含 None 的序列求和时抛 TypeError 或得 None。

**Validates: Requirements 1.3**

### Property 5: 方向不一致的族按符号求和

构造同族内 `closing_direction` 为 debit 与 credit 混合的叶子行，聚合结果等于带符号和；反向自检：逐行 abs 时结果与带符号和不等。

**Validates: Requirements 1.4**

### Property 6: 共享件按实证签名调用

7 个 D render 与新增编排件中，`select_leaves` 不得被 `await`（同步纯函数）、`aggregate_leaves` 必须传 `prefixes`、`get_active_filter` 必须四参调用。判据以 `inspect.signature` 实证为准。

**Validates: Requirements 1.7**

### Property 7: 备抵槽不含一级科目通名

`D_CYCLE_SPECS` 中每个 `is_provision=True` 的槽，其 `names` 元组不得包含 `坏账准备` / `减值准备` / `跌价准备` 等裸通名；且每个备抵槽至少提供横杠与下划线两种写法、并声明非空 `subject_keywords`。

**Validates: Requirements 2.7**

### Property 8: D1 与 D2 备抵科目码集合无交集

对真实库每个项目，D1 与 D2 经各自解析器 + 名称过滤后的备抵原始码集合交集为空。反向自检：跳过名称过滤时，在那 2 个含 `auto_fuzzy` 错映射的项目上 D2 会拿到 `1231.05`。

**Validates: Requirements 2.5**

### Property 9: 名称过滤无条件生效且剔除被如实记录

D2~D7 的备抵侧必须无条件调用 `filter_provision_codes`（不以 `use_provision_name_filter` 为门），源码级断言此点。被剔除的码进 `dropped`（含 `code`/`name`/`reason` 三字段）、名称缺失的进 `warnings` 且仍在 `kept` 中，两集合无交集。

**Validates: Requirements 2.1, 2.3, 2.4**

### Property 35: 主体关键词粒度足以区分同族科目

对每个循环的 `subject_keywords`，断言用它过滤时能拦住同族异科目名：D2 的关键词必须拦住「坏账准备_长期应收款」而放行「坏账准备_应收账款」。反向自检：关键词换成「应收」时该断言打红。

**Validates: Requirements 2.2, 2.8**

### Property 10: 四态互不混淆

对同一槽：`found=False` ⇒ `amount is None` 且 `codes == []`；`found=True` 且 `tb_rows_count == 0` ⇒ `amount is None`；`found=True` 且 `tb_rows_count > 0` 且聚合为 0 ⇒ `amount == 0`（不是 None）；render 未执行 ⇒ 载荷中无该槽键。四者两两互斥。

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

### Property 33: 前缀体系不匹配被检出而非静默取空

当某槽 `query_codes` 中存在含横杠的码（说明 `account_mapping` 反解失败、`resolve_semantic_accounts` 保留了标准码）且 `tb_rows_count == 0` 时，该槽必须带 `prefix_mismatch` 标志。反向自检：构造 `query_codes=['1231-04']` 的槽，断言标志为真；构造 `['1231.04']` 的槽断言为假。

**Validates: Requirements 3.2, 3.6**

### Property 11: 原值与备抵拆分正确且不互相污染

对真实库每个项目、每个有备抵的 D 循环（D1/D2/D6），断言 `gross` 与 `provision` 的原始码集合交集为空，且 `gross` 中不含任何命中 `_PROVISION_CODE_PREFIXES` 的码。反向自检：跳过 `split_gross_provision` 时 `1231` 会同时出现在两侧。

**Validates: Requirements 3.8**

### Property 12: 前端不依赖 `Number(null) === 0`

前端消费 `tb_source_codes` 与 `adjudication_prefill` 的代码中，取数值前必须有 `!= null` 或 `!== null` 或 `Number.isFinite` 守卫；守卫扫描相关 composable 源码断言此点。

**Validates: Requirements 3.5**

### Property 13: 宿主已传 `:html-data`

扫描 7 个 D 循环宿主 SFC 模板，凡渲染 `DNTabAdjudication` 的位置必须带 `:html-data` 或 `v-bind="$props"`。反向自检：移除任一处后守卫打红。

**Validates: Requirements 4.2**

### Property 14: 溯源面板属性名与 defineProps 一致

从 `WpFourTableSourcePanel.vue` 的 `defineProps` 动态抽取合法属性名（转 kebab-case），断言 7 个调用点的属性名均在该集合内，且必填属性已传。反向自检：传一个不存在的属性名时打红。

**Validates: Requirements 4.1, 4.6**

### Property 15: 带入操作不覆盖手工值且清零有提示

`pullFromFourTable` 纯函数：对已有手工值的行返回原值；对四表命中的行返回四表值；对「四表无数据且无手工值」的行返回 0 并计入 `clearedCount`。断言 `clearedCount` 被提示文本消费。

**Validates: Requirements 4.4, 4.5**

### Property 16: 公式预设脚本幂等且 round-trip 安全

`fix_d_cycle_prefill_presets.py --apply` 连跑两次，第二次 `--check` 返回 0 项欠账；且脚本在写回前对未改动部分做 `json.dumps` 逐字比对，不一致则退出非零。

**Validates: Requirements 5.1, 5.2**

### Property 17: 预设 sheet 名存在于源模板

D 类全部预设块的 `sheet` 值必须能在对应源 xlsx 的 `wb.sheetnames`（含 hidden）中找到。判据以 openpyxl 直读为准。反向自检：保留 `审定表D0-1` 时打红。

**Validates: Requirements 5.3**

### Property 18: D4 审定表期初与未审数公式不同

`营业收入审定表D4-1` 块中「期初余额」与「未审数」两个 cell 的 `formula` 不得逐字相同；且「期初余额」必须是 `PREV` 类型。

**Validates: Requirements 5.4**

### Property 19: `WP()` 联动无环

对 D 类全部预设块构图（块 → 其 `WP()` 引用的目标 sheet），图中不得存在环。反向自检：给明细表块加一条反向引用审定表的 `WP()` 时打红。

**Validates: Requirements 5.8**

### Property 20: PLACEHOLDER 逐条登记理由

D 类预设中每个 `formula_type == 'PLACEHOLDER'` 的 cell，其 `description` 长度 ≥ 20 字且须说明「为什么写不成公式」；且该 cell 必须在守卫的 `_PLACEHOLDER_REGISTRY` 中登记。

**Validates: Requirements 5.9**

### Property 21: 曾被列为孤儿的 5 章仍归属母公司章

`PROTECTED_SECTIONS` 中每一章在模板 JSON 里必须存在、且 `parent_section_id` 等于对应变体的
母公司章 `section_id`、`scope == 'consolidated_only'`、子表数 > 0。任一条不满足即打红
（形态漂移或被删除都会被抓到）。反向自检：断言同章另有 ≥3 个子节形态相同
（`_aligned_by=None` + `columns` 全 0），证明原「孤儿判据」描述的是母公司章共性而非孤儿特征。

**Validates: Requirements 6.1, 6.3**

### Property 22: 无 NoteSectionMap 指向母公司章

扫描全部 `*NoteSectionMap.ts` 的章节号常量（80 个文件），断言无一以 `十六、`（listed 母公司章）
或 `十二、`（soe 母公司章）开头 —— 母公司章取数归 A spec 的 `parent_company_scope`，
per-cycle map 指向它就会把合并口径数据推进母公司章。实测当前命中数为 0。

**Validates: Requirements 6.4, 6.5**

### Property 23: 诊断脚本只读且不含删除能力

`scripts/diagnose/diagnose_d_cycle_note_section_hygiene.py` 源码经 `stripComments()` 后
不得出现 `DELETE` / `db.delete(` / `--apply` / `--confirm`；模块 docstring 必须声明
「只读」。反向自检：断言脚本里确实有 `SELECT`/读模板 JSON 的行为（证明它不是空文件）。

**Validates: Requirements 6.2, 6.3**

### Property 24: D4 动态列键稳定且不复用序号

`allocateSegment` 纯函数：删除某列再新增，新列 `seq` 严格大于历史最大值；键形如 `seg_\d+`，不含中文。反向自检：按「现有最大 seq + 1」分配时会复用已删除序号。

**Validates: Requirements 7.2, 7.3**

### Property 25: D4 分解信息表无硬编码行业名

`d4NoteSectionMap.ts` 与 D4 披露组件源码中，不得出现 `汽车` / `消费品` / `能源` 作为列定义字面量；附注模板该表的 `columns` 由动态列生成，两侧列头同构（收入/成本两级分组）。

**Validates: Requirements 7.1, 7.5**

### Property 26: D3/D7 账龄档位取自单一真源

`D3TabDisclosureListed.vue` / `D3TabDisclosureSoe.vue` / `D7TabDisclosure.vue` 必须 import `disclosureAgingLabels`，且不得出现 `1年以内` / `1至2年` / `3年以上` 等档位字面量；国企首档必须引用 `DISCLOSURE_AGING_WITHIN1_SOE`。

**Validates: Requirements 8.1, 8.3**

### Property 27: 无账龄维度的循环不得引用账龄真源

D1 / D5 / D6 的披露组件不得 import `disclosureAgingLabels`（源模板依据：D1 按票据种类、D5 为票据、D6 按组合/单项）。此为反向锁死，防「统一化」误改。

**Validates: Requirements 8.5**

### Property 28: 金额控件已收敛且非金额列未误套

D2/D5/D6/D7 披露组件的 `el-input-number` 计数为 0；同时断言比例 / 损失率 / 账龄天数 / 年度 / 笔数列未使用 `WpAmountInput`（反向边界）。

**Validates: Requirements 9.2, 9.3**

### Property 29: `fmtAmount` 以 store 成员方式取得

相关组件不得出现 `import { fmtAmount } from '@/stores/displayPrefs'`（模块级命名导出不存在，会让整页崩）；必须在 setup 顶层 `inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()` 后调用成员方法。

**Validates: Requirements 9.4**

### Property 30: 联动 seed 幂等且不覆盖手工

`seedD3Detail` / `seedD4Segment` 纯函数：对已有手工行返回原行；重复执行不产生重复行（按业务键去重）；某侧缺失时留 `null` 而非 0。

**Validates: Requirements 10.3, 10.4**

### Property 31: seed 按本项目实际叶子名建行

`seedD3Detail` 的入参是本项目叶子行集，输出行名逐字取自 `account_name`；断言不含任何跨项目固定分类名常量。

**Validates: Requirements 10.5**

### Property 32: 既有 render 输出键零回归

对 7 个 D render，改造前后 `html_data` 的键集合（递归到二级）必须满足：改造后 ⊇ 改造前；且既有键在同一输入下取值逐字节相同。以 characterization 测试锚定。

**Validates: Requirements 1.1, 1.2**

## Error Handling

| 场景 | 处理 | 理由 |
|---|---|---|
| `resolve_semantic_accounts` 抛异常 | fail-open 返回空槽 + WARNING（含 wp_code 与阶段） | 取数失败不应让整张底稿打不开 |
| 某槽定位不到科目 | `found=False` / `amount=None`，**不抛异常** | 「本项目无此科目」是正常业务态 |
| `account_mapping` 无反解行 | 退化为直接用标准码前缀查 `tb_balance`，并在 `resolved_from` 标注 | 部分项目原始码与标准码同形 |
| 名称过滤把某槽剔空 | `codes=[]` + `dropped` 记录全部被剔行 | 宁缺勿造，且必须可追溯 |
| `parent_check` 查不到父行 | `parent_amount=None`、`diff_parent=None` | 三态原则，不编造 0 |
| `report_config` 公式解析失败 | 跳过第③层，直接走槽兜底码 | 不让配置问题阻塞取数 |
| 孤儿章处置时某条记录有数据 | 跳过并记入 `skipped`，不计入失败 | 数据零丢失红线 |
| 公式预设脚本 round-trip 失败 | 退出码 2，不写盘 | 防全文件重排与并发冲突 |
| D4 旧列无法匹配新板块 | 保留进 `legacy` 并标注待人工归并 | 不静默丢弃已同步数据 |

## Testing Strategy

### 后端

- `tests/four_table/test_d_cycle_specs_evidence.py` — 冻结 7 个 spec 的 `row_code` ↔ 报表行名（连库快照，一次 `asyncio.run` 取全部数据后同步断言）+ 备抵槽全名断言 + 跨循环互斥
- `tests/four_table/test_d_cycle_extraction.py` — 编排件纯函数：NULL 聚合 / 方向混合 / 三态 / 名称过滤，含 5 条反向自检
- `tests/four_table/test_d_render_wiring.py` — 源码级：真实消费（变量名无关）/ 无硬编码码 / 签名正确
- `tests/four_table/test_d_render_characterization.py` — Property 32 键集与取值零回归
- `tests/test_d_cycle_prefill_presets.py` — sheet 名存在性（openpyxl 直读）/ 期初≠未审数 / 无环 / PLACEHOLDER 登记
- `tests/services/test_note_d_orphan_sections.py` — Property 21/22/23

### 前端

- `dCycleAccountScope.spec.ts` — 三态判定 + 读后端 py 源码交叉锁死槽键与兜底码（`REPO_ROOT` 用双哨兵**具体文件**向上查找，禁写死回退级数）
- `dHostPropWiring.spec.ts` — Property 13/14（从 SFC 动态抽 defineProps）
- `d4RevenueSegmentColumns.spec.ts` — Property 24/25，含 PBT
- `dCycleAgingWiring.spec.ts` — Property 26/27
- `dCycleAmountControl.spec.ts` — Property 28/29
- `dCycleSeed.spec.ts` — Property 30/31

### 真实库验收（不可省，单测替身查不出的三类）

`scripts/diagnose/verify_d_cycle_extraction_live.py`（只读）逐项目逐循环输出，必须满足：

1. **D7 在那个 client 码为 `2204` 的项目取到 7,855.34**（这是本 spec 最硬的单点验收）
2. D6 / D5 全部项目 `found=False` 且 `amount=None`（不是 0）
3. D1 备抵不含 `1231.02`；D1 与 D2 备抵 `query_codes` 交集为空
4. 全部 `found=True` 的槽 `parent_check.diff_parent` 绝对值 ≤ 0.01
5. 含 NULL 余额的 5 个子科目所在循环聚合结果为数值而非 None

### 浏览器实测（三件套，缺一不算实测）

录 ≥2 行真实数据 → 看目标区域真出数 → postgres 查落库；测完按快照复原（含 `parsed_data` / `checklist_responses` / 附注 `last_sync_at`）。
