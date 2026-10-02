# Design — 抽凭科目真源接线与挂凭链路收口

## 现状确认（设计阶段实证，非引用快照）

所有计数为 2026-09-28 现算。**禁写死行号**：`.vue` 行号会漂，判据锚点统一用「文件名 + 导出常量名 + 形态特征」。

### 科目关联的两条路径

```
路径 A（抽凭引擎）—— 关联在查询阶段完成，机制正确
  宿主 account-code
    → useVoucherSampling.buildDefaultConfig()  split(',') → config.accountCodes
    → POST /voucher-extract  filters.account_codes
    → 后端按科目查 tb_ledger（LedgerSamplingService）
    → 返回行天然带 account_code
    → 样本 accountCode = item.account_code
    → 宿主 @filled → onSampleFilled 回填

路径 B（序时账挂凭）—— 关联在回拉阶段靠前缀筛，有两处缺陷
  用户序时账挂凭 → sampled_vouchers(account_code, voucher_date, working_paper_id)
    → pullSamplesForWorkpaper(projectId, year, wpId, accountPrefixes)
    → fetchVoucherLines(no, date)  取【整张凭证全部分录】
    → lineMatchesAccounts(line, accountPrefixes)  按前缀筛
    → 🔴 缺陷①：if (picked.length === 0) picked = lines   ← 筛空回退取全部
    → 🔴 缺陷②：rec.account_code（挂凭意图）只用于兜底显示，不参与筛选
    → 宿主 onSampleFilled 回填
```

### 挂载点分布

| 类别 | 现算数量 | 说明 |
|---|---|---|
| 静态字面量 `account-code="1234"` | **70** | 本 spec 主改造对象 |
| 动态绑定 `:account-code="X"` | **17** | 形态正确，但须验证 `X` 的取值来源（Requirement 6.6） |
| 与真源不一致的静态挂载点 | **25** | 分布见 requirements Requirement 1.4 |
| 路径 B 的消费端 | **1** | 仅 `E1TabLargeCheck`（`pullSamplesForWorkpaper` 全仓 3 处命中：定义 + 该宿主 + 无第三方调用） |

### 真源资产

| 类别 | 现算数量 | 位置 |
|---|---|---|
| 前端科目真源 | **42** | `components/workpaper/composables/*AccountScope.ts` |
| 后端科目真源 | **11** | `services/four_table/*_account_scope.py` |
| 真源判「宁缺勿造」（`FALLBACK_STANDARD = ''`） | **3** | `i5AccountScope` · `k4AccountScope` · `l7AccountScope` |

真源导出形态（以 `k5AccountScope.ts` 为范式，其余同构）：

```ts
export const K5_REPORT_ROW_CODE_LISTED = 'BS-065'
export const K5_FALLBACK_STANDARD = '2801'     // 兜底标准码（trial_balance 口径）
export const K5_ACCOUNT_NAME = '预计负债'
export function k5QueryCodes(src?): string[]    // 原始码前缀集（tb_balance/明细查询口径）
export function k5AccountCode(src?): string     // 标准码单值（回写 trial_balance 口径）
export function k5SourceLabel(src?, isListed?): string  // 溯源展示文案
```

🔴 **两种口径不可混用**：`{x}QueryCodes()` 返原始码前缀集（供 `tb_ledger`/`tb_balance` 前缀匹配），`{x}AccountCode()` 返标准码单值（供 `trial_balance` 回写）。抽凭查的是 `tb_ledger` ⇒ **应用 `QueryCodes`**；本轮前置修复因两个 K5 宿主无 `tbSourceCodes` prop 而用了 `FALLBACK_STANDARD`，属可接受降级（见「决策 D-3」）。

## 架构决策

### D-1：以前端 `*AccountScope.ts` 为唯一判据，不以 `wp_account_mapping.json` 为准

**理由**（三方对账实证）：

