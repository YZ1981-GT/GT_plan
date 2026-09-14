# Implementation Plan: 工作簿级行变更传播

## Overview

26 个任务 / 7 个 Wave。三条硬顺序约束：

1. ✅ **Wave 0 四个 Open Gate 已于 2026-09-04 全部裁决**（Task 1~4 已 `[x]`）。裁决改动了
   三处设计：Gate 1 → 禁止启发式推断、覆盖面 = 4 个已发契约 entry、**首要判据载体由 K11
   改为 D2**；Gate 2 → R4.2 点名的四类载体是空集且结构性不可能，真载体换成
   `hyperlink@location` / `dv formula` / `cf formula` 三类 + definedNames 五分类；
   Gate 4 → fail-closed 保留但补第三态 `undeletable_rows`（新增 AC 3.8）。
   裁决正文见 design.md「Open Gates（Wave 0 已裁决）」。
2. **零回归拆成两步，且第一步时间敏感。**
   **Task 6（Wave 0，只读，必须在上游改动 `excel_row_shift.py` 之前做）** 冻结基线 ——
   Requirement 7.4 的参照物是「本 spec 前」的行为，上游一旦落地改动就再也无法取证；
   **Task 28（Wave 1，门后）** 加 `propagate_sheets` 后复跑基线并要求逐字相同，
   才允许 Wave 2 接传播。分母用 Wave 0 复算值 **182 份 / 144,154 处**
   （原登记 176 / 81,955 复算不上，详见 design.md「分母断言」）。
3. **插行传播（Wave 2）先于删行（Wave 3）。** 删行多一类必须处理的情形（悬空引用），
   在插行传播已被证明正确后再叠加，失败时能分清是传播错还是删行错。
4. **🔴 跨 spec 顺序：Task 101 是 Wave 2 起各任务的开工前提。** 本 spec 与
   `excel-structural-row-insertion-and-shift-aware-verification` 共改三个生产文件
   （`excel_row_shift.py` / `excel_materialize.py` 的 `plan_managed_writes` /
   `excel_extract.py` 的归一化），并行编辑会互相回退。必须现读上游 tasks.md 确认其
   Wave 4（Task 16 / 17 / 18）已 `[x]`。

## Tasks

### 文件记号

| 记号 | 文件 | 性质 |
|---|---|---|
| N1 | `backend/app/services/workpaper_sync/excel_workbook_row_change.py` | 新增：计划 / 扫描 / 传播 / 收缩 |
| M1 | `backend/app/services/workpaper_sync/excel_row_shift.py` | 改：`_rewrite_formula_refs` 加 `propagate_sheets` 参数 |
| M2 | `backend/app/services/workpaper_sync/excel_materialize.py` | 改：`plan_managed_writes` 接工作簿级计划 |
| M3 | `backend/app/services/workpaper_sync/excel_extract.py` | 改：未管理区域摘要按声明传播量归一化 |
| M4 | `.kiro/specs/excel-structural-row-insertion-and-shift-aware-verification/requirements.md` | 改：撤销 R12.1 / R12.4 排除 |
| T1 | `backend/tests/workpaper_sync/test_workbook_row_change_plan.py` | 新增：计划与零回归判据 |
| T2 | `backend/tests/workpaper_sync/test_workbook_row_change_insert.py` | 新增：插行传播判据（K11 的 114 处） |
| T3 | `backend/tests/workpaper_sync/test_workbook_row_change_delete.py` | 新增：删行与悬空引用判据 |
| T4 | `backend/tests/workpaper_sync/test_workbook_row_change_carriers.py` | 新增：definedNames / sqref / 图表登记判据 |
| D1 | `backend/data/workpaper_row_change_reachability.json` | 新增：**136** 份可达性清册（生成器产出，**已交付**） |
| G1 | `backend/scripts/gen/generate_row_change_reachability.py` | 新增：清册生成器（`--check` / `--apply`，**已交付**） |
| T7 | `backend/tests/workpaper_sync/test_workbook_row_change_reachability.py` | 新增：清册守卫 + design.md 分母表三向锁（**已交付**） |
| T8 | `backend/tests/workpaper_sync/test_workbook_row_change_openability.py` | 新增：Task 25 三层可打开性 + AC 8.4 求值层诚实拆层（**已交付**） |
| T5 | `backend/tests/workpaper_sync/test_workbook_row_change_upstream_gate.py` | 新增：Task 101 上游就绪门 + Property 27 基线（**已交付**） |
| T6 | `backend/tests/workpaper_sync/test_workbook_row_change_zero_regression.py` | 新增：零回归基线守卫（Task 6） |
| D2 | `backend/tests/workpaper_sync/data/workbook_row_change_zero_regression_baseline.json` | 新增：冻结基线（生成器产出） |
| G2 | `backend/scripts/gen/generate_workbook_row_change_zero_regression_baseline.py` | 新增：基线生成器（`--check` / `--apply`） |
| X1 | `backend/scripts/diagnose/mutate_workbook_row_change_guards.py` | 新增：变异检验脚本。⚠ 分工书 §2 把 `backend/scripts/diagnose/mutate_*.py` 判给 **E**，本文件由 E 统一写（四态判读标准统一）；C 只提供变异清单与预期态 |

---

### Wave 0 —— 前置裁决（不写生产代码）

> **2026-09-04 全部裁决完毕。** 扫描口径复用生产分词器（`excel_row_shift` 的
> `_QUALIFIED_PREFIX_RE` / `_REF_TOKEN_RE` / `_STRING_LITERAL_RE` / `_left_boundary_ok` /
> `_BARE_TOKEN_RE`）+ `excel_structure_fingerprint._parse_workbook_xml` / `_normalise_part`，
> 未手搓正则。完整裁决正文见 design.md「Open Gates（Wave 0 已裁决）」；分母表见
> design.md「分母断言」。

- [x] 1. 裁决 Gate 1：受管 sheet 判定对受影响模板的覆盖率
  - **裁决 = 一律登记 `blocked`（原因码 `no_projection_contract`），禁止启发式推断**
  - 实测三条：`DELIVERED_PER_ENTRY_CONTRACTS` 只有 **4 行**（b60 / d2 / g7 / h1）；
    全库 351 份 xlsx 里含 Excel Table 的只有 **1 份**（`C24` 的 `_2025__2`，与受管无关）；
    每份受影响模板中含占位标记的 sheet 张数中位数 **4**、最多 **18**
  - 根因：`resolve_managed_region` 的唯一锚点是 **Excel Table displayName**，而 Table 是
    `excel_instrumentation` **注入**的，不是权威模板自带的 ⇒ 「受管 sheet 可知」的充要条件
    是**该 entry 有已审核契约**，与模板长什么样无关
  - 🔴 启发式推断被拒的理由：猜错受管 sheet 产出的 xlsx 仍能打开、公式仍有值、只是值错了 ——
    那正是本 spec 要消除的静默错行，用它当实现手段自相矛盾。「推断错了被什么判据抓住」
    这个问题**没有可接受的答案**
  - 🔴 副产物发现：**今天唯一有真实传播需求的契约 entry 是 D2**（`明细表D2-2` 被 4 张 sheet
    的 **52 处**引用，被引用行 13 / 25 / 26）；b60 / g7 / h1 各 **0 处**；K11 的 114 处
    **没有契约** ⇒ K11 是动机样本不是可执行样本 ⇒ **判据载体分两级**（见 Task 10 / 11）
  - 🔴 副产物发现：**sheet 名不是全库唯一**，`附注披露信息（国企）` 在 **39 份**模板里都存在
    且被引用情况各不相同 ⇒ 新增 AC 6.5，宿主必须由 entry → representation → 模板绑定确定
  - **Validates: Requirements 6.1, 6.2, 6.5**

- [x] 2. 裁决 Gate 2：引用载体的真实规模
  - **裁决 = R4.2 点名的四类是空集且结构性不可能；真载体是另外三类**
  - 实测：`conditionalFormatting@sqref` **0/440** · `dataValidation@sqref` **0/1223** ·
    `mergeCell@ref` **0/37456** · `hyperlink@ref` **0/3950** —— 这四类的 OOXML 类型是
    `ST_Sqref` / `ST_Ref`，语义上就是所在 worksheet 内的区间，**表达不了 sheet 前缀**；
    实测取值形态逐一印证（`H7:M7 C7:F7 J7:J48` / `A1:R1` / `X3`，无一带 `!`）
  - 真载体：`hyperlink@location` **3,480/3,764**（158 份）· `definedNames` **5,002/63,973**
    （341 份）· `dataValidation/formula1|2` **8/1,094**（4 份）·
    `conditionalFormatting/formula` **6/552**（1 份）⇒ 新增 AC 4.5 / 4.6 / 4.7
  - definedNames 的 5,002 条**必须先分解**（五类处置各不相同）：`builtin_self_scope` **2,457**
    （传播）· `target_not_in_workbook` **1,991**（登记）· `user_self_scope` **292**（传播）·
    `user_cross_sheet` **252**（传播，R4.1 真正的对象）· `builtin_other_sheet` **10**
  - `xl/charts/**` **8** 个部件 / 1 份模板（可用真实样本）；`xl/pivot*/**` **0** 个部件
    ⇒ pivot 分支判据必须用注入变体，否则空集恒真
  - 🔴 实测踩坑（已写进 AC 4.6）：扫整个 `<dataValidation …>` 元素会把 `error=` 里的中文
    提示（「请从G7-14名称列表…」）当成跨 sheet 引用 —— 只能扫 `<formula1>` / `<formula2>`
    的**内容**
  - **Validates: Requirements 4.4, 4.5, 4.6, 4.7**

- [x] 3. 裁决 Gate 3：极端规模模板的性能阈值
  - **裁决 = 不异步化、不登记 `blocked`，阈值 2,000 ms**
  - 实测（读 zip + 全工作簿每个 `<f>` 过一遍生产改写器 + zip 重打包 = 成本上界）：
    `C24` **1,158 ms** · `A2-1`(9,744) **201 ms** · `A3-4`(3,659) **181 ms** ·
    `A3-1`(3,137) **163 ms** · `K11`(114) **7 ms** · `H1`(0) **43 ms**
  - 🔴 发现比 spec 登记更极端的样本：`C/C24 会计分录 - 细节测试.xlsx` 的 `2025假期清单`
    被引用 **63,240 处** = 原登记 9,744 的 **6.5 倍**；> 1,000 处的组合实测共 **10** 个
  - 阈值依据：这是显式的「保存底稿」动作而非键入实时反馈；且 1,063 ms 那项是**全量**改写，
    真实传播只改命中受管 sheet 的引用
  - 🔴 耗时由**公式文本长度**主导而非条数（`A2-1` 的 16,179 条只用 144 ms，`C24` 的
    10,906 条用了 1,063 ms）⇒ 性能判据的自变量必须是**引用处数**
  - **Validates: Requirements 6.3, 8.5**

- [x] 4. 裁决 Gate 4：删行的悬空引用普遍度
  - **裁决 = fail-closed 保留（R3.4 不动），但必须补第三态「不可删行」（新增 AC 3.8）**
  - 有契约的 4 张受管 sheet 实测：`明细表D2-2` 被引用 3 行（13 / 25 / 26，全 ≥ anchor 11）
    ⇒ 3 行不可删、其余可删；其余三张受管 sheet **0 行** ⇒ **删行不因本 Gate 阻塞**
  - 🔴 但 K11 形态下 fail-closed = 删行零可用：受管区 `A7:N25` 共 19 行，被引用行落在区内
    **19/19 = 100%** ⇒ 可安全删除 **0/19**
  - 全库代理统计（172 个「受影响模板 × 被引用 sheet」组合）：**82 个（47.7%）**的被引用行
    span 内 100% 全被引用，≥ 90% 的 92 个，≥ 70% 的 122 个 —— 不是个别形态
  - ⇒ `undeletable_rows` 是与 fail-closed **同批交付**的计划字段（不是独立特性）：把拦的
    位置前移到 HTML 侧发起删行**之前**，同一条语义换成可用形态
  - **Validates: Requirements 3.4, 3.8**

