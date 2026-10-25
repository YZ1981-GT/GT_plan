# Task 0 前置依赖核查证据

**核查日期**：2026-09-26　**判定方法**：`git show HEAD:<path>` / `git grep <pattern> HEAD` /
`git ls-tree -r HEAD`（**全程不读工作树**，按 requirements.md 需求 7.2 与 design.md「Error
Handling」表格纪律）

**HEAD 提交**：`5a791a5a7 fix(d567): 修 D6/D7 底稿目录聚合键缺陷 + Task0 前置门核查`
（当前分支 `work/2026-09-14-d4-dual-mode-p0-fixes`，工作树相对该 HEAD 有大量未提交改动 ——
`git status` 显示 `?? .kiro/specs/d1-sync-row-table-engine-and-d1-coverage/`、
`?? .kiro/specs/d3-sync-coverage-via-row-table-engine/` 等均为**未跟踪**，本核查全部忽略工作树，
只信 HEAD）

## 结论一句话

**前置 A / B 均不满足（上游 `d1-sync-row-table-engine-and-d1-coverage` 框架层 0% 未入 HEAD，
该 spec 本身在 HEAD 里都不存在）。前置 C 的两个函数已入 HEAD（满足）。前置 D 现状 False，
与 spec 文档记录一致。**

⇒ 按 tasks.md 的阻塞规则「IF A 未满足 THEN 全部阻塞」，**本 spec 全部 16 个任务阻塞**，
不应继续推进阶段 1~5 的任何任务。

---

## 逐前置判定

### 前置 A：上游框架层已入 HEAD —— ❌ 不满足

需核实四项：`RowTableSheetSpec` 数据类 / `StoreItemSpec` 注册表 / `attach_sibling_bindings(provider=…)` /
`phase5_d3_02_detail.py` 声明拆分模块。

**1. 先用 grep_search 定位符号可能所在路径**（工作区实时搜索，仅用于定位候选路径，不作为判定依据）：

- `class RowTableSheetSpec` grep_search 唯一命中 `.kiro/specs/d1-sync-row-table-engine-and-d1-coverage/design.md:50`（spec 文档，非生产代码）
- `class StoreItemSpec` grep_search 唯一命中同一份 design.md:148（同上）
- `attach_sibling_bindings`（不带下划线前缀的通用函数）grep_search **零命中**
- `phase5_d3_02_detail.py` file_search **零命中**（`No files found matching your search`）

**2. 用 `git show HEAD:` / `git grep HEAD` 逐一核实 HEAD 版本**：

```
$ git show HEAD:backend/app/services/workpaper_sync/row_table_engine.py
fatal: path 'backend/app/services/workpaper_sync/row_table_engine.py' does not exist in 'HEAD'
Exit Code: 1
```

```
$ git grep -n "class RowTableSheetSpec" HEAD -- backend/
Exit Code: 1  （零命中，backend/ 生产代码下没有这个类）
```

```
$ git grep -n "class StoreItemSpec" HEAD -- backend/
Exit Code: 1  （零命中）
```

```
$ git grep -n "attach_sibling_bindings" HEAD -- backend/
HEAD:backend/app/services/workpaper_sync/phase5_d4_revenue_detail.py:478:#: 缺口解除（`_attach_table_part` XML 合并 / `_attach_sibling_bindings` 按 managed_sheet 归组 /
HEAD:backend/app/services/workpaper_sync/phase5_d4_revenue_detail.py:2645:    sibling_bindings = _attach_sibling_bindings(
HEAD:backend/app/services/workpaper_sync/phase5_d4_revenue_detail.py:2666:def _attach_sibling_bindings(
HEAD:backend/tests/workpaper_sync/test_d4_1_sibling_binding_alignment.py:10:...
```

**关键区别**：HEAD 里存在的是 `_attach_sibling_bindings`（**私有**、下划线前缀、**硬编码在
`phase5_d4_revenue_detail.py` 里，专属 D4**），不是需求 7.1 描述的**通用框架层函数**
`attach_sibling_bindings(provider=…)`（公开、接受 `provider=` 参数、供任意循环复用）。
这正是上游 `d1-sync-row-table-engine-and-d1-coverage` design.md 里裁决要做的「泛化」工作
（design.md 原话：「`_attach_sibling_bindings` 的 D4 特化**只有一行 import** ⇒ 泛化=提成参数、
函数体不动」）—— 但这件泛化工作**尚未落地**。