| 来源 | K10 | K12 | H5 | 与真实库科目名一致？ |
|---|---|---|---|---|
| 底稿真实名（`wp_index`） | 其他收益 | 营业外收入 | 油气资产 | — |
| 前端真源 | `6117` 其他收益 | `6301` 营业外收入 | `1631` 油气资产 | ✅ 全中 |
| `wp_account_mapping.json` | `6301` 营业外收入 | `6001` 主营业务收入 | `1606` 固定资产清理 | ❌ 全错 |

前端真源文件头带 `account_chart` / `tb_balance` / `report_config` 公式的实证记录（如 `k5AccountScope.ts` 明写「`report_config` 的 BS-068/BS-094 公式也是 `TB('2801')`」），可审计性强于 json。

### D-2：`QueryCodes` 优先、`FALLBACK_STANDARD` 降级，禁止第三种来源

```
科目码解析优先级（每个挂载点一律按此顺序）
  1. props.tbSourceCodes 存在 → {x}QueryCodes(props.tbSourceCodes)   ← 运行态解析，最准
  2. 无该 prop              → [{X}_FALLBACK_STANDARD]                ← 标准码兜底
  3. FALLBACK 为空串        → 降级禁用抽凭（Requirement 2）           ← 宁缺勿造
```

**禁止**：组件内字面量、从 `wp_account_mapping.json` 另读一份、跨循环借用别的真源。

### D-3：本轮前置修复（K5）的降级取值是否需要升级为 `QueryCodes`

现算 `K5TabLitigationCheck` / `K5TabProvisionCheck` 的 `defineProps` **均无 `tbSourceCodes`**，故前置修复取 `K5_FALLBACK_STANDARD`。

判定：**本 spec 不为此单独加 prop 链路**。理由 —— 加 prop 需改 K5 主入口的 provide/props 下传（跨 4+ 组件），收益仅在「项目 report_config 把预计负债映射到非 2801 的自定义码」这一低频场景；而 `2801` 已由真实库 6 项目实证为标准码。**改为在真源模块留 TODO 锚点**，待 K5 主入口下次改造时顺带下传。此判定写入 design 供复核，不静默省略。

### D-4：路径 B 的「挂错底稿」如何呈现

三个候选：

| 方案 | 行为 | 取舍 |
|---|---|---|
| A. 拒绝导入并报错 | 整批失败 | ❌ 一张挂错拖垮整批 |
| B. 跳过该凭证 + 汇总提示 | 其余正常导入，末尾列出挂错的凭证号与其实际科目 | ✅ **采用** |
| C. 导入但标红待核 | 错科目数据进底稿 | ❌ 错数据落库，违背「不静默灌错」 |

采用 B。提示形态用可关闭的 `ElMessage`/`ElNotification`（含凭证号 + 实际科目列表），不阻塞。

### D-5：守卫的「换地方硬编码」规避问题

仅禁模板内字面量会被 `const X_ACCOUNT_CODE = '1717'` 规避（现算 17 处动态挂载点正是这种形态，其中多数引用的是真源、但不能假定）。

守卫策略：对动态挂载点，解析其绑定标识符，要求该标识符**或**来自 `*AccountScope` 的 import，**或**其赋值右侧不是数字字面量。两条件皆不满足即违规。

## 数据流改造对照

### 改造前后（路径 A，以 I2 为例，7 处同型）

```
改造前：<GtVoucherSamplingEngine account-code="1717" .../>
        └─ 1717 真实库无此码 ⇒ 后端按不存在的科目查 ⇒ 抽样总体为空或全库
改造后：import { i2GrossQueryCodes, I2_GROSS_FALLBACK_STANDARD } from '../../composables/i2AccountScope'
        const samplingAccountCode = computed(() =>
          (props.tbSourceCodes ? i2GrossQueryCodes(props.tbSourceCodes) : [I2_GROSS_FALLBACK_STANDARD])
            .filter(Boolean).join(','))
        <GtVoucherSamplingEngine :account-code="samplingAccountCode" .../>
```