- [x] 6. G2 + D2 + T6：冻结零回归基线（🔴 **时间敏感，必须在上游改动 `excel_row_shift.py` 之前做**）
  - ✅ **2026-09-04 已冻结**。产物三件：G2 生成器（`--check` / `--apply`）+ D2 基线 JSON
    （216 KiB，入库）+ T6 守卫（**16 例绿**，全库现算 9.5 秒，变异 **7/7 RED**）
  - 🔴 **基线独立复现了 Wave 0 的全部分母**（生成器与 Gate 扫描是两份独立实现）：
    xlsx **351** / 含跨 sheet 引用模板 **182** / 跨 sheet 引用 **144,154** 处 /
    含跨 sheet 引用的公式 **72,825** 条 / 3D **0** 处 / 外部工作簿 **2,908** 处；
    另得公式总条数 **126,565**
  - 三个情景独立冻结（`insert_ctx` / `insert_no_ctx` / `filldown`），并有判据断言
    「至少一份模板上三者两两不同」—— 否则三组参数没被真正区分，基线只覆盖了一种行为
  - ⚠ **Task 27 落地时 `filldown` 情景必然变红，那不是回归**：现基线冻结的恰是
    Requirement 10 要修的**带缺陷**行为。Task 27 须①先看差异清单确认变化全落在跨 sheet
    相对引用上 ②确认 `insert_ctx` / `insert_no_ctx` 未变 ③再 `--apply` 重新冻结并说明理由。
    守卫里 `test_filldown_currently_does_not_shift_cross_sheet_refs` 的 docstring 已写明
    「修好后必须把本判据改成断言会平移，留着不改就是把缺陷永久锁死」
  - 反向自检两条（这两条才证明基线真挂在被观测对象上，而非两份互相复制的数字）：
    ① `test_guard_detects_real_rewriter_behaviour_change` —— **进程内 monkeypatch**
    扰动 `_rewrite_formula_refs`，三个情景的 digest 必须各自变化。刻意不改磁盘上的
    `excel_row_shift.py`（它归上游且正被并发会话编辑，变异式改文件再复原有覆盖风险）
    ② `test_diff_detects_offsetting_changed_counts` —— 两处**相反**的 `changed` 变化
    （全库总数不变）也必须被报出，这是「只存聚合计数不够」的实证
  - 🔴 变异检验捞出一条判据形态缺陷（已修）：`test_every_class_has_samples` 原先只查磁盘
    基线不查现算 ⇒ 清空合成用例的变异先被基线比对抓住（判 WRONG-TEST），语义上该由本条
    报出「某类不再有样本」⇒ 改为 `stored` / `current` **两侧都查**
  - **Validates: Requirements 7.4, 7.7**
  - _原任务描述（保留备查）_：
  - 🔴 **为什么排在门之前**：Requirement 7.4 要求「未声明传播时行为与**本 spec 前**逐字相同」。
    「本 spec 前」是一个**会随时间消失**的参照物 —— 上游一旦落地 Wave 2~4 的改动，当初的行为
    就再也无法取证，7.4 退化为无法证伪的声明。冻结动作本身**只读**（不碰任何共改文件）
    ⇒ 不受 Task 101 阻断（新增 AC 7.7）
  - 生成器 `--check` / `--apply`；基线内容两层，缺一不可：
    - **逐模板摘要**（每份模板一条摘要 digest + 计数）—— 任何行为变化都能被发现
    - **分类样本的完整输入/输出对** —— 变化时能定位到是哪一类误命中回归了。至少覆盖：
      跨 sheet 逐字不动 / 表名形如 A1（**15,066** 处）/ 自限定引用 / 3D（**0** ⇒ 合成用例）/
      外部工作簿（**2,908** 处）/ 带数字函数名 `LOG10` / 字符串字面量 / 混合形态
  - 🔴 只存聚合计数**不够**：两处相反的行为变化会互相抵消 ⇒ 摘要必须是**顺序敏感的
    输入→输出序列 digest**，不是计数之和
  - 分母断言：**351** 份 xlsx / **182** 份含跨 sheet 引用 / **144,154** 处引用 /
    **72,825** 个含跨 sheet 引用的 `<f>`
  - 守卫必须在**干净 checkout** 下可跑（基线 JSON 入库），且 CI 可复算
  - **Validates: Requirements 7.4, 7.7**

- [x] 101. 前置 spec 就绪门（**Wave 1 起各任务的开工前提**）
  - ✅ **2026-09-05 门已开并复跑通过**：现读上游 tasks.md，Wave 4 的 Task 16 / 17 / 18
    **均为 `[x]`**（该三条无 `*` 子任务）⇒ 门放行，Wave 1+ 解除阻断
  - 🔴 **反向判据自动失效并 skip**（设计如此）：`test_wave2_artifacts_absent_while_gate_closed`
    只在门关时适用，门开后改由门后各任务自身判据接管 ⇒ 现读 17 passed / **1 skipped**
  - Property 27 复核：`_A1_PIECE_RE` 的 AST owner 仍恰为 `{_rewrite_formula_refs}`
    —— 上游把 `excel_row_shift.py` 从 78,416 长到 99,223 字节，**没有**新造第二个 A1 改写入口
  - **门已建成并交付**：`backend/tests/workpaper_sync/test_workbook_row_change_upstream_gate.py`
    （T5，**18 例全绿**）。**门当前判定：关闭** —— 2026-09-04 现读上游 tasks.md，
    Wave 4 的 Task 16 / 17 / 18 **均为 `[ ]`** ⇒ 本 spec Wave 2 起各任务拒绝开工
  - ⚠ 上游 tasks.md 在并发会话中被实时编辑（建门时其 mtime 距当时 **2 分 39 秒**）
    ⇒ 判据现读磁盘不缓存；**C 不碰上游任何文件**
  - 门的五类判据（各自能独立打红）：① 解析器正确（顶层三条全在 + 只认 Wave 4 相关 id）
    ② 上游整份文件的形态断言（实测 **27** 条 = **22** 顶层 + **5** 个 `*` 子任务、零重复）
    ③ 门的行为（`[x]` 之外含 `~` / `-` 全拦；`*` 子任务未完成同样拦；异常携带完整清单）
    ④ 🔴 **反向判据** —— 门关着时 `excel_workbook_row_change.py` 必须不存在、
    `_rewrite_formula_refs` 签名里必须没有 `propagate_sheets`（有人无视门开工就红）
    ⑤ Property 27 基线（`_A1_PIECE_RE` 的 AST owner 恰为 `_rewrite_formula_refs`）
  - 变异检验 **9/9 RED**（复原后基线全绿）：行首锚定组合变异 / 同 id 重复 fail-closed /
    `~` 当就绪 / `propagate_sheets` 检测器短路 / owner 检测器掩盖第二入口 / 分母期望值改错 /
    漏 `\*?` / 编号只捕前导整数 / 就绪判定漏掉 `*` 子任务
  - 🔴 变异检验与 A 的 M0 对齐合起来捞出**四条**真问题，均已修：
    1. 最初「同编号保留最后一次」的收敛语义**掩盖了行首锚定判据** —— 叙述句排在真任务行
       之后时，`.match` → `.search` 的变异结果不变 ⇒ 改为收集全部出现次数 + 重复即
       fail-closed，变异才敏感
    2. 正则里的 `^` 与调用侧的 `.match` **互为第二道防线**，单独改任一个都被另一个挡住
       ⇒ 按「变异用例必须让被检验机制成为唯一保护」，那两条单点变异是**无效用例**而不是
       守卫缺陷；真正敏感的是**同时**去掉两者
    3. **漏 `\]\*?`**（A 在分工书 §10.3 指出的公共缺陷）：上游把可选子任务写成
       `- [ ]* 2.1 …`，原正则漏读 **5** 条（A 实测 P 少算 15 条、S 少算 5 条）
    4. 🔴 **A 给的修正正则 `(\d+)` 仍不够**：它把 `- [ ]* 2.1` 读成「任务 2」，于是
       2 / 5 / 6 / 8 / 10 各凭空多一次出现 ⇒ 本门的「重复即 fail-closed」会**误触发并永久
       关闭**。正解是把编号捕成完整 id：`(\d+(?:\.\d+)*)`。实测：完整 id 得 27 条 / 零重复；
       只捕前导整数得 `{2: 2, 5: 2, 6: 2, 8: 2, 10: 2}` 五组假重复。**已回报 A**（§9 的 C 行）
  - 就绪判定**纳入 `*` 子任务**（依平台既定要求「optional(*) 任务也要做完」）：顶层三条全 `[x]`
    但子任务还空着时门仍关闭。当前 Task 16 / 17 / 18 **无子任务**，暂不受影响
  - **本条保持 `[~]`（门已建成、判定为关闭），待上游 Wave 4 转 `[x]` 后复跑本门再收为 `[x]`**
  - **Validates: Requirements 7.5, 7.6**
  - _原任务描述（保留备查）_：
  - 🔴 本 spec 与 `excel-structural-row-insertion-and-shift-aware-verification` **共改三个生产文件**：
    `excel_row_shift.py`（前者新建 / 本 spec 改）、`excel_materialize.py`（两者都改
    `plan_managed_writes`）、`excel_extract.py`（前者加 `row_shift` 归一化 / 本 spec 改为按声明
    传播量归一化）。并行编辑会互相回退 —— 这是本仓库已发生过的事故形态
  - 现读前置 spec 的 `tasks.md`，断言 Wave 4 的 Task 16 / 17 / 18 均为 `[x]`；未完成即报清单并阻断
  - 判据落在**现读复选框**而非人工记忆；行首锚定正则 `^\s*-\s\[([ x~-])\]\s+\d+\.`
  - 同时断言 `_rewrite_formula_refs` 在前置 spec 收口后仍是唯一 A1 改写入口（与 Property 27 同源）
  - **Validates: Requirements 7.5, 7.6**

---

### Wave 1 —— 骨架与零回归复核（🔴 全部在 Task 101 门后）

- [x] 5. N1：类型、异常与纯函数骨架
  - ✅ **2026-09-05 已交付**（`excel_workbook_row_change.py`，约 640 行）
  - 🔴 **`PROPAGATION_CARRIERS` 刻意只有 5 项，不含 `sqref` / `merge` / `hyperlink_ref`**：
    Gate 2 全库实测这四类属性含跨 sheet 引用为 `0/440`（cf@sqref）、`0/1223`（dv@sqref）、
    `0/37456`（mergeCell@ref）、`0/3950`（hyperlink@ref）—— 不是样本不够，而是 OOXML
    **结构性不可能**（`ST_Sqref` / `ST_Ref` 语义上就是所在 worksheet 内的区间，表达不了
    sheet 前缀）。留一个恒为 0 的载体/计数器等于给「空集上恒真」留位置：那类判据永远绿，
    且没人会发现它从未真正执行过
  - 🔴 **`UNPROPAGATED_REASONS` 补了一项设计清单里没有的 `prefix_without_coordinate`**：
    Task 9 实测发现 D2 上有 **10 处** `'明细表D2-2'!#REF!` —— `_QUALIFIED_PREFIX_RE`
    命中前缀但 `_REF_TOKEN_RE` 对 `#REF!` 返回 None。传播器不动它是对的，但不登记就等于
    「有 10 处引用没被处理」不可见
  - 🔴 **`shift()` 返回 `int | None`，被删行返回 `None`** —— 返回行号本身会说谎（那个行号
    已被别的行占用），返回 0/-1 会被当成有效行号继续参与计算。`None` 逼调用方显式处置，
    而「显式处置悬空引用」正是 Requirement 3.4 要的
  - `assert_carrier_tables_consistent()` 把载体词表 ↔ 报告字段**双向**锁死（键集相等 /
    计数器是真实字段 / 没有多出来的 `*_changed` 死字段）—— 加一类载体时漏改任一侧都打红
  - `PropagationReport.assert_matches_plan()` **逐载体**对账而非只比总数（两个载体一多一少
    总数会互相抵消）
  - `undeletable_rows` 前置声明：K11 实测受管区 19 行**全部**被引用（19/19 = 100%），
    全库 172 个组合中 82 个（47.7%）是 100% 密度 ⇒ 只有 fail-closed 抛错时删行功能表现为
    「永远失败」，所以把拦的位置前移到发起删行之前（AC 3.8）
  - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**
  - _原任务描述（保留备查）_：
  - `RowChangeKind` / `PropagationEntry` / `UnpropagatedCarrier` / `WorkbookRowChangePlan` /
    `PropagationReport`；7 个异常类，`error_code` 两两不同
  - 🔴 `PropagationEntry.carrier` 的取值域按 Wave 0 Gate 2 定：`formula` /
    `hyperlink_location` / `data_validation` / `conditional_format` / `defined_name`
    —— **不含** `sqref` / `merge` / `hyperlink_ref`（结构性不可能带跨 sheet 引用，
    留一个恒为 0 的取值等于给「空集上恒真」留位置）
  - 🔴 `WorkbookRowChangePlan` 含 `undeletable_rows`（AC 3.8）；`PropagationReport` 的
    计数器与 `carrier` 取值一一对应，**不设** `sqrefs_changed` / `merges_changed`
  - `plan_workbook_row_change` 零磁盘零 DB；`shift`/`unshift` 为声明值映射
  - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**

- [x] 28. M1 + T6：`propagate_sheets` 参数与零回归复核（**接线前必须先绿**）
  - ✅ **2026-09-05 已交付，与 Task 9 同批**（刻意合并：只加参数不接消费方 =
    平台明令禁止的死代码/假绿第①源「additive 注入即死代码」）
  - `_rewrite_formula_refs` 加 `propagate_sheets: frozenset[str] = frozenset()`（第 8 个
    kwonly 参数）；空集时行为逐字不变，传播是**加法**不是行为翻转
  - 🔴 **零回归实测逐字相同**：`--check` 报 351 份 xlsx / 126,565 条公式 /
    182 份含跨 sheet 引用 / **144,154** 处引用 / 72,825 条含跨 sheet 引用的公式 /
    3D 0 处 / 外部工作簿 2,908 处，三个情景 digest 与冻结基线全等（9.09s）
  - Property 27 仍绿：新增的 `_row_only_piece` / `_propagated_token` 是 `_rewrite_formula_refs`
    的**嵌套**函数 ⇒ `a1_rewrite_owners()` 归属仍只有它一个顶层函数，未造第二入口
  - ⚠ **辐射面必须按引用关系反查，不能跑全量**：`backend/tests/workpaper_sync/` 整目录
    实测 >15 分钟超时。剥 docstring 后按 `excel_row_shift` / `_rewrite_formula_refs` /
    `translate_formula_rows` / `remap_a1_rows` / `unextend_total_formula` /
    `shift_sheet_rows` / `RowShiftPlan` / `propagate_sheets` 反查得 **8 个**测试文件，
    **233 passed / 2 skipped / 27.44s**
  - **Validates: Requirements 7.4**
  - _原任务描述（保留备查）_：
  - 判据：加参数后复跑 Task 6 冻结的基线，**逐模板摘要与全部分类样本必须逐字不变**
  - 🔴 **分母用 Wave 0 复算值，不用原登记值**：**182** 份含跨 sheet 引用（原登记 176）/
    **144,154** 处引用（原登记 81,955）/ **72,825** 个含跨 sheet 引用的 `<f>`。
    口径定义见 design.md「分母断言」——「每个限定前缀 + 目标 token 算一处」，排除自限定、
    3D、外部工作簿，且要求目标 sheet 在本工作簿内真实存在
  - ⚠ 改 `excel_row_shift.py`（M1）⇒ **门后任务**。Task 101 的反向判据会在 `propagate_sheets`
    提前出现在签名里时打红
  - **Validates: Requirements 7.4**

