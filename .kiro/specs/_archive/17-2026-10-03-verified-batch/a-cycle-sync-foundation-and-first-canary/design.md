# A 循环双向回写地基与首张 canary — 设计

## 概述

本 spec 是 A 循环（报表/调整）三份 sync spec 的**地基层**：一次性裁定 AC-1 ~ AC-48 共同判据、锁定 20 条 entry 的事实基线、落地首张 canary（`xlsx/gt-a51-cashflow-audit`）。两份 lane spec 只引用 AC 编号。

**权威事实来源**（全部现算校验过，禁二次推演）：

| 来源 | 路径 | 体量 | 冻结 |
|---|---|---|---|
| abcs slice | `backend/data/workpaper_sync_abcs_cycle_manifest_slice.json` | **750,744 B** | Task 57（2026-08-31） |
| 删除清册 | `backend/data/workpaper_sync_abcs_cycle_deletion_plan.json` | 27,566 B | 同上 |
| 既存守卫 | `backend/tests/workpaper_sync/test_task57_abcs_and_shared_migration.py` | 2472 行 / 17 类 / 130 test | — |

🔴 **本轮四个结构性「第一次」**：① slice 的 `cycle` 是**复合值**（`"A/B/C/S + cross_cycle_shared"`）② 权威册**大量是 docx**（A 域 16/20）③ `excluded_pilot_entry_count` **首次非 0** ④ **Property 22 首次拿到非空分母**。

## 三份 spec 分工

| # | 目录 | entry | 主题 | Property 前缀 |
|---|---|---|---|---|
| 1 | `a-cycle-sync-foundation-and-first-canary` | `xlsx/gt-a51-cashflow-audit` | 地基 + AC 裁决 + canary 闭环 | **AF-P** |
| 2 | `a-class-docx-authority-workbook-lanes` | **16 条 docx 册 entry** | docx 权威册（BP-9）+ 合并单元格定位 | **AG-P** |
| 3 | `a-class-runtime-sheetname-and-carrier-exceptions` | `xlsx/gt-a177-independence-declaration` · `xlsx/gt-a3-consolidation-console` · `xlsx/gt-a38-goodwill-impairment` | 运行时册名 + 无开关 + 动态列缺陷 | **AH-P** |

**切分依据**（探针穷举，非凭感觉）：公共 BP 6 项对切分无影响；区分项为 BP-6{a38} · BP-8{a177} · BP-9{16 条} · BP-10{a3-console} · BP-11{a91}。

🔴 **决定性理由 —— BP-9 集合与 docx 集合是同一分界**：现算 `BP-9 集合 == docx 集合` 为 **`True`**（16 == 16）⇒ 按 docx 轴切等价于按 BP-9 轴切。穷举结果：**横跨数 = 0 的方案恰 4 个**，foundation 必须取非 docx 的 4 条之一，且全部呈 `1 + 16 + 3` 结构；其余方案横跨 ≥ 1。

**归属校验**：
- lane2 16 = GRP-01 **13** + GRP-02 **1**（a115）+ GRP-03 **1**（a112）+ GRP-10 **1**（a91）
- lane3 3 = GRP-01 **1**（a177）+ GRP-03 **2**（a3-console / a38）
- foundation 1 = GRP-01 **1**（a51）
- 合计 `1 + 16 + 3 = 20` ✓ · 区分项 BP **全部内聚**（BP-9 与 BP-11 → lane2；BP-6 / BP-8 / BP-10 → lane3）⇒ **横跨 0**

**Property 前缀选择**：用 AF-P / AG-P / AH-P，避开已用的 MF-P / MA-P / MB-P（M 轮）与 NF-P / NA-P / NB-P（N 轮），也避开本轮 slice 已占用的 **AD-1 ~ AD-12**（`abcs_form_differences`）。

## 20 条 entry 事实基线

