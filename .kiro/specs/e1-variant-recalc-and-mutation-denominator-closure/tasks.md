# Implementation Plan

## Overview

两组任务：**A 组**（Task 1、2、5、6、7、15、18）修 E1-3 `multi` 口径抹零；**B 组**（Task 3、4、8~14、16）把变异检验样板收敛成 `backend/scripts/_mutation_kit/` 并推广。Task 17、19 是两组共用的收口。

顺序原则沿用平台惯例：**判据先行**（守卫先打红再改实现）· 每个 Wave 末尾配变异检验 · 浏览器实测与真实库验收放最后。

A 组的新守卫用 B 组的共享件写变异脚本 —— 故 Task 15（A 组变异）依赖 Wave 3（共享件）。这是有意的耦合：让推广的第一个用例就是本 spec 自己。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "name": "判据先行与产物入库", "tasks": ["1", "2", "3", "4"], "parallel": true },
    { "wave": 2, "name": "A 组实现：三形态与三态归一", "tasks": ["5", "6", "7"], "depends_on": [1] },
    { "wave": 3, "name": "B 组共享件", "tasks": ["8", "9", "10"], "depends_on": [1] },
    { "wave": 4, "name": "B 组迁移与采纳守卫", "tasks": ["11", "12", "13", "14"], "depends_on": [3] },
    { "wave": 5, "name": "变异、CI、实测与回归", "tasks": ["15", "16", "17", "18", "19"], "depends_on": [2, 3, 4] }
  ],
  "notes": [
    "Task 1/2 必须在 Task 5/6 之前对**当前实现**打红 —— 打不红说明判据无效，不是代码没问题。",
    "Task 3（脚本入库）与 A 组零文件重叠，可完全并行；它是 Wave 4 迁移的前置。",
    "Task 4（跟踪守卫 + 豁免表）依赖 Task 3 的入库结果才能归零，故 Task 3 先完成。",
    "Task 5（recalcRow 三形态）与 Task 6（fxRate 三态）碰同一文件 useE1BankDetail.ts，必须串行：先 5 后 6，或一次落地。",
    "🔴 Task 6 依赖 Task 5：形态 B 要靠 fxRate===0 显示「待录入」，而三态归一是它的前提；但形态判定本身用 fxCurrency 不用 fxRate，故 Task 5 可先独立完成并自证。",
    "Task 11（迁 e_cycle）必须是迁移的第一个 —— 它是唯一 11/11 的范式基准，若共享件表达不出它的某项能力，改共享件而不是削减该脚本。",
    "Task 15（A 组变异）依赖 Wave 3 共享件 + Wave 2 实现 + Task 1/2 守卫三者全绿。",
    "Task 18（浏览器实测）是最后一步，必须在 Task 17 CI 接线后做，且实测前后要做库侧基线/复原双证。",
    "🔴 全程不得触碰 mutate_k_cycle_guards.py / mutate_i_cycle_guards.py / mutate_ie_lifecycle_guards.py（在办 spec，Property 18）。"
  ]
}
```

## Tasks

- [x] 1. 形态判定与 fxRate 三态守卫（先打红）
  - 新建 `audit-platform/frontend/src/components/workpaper/composables/__tests__/e1BankDetailFxForm.spec.ts`
  - 断言 `classifyFxForm` 的三形态划分：fc 列任一非 0 ⇒ `fc-authoritative` · fc 全 0 且 `isBaseCurrency(fxCurrency)` ⇒ `base-identity` · fc 全 0 且非本位币 ⇒ `foreign-pending`（Property 1/2/3）
  - 断言 `recalcRow(row,'multi')` 在形态 A 下**本位币六列与输入逐字相等**、`ending` 按 `calcCashBalance` 算出（Property 1）；形态 B 下本位币列为 0 且 `fxRate` 保持 0（Property 2）；形态 C 下与修复前逐字相同（Property 3）
  - 断言 `recalcRow(row,'rmb')` 输出与修复前逐字相同（Property 4）——**零回归支点**，把修复前的期望值硬编码为基线常量并注明「值来自修复前实测而非预期」
  - 断言 `loadFromResponses` 的 fxRate 三态：缺失（`undefined`/`null`/`''`）→ 1 · 显式 `0` → **0** · 其他 → 原值（Property 8/9）
  - 断言形态 A 下 `endingFc === calcCashBalance(opening,increase,decrease)`（Property 13）—— 防「本位币有值而原币显 0」的自相矛盾
  - 历史数据兼容：用不含 `fxRate` 键的行 JSON 作输入，断言本位币列非 0（Property 10）
  - **必须先红**：`classifyFxForm` 尚不存在 ⇒ import 失败即红；三态断言在当前 `|| 1` 实现下必红。跑一次记录红的条数与测试名，写进本文件实录
  - PBT（`fast-check`，仓库已有）：任意 fc 列组合下「任一非 0 ⇒ 恒为形态 C」
  - _Requirements: 1.1, 1.2, 1.6, 2.1, 2.2, 2.3_

- [x] 2. 跨层端到端守卫（先打红）
  - 新建 `composables/__tests__/e1BankVariantIntegrity.spec.ts`
  - 判据形态：**从写入侧出发、经序列化、到消费侧**，断言本位币金额守恒。禁止只测纯函数返回值 —— 那正是本缺陷穿过 29 条变异 + 568 例守卫的原因
  - 链路 = `buildBankSeedRowsFromAccounts(p, variantA)`（或 `buildBankSeedRows(p)`，或手工构造的录入行）→ `JSON.stringify` → 塞进 `allResponses` 的 `E1-bank-detail-rows` → `useE1BankDetail({ variant: ref(variantB) })` → `rows.value` 的本位币列
  - `variantA × variantB` **四组合**全覆盖（rmb→rmb / rmb→multi / multi→rmb / multi→multi）× **三来源**（账户级 / 叶子口径 / 手工录入）（Property 5）
  - 叶子口径单独一条（Property 6）：`buildBankSeedRows` 产出的行在 `multi` 下本位币金额非 0 ——**这条在改造前就该红**，与 variant 切换无关
  - 手工录入路径用 `addRow` + `updateCell` 真实走一遍，不手搓 row 对象（否则测不到 `updateCell` 里的 `recalcRow(row, variant.value)`）
  - 文件头注释写明**断言半径**：跨了种子 → 序列化 → 加载 → 重算四层，以及为什么单层守卫不够（引用既有守卫「multi 版必须下发原币列」措辞准确但半径只到纯函数输出这一事实）（Property 15）
  - **必须先红**：至少 rmb→multi 与「叶子口径→multi」两组必红。逐条记录红的测试名（Property 14 的前置证据）
  - _Requirements: 1.3, 4.1, 4.2, 4.3, 4.5_

- [x] 3. 未入库变异脚本入库 + 归属查清
  - 7 个 `backend/scripts/check/mutate_task{13,14,18,19,20,21,23}_*.py` 属已归档 `procedure-trimming-and-delegation-intelligence`(26/26)，当前 `??` 未跟踪 ⇒ 入库（Property 16）
  - 入库前逐个跑只读子命令（`--list` 或等价）确认可运行、退出码 0 且输出非空；不可运行的**不入库**，如实登记原因（Property 17）
  - `mutate_wp_export_resolver_guards.py` 归属未明 ⇒ 按「内容关键词 + mtime + 对应守卫文件所属 spec」三条判归属，给出明确结论（入库 / 删除），写进实录，**不留 `??`**（Property 19）
  - 归属判据不得只看文件名（memory 实证：`tmp_t22_base.json` 名字带 t22 但属他 spec）
  - 入库后逐个 `git ls-files --error-unmatch` 复核并把结果贴进实录（Property 16）
  - **不得** `git add` 在办 spec 的 3 个脚本（`k_cycle` / `i_cycle` / `ie_lifecycle`）（Property 18）
  - _Requirements: 5.1, 5.2, 5.3, 5.5_

- [x] 4. 变异脚本跟踪守卫 + 豁免表
  - 新建 `backend/data/mutation_kit_exemptions.json`，schema 见 design.md §Data Models（`script`/`spec`/`reason`/`registered_at`/`revoke_when` 五个必填）
  - 登记在办 spec 的 3 个脚本，`reason` 写明「spec 在办 + 并发会话在编辑」，`revoke_when` 写「spec 归档后」
  - 新建 `backend/tests/test_mutation_kit_scripts_tracked.py`：扫 `backend/scripts/{check,diagnose}/mutate*.py`，未被 git 跟踪且不在豁免表 ⇒ 失败（Property 16）
  - 新建 `backend/tests/test_mutation_kit_exemptions.py`：豁免项缺任一必填字段 ⇒ 失败；`reason` < 10 字 ⇒ 失败；**豁免项的 spec 目录已不在 `.kiro/specs/` 下（= 已归档）⇒ 失败并提示撤销**（Property 30）
  - 豁免表 JSON 解析失败时守卫**失败**而非静默跳过（fail-closed）
  - 反向自检：把某在办 spec 的目录名改成不存在的值，失效检测必须打红
  - _Requirements: 5.4, 5.6, 8.5_

- [x] 5. `classifyFxForm` + `recalcRow` 三形态
  - 在 `composables/useE1BankDetail.ts` 新增导出纯函数 `classifyFxForm(row): FxForm`，签名见 design.md §Components
  - 判据用 `fxCurrency` + `isBaseCurrency()`（既有单一真源），**不用 `fxRate`** —— 用 fxRate 会把形态 B 误判成 A 从而臆造汇率 1（Property 34 禁止）。这条理由写进函数注释
  - 改 `recalcRow` 的 `multi` 分支按三形态分派：形态 A 保留本位币六列 + `endingFc` 镜像本位币；形态 B 保持现状（全 0）；形态 C 保持现状（由 fc 派生）（Property 1/2/3/13）
  - `rmb` 分支**一行不改**（Property 4）
  - 不改 `buildBankSeedRowsFromAccounts` / `buildBankSeedRows` 的任何一行（Property 7）—— 种子侧 variant 分流是 AC 1.4 的设计意图，既有守卫已锁死
  - 不新增 `BankDetailRow` 字段、不改 `USER_FIELDS`、不落库 `fxForm`（形态是推导出来的，落库即产生第二真源）
  - 跑 Task 1 的守卫，确认此前红的形态断言转绿、`rmb` 零回归断言仍绿
  - _Requirements: 1.1, 1.2, 1.4, 1.5, 1.6_

- [x] 6. `loadFromResponses` 的 fxRate 三态归一
  - 把 `fxRate: parseNum(r.fxRate) || 1` 改为显式三态：`(r.fxRate === null || r.fxRate === undefined || r.fxRate === '') ? 1 : parseNum(r.fxRate)`
  - 注释写明**为什么缺失回落 1**（「缺失 = 该行只有本位币列 = 原币与本位币恒等」），而不是「历史如此」（Property 9）
  - 确认形态 B 的行加载后 `fxRate` 为 0，且界面提示走既有 `FOREIGN_FC_HINT` 单一真源，**不新造第二份文案**（Property 2）
  - 历史兼容验证（Property 10）：取真实库里既有的 `E1-bank-detail-rows`（若存在）或构造无 `fxRate` 键的行，断言加载后本位币列非 0
  - 与 Task 5 碰同一文件，串行或一次落地
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.6_

- [x] 7. 落库形态与跨 sheet 聚合守卫
  - 在 Task 2 的守卫文件里补：断言 `serializeRows(rows, USER_FIELDS)` 输出的 JSON 里每行 `opening`/`increase`/`decrease`/`adjustment` 等于**写入时**的值（Property 11）
  - 判据必须落在**序列化输出**上，不是内存 `rows` —— 落库形态由 `USER_FIELDS` 决定，两者可能不同
  - 断言 `syncCrossSheetTotals()` 的四个跨 sheet 键（`E1-bank-detail-{principal,institution,finance,other}-{opening,total}-unaudited`）在 variant 切换前后取值相同（Property 12）
  - 形态 B 的行落库值必须与写入时一致（不被派生结果覆盖），即「真外币未录汇率」的 0 是写入时就是 0，不是被算成 0（Property 11 的 AC 3.4 分支）
  - **不在持久化层加防御**：不写「落库前检查是否变 0」那类补丁（会掩盖真因，且分不清合法 0）
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 8. 共享件骨架：`spec.py` / `anchor.py` / `apply.py`
  - 新建 `backend/scripts/_mutation_kit/`（`__init__.py` 公开 API）
  - `spec.py`：`Mutation` 数据类（字段见 design.md §Components）+ 声明期校验（`kind` 合法 · `anchor` 非空且**不含 `\n`** · `want` 非空 · `why` 非空）
  - `anchor.py`：锚点定位。**行级唯一 + 行号消歧 + 该行逐字相等 + 命中数恰好 1** 四重断言；`splitlines(keepends=True)` 保留行尾，CRLF 安全（工作树是 CRLF，含 `\n` 的锚点必然 MISS）
  - `apply.py`：备份 / 应用（replace·delete·insert·swap·move 五种 kind）/ 还原。还原写在 `finally`；还原后用 **md5 与变异前逐字比对**，不符时抛异常并打印两个 md5（不信「写回成功」）
  - 截取块（swap/move）用**括号配对**且**先跳参数列表**，禁固定字符窗口 —— TS 返回类型注解 `): Promise<{...}>` 与 Python 多行签名都会骗到「第一个 `{`」
  - 零新增第三方依赖：只用 `dataclasses`/`pathlib`/`hashlib`/`re`（Property 25）
  - _Requirements: 6.1, 6.6_

- [x] 9. 共享件执行与判定：`runner.py` / `verdict.py` / `coverage.py` / `cli.py`
  - `runner.py`：pytest 与 vitest 执行 + **失败测试名集合**提取（pytest 用 `-rf` 解析；vitest 用 `--reporter=json` 取 `fullName`）。子进程一律 `subprocess.run([...])` **不经 shell**（`-k "a or b"` 经 shell 会被拆成多个位置参数）
  - `verdict.py`：四态判定（RED / GREEN / ANCHOR-MISS / WRONG-TEST），判据是**新增失败集合的差集**，退出码不作判据
  - `coverage.py`：覆盖面分母 tally —— 输入守卫文件全集，输出「未被任何变异打红」的清单，报告末尾打印（Property 21）
  - `cli.py`：`--list` / `--check-anchors` / `--run` / `--restore` 统一入口
    - `--check-anchors` **只读**：执行后目标文件 md5 全不变、无 `.bak`/`.mutbak` 残留、无新增文件（Property 23）
    - `--list` **不得只打印**：同时校验「锚点命中恰好 1 次 + 替换文本 ≠ 锚点 + `want` 可定位到真实测试」，任一不满足即非零退出（Property 24）——g7 spec 教训：只打印的 `--list` 在 CI 里恒绿
  - `run_cli()` 的 `guard_files` 设为**必填关键字参数** —— 让「没有分母」在签名层面不可能（Property 21）
  - 冻结基线：`baseline_backend_passed` / `baseline_frontend_passed` 不符时打印 WARN 含实测值与基线值；注释要求改基线必须说明来源（Property 22）
  - _Requirements: 6.2, 6.3, 6.4, 6.7_

- [x] 10. 共享件自身守卫
  - 新建 `backend/tests/test_mutation_kit_capabilities.py`，七项能力每项一条**行为**测试，判据是「故意破坏后必失败」而非「函数存在」（Property 20）
  - 具体：锚点唯一性（构造同名多处命中 ⇒ 必报 ANCHOR-MISS） · md5 还原核验（篡改还原内容 ⇒ 必抛） · 分母 tally（声明 3 个守卫文件但只有 2 个被打红 ⇒ 报告必列出第 3 个） · 四态（构造四种情形各自命中对应态） · `--check-anchors` 只读（跑前后 md5 比对） · `--list` 校验（构造 want 定位不到的变异 ⇒ 必非零退出） · 冻结基线（实测 ≠ 基线 ⇒ 必 WARN）
  - 反向自检：把上述任一断言的被测代码改坏，对应测试**必须**打红（写进实录，没打红=守卫有缺陷）
  - 用临时目录 + 替身文件做被测对象，**不拿真实生产文件**做共享件的测试素材
  - _Requirements: 6.5_

- [ ] 11. 迁移范式基准：`mutate_e_cycle_guards.py`
  - **迁移的第一个**。迁移前先跑一遍**全量**变异，存下判定矩阵（变异 id → 四态 + 打红测试名集合）作等价性基线（Property 26）
  - 🔴 迁移前必查：`mutate_e_cycle_guards.py` 的 M09/M10/M29 锚在 `backend/data/note_template_soe.json`，该文件长期带并发 K 循环的未提交改动。跑全量变异会改它 ⇒ **开工前先确认该文件当前状态并与并发会话协调**；若不可协调，改用「按变异分批 + 每批后立即 md5 复核」并在实录写明
  - 迁移后重跑同一变异集，判定矩阵**逐一比对**必须相同（Property 26）
  - 若共享件表达不出该脚本的某项能力（如它的 `SPEC_GUARD_FILES` 说明文字、M01 的 want 多目标匹配），**改共享件**而不是削减该脚本的能力
  - 迁移后确认七项能力齐全（Property 27）
  - _Requirements: 7.1, 7.3, 7.4_

- [ ] 12. 迁移其余 5 个已归档 spec 的脚本
  - `mutate_h_cycle_guards.py` · `mutate_g7_column_alignment_guards.py` · `mutate_trim_decision_guards.py` · `mutate_note_conversion_section_mapping_guards.py` · `mutate_note_text_hygiene_and_expandable.py`
  - 每个都按 Task 11 的等价性流程（迁移前矩阵 → 迁移 → 迁移后矩阵 → 逐一比对）（Property 26）
  - 顺带补齐它们缺的能力：`g7` 缺 md5 还原核验 · `h_cycle`/`note_text_hygiene`/`note_conversion` 缺 WRONG-TEST 态 · 五个全缺覆盖面分母与静态锚点自检（Property 27）
  - 补分母时守卫文件全集要**真查**该 spec 的守卫文件（从其 tasks.md 或 CI job 反查），不得随手列几个凑数 —— 分母不全等于分母无效
  - 迁移中发现的既有判据缺陷（无效变异、锚点已漂移、want 定位不到）**如实登记不顺手改**（Property 28），除非不改无法完成迁移，此时在实录写明理由
  - _Requirements: 7.1, 7.3, 7.4, 7.6_

- [ ] 13. Task 3 入库脚本的迁移决策
  - 对 Task 3 入库的 7~8 个脚本，逐个判「迁移后能否复现原判定」
  - 能复现的迁移（走 Task 11 的等价性流程）；不能复现的**不迁**并写明原因（Property 26 / AC 7.2）
  - 这批脚本属已归档 spec 且从未入库，可能存在「写完就没再跑过」的情况 ⇒ 先跑一遍取当前判定矩阵，若脚本本身已失效（锚点全 MISS）则登记为「历史产物，保留但不迁」，不强行修复
  - _Requirements: 7.2_

- [ ] 14. 采纳守卫 + 在办 spec 登记
  - 新建 `backend/tests/test_mutation_kit_adoption.py`：扫 `backend/scripts/{check,diagnose}/mutate*.py`，未 `from _mutation_kit import` 且不在豁免表 ⇒ 失败（Property 29）
  - 判据不能是「文件里出现 `_mutation_kit` 字符串」（注释里提一句就绿了）⇒ 用 AST 解析真实 import 语句
  - 在豁免表补登在办 spec 的 3 个脚本（若 Task 4 已登记则复核其 `reason`/`revoke_when` 仍准确）（Property 18 / AC 7.5）
  - 变异检验：新增一个不带分母的临时脚本 ⇒ 采纳守卫必红；把某脚本从豁免表移除 ⇒ 必红（Property 29）
  - 临时脚本用完即删，并复扫确认无残留
  - _Requirements: 7.5, 8.1, 8.2_

- [ ] 15. A 组变异检验
  - 用**本 spec 的共享件**新建 `backend/scripts/diagnose/mutate_e1_variant_recalc_guards.py`（自举：推广的第一个真实用例）
  - `guard_files` 分母 = Task 1/2/7 新建或扩展的守卫文件全集
  - 变异至少覆盖：形态判定改用 `fxRate` 而非 `fxCurrency`（应打红 Property 2 的外币断言）· 形态 A 分支删掉（退回无条件派生，应打红 Property 1/5/6）· `fxRate` 三态改回 `|| 1`（应打红 Property 8，AC 2.5）· `endingFc` 镜像删掉（应打红 Property 13）· `rmb` 分支动一行（应打红 Property 4 零回归）· 跨层守卫的四组合删一组（应打红覆盖面 tally）
  - 每条变异的 `why` 写明**为什么这条变异不是无效变异**（e-cycle 的 M3/M15 各踩过一次：删了行为不变 = 无效）（Property 14 / AC 4.4）
  - 结果必须 **RED**（GREEN=0 / ANCHOR-MISS=0 / WRONG-TEST=0）；四态逐条记录进实录，只看退出码会把后三态误判成 RED
  - 覆盖面 tally 必须显示「0 个守卫文件未被打红」
  - _Requirements: 2.5, 4.4_

- [ ] 16. B 组变异检验
  - 在 Task 15 的脚本里加一组，或另建脚本，覆盖 B 组守卫
  - 变异至少覆盖：`anchor.py` 的唯一性断言删掉（应打红 Property 20 的唯一性用例）· `apply.py` 的 md5 核验删掉（应打红）· `coverage.py` 的 tally 输出删掉（应打红）· `cli.py` 的 `--check-anchors` 改成会写文件（应打红 Property 23）· `--list` 的校验删掉只留打印（应打红 Property 24）· 豁免表失效检测删掉（应打红 Property 30）
  - 结果必须全 RED，四态逐条记录
  - _Requirements: 8.2_

- [ ] 17. CI 接线（归因型验收）
  - 在 `.github/workflows/governance-checks.yml` 新增 job：A 组前端守卫（vitest）+ B 组后端守卫（pytest）+ 共享件能力守卫 + `--check-anchors` 静态自检
  - 挂 CI 前逐个验证引用文件 **exists + tracked**（沿用本轮复盘的「37/37」判据形态），干净 checkout 下可跑（Property 31）
  - 🔴 改 yml 用 `fs_append` 或精确 `str_replace`；验收用**归因型**判据（变动是否落在本 spec 的字节区间内），**不用**「其他 job 一个都没变」的全局等值型 —— 并发会话同时改该文件是常态，全局等值必假红（Property 32）
  - 记录改动前后的 job 总数与本 spec 新增的 job 名，作归因证据
  - _Requirements: 8.3, 8.4_

- [ ] 18. 浏览器实测与真实库验收
  - 实测前：postgres 只读取基线（目标项目的 `E1-bank-detail-rows` + 四个跨 sheet 聚合键 + `E1-bank-variant` 的 md5 与 `updated_at`）
  - 复现原缺陷路径确认已修：加载 → 点 `(仅人民币)E1-3` → 再点 `(人民币及外币)E1-3`，22 行金额**不得**变 `-`，横幅**不得**出现「审定合计 0.00 ≠ TB数」
  - 叶子口径兜底路径单独验（Property 6）：选一个 aux 侧无银行账户数据的项目，直接开 `multi` 版，金额不得恒零。若全库无此类项目，如实登记 UNVERIFIABLE 并给替代证据（vitest + 变异）
  - 手工录入路径验：在 `仅人民币` 版改一格 → 等 2 秒（`scheduleSave` 窗口）→ 切 `人民币及外币` → 再切回 → 金额仍在
  - 外币行验 Property 2：若有非本位币账户则验「本位币列 0 + 汇率显 0 + note 提示」；全库 `currency_code` 全 `CNY` ⇒ 如实登记 UNVERIFIABLE + 替代证据
  - 实测后：按基线**逐字节复原**并双重核实（脚本 verify + 独立 SQL 直查）；🔴 复原前先判「差异是谁造成的」—— 把并发会话的新成果当污染去复原就是回退事故（e-cycle Task 22 的实证教训）
  - 判成败一律**查数据**不看退出码（`--apply` 常被 Ctrl+C 中断但写入已提交）
  - _Requirements: 1.1, 1.3, 3.1_

- [ ] 19. 回归与清理
  - 前端：按引用关系反查辐射面跑 vitest（**不跑全量**），至少覆盖 `e1*` 全域 + 本 spec 新建守卫；记录 passed 数并与冻结基线比对
  - 后端：`backend/tests` 里与 `_mutation_kit` / 豁免表 / 采纳守卫相关的文件；**不跑全量 `backend/tests`**（1522 个文件，前台无中间输出会被误判卡死）
  - 三件套机器校验：`get_diagnostics` 对本 spec 三个 md 零诊断
  - 产物入库复核：`git status --porcelain -- <本 spec 产物清单>`，见到 `??` 即 add（memory 铁律：「spec 全绿」≠「产物已入库」，G7 收口时实测 10 个正式产物全未跟踪）
  - 清理本 spec 自己的 `tmp_*` / `_wip_*` 诊断产物；归属判据 = 前缀 + 内容关键词 + mtime 三条，**不按文件名里的任务号**（`tmp_t22_base.json` 陷阱）
  - 复扫 `*.mutbak` / `*.bak` 残留为 0
  - _Requirements: 无新增 AC（收口任务）_

## Notes

### 立项时的实证基线（2026-08-15，只读零改动）

见 requirements.md §实证基线 与 design.md §Notes。关键行号：

| 位置 | 事实 |
|---|---|
| `useE1BankDetail.ts` L105~L119 | `recalcRow` 的 `multi` 分支无条件由 fc 列派生并 `...row` 覆盖本位币列 |
| `useE1BankDetail.ts` L176~L179 | `fxRate: parseNum(r.fxRate) \|\| 1`（回落 1）vs `openingFc: parseNum(r.openingFc)`（回落 0）—— 不对称 |
| `useE1BankDetail.ts` L193 | `watch(variant, ...)` 切换即全表重算 |
| `useE1BankDetail.ts` L92~L98 | `USER_FIELDS` 同含本位币四列与原币五列 ⇒ 抹零会落库 |
| `useE1BankDetail.ts` L248~L250 | `syncCrossSheetTotals` 的 watch 带 `immediate: true` ⇒ 聚合键同步归零 |
| `useE1BankDetail.ts` L253~L262 | `scheduleSave()` 2 秒 → `persistToResponses()` → `saveImmediate()` 写库 |
| `e1FourTablePrefill.ts` `buildBankSeedRows.mk()` | 无条件 `fxRate:1` + fc 全 0 ⇒ 叶子口径兜底在 `multi` 版**恒零** |
| `useE1FormulaEngine.ts` L126~L128 | `calcFxConvert(fc,rate) = fc * rate`，纯乘法 |

### 变异脚本普查（2026-08-15）

17 个脚本 / 9657 行。分母 3/17 · 静态锚点自检 1/17 · 冻结基线 1/17 · WRONG-TEST 13/17 · 锚点唯一性 16/17 · md5 16/17。仅 `mutate_e_cycle_guards.py` 11/11。

**该普查用的是字符存在判据（粗筛），仅用于定缺口规模；Task 10/14 的正式判据必须落在行为/AST 上。** 这一条本身就是本 spec 要防的错的一个实例，故如实标注。

### 与并发会话的边界（开工前必复查）

| 文件 | 立项时状态 | 处置 |
|---|---|---|
| `mutate_k_cycle_guards.py` | `??`，mtime 距调查 5 分钟内 | **不碰**，豁免登记 |
| `mutate_i_cycle_guards.py` | `A `（staged 未提交） | **不碰**，豁免登记 |
| `mutate_ie_lifecycle_guards.py` | clean，spec 在办 24/25 | **不碰**，豁免登记 |
| `backend/data/note_template_soe.json` | 带并发 K 循环 +150/-98 未提交改动 | Task 11 跑全量变异会改它 ⇒ 开工前协调 |
| `.github/workflows/governance-checks.yml` | 带并发 K 循环 +22 未提交改动 | Task 17 用归因型验收 |
| `useE1BankDetail.ts` / `e1BankAccountPrefill.ts` | 立项时 clean | 开工时复查，若并发在编辑先协调 |

### 明确不做（范围外，登记备查）

- E1-10 交叉核对把科目码当账号比对（e-cycle spec 登记的另一处存量口径问题）—— 与本 spec 无文件重叠，建议并入存量口径回填 spec。
- 存量 `el-input-number :formatter` 千分符空操作（40+ 处，EP 2.13.6 无该 prop）—— 属另一个待立 spec。
- 迁移中发现的他 spec 判据缺陷（Property 28）—— 只登记。

### Wave 1 实录之一：变异脚本入库（Task 3，2026-08-15）

commit `45bca0ef`，7 个脚本 / 3108 行入库。

**AC 5.3「确认可运行」的判据被现实改写**：任务原文写「至少 `--list` 或等价只读子命令不报错」，实测 8 个待入库脚本里**只有 `mutate_task13` 有只读子命令**（`--anchors`），其余只有 `--only`/`--restore`，无参数运行即执行变异改生产代码。改用**外部只读探针**提供等价能力 —— import 模块取 `MUTATIONS` 后逐条数锚点命中行数（模块级已用 AST 静态确认无副作用、7 个全有 `__main__` 守护）。判据四项：模块可 import · `MUTATIONS` 非空 · 目标文件存在 · 锚点可唯一定位。**「6/8 缺只读子命令」这件事本身登记为 Wave 4 迁移时要补的能力。**

**结果 84 条变异 / 90 处锚点**：

| 脚本 | 变异 | 锚点 | 可唯一定位 | 漂移 |
|---|---|---|---|---|
| `mutate_task13_wiring_guards.py` | 5 | 9 | 9 | 0 |
| `mutate_task14_cscope_guards.py` | 14 | 14 | 14 | 0 |
| `mutate_task18_suggestion_guards.py` | 7 | 7 | 7 | 0 |
| `mutate_task19_apply_guards.py` | 12 | 12 | 12 | 0 |
| `mutate_task20_review_guards.py` | 14 | 14 | 14 | 0 |
| `mutate_task21_note_linkage_guards.py` | 20 | 20 | 20 | 0 |
| `mutate_task23_baseline_guards.py` | 12 | 12 | **10** | **2** |

🔴 **探针首轮有两处自身缺陷，修正后才得出上表**（对应 memory「ANCHOR-MISS 优先怀疑脚本缺陷」）：

| 首轮误报 | 真因 | 修法 |
|---|---|---|
| `task14` 14 条全 `PATH-MISSING`、mid 显示 `?` | 该脚本**无类定义**，`MUTATIONS` 元素是 **dict**（键 `id`/`file`/`anchor`/…），路径字段叫 `file` 而非 `path`，且已是绝对 `WindowsPath` | 取值改为兼容 dict 与对象两形态，`PATH_FIELDS` 补 `file` |
| `task19` M5 报 `HITS=2` | 探针用 `anchor.strip() in line` 匹配，把锚点的 6 空格缩进抹掉后，4 空格的另一行（L3611）也算进来。用原始锚点只命中 L3582 | 改「原始锚点精确子串」优先，`strip` 仅作参考回退 |

**登记未修（Property 28）**：`mutate_task23_baseline_guards.py` 的 **T23-4 / T23-8** 锚点 `? Number((ctx.accounts as any)[accountName]?.amount)` 在 `ProcedureTrimming.vue` **零命中**（放宽到 `ctx.accounts as any` 仍 0 行）。真因是取金额逻辑已重构为独立函数 `resolveAccountAmount`（L2981 注释「金额走与 `buildAndDecide` **同一个** `resolveAccountAmount`」），而该文件最后一次实质改动正是 procedure-trim 自己的归档 commit `af060c4d` ⇒ **这两条变异在该 spec 归档时就已失效**。之所以无人发现，恰恰因为脚本从未入库、没有 CI 跑它们 —— 这条因果关系是本 spec R5 存在的最直接理由。

**归属查清（AC 5.2 / Property 19）**：`mutate_wp_export_resolver_guards.py` **不入库**。三条判据：① 其变异目标 `wp_export/wp_file_resolver.py` 正是**在办** spec `workpaper-import-export-lifecycle-closure`(24/25) 的核心真源（该 spec 的 design.md 把 `VERDICT_LABELS` / `WP_FILE_VERDICTS` 列为单一真源）② mtime 2026-08-09 早于该 spec 自己的 `mutate_ie_lifecycle_guards.py`(08-12)，属前身工作产物 ③ docstring 写的 `wp-export-file-path-resolution` 在 `.kiro/specs/` 与 `_archive/` 下**均无对应目录**（从未建过）。结论 = 归在办 spec、登记豁免、由其推进方裁决入库或删除（其目标文件与测试当前均存在，脚本主体有效）。

**未触碰**：`mutate_k_cycle_guards.py` · `mutate_i_cycle_guards.py` · `mutate_ie_lifecycle_guards.py`（Property 18）。提交用 `git commit -- <pathspec>` 限定 —— 因为 index 里有并发 i-cycle 会话预先 `git add` 的 8 个文件（含 `mutate_i_cycle_guards.py` 本身），直接 `git commit` 会把它们一起提交。提交后复核这 8 个仍为 staged 未提交态。

### Wave 1 实录之二：跟踪守卫与豁免表（Task 4，2026-08-15）

产物：`backend/data/mutation_kit_exemptions.json` · `backend/tests/test_mutation_kit_scripts_tracked.py`（12 例）· `backend/tests/test_mutation_kit_exemptions.py`（10 例）。**22 passed**。

🔴 **守卫上线第一次运行就抓到一个立项调查时不存在的欠账**：`backend/scripts/check/mutate_report_line_resolution_guards.py`（436 行，`??` 未跟踪）。它属**在办** spec `procedure-trim-report-line-account-resolution` 的 Task 13，实测 mtime **12:08:10** 而抓到时点是 12:14 —— 距创建仅 6 分钟，并发会话正在写。已登记豁免（不代它入库）。这比任何人工构造的变异都更有力地证明了守卫在承重：**它抓的不是历史欠账，是正在产生的欠账**。

豁免表现有 5 项：`k_cycle` · `i_cycle` · `ie_lifecycle` · `report_line_resolution` · `wp_export_resolver`，全部指向在办 spec，每项带 `reason` + `registered_at` + `revoke_when`。

**变异检验 3/3 全 RED**（GREEN=0 / ANCHOR-MISS=0 / WRONG-TEST=0），还原后 md5 与基线逐字相符、复跑回到 22 passed：

| 变异 | 判定 | 命中 |
|---|---|---|
| M1 把某豁免项的 `spec` 换成已归档的 spec 名 | RED | `test_no_stale_exemption_after_spec_archived` |
| M2 移除一条豁免项（未入库脚本应被抓） | RED | `test_every_mutation_script_is_tracked_or_exempt` |
| M3 把 `exemptions[0].reason` 改短 | RED | `test_every_entry_has_valid_fields` |

🔴 **M3 首轮判成 GREEN，实为变异脚本的锚点缺陷 —— 这条教训要带进 Wave 3 的共享件设计**：正则 `"reason": "[^"]{20,}"` 命中的是豁免表顶部 `_schema.reason` 那条**文档说明**，而 `validate_entry` 只校验 `exemptions[]` 内的项 ⇒ 变异落在被测判据的**作用域之外**。按四态定义应记 ANCHOR-MISS，但「新增失败集合是否为空」这个判定式**识别不出「锚点落在作用域外」**，于是把脚本缺陷误报成守卫缺陷。修法是改用 JSON 结构定位（天然落在 `exemptions[0]` 内）并加一句作用域自证断言。⇒ **共享件的 `--list` 校验除了「锚点命中恰好 1 次」，还应支持调用方声明作用域自证**（Requirement 6.7 的实现要覆盖这一形态）。