- [x] 7. T1：Property 1 / 2 / 3 骨架判据 + 变异
  - ✅ **2026-09-05 已交付**（`test_workbook_row_change_plan.py`，**76 passed / 1.12s**）
  - **P1 零写入面**用两条互补判据：① 复用生产守卫 `assert_no_mutation_surface` 本体
    （不另写一份检查）② **磁盘桩** —— 把 `builtins.open` / `zipfile.ZipFile` /
    `Path.open` / `read_bytes` / `read_text` 全替换成会抛的桩再建一次计划。桩比「读源码看
    有没有 open」强的地方是连**间接**触碰也抓得到。两条各带反向自检（塞假 session 必抛 /
    桩确实能抓真实读取）
  - **P2** 覆盖 `count<=0` / 裸字符串 `kind`（`RowChangeKind` 继承 `str` ⇒ 值相等，只有
    显式 `isinstance` 拦得住，本条锁的正是那个 isinstance）/ `style_from` 落在新行区间
    （`at=26,count=2,style_from=27` 这个实测漏网形态）/ `shift`↔`unshift` 往返
  - **P3** 用 **8 种非法 part 形态**取证，最危险的一种是直接把 sheet 名当 part（= 调用方
    压根没解析）；配 3 种合法形态做分母对照，避免在「全都拒绝」上恒真；再加一条**真实 D2
    模板**上的解析链条验证（`_parse_workbook_xml` → 按名找 → `_normalise_part` → 确认
    命中唯一且 part 在 zip 里）—— 否则 P3 的判据形态是空谈（要求了一个求不出来的东西）
  - **变异五条，且做了反向自检**（进程内 monkeypatch，不改磁盘生产文件 —— 那两个文件可能
    被并发会话编辑，变异式改文件有覆盖对方改动的风险）：M1 短路 `count` 校验 / M2 放宽
    part 正则 / M3 短路方向校验 / M4 词表多一项 / M5 计数器表多一项（M4+M5 合起来才证明
    「双向」，只测一个方向时反方向漂移会静默通过）。
    **三态实证**：未变异必抛 → 变异后不抛 → 复原后回到必抛，三步全绿 ⇒ 判据确实承重、
    不存在第二道防线代为拦截、变异无残留
  - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 8.1, 8.2, 8.3**
  - _原任务描述（保留备查）_：
  - 纯函数性（无文件创建、无 DB 连接）、kind/count 合法域、受管 sheet part 解析来源
  - 变异：把 `_parse_workbook_xml` 换成手搓正则时必须打红（B60/H1/G7 三模板全失败）
  - **Validates: Requirements 1.3, 1.4, 1.5**

---

### Wave 2 —— 插行传播

- [x] 8. N1：`scan_reference_carriers` —— 扫全工作簿找指向受管 sheet 的引用
  - ✅ **2026-09-05 已交付**（与 Task 12 的载体判据同批）
  - 🔴 **权威分词器落在生产侧**：新增 `excel_row_shift.iter_qualified_references()` +
    `QualifiedReference`，扫描器**共用改写器的原语**（`_STRING_LITERAL_RE` /
    `_ENTITY_LITERAL_RE` / `_left_boundary_ok` / `_QUALIFIED_PREFIX_RE` / `_REF_TOKEN_RE` /
    `_prefix_sheet_name`），不另写扫描器。两个生成器里各有一份 `qualified_hits` 已是两份
    拷贝，再抄第三份必然漂移
  - 🔴 **全库一致性判据**（`test_scanner_agrees_with_rewriter_on_whole_corpus`）：
    351 份 / 126,565 条公式，扫描器预期改动的 A1 片段数 == 改写器实际改动数，**0 处漂移**
  - 🔴 **这条判据实测抓到两个真问题**：
    1. **单位不一致** —— 首版按「去重行号数」对账，在 `'表'!E10:F10`（两个端点都是行 10）
       上 **12 处**不吻合。根因是 `PropagationEntry` 只有单数 `row_before/row_after`，
       表达不了「一处引用含 2 个片段」。已补 `piece_count` 派生属性 +
       `propagation_piece_counts()`，并把 `assert_matches_plan` 改为按片段数对账 ——
       否则区间引用会让**与计划完全一致**的传播被判漂移（最难查的一类假红）
    2. **带引号外部工作簿盲区** —— `'[31]已审利润纵向分析A1-13-4'!$E$27` 这种形态全库
       **2,971 处 / 150 份模板**被误判成「本工作簿内的 sheet」。成因与之前修的带引号 3D
       **完全相同**：Excel 对含标点的名字加引号，分隔标记（3D 的 `:` / 外部簿的 `[n]`）
       落在引号内 ⇒ 正则对应分组永不命中。修在 `_prefix_sheet_name` 一处（剥引号后再查
       `[n]`）+ `iter_qualified_references` 的分类分支
       - 后果本来有两条：① fill-down 下被平移（违反 AC 10.3）② 扫描时被登记成
         `target_not_in_workbook` 而非 `external_workbook`（把「指向别的文件」记成「引用坏了」）
       - 分词计数变化：`sheet` 145,106 → **144,155**（-951）/ `external` 2,908 → **3,883**
         （+975）/ `no_target` 203 → **179**（-24），合计 **-951+975-24 = 0** ⇒ 只是重新
         分类，没有漏扫
       - **基线已按此重新冻结**，前置五条机械核验：insert 两情景 **0** 处变化 / 扫描面指标
         **0** 变化 / filldown digest 变 **9 / 351** 份 / filldown 的 `changed` **只减不增**
         （0 处增加，9 份减少，如 `F2存货` 2637→2053）/ 变化样本全部含带引号外部簿引用
         （无关变化 **0** 处）。复核 `ok=True` 0 差异
  - 🔴 **`referenced_rows` 与 `covered_rows` 分开**：前者是**字面**行号（区间端点，与清册
    同口径），后者是区间**展开**。混用会错 —— 用端点判「某行是否被引用」会漏区间内部；
    用覆盖面当 `undeletable_rows` 则 D2 的 `Print_Area`（`$A$1:$AM$34`）会让 34 行全不可删。
    「哪些行真的不可删」留给 Wave 3 Task 16，本扫描只提供事实
  - **与清册对账**（两条独立代码路径）：D2 `formula`(42) + `prefix_without_coordinate`(10)
    = **52** = 清册 `referencing_sites` ✅；K11 `formula` = **114** = 清册
    `k11_managed_sheet_sites` ✅；K11 受管区 `A7:N25` 的 **19 行全部**被引用 = 清册
    `k11_managed_sheet_rows` ✅（这就是 AC 3.8 存在的理由 —— 只有 fail-closed 时删行永远失败）
  - **Validates: Requirements 2.6, 4.1, 4.2, 4.3, 4.5, 4.6, 4.7, 9.4**
  - _原任务描述（保留备查）_：
  - 🔴 **载体清单按 Wave 0 Gate 2 实测改过**，不是原来的四类：
    - 传播：`<f>` 文本 · `hyperlink@location`（3,138 条工作簿内）· `definedNames`
      （`builtin_self_scope` 2,457 + `user_self_scope` 292 + `user_cross_sheet` 252）·
      `dataValidation/formula1|2`（8 条）· `conditionalFormatting/formula`（6 条）
    - **不是载体**：`conditionalFormatting@sqref` / `dataValidation@sqref` / `mergeCell@ref`
      / `hyperlink@ref` —— OOXML 类型是 `ST_Sqref` / `ST_Ref`，结构性不含 sheet 前缀
      （全库实测 0/440、0/1223、0/37456、0/3950）
    - 登记不传播：3D（全库 **0**）· 外部工作簿（**2,908** 处）· chart（8 部件）·
      pivot（**0** 部件）· `target_not_in_workbook`（definedNames 1,991 + hyperlink 321）
  - 🔴 `dataValidation` 只能扫 `<formula1>` / `<formula2>` 的**内容**，不得扫整个元素
    - ⚠️ **原文「`error=` 属性里的中文提示会造成假阳性（实测发生过一次）」经全库复测
      不成立，已改正**：`error=` 48 处、`prompt=` 14 处含中文，被分词器误判成限定引用的
      是 **0 处** —— `prompt=` 里确有「根据D2-2 审计调整前的账龄数据填写」这种含 sheet 名
      的提示，但其后没有 `!`，`_QUALIFIED_PREFIX_RE` 不命中。只扫子元素内容仍然要做，
      但它是**结构性预防**（不依赖那个巧合），不是在修一个已发生的假阳性
    - 🔴 **真实发生的假阳性在另一处**：`conditionalFormatting/formula` 的 41 处含 `!` 里
      **32 处是中文感叹号**（`"报表未调平!"` / `"调整事项未全部链入试算平衡表…!"`），
      按 `!` 粗暴 grep 会全算成跨 sheet 引用；真跨 sheet 的只有 9 处。挡住它的是分词器
      跳字符串字面量 ⇒ 这就是「扫描必须走 `iter_qualified_references`、不得自己 grep」
      的实证理由
  - 出现未登记载体形态时抛 `UnpropagatedCarrierError`
  - **Validates: Requirements 2.6, 4.1, 4.2, 4.3, 4.5, 4.6, 4.7**

- [x] 9. M1：传播规则接入 `_rewrite_formula_refs`
  - ✅ **2026-09-05 已交付，与 Task 28 同批**（见 Task 28 的合并理由）
  - 前缀分支由**两路改三路**：① 自限定（`'本表'!A1`，等价裸引用 → 位移）
    ② `propagate_sheets` 命中（→ 传播）③ 其余（→ 逐字不动，保守默认）
  - 抽出 `_prefix_sheet_name()` 统一做引号剥离与 `''` 转义还原 —— 原先这段逻辑只长在
    `_prefix_targets_sheet` 里，传播判定若自己抄一份必然漂移；新增
    `_prefix_is_propagation_target()`（空集恒假 ⇒ 零回归靠它）
  - 🔴 **新增 `_ROW_ONLY_PIECE_RE` + `_row_only_piece()`，这是实测补出来的必要项**：
    `_REF_TOKEN_RE` 的第三分支 `\$?\d+:\$?\d+` 会命中**整行区间**（无列标），而
    `_A1_PIECE_RE` 要求列标 ⇒ 对 `$2:$6` 必然 `fullmatch` 失配。不补这一条，
    definedNames 里 `_xlnm.Print_Titles` **整类**会被静默漏传播（D2 上的真实样本
    就是 `'明细表D2-2'!$2:$6`）
  - `_propagated_token()` 按 token 三形态显式分派（带列标 → `_piece` / 整行区间 →
    `_row_only_piece` / 整列区间 `$A:$C` → 逐字不动，因它不含行号）。整列区间落进
    `_piece` 也会被原样退回，但那是**碰巧**对 —— 写成显式分派让「不含行号所以不传播」
    成为可读判断，而不是依赖另一个正则的失配副作用
  - `$` 锁定的绝对行同样传播（AC 2.3）；区间首尾各自判定（AC 2.4）
  - **D2 真实模板行为实测**（`明细表D2-2`，`at=13, count=1`）：含目标 sheet 的公式 38 条，
    `changed` 合计 **10 → 70**，**33** 条输出发生变化；
    `SUMIF('明细表D2-2'!$AI$13:$AI$25,…)` → `$AI$14:$AI$26` ✅；
    definedNames 的 `Print_Area`（`$A$1:$AM$34`→`$AM$35`）与 `_FilterDatabase`
    （`$A$1:$AK$31`→`$AK$32`）末行扩张 ✅；`Print_Titles`（`$2:$6` 在插入点**之上**）
    不动 ✅；外部工作簿 / 3D / 字符串字面量里的表名 / 整列区间 / 指向别的 sheet 的引用
    **全部逐字不动** ✅
  - 🔴 **实测捞出 Task 8 的一条硬要求**：D2 上有 **10 处** `'明细表D2-2'!#REF!` ——
    `_QUALIFIED_PREFIX_RE` 命中前缀但 `_REF_TOKEN_RE` 取不到坐标 ⇒ 传播器不动它（正确），
    但**扫描器必须把「前缀命中而取不到坐标」登记成 `UnpropagatedCarrier`**，不得静默
    跳过 —— 静默跳过会让「有 10 处引用没被处理」这件事不可见。这 10 处是分母
    `unresolvable_cross_sheet_sites`（3,428）在首要载体上的具体实例
  - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**