| entry_id | wp_code（双 pattern） | group | channel | 册格式 | 载体 / switch | BP 数 |
|---|---|---|---|---|---|---|
| `xlsx/gt-a101-governance-communication` | A10-1 / A101G | GRP-01 | checklist | docx | segmented / redeemable | 7 |
| `xlsx/gt-a111-subsequent-events-inquiry` | A11-1 / A111S | GRP-01 | checklist | docx | segmented / redeemable | 7 |
| `xlsx/gt-a112-dual-checklist` | **A1-12** / A112D | GRP-03 | field_ovr | docx | segmented / redeemable | 7 |
| `xlsx/gt-a115-disclosure-checklist` | **A1-15** / A115D | GRP-02 | 两通道 | docx | segmented / redeemable | 7 |
| `xlsx/gt-a121-legal-confirmation` | A12-1 / A121L | GRP-01 | checklist | docx | segmented / redeemable | 7 |
| `xlsx/gt-a171-audit-summary` | A17-1 / A171A | GRP-01 | checklist | docx | segmented / redeemable | 7 |
| `xlsx/gt-a1721-kam` | A17-2-1 / A1721K | GRP-01 | checklist | docx | segmented / redeemable | 7 |
| `xlsx/gt-a173-consultation-record` | A17-3 / A173C | GRP-01 | checklist | docx | segmented / redeemable | 7 |
| `xlsx/gt-a1731-consultation-execution` | A17-3-1 / A1731C | GRP-01 | checklist | docx | segmented / redeemable | 7 |
| `xlsx/gt-a174-disagreement-record` | A17-4 / A174D | GRP-01 | checklist | docx | segmented / redeemable | 7 |
| `xlsx/gt-a176-closing-meeting` | A17-6 / A176C | GRP-01 | checklist | docx | segmented / redeemable | 7 |
| `xlsx/gt-a177-independence-declaration` | **A177I**（单 pattern） | GRP-01 | checklist | **无册** | segmented / redeemable | 7 |
| `xlsx/gt-a181-regulatory-submission` | A18-1 / A181R | GRP-01 | checklist | docx | segmented / redeemable | 7 |
| `xlsx/gt-a182-regulatory-communication` | A18-2 / A182R | GRP-01 | checklist | docx | segmented / redeemable | 7 |
| `xlsx/gt-a271-it-audit-memo` | A27-1 / A271I | GRP-01 | checklist | docx | segmented / redeemable | 7 |
| `xlsx/gt-a3-consolidation-console` | A3-3 / **A3C** | GRP-03 | field_ovr | **xlsx** | **no_carrier / no_switch** | 7 |
| `xlsx/gt-a38-goodwill-impairment` | A3-8 / A38G | GRP-03 | field_ovr | **无册** | segmented / redeemable | 7 |
| **`xlsx/gt-a51-cashflow-audit`** | A5-1 / A51C | GRP-01 | checklist | **xlsx** | segmented / redeemable | **6** |
| `xlsx/gt-a81-other-info-representation` | A8-1 / A81O | GRP-01 | checklist | docx | segmented / redeemable | 7 |
| `xlsx/gt-a91-deficiency-letter` | A9-1 / A91D | **GRP-10** | checklist | docx | segmented / redeemable | **8** |

算术：**20 条** = docx **16** + xlsx **2** + 无册 **2** ✓ · group `15 + 1 + 3 + 1 = 20` ✓ · OO 挂点 **20**（`mount_count` 全 1）· segmented **19** · mode 门控 **19** · `migration_state` 全 `legacy_fake_bidirectional` · `capability` 全 **null** → target 全 `bidirectional` · `adapter_id` / `authority_model` / `instrumentation_candidate` / `scenario_profile_id` 全 **null** · `html_counterpart_verdict` 全 `exists` · `capability_verdict_stage` 全 `step_4_blocked_by_step_3_result_exists`

🔴 **wp_code 第二形态的构造规则不统一**（判据禁按规则推导，须逐条读）：`A10-1`→`A101G`（去连字符 + 首字母）· `A1-12`→`A112D` · `A17-2-1`→`A1721K`（去两个连字符）· 但 **`A3-3`→`A3C`**（少了一个 3，**打破规则**）· `A177I` **本身就是第二形态**（无第一形态的连字符版）。
🔴 **entry_id 到 wp_code 的切分规则也不统一**：`gt-a101`→`A10-1` 但 `gt-a112`→**`A1-12`**、`gt-a115`→**`A1-15`**（同样 3 位数字两种切法）。

## AC-1 ~ AC-48 共同裁决对照表

判定图例：✅ 沿用 · ⚠️ 变形（方向不变但锚点/口径须改）· ❌ 不适用（空分母）· 🔁 反转（N 轮结论在 A 被证伪）· ➕ 新增（A 独有）