```
$ git ls-tree -r HEAD --name-only -- backend/app/services/workpaper_sync/ | grep -i "phase5_d3"
backend/app/services/workpaper_sync/phase5_d3_prepaid_receipts.py
```

HEAD 下 D3 相关 provider 文件只有单一的 `phase5_d3_prepaid_receipts.py`（847 行，与 requirements.md
「实测」表格记录的行数一致），**没有** `phase5_d3_02_detail.py` 这个声明拆分模块。

**3. 交叉验证：上游 spec 目录本身在 HEAD 是否存在**

```
$ git log --oneline -3 -- .kiro/specs/d1-sync-row-table-engine-and-d1-coverage/
（空输出，无任何提交历史）

$ git ls-tree -r HEAD --name-only -- .kiro/specs/d1-sync-row-table-engine-and-d1-coverage/
（空输出）
```

`git status` 里该目录标 `??`（untracked），证实：**`d1-sync-row-table-engine-and-d1-coverage`
这个上游 spec 本身在 HEAD 从未被提交过**，它当前只存在于工作树里。上游 spec 自己的 INDEX.md
（HEAD 版本）也记录其状态为 `0/35` 未实施。

**4. 独立交叉验证来源**：仓库内已有一份先于本次核查完成的、针对同一批前置的核查证据
`docs/operations/evidence/d567-sync-coverage/task0-preflight-gate.md`（该文件**已入 HEAD**，
`git grep` 命中于 `HEAD:docs/operations/evidence/d567-sync-coverage/task0-preflight-gate.md`），
是姊妹 spec `d567-sync-coverage-via-row-table-engine` 在 2026-09-26 对同一组前置（A/B/C 定义完全
相同，因为都消费同一个上游 d1 spec）做的独立核查，结论逐字一致：

> 「前置 A/B/C 全部未满足（上游 D1 spec 框架层真 0% 未入 HEAD）」
> 「`git show HEAD:backend/app/services/workpaper_sync/row_table_engine.py` Exit 1（文件不存在）；
> 全仓 grep `class RowTableSheetSpec` / `aging_layout` 仅命中 `.kiro/specs/*` 文档，零生产代码」

**判定：前置 A 不满足。** `RowTableSheetSpec` / `StoreItemSpec` 均只存在于 spec 设计文档里，
生产代码零实现；`attach_sibling_bindings(provider=…)` 这个通用签名不存在，只有 D4 专属的私有
`_attach_sibling_bindings`；`phase5_d3_02_detail.py` 声明拆分模块不存在。

---

### 前置 B：`AdjudicationSheetSpec` 已交付 —— ❌ 不满足

```
$ git grep -n "class AdjudicationSheetSpec" HEAD -- backend/ .kiro/
Exit Code: 1  （零命中于生产代码；.kiro/ 下也零命中类定义，只有各 spec 文档提及这个名字作为
              「待交付」的设计意图，例如 d2-sync-coverage-via-row-table-engine/design.md 里写
              「引擎、注册表、AdjudicationSheetSpec、四态状态机全部由它交付」——用的是将来时）
```

`git ls-tree -r HEAD` 未见任何 `adjudication_sheet_spec.py` 或同义命名文件。前面姊妹 spec 的
`task0-preflight-gate.md`（已入 HEAD）同样记录：

> 「B | `AdjudicationSheetSpec` 已交付 | ❌ **未满足** | `git show HEAD:.../adjudication_sheet_spec.py` Exit 1；grep `class AdjudicationSheetSpec` 零命中」

**判定：前置 B 不满足。** `AdjudicationSheetSpec` 目前只是设计意图，HEAD 生产代码里不存在这个类。

---

### 前置 C：`merge._protection` 的 `cell_in_ranges` + `_mask_spans_data_column` 已入 HEAD —— ✅ 满足

```
$ git grep -n "def cell_in_ranges" HEAD -- backend/app/services/workpaper_sync/
HEAD:backend/app/services/workpaper_sync/contracts.py:582:def cell_in_ranges(column: str, row: int, ranges: Sequence[str]) -> bool:
```

```
$ git grep -rn "def _mask_spans_data_column" HEAD -- backend/app/services/workpaper_sync/
HEAD:backend/app/services/workpaper_sync/merge.py:663:def _mask_spans_data_column(column: str, first_data_row: int, mask: tuple[str, ...]) -> bool:
```