- [x] 10. T2：Property 4 / 5 / 6 / 7 / 8 插行传播判据
  - ✅ **2026-09-05 已交付**（`test_workbook_row_change_insert.py`，与 Task 11 同批，
    **43 passed / 0.98s**）。判的是**传播器的输出**，不依赖 Task 13 的 apply
  - 🔴 **本任务逼出了一个新参数 `qualified_only`** —— 首次实测时
    `test_bare_references_in_same_formula_are_untouched` **红了**：
    `=SUM(A20:B20)+'明细表D2-2'!F20` 传播后得到 `=SUM(A21:B21)+'明细表D2-2'!F21`，
    **裸引用被一起推走了**
    - 那是错的：裸引用属于**引用侧** sheet（`审定表D2-1`），没人在它上面插行。推走它们
      = 引用侧 sheet 自己的坐标全部错位，且产物仍能打开 ⇒ 静默错行
    - `_rewrite_formula_refs` 原先对裸引用与限定引用用**同一个** `remap`，表达不了这个
      区分；恒等 `remap` 也绕不过（那样限定引用也不动，等于没传播）
    - 已加 `qualified_only: bool = False`（第 10 个 kwonly）：True 时只改带前缀的引用。
      **零回归复核 ok=True 0 差异** ⇒ 纯加法
    - 配了**反面对照** `test_managed_sheet_side_still_shifts_bare_references`：不开开关时
      裸引用**必须**动 —— 否则把开关写成恒 True 也能让前一条绿，而那会让受管 sheet 自身
      插行时坐标全不动
  - P4：`>= at` 的 `+count` / `< at` 不动，三个 count（1/2/5）各测 —— 只测 count=1 时
    「+1」与「+count」分辨不出来；`at-1` 边界单列一条（判据写成 `> at` 时会红）；
    D2 真实模板 **46 处逐处**核对（不抽样），且断言「传播的」与「不动的」两侧都非空
  - P5：四种 `$` 组合全测；断言 `$` 的个数不变。🔴 插行时 `$` 锁定的行**同样**位移 ——
    与 fill-down **相反**（那时 `$` 才意味着不动），两个场景各有判据
  - P6：七种区间边界形态（完全在前 / 完全在后 / 跨插入点 / 首行 == at / 末行 == at-1 /
    count>1 / 单行区间）+ 整行区间 `$2:$6` + 整列区间 `$A:$C`
  - P7：混合公式（两 sheet / 三 sheet 只声明一张）· 裸引用 · 自限定 · 字符串字面量
    （两种实体形态）· 带数字函数名 · **D2 真实模板**上指向别的 sheet 的引用逐字不变
  - P8：3D 用**注入**（全库 0 处）· 外部工作簿用**真实样本**（3,883 处，两种写法）。
    两类都验 ① 输出逐字不变 ② 在 `unpropagated` 里**各自**一条计数 ——
    🔴 只验①不够（静默跳过也能让输出不变）；且计数不得合并（外部簿不传播是设计，
    3D 出现则说明语料变了需要重新裁决，两者处置完全不同）
  - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 9.4**
  - _原任务描述（保留备查）_：
  - 🔴 **首要载体改为 D2**（Wave 0 Gate 1 裁决）：`D/D2-1至D2-4 应收账款….xlsx`，
    受管 sheet `明细表D2-2`（anchor A11），被 4 张 sheet 的 **52 处**公式引用 ——
    它是今天**唯一**既有已审核契约又有真实跨 sheet 引用的 entry，即唯一可端到端执行的样本
  - 3D 引用全库 **0** 处 ⇒ Property 8 的 3D 分支必须用注入变体；外部工作簿 **2,908** 处
    可用真实样本。两者都要逐字不变且各有一条计数
  - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 9.4**

- [x] 11. T2：Property 9 —— K11 的 114 处引用逐处正确
  - ✅ **2026-09-05 已交付，与 Task 10 同批**（`TestProperty9K11EverySiteCorrect`）
  - 分母断言 **恰为 114** —— 这个数同时防「扫少了」与「扫多了」；受管区 `A7:N25` 的
    **19 行全部**被引用到
  - **114 处逐处**核对（不抽样）：每处按它自己的行号判 `>= at` 的 `+count`、其余不动，
    且 sheet 名一个字符不动；额外断言「传播的」与「不动的」两侧都非空 —— 否则
    「该动的动了」与「不该动的没动」只有一半被取证
  - 传播后重新分词，`sheet` 类引用总数仍为 **114** —— 传播只改行号，不得增删引用
    （少了说明某处被吃掉、多了说明产生了意外分词结果）
  - 🔴 **把「K11 不可执行」钉成判据** `test_k11_has_no_per_entry_contract`：断言
    `RG.DELIVERED_PER_ENTRY_CONTRACTS` 里没有 k11、且**有** d2。防两件事：
    ① 有人后来伪造一份 K11 契约当已审契约用 ② D2 掉出登记表后 Gate 1 的「首要载体」
    裁决失效而无人发现。若哪天 K11 真有了已审契约，本条会红 ⇒ 那时应升级为端到端判据，
    不是删掉本条
    - ⚠ 该常量在 `adapters.registry` 而非 `contracts`，首次写错了 import 路径
  - **Validates: Requirements 2.7**
  - _原任务描述（保留备查）_：
  - 受管 sheet `审定表K11-1`（受管区 `A7:N25`），被 `附注披露信息（上市公司）` 与
    `附注披露信息（国企）` 共 114 处公式引用，行号 7~25 共 19 个不同行（Wave 0 复算一致）
  - 🔴 **K11 是结构判据载体，不是可执行载体**：它**没有** per-entry 契约
    （`DELIVERED_PER_ENTRY_CONTRACTS` 只有 b60 / d2 / g7 / h1 四行）⇒ 本条按
    「给定受管区声明后传播器的输出」取证，不得伪造一份 K11 契约当已审契约用
  - 逐处比对：`>= at` 的全部 `+count`，其余不变，总处数仍为 114
  - 断言引用处数 > 0（防空集恒真）
  - **Validates: Requirements 2.7**

- [x] 12. T4：Property 16 / 17 / 18 / 19 / 20 / 32 / 33 / 34 载体判据
  - ✅ **2026-09-05 已交付**（`test_workbook_row_change_carriers.py`，**30 passed / 6.00s**）
  - 🔴 **definedNames 分类的分母改用「现口径」，不沿用清册那组数 —— 差异已定位归因。**
    清册登记 `defined_name_cross=5002` / `target_not_in_workbook=2001` /
    `user_self_scope=292` / `user_cross_sheet=252`；本口径实测 **2,939 / 6 / 267 / 4**
    （另有 `builtin_self_scope` 2,465 / `builtin_cross_sheet` 0 / `global_scope` 197）。
    - 归因：清册生成器用的是它自己那份**历史**口径 `qualified_hits`，不认「带引号外部
      工作簿」（Task 8 才修）。实测历史口径在 definedNames 上数出 **5,097** 条
      `kind=sheet`，比现口径多 **2,158** 条，而那些现在被正确判成 `external`
      ⇒ 清册的 `target_not_in_workbook=2001` 里绝大多数其实是**指向别的文件**的引用，
      被记成了「引用坏了」
    - 口径写进判据 docstring（只取 `kind=="sheet"`，再按 `scope` 分六类），
      并配三条分母非空自检。清册那组数**不动** —— 它是 Wave 0 历史留痕，其生成器刻意
      保持历史口径以维持零回归基线分母稳定
  - **chart 用真实样本 / pivot 用注入**，并把这个差异本身写成判据
    （`test_chart_has_real_sample_while_pivot_needs_injection`）：chart 实测 **8 个部件 /
    1 份模板**（`C24 会计分录 - 细节测试.xlsx`）、pivot 全库 **0** 部件。有真实样本时用
    注入等于放着真数据不验，所以要拦住这种退化
  - ✅ 已交付部分：
    - 地基 = 全库一致性（扫描器 ↔ 改写器，351 份 / 126,565 条公式 / 0 漂移，见 Task 8）
    - **真实样本**：D2 `formula` 42 / `defined_name` 3 / `hyperlink_location` 1 /
      `prefix_without_coordinate` 10；K11 `formula` 114 覆盖受管区 19 行；外部工作簿 3,883 处
    - **注入变体**（全库为 0 或结构性不可能 ⇒ 真实样本会空集恒真）：
      `sqref` / `mergeCell@ref` / `hyperlink@ref` 造带 `sqref="'明细表D2-2'!A1:B2"` 的 XML
      （Excel 不会产出、schema 也不允许），断言 `qualified_total == 0`。
      🔴 用注入的理由：真实语料里这四类恒为 0，「扫不到」在空集上恒真；注入一个
      「若真去扫就会命中」的形态，才能证明扫描器**确实没扫**
      · 3D 两种写法 · pivot 部件 · `prompt=`/`error=` 带 `!` 的提示文本
    - 整列区间 `$A:$C`（全库 66,059 处）既不进 `sites` 也不进不传播登记 —— 不含行号，
      登记它会让不传播计数被 6.6 万条无关项淹没
  - 🔴 **改正了一条我自己写错的断言**：原文与 N1 docstring 都称「`error=` 属性里的中文提示
    造成假阳性（实测发生过一次）」。全库复测**不成立** —— `error=` 48 处、`prompt=` 14 处
    含中文，被分词器误判的是 **0 处**。真实的假阳性在 `conditionalFormatting/formula`：
    41 处含 `!` 里 **32 处是中文感叹号**（`"报表未调平!"`），真跨 sheet 只有 9 处。挡住它的
    是**分词器跳字符串字面量** —— 这才是「扫描必须走 `iter_qualified_references`、不得自己
    grep」的实证理由
  - **Validates: Requirements 4.1, 4.2, 4.3, 4.5, 4.6, 4.7**
  - _原任务描述（保留备查）_：
  - 依 Wave 0 Task 2 的实测规模定判据形态，**逐类带分母**：
    - Property 16 / 34：definedNames 五分类各自的分母（2,457 / 1,991 / 292 / 252 / 10）——
      只断言总数 5,002 不算判据
    - Property 17（**语义已反转**）：往真实模板 zip 级注入带 sheet 前缀的 `sqref`，
      传播器必须**不动它**，且该注入必须被未登记载体判据打红
    - Property 18：chart 用真实样本（8 部件 / 1 份）；pivot 全库 **0** 部件 ⇒ 必须用注入变体
    - Property 32：`hyperlink@location` 三分类（3,138 / 321 / 21）
    - Property 33：`dataValidation/formula1|2`（8 条）+ `conditionalFormatting/formula`（6 条），
      🔴 只扫子元素内容不扫整个元素
  - 未登记载体打红
  - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 9.5**

- [x] 13. N1：`apply_workbook_row_change`（插行分支）
  - ✅ **2026-09-05 已交付**（`test_workbook_row_change_apply.py`，**26 passed / 1.73s**）
  - 受管 sheet 整个复用 `shift_sheet_rows`；引用侧走新增的 `propagate_reference_side`
    （`qualified_only=True`）；definedNames 走 `propagate_defined_names`
  - 落盘版 `apply_workbook_row_change_to_path`：先算完整字节 → 对账 → 临时文件 →
    `os.replace`。**失败即零产物**（判据 `test_failure_leaves_target_untouched` 用篡改的
    声明触发失败路径，断言原文件逐字节未变且无 `.tmp` 残留）
  - 🔴 **新增 `build_insert_plan` / `build_propagation_entry` —— 声明的唯一构造入口。**
    首次实测时我手搓 `PropagationEntry`，当场撞出两类错误：
    1. `ref_after` 手算 ⇒ 与执行时的改写器不是同一份代码，声明与实测天然可能不一致。
       构造器改用 `_rewrite_formula_refs` 生成，与执行**同一个入口**
    2. `row_before` 填成「最小行号」⇒ D2 的 `_FilterDatabase`（`$A$1:$AK$31`）在 `at=13`
       时**首端点不动、末端点动**（31→32），按最小行号填得到 `1 → 1` 被空操作守卫拦掉。
       改为「第一个**真的**位移的行」，`delta` 才恒等于 `±count`
  - 🔴 **`_unescape` 改用 `html.unescape`（认数字字符引用）**。实测全库 **2,591 处**公式
    把 sheet 名写成 `&#24213;&#31295;&#30446;&#24405;!A2`（= `底稿目录!A2`），分布 6 份
    模板（G4/G5/G6/G7/H1/H10），其中 **1,842 处**在不还原时命中不到任何真实 sheet 名
    ⇒ 与 `propagate_sheets` 比对必然失配 ⇒ **静默漏传播**
    - 连带把载体判据的分母改了：`corpus_sheet_refs` 144,155 → **144,904（+749）**，
      其余三类 **各 +0**。逐类归因实测确认 +749 **全部**来自含数字字符引用的公式
      （2,941 条）⇒ 是「先前没看见」而非「先前分错类」
    - 零回归基线 **ok=True 0 差异** —— 生成器保持它自己那份历史口径 `_unescape`，
      这次证明了那份「重复」是有理由的
  - 🔴 **`_rewrite_text_preserving_unchanged`：没改动的载体退回原始字节。** 若无条件走
    「还原 → 改写 → 重新转义」，没有任何改动的公式也会因转义风格变化产生字节差异
    （`&#24213;` → `底`）⇒ 「除声明条目外零字节变化」判据会对一大批无关公式报警，
    把真正的越权改动淹掉
  - 🔴 **受管 sheet 过两遍改写，钉住「不得双重位移」**：apply 对受管 sheet 先跑
    `shift_sheet_rows` 再跑 `propagate_reference_side`，自限定引用（`'受管表'!A20` 写在
    受管表上）同时落在两遍的定义域边缘。实测 `shift_sheet_rows` **不传** `current_sheet`
    ⇒ 自限定落进「其余」分支逐字不动，第二遍传播正好补上，净效果位移**一次**。
    - ⚠ 这靠一个巧合成立 ⇒ 用 AST 判据 `test_shift_sheet_rows_does_not_pass_current_sheet`
      锁死。哪天有人给它补上 `current_sheet`（看着像"修正"）会当场变红，并在报错里给出
      正确修法（受管 sheet 只跑 shift，不再跑传播）
    - D2 上恰好没有自限定引用 ⇒ 该风险只能用注入取证
  - **D2 真实产物实测**：46 处扫到 → 44 条声明（2 处一个片段都不动：`Print_Titles` 的
    `$2:$6` 全在插入点之上、`hyperlink@location` 的 `A1`）→ 实测 60 + 2 个片段，
    逐载体对账吻合；48 个部件里**恰 5 个**字节变化（workbook.xml + 受管 sheet +
    3 张引用侧 sheet）；`styles.xml` / `sharedStrings.xml` / `theme1.xml` / rels /
    `[Content_Types].xml` 逐字节相等；未改动部件的 `ZipInfo`（`date_time` /
    `compress_type`）也不变；**openpyxl 真实加载成功**且被传播的公式读出来是改后文本
  - 「被排除的 2 处必须**真的**一个片段都不动」单列一条判据 —— 没有它，
    `build_propagation_entry` 里任何「返回 None」的 bug 都会表现为「声明少了但对账依然
    吻合」（因为实测那侧也少了）
  - **Validates: Requirements 2.1, 4.4, 5.2, 5.4**
  - _原任务描述（保留备查）_：
  - 受管 sheet 复用 `shift_sheet_rows`；引用侧按传播条目定点改写
  - 传播失败整次放弃（临时文件 + `os.replace`）
  - **Validates: Requirements 2.1**

