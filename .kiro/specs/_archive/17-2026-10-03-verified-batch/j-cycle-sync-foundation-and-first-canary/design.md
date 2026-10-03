# Design Document

## Overview

本 design 承载 **JC-1 ~ JC-20 共同裁决**、**canary `J1-6-short-term` 端到端设计**，
以及 **FC / GC / HC / IC 在 J 的适用性重裁**。

🔴 **分工铁律**：JC-1 ~ JC-20 只在本文件裁一次，下游 lane spec
（`j2-j3-non-entry-hosts-and-orphan-cleanup`）**只写编号 + 一句话用途**，正文一条不抄。

### J 循环一句话形态

**3 个可达宿主 + 3 本权威模板 + 160 个传输键 + 11 条 BP，但只 1 条独立 entry。**
前六轮的隐含前提「每宿主 ↔ 每 entry」在 J 全面失效：照它写「entry 数 == 册数」会得 3 而实际 1，
要么假红、要么被「手写补两条 entry」的错误修法绕过（违反 slice selection_rule 的 forbidden）。

## 实测与 slice 的关系：结构性零反驳 + 六处快照过期 + 五处实质反驳

### 结构性结论（现算零反驳，可直接采信）

3 模板 sha256/size/sheets · 4 orphan 行数 41/37/35/39 · 共享基类 65 行 / localStorage 0 /
statement 边 **29** / J 贡献 **3** · `useChecklistPersistence` 边 **23** ·
第二写路径 **7 文件 / 8 站点** · owner 常量实值逐字相符 · **8 个 guessed key 各 0 命中** ·
位置化 family_a **1** / family_b **6** · `severance.defaultRows` 恰 **1 行**空 label ·
`J1_DETAIL_SECTION_KEYS` 三字面量 + 注释「与 useJ1Detail 的 STORAGE_KEY_PREFIX 一致」逐字确认。

### 🔴 六处快照过期（实施时必须重算）

| # | slice 记 | 现算 |
|---|---|---|
| 1 | manifest entries **186** | **155** |
| 2 | 契约目录 **5** 份 | **18** 份；`DELIVERED_PER_ENTRY_CONTRACTS` **21** 条；`adapter_registered=True` **5** 条 `{d2,d4,g7,h1,d1}` |
| 3 | 共享基类宽口径 **30**，差集 **1** | 宽 **34**，差集 **5**（生成文件 + 自身 + `GtG2InterestReceivable.vue` + `GtN2TaxesPayable.vue` + `useK9DualMode.ts`） |
| 4 | Notice 消费方 **41** | **48**（J 域仍 0 ✓） |
| 5 | 组件类行号 | 🔴 **全漂 10~28 行**；composable 常量区**未漂** |
| 6 | `useJ2FormData.ts` 待删 | **已被物理删除** |

### 🔴 五处实质反驳（不是过期，是结论错）

1. **J1 有 TB 发布门** —— slice 与「`publishToTb` 符号名 0 命中」都误导；
   真实门在 `J1TabAdjudication.vue` 的 `api.post('…/audit-determination/publish-to-tb')`
   ⇒ **GC-9 在 J 是 1/1 有门**，canary 能覆盖发布链。
2. **写路径六类端点**，slice 的「双轨」严重低估（详见 JC-3）。
3. **OCR 在 J 命中** —— `useJ1VoucherOcr.ts` 调 D4 端点 ⇒ FC-8 不是「不适用」。
4. **披露层 8 个拼接键**完全不在 slice 的 TK-1~TK-7 里 ⇒ `declarations_total = 7` 不完整。
5. **BP-11 是 4 文件 5 处真源**，slice 只记「两份」。

---

## JC-1 ~ JC-20 共同裁决

### JC-1　manifest capability 的实测口径与迁移路径（= BP-9）

现算 J 的两条 manifest entry（1 independent + 1 parent_duplicate）：

```
capability        : single_onlyoffice        # 🔴 不是 slice 的 null（那是 slice 的裁决值）
html_store        : unresolved
capability_target : <字段不存在>              # 🔴 slice 的 bidirectional 是 slice 裁决值
mount_count       : <字段不存在>              # 🔴 slice 的 1 是 slice 自算值
adapter_id        : None
independent_entry : True / False
parent_entry_id   : None / xlsx/j1/gt-j1-employee-compensation
```

**根因**：那两个值来自 `backend/data/workpaper_sync_entry_overlay.json` 的
`defaults_by_component.GtOnlyOfficeSheet` —— 对**所有**挂 `GtOnlyOfficeSheet` 的 entry 一律给默认值。
⇒ 重新生成 manifest **不会**自动修正，必须先改 overlay 的 defaults 或给该 entry 加 override。

**裁决**：迁移只走 `register_from_manifest()`；🔴 **禁手改 manifest 文件**。
与 FC-12 / G BP-6 / HC-1 / IC-1 同源，本条只补 J 的实测值。

### JC-2　载体族第三种：`shared_platform_persistence_adapter`（IC-2 在 J 的扩展）

```
write_carrier      : composables/workpaper/useChecklistPersistence.ts
write_client       : api                      # 🔴 import { api } from '@/services/apiProxy'
write_endpoint     : PUT /api/workpapers/{wp_id}/checklist-responses
read_carrier       : 同一适配器的 load()      + render-config 快照作断网/旧数据兼容基线
statement 消费边   : 23（现算）—— K1~K13 十三个 + createChecklistFormData + useD2FormData
                     + useK5FormData + J1/J2/J3 三宿主 + k5Persistence + checklistPersistenceHelpers + 2 test
宿主侧            : handleChildSave(items) → persistence.saveDebounced(item_id, patch)
```

🔴 **两条对照反证（判据必须含）**：
① 按 H 的「载体里必须有 `http.put`」去核 ⇒ 在 `useChecklistPersistence` 上**假红**（它用 `api.put`）
② 按 I 的「宿主必须 import `@/utils/http`」去核 ⇒ 在 J1 宿主上**假红**
   （现算宿主 `@/utils/http` 与 `apiProxy` 命中**均为 0**，逐 item 防抖 / flush / 错误态全在适配器里）

⇒ 判据 SHALL 按 entry 声明的 `write_client` 名字去找 `{client}.put(`，不写死 `http`。

### JC-3　🔴 写路径判定必须按端点字面量，不是符号名（IC-3 在 J 的扩展）

IC-3 把「禁符号名 grep」用在 **import 边**；J 证明它同样适用于**写路径与发布门**。

| # | 端点 | 文件数 | 性质 |
|---|---|---|---|
| ① | `PUT /api/workpapers/{wpId}/checklist-responses` | **11** | 主写（J1 十个子 Tab + 🔴 `j3/core/J3TabDetail.vue`）+ orphan `useJ3FormData.ts` |
| ② | `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb` | **1** | 🔴 **TB 发布门** |
| ③ | `POST /api/projects/{projectId}/disclosure-notes/sync-from-workpaper` | **4** | 🔴 写**另一张表** |
| ④ | `POST /api/projects/{projectId}/events/publish` | **4** | 事件广播（J2/J3 侧） |
| ⑤ | `POST /api/projects/{projectId}/cross-wp-references/batch` | **1** | 跨底稿引用（J3 侧） |
| ⑥ | `POST /api/workpapers/{wpId}/ai/generate-text` | **15** | AI 生成（**非持久化**） |