| AC | 主题 | NC 基准 | 判定 | A 侧现算分母 | 归属 |
|---|---|---|---|---|---|
| AC-1 | slice 范围与 manifest 分歧 | NC-1 | ⚠️ | cycle **复合值** / 46 切 **20** | foundation |
| AC-2 | 载体族并存 | NC-2 | ⚠️ | segmented **19** + no_carrier **1**；per-entry composable **0** | foundation |
| AC-3 | 端点字面量须认反引号 + 剥注释 | NC-3 | ⚠️ | publish-to-tb **0**（空）· health **13** | foundation |
| AC-4 | 确认门独立存在 | NC-4 | ✅ | confirm **7** / 3 文件 | foundation |
| AC-5 | strict 域须含小写前缀分支 | NC-5 | ✅ | 148（生产 79）/ 漏 **34** | foundation |
| AC-6 | 行身份正面样板 | NC-6 | ⚠️ | E 族 **21** / 8 文件 | foundation |
| AC-7 | `removeRow` 签名族 | NC-7 | ❌ | **0**（宿主内无 removeRow） | — |
| AC-8 | 位置化族分类 | NC-8 | ⚠️ | C 族 **64** 为主；A 族 **0** | foundation |
| AC-9 | `definedName` 断链登记 | NC-9 | ⚠️ | A3-3 **261/190** · A5-1 22/14 | foundation |
| AC-10 | sheet 名禁归一化 | NC-10 | ⚠️ | 跨循环码 **F6-10** | foundation |
| AC-11 | 扫描口径差须登记 | NC-11 | ✅ | 6 组口径差 | foundation |
| AC-12 | notice 接线，tooltip 不算 | NC-12 | ✅ | A 域 **0** / 全域 41 | foundation |
| AC-13 | 门控判据 | NC-13 | 🔁 | **祖先链 × 递归 v-else 回溯**；N 口径假阴 **5** | foundation |
| AC-14 | `derived_total` 双正则 | NC-14 | ⚠️ | TAIL **4** : MID **2** | foundation |
| AC-15 | `item_id` / wp_code 命名轴 | NC-15 | ⚠️ | 双 pattern 19 + 单 1；切分规则不统一 | foundation |
| AC-16 | localStorage mode 分区 | NC-16 | ❌ | 仅 `'token'` 1 处，**无 mode 键** | — |
| AC-17 | 「合计漏加小计」双条件 | NC-17 | ❌ | 标签 13 处**全在首列**；xlsx 仅 2 本 | — |
| AC-18 | canary 判据 | NC-18 | 🔁 | **第二次偏离**（唯一命中是 E2E seed） | foundation |
| AC-19 | 跨循环键 + 跨 entry 污染 | NC-19 | ⚠️ | 污染 **0**（28/28 对齐）；A 被 N5 引用 | foundation |
| AC-20 | 空分母纪律 + 变异证明 | NC-20 | ✅ | 结构性零 **23** 项 | foundation |
| AC-21 | 跨册复制残留 | NC-21 | ⚠️ | `F6-10` 混入 A3-3 sheet 名 | foundation |
| AC-22 | 科目性质四分 | NC-22 | ❌ | **A 类非科目底稿，无借贷方向** | — |
| AC-23 | `SHEET_MAP` 常量映射 | NC-23 | ❌ | A 域无此形态 | — |
| AC-24 | 历史 sheet 过滤 | NC-24 | ❌ | A 域册名含「原底稿/历史」**0** | — |
| AC-25 | 已归档 spec 边界 | NC-25 | 🔁 | **35 份且 6 份未 100%**（N 是 16 份全绿） | foundation |
| AC-26 | 脏字面量登记 | NC-26 | ⚠️ | 占位符五形态 + **`20l×年`** | foundation |
| AC-27 | 「原底稿」空格形态穷举 | NC-27 | ❌ | 空分母（同 AC-24） | — |
| AC-28 | `resolveProcedureSheetKey` 接入 | NC-28 | 🔁 | **整段缺失**（M 缺 4 / N 完备 / A 无分支） | foundation |
| AC-29 | 行数口径 + 上游计数 | NC-29 | ✅ | slice 自相矛盾 **4** 处 | foundation |
| AC-30 | `transport_key_resolution` | NC-30 | ❌ | **abcs slice 无此节** | — |
| AC-31 | `parent_duplicate` 条件节 | NC-31 | ❌ | in-scope **0**（**与 N 反转**，N 触发 4 条） | — |
| AC-32 | wp_code 与 Excel A1 引用同形 | NC-32 | ❌ | 超列引用 **0**（A 码带连字符不成合法引用） | — |
| AC-33 | slice schema 校验器 | NC-33 | ⚠️ | `residual_inconsistency` **null**；走追加节 | foundation |
| AC-34 | `conclusion` 是主载荷 | NC-34 | ✅ | 非空 **24** > remark **4**（连续第二轮） | foundation |
| AC-35 | 超宽表 + 幽灵列 | NC-35 | ❌ | xlsx 最宽 **33** 列，无 256 列形态 | — |
| AC-36 | footer 形态 | NC-36 | 🔁 | **禁用 openpyxl**；中文/英文双语 footer | foundation |
| AC-37 | prefill 分母 | NC-37 | ✅ | **11** 命中 / 2 文件 | foundation |
| AC-38 | docx 权威册按 format 分流 | — | ➕ | **16** 条（BP-9 == docx 集合） | foundation（判据）+ lane2（数据） |
| AC-39 | docx 合并单元格定位去重 | — | ➕ | `merged_refs` 最高 **99.5%** | foundation（判据）+ lane2 |
| AC-40 | 公式行数超出数据行数致除零 | — | ➕ | A3-3 AE 列 **10 : 1** | foundation（判据）+ lane3 |
| AC-41 | mode 载体二分（中文标签作值） | — | ➕ | 形态 1 **17** / 形态 2 **2** | foundation |
| AC-42 | 持久化在 import 闭包（深度 3） | — | ➕ | 宿主内 `/checklist-responses` **0** | foundation |
| AC-43 | entry_groups 二维分组可复算 | — | ➕ | **13 组 / 9 家族 / 4 通道** | foundation |
| AC-44 | 册↔entry 双射降级为单射 | — | ➕ | A 目录 **97** 本只 **18** 归属 | foundation |
| AC-45 | 单宿主多 componentType | — | ➕ | BP-11 **1** 条（a91） | foundation（判据）+ lane2 |
| AC-46 | BP-6 归因更正 | — | ➕ | `'A3-8'` 纯码**也**解析为 None | foundation（判据）+ lane3 |
| AC-47 | slice 自相矛盾 4 处 | — | ➕ | 4 处（两个来源都有错） | foundation |
| AC-48 | Property 22 首次非空分母 | — | ➕ | 站点 **7** / label-as-key **3** / PARTIAL | foundation（判据）+ lane3 |