- [x] 27. M1 + T2：新插入行的跨 sheet 相对引用随行平移（承接前置 spec 的 R12.4）
  - ✅ **2026-09-05 已交付。** `translate_formula_rows` 传 `translate_qualified_rows=True`；
    十二条形态实测全对（含 AC 10.4 的混合形态与「绝对+相对+3D」三合一形态）
  - 🔴 **新参数与 `propagate_sheets` 是两个开关，不可合并** —— 差别在「谁动了」：
    `propagate_sheets` 是**目标 sheet 的行被推走了**（只对声明过的 sheet 生效）；
    `translate_qualified_rows` 是**公式自己被复制到别的行**（Excel 填充柄对工作簿内
    所有相对引用一视同仁，不问目标 sheet 动没动）。合成一个开关会让 fill-down 需要先
    知道「目标 sheet 动没动」—— 而那与它无关。对照表写进 `_prefix_rows_follow` 的 docstring
  - 🔴 **实测捞出一条既有缺陷（本次修掉）**：3D 引用有两种写法，`_QUALIFIED_PREFIX_RE`
    的 `span` 分组**只认得不带引号的那种**。Excel 对含标点的 sheet 名加引号，而 3D 区间的
    冒号**落在引号内** ⇒ `'明细表K11-2:明细表K11-3'!` 整段被 `first` 分支贪婪吃掉，
    `span` 永不命中，剥引号后得到一个**含冒号的假 sheet 名**，于是被当普通 sheet 平移
    （实测 `F29`→`F30`，违反 AC 10.3）。修在 `_prefix_sheet_name` 一处：剥引号**之后**
    再查冒号（真实 sheet 名不允许含 `:`，Excel 明令禁止 `: \ / ? * [ ]`）。
    该盲区是**既有的**、非本 spec 引入 —— 此前所有带前缀的引用一律逐字不动，盲区不可见
  - 同步改正 `translate_formula_rows` 的 docstring（AC 10.6）：删掉「Excel 的填充柄也是
    这个行为 —— 相对引用只在**本** sheet 内平移」那段与 Excel 语义相反的叙述
  - **基线已按新行为重新冻结**，`--apply` 前做了**七条机械核验**（不靠眼看 364 处差异）：
    ① 两个 insert 情景逐字不变（**0** 处）② 扫描面指标不变（公式条数/引用处数/3D/外部
    工作簿全等）③ `filldown` digest 在 **180 / 351** 份模板上变化 ④ `filldown` 的
    `changed` **只增不减**（**0** 处减少）⑤ 分类样本 insert 输出 **0** 处变化
    ⑥ 3D 引用在三情景下逐字不动 ⑦ 外部工作簿 6 条全不变
  - 🔴 **顺带修掉基线自己的一个盲区**：`filldown` 情景原先**不传** `translate_qualified_rows`
    而真实入口传了 ⇒ fill-down 语义改完后基线**没有变红**，与生成器/守卫里「Task 27 必然
    变红」的声明矛盾。**一条声称在观测某函数、参数却与它不同的判据，观测的是一条没人走的
    路** —— 这类盲区不以假红暴露，只让本该变红的时刻悄悄溜过。已新增
    `test_filldown_scenario_matches_real_entrypoint_params` 用 **AST** 锁死「真实入口传的
    关键字实参 ⊆ 情景 kwargs」
  - **翻转了两条把缺陷钉住的判据**（两者的 docstring 都明写「修好后必须翻转」）：
    - 零回归守卫的 `test_filldown_currently_does_not_shift_cross_sheet_refs`
      → `test_filldown_shifts_cross_sheet_relative_refs`。**不只断言「有平移」**
      （那在「把所有限定引用无脑位移」时也成立、而那会撞坏表名），而是同时断言
      「目标格行号平移了 **且** sheet 名一个字符没动」+ 绝对行不动
    - 上游 `test_excel_row_shift.py` 的 `test_cross_sheet_references_are_left_verbatim`
      **拆成两条**：`..._on_existing_rows_stay_verbatim`（既有行不动，核 ≥2 行）与
      `..._on_inserted_rows_are_translated`（新行按**各自偏移量**平移，逐引用比对
      表名/列/绝对行三项，并加反面对照「两个新行的引用必须互不相同」——
      相同即照抄）
  - 实测 **257 passed / 2 skipped**（辐射面 9 个文件）+ materialize 端到端
    **236 + 311 passed**（Task 38 / 42 / 43 / 37，它们真的走 `shift_sheet_rows` 产出新行公式）
  - **Validates: Requirements 9.0, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7**
  - _原任务描述（保留备查）_：
  - 🔴 **Wave 0 实测的第二个方向**，与 Task 9 的传播方向相反：Task 9 是「引用侧 → 受管
    sheet」（别人指向我、我插行了、别人跟着改）；本任务是「受管 sheet 新行 → 别的 sheet」
    （我新增了行、新行的取数源要跟着走）
  - 现状实测（生产 `translate_formula_rows`，`from_row=25 → to_row=26`）：
    `SUM(F25:G25)` → `SUM(F26:G26)` ✅ ·
    `='明细表K11-2'!F29` → 🔴 `F29`（Excel 填充柄给 `F30`）·
    `=Sheet2!F29` → 🔴 `F29` ·
    🔴 混合 `='明细表K11-2'!F29+G25` → `='明细表K11-2'!F29+G26`
    **同一条公式内裸引用平移了、跨 sheet 引用没平移**
  - 后果：新插入行与样式来源行**指向同一个源格** ⇒ 静默重复取数。前置 spec 的
    `test_excel_row_shift.py` docstring 已把这条登记为已知限制并明写交本 spec 承接
  - 判据必须含**混合形态**（AC 10.4）：单独测两类引用发现不了自相矛盾这一形态
  - 同步改正 `translate_formula_rows` 的 docstring —— 它现在写「Excel 的填充柄也是这个行为
    —— 相对引用只在**本** sheet 内平移」，**与 Excel 语义相反**，且与前置 spec 测试里的
    描述互相矛盾（AC 10.6）
  - 以现有参数形态承接，不新造 A1 改写入口（Property 27 用 AST 锁死）
  - ⚠ 改 `excel_row_shift.py`（M1）⇒ 与 Task 6 / 9 同属门后任务，须 Task 101 门开才动
  - **Validates: Requirements 9.0, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7**

---

### Wave 3 —— 删行与收缩

- [x] 14. N1：`shrink_sheet_rows` —— 受管 sheet 内的删行
  - ✅ **2026-09-05 已交付**（Wave 3 四个任务同批，判据见 Task 18）
  - **刻意不复用** `shift_sheet_rows`：那个函数的语义是「造新行 + 下移」，删行是
    「移除 + 上移」，共用一个实现会让两边的边界条件互相干扰
  - 🔴 **只改结构，不改公式文本**：`<row r=>` 与其中每个 `<c r=>` 一起改、`<dimension>`
    收缩；公式里的行号由传播那半（负 delta 的 remap）处理。判据用「`<f>SUM(A20:B20)</f>`
    原样保留」把这个分工边界钉住 —— 混在一起时任何一边的 bug 都会被另一边掩盖
  - **Validates: Requirements 3.1, 3.2, 3.6**
  - _原任务描述（保留备查）_：
  - 被删区间的行与其格移除；其后行上移 `count`
  - 删除越过受管区抛 `RowChangeOutOfRegionError`
  - **Validates: Requirements 3.1, 3.2, 3.6**

- [x] 15. N1：删行的业务键留痕
  - ✅ **2026-09-05 已交付**（`resolve_deleted_row_keys`）
  - 优先级 `row_uuid` → 稳定序号 → 抛 `MissingRowIdentityError`。🔴 **不可颠倒**：
    `row_uuid` 是行的**身份**（行移动后仍指同一笔业务数据），稳定序号只是**位置**的稳定
    表达 —— 删行后它会指到另一笔上
  - 空串/空白不算键（否则「有键」会被空字符串蒙过去）；重复键拒绝（无法一一对应到被删行
    ⇒ 事后无从复原）；计划层另有「键数 == 被删行数」守卫
  - D2 的 `row_identity` 实测是 `/rows/*/rowId`（`RowIdentityKind.field`）
  - **Validates: Requirements 3.7**
  - _原任务描述（保留备查）_：
  - `deleted_row_keys` 取值优先级：row_uuid → 契约稳定序号 → 抛 `MissingRowIdentityError`
  - **Validates: Requirements 3.7**

- [x] 16. N1：悬空引用检测与 fail-closed + `undeletable_rows`
  - ✅ **2026-09-05 已交付**（`find_dangling_sites` / `find_undeletable_rows` /
    `DanglingSite`；拦截在 `build_delete_plan`，即**计划阶段**，不等写盘）
  - 🔴🔴 **本任务实测更正了 requirements.md 3.8 的判据与全部三个数据。**
    原表述「`undeletable_rows` = 受管区内**被引用侧引用到**的行」**过严**，会把本可安全
    删除的行锁死。三种引用形态在删行下的 Excel 语义完全不同：
    | 形态 | 样本 | 删掉被指的那行 |
    |---|---|---|
    | **单格** | `'明细表D2-2'!AC26` | 🔴 变 `#REF!` |
    | 区间**端点** | `$AI$13:$AI$25` 删第 13 或 25 行 | ✅ 收缩成 `$AI$13:$AI$24` |
    | 区间**内部** | 同上，删第 20 行 | ✅ 同样收缩 |
    | 区间被**删光** | 13..25 全删 | 🔴 变 `#REF!` |
    删掉区间内部一行，Excel 的语义就是「那笔数据没了，合计少算一笔」—— 这正是删行
    **应有**的效果，不是损坏
  - 🔴 **原文声明的 D2 = `{13, 25, 26}` 三个数逐个都不该在**，实测逐项核过：
    - **13 / 25** —— 只作为**区间端点**出现，数据区内**单格引用 0 处**
    - **26** —— 是**合计行**（`A26`=`合计`，`footer_anchor.marker` 印证），**不在数据区内**。
      它确有 24 处单格引用，但删数据行时它**上移** ⇒ 属 AC 3.3 的传播，不属「不可删」
    - ⇒ 修正后 **D2 = `∅`，13 行全部可删**；**K11 = 19 行全部**（每行各 6 处单格引用）
      ⇒ 「100% 阻断」的实测结论**成立**，本条存在的理由不受影响
  - 🔴 **`region` 的真实边界也一并查清**：D2 数据区是 **13..25**，不是我此前在 Task 7/10/13
    判据里用的 11 —— `anchor='A11'` 是**表头**起点，`header_rows=2` ⇒ 数据首行 13
    （`formula_mask=('Q13:Q25','S13:S25','AB13:AB25')` 印证）。判据从契约**现算**，不写死
  - 🔴 **第②条判据首版写错，实测当场打红**：原写「区间完全落在受管区内 ⇒ 锁」，而 D2 的
    `$AI$13:$AI$25` 覆盖的 13..25 恰好**就是**整个数据区 ⇒ 13 行全被锁。改为
    「区间覆盖行数 **≤ 本次删除行数**」才对 —— 删 1 行只让区间收缩，只有删光才 `#REF!`。
    `count` 参数默认 1（HTML 侧逐行删的粒度），传 13 时锁定集正确地变成全区
  - `DanglingReferenceError` 携带**完整清单**（最多列 12 条 + 省略号），点名
    `part!locator 引用原文（reason，坏在第 N 行）` —— 只报第一处会让调用方逐个试错
  - `allow_ref_errors` 默认 False ⇒ fail closed；刻意做成必须**显式**打开：静默写 `#REF!`
    会让底稿在用户打开时才暴露损坏，那时已无从追溯是哪次同步造成的（AC 3.5）
  - **Validates: Requirements 3.4, 3.5, 3.8**
  - _原任务描述（保留备查，⚠ 其中的 `{13, 25, 26}` 已被上述实测推翻）_：
  - 计划阶段就发现（不等写盘），抛 `DanglingReferenceError` 并携带完整清单
  - 仅契约显式声明允许时才写 `#REF!`
  - 🔴 **Wave 0 Gate 4 裁决新增**：计划必须同时携带 `undeletable_rows`（受管区内被引用侧
    引用到的行集合，AC 3.8 / Property 35），供 HTML 侧在**发起删行之前**把这些行标成锁定
  - 判据两侧都要：K11 上应为受管区全部 19 行（100% 阻断）；D2 上应为 `{13, 25, 26}`
    三行、其余可删。两侧均断言「不可删行数 > 0」且「≠ 受管区行数」（防空集与防恒等于全区）
  - ⚠ `undeletable_rows` **不得替代** 3.4 的后端拦截（前端标记可被绕过）
  - **Validates: Requirements 3.4, 3.8**

- [x] 17. N1：删行的引用侧向上传播
  - ✅ **2026-09-05 已交付**（`apply_workbook_row_change` 的 delete 分支 + 负 delta remap）
  - 指向被删区间**之后**的引用 `-= count`；之前的不动；区间引用**收缩**
    （`$A$13:$A$25` 删 1 行 → `$A$13:$A$24`）
  - 判据断言删行条目的 `delta` 恒为**负** —— 方向错了等于把数据指到反方向
  - 真实形态取证：D2 合计行（26）的 **24 处**引用在删数据行后全部上移到 25，
    产物里 `'明细表D2-2'!AC26` → `AC25` 且无残留
  - **Validates: Requirements 3.3**
  - _原任务描述（保留备查）_：
  - 指向被删区间之后的引用行号 `-= count`
  - **Validates: Requirements 3.3**