另一处踩坑：首轮用 `Path.write_text()` 还原，Windows 把 LF 写成 CRLF ⇒ 内容对但 **md5 不符**。全程改 `read_bytes`/`write_bytes` 后逐字相符。这正是 design.md 给共享件定的硬约束（「写回不改 CRLF」）在自己身上先验证了一次。

### Wave 1 实录之三：两个守卫先打红（Task 1 + Task 2，2026-08-15）

产物：`__tests__/e1BankDetailFxForm.spec.ts`（19 例）· `__tests__/e1BankVariantIntegrity.spec.ts`（22 例）。

**先打红基线：41 例 / 24 红，且「标 🔴 的全红、未标记的全绿」—— 假绿 0 / 意外红 0。**

| 文件 | 例数 | 红 | 绿（零回归基线） |
|---|---|---|---|
| `e1BankDetailFxForm.spec.ts` | 19 | **13** | 6 |
| `e1BankVariantIntegrity.spec.ts` | 22 | **11** | 11 |

**观察窗口的选择（Task 1 的关键设计）**：`recalcRow` 未导出，但**不为测试而导出** —— 导出它只能测到它自己，测不到 `loadFromResponses` 的字段归一（`fxRate: parseNum(r.fxRate) || 1` 那行恰是缺陷的一半）。改用 `useE1BankDetail` composable 作观察窗口，经 `@vue/test-utils` 的 `mount` 挂在真实组件上下文里（裸调用会让 `onBeforeUnmount` 脱离组件实例，且 `watch(variant)` 的重算依赖 watch 真实触发）。`classifyFxForm` 用**动态 import + 存在性断言**，这样函数尚不存在时只让那一组红，不至于整个文件 collect error。