**编号完整性（逐条数表格得出，禁凭印象）**：AC-1 ~ AC-48 连续无缺号、无重号，判定分布 **8 + 13 + 5 + 11 + 11 = 48** ✓

| 判定 | 条数 | 编号 |
|---|---|---|
| ✅ 沿用 | **8** | AC-4 / 5 / 11 / 12 / 20 / 29 / 34 / 37 |
| ⚠️ 变形 | **13** | AC-1 / 2 / 3 / 6 / 8 / 9 / 10 / 14 / 15 / 19 / 21 / 26 / 33 |
| 🔁 反转 | **5** | AC-13 / 18 / 25 / 28 / 36 |
| ❌ 不适用 | **11** | AC-7 / 16 / 17 / 22 / 23 / 24 / 27 / 30 / 31 / 32 / 35 |
| ➕ 新增 | **11** | AC-38 ~ AC-48 |

🔴 **❌ 11 条是历轮最多**（N 轮仅 1 条、M 轮 5 条）—— 根因是 A 类底稿的业务性质与 D~N 的科目类底稿**根本不同**（报表/沟通/声明类，无科目借贷、不回写试算表、权威册是 Word）。这不是「判据质量下降」，而是**判据体系首次遇到异质域**。

## 关键判据的可执行形式

### AC-13 · 门控判据（两次口径迭代已实证，禁照抄中间版本）

```
# ❌ 版本 1（N 轮口径）：只看挂点自身属性 → 得 14，假阴 5
# ❌ 版本 2（中间版）：挂点自身 + 挂点自身的 v-else 链头 → 祖先命中只得 3
# ✅ 版本 3（最终）：
def effective_conds(node, siblings_at_same_level):
    c = [v for k, v in node.attrs.items() if k.startswith((':', 'v-'))]
    if 'v-else' in node.attrs or 'v-else-if' in node.attrs:
        for prev in reversed(siblings_at_same_level):
            if 'v-if' in prev.attrs:
                c.append(prev.attrs['v-if']); break      # 🔴 链头回溯
    return c

gated = any(MODE.search(c)
            for c in effective_conds(oo_mount) + sum(
                (effective_conds(anc) for anc in oo_mount.ancestors), []))   # 🔴 祖先也回溯
MODE = re.compile(r'\b\w*[Mm]ode\b')
```
断言：OO 挂点 **20** · segmented **19** · **有 mode 门控 19** · 无门控恰 **1**（a3-console）。变异证明：版本 1 在同一批文件上应得 14（差 5），版本 2 应得祖先命中 3。

### AC-38 / AC-39 · docx 册按 format 分流 + 合并单元格去重