- [x] 18. T3：Property 10 / 11 / 12 / 13 / 14 / 15 / 35 删行判据
  - ✅ **2026-09-05 已交付**（`test_workbook_row_change_delete.py`，**38 passed / 1.65s**）
  - **两个载体分工**（缺任一侧就有一条路径从未被执行）：
    - **D2** = **正常路径**（删得成）—— 区中间删一行不抛、计划建成、44 条传播、
      产物 openpyxl 打开成功且 `max_row` 减 1
    - **K11** = **阻断路径**（100% 拦下）—— 删第 16 行命中 **6 处**单格引用，
      `DanglingReferenceError` 点名 `sheet4.xml` / `sheet5.xml` 的具体位置
    - 🔴 配 `test_both_sides_are_non_degenerate`：断言两侧结果**必须不同**（D2=0 行 /
      K11=19 行）—— 拦的是「两侧碰巧都对但实现其实是常量」这类退化
  - **P35 反面对照** `test_multi_row_delete_widens_the_locked_set`：`count=1` ⇒ ∅，
    `count=13` ⇒ 锁全区。没有它，把第②条写成恒不命中也能让 D2 那条绿
  - **P12 的核心一条** `test_range_partially_deleted_is_not_dangling`：区间内部/端点被删
    都**不算坏**；配 `test_range_fully_deleted_is_dangling` 验删光时确实拦
  - **P13** `test_dangling_list_is_complete_not_first_only`：6 处一次给全，逐条 reason
    与 broken_rows 都核
  - 退化区间 `A20:A20`（全库 0 处）用**注入**取证
  - 🔴 **翻转了 Task 13 的一条判据**：`test_delete_kind_is_refused` →
    `test_delete_kind_is_now_implemented`。它钉的是「当时还没有的能力」，Wave 3 实现后
    **必然变红** —— 这正是该有的行为。翻转后钉住新事实（delete 走 `shrink_sheet_rows`，
    与 insert 的 `shift_sheet_rows` 是两条独立路径）
  - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8**
  - _原任务描述（保留备查）_：
  - Property 13 须在 K11 受管区中间删一行、命中 114 处引用之一，据此打红 Property 12
  - 🔴 Property 11 / 12 的**正常路径**载体用 **D2**（唯一有真实混合形态：3 行阻断、
    其余可删）；K11 只用于 100% 阻断这一极端形态 —— 只在 K11 上取证会让「部分阻断」
    这条路径从未被执行过
  - Property 35：`undeletable_rows` 两侧判据（K11 = 19/19，D2 = `{13, 25, 26}`）
  - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8**

---

### Wave 4 —— 验证侧与接线

- [x] 19. M3：未管理区域摘要按**声明**传播量归一化
  - ✅ **2026-09-05 已交付**（判据见 Task 20）。**M3 = `excel_extract.verify_unmanaged_regions`**
  - 落点找准了：引用侧 sheet 落在 `_classify_parts` 的 **`other_sheet_parts`** 桶，
    原本走 `_part_digest` **逐字节**比对 ⇒ 传播必然被判漂移。不是「保守地安全」，
    而是让传播功能**永远无法通过验证**
  - 新增 N1 的 `normalise_propagated_part` + `assert_propagation_declared_exactly`；
    `excel_extract` 侧新增 `_propagation_normalised_digest`，并给
    `unmanaged_region_digest` / `verify_unmanaged_regions` 加 `propagation` 参数
    （只给 **after** 侧，与 `row_shift` 同一条纪律）
  - 🔴 **归一化是「逐条逆替换**声明**」，不是「整体反向 remap」**。差别是判据的全部意义：
    | 做法 | 实测==声明 | 实测≠声明 | 传播之外的改动 |
    |---|---|---|---|
    | 放宽（跳过该桶） | 过 | **过**（错） | **过**（错） |
    | 整体反向 remap | 过 | 过（错） | 形态像位移的**过**（错） |
    | **逐条逆替换声明** | 过 | **红** | **红** |
    整体 remap 等于让被检查对象自己声明自己合法 —— design.md 明确拒绝的方案
  - 🔴 **单一真源**：`excel_extract` 侧**不**重写逆替换逻辑，调 N1 的
    `normalise_propagated_part`。抄第二份必然与执行侧漂移，已用 AST 判据锁死
  - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**
  - _原任务描述（保留备查）_：
  - 归一化只动行号；`t`/`s`/`f`/`v` 逐字进摘要
  - 实测传播 ≠ 声明抛 `PropagationDriftError`
  - 引用侧除声明条目外任何字节变化判漂移
  - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**

- [x] 20. T1：Property 21 / 22 / 23 验证侧判据 + 变异
  - ✅ **2026-09-05 已交付**（`test_workbook_row_change_verification.py`，**14 passed / 1.21s**）
  - **P21**：D2 插一行后，4 张引用侧 sheet 逆归一化回改前，**逐字节相等**
  - **P22 四个变异全部打红**：
    - 多改一处**未声明**的引用 ⇒ 红（这是「逐条逆替换」优于「整体 remap」的唯一可执行
      证据 —— 整体 remap 会把它一并还原从而放过）
    - 声明了但**产物里没做** ⇒ 红（`reverted != declared`）
    - 改了个 **`<v>` 值**（非位移性改动）⇒ 红（钉住 AC 5.3：归一化只动行号）
    - 改了 **`s=` 样式** ⇒ 红
    - 配 `test_detector_is_not_vacuous`：**未**变异时必须**不**抛 —— 上面四条
      `pytest.raises` 在「检测器恒抛」时也会绿，本条是它们的分母
  - **P23 接入真实入口**（只测 helper 不够 —— 那只证明「helper 会算」，不证明「验证真的
    用了它」；没有本类，`propagation` 可能是**死参数**而所有 helper 判据依然全绿）：
    - AST 断言 `unmanaged_region_digest` 函数体**真的读**了 `propagation`
    - AST 断言带 `propagation=` 的 `unmanaged_region_digest` 调用**恰好 1 处**（after 侧）
    - AST 断言验证侧走的是 N1 的 `normalise_propagated_part`，没自己抄一份
    - 端到端：`_propagation_normalised_digest`（真实算 digest 的那个函数）算出的
      「改后归一化」digest == 「改前逐字节」digest
    - 🔴 反面对照：**不**给 `propagation` 时 4 张 sheet 的原始字节**必须都不同** ——
      证明归一化确实必需，而不是「反正都相等」（否则恒等函数也能让上一条绿）
  - 🔴 **实测打红一次，改出了更强的判据**：`normalise_propagated_part` 首版按条目逐条
    `replace` 并 `reverted += 1`，D2 上 **18 条声明只数出 4** —— 因为
    `SUMIF('明细表D2-2'!$AI$13:$AI$25,…)` 这段文本出现在 18 个不同单元格里，而
    `str.replace()` 一次就把全部出现换掉了。改成**按出现次数**计量后，判据不只要求
    「这段文本出现过」，还要求出现**次数**恰好等于声明数（少一处=有条目没做；
    多一处=有未声明的改动被写成了与声明相同的形态）。并加
    `test_occurrence_count_not_distinct_text_count` 把「同一文本对应多条条目」
    这个真实形态钉住（冻结 18 条 / 4 段），防实现退回按条目计量
  - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**
  - _原任务描述（保留备查）_：
  - 变异：把实测差异塞进归一化时必须打红
  - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**

- [x] 21. M2：`plan_managed_writes` 接工作簿级计划
  - ✅ **2026-09-05 已交付**（`test_workbook_row_change_wiring.py`，**13 passed / 1.09s**）
  - **M2 = `excel_materialize.plan_managed_writes`**。三个关口用**同一份**声明：
    1. **计划期冻结** —— `MaterializePlan` 新增 `workbook_row_change` 字段（默认 `None`）；
       `plan_managed_writes` 在 `row_shift is not None` 时调
       `plan_workbook_row_change_for_insert` 扫一次载体并冻结声明
    2. **apply 期按声明改** —— 新增 `_apply_workbook_propagation`，在
       `apply_plan_zip_with_report` 的**位移之后、写格之前**执行
    3. **verify 期按同一份归一化** —— `verify_unmanaged_regions(propagation=...)`
  - 🔴 **apply 期不重跑扫描**（AST 判据锁死）：重扫会让 apply 与 plan 成为两个真源，而
    verify 的归一化只认 plan 那一份 ⇒ 任何不一致都表现为「验证判漂移」而真因是
    「apply 没按声明做」
  - 🔴 **受管 sheet 不在传播里改**：那半由 `shift_sheet_rows` 处理（裸引用 + 自限定），
    重复改会双重位移
  - 🔴 **顺序判据用 AST 而不是 `str.find`**：`apply_plan_zip_with_report` 的 docstring 里
    写着「最后才 `_patch_sheet_xml` 写格」，字符串查找会命中那句话（偏移 379）而不是真正的
    调用（偏移 1601）⇒ 判据在**正确**的代码上打红。首版就踩了这个坑，已改成按 AST 的
    `lineno` 排序取调用顺序
  - **零传播路径逐字节不变**：`row_shift is None` 或工作簿里没有跨 sheet 引用指向受管 sheet
    时 `workbook_row_change` 为 `None`，代码路径与本 spec 之前完全相同。
    `plan_workbook_row_change_for_insert` 在「有引用但一条都不需要改」时也返回 `None`
  - fail-closed 两条：声明要改的 part 不在 zip 里 ⇒ 抛；声明 N 处但实际只改了 M 处 ⇒ 抛
  - ⚠ `MaterializePlan.dynamic_column_columns` 是 **Mapping** 而不是 tuple（`as_dict()`
    对它调 `.items()`）—— 判据里造最小 plan 时填 `{}`
  - **Validates: Requirements 1.1**
  - _原任务描述（保留备查）_：
  - 保留并强化残余 fail-closed 分支；不得为满足接线而放宽既有判据
  - **Validates: Requirements 1.1**

- [x] 22. M4：撤销前置 spec 的两条排除
  - ✅ **2026-09-05 已交付**。`excel-structural-row-insertion-and-shift-aware-verification`
    的 **R12.1**（删行）与 **R12.4**（跨 sheet 联动）从「已承接」升级为「**已交付并接线**」，
    各自补了交付事实与接线点
  - 🔴 **R12.4 连带翻转了上游 spec 的一条判据**
    （`test_excel_row_insertion_wiring.py::test_unmanaged_regions_are_equivalent_under_the_declared_plan`）：
    翻转前 `row_shift` + `total_formula_rows` 两个声明足以判等价；翻转后**少传
    `propagation` 就判漂移**。这不是判据变弱，而是**多了一类必须声明的改动** ——
    K11 上实测首个差异是 `workbook_and_styles`（definedNames 落在那一桶）
  - 🔴 **「跨 sheet 引用逐字不动」这条旧保证已不再成立，也不该成立**：它当时的作用是
    「不改坏」，现在的正确行为是「按声明联动」。上游的零回归基线（144,154 处逐字不变）
    仍然守着「**没有计划时**不得擅自改」这一半 —— 那一半永远有效
  - **Validates: Requirements 7.1**
  - _原任务描述（保留备查）_：
  - `excel-structural-row-insertion-...` 的 R12.1 / R12.4 改为「由
    `excel-workbook-wide-row-change-propagation` 承接」
  - 判据：两个 spec 的范围边界不再互相矛盾
  - **Validates: Requirements 7.1**

- [x] 23. T1：Property 27 —— A1 改写入口仍然唯一
  - ✅ **2026-09-05 复跑通过**（Wave 4 各任务交付后随本 spec 全量一起绿）
  - Wave 1~4 累计给 `_rewrite_formula_refs` 加了三个 kwonly（`propagate_sheets` /
    `translate_qualified_rows` / `qualified_only`）、新增了 `iter_qualified_references`
    与 `shrink_sheet_rows`，A1 改写 owner 仍**只有** `_rewrite_formula_refs`
  - `shrink_sheet_rows` 刻意**不**改公式文本（只改 `<row r=>` / `<c r=>` / `<dimension>`）
    ⇒ 它不构成第二个 A1 改写入口，这一点由 Task 14 的「`<f>` 内容原样保留」判据印证
  - **Validates: Requirements 7.1**
  - _原任务描述（保留备查）_：
  - AST 级：`excel_row_shift` 里做 A1 行号改写的函数只有 `_rewrite_formula_refs`
  - ✅ **基线已在 Wave 0 交付**：T5 的 `a1_rewrite_owners()` + `test_single_a1_rewrite_entrypoint`
    （判据落在 `_A1_PIECE_RE` 的 AST owner 集合）+ `test_a1_owner_detector_fires_on_second_entrypoint`
    （反向自检：喂一份有第二入口的合成源必须报出两个 owner）。变异检验已 RED
  - 本任务只需在本 spec 收口时**复跑**该基线并把 T1 侧的引用接上，不重写判据
  - **Validates: Requirements 7.2, 7.3**

---

### Wave 5 —— 可达性与性能