另有：`j1/import-data` · `j1/export-data` · `j1/export-template` · `j2/*` · `import-export/*` ·
🔴 `POST /api/workpapers/{wpId}/d4/contract-ocr`（跨循环端点复用）·
`GET /api/projects/{projectId}/trial-balance` · `GET /api/workpapers/onlyoffice/health`（orphan 违规直调）。

🔴 **非空反证**：符号名 `publishToTb` 在全 J 域命中 **0**，而端点 ② 命中 **1**。
「按函数名判定得 0、按端点判定得 1」就是本条判据存在的全部理由 —— 没有这个反证，
「我们按端点判定」只是自述。

### JC-4　一表三键 + 键真源多份（JD-4 / BP-11）

```
primary managed table : J1-2-detail-{shortTerm | postEmployment | severance}
derivation            : `${STORAGE_KEY_PREFIX}${section}`，section ∈ J1_SECTIONS[].key
owner (写方)          : composables/workpaper/j1/useJ1Detail.ts
identity_field        : id                    # 🔴 不是 rowId
key_order_matters     : true（决定 persistAll 里 items 的顺序）
```

🔴 **BP-11 实测是 4 个文件 5 处声明**（slice 只记两份）：

| # | 文件 | 形态 |
|---|---|---|
| ① | `useJ1Detail.ts` | `STORAGE_KEY_PREFIX` + `storageKey()` **派生**（写方） |
| ② | `useJ1Adjudication.ts` | `J1_DETAIL_SECTION_KEYS` 三**字面量** |
| ③ | 🔴 `J1TabAccrualCheck.vue` | `DETAIL_KEYS` 三字面量 |
| ④ | 🔴 `J1TabAllocationCheck.vue` | `DETAIL_KEYS` 三字面量 |
| ⑤ | 🔴 `useJ1DisclosureSections.ts` | 三处 `readJson('J1-2-detail-…')` **内联** |

⇒ 判据 SHALL **五处同时比对**；变异「只改前缀」SHALL 打红（当前五处逐字一致，但这是**五份真源**，
改一处不会传播到另外四处，而读方会静默读空）。

同型多真源一并登记：`J1-1-rows` 2 处 · `J1-3-adjustment-rows` 同文件 2 处 · `J2-3-entries` 同文件 2 处。

### JC-5　🔴 模板字符串拼接键必须单独一族 + 三命名空间分清

slice 的 TK-1 ~ TK-7 **漏掉披露层 8 个键**，因为它们是**拼接**出来的：

```
useJ1DisclosureSections.ts:
  const prefix        = `J1-disc-${variant}`        # variant ∈ {listed, soe}
  const KEY_SUMMARY   = `${prefix}-summary`
  const KEY_SHORT_TERM= `${prefix}-short-term`
  const KEY_POST      = `${prefix}-post-employment`
  const KEY_NOTES     = `${prefix}-notes`
⇒ 2 × 4 = 8 键
```

真库确认有载荷：`J1-disc-soe-short-term` **1325 B** · `-post-employment` **917 B** ·
`-summary` **532 B** · `-notes` **118 B**。

⇒ 判据 SHALL 含**拼接键解析**：按前缀常量 × 后缀常量的笛卡尔积展开后再验，
完整字面量 grep 抓不到（这正是 slice 自己 `forbidden_shortcuts` 第 1 条「只 grep 键字符串存在」
警告的反面 —— 而 slice 自己在披露层踩了它）。

🔴 **三个命名空间必须分清，判据不得混用**：

| 命名空间 | 是持久化键？ | 用途 | 现算命中 |
|---|---|---|---|
| `J1-disc-{variant}-{section}` | ✅ **是** | checklist_responses 的 item_id | 8 |
| `J1-disclosure-{variant}[-{section}]` | ❌ 否 | `GtReviewTrigger` 的 `section-id` + `J1TabIndex` 的 `progressKeys` | 10 |
| `j1-disclosure-{variant}-${aiSection}`（小写） | ❌ 否 | AI 生成的 section 标识 | 2 |

🔴 **披露层缺口**：`J1TabDisclosureListed.vue` 有 `J1-disclosure-listed-severance` 这个 section-id，
但 `useJ1DisclosureSections` 只拼 4 个键（**无 severance**）⇒ 有该 UI 区块但**无对应持久化键**。

### JC-6　行身份族划分按 J 口径重裁（IC-6 在 J 的扩展）

| 族 | 判据 | J 现算 | 处置 |
|---|---|---|---|
| **A 纯序号真落库** | 身份完全由 `i + 1` 构成、无稳定兜底、经 saveImmediate 真写库 | **1**（`J2TabAdjustment` 的 `id: i + 1` → `J2-3-entries`） | **必修**（下游 lane；🔴 真库 171 B 载荷里 `"id":1` **已确证落库**） |
| **B 下标兜底** | 主身份是上游稳定 id，仅缺失时回落下标 | **6** | **必修**（entry 内 2 / non_entry 4） |
| **C 安全生成** | 含 `Math.random()` 且回落分支**不是**下标 | **3 + 1** | 保持，**反向断言不被点名** |
| **D 展示序号** | `seq: i + 1` 等，键不是身份字段 | **3**（三个目录页） | 保持，反向断言不被点名 |
| **E 四表种子** | `` `(seed\|row\|detail\|item)-${i}` `` | **0** | 空分母，只断言「现算 0 且不是漏扫」 |

🔴 **JD-8：slice 的 family_c 判别式过严**。它要求「同时含 `Date.now()` 与 `Math.random()`」，
但 `useJ1DisclosureSections.ts` 的 `id: String(r.id || \`row-${Math.random()…}\`)`
**只有 random 没有 Date.now()** ⇒ 会被排除出 C 族，而它其实安全。
⇒ 判别式 SHALL 扩为「含 `Math.random()` **且回落分支不是下标**」。
🔴 但 **原判别式的严格性不能丢**：`genId(idx)` 的函数体里也出现 `Math.random()`，
那是 `??` 的另一支、给了 idx 时不执行 ⇒ 判别式必须同时排除「`??`/`||` 左支给了下标」的形态。

🔴 **JD-7：披露层 49 个硬编码序号 id —— 登记但不判为位置化缺陷**

```
SOE   : s-1..s-5 (5) + st-1..st-12 (12) + pe-1..pe-8 (8) = 25
Listed: s-1..s-4 (4) + st-1..st-12 (12) + pe-1..pe-8 (8) = 24
合计 49
```