#### 🔴 三处判据缺陷（都是我自己写守卫时踩的，逐一记下形态）

**① 断言右侧不得用被测输出算期望值（假绿）**。`Property 13`「原币小计镜像本位币」原本写成：

```ts
expect(row.endingFc).toBeCloseTo(calcCashBalance(row.opening, row.increase, row.decrease), 2)
```

缺陷会把 `row.opening` 抹成 0 ⇒ 右侧算出 0，左侧 `endingFc` 也是 0 ⇒ **恒真式**。首轮该条标了预期红却 passed。修法：期望值取自**输入的原始数**（`calcCashBalance(848871.86, 120000, 641776.66)`）。

**② 预期红的标记规则不能用粗判据**。Task 2 首轮用 `vb === 'multi'` 一律标 🔴，结果「账户级 multi 写入 → multi 消费」标了红却 passed —— 该组合 fc 列齐备（multi 版对本位币账户下发 `openingFc = opening`，恒等事实），multi 消费本就能算对。改用显式预期矩阵 `expectedRedBeforeFix(source, va, vb)`，按「写入侧 fc 是否齐备」+「写入动作本身是否被抹零」两个维度算：

| 来源 | 写入 variant | fc 齐备 | rmb 消费 | multi 消费 |
|---|---|---|---|---|
| 账户级种子 | rmb | 否 | 绿 | **红** |
| 账户级种子 | multi | **是**（本位币恒等） | 绿 | 绿 |
| 叶子口径兜底 | 任意 | 否（fc 恒 0） | 绿 | **红** |
| 手工录入 | rmb | 否 | 绿 | **红** |
| 手工录入 | multi | — | **红** | **红** |