`join(',')` 的依据：`useVoucherSampling.buildDefaultConfig()` 现算对 `accountCode` 做 `split(',')`，故多码用逗号拼接是既有契约，无需改引擎。

### 改造前后（路径 B 筛选优先级）

```
改造前：picked = lines.filter(命中底稿前缀)
        if (picked.length === 0) picked = lines            ← 灌入全部科目
改造后：picked = lines.filter(命中底稿前缀)                 ← ① 正常
        if (空) picked = lines.filter(命中 rec.account_code) ← ② 挂凭意图，remark 标注
        if (空) → misattached.push({voucherNo, 实际科目})    ← ③ 不产样本，汇总提示
        lines 本身为空（穿透失败）→ 保留占位样本            ← 技术失败，与 ③ 区分
```

## 实施顺序与风险

| 阶段 | 内容 | 风险 | 缓解 |
|---|---|---|---|
| 1 | 守卫先行（先写、允许初始红） | 无 | 红即待修清单，可量化进度 |
| 2 | 值已正确的接线（K10/K12/H5/E1） | 极低（运行时逐字节不变） | 用作接线模式样板 |
| 3 | 值错误的接线（G1/I2/I6/F2） | 中（抽样总体会真的变化） | 逐循环验证抽样总体非空 |
| 4 | 空码降级（I5/K4） | 中（UI 态新增） | 三态可区分（禁用/加载/只读）+ 截图留痕 |
| 5 | 路径 B 筛选优先级 | 中（唯一消费端 E1） | 单测覆盖 ①②③ + 穿透失败四情形 |
| 6 | 勘误登记 + 清理探针 | 无 | — |

**阶段 3 的真实风险**：修正科目码后抽样总体从「空/全库」变为「真实该科目」，样本会与修正前不同。这是**修复的正确后果**，但若已有项目基于错科目抽过样并留痕，历史批次不应被追溯改写 —— `workpaper_extraction_log` 是 append-only 审计轨迹，本 spec 不回填历史批次，只影响新发起的抽样。该点须在交付说明中明示。

## 测试策略

| 层 | 内容 |
|---|---|
| 守卫（源码级） | 静态字面量禁令 + 动态标识符溯源 + `accountPrefixes` 禁字面量 + 禁「筛空回退」形态；每条配反向自检 |
| 单元 | 路径 B 四情形（①②③ + 穿透失败）；空码降级的三态 |
| 契约 | `{x}QueryCodes` / `{X}_FALLBACK_STANDARD` 导出存在性（防真源改名致静默降级） |
| 真源值 | 对 25 处涉及的真源常量断言具体值（如 `I2_GROSS_FALLBACK_STANDARD === '1704'`），防有人"顺手"改回错码 |
| 零回归 | 既有 42 + 9 + 187 test 全绿 |

🔴 **剔注释纪律**：所有源码级守卫必须先剔 `<!-- -->` / `/* */` / `//`，因为「为什么不能用 1717」这类说明性注释会含被禁字面量。本轮 K5 守卫首版即因此误报 3 个已修好的文件。剔除器本身须有自检（剔后仍能取到关键代码）。

## 判据引用闭合性

本 spec 的每条 Requirement 验收项都须被 tasks 中某个任务显式引用。交付前用脚本核对「每条 AC 至少被引用一次」，而非只数编号连续 —— 前者能抓出「整族任务漏写」，后者不能。

---

## 实证更正节（阶段 1 守卫落地后现算，2026-09-28）

守卫跑出的真实数字与设计阶段的估算有出入，此处如实更正。**本节为 append，不回填修改上文**（保留原判断轨迹便于复核）。

### 更正 1：两个分母必须分开说 —— 「60 个文件」与「25 处不一致」