**为什么 slice 的扫描漏掉**：它们是**字面量 `'st-1'`**，表达式里没有 `i`/`idx`/`index`。
**为什么不判为缺陷（诚实结论）**：id 与 label 写在**同一个对象字面量**里，
绑定是静态的、不随数组顺序变 ⇒ 报成位置化会造出 49 个假缺陷。

**真正的四条风险（这才是须落表的内容）**：

| # | 风险 | 实证 |
|---|---|---|
| ① | 🔴 **同 id 跨变体语义不同** | SOE `st-4`=`其中：医疗保险费` / Listed `st-4`=`其中：1. 医疗保险费`；SOE `st-5`=`工伤保险费` / Listed `st-5`=`2. 工伤保险费`；🔴 SOE `st-7`=`其他` / Listed `st-7`=**`住房公积金`** |
| ② | 两侧行数不同 | SOE summary **5** / Listed summary **4**；SOE `st-12` 含「其他」/ Listed 含「非货币性福利」 |
| ③ | 🔴 新增行 id 形态与骨架不同 | `${category}-${Date.now()}` vs `st-N` ⇒ 同一数组混两形态 |
| ④ | 🔴 `s-${Date.now()}` **无随机串** | 同毫秒两次点「新增」会撞 id |

🔴 **entry / non-entry 必须分开登记**（J 独有的必要划分）：
缺陷维度 entry_scope **2** + non_entry **5** = **7**；两者 `must_fix_before` 不同
（entry 内的在发 per-entry contract 之前修；non_entry 的在 J2/J3 成为 entry 之前修，归下游 lane）。
混成一个数会让「J1 的契约还差什么」说不清。

### JC-7　removeRow 四种签名形态（IC-7 在 J 的扩展）

| 形态 | arity | 站点数 | 站点 |
|---|---|---|---|
| 单参 `id` | 1 | **3** | `J1TabAdjudication` · `J1TabNonMonetaryCheck` · `J1TabSeveranceCheck` |
| 单参 `rowId` | 1 | **1** | `J1TabAdjustment` |
| 🔴 双参 `(id, category)` | 2 | **2** | `J1TabDisclosureListed` · `J1TabDisclosureSoe` |
| 🔴 双参（参数顺序相反） | 2 | **2** | `J1TabGeneralCheck(key, id)` · `useJ1Detail(section, rowId)` |

合计 **8 处 / 4 形态**。

**裁决**：契约字段 SHALL 是 `{kind, arity, param_order}` **三元组** ——
H/I 用的单值枚举 `row_delete_api_kind: "index" | "identity"` 在 J 装不下。
🔴 **J 无「下标族」**（H/I 都有按 `rowIndex`/`index` 删的）⇒ 这是 J 比 H/I 好的一点，
但**双参形态是 J 独有** ⇒ 判据不得与 H/I 复用同一签名断言。

### JC-8　三边锁覆盖面必须扩到 `明细表J1-2 ` 之外（JD-9 ⇒ 新增 RD-5）

slice 的 **RD-1 ~ RD-4 全部只对 `明细表J1-2 `**。J1 册另有 4 张有行骨架的检查表
（`计提情况检查表J1-6` / `分配情况检查表J1-7` / `非货币性福利检查表J1-9` / `辞退福利检查表J1-10`）
**一条三边声明都没有** ⇒ 覆盖面缺口。

**五条 RD 裁定**：

| RD | impl 常量 | 源区间 | verdict | status |
|---|---|---|---|---|
| RD-1 | `J1_SECTIONS[shortTerm].defaultRows`（20） | `明细表J1-2 !B13:B32` | **MATCH 20/20** | clean（**唯一正例锚点**） |
| **RD-2** | `J1_SECTIONS[postEmployment].defaultRows`（8） | `明细表J1-2 !B37:B44` | **MISMATCH 2/8** | **defect** |
| RD-3 | `J1_SECTIONS[severance].defaultRows`（1 行空 label） | `明细表J1-2 !B50:B52`（三格真读全 None） | NEGATIVE | negative_clean |
| **RD-4** | `POST_EMPLOYMENT_DEFAULTS`（`J1TabAccrualCheck.vue`） | 同 RD-2 区间 | **第二份 impl 与源一致** | cross_impl_divergence |
| 🔴 **RD-5（新）** | `SHORT_TERM_DEFAULTS`（19，`J1TabAccrualCheck.vue`） | `计提情况检查表J1-6!A17..` | **MISMATCH** | **defect（本轮实测）** |

**RD-2 的两类差异必须分开计数（强度不同）**：
① **真标签差异 1 处** —— impl `其中：1.基本养老保险` 比源 `其中：1．基本养老保险费` **少一个「费」**
② **序号分隔符差异 5 处** —— 源全角 `．`(U+FF0E) / impl 半角 `.`（第 2/3/4/6/7 项）
第 1 项同时含两类 ⇒ 按位置计 **6 处不等 / 2 处相等**。

**RD-4 的价值**：三个真源（源 xlsx `B38` + `note_template_soe.json` + `note_template_listed.json`
后两者逐字相同 9 行）与**第二份 impl** 都带「费」，只有**第一份 impl** 不带
⇒ 把「改哪一边」从判断变成事实（改 impl 不改源），且**双向锁死**（把带费那份改成不带费也打红）。

**RD-5 实测差异（19 行逐格现算）**：🔴 **行数 19/19 一致**，但 **10 处内容不等**，分**三类**：

| 类 | 处数 | 样本 |
|---|---|---|
| ① 序号分隔符 全角 `．` vs 半角 `.` | 与 ② 叠加共 9 处 | 模板 `其中：1．工资` / impl `其中：1.工资` |
| ② 🔴 **缩进字符** | 同上 | 模板 `　　　2．奖金`（**3 个全角空格** U+3000）/ impl `2.奖金`（无前缀） |
| ③ 🔴 **单元格内换行符 `\n`**（RD-2 没有的第三类） | **1** | 模板 `八、辞退福利\n（因解除劳动关系给予的补偿）` / impl 同串**无换行** |

🔴 **同一张 sheet 内两个分区用不同缩进字符**：第 1 分区 R19-21/R25-27 用**全角空格** `　　　`，
第 2 分区 R42-44 用**半角空格** `    `（4 个）⇒ 判据不能用统一 strip 规则，须逐格字节比对。

修法标 `[ ]*`（业务确认改哪一侧）。

### JC-9　🔴 全角/半角与缩进禁归一化

`forbidden_shortcuts` 在 slice 冻结了 5 条，本条把第 5 条（**禁标点归一**）单列成裁决：
归一化会同时洗掉 RD-2 的 5 处分隔符差异与 RD-5 的缩进差异 ⇒ 判据从「抓到 6 处不等」变成「全等通过」。
变异「在比对前 `NFKC` 归一」SHALL 打红。

### JC-10　sheet 名三类空格禁 strip