- [x] 24. G1 + D1 + T7：可达性清册生成器（**已于 Wave 0 执行，见下「为什么能提前」**）
  - ✅ **2026-09-04 已交付**。产物三件：G1 生成器（`--check` / `--apply`）+ D1 清册 JSON
    （100 KiB，入库）+ T7 守卫（**22 例绿**，现算 4.5 秒，变异 **9/9 RED**）
  - 🔴 **为什么能从 Wave 5 提前到 Wave 0**：原 rationale 是「需等传播能力落地才知道哪些
    `blocked`」。**Gate 1 的裁决把这条依赖消掉了** —— `blocked` 的判定依据变成「该 entry
    有没有已审核契约」，今天就完全可判定。唯一要等传播落地的是「有契约且有传播需求的」
    从 `pending_implementation` 翻成 `propagated`，今天只有 D2 一条 ⇒ 拆出 **Task 29** 承接。
    清册本体只读、零文件冲突 ⇒ 不受 Task 101 阻断
  - **136** 份受影响模板逐份登记受管 sheet 候选、引用侧 sheet、引用处数、状态与原因
  - 状态与原因都是**封闭词表**：`propagated` / `blocked` / `out_of_scope` ×
    `no_projection_contract` / `pending_implementation` / `no_propagation_demand`；
    实测 >90% 的受影响模板以 `no_projection_contract` 阻塞（与 Gate 1 裁决一致）
  - 极端组合 **10** 个单独登记，最大 **63,240**（C24 的 `2025假期清单`），前四份带 Gate 3
    冻结耗时 + 阈值 2,000 ms。**耗时是冻结常量不重测** —— 重测会让 `--check` 每次都报差异
  - 🔴 **三向锁死**（design.md 分母表 ↔ 清册 JSON ↔ 现算）：守卫**解析 design.md 的表**
    逐键比对，不把数字硬编码。分母表新加 `key` 列作机器键。改真源不改代码、或改代码不改
    真源，都会打红
  - 🔴 **AC 6.5 的宿主定位**：走 `contract.template.relative_path` + `template_sha256`
    （**内容寻址**），顺带白得一条模板漂移判据。实测 manifest 的
    `wp_match.wp_code_patterns` **不可用**（是从组件名派生的 `D2A`/`G7L`/`H1F`，
    `_index.json` 里查不到）；清册另登记 `host_ambiguity` 量化「按名定位会多歧义」
    （最大同名冲突 **39** 份模板）
  - **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 8.5**
  - _🔴 三向锁在首次运行时抓出的四处真源缺陷（均已修）_：
    1. **分母表把两个口径混成一行**：定义写「指向同工作簿内另一张**真实存在** sheet」，
       数值却取自不做存在性过滤的基线口径 ⇒ 拆成 `cross_sheet_sites` **144,154**（全部
       限定引用，零回归基线用）与 `resolvable_cross_sheet_sites` **140,726**（目标真实
       存在，传播用），差值 **3,428** 处是权威模板里**已坏**的引用（18 份模板），单列分母
    2. `sheet_name_looks_like_a1_sites` 同源口径差：**15,066 → 18,491**（按全部限定引用计，
       该防护对目标是否存在一视同仁）
    3. **definedNames 的 `builtin_other_sheet` 类名与它自己的样本自相矛盾** ——
       样本 `_xlnm._FilterDatabase → '[1]关联交易-存款'!#REF!` 本身就是「目标不在本工作簿」
       ⇒ 五类归并为四类，`target_not_in_workbook` **1,991 → 2,001**，和恰为 5,002
    4. 🔴 **我自己的转述错误**：「同名 sheet 出现在 **41 份**模板」是凭印象写的，实测 **39**
       —— 已在 5 个文件 6 处统一改正。这条正是「守卫解析真源」而非「守卫硬编码数字」
       才能抓到的
  - _变异检验捞出的两条判据缺陷（均已修）_：
    1. `test_host_binding_is_content_addressed` 原先**读生成器写下的 `template_sha256_matches`
       布尔值** = 守卫在核对自己写的数字（假绿第②源）⇒ 改为独立重算 sha256，并加
       `test_binding_verifier_detects_injected_digest_drift` 注入错 digest 做反向自检
    2. `test_sheet_name_lookup_would_have_been_ambiguous` 只查磁盘清册不查现算 ⇒
       生成器侧退化被 `test_inventory_matches_current_computation` 抢先报出（WRONG-TEST）
       ⇒ 改为两侧都查。**这与 Task 6 那条是同一形态，已成规律：只读冻结产物的判据抓不住
       生成器侧的退化**
  - _另一条无效变异用例（登记给 E）_：把 `template_sha256_matches` 短路成 **`True`** 判 GREEN
    —— 在「本来就全部匹配」的状态下它不改变任何可观测结果，是**无效用例**而非守卫缺陷；
    敏感做法是短路成 `False`，或注入一个不匹配的 digest

- [x] 29. T7：清册状态翻转复核（**门后**，承接 Task 24 拆出的部分）
  - ✅ **2026-09-05 已收口**（`test_workbook_row_change_reachability.py`，**25 passed**）
  - 🔴 **本任务是「守卫先抓到、再收口」的实例，值得记下过程**：Task 13 落地后有人改了 G1
    生成器（+26/-7：`REASONS` 加 `implemented`、D2 按 `demand` 翻转、
    `affected_templates` 改为按 `in_contract` 分支），但**没重跑 `--apply`**
    ⇒ Task 24 的守卫 `test_inventory_matches_current_computation` 当场打红
    「`contracted_entries` 变了」。这正是三向锁要拦的形态：真源改了、冻结产物没跟上
  - **先验证再 `--apply`**（不先信清册的声明）：`propagated` 是**声明**，不是证据
    ⇒ 先跑 Task 8~13 的 240 例全绿确认传播能力真落地，才重冻结清册
  - diff 规模复核（规则 3）：**6 插 5 删** —— D2 的 `state`/`reason` 各一处 ×2（contracted
    与 affected 两侧）+ 词表新增 `implemented`。其余 135 份与 3 个 `out_of_scope` 逐字不变
  - 🔴 **本轮新增两条判据，把「人工看 diff」固化成可复算的守卫**：
    1. `test_only_d2_flipped_to_propagated` —— 翻成 `propagated` 的 entry 集合**恰为**
       `{xlsx/gt-d2-accounts-receivable}`，D2 的 `propagation_demand_sites` **恰为 52**，
       受影响模板状态分布**恰为** `{(blocked, no_projection_contract): 135,
       (propagated, implemented): 1}`。判据形态刻意**按状态计数**而非「diff 只有 N 行」——
       后者依赖 git 工作树，在干净 checkout 上无从求值
    2. `test_all_three_states_are_reachable` —— 三态**各自**被真实取到。🔴 本轮之前
       `propagated` 是个**从未被使用**的状态值（词表里列着、清册里一条都没有），那时
       Task 24 的守卫只能验「词表没漂移」，验不到「这个状态真的可达」= 空集上恒真
  - ⚠ **他人那次改动顺带修掉了我上轮的一处真缺陷**（已在其注释里点明）：
    `"blocked" if not in_contract else "blocked"` 是**两个分支完全相同**的三元。它当时
    不影响结果（那时两类都该是 blocked），但把「这一维本该随契约分支」这件事藏了起来。
    与我上轮抓到的「布尔值只读不重算」是同源形态：**看着在分支/在校验，实际从未生效**
  - _流程自纠_：我一度在 `--apply` **之前**跑守卫，module-scope 的 `stored` fixture 缓存了
    旧清册 ⇒ 报出 4 failed（含「136 份全 propagated」这种不可能的分布）。那是我的操作
    顺序问题，不是代码缺陷；单独重跑即 1 passed，`--apply` 后全套 25 passed。
    **教训：改冻结产物的任务，必须先 `--apply` 再跑守卫，否则读到的是过期快照**
  - **Validates: Requirements 6.2, 6.4**

- [x] 25. T2 + T3：Property 31 —— 传播产物真实可打开
  - ✅ **2026-09-05 已交付并在真实环境全绿**（`test_workbook_row_change_openability.py`）
  - 🔴 **两阶段实测，两组变异**：
    | 阶段 | 环境 | 结果 | 变异 |
    |---|---|---|---|
    | 首轮 | Docker 中途挂掉 | 6 passed / **4 skipped**（第三层与求值层 UNVERIFIABLE） | 6/6 RED（仅覆盖前两层） |
    | 复跑 | Docker 恢复、容器 healthy | **10 passed / 0 skipped** | **8/8 RED**（注入式，覆盖第三层与求值层） |
  - 🔴 **首轮那 4 条 skip 意味着它们的变异从未被真正覆盖** —— skip 的测试不会因变异变红。
    所以 Docker 恢复后**必须补跑一轮变异**，否则「6/6 RED」是在一个不含这 4 条的
    子集上得出的结论。这一点值得写成通则：**变异覆盖面 = 基线里真正 run 起来的那些测试**，
    基线有 skip 时变异结论必须标注覆盖范围
  - **三层判据，强度递增**：① 本仓库 OOXML 门（`validate_ooxml_artifact` errors 为空）
    ② openpyxl（独立第三方实现）能加载且读到的是传播**后**的公式
    ③ 🔴 OnlyOffice 9.4 的 `x2t` 走通 xlsx→bin→xlsx，回转产物里传播后的引用**逐字保留**
  - 🔴 **第三层已在真实环境取到证据**（Docker 可得窗口内实测）：
    `'明细表D2-2'!AC26` 传播成 `AC28`，x2t 回转产物里是
    `<f>&apos;明细表D2-2&apos;!AC28</f>` —— 引擎解析→序列化→写回后行号 28 完整保留。
    ⚠ 引擎把单引号写成 `&apos;` 实体 ⇒ 判据只能比**坐标片段**，不能整条 `ref_after` 子串匹配
  - 🔴 **x2t 调用必须走 `params.xml` 协议**：直接 `x2t in.xlsx out.bin` 报
    `Couldn't create temp folder`。那**不是权限问题**（实测 chown/chmod 无效），
    是调用协议不对 —— 误判成权限会让人一路去改 owner 然后依然失败

  - 🔴 **AC 8.4 的「公式求值正确」被诚实拆成两层，并实测出不可验的边界**：

    | 层 | 能验什么 | 处置 |
    |---|---|---|
    | 结构 | 引擎解析→序列化→写回后传播后的引用逐字保留 | ✅ 断言（可复算） |
    | 求值 | Excel 重算后指向的是新行的数据 | ⚠ **UNVERIFIABLE** |

    实测依据（`X2T_RECALCULATES_FORMULAS = False`）：往受管表目标格
    `'明细表D2-2'!AC28` 写入可辨认值 `424242`，再送 x2t 回转 ——
    **目标格本体**变成 `<v>424242</v>`（值被搬运），而**引用它的两个格**仍是 `<v>0</v>`；
    写标记前/后两次回转引用格的 `<v>` 完全相同 ⇒ **x2t 不重算公式**。

    ⇒ 它证明的是「引用被正确保留」，**不是**「引用求出的值正确」。两者差一个重算引擎。

  - 🔴 **这是「用更权威的东西冒充」这一类假绿的实例，值得单独记住**：AC 8.4 明令
    「不得用 fixture 冒充」，而这次的冒充候选**不是 fixture，是真实引擎**——
    x2t 返回 rc=0 且产物公式文本正确，极容易被写成「已用真实 OnlyOffice 验证求值通过」。
    fixture 冒充一眼假；**真实引擎的成功看起来是最强证据**，因此更危险。
    判别法：问「这个工具有没有能力回答我在问的问题」——x2t 是**转换器**不是**计算引擎**
  - 求值层的 UNVERIFIABLE 有**实验做反向自检**（`test_formula_evaluation_is_unverifiable_by_x2t`），
    不是只信那个常量：常量可能被人改错，实验不会。若哪天 x2t 开始重算，该实验会
    `pytest.fail` 并指示把求值层升级成真判据 —— 升级必须是**有意**的决定
  - ⚠ **skip 理由必须指向真实根因**：实测中途 Docker Desktop 挂了，原本的理由一律写成
    「容器里取不到 x2t」⇒ 会让人去容器里找文件，而真正该做的是把 Docker 拉起来。
    已拆成「守护进程不可用」与「容器缺文件」两条独立理由
  - **【第一组变异 · 前两层 · Docker 不可得时】** 终态 **6/6 RED**，但**首轮只有 1/6 RED**
    —— 4 条无效用例 + 1 条真守卫缺陷，逐条辨明：

    | 变异 | 首轮 | 根因 | 处置 |
    |---|---|---|---|
    | M1 apply 退化成原样复制 | GREEN → RED | 首版改的是「放宽断言」（`assert X` → `assert True`），数据本就正确时放宽不改变结果 | 改为注入错误**产物**（返回原字节） |
    | M2 传播被回退成传播前引用 | GREEN → RED | 🔴 对 zip 容器做 `bytes.replace` —— xlsx 里 XML 是 **DEFLATE 压缩**的，裸字节替换碰不到 `AC28` | 加 `_rewrite_zip_xml`：解包→改 XML→重打包 |
    | M3 after 与 before 并存 | GREEN → RED | 🔴 **真守卫缺陷**（见下） | 判据改比坐标片段 |
    | M5 传播条目清空 | WRONG-TEST → RED | 判据其实红了（4 个测试 ERROR），是我把 expected 写成了 **fixture 名**而非测试名 | 修标签 |
    | M6 UNVERIFIABLE 前缀去掉 | GREEN → RED | 打的是「docker CLI 不存在」分支，而本机 CLI **存在**（挂的是守护进程）⇒ 该行在当前环境**不可达** | 改打真正会执行的那条分支 |

  - 🔴 **M3 揭出的真守卫缺陷（已修）**：openpyxl 层原用**完整** `ref_before`
    （`'明细表D2-2'!AC26`）做「不含传播前引用」的子串检查。注入 `!AC28+0*AC26` 让
    传播前后坐标**并存**时抓不住 —— 因为注入的是**裸** `AC26`（无 sheet 前缀）。
    而「同一 sheet 的裸引用回退」恰是最可能的错法（改写器少加一次前缀就退化成这样）。
    改比**坐标片段**后立刻打红，且与第三层口径一致
  - 🔴 **给 E 的第四类无效变异用例**（前三类见 §11.2 / §11.10）：
    **变异打在当前环境不可达的分支上**（M6）。它与「恒等分支」是对偶：前者是代码可达
    但语义空转，后者是语义有效但代码不可达。两者都会判 GREEN 并被误读成守卫缺陷。
    判别法：变异前先确认**那一行在本次运行里真的会被执行**

  - **【第二组变异 · 第三层与求值层 · Docker 恢复后】** **8/8 RED**（基线 10 passed / 0 skipped，
    复原后重跑仍 10 passed）。这一组是首轮 4 条 skip 判据的**首次真实覆盖**：

    | 注入 | 模拟的真实错法 | 判读 |
    |---|---|---|
    | I1 传播被整体回退（`AC28`→`AC26`） | 改写器根本没跑，引用错行但结构完好 | RED |
    | I2 after 与 before 并存（`!AC28+0*AC26`） | 改写器少加一次 sheet 前缀 | RED |
    | I3 引用改指不存在的格（`!ZZ99999`） | 「传播不了就改掉」这种 fail-open | RED |
    | I4 产物 zip 截半 | 验第三层**真的会拒**，不是恒返回 rc=0 | RED |
    | I5 把标记值预写进引用格的 `<v>` | 模拟「x2t 会重算」的世界 ⇒ UNVERIFIABLE 该被撤销 | RED |
    | I6 引擎探测谎报 `9.4-FAKE` | 版本判据是否真能识别引擎换版 | GREEN → **真缺陷** |
    | I7 探测谎报不可用但不带 UNVERIFIABLE 前缀 | 「不可验」与「已验证」混为一谈 | RED |
    | I8 计划里传播条目清空 | 分母判据是否防空集恒真 | RED |

  - 🔴 **第二组首跑时我又犯了同一个错**：先写的 8 条里 7 条是「放宽断言」型
    （`assert X` → `pass`），全判 GREEN。根因正是我自己在第一组里已登记过的
    **第三类无效用例（当前状态下与正确结果同值）**——数据本就正确时，放宽一个本来就
    成立的断言不改变任何结果。⇒ **有效变异必须让「被检查对象」变错，而不是让「检查」变松**。
    改成全注入式后立刻 7/8 RED。**同一类错误跨轮复现，说明它不是笔误而是思维默认路径**
  - 🔴 **I6 揭出的真守卫缺陷（已修）**：引擎版本判据原写 `detail.startswith("9.4")`，
    被伪造串 `"9.4-FAKE"` 直接骗过。而真实风险不是有人伪造，是**引擎升级到 `9.40`**
    ——`"9.40".startswith("9.4")` 恒真 ⇒ 大版本换代会被静默放过，届时本任务对
    identity 载体、`&apos;` 实体、「x2t 不重算」这些**全部实测结论同时失效却无人知晓**。
    已改为解析版本号**按点分段**比对（`(major, minor) == (9, 4)`），并对形态非法的
    版本串直接判失败（拿不到可比对的版本号时不得当成通过）
  - 🔴 **给 E 的第五类无效变异用例 —— 「保护对象在基线里是 skip 状态」**：
    前四类都是「变异本身无效」，这一类不同 —— **变异有效，但没有观察者**。首轮
    Docker 挂掉时第三层与求值层 4 条判据全 skip，此时对它们做任何变异都恒 GREEN，
    极易被误读成「守卫缺陷」而去改本来正确的守卫。
    通则：**变异覆盖面 = 基线里真正 run 起来的那些测试**；基线含 skip 时，变异结论
    必须显式标注覆盖范围，并在环境恢复后**补跑**。变异脚本应把基线的 skip 数打进
    报告首行（本任务的一次性 harness 已这么做，见判读第 2 行）
  - **Validates: Requirements 8.4**