```
fmt = entry['template_ref']['workbook_format']
if fmt == 'xlsx':   openpyxl.load_workbook(p, data_only=False)   # 2 条
elif fmt == 'docx': docx.Document(p)                             # 16 条
else:               declare_empty_denominator(entry)             # 2 条

# 合并单元格：同一 <w:tc> 会被多个 cell 对象引用
seen = set()
for r in table.rows:
    for c in r.cells:
        if id(c._tc) in seen: continue      # 🔴 去重，否则 a115 会把 3174 格算成 3174 个独立位置
        seen.add(id(c._tc)); yield c
```
断言：openpyxl 对 docx 抛 `InvalidFileException`（反证）· `merged_refs` a115 **3159/3174 = 99.5%**。

### AC-40 · 公式行数超出数据行数致除零（A 域新族）

```
for col in formula_columns(sheet):
    rows_with_formula = [r for r in col if has_formula(r)]
    for r in rows_with_formula:
        for ref in referenced_cells(sheet[col][r]):
            if is_empty(ref) and in_denominator(ref):
                report(col, r, ref)          # 分母引用空格 ⇒ 恒 #DIV/0!
```
断言：`A3-3` 的 `AE6~AE15` 全 10 行有 `=(AB#+AC#+AD#)/(L#*J#)`，而 `AB/AC/AD` 与 `L/J` **只 r6 有值** ⇒ AE7~AE15 恒 `#DIV/0!`，反向分母 **10 : 1**。

### AC-36 · footer 必须读 raw XML

```
# ❌ ws.oddFooter —— openpyxl 报 "Cannot parse header or footer so it will be ignored" 后静默返回空
z = zipfile.ZipFile(xlsx_path)
for n in [x for x in z.namelist() if re.match(r'xl/worksheets/sheet\d+\.xml$', x)]:
    x = z.read(n).decode('utf-8')
    has_container = '<headerFooter' in x
    odd = re.findall(r'<oddFooter>(.*?)</oddFooter>', x, re.S)
```
断言三态：**2 有内容** + **7 有容器无 `oddFooter`** + **4 无容器** = 13 ✓；内容为 `第 &P 页，共 &N 页`（中文）与 `Page &P`（英文，无 `&N`）。

### AC-42 / AC-43 · 分组键二维复算

```
# 第一维 componentType 家族：从 htmlRendererRegistry.ts 按「模块边」匹配
#   🔴 registry 有两种 component: 写法（提升的 const / 内联 defineAsyncComponent）
#   只认一种会漏 94/211 条 ⇒ 须把 componentType: 与紧随 component: 解析成磁盘路径再比 host_path
# 第二维 persistence_channel：现读宿主 import 闭包（深度 3）里的真实 HTTP 站点
CHANNELS = ('/checklist-responses', '/api/workpapers/field-overrides', '/custom-cells')
```
断言：13 组 / 9 家族 / 4 通道 · `componentType:` 行数 **211** · A 域 GRP-01 **15** / GRP-02 **1** / GRP-03 **3** / GRP-10 **1**。
🔴 只扫宿主文件会让 `/checklist-responses` 命中 **0**（实测），必须走闭包。

## 模板层缺陷台账（只登记不修改）

| # | 位置 | 形态 | 性质 | 反向分母 | 归属 |
|---|---|---|---|---|---|
| T-1 | `A3-3` / `结构化主体纳入合并范围判断F6-10` **AE7~AE15** | `=(AB#+AC#+AD#)/(L#*J#)` 而 AB/AC/AD 与 L/J 只 r6 有值 | 🔴 真缺陷，恒 `#DIV/0!` | **10 : 1** | lane3 |
| T-2 | `A3-3` sheet 名 | 码是 **`F6-10`** 而 wp_code 是 `A3-3` | 🔴 跨循环码混入（比 N 的 `O1A` 更严重：不同字母体系） | — | lane3 |
| T-3 | `A3-3` definedName | **261 / broken 190（73%）**，含 `_.dbf` · `_1固定资产数据库_筛选打印` · `_2其他资产_开办费除外_明细表` · `_3余额表_一级_.dbf` | 🔴 dBase/Foxpro 时代旧底稿残留，规模是 N 全域的 4 倍 | 261 : 190 | lane3 |
| T-4 | `A5-1` definedName | 22 / broken 14（`XREF_COLUMN_*` · `XRefCopy*` · `[1]Breakdown!#REF!` · `'[2]2004'!#REF!`） | 与 N 域**完全同源** | 22 : 14 | foundation |
| T-5 | `A9-1向管理层通报内部控制缺陷-沟通函.docx` P2 | **`20l×年12月31日`** | 🔴 小写字母 `l` 冒充数字 `1` | — | lane2 |
| T-6 | `A1-15 …核对表20141021.docx` | 934 行巨表 / merged_refs **99.5%** | 定位与性能风险 | 3174 : 3159 | lane2 |
| T-7 | `A18-1 …的函.docx` / `A9-1…docx` | **0 表格** / 2 个 1x1 表 | 纯信函型，「有表格」判据必假 | 16 : 2 | lane2 |
| T-8 | `A17-3 业务咨询记录…docx` 首段 | `【参考格式，但至少包括以下四方面要素…` | 指引文字占据标题位 | — | lane2 |
| T-9 | 16 本 docx | 示例公司名两种（`XX股份有限公司` vs `ABC公司`） | 文案不统一 | — | lane2 |
| T-10 | `A3-8` | **无权威册**（`'A3-8'` 纯码也解析为 None） | BP-6 归因须更正 | — | lane3 |
| T-11 | `GtA38GoodwillImpairment.vue#L154` | `v-for="(_, i) in 5"` + `key="i"` | 🔴 写死列数 + 裸下标作 key（Property 22） | 7 : 3 | lane3 |