**③ 构造数据自证不能被缺陷带红**。首轮「三个来源都产出了行且带金额」这条因手工录入在 multi 版被抹零而红 —— 于是分不清「构造数据没生效」与「缺陷生效了」。拆成两条：结构自证（行数 + `opening` 字段存在，不受缺陷影响）与金额自证（只对 `zeroedOnWrite=false` 的组合断言）。

#### 🔴 实测发现缺陷的第三个面（比立项登记的更严重）

上表末行「手工录入 / multi 写入」两格都红，追因后确认：**在「人民币及外币」版直接手工填本位币金额（不填原币列），`updateCell` 内的 `recalcRow(row, 'multi')` 当场就把它抹成 0，`scheduleSave` 2 秒后落库的就是 0。**

这不是「切 variant 才丢」，是**填完即失**。而「在 multi 版只填本位币列」是完全正常的用法 —— 该版界面同时显示本位币与原币两组列，审计师若手上只有人民币账户数据，自然只填本位币那组。

立项时 requirements.md 登记的三个面是「种子行 / 切 variant / 落库不可恢复」，此处是第四种触发路径，已由 `zeroedOnWrite` 维度纳入判据矩阵，并单独立一条 `🔴 手工录入在 multi 版下被 updateCell 当场抹零`。Wave 2 的修复必须同时覆盖它（形态 A 判定发生在 `recalcRow` 内，故一处修复即可覆盖，但**必须有这条守卫钉住**）。