---

### Wave 6 —— 变异与收口

- [x] 26. X1：变异检验脚本 + 范围边界判据 + 产物入库
  - ✅ **2026-09-05 E 已交付三项**（`--run all` 实测 **10/10 RED**、覆盖面 **3/3**、
    退出码 0、三守卫基线 **49 passed / 1 skipped**、`.mutbak` 残留 0、被变异的 C 文件
    `git status` 无我的改动残留）：
    - **X1 脚本**：`backend/scripts/diagnose/mutate_workbook_row_change_guards.py`（走
      `_mutation_kit` 共享件，四态判读按**失败测试名集合差集**，退出码不作判据）
    - **范围边界判据**：`backend/tests/workpaper_sync/test_workbook_row_change_scope_boundary.py`
      （**10 passed**，Requirement 9.1–9.6 逐条可执行化）
    - **CI**：`governance-checks.yml` 追加 job `workbook-row-change-scope-and-mutation-anchors`
      （范围边界判据 + `--check-anchors`，两步只读且不受上游门约束；YAML 已验、依赖全已跟踪）
    - **产物入库**：两个新产物均已 `git add`
  - ✅ **C 清单六条全部落地**（M01 行首锚定组合变异 / M03 重复编号 fail-closed / M04 `~` 当就绪 /
    M05 `propagate_sheets` 检测器短路 / M06 A1 owner 掩盖第二入口 / **M07 分母期望值改错**），
    另加 M02（`\*?` 被去掉 ⇒ `*` 子任务读不到、分母 27→22）、M08 + M10（模板写入检测器**双向**：
    恒命中与恒不命中各一条）、M11（元判据：词表断言的 `==` 不得降级为 `>=`）
  - 📌 M07 曾因该守卫基线为红而缓一轮（清册 D2 已 `propagated`、守卫仍断言 `blocked`）；
    **C 于 2026-09-05 收口后基线转绿，当轮补入**，`GUARD_FILES` 分母随之 2/2 → **3/3**
  - ⏳ 门后各 Wave（T2 / T3 / T4）的变异清单待 C 交付后另行落地（不阻塞本任务：
    本任务的交付面是「X1 脚本 + 范围边界判据 + 产物入库」三项，均已完成）
  - 🔴 **两条实测教训（E 补记，2026-09-05）**：
    1. **锚点必须按内容现查，不得沿用早先探测的行号。** 首版第 6 条锚在旧版 L305，
       实测判 GREEN；排查发现 C 在会话期间重写了该守卫文件，那行已不存在，而
       `--check-anchors` 仍报 OK —— 因为共享件拿「去行尾整行文本」在**当前**文件里查唯一命中，
       恰好匹配上另一处同内容的行。「锚点命中」与「命中我想要的那一处」是两件事。
       这也正是 GREEN 这一态的价值：按退出码判定会把锚点漂移记成 RED。
    2. **GREEN 的正确用法是补强判据，不是记账。** 首轮「把词表判据的 `==` 降级成 `>=`」
       判 GREEN —— 不是守卫缺陷，而是「判据自身的运算符被改弱」在真实枚举仍只有两个成员时
       **无任何常规判据能观察到**。已补元判据
       `test_boundary_equality_assertions_are_not_downgraded_to_subset`（读自身 AST 断言
       比较节点是 `ast.Eq`），同一变异随即从 GREEN 转 RED（现 M11）
  - 逐条改一字，四态判定；每条变异用例验证「唯一保护性」
  - 🔴 **Wave 0 已实测出两类无效变异用例，清单必须避开**：
    1. 被**收敛语义**掩盖的 —— 「同编号保留最后一次」让行首锚定变异结果不变
    2. 被**第二道防线**挡住的 —— 正则里的 `^` 与调用侧的 `.match` 互为冗余，
       单点变异必判 GREEN；这类必须做**组合变异**
  - 已交付的 T5 变异清单（6/6 RED，可直接并入 X1）：行首锚定组合变异 / 重复编号 fail-closed /
    `~` 当就绪 / `propagate_sheets` 检测器短路 / A1 owner 检测器掩盖第二入口 / 分母期望值改错
  - 范围边界：不做 reorder / 不做列变更 / 不放宽 OOXML 安全策略 / 不传播跨工作簿引用 /
    不传播图表透视 / 不改 `backend/wp_templates/` 任何字节
  - `git status --porcelain -- <产物清单>`，见 `??` 即 add；CI job 在干净 checkout 下可跑
  - **Validates: Requirements 8.1, 8.2, 8.3, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6**

---

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 0,
      "name": "前置裁决、零回归基线冻结与上游就绪门",
      "tasks": [1, 2, 3, 4, 6, 24, 101],
      "depends_on": [],
      "rationale": "四个 Open Gate 决定可达性分母、判据形态、性能策略与删行设计（2026-09-04 已全部裁决）。Task 6 排在本 Wave 而非 Wave 1，是因为它时间敏感且只读：Requirement 7.4 的参照物是『本 spec 前』的行为，上游一旦改动 excel_row_shift.py 就再也无法取证，所以基线必须在门之前冻结（AC 7.7），而冻结动作不碰任何共改文件故不受门阻断。Task 101 是上游就绪门：本 spec 与 excel-structural-row-insertion 共改 excel_row_shift.py / excel_materialize.py / excel_extract.py 三个生产文件，必须现读上游 tasks.md 确认其 Wave 4（Task 16/17/18 含 * 子任务）已 [x] 才允许 Wave 1 起开工，否则两边并行编辑会互相回退"
    },
    {
      "wave": 1,
      "name": "骨架与零回归复核",
      "tasks": [5, 7, 28],
      "depends_on": [0],
      "rationale": "🔴 本 Wave 起全部在 Task 101 门后（AC 7.6 于 2026-09-04 由『Wave 2 起』修正为『Wave 1 起』——原文与 7.5 自相矛盾：7.5 明列 excel_row_shift.py 为共改文件，而原 Wave 1 的 Task 6 正要改它的 _rewrite_formula_refs）。Task 5 的 N1 也在门后，因为 WorkbookRowChangePlan 以上游的 RowShiftPlan 为其受管 sheet 分量，形态未定型就落盘要返工。Task 28 加 propagate_sheets 后必须复跑 Wave 0 冻结的基线并逐字相同，才允许 Wave 2 接传播——先证明加法不产生回归，再加功能"
    },
    {
      "wave": 2,
      "name": "插行传播",
      "tasks": [8, 9, 10, 11, 12, 13, 27],
      "depends_on": [1],
      "rationale": "先做插行：它没有悬空引用这一类情形，是传播机制的最小可证形态。Wave 0 Gate 1 裁决后主判据载体改为 D2（唯一既有已审核契约又有真实跨 sheet 引用的 entry，52 处），K11 的 114 处降为结构判据载体（无契约）。Task 27 是 Wave 0 实测补入的**第二个传播方向**（受管 sheet 新行 → 别的 sheet 的取数源），承接前置 spec 明写交出的 R12.4；它与 Task 9 共改 excel_row_shift.py 且方向相反，放同一 Wave 便于两侧判据互相对照"
    },
    {
      "wave": 3,
      "name": "删行与收缩",
      "tasks": [14, 15, 16, 17, 18],
      "depends_on": [2],
      "rationale": "删行复用同一份传播器（方向相反）并多出悬空引用与业务键留痕两类要求；在插行传播已被证明正确后叠加，失败时能分清是传播错还是删行错"
    },
    {
      "wave": 4,
      "name": "验证侧与接线",
      "tasks": [19, 20, 21, 22, 23],
      "depends_on": [3],
      "rationale": "验证器改成按声明值归一化必须在两个方向的传播都实现后做，否则判据只覆盖一半；接线放最后，且不得为接线放宽既有 fail-closed 判据"
    },
    {
      "wave": 5,
      "name": "清册状态翻转与真实环境验证",
      "tasks": [25, 29],
      "depends_on": [4],
      "rationale": "🔴 Task 24（清册本体）已于 2026-09-04 提前到 Wave 0 执行：原 rationale 是『需等传播能力落地才知道哪些 blocked』，但 Gate 1 的裁决把 blocked 的判定依据改成了『该 entry 有没有已审核契约』——今天就完全可判定，且清册只读零文件冲突。留在本 Wave 的是 Task 29：传播落地后把 D2 那一行从 pending_implementation 翻成 propagated，并断言『只有 D2 那一行变』。真实环境验证（Task 25）仍需等产物能真实生成"
    },
    {
      "wave": 6,
      "name": "变异与收口",
      "tasks": [26],
      "depends_on": [5],
      "rationale": "变异检验要在全部判据到位后做；收口核查产物入库，防『spec 全绿 ≠ 产物已入库』"
    }
  ]
}
```

## Notes

### 复用而非重写

`excel_row_shift._rewrite_formula_refs` 是本模块唯一的 A1 改写入口，已处理四类误命中：

1. 跨 sheet 表名含「字母+数字」被当坐标（实测 16,027 处）
2. 跨 sheet 目标格被本 sheet 插行误位移
3. 带数字的函数名（`LOG10` → `LOG11`）
4. 字符串字面量里的 `K11`

本 spec 以 `propagate_sheets` 参数形态接入，**不新造第二个入口**（Property 27 用 AST 锁死）。

### 反面教材

* **openpyxl 全量重写**：K11 实测 zip 部件 37→19、共享公式主格 12→0、非空缓存值 716→28、
  中文表名写成 `&#23457;` 数字实体。禁止用于传播落盘。
* **手搓正则解析 sheet → part**：对 B60 / H1 / G7 三个模板全部失败（中文括号、属性顺序不定）。
  必须用 `app.services.excel_structure_fingerprint._parse_workbook_xml` + `_normalise_part`。
* **变异用例不敏感**：前置 spec 实测过 —— `'明细表K11-2'!F29` 做变异用例时行号 11 小于
  `insert_at=26`，位移是空操作，且 `!` 左边界是第二道防线，于是变异不打红被误判成守卫缺陷。
  换成行号落在插入点之后的用例才敏感。

### 判据纪律

* 「字符存在」型判据不算判据。对生产源做「某符号是否真被用到」的判断前必须先剥 Python
  docstring（`_strip_comments` 不剥它），否则 docstring 里叙述性提到的符号名会被当成真实引用。
* 每条结构性判据写完必做变异检验；没打红 = 守卫有缺陷，不是代码没问题。
* 🔴 **变异用例的两类无效形态**（Wave 0 实测各踩一次，详见 Task 101）：被**收敛语义**掩盖的、
  被**第二道防线**挡住的。后者必须改成组合变异；把它们误判成「守卫缺陷」会去改本来正确的守卫。
* 所有判据必须带分母断言，且**用 design.md「分母断言」表里的 Wave 0 复算值**：
  **351** 份 xlsx / **182** 份含跨 sheet 引用 / **144,154** 处引用 / **136** 份受影响 /
  **4** 个已发契约 entry / **D2 的 52 处**（首要载体）/ **K11 的 114 处 19 行**（结构载体）/
  最极端 **C24 的 63,240 处**。
  ⚠ 原 requirements.md Introduction 登记的 `176` / `81,955` / `16,027` / `137` / `604`
  **复算不上**，已在该处标注并报给 A（分工书 §9 的 C 行）。**判据不得引用这五个数字。**

### 收口

* 改动 `backend/app/**/*.py` 后必须重跑受影响的生成器（`generate_workpaper_writer_inventory.py`
  等），否则一批 freshness 判据会连带打红。归因方法：`git status --porcelain` 空输出 = 未修改，
  用它区分自己的债与并发会话的债。
* 本 spec **不新增数据库迁移**（Requirement 9 未列但 design.md 的 Data Models 已声明）。