| 类 | 数量 | 实例 |
|---|---|---|
| 尾部空格 | **2** | `审定表J1-1 ` · `明细表J1-2 ` |
| 名中空格 | **6** | `应付职工薪酬实质性程序表 J1A` · `…J1A-原版` · `…L1A-原` · `长期应付职工薪酬实质性程序表 J2A` · `…L2A` · `股份支付实质性程序表 J3A` |
| 🔴 跨 sheet 引用里带空格 + 单引号包裹 | 逐格 | `审定表J1-1 !B8 = ='明细表J1-2 '!C13` |

⇒ openpyxl 按精确名取表；重写公式时 SHALL 保留空格与单引号。变异「strip 后匹配」SHALL 打红。

### JC-11　HC-5 变体轴在 J 命中 2 组（I 循环是 0 组）

| 组 | 成员 | 性质 |
|---|---|---|
| `J1A` | `应付职工薪酬实质性程序表 J1A`(visible) + `…J1A-原版`(hidden) | 版本变体 |
| 🔴 `J1-10` | `辞退福利检查表J1-10`(visible, 48 行) + `股份支付检查表J1-10-删除`(hidden, 66 行) | **一码两义** |

🔴 `J1-10` 那组**不是版本变体**：两张的标题行逐字是「应付职工薪酬-辞退福利检查表」与
「应付职工薪酬-股份支付检查表」—— **两张完全不同业务的表共用一个子码**。
⇒ 按 sheet 尾码定位 SHALL 带 **visible 过滤**；变异「只按尾码匹配」SHALL 在 `J1-10` 上取到两张而打红。

**跨循环程序表串册 2 处**（登记不修）：J1 册 `应付职工薪酬实质性程序表 L1A-原`（🔴 **slice 漏记**）
+ J2 册 `长期应付职工薪酬实质性程序表 L2A`（现算是 **hidden**，slice 未记 hidden）——
两者都是 **L 循环**的程序表串在 J 册里。

### JC-12　footer 三形态 + 🔴 幽灵行

`明细表J1-2 ` 的三个分区 footer **形态各不相同**：

```
R33（短期薪酬合计）  =SUM(C13,C19:C20,C25:C31)   🔴 跳跃式（跳过已是小计的 C14:C18 / C21:C24）
R46（离职后福利合计） =C42+C37                     🔴 加法式（不是 SUM）
R53（辞退福利合计）  =SUM(C50:C52)                连续区间
```

`审定表J1-1 ` 同样三形态（R22 跳跃 `=SUM(B8:B10,B15:B21)` / R34 加法 `=B26+B31` / R41 连续）。
⇒ 照单一口径验 SHALL 假红。

🔴 **幽灵行 R45**：A/B/C 列全空但**有公式** `F45 = =C45+D45-E45`，
位于数据区 R37:R44 之后、footer R46 之前。
⇒ 按「有公式即业务行」会把 8 行算成 **9 行**而与 impl 的 8 项不符（假红）。
判据 SHALL 按 **B 列非空**判业务行，并对 R45 写显式排除断言。

### JC-13　definedName 基线 + 🔴 断链登记（IC-10 在 J 的加重）

```
现算基线   J1: 0     J2: 37    J3: 502
含 #REF!   —         30 (81%)  479 (95%)
```

🔴 J3 的 502 个实测是**跨循环复制残留**：`_1固定资产数据库_筛选打印` /
`_2其他资产_开办费除外_明细表` / `_2、主要业务活动` / `_.dbf` / `AS2DocOpenMode` 等
—— 明显来自 H（固定资产）/ K（其他资产）册。

**裁决**：登记基线 + 断言**不增长**；🔴 **不删**（删会让 max_column 内的公式整片失效）；
只声明「同步时不新增、不改写」。J2/J3 的处置归下游 lane。
🔴 **比 I 严重一级**：I 只是「definedName 非 0」（I4 476 / I5 334），J 是「非 0 **且绝大多数断链**」。

### JC-14　裸 IF per-file 中性化

```
现算 J1: 132   J2: 12   J3: 0      总 144
J1 内部  审定表J1-1  56 · 与同行业对比分析表J1-5 60 · 月度分析表J1-4 16
```

🔴 **J3 整册裸 IF 为 0**。per-file 挂 `oo_crash_neutralization_fn`；变异「整册统一挂」SHALL 打红。

### JC-15　BP-10 在 J 比 I 更差一层：无声失败

```
① notice 挂载       现算 J 域 0（该组件 48 个生产消费方全是 D/E/F/G/H，I 与 J 各 0）
② 文案真源引用      现算 J 域 0（workpaperEntrySyncNotice.ts）
③ el-segmented      宿主 1 处，但 🔴 isOoAvailable 在宿主命中 0 ⇒ 无二级门控
④ 兜底 tag          `仅结构化视图` 宿主命中 1（OO 探测失败时出现）
⑤ 运行时兜底        共享基类 switchMode 里 `if (target === 'onlyoffice' && !ooAvailable.value) return`
```

🔴 **为什么比 I2 那条更差**：I2 是「按钮可点但切不过去」；J1 在此之上还叠加了**共享基类的静默 return**
⇒ 用户点了**什么反应都没有**，既不切换也不报错，比 AC 1.5 要求的「不显示不可兑现的按钮」**更差**。

**裁决**：canary 内建**第一处** notice 挂载（文案真源必须是 `workpaperEntrySyncNotice.ts`，
🔴 禁在宿主硬编码中文）+ 同时给 `el-segmented` 补二级门控 `v-if="dualMode.isOoAvailable.value"`。
判据 SHALL **按 toolbar class `j1-dual-mode-bar` 定位区块**再看 —— 全文件 grep `el-segmented`
会命中 `J1TabGeneralCheck.vue` 与 `J2TabAdjudication.vue` 两处 **Tab 内部分段控件**而误判。

### JC-16　JD-6 伪消费边判据必须改（现算已失效）

slice 的 JD-6 说「宽口径 30、窄口径 29，**差集恰是** `workpaperSyncLegacyBaseline.generated.ts`」。
现算：宽 **34** / 窄 **29** / **差集 5 个**：

```
① components/workpaper/sync/workpaperSyncLegacyBaseline.generated.ts   ← JD-6 说的那个（5 处 JSON snippet 字符串）
② components/workpaper/composables/useWorkpaperEntryDualMode.ts        ← 自身（合理）
③ 🔴 components/workpaper/GtG2InterestReceivable.vue
④ 🔴 components/workpaper/GtN2TaxesPayable.vue
⑤ 🔴 components/workpaper/composables/useK9DualMode.ts
```

**裁决**：判据改成「差集**包含**该生成文件」+ **现算差集清单**，禁写死「差集恰是 1 个」。
🔴 但**窄口径的判别规则必须保留**：匹配点所在行、其之前的未转义双引号个数为奇数 ⇒ 落在字符串内 ⇒ 不是语句。
没有这条规则，连 import 路径字面量口径都会被那 5 处 JSON snippet 骗到。

### JC-17　跨循环冻结在 J 不命中（HC-8 / IC-17 反向）+ 端点跨循环复用命中 1 处