#### 绿的 17 例即零回归基线（Wave 2 改实现后必须仍绿）

`e1BankDetailFxForm`：形态 C 由原币派生（1000×7.2 等值取自实测复算）· rmb 分支两条 · 缺失 `fxRate` 回落 1 · 真实汇率原样保留 · 形态 B 本位币列为 0（Property 34）。
`e1BankVariantIntegrity`：三来源 × rmb 消费 5 条 · 账户级 multi→multi · 叶子 rmb 消费 · 写入侧前提两条（账户级 rmb 版确实不下发原币列、multi 版确实下发）· 构造数据结构与金额自证 2 条。

### Wave 2 实录：三形态 + 三态归一 + 落库与聚合守卫（Task 5 / 6 / 7，2026-08-15）

改动集中在 `composables/useE1BankDetail.ts`（**+62 / −1**，该文件上次实质改动是 2026-07-23，无并发冲突），种子侧与持久化层**一行未动**。

**Task 5**：新增导出 `FxForm` 类型与 `classifyFxForm()`；`recalcRow` 的 `multi` 分支前插形态 A 分支。`isBaseCurrency` 从 `e1BankAccountPrefill` 引入 —— 该模块**零 import**，不构成循环依赖（开工前查过三个候选模块的 import 图）。

**Task 6**：`fxRate: parseNum(r.fxRate) || 1` 改为显式三态，注释写明「缺失回落 1 是因为『该行只有本位币列』等价于『原币与本位币恒等』」而非「历史如此」。