两个函数**都已存在于 HEAD**（分别在 `contracts.py:582` 与 `merge.py:663`）。

**这一条与前置 A/B 的结论不同，须特别说明理由**：requirements.md 需求 7.2 与design.md「Error
Handling」表格里提到的「上游 spec 调研期间正因读工作树而误登记过一次」这条教训，指的是
**上游 `d1-sync-row-table-engine-and-d1-coverage` spec 自己在调研阶段的一次误判**（该 spec
INDEX.md 记录：「调研中一度把 `merge._protection` 登记成『已修复』，复核 `git show HEAD:…/merge.py`
后发现**修复只在工作树、HEAD 仍是只比列旧实现**」）—— 但那次误判发生的**时间点更早**（HEAD 当时
还没有这次修复）。本次核查针对的是**当前 HEAD**（`5a791a5a7`），此时 `merge.py` 与 `contracts.py`
的格级判定函数**已经真实提交入库**，不再是「只在工作树」的状态。姊妹 spec `d567` 的核查记录也在
「佐证」区块间接确认了这一点的时间线（它引用的是 d1 spec **tasks.md 里自记的历史教训**，而非
对 C 项重新做一次 HEAD 判定；本次核查是对 C 项本身做的独立 HEAD 判定，结果为满足）。

⚠️ 需要标注的边界：本条只核实了**函数存在**，未核实这两个函数是否已被 D3-1
审定表的具体接入代码引用（因为该引用代码本身尚不存在——见前置 A/B 结论）。也未核实
`test_masked_cell_protection_is_cell_level.py` 一类的判据测试文件是否已入 HEAD 并通过（超出
Task 0 核查范围，留给阶段 4 的 Task 13 实际接入时验证）。

**判定：前置 C 满足。** `cell_in_ranges`（`contracts.py:582`）与 `_mask_spans_data_column`
（`merge.py:663`）均已在 HEAD 存在。

---

### 前置 D：D3 的 `adapter_registered` 现状 —— False（与 spec 文档记录一致，符合预期）

定位 `register_from_manifest` 的实现：

```
$ git grep -n "def register_from_manifest" HEAD -- backend/
HEAD:backend/app/services/workpaper_sync/adapters/registry.py:550:    async def register_from_manifest(self, *, session: Any) -> "ManifestRegistrationOutcome":
```

读取该实现附近的 manifest 裁决表（`registry.py` HEAD 版本，Task 41 追加的字节区间），逐条列出
各 entry 的 `adapter_registered` 裁决理由，其中直接包含对 D3 的显式结论：

```python
"adapter_registered=True"：2026-09-07 实测真库 register_from_manifest() 已注册
  d2.receivable_detail / h1.disposal_check / g7.soe_subsidiary_disclosure
  （approved bundle / current published representation / entry_state 三件供给齐备）

"register_from_manifest() 当前只注册 {d2,d4,g7,h1}（有真实供给的 entry），
  D3-det-rows / D3-vc 全库 0 行、无 current published representation ⇒ 未注册成功。
  原登记乐观标 True 与现实脱钩（Property 49 实测捕获）；发布链真正产出 representation 后再回填 True。"
```

以及 D3 entry 自身的裁决段落（`registry.py` HEAD，manifest 条目 `contract_id: "d3.prepaid_receipts_detail"`,
`entry_id: "xlsx/gt-d3-prepaid-accounts"`）：

```python
"（不是 D3P 幻影码 / D3-2 名义码）：D3-det-rows 全库 0 行（同 H1 空表单），但 sibling
  D3-vc-current-rows 载荷落 wp_code=D3（1 行 3601B）已证 D3 store 落点=D3，且 D3 wp 未删除"
"register_from_manifest() 当前只注册 {d2,d4,g7,h1}（有真实供给的 entry），
  D3-det-rows / D3-vc 全库 0 行、无 current published representation ⇒ 未注册成功。"
```

这段是 `adapters/registry.py` 模块自身的 HEAD 版本内容（不是 spec 文档、不是本次核查臆测），
由生产代码的注释/裁决说明**直接确认**：D3 的 `adapter_registered` 现状为 **False**，
只有 `{d2, d4, g7, h1}` 四家被真实注册。