| 口径 | 现算值 | 含义 |
|---|---|---|
| 含静态 `account-code` 字面量的**文件**数 | **60** | 守卫 R6.1 的违规面（判据＝来源形态） |
| 静态**挂载点**数（文件 × 挂载点，I2/I6 的 Cutoff 各含 2 处） | **70** | 设计阶段写的数，口径是挂载点 |
| 与真源**取值不一致**的处数 | **25** | Requirement 1.4 表格的行数（判据＝取值对错） |
| 值正确但仍是字面量（须接线防漂移，R1.5） | **35** | = 60 − 25（按文件口径的近似差，非精确减法） |

上文 design「挂载点分布」表里的 70 与 requirements R1.4 的 25 **都没错，是两个不同判据的分母**；但只写其中一个会让人误以为工作量是 25。**接线工作量的真实规模是 60 个文件**，比设计阶段的直觉估算大一倍以上。

### 更正 2：F2 归类错误 —— 属「宁缺勿造」而非「错码」

requirements R1.4 把 `F2TabContractCostCheck` 的 `1410` 列为「真实库无此码 ⇒ 组件错」，归入阶段 3（值错误的接线）。现算推翻该归类：

| 证据 | 现算结果 |
|---|---|
| `F2_INVENTORY_ACCOUNT_CODES`（`f2NoteSectionMap.ts`） | `Array.from({length:12}, (_,i)=>String(1401+i))` = `['1401'..'1412']` ⇒ **1410 在区间内**，不是「区间外的错码」 |
| 另一处同名常量（`useF2InspectionCheckFormulas.ts`） | 字符串 `'1401,...,1411'`，**亦含 1410** |
| 真实库 `1410` | **零命中** |
| 真实库 `1341`（准则的合同履约成本标准码） | **零命中** |
| 真实库 `1412` | **零命中** |
| 真实库任何 `account_name LIKE '%合同履约成本%'` 或 `'%合同资产%'` | **零命中**（8 个项目全无） |

⇒ 正确结论：**这 8 个真实项目（医药流通 / 租车）确实没有合同履约成本业务**，不是组件把码写错了。把 `1410` 改成 `1341` 毫无意义（两者真实库都查不到），且属于替审计师做专业判断。

**处置更正**：F2 从阶段 3 移入阶段 4（宁缺勿造降级），与 I5 / K4 同组 —— 抽凭入口在解析不出科目时禁用并提示，而不是拿一个查不到的码去抽空。

🔴 该更正同时意味着 **`f2AccountScope.ts` 缺位**：F2 现算无 `*_FALLBACK_STANDARD` 导出（只有 `F2_INVENTORY_ACCOUNT_CODES` 这个存货区间常量，语义是「存货族前缀集」而非「合同履约成本科目」）。按 requirements R1.3，须先建真源再接线；但本 spec 不替审计裁决「合同履约成本该用哪个码」⇒ 真源建立时 `FALLBACK` 取**空串**（宁缺勿造），并在文件头记录上表证据。

### 更正 3：守卫抓到一处设计阶段未登记的违规

`F2ValuationTestSheet.vue` 的 `:account-code="valuationAccountCodes.join(',')"` 形态合规（动态绑定），但 `valuationAccountCodes` 的赋值右侧是数字字面量 ⇒ 属「换地方硬编码」，被 R6.6 判据抓到。

这印证了 D-5 决策的必要性：**只禁模板内字面量会被常量规避**。该条目补入待修清单（阶段 3 处理）。

### 更正 4：阶段 3 / 阶段 4 的任务边界随之变化

| 原 tasks | 更正后 |
|---|---|
| 3.4 F2 一处：`1410` → `F2_INVENTORY_ACCOUNT_CODES` | **移入阶段 4**：建 `f2AccountScope`（FALLBACK 空串）+ 降级禁用 |
| 阶段 3 新增 | `F2ValuationTestSheet` 的 `valuationAccountCodes` 溯源修正 |
| 阶段 4 覆盖面 | 由 I5 / K4 两处 → I5 / K4 / F2ContractCost 三处 |

任务总数不变（32），只在阶段间移动与替换。

---

## 阶段 3 实证记录（任务 3.5 / 3.6，2026-09-28）