**Task 7**：在 `e1BankVariantIntegrity.spec.ts` 追加 7 例，判据落在**序列化输出**与**聚合键取值**上：`persistedRows()` 读 `allResponses[STORAGE_KEY].remark`（`serializeRows` 的真实产物，非内存 `rows`），`crossSheetSnapshot()` 读八个跨 sheet 键。落库形态用 `vi.useFakeTimers()` 推进 `scheduleSave` 的 2 秒窗口拿到，不用手搓。

#### 结果

| 项 | 数值 |
|---|---|
| 两个守卫文件 | 41 → **48 例全绿**（Task 7 追加 7 例） |
| Wave 1 的 24 条红 | **全部转绿** |
| Wave 1 的 17 条零回归基线 | **仍绿** |
| e1 全域回归 | **148 suites / 609 passed / 0 failed** |

609 与 e-cycle spec 冻结基线 `BASELINE_FE_PASSED = 568` 之差恰为 **41**（= 本 spec 新增例数），交叉印证零既有守卫被打破。

#### 变异检验 4/4 全 RED（GREEN=0 / ANCHOR-MISS=0 / WRONG-TEST=0）

还原后 md5 与基线逐字相符、复跑回到 48 passed。

| 变异 | 判定 | 新增失败 |
|---|---|---|
| M1 删掉形态 A 分支（退回无条件由原币派生） | RED | **22** 条 |
| M2 `fxRate` 显式 0 被压成 1（三态退回两态） | RED | 3 条 |
| M3 形态判据改用 `fxRate` 而非 `fxCurrency` | RED | 2 条 |
| M4 `endingFc` 镜像改回由 fc 列算 | RED | 1 条 |