```
J 键被非 J 路径文件消费     : 0
J 文件里出现非 J 循环的键   : 0
⇒ J 循环完全自闭 ⇒ 改键名无跨循环风险（重大简化）
```

🔴 **但端点层面有跨循环复用 1 处**：`composables/workpaper/j1/useJ1VoucherOcr.ts` 调
**D4 的** `POST /api/workpapers/{wpId}/d4/contract-ocr`。
⇒ 冻结对象从「键」换成「**端点**」：改 D4 那个端点的请求/响应形状会打断 J1 的凭证 OCR。
⇒ 同时说明 **FC-8（OCR）在 J 命中**，不是「不适用」—— 宿主层 `ocr` 命中 0 成立，但 composable 层有。

### JC-18　`derived_total_keys` 现算 7 个 + 🔴 正则覆盖面

```
现算 7 个：
  J1-1-audited-total            J1-1-audited-begin-total
  J1-7-total-admin-expense      J1-7-total-production-cost    J1-7-total-selling-expense
  J2-listed-summary             J2-soe-summary
```

🔴 **正则必须覆盖 `-total-` 出现在中间的形态**：只写 `(total|subtotal|summary)$` 会得 **4** 个，
漏掉 `J1-7-total-*` 三个。这是本轮第三次「扫描口径漏网」（前两次是披露层拼接键、披露层 49 个硬编码 id）。
⇒ 判据 SHALL 现算并与基线等值比对，**禁写死阈值**。

键全集现算 **160 条**（J1 ~93 / J2 ~50 / J3 ~17）—— **全平台单循环最多**。

### JC-19　prefill 四处缺陷（登记 + 判据，修法外移）

字段名是 **`sheet`** 不是 `sheet_name`；J 命中 **10 条**，全 `cells` 型 / `items` 全 0；
`wp_code` 只 `J1`/`J2`/`J3` 三值（非子码）。

| # | 缺陷 | 后果 |
|---|---|---|
| ① | 🔴 `sheet: '审定表J1-1'` **缺尾部空格** | 模板真名是 `审定表J1-1 ` ⇒ 按名定位必失配 |
| ② | 🔴 `sheet: '明细表J1-2 '` 那条 `cells: []` | 空数组 = 死配置 |
| ③ | 🔴 `=PREV('J1','分析程序J1-3','审定数')` | **`分析程序J1-3` 在 23 张 sheet 里不存在**（真名 `调整分录汇总表J1-3`） |
| ④ | 🔴 J3 一条 `wp_name: '股份支付审定表'` | **J3 册没有审定表**（6 张 sheet 里无 `审定表J3-*`） |

修法标 `[ ]*`（prefill 配置属另一条产品链路）。

### JC-20　空分母纪律（Property 3 / 20 / 69 / 70）

| Property | J 分母 | 处置 |
|---|---|---|
| 3 | **两个，一空一实**：`bidirectional` entry 数 = 0（空）· AC 1.4 否定式义务（实） | 空的部分只断言前提（正向门关着），**不宣称通过** |
| 20 | contract 维度**空**（本 slice contract 数 = 0） | 只断言「逐文件读 `review.entry_id` 无一条属 J」+ 承载者存在，**不宣称通过** |
| 69 | 非空但**全为负向**（`UNVERIFIABLE` + 非空 `unverifiable_reasons` 6 条） | 正向逐 scenario 闭合需 BP-4，**不宣称通过** |
| 70 | **非空**：1 条 J entry × (D 7 + E 1 + F 8 + G 17 + H 9 + I 6) 两两不相交 + 契约归属逐文件读 | 真验，宣称通过 |

🔴 **其余「查过且为 0」的项一律同纪律**：`family_e` = 0 · 跨循环键引用 = 0 ·
`hardcoded_scan_result` 六模式全 0 · 越界引用 = 0 · 宽表 = 0 · Excel Table = 0 · localStorage = 0
⇒ 一律写成「**现算为 0 且不是漏扫**」，并 🔴 **复用已有变异注入脚本**
`backend/scripts/diagnose/mutate_task52_j_cycle_migration_guards.py` 逐条证明非空跑。

---

## FC / GC / HC / IC 在 J 的适用性重裁

### 🔴 反向或须修正

| 上游裁决 | 在 J 的状态 |
|---|---|
| **FC-8**（OCR 不适用） | 🔴 **命中** —— composable 层有真 OCR 调用，且**跨循环复用 D4 端点**（JC-17） |
| **GC-9**（TB 发布门） | 🔴 **1/1 有门** —— 按端点判定；符号名判定得 0 是误判（JC-3） |
| **HC-5**（变体轴） | 🔴 **命中 2 组**（I 循环是 0 组），其中 `J1-10` 是**一码两义**（JC-11） |
| **HC-8 / IC-17**（跨循环键冻结） | 🔴 **不命中** —— J 完全自闭；但**端点**跨循环复用命中 1 处（JC-17） |
| **IC-2**（载体族二分） | 须扩到**第三种** `shared_platform_persistence_adapter`（JC-2） |
| **IC-3**（禁符号名 grep） | 须从 import 边扩到**写路径与发布门按端点字面量判定**（JC-3） |
| **IC-6**（行身份四族） | 须加 JD-7（49 硬编码 id 登记不判缺陷）+ JD-8（family_c 判别式放宽）（JC-6） |
| **IC-7**（removeRow 两族） | 须扩到**四种签名形态 + `{kind, arity, param_order}` 三元组**（JC-7） |
| **IC-10**（definedName 基线） | 须加**断链登记**（J2 30 / J3 479 含 `#REF!`）（JC-13） |
| **IC-13**（footer 形态） | 须扩到**三形态并存 + 幽灵行排除**（JC-12） |

### 不命中（须按空分母纪律断言「查过且为 0」）

HC-13 宽表（max_column ≥ 200 的 0 张）· 越界引用 0 · Excel Table 0 · localStorage 0
（共享基类零 localStorage ⇒ legacy_deletion_paradigm **step 5 不适用**）·
IC-19 双区/三区派生区（`明细表J1-2 ` 是同一 sheet 内三分区，不是 I 的「派生区」形态）·
`family_e` 四表种子 0（J 的取数走序时账按月拉取、按 label 匹配已有行填值，**不新建行**）。

### 成立

FC-3 一册一 entry —— 🔴 J 是 **3 册 ↔ 1 entry = 单射但不满射**
（判据须验「单射 + 每个 `belongs_to_entry: null` 都带 `excluded_reason` + 有主那条真命中 entry_id」；
🔴 写死「双射」对本 slice 假红，写死「多对一」会放过夹带跨循环模板）·
FC-5 覆盖层例外 —— **J 暂无模板金额错误**（`附注披露信息（国有企业）!B29:E29` 经逐格核验是
**正确的去重写法**非缺陷，见下）· GC-10 零回归现算 · GC-1 representation pointer 按 entry_id ·
IC-12 wp_index 禁依赖（契约 `source_ref` 只用 `{workbook_sha256, sheet_name}`）。