🔴 **T-1 与 N 轮的超列引用族（NC-32）不同型**：那里是「引用了超出 max_column 的列」，这里是「公式行数超出数据行数」；两者都导致静默错值，但扫描器完全不同。

## 口径差与已证伪项

| 项 | 上游声明 | 本轮现算 | 差因 |
|---|---|---|---|
| B 域 entry 数 | `letter_bucket_counts` **11** | **10** | 未扣 pilot B60 |
| C 域 entry 数 | `description` **2** | **1** | description 错 |
| 跨循环共享 entry 数 | `description` **4** | **5** | description 错 |
| 持久化通道数 | `description` **5** | **4** | 与 `counters.channels` 一致者为真 |
| 全域 `*DualMode*.ts` | 正文 **115** | **114**（同节字段值） | slice 节内自相矛盾 |
| `_should_skip_historical_sheet` 消费方 | M 轮记 **2** | **3** | 须现算 |
| A 域 footer | 我第一版读出「全空」 | **三态（2/7/4）** | 🔴 openpyxl 解析失败而非事实为空 |
| `modeOptions` 字面量 | 我第一版读出「4 值混排」 | **label/value 分离的对象数组** | 🔴 未区分字符串数组与对象数组 |
| 门控命中数 | 我第一版 3 / 第二版 14 | **19** | 🔴 须递归回溯祖先的 v-else 链头 |

🔴 后三行是**我自己在本轮犯的口径错误**，已现读源码更正并保留对照 —— 它们构成 AC-20「结构性零须配变异证明」的直接案例。

## Property 清单（AF-P1 ~ AF-P36）

前缀 **AF-P** 为本 spec 专属，lane2 用 **AG-P**、lane3 用 **AH-P**。所有现算值禁写死在断言里。