🔴 **M1 打红的 22 条里包含 Task 7 那 7 条**（「在 multi 版编辑一格后落库的本位币列仍是录入值」「切 variant 前后八个聚合键取值相同」×3「E1-1 审定表读取的 institution 期末聚合…」等）。这一点必须单独记：Task 7 的守卫是**在修复之后**写的、一上手就是绿的，属 memory 警告的「守卫把错值当基线锁死」高风险形态。它们能被 M1 打红，才证明承重。

🔴 **M3 的 RED 验证了 design.md 里那个判据取舍不是纸上推演**：把形态判据从 `fxCurrency` 换成 `fxRate === 1` 后，`fc 列全 0 且本位币 → base-identity` 与 `空 fxCurrency 按本位币处理` 两条立刻红 —— 因为归一后「缺失」也回落 1，拿 `fxRate` 判形态会把外币待录入误判成本位币恒等，进而按汇率 1 反填原币（Property 34 明令禁止）。

#### 🔴 自己又踩了写在自己 design.md 里的坑

M2/M4 首轮报 **ANCHOR-MISS（命中 0 次）**：锚点写成了多行、含 `\n`，而工作树是 CRLF ⇒ 字节匹配必然失败。这条坑 design.md §Components 明文写着「`anchor` 非空且**不含 `\n`**」，仍然踩到。

⇒ **给 Wave 3 共享件的硬结论**：「不含 `\n`」不能只写在文档里，必须在 `Mutation` 的**声明期校验**里直接拒绝（`spec.py` 的职责），否则每个调用方都会各踩一次。同理 Wave 1 实录之二记的「锚点落在作用域外」也要在声明期或 `--list` 阶段拦住 —— 两条合起来说明：变异脚本的正确性判据本身就该由共享件强制，而不是靠每个作者记得。

### Wave 3 实录：共享件 + 自身守卫 + 自举变异（Task 8 / 9 / 10，2026-08-15）

产物：`backend/scripts/_mutation_kit/` **8 个模块**（`__init__` / `spec` / `anchor` / `apply` / `runner` / `verdict` / `coverage` / `cli`，约 46 KB）· `backend/tests/test_mutation_kit_capabilities.py`（**40 例**）· `backend/scripts/diagnose/mutate_mutation_kit_guards.py`（**15 条变异，自举**）。