**交叉验证**（三个独立来源结论一致）：
1. `adapters/registry.py`（HEAD 生产代码注释，本次核查一手证据）→ False
2. `requirements.md` / `design.md`（本 spec 自身文档，声称的「实测现状」）→ False
3. `docs/operations/evidence/d567-sync-coverage/task0-preflight-gate.md`（已入 HEAD 的姊妹 spec
   核查证据，独立核查同一批 entry）→「前置 E | 三家 `adapter_registered` 是否 True | ❌ 全 False」
   （该文档核查的是 D5/D6/D7，但同一条 registry.py 裁决表明确写明「当前只注册 {d2,d4,g7,h1}」，
   D3 不在其中）

**未做的事（如实说明）**：本次核查**未连接真实数据库**去执行 `register_from_manifest()` 或查询
`working_paper_sync_entry_state` 表，只读取了 `adapters/registry.py` 源码里固化的 manifest 裁决
表（这是生产代码本身对「哪些 entry 已注册」这一状态的**权威静态声明**，而非运行时查询结果）。
按代码逻辑推断，结论为 False；未连真库复核一次运行时的实际值。鉴于该源码段落本身就是「真实供给
不足即显式给出未注册原因」的机制实现（`register_from_manifest` 文档字符串写明「未满足供给的给
显式原因，绝不用占位 id 充数」），且三个独立来源结论完全一致，可信度较高，但严格意义上仍属
「代码层面推断」而非「本次亲自连库验证」。

**判定：前置 D 为 False**（不满足，与 spec 文档预期一致，非过期结论）。

---

## 四项判定汇总

| 前置 | 判定 | 证据来源 |
|---|---|---|
| A（上游框架层入 HEAD） | ❌ **不满足** | `git show HEAD:.../row_table_engine.py` Exit 1；`git grep HEAD` 对 `RowTableSheetSpec`/`StoreItemSpec` 零命中于 `backend/`；`attach_sibling_bindings(provider=…)` 不存在，仅有 D4 专属私有 `_attach_sibling_bindings`；`phase5_d3_02_detail.py` 不存在；上游 spec 目录本身 `git log`/`git ls-tree` 均空（未提交，仍是 `??` 工作树文件） |
| B（`AdjudicationSheetSpec` 已交付） | ❌ **不满足** | `git grep -n "class AdjudicationSheetSpec" HEAD` 全仓零命中（`backend/` 与 `.kiro/` 均无生产定义，仅设计文档提及为「待交付」） |
| C（`merge._protection` 两函数入 HEAD） | ✅ **满足** | `cell_in_ranges` 存在于 `HEAD:backend/app/services/workpaper_sync/contracts.py:582`；`_mask_spans_data_column` 存在于 `HEAD:backend/app/services/workpaper_sync/merge.py:663` |
| D（`adapter_registered`） | **False**（预期结论，非过期） | `HEAD:backend/app/services/workpaper_sync/adapters/registry.py:550` 附近 manifest 裁决表明确记录「`register_from_manifest()` 当前只注册 {d2,d4,g7,h1}」，D3 因 `D3-det-rows`/`D3-vc` 全库 0 行、无 published representation 未注册；按代码逻辑推断，未连真库复核运行时结果 |

---

## 下游影响结论

按 tasks.md Task 0 原文的阻塞规则：

> IF A 未满足 THEN 全部阻塞。IF B/C 未满足 THEN 阶段 4（D3-1）阻塞，其余可推进。
> IF 仅 D 未满足 THEN 代码与合成判据可推进、真栈实测阻塞并标 `[ ]*`

本次核查结果是 **A 不满足**（同时 B 也不满足，C 满足，D 现状 False）。

**规则里「IF A 未满足 THEN 全部阻塞」是最高优先级判据，一旦触发即覆盖后续所有「IF B/C」「IF 仅 D」
的细分处置** —— 这些细分处置的前提都隐含「A 已满足」（否则 `RowTableSheetSpec` /
`AdjudicationSheetSpec` 这些类型本身不存在，阶段 1~3 声明 `RowTableSheetSpec(...)` 的代码在
import 时就会因符号不存在而失败，不存在「B/C 未满足但阶段 1~3 可推进」的中间状态）。

⇒ **本 spec 的 16 个任务（阶段 0~5，Task 1 至 Task 16）全部阻塞，不应继续推进。**