### 更正 5：我自己把 `6604` 误判为「勘探费用」—— 科目定义的权威源是 `account_chart`

设计与调研阶段我用 `tb_balance` 的 `MIN(account_name)` 聚合取科目名，得出「6604 = 勘探费用」，并据此怀疑 `i6AccountScope` 的真源值有错。**该判断是错的**：

| 数据源 | `6604` 的名称 | 说明 |
|---|---|---|
| `account_chart`（科目**定义**表） | **研发费用 6 条** + 勘探费用 1 条 | 权威源 |
| `tb_balance` 的 `MIN(account_name)` | 勘探费用 | 恰好取到唯一那个把 6604 用作勘探费用的项目 |
| `wp_index` 的 I6 底稿名 | **研发费用** | 与 `account_chart` 多数口径一致 |

⇒ `I6_GROSS_FALLBACK_STANDARD = '6604'`（研发费用）**正确**，组件的 `6602`（管理费用，K9 循环）**错误**。

🔴 **方法论教训（下一轮必带）**：查「某科目码是什么科目」必须用 `account_chart`（定义表），**不能**用 `tb_balance` / `tb_ledger` 的 `MIN/MAX(account_name)` 聚合 —— 后者是各项目账套的**实际用法**，同一码在不同项目可以挂不同名称，聚合函数会随机取到其中一个，样本偏差会直接导致误判真源有错。

顺带更正 `i6AccountScope.ts` 的文件头标题：原写「I6 管理费用」，与其下一行「不是 6602（管理费用）」自相矛盾，已改为「I6 研发费用」。该误写正是上述误判的诱因之一。

### 任务 3.5：修正后科目的真实数据状况

| 循环 | 改后码 | `account_chart` 定义 | `tb_balance` 覆盖项目 | active `tb_ledger` 行数 | 判读 |
|---|---|---|---|---|---|
| G1 主表 | `1101` | 交易性金融资产 | 6 | **0** | balance 有余额、ledger 无发生额（本年无交易），正常 |
| G1 衍生 | `1102` | 衍生金融资产 | 0 | 0 | 这 8 个项目无衍生业务 |
| I2 | `1704` | 开发支出 | 5 | **0** | 有科目但期末余额全 NULL，无发生额 |
| I6 | `6604` | 研发费用 | 1 | **0** | 医药流通/租车企业无研发支出 |
| H5 | `1631` | 油气资产 | 1 | 0 | 仅 1 个项目有该科目 |

**改前 I6 的 `6602` 在 active `tb_ledger` 有 52,617 行（9 个项目）。** 表面看「修复后抽样总体从 5 万行变 0 行」像是功能退化，实则相反：

- 那 52,617 行是**管理费用**凭证，与「研发费用检查」无关 —— 抽出来的样本从一开始就是错的，只是「碰巧有数据」掩盖了错误；
- 改后为 0，反映的是**这些项目确实没有研发支出业务**这一真实事实。正确的产品行为是走 Requirement 2 的降级（明确提示「本项目无此科目」），而不是拿错科目凑出样本。

⇒ 该现象印证了 Requirement 2「宁缺勿造 + 显式降级」的必要性，且**降级的适用面比设计阶段预估的更广**（不止 I5/K4/F2，G1/I2/I6/H5 在当前数据下同样会落到空总体）。阶段 4 的降级逻辑应做成**通用**的（按解析结果为空即降级），而非只给 I5/K4/F2 三处打补丁。

### 任务 3.6：历史批次不追溯（交付说明）

`workpaper_extraction_log` 是 append-only 审计轨迹。本 spec **不回填**基于错科目发起的历史抽样批次：

- 修正只对**新发起**的抽样生效；
- 已留痕的历史批次保持原样（含其 `filled_voucher_nos` 与方法学快照），便于复核追溯「当时依据什么科目抽的」；
- 若需重抽，由审计师在底稿内显式重新发起，走正常的批次状态机。