**零第三方依赖**（Property 25）：AST 扫全部 import，外部依赖集合为空，`backend/requirements.txt` 零改动。

#### 自举变异 15/15 全 RED · 覆盖面 3/3 无 GAP · RC=0

用共享件**给自己**跑变异 —— 它同时是共享件的第一个真实调用方，API 表达不出这套用法就说明设计不足。还原全部成功、md5 逐字相符。

| 变异 | 目标 | 命中 |
|---|---|---|
| M01 删锚点唯一性断言 | `anchor.py` | `test_anchor_multiple_hits_is_rejected`（+4） |
| M02 删**定位期**换行检查 | `anchor.py` | `test_find_anchor_rejects_multiline_anchor` |
| M03 整行相等改 strip 子串 | `anchor.py` | `test_anchor_substring_does_not_count_as_hit` |
| M04 删**声明期**换行拒绝 | `spec.py` | `test_multiline_anchor_rejected_at_declaration`（+2） |
| M05 删「new == anchor」拒绝 | `spec.py` | `test_noop_mutation_also_rejected_at_declaration`（+2） |
| M06 删还原 md5 核验 | `apply.py` | `test_restore_failure_is_raised_not_swallowed` |
| M07 删「变异后 md5 未变」检测 | `apply.py` | `test_noop_mutation_reported_as_anchor_miss` |
| M08 允许空分母 | `coverage.py` | `test_empty_denominator_is_rejected` |
| M09 报告不列 GAP | `coverage.py` | `test_tally_reports_uncovered_guard_file` |
| M10 全量运行也走「子集不给结论」分支 | `coverage.py` | 同上（+2） |
| M11 删作用域自证 | `cli.py` | `test_scope_check_failure_is_anchor_miss_not_green` |
| M12 `--list` 的 want 定位永远走成功分支 | `cli.py` | `test_list_fails_when_want_cannot_be_located` |
| M14 豁免项 spec 换成已归档的 | 豁免表 | `test_no_stale_exemption_after_spec_archived` |
| M15 豁免项 script 指向别处 | 豁免表 | `test_every_mutation_script_is_tracked_or_exempt`（+3，跨两个守卫文件） |
| M16 登记日期改非 ISO 格式 | 豁免表 | `test_every_entry_has_valid_fields` |

#### 🔴 变异检验抓出的两个真实缺口（都是首轮才暴露的）

**① M02 首轮判 GREEN —— 定位期的换行检查无任何测试覆盖。** 当时只有 `test_multiline_anchor_rejected_at_declaration` 覆盖**声明期**（`spec.validate_mutation`），`anchor.find_anchor` 里那道**定位期**检查删掉后没有一条测试会红。两层是独立防护：绕过 `run_cli` 直接调 `find_anchor` 的调用方（共享件内部的 `block_range`、临时诊断脚本）走的正是定位期那层。补 `test_find_anchor_rejects_multiline_anchor` 后转 RED，冻结基线 62 → **63**（改动处已注明来源，符合 Property 22 的要求）。

**② 覆盖面 tally 首轮报 2 个 GAP —— 「12 条变异全 RED」时仍有两个守卫文件从未被反证。** 缺口是 `test_mutation_kit_exemptions.py` 与 `test_mutation_kit_scripts_tracked.py`：Wave 1 给它们做过 3 条变异全 RED，但用的是临时脚本、跑完即删、**没有固化**。补 M14/M15/M16 后 3/3 归零。

这两条合起来正是 e-cycle 脚本当年抓出「7 个前端守卫文件从未被打红」的同一形态，只是这次发生在共享件自己身上 —— 分母机制在它的第一个用例上就兑现了价值。

#### 🔴 失效检测实战命中（登记后约 100 分钟）

Wave 1 给 `mutate_report_line_resolution_guards.py` 登记豁免时（12:14），其 spec `procedure-trim-report-line-account-resolution` 实扫 0/16 在办。**约 13:50 跑基线时 `test_no_stale_exemption_after_spec_archived` 打红** —— 并发会话已把该 spec 做完并移入 `_archive/05-business-features/`。

复核：该脚本已被其推进方 `git add`（`A ` 态），归档目录尚未 commit（远端也无），说明并发会话正在收口中途。按 `revoke_when` 撤销该豁免项，并在豁免表加 `_revoked_log` 留档 —— **直接删掉会让下一轮无法判断某脚本是从未登记过还是登记后撤销过**。该脚本转入 Wave 4 待迁清单（属已归档 spec）。

**登记一个 schema 缺口（不在本 Wave 修）**：豁免表只能表达「因 spec 在办而暂缓」，无法表达「spec 已归档但尚未迁移」—— 因为失效检测靠「spec 是否在 `.kiro/specs/` 一级下」这个结构事实，已归档的 spec 天然判为失效。当前处置（撤销 + 转待迁清单）是正确流程，但如果 Wave 4 的迁移跨越多个会话，中间态会缺一个登记位。

#### 🔴 tracked 守卫第二次抓到实时产生的欠账

这次是**我自己刚建的** `mutate_mutation_kit_guards.py`：跑变异基线时 RC=4（基线非空），追因发现是该脚本未入库。`git add` 后基线转 63 passed。第一次是 Wave 1 抓到并发会话的 `mutate_report_line_resolution_guards.py`（mtime 距抓到仅 6 分钟）。两次都不是历史欠账，是**正在产生**的欠账。

#### `--list` 在跑变异之前拦住了两处声明错误

- M12 原写 `line=155` 消歧，实际那行是别的内容 ⇒ `--list` 直接报「消歧行号 155 内容不符」并打印期望/实为
- 顺带发现原本的替换方案会**破坏语法**：`problems.append(` 那处是多行调用，单行替换会留下孤立字符串与右括号 ⇒ 整批测试挂掉，判定退化成 WRONG-TEST/ERROR 而非精确命中。改为条件反转（`if hit_files:` → `if True:`）

这正是 Requirement 6.7 要的：只打印的 `--list` 在 CI 里恒绿，等于没挂。

#### 相对 e-cycle 范式基准的四项新增能力

| 能力 | e-cycle | 共享件 |
|---|---|---|
| 声明期校验 | 无（只在定位期查换行） | `validate_all` 对所有子命令无条件生效 |
| `guard_files` 强制 | 模块级常量，靠约定 | **必填关键字参数**，签名层面不可能省略 |
| `--list` 校验 | 只打印 | 四项校验（声明 / 锚点唯一 / 文件存在 / want 可定位） |
| 作用域自证 | 无 | `Mutation.scope_check`，落在作用域外判 ANCHOR-MISS 而非 GREEN |