具体表现：
- Task 1（六张 sheet 形态判定 + 几何实测填参）：**几何实测本身**（openpyxl 直读模板行列数/公式数）
  不依赖框架层，理论上可独立做；但 requirements.md/design.md 记录的几何数字（D3-1 30r×12c/88f、
  D3-4 38r×9c/22f 等）**已经是本 spec 文档里现成的「实测在案」数据**，重新跑一次 openpyxl 不会
  产生新信息，且 Task 1 的产出目的是喂给 Task 6/8/9/11/13 的 `RowTableSheetSpec(...)` 声明——
  而这些声明代码本身因前置 A 不满足而无法落地。
- Task 2~5（零回归基线 / 红判据 / 性能基线）：这些判据脚本引用的是 D3-2 现有已接入的 contract
  与 `verify_unmanaged_regions` 等**已存在**的机制，理论上可独立跑；但 Task 3/4 的红判据要断言
  的正是「D3-6/D3-4/D3-7 尚未接入」这件事，而它们尚未接入的**根本原因**正是前置 A 不满足 ——
  在前置 A 解除之前跑这些判据，能确认的只是「这些 sheet 现在确实没接」，不能推进接入。
- Task 6~15（六张 sheet 各自的 `RowTableSheetSpec` / `AdjudicationSheetSpec` 声明代码）：**直接
  阻塞**，因为这些类型在 HEAD 生产代码里不存在，声明代码 import 即报错。
- Task 16（前端接线 + 真栈验收）：依赖 Task 6~15 已完成的后端受管清单，**直接阻塞**。

**与 IF B/C、IF 仅 D 两条细分规则的关系**：即使假设性地忽略 A（仅看 B/C/D），核查结果显示
B 也不满足（`AdjudicationSheetSpec` 未交付），C 满足，D 为 False —— 若 A 满足而 B/C 不满足，
按规则应是「阶段 4（D3-1）阻塞，其余可推进」；但由于 A 本身就不满足，这条规则不适用，
**不能**得出「阶段 1~3（D3-6/D3-4/D3-5/D3-7）可以推进」的结论，因为这些阶段同样依赖
`RowTableSheetSpec`（框架层的一部分，属前置 A），而不仅仅依赖 `AdjudicationSheetSpec`
（前置 B，只影响 D3-1）。

## 与本 spec 文档记录的一致性说明

本次核查的四项结论（A 不满足 / B 不满足 / C 满足 / D=False）与 requirements.md 需求 7、
design.md 裁决 F5、tasks.md Task 0 原文里**记录的「实测现状」完全一致** —— 这些文档在编写时
已经如实记录了「上游框架层未入库」「`adapter_registered=False`」等结论，本次核查是对这些
已记录结论的**独立复核确认**，未发现结论过期或与当前 HEAD 不符的情况。唯一需要澄清的是前置 C：
design.md「Error Handling」表格引用的「上游曾因读工作树误登记过一次」这条教训，指的是**更早
时间点**（上游 d1 spec 调研阶段）的一次历史误判，与本次核查针对**当前 HEAD** 的判定（C 满足）
不矛盾——两者是不同时间点的两次独立判定，当前 HEAD 已经包含了那次误判之后补入库的格级判定代码。

## 判定结果一览（供 orchestrator 决策）

**A=不满足 / B=不满足 / C=满足 / D=False（现状确认，非过期）⇒ 触发「IF A 未满足 THEN 全部阻塞」
最高优先级规则，本 spec 全部 16 个任务（阶段 0~5）阻塞，不应继续执行 run-all-tasks 后续任务。**


---

# 复核追记（2026-09-26 之后，HEAD 已推进至 d2dbac39b）

**触发原因**：用户询问「目前是否可以开发」，由于上次核查刻意锁定在 HEAD `5a791a5a7`（不读工作树），
而当前 HEAD 已推进多个 commit，需重新核查四项前置是否仍然成立——上次的「全部阻塞」结论**有时效性**，
不能假定它对新 HEAD 仍然有效。

**当前 HEAD**：`d2dbac39b chore(sync): 两 spec 收尾 —— CI 卡点接入 + tasks.md 诚实标注 + 复盘`