| # | 断言 | 现算值 | 关联 AC |
|---|---|---|---|
| AF-P1 | slice `cycle` 是复合值，「单字母」判据必假红 | 复合 | AC-1 |
| AF-P2 | 46 条按首字母分域 = A20/B10/C1/S10/无码5 | 46 | AC-1 |
| AF-P3 | A 域 20 条全名逐一吻合 | 20 | AC-1 |
| AF-P4 | slice 自相矛盾 4 处已登记 | 4 | AC-47 |
| AF-P5 | 域归属按 `wp_code_patterns` 现算，非按 entry_id 猜 | 1 反例（c-control-test） | AC-1 |
| AF-P6 | `excluded_pilot_entry_count` 首次非 0 | 1 | AC-1 |
| AF-P7 | in-scope parent_duplicate = 0，条件节不触发（与 N 反转） | 0 vs N 的 4 | AC-31 |
| AF-P8 | publish-to-tb 在 A 域 = 0（空分母，首次） | 0 | AC-3 |
| AF-P9 | `trial-balance/writeback` = 0（反向断言仍有效） | 0 | AC-3 |
| AF-P10 | 宿主内 `/checklist-responses` = 0 ⇒ 须走 import 闭包 | 0 | AC-42 |
| AF-P11 | 持久化通道 4 种，A 域涉 3 种 | 4 / 3 | AC-43 |
| AF-P12 | 确认门 7 命中 / 3 文件，独立存在 | 7 | AC-4 |
| AF-P13 | OO 挂点 20 · segmented 19 · mode 门控 19 | 20/19/19 | AC-13 |
| AF-P14 | 门控判据须递归回溯祖先 v-else 链头；两中间版本对照 | 19 vs 14 vs 3 | AC-13 |
| AF-P15 | 无门控恰 1 条（a3-console），与 `no_switch_at_all` 吻合 | 1 | AC-2 |
| AF-P16 | 开关裁决 42 redeemable + 0 inert + 4 no_switch；A 域 19+1 | 0 inert | AC-2 |
| AF-P17 | mode 形态 1（中文标签作值）17 条 · 形态 2（label/value 分离）2 条 | 17 / 2 | AC-41 |
| AF-P18 | `'onlyoffice'` 字面量 = 0（OO 值是 `'docx'`） | 0 | AC-41 |
| AF-P19 | localStorage 无 mode 分区键（仅 `'token'`） | 1 | AC-16 |
| AF-P20 | canary 五项替代判据全中且全域唯一 | 5/5 | AC-18 |
| AF-P21 | canary 判据三轮轨迹（M 偏离→N 收回→A 再偏离）已写明 | 3 轮 | AC-18 |
| AF-P22 | A 域真库 28 行，与 20 条 entry 交集仅 1 且是 E2E seed | 28 / 1 | AC-18 |
| AF-P23 | `conclusion` 非空 24 > `remark` 4（NC-34 连续第二轮成立） | 24 / 4 | AC-34 |
| AF-P24 | AI 会话行按白名单排除（第三轮出现，261 B） | 1 | AC-18 |
| AF-P25 | 跨 entry 污染 0（28/28 对齐），变异证明取 L/N 的 G8 | 0 | AC-19 |
| AF-P26 | 权威册 18/18 sha256+size match，交付后仍 match | 18 | AC-44 |
| AF-P27 | A 目录 97 本 = xlsx 65 + docx 32，与 AD-3 逐值吻合 | 97 | AC-44 |
| AF-P28 | 册↔entry 双射降级单射：只 18 归属，79 本须写 excluded_reason | 18 / 79 | AC-44 |
| AF-P29 | format 分流：docx 走 python-docx；openpyxl 对 docx 抛异常（反证） | 16/2/2 | AC-38 |
| AF-P30 | footer 读 raw XML，三态 2/7/4 = 13 | 13 | AC-36 |
| AF-P31 | xlsx 公式格 120（63+57）· 带 fx 7 · `data_only` 反证 0 | 120 | AC-38 |
| AF-P32 | 结构性零 23 项各附变异证明 | 23 | AC-20 |
| AF-P33 | 分组 13 组 / 9 家族 / 4 通道 · registry 211 行 | 13 / 211 | AC-43 |
| AF-P34 | 归档 spec 35 份，6 份未 100%（7 条欠账）· 4 份 0/0 | 35 / 6 / 4 | AC-25 |
| AF-P35 | `resolveProcedureSheetKey.ts` 91 行且无 A 分支（三轮三态） | 0 分支 | AC-28 |
| AF-P36 | Property 22 分母首次非空，verdict PARTIAL，A 域占 1 条 | 7/3/1 | AC-48 |

**编号完整性**：AF-P1 ~ AF-P36 连续 **36** 条，无缺号无重号，每条关联至少一个 AC 编号。

## 算术自检（交付前必跑）

| 量 | foundation | lane2 | lane3 | 合计 | 权威值 |
|---|---|---|---|---|---|
| entry 条数 | 1 | 16 | 3 | **20** | 20 ✓ |
| docx 册 | 0 | 16 | 0 | **16** | 16 ✓ |
| xlsx 册 | 1（A5-1） | 0 | 1（A3-3） | **2** | 2 ✓ |
| 无册 | 0 | 0 | 2（a177/a38） | **2** | 2 ✓ |
| GRP-01 | 1 | 13 | 1 | **15** | 15 ✓ |
| GRP-02 | 0 | 1 | 0 | **1** | 1 ✓ |
| GRP-03 | 0 | 1 | 2 | **3** | 3 ✓ |
| GRP-10 | 0 | 1 | 0 | **1** | 1 ✓ |
| OO 挂点 | 1 | 16 | 3 | **20** | 20 ✓ |
| segmented | 1 | 16 | 2 | **19** | 19 ✓ |
| mode 门控 | 1 | 16 | 2 | **19** | 19 ✓ |
| BP 数合计 | 6 | 16×7+1 = **113** | 7×3 = 21 | **140** | 现算校验 |
| xlsx 公式格 | 57 | 0 | 63 | **120** | 120 ✓ |
| xlsx sheets | 9 | 0 | 4 | **13** | 13 ✓ |
| Property 22 站点（A 域） | 0 | 0 | 1 | **1** | 1 ✓ |
| 真库行数（本轮 20 条内） | 0 | 1（a171） | 0 | **1** | 1 ✓ |

另需成立：`docx 16 + xlsx 2 + 无册 2 = 20` · `BP-9 集合 == docx 集合` 为 True · 区分项 BP 横跨数 = **0** · lane2 的 BP 数 = 15×7 + 1×8（a91）= **113**。