### 🔴 一处扫描误报的复核结论（必须如实登记）

```
命中：附注披露信息（国有企业）!B29:E29 = =SUM(B17:B28)-SUM(B20:B23)     4 格
逐格核验：R19「社会保险费」= =SUM(B20:B23) 是小计；R20:R23 是其四个明细
语义：全区加总（含小计 R19 + 明细 R20:R23 = 重复计）再减去明细 ⇒ 正好抵消重复
结论：**正确的去重写法，不是缺陷**
```

⇒ 判据 SHALL 记录「扫描命中 4 格、逐格核验后判定非缺陷」。
只看命中数会造出 **4 个假缺陷** —— 这是「扫描口径必须复核」的第四个实例
（前三个是披露层拼接键、披露层 49 硬编码 id、`derived_total` 的 `-total-` 中置形态）。

### template_resolution_audit = clean（沿用 slice，现算复核）

37 个 J 码逐个实跑 `find_template_file` / `find_template_file_any`，**无一条回落到另一本**。
🔴 三条须登记的「非缺陷但反直觉」：
① `J1A` / `J2A` / `J3A` 程序表码在 `_index.json` 里**无独立条目**也无独立 render schema
② `J0` 两个函数都返 None（无函证册）
③ 🔴 `J2-5..J2-10` 与 `J3-3..J3-10` 这些**源模板里并不存在对应 sheet** 的子码，
   两个解析函数**仍返回各自的册**（解析按册前缀而非 sheet）
   ⇒ 判据若写成「解析结果非 None ⇒ 该 sheet 存在」会假绿。

---

## canary 选型：为什么是 `J1-6-short-term`

### 🔴 硬标准口径必须改

D~I 七轮的硬标准是「**真库 primary managed table 有非空载荷**」。在 J 它**不成立**：

```
J1-2-detail-shortTerm      真库无行
J1-2-detail-postEmployment 真库无行
J1-2-detail-severance      真库无行
J1-1-rows（审定表）         真库无行
J1-3-adjustment-rows        真库无行
```

⇒ 改为「**真库有非空载荷 + 在 entry 内 + 非 parent_duplicate + 单 sheet 单键组**」四项。

### 四候选对照

| 候选 | 真库 | 模板几何 | 归属 | 裁决 |
|---|---|---|---|---|
| ✅ **`J1-6-short-term`** | **3473 B**（全 J 最大） | `计提情况检查表J1-6` r=60 c=11 f=63 **裸 IF 0** merged=17 | entry 内 | **入选** |
| ❌ `J1-disc-soe-short-term` | 1325 B **且有真金额** | `附注披露信息（国有企业）` r=44 c=5 f=108 | entry 内 | 否决 |
| ❌ `J1-8-voucher-check` | 911 B，id 形态 `j1vc-imp-credit-1` 真实 | `检查表J1-8` r=58 c=16 f=19 | 🔴 **parent_duplicate** | 否决 |
| ❌ `J1-2-detail-*` | **空** | `明细表J1-2 ` 三分区 r=67 | entry 内 primary | 不满足硬标准 |

### 入选三条依据

1. **唯一同时满足四项硬标准**的候选。
2. 键组 **clean**（slice TK-4 `status=resolved`；id 形态 `acr-{ts}-{i}-{rnd}` 属安全族）
   ⇒ canary **不必先修身份缺陷**（对比 `J2-3-entries` 要先修 family_a、`J1-3-adjustment-rows` 要先修 family_b）。
3. 几何中等且 🔴 **裸 IF 0**（对比 `审定表J1-1 ` 56 / `与同行业对比分析表J1-5` 60）
   ⇒ `oo_crash_neutralization_fn` 在 canary 上是**空操作**，不会与中性化逻辑纠缠。

### 三条逆风（如实登记）

1. 🔴 **3473 B 载荷的金额字段全 0**：逐行实测 `baseAmount` / `rate` / `estimated` / `actual` / `diff`
   全 0，`baseName` / `baseIndex` / `diffReason` / `conclusion` 全空串；id 全是
   `acr-1784110937961-{i}-{rnd}`（**同一时间戳**）
   ⇒ 它是「`loadOrDefault()` 生成骨架后被 `persist()` 落库」的结果，**不是真实业务数据**
   ⇒ roundtrip 只能验**结构**不能验**数值** ⇒ SHALL **另造带金额的合成载荷**补一轮。
2. 🔴 **RD-5 的三边校验缺口必须在 canary 内先补**（`SHORT_TERM_DEFAULTS` 19 项 vs
   `计提情况检查表J1-6!A17..` 的全角/缩进差异）—— 否则 canary 的 representation
   会把错标签固化进契约。
3. 🔴 同 Tab 的 `J1-6-questions` 901 B 是 **AI 生成的 markdown 长文本**：
   实测 `["由于您未提供…（含 ### 标题与列表的整段中文）", "", "", "", ""]` **5 元素字符串数组**
   ⇒ representation SHALL 区分「**结构化行数组**」与「**自由文本数组**」两种 shape，
   不能用同一个 row-mapping 规则套。

### 否决披露层的理由（5 个叠加形态）

双变体（listed / soe）· 49 个硬编码 id · 🔴 **同 id 跨变体语义不同**（`st-7` 一边是「其他」
一边是「住房公积金」）· 第三条写路径写**另一张表**（`disclosure-notes/sync-from-workpaper`）·
与明细表**非行对行映射**（披露 12 行 ← 明细 20 行，含 **3 处两行合一** `J21+J22` / `J26+J27` /
`J30+J31` + **1 处手填** R23）
⇒ 首例不宜同吃 5 个最难形态（与 I 轮否决 I5 同理）。

### 否决 `J1-8-voucher-check` 的理由

它属 **parent_duplicate 子入口** `xlsx/j1/inspection/j1-tab-general-check`，
按 AC 1.6 复用父 entry 的 adapter、**不独立发布** contract / bundle / candidate / evidence。
🔴 但 SHALL 登记一条**与 slice 不符**的实测：slice 说该表「无身份字段、整表 JSON 数组按位置存」，
真库 911 B 载荷实测 `{"criteria":{…11 字段}, "occurrenceRows":[{"id":"j1vc-imp-credit-1", …}]}`
—— **有 `id` 字段且形态是「前缀+语义+序号」** ⇒ slice 该条声明须按现算修正。

---

## canary 端到端设计

### 契约 `j1.accrual_check_short_term.json`