中间关键提交（`git log --oneline`）：
```
d2dbac39b chore(sync): 两 spec 收尾 —— CI 卡点接入 + tasks.md 诚实标注 + 复盘
ab0c437de feat(sync): E1 provider 从零建 + canary E1-2 + E1-4 + E1-11（唯一 static_region）
399981c61 feat(sync): d1 spec 框架层阶段0~2完整交付，解除 d567 上游阻塞
04a90f386 feat(sync): D2 受管覆盖 1→3 张（D2-3 坏账准备双区 + D2-1 审定表逐格 + D2-4 single_html 裁决）
f1ec1c67d feat(sync): AdjudicationSheetSpec + D1 sheet 声明层（D1-2/D1-3/D1-4 三区）+ 多受管扩容骨架
```

## 逐前置重新判定（`git show HEAD:` / `git grep HEAD`，仍不读工作树）

### 前置 A：上游框架层已入 HEAD —— ✅ 现已满足（结论反转）

```
git grep -n "class RowTableSheetSpec" HEAD -- backend/
HEAD:backend/app/services/workpaper_sync/phase5_row_table_sheet.py:101:class RowTableSheetSpec:

git grep -n "class StoreItemSpec" HEAD -- backend/
HEAD:backend/app/services/workpaper_sync/store_item_registry.py:75:class StoreItemSpec:

git grep -n "def attach_sibling_bindings" HEAD -- backend/
HEAD:backend/app/services/workpaper_sync/phase5_row_table_sheet.py:390:def attach_sibling_bindings(
```

读取该函数定义（`phase5_row_table_sheet.py:390`）确认签名为
`attach_sibling_bindings(*, provider: Any, primary: Any, contract: Any, dynamic_bindings: Mapping[str, Any])`
——与需求 7.1 描述的通用签名一致。函数文档字符串自述：「从 `phase5_d4_revenue_detail._attach_sibling_bindings`
逐字搬来，**函数体不动**，只把硬编码 import 改成显式 `provider` 参数」。

**交叉验证泛化已生效（不是只加了个新函数、旧调用点没接上）**：

```
git grep -n "attach_sibling_bindings(" HEAD -- backend/app/services/workpaper_sync/
backend/app/services/workpaper_sync/phase5_row_table_sheet.py:390:def attach_sibling_bindings(
backend/app/services/workpaper_sync/phase5_d4_revenue_detail.py:2645:    sibling_bindings = _attach_sibling_bindings(
backend/app/services/workpaper_sync/phase5_d4_revenue_detail.py:2687:    return attach_sibling_bindings(
```

`phase5_d4_revenue_detail.py` 的私有 `_attach_sibling_bindings`（原来的 D4 硬编码版本）现在
**内部委托**给通用的 `attach_sibling_bindings(provider=_self, ...)`——即泛化后 D4 自己也切到了
新函数，不是两套并存。这与前次核查时（HEAD `5a791a5a7`）「只有 D4 专属私有版本，通用签名不存在」
的结论**相反**。

唯一仍不存在的是 `phase5_d3_02_detail.py`：
```
git show HEAD:backend/app/services/workpaper_sync/phase5_d3_02_detail.py
fatal: path '...' does not exist in 'HEAD'
```
但这**不是前置条件的一部分**——它是本 spec 自己 Task 1/6/8/9/11/13 要新建的声明模块（D3 侧的
「声明拆分」产出物），前置 A 要求的是「框架层」（`RowTableSheetSpec` 等类型定义）已入 HEAD，
不要求 D3 已经用上它。

另外交叉核实了上游 spec 自己的 tasks.md 记录（`.kiro/specs/d1-sync-row-table-engine-and-d1-coverage/tasks.md`
顶部 Overview）：「✅ 2026-09-26 阶段 0~2（Task 0~14）完整交付并验证」「**直接解锁**：
`d567-sync-coverage-via-row-table-engine` 前置门已解除」——上游自己也确认了框架层已交付。

**判定：前置 A 现已满足。**

### 前置 B：`AdjudicationSheetSpec` 已交付 —— ✅ 现已满足（结论反转）

```
git grep -n "class AdjudicationSheetSpec" HEAD -- backend/
HEAD:backend/app/services/workpaper_sync/phase5_adjudication_sheet.py:98:class AdjudicationSheetSpec:
```

读取该类定义（`phase5_adjudication_sheet.py:98` 附近），字段与需求描述吻合：`sections`
（区块元组）、`row_mode`（行模型枚举）、`cell_mask`（逐格 mask，非列向区间）、`value_sources`
（字段值来源声明）。`__post_init__` 里还带了两条防御性校验（同 sheet 多区 `uuid_col` 不可重复 /
`section.table_key` 不可重复），说明这不是空壳声明，是已经踩过坑（D4-1 uuid_col 串区教训）
之后写的防御代码。