## 架构决策

### 决策 1 — canary 判据第二次偏离，但三轮轨迹须完整留痕
A 域真库唯一命中是 E2E seed ⇒ 硬标准无解。采用五条替代判据，**并在交付物中写明 M→N→A 三轮态度**，使读者能确认每轮都现查了分母。后续 B / C / S 轮仍须先查真库分母再决定用哪套判据。

### 决策 2 — 按 docx 轴切分（等价于 BP-9 轴）
`BP-9 集合 == docx 集合` 现算为 True，这是 A 域唯一能做到**零横跨**的切分轴。foundation 取非 docx 的 a51（零区分项），lane2 收全部 docx，lane3 收 3 条非 docx 特例。

### 决策 3 — 不统一 mode 载体，只加统一判据层
17 个 entry 用中文标签作 mode 值、2 个用 label/value 分离。本 spec **不做全域归一化重构**（20 个宿主大改，风险远超收益），而是：判据层按「能力契约」断言；lane2 / lane3 在各自范围内把形态 1 收敛到形态 2（已有 2 个正面样板可抄）。

### 决策 4 — docx 定位模型以 `tc` 对象标识去重
合并单元格比例最高 99.5%，按 (row, col) 遍历会重复命中同一 `<w:tc>`。双向回写的 docx 侧定位键须基于 `tc` 标识，并在守卫中锁定各册的 `merged_refs` 现值。

### 决策 5 — 模板层缺陷全部登记不修
T-1 ~ T-11 共 11 项，含 `20l×年` 字符缺陷与 `F6-10` 跨循环码。修模板须业务确认且会动 sha256 基线（既存守卫会红）⇒ 本轮以记录型测试锁定现状，标 `[ ]*`。

### 决策 6 — A 域不接 TB 发布门
`publish-to-tb` 在 A 域现算 0，且 A 类底稿（沟通函/声明书/汇总/核对表）业务上不产生审定数 ⇒ 改线 SHALL NOT 新增该端点调用，并在 spec 显式声明空分母而非「已合规」。

## 测试策略

**测试文件**：`backend/tests/workpaper_sync/test_a_cycle_foundation_canary.py`（新建，与既存 `test_task57_abcs_and_shared_migration.py` 并存）。

🔴 **测试类命名禁照抄 N**：

| 类名 | 覆盖 | 与 N 轮差异 |
|---|---|---|
| `_VueGateParser` | AF-P13 · AF-P14 | 🔴 辅助类（非 Test 前缀），对齐既存守卫的 `_VueTemplateParser` |
| `TestSliceScopeAndDomainSplit` | AF-P1 ~ AF-P7 | 🔴 A 独有（四循环合一 slice） |
| `TestWritePathAndChannels` | AF-P8 ~ AF-P12 | 🔴 发布门改为空分母断言 |
| `TestModeGateResolution` | AF-P13 ~ AF-P16 | 🔴 递归回溯 + 两中间版本变异证明 |
| `TestModeCarrierDichotomy` | AF-P17 ~ AF-P19 | 🔴 A 独有 |
| `TestCanarySelectionAndDeviation` | AF-P20 ~ AF-P22 | 🔴 含三轮轨迹断言 |
| `TestContractFieldsAndRealDb` | AF-P23 ~ AF-P25 | — |
| `TestTemplateFormatDispatch` | AF-P26 ~ AF-P31 | 🔴 A 独有（format 分流 + raw XML footer） |
| `TestStructuralZerosWithMutationProof` | AF-P32 | — |
| `TestEntryGroupsAreRecomputable` | AF-P33 | 对齐既存守卫同名类 |
| `TestArchivedSpecBoundary` | AF-P34 · AF-P35 | 🔴 含 6 份未完成欠账 |
| `TestProperty22DynamicColumn` | AF-P36 | 对齐既存守卫同名类 |

**原则**：
1. 期望值由扫描器现读源文件得出，禁在断言里写死数字。
2. 结构性零必须成对出现「零断言 + 变异证明」。
3. 权威册 sha256 断言置于最前，失败即中止。
4. 真库测试用 asyncpg（🔴 DSN 从 `backend/app/core/config.py` 的 `settings.DATABASE_URL` 取并去掉 `+asyncpg`；`.env` 无 `DATABASE_URL` 键），无库环境 skip 并标原因。
5. 🔴 扫归档区一律带 `errors="replace"`（有非 UTF-8 文件）。
6. 🔴 docx 册禁跑 openpyxl；对 docx 的「公式格计数」判据一律不写（无意义）。