```
entry_id        : xlsx/j1/gt-j1-employee-compensation
provider_id     : phase5_accrual_check_short_term          # phase5_* 范式，不照 pilot_*
source_ref      : { workbook_sha256: a6100d91202f4d06…,
                    sheet_name: "计提情况检查表J1-6" }        # 🔴 只此两字段，禁 wp_index（IC-12）
managed_table   : { item_id: "J1-6-short-term",
                    owner_module: "components/workpaper/j1/inspection/J1TabAccrualCheck.vue",
                    owner_constant: "KEYS",                 # KEYS.shortTerm
                    owner_declaration_kind: "component_local_object_constant",
                    identity_field: "id",
                    identity_generator_form: "`acr-${Date.now()}-${i}-${Math.random().toString(36).slice(2,5)}`",
                    identity_family: "C_safe_generated",    # JC-6
                    skeleton_constant: "SHORT_TERM_DEFAULTS",
                    skeleton_row_count: 19,                 # 现算，禁写死
                    skeleton_source_ref: "计提情况检查表J1-6!A17:A35",  # RD-5，19 行
                    skeleton_verdict: "ROW_COUNT_MATCH_BUT_10_LABEL_DIFFS",
                    skeleton_diff_kinds: { fullwidth_separator: 9, fullwidth_indent: 9,
                                           embedded_newline: 1 },   # 🔴 ①②叠加 9 处 + ③ 1 处
                    skeleton_fix_blocked_by: "business_confirmation" }
geometry        : { header_rows: [15, 16], section_title_row: 14,
                    data_rows: [17, 35],                     # 19 行，与 impl 一致
                    footer_rows: [],                         # 🔴 本 sheet 无 footer 合计行
                    second_region: { title_row: 37, header_row: 38, data_rows: [40, 47] },
                    trailing_text_from_row: 48,              # 「三、审计说明」起
                    effective_columns: 11,                   # == max_column
                    column_semantics: "A 项目 / C-E 计提基数[名称,金额,索引] / F 计提比例 / "
                                      "G 应提金额(=ROUND(D*F,2)) / H 实际计提数 / I 差异(=G-H) / "
                                      "J 差异原因 / K 结论" }
sibling_keys    : ["J1-6-post-employment", "J1-6-questions", "J1-6-conclusion"]
sibling_shapes  : { "J1-6-post-employment": "structured_row_array",
                    "J1-6-questions": "free_text_array",    # 🔴 5 元素，首元素是 AI markdown 长文
                    "J1-6-conclusion": "free_text_scalar" }
carrier         : { write: "shared_platform_persistence_adapter",       # JC-2
                    write_carrier_path: "composables/workpaper/useChecklistPersistence.ts",
                    write_client: "api",                                # 🔴 不是 http
                    write_client_import: "import { api } from '@/services/apiProxy'",
                    write_endpoint: "PUT /api/workpapers/{wp_id}/checklist-responses",
                    child_to_host: "props.saveImmediate → handleChildSave → persistence.saveDebounced",
                    read: "same_adapter_load_plus_render_config_snapshot_baseline" }
row_delete_api  : { kind: "identity", arity: 1, param_order: ["id"] }   # 🔴 JC-7 三元组
tb_publish_gate : { endpoint: "POST /api/workpapers/{wpId}/audit-determination/publish-to-tb",
                    site: "components/workpaper/j1/core/J1TabAdjudication.vue",
                    client: "api",
                    symbol_name_hit_count: 0 }              # 🔴 JC-3 的非空反证
payload_column_mode : "remark_only"                          # 真库 83 行 conclusion 全 NULL
payload_column_mode_status : "verified_in_live_db"
live_payload_note : "3473 B 但金额字段全 0 —— 骨架已落库业务未填；roundtrip 须另造带金额合成载荷"
live_payload_flag : "skeleton_persisted_no_business_values"
sheet_name_traps: ["尾部空格 2 张（审定表J1-1 / 明细表J1-2 ）",
                   "名中空格 6 张", "跨 sheet 引用带空格且单引号包裹"]
variant_axis    : { hit: true, groups: ["J1A", "J1-10"],
                    j1_10_note: "🔴 一码两义，按尾码定位须带 visible 过滤" }   # JC-11
defined_name_baseline : 0                                    # J1 册；J2 37 / J3 502 归下游 lane
bare_if_count   : 0                                          # 🔴 本 sheet 为 0（J1 册总 132）
oo_crash_neutralization_fn : g7_oo_crash_if_neutralize.neutralize_oo_crash_if_formulas  # per-file
uuid_column     : 12                                         # 有效列 11 + 1（max_column 11）
derived_total_keys : <现算 7 个，禁写死>                       # JC-18
cross_cycle_endpoint_dependency : ["POST /api/workpapers/{wpId}/d4/contract-ocr"]  # JC-17
```

### roundtrip 前置断言

1. **JC-3**：断言 canary 的写入只经声明的 `write_carrier`；🔴 同时断言 `J1TabAccrualCheck.vue`
   **不在**第二写路径的 7 文件清单里（它走 `props.saveImmediate` 汇入宿主适配器）。
2. **JC-2**：roundtrip 期间**冻结** `useAdjustmentCentralSync`（J1 侧 1 处），否则第二写入方污染比对。
3. **JC-18**：`derived_total_keys`（现算 7 个）排除在业务比对之外。
4. **JC-4/JC-5**：不改任何键名；🔴 特别是 `J1-2-detail-*` 三键（4 文件 5 处真源）与
   `J1-disc-*` 8 个拼接键，本 canary **一个都不碰**。
5. 🔴 **JC-12**：`计提情况检查表J1-6` 的数据区边界须按 **A 列非空**判定
   （表头 R15/R16 两级 · 数据区 **R17:R35** · 🔴 **本 sheet 无 footer 合计行**，R48 起是「三、审计说明」）；
   不得套 `明细表J1-2 ` 的「B 列 + 三 footer」口径 —— 套了会在 J1-6 上找不到 footer 而假红。
6. 🔴 **两轮 roundtrip**：第一轮用真库 3473 B（只验结构）· 第二轮用**合成带金额载荷**（验数值，
   须覆盖 `G=ROUND(D*F,2)` 与 `I=G-H` 两条派生列）。

### BP-10 的第一处 notice 挂载

挂载点 SHALL 在 `class="j1-dual-mode-bar"` 区块内；文案真源 SHALL 是 `workpaperEntrySyncNotice.ts`。
同时给 `el-segmented` 补 `v-if="dualMode.isOoAvailable.value"` 二级门控。
🔴 判据 SHALL **先按 toolbar class 截出区块再看** —— 全文件 grep `el-segmented` 会命中
`J1TabGeneralCheck.vue` 与 `J2TabAdjudication.vue` 两处 **Tab 内部分段控件**而误判。

---

## Property（JF-P）