**判定：前置 B 现已满足。**

### 前置 C：`merge._protection` 两函数 —— ✅ 仍满足（结论不变）

复核一次，结论与前次一致：
```
git grep -n "def cell_in_ranges" HEAD -- backend/app/services/workpaper_sync/
HEAD:backend/app/services/workpaper_sync/contracts.py:582:def cell_in_ranges(...)

git grep -n "def _mask_spans_data_column" HEAD -- backend/app/services/workpaper_sync/
HEAD:backend/app/services/workpaper_sync/merge.py:663:def _mask_spans_data_column(...)
```

**判定：前置 C 满足（不变）。**

### 前置 D：`adapter_registered` —— False（不变，仍是已知卡点）

复核 `adapters/registry.py` 里的 manifest 裁决表，D3 相关段落**原文未变**（HEAD `d2dbac39b`
与前次核查的 HEAD `5a791a5a7` 相比，D3 这一条注释逐字相同）：

```
"register_from_manifest() 当前只注册 {d2,d4,g7,h1}（有真实供给的 entry），
D3-det-rows / D3-vc 全库 0 行、无 current published representation ⇒ 未注册成功。"
```

**判定：前置 D 仍为 False（不变，符合预期，仍是已知的真栈实测卡点）。**

## 复核后四项判定汇总

| 前置 | 上次判定（HEAD 5a791a5a7） | 本次判定（HEAD d2dbac39b） | 变化 |
|---|---|---|---|
| A（框架层入 HEAD） | 不满足 | **满足** | 反转（上游 d1 spec 阶段 0~2 已交付） |
| B（`AdjudicationSheetSpec`） | 不满足 | **满足** | 反转（`phase5_adjudication_sheet.py` 已交付） |
| C（`merge._protection` 两函数） | 满足 | 满足 | 不变 |
| D（`adapter_registered`） | False | False | 不变（已知卡点，非过期结论） |

## 下游影响结论（复核后）

按 tasks.md Task 0 原文的阻塞规则：

> IF A 未满足 THEN 全部阻塞。IF B/C 未满足 THEN 阶段 4（D3-1）阻塞，其余可推进。
> IF 仅 D 未满足 THEN 代码与合成判据可推进、真栈实测阻塞并标 `[ ]*`

**A/B/C 三项均满足，仅 D 不满足** ⇒ 命中第三条规则：**代码与合成判据可以全面推进，真栈实测阻塞
并标 `[ ]*`**。

具体表现：
- Task 1~15（六张 sheet 的形态判定、几何实测、`RowTableSheetSpec`/`AdjudicationSheetSpec` 声明、
  Property 1~11 各判据）：**可以推进**，`RowTableSheetSpec` / `AdjudicationSheetSpec` /
  `attach_sibling_bindings(provider=…)` / `cell_in_ranges` / `_mask_spans_data_column` 均已是
  HEAD 生产代码里的真实符号，声明代码 import 不会失败。阶段 4（Task 13/14，D3-1 审定表）此前
  因前置 B/C 而预留的阻塞已解除。
- Task 16（前端接线 + 变异检验 + 真栈 + 证据）：前端接线与变异检验部分可以推进；**真栈整段**
  （切「在线编辑」→ OO canvas 断言 → forcesave → 回读）仍须按 tasks.md 原文标 `[ ]*` 并写明
  「代码已改但未实测，卡 adapter 未注册」——这是前置 D 尚未解除的直接后果，**不得**用合成测试
  冒充真栈验收。
- 性能基线（Task 5）：若耗时判据依赖真库整册 materialize，同样受 D 卡点影响，需按脚本实际能否
  连库分别登记，不得笼统标「已完成」。

## 结论（供 orchestrator 决策，取代上次「全部阻塞」）

**当前 HEAD（`d2dbac39b`）下，前置 A/B/C 均满足，仅前置 D（`adapter_registered=False`）为已知
卡点。本 spec 可以开始开发——Task 1 至 Task 15 均可正常推进；Task 16 的真栈实测部分需标 `[ ]*`
待前置 D 解除后补验。上次（HEAD `5a791a5a7`）「全部阻塞」的结论已因上游 spec 在中间提交完成
交付而失效，不再适用于当前 HEAD。**