| # | Property | 引用 |
|---|---|---|
| JF-P1 | 结构性结论现算零反驳（3 模板 digest / 4 orphan 行数 / 共享基类 65 行·边 29·J 贡献 3 / 适配器边 23 / 第二写路径 7 文件 8 站点 / 8 guessed key 各 0） | Req 1 |
| JF-P2 | 🔴 六处快照现算重算（manifest 155 / 契约 18 / 宽口径 34 差集 5 / Notice 48 / 行号 / `useJ2FormData` 已删） | Req 1 |
| JF-P3 | 🔴 判据按常量名·形态·端点定位，**禁写死行号**；变异「用 slice 行号锚定」SHALL 打红 | Req 1.3 |
| JF-P4 | 无 pilot（逐文件读 `review.entry_id`）· 无 J0（两函数返 None）· 模板恰 3 本 | Req 2 |
| JF-P5 | J 完全自闭（J 键无非 J 消费 ∧ J 文件无非 J 键）；🔴 但端点跨循环复用命中 1 处 | JC-17 |
| JF-P6 | 🔴 扫描误报复核：`附注披露信息（国有企业）!B29:E29` 命中 4 格但判定**非缺陷** | FC-5 重裁 |
| JF-P7 | 载体族第三种落表；两条对照反证（H 口径 / I 口径）SHALL 分别假红 | JC-2 |
| JF-P8 | 🔴 六类端点现算落表；`publishToTb` 符号名 0 vs 端点 1 的非空反证 | JC-3 |
| JF-P9 | TB 发布门 **1/1 有**；只走显式端点 + 二次确认；禁 watch/onMounted/debounce | JC-3 / Req 8.5 |
| JF-P10 | `useAdjustmentCentralSync` **2/3**（J3 无）；OCR 在 composable 层命中 | JC-3 / Req 3.6-3.7 |
| JF-P11 | 一表三键派生 == 实测；身份字段是 `id` | JC-4 |
| JF-P12 | 🔴 BP-11 **4 文件 5 处**同时比对；变异「只改前缀」SHALL 打红 | JC-4 |
| JF-P13 | 🔴 披露层 **8 个拼接键**由笛卡尔积展开后验；完整字面量 grep SHALL 抓不到 | JC-5 |
| JF-P14 | 🔴 三命名空间分清（`J1-disc-*` 8 / `J1-disclosure-*` 10 / 小写 AI section 2）；混用 SHALL 打红 | JC-5 |
| JF-P15 | 披露层 severance 有 section-id 无持久化键，已登记 | JC-5 |
| JF-P16 | 行身份五族现算（A 1 / B 6 / C 3+1 / D 3 / E 0）；C·D 两族**不被点名** | JC-6 |
| JF-P17 | 🔴 family_c 判别式放宽后仍排除 `genId(idx)` 那种 `??` 左支给下标的形态 | JC-6 |
| JF-P18 | 🔴 披露层 49 个硬编码 id **登记但不判缺陷**；报成位置化 SHALL 打红 | JC-6 |
| JF-P19 | 披露层四条真实风险逐条（同 id 跨变体语义不同 / 行数不同 / 新增行形态不一 / `s-${Date.now()}` 无随机串） | JC-6 |
| JF-P20 | entry/non-entry 缺陷维度 **2 + 5 = 7**，两组数分别现算分别登记 | JC-6 |
| JF-P21 | removeRow **8 处 / 4 形态**；契约用 `{kind, arity, param_order}`；与 H/I 不复用签名断言 | JC-7 |
| JF-P22 | 五条 RD 三边比对（RD-1 20/20 正例锚点 · RD-2 2/8 · RD-3 否定式 · RD-4 双向锁死 · 🔴 RD-5 新增） | JC-8 |
| JF-P23 | 🔴 RD-5 三类差异分开计数（分隔符+缩进 9 / **换行符 1**）；同 sheet 两分区缩进字符不同 | JC-8 |
| JF-P24 | 🔴 禁全角/半角与缩进归一化；变异「比对前 NFKC」SHALL 打红 | JC-9 |
| JF-P25 | sheet 名三类空格禁 strip（尾部 2 / 名中 6 / 跨 sheet 引用带空格+单引号） | JC-10 |
| JF-P26 | 变体轴 **2 组**；🔴 `J1-10` 一码两义须带 visible 过滤；只按尾码匹配 SHALL 打红 | JC-11 |
| JF-P27 | 跨循环程序表串册 2 处（`L1A-原` 🔴 slice 漏记 + `L2A` hidden）已登记 | JC-11 |
| JF-P28 | footer 三形态（跳跃/加法/连续）分别标；照单一口径验 SHALL 假红 | JC-12 |
| JF-P29 | 🔴 幽灵行 R45 显式排除；按「有公式即业务行」会把 8 行算成 9 行而打红 | JC-12 |
| JF-P30 | definedName 基线 `{0, 37, 502}` + **断链数 {—, 30, 479}** + 断言不增长 + 不删 | JC-13 |
| JF-P31 | 裸 IF per-file `{132, 12, 0}` 总 144；整册统一挂 SHALL 打红 | JC-14 |
| JF-P32 | 🔴 BP-10 无声失败三要素（notice 0 / `isOoAvailable` 0 / 基类静默 return）；按 toolbar class 定位 | JC-15 |
| JF-P33 | 🔴 JD-6 判据改「差集**包含**生成文件」+ 现算清单；窄口径的奇数双引号规则保留 | JC-16 |
| JF-P34 | `derived_total_keys` 现算 **7**，禁写死；正则覆盖 `-total-` 中置形态 | JC-18 |
| JF-P35 | 键全集现算 **160**，禁写死 | JC-18 |
| JF-P36 | prefill 四处缺陷逐条登记（缺尾部空格 / 空 cells / 引用不存在 sheet / J3 无审定表） | JC-19 |
| JF-P37 | Property 3/20/69 的空分母与全负向分母**不宣称通过**；Property 70 真验 | JC-20 |
| JF-P38 | 🔴 七项「查过且为 0」一律写「现算 0 且不是漏扫」，并**复用已有变异脚本**逐条证明非空跑 | JC-20 |
| JF-P39 | canary 硬标准改四项口径；四候选裁决与三条逆风如实登记 | Req 8 |
| JF-P40 | canary 几何现算（表头 R15/R16 · 数据区 R17:R35 · **无 footer** · 有效列 11 · UUID 12 · 裸 IF 0） | canary |
| JF-P41 | `J1-6-questions` 是 free_text_array（5 元素）；与 structured_row_array 用不同 shape 规则 | canary |
| JF-P42 | 🔴 两轮 roundtrip（真库 3473 B 验结构 + 合成带金额载荷验 `G=ROUND(D*F,2)` / `I=G-H`） | canary |
| JF-P43 | 零回归基线**现算**（契约目录 / 注册集 / adapter 成员），禁写死 | Req 9.3 |
| JF-P44 | 🔴 3 册 ↔ 1 entry **单射不满射**：验单射 + 每个 null 有 `excluded_reason` + 有主那条命中 entry_id | FC-3 重裁 |
| JF-P45 | `J1A`/`J2A`/`J3A` 无独立索引条目 · `J0` 返 None · 🔴 `J2-5..J2-10`/`J3-3..J3-10` 解析返册但 sheet 不存在 | template_resolution_audit |

🔴 **空分母纪律（JC-20）**：JF-P5 / JF-P38 / JF-P44 里所有「为 0」的断言 SHALL 写成
「现算等于 0 **且不是漏扫**」，**不宣称该维度通过**；
JF-P37 的 Property 3/20/69 三条明确标 `not_claimed_passing`。
