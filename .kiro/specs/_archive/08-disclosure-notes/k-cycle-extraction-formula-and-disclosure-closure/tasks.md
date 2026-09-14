# Implementation Plan: K 循环取数、公式预设与披露附注收口

## Overview

25 个任务分 7 波，收口 K 循环（K0~K13）的「四表入库 → 底稿取数 → 披露表 → 附注模块」全链。

**Wave 1（Task 1~3）必须先对当前状态打红** —— 三个守卫按「类 A 独立口径应全绿 / 类 B 被测实现应全红」分开写，红的消息带「尚未实现（Wave N Task M）」。预期打红：9 处 row_code、4 处方向声明、1 处 `has_account`。

**两条硬前置**：Task 14（附注 `report_row_code`）→ Task 19（`_row_scope`），否则接了即 fail-closed 整表跳过写入；Task 17（列头对齐）→ Task 18（expandable 标记），因为标记落在行上而行集可能随列头修订变化。

**Wave 4（公式预设，Task 11~13）与 Wave 2/3 无文件重叠可并行**，但 `prefill_formula_mapping.json` 被 5 个 spec 共享，改前必查 mtime。

本 spec 的量化台账全部经 2026-08-09 独立复算（连库反查 `report_config` / `account_chart`、openpyxl 直读 14 个源 xlsx、逐块 dump 26 个预设块），**推翻立项初稿 5 处**（动态标记 24→148、括号 4→6 种、`formula_type` 缺失 7→12 块、AUX 维度名、`…` 是否存在）。逐条对照见 requirements.md §核心事实。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "name": "判据先行（守卫先打红）", "tasks": ["1", "2", "3"] },
    { "wave": 2, "name": "科目定位真源改正", "tasks": ["4", "5", "6", "7"] },
    { "wave": 3, "name": "取数装配补齐", "tasks": ["8", "9", "10"] },
    { "wave": 4, "name": "公式预设收口", "tasks": ["11", "12", "13"] },
    { "wave": 5, "name": "附注模板前置（阻塞 Wave 6）", "tasks": ["14", "15", "16"] },
    { "wave": 6, "name": "披露表结构与载荷", "tasks": ["17", "18", "19", "20"] },
    { "wave": 7, "name": "守卫收口与验收", "tasks": ["21", "22", "23", "24", "25"] }
  ],
  "notes": "Wave 1 必须先对当前状态打红。Wave 4 与 Wave 2/3 无文件重叠可并行。Task 14（附注 report_row_code）硬前置于 Task 19（_row_scope），否则接了即 fail-closed。Task 18（expandable）须晚于 Task 17（列头对齐）。"
}
```

## Tasks

- [x] 1. 建 row_code 连库对账守卫（先打红）
  - 新建 `backend/tests/four_table/test_k_cycle_row_code_evidence.py`
  - 按 `row_name` 反查 `report_config` 四变体（排除 `project:%`），断言声明的 row_code 落在该科目名的码集内
  - 反向自检：按 row_code 正查，断言 `BS-081`=实收资本 / `BS-024`=长期股权投资 / `IS-023`=所得税费用 / `IS-022`=利润总额 / `BS-015`=流动资产合计 / `BS-069`=非流动负债合计
  - 分级断言：按 §Data Models 的 `severity` 判定，逐循环输出三级分类
  - 连库形态：一次 `asyncio.run` 取快照 + 全部断言同步（禁每测试各自 async）
  - 预期：当前状态下 9 处 row_code 断言全红、分级输出 4 ACTIVE_WRONG / 1 SILENT_EMPTY
  - _Requirements: 1.1, 1.2, 13.1, 13.5_

- [x] 2. 建方向与宁缺勿造守卫（先打红）
  - 同文件新增：`account_chart` 按 source 分域查方向，断言 credit 科目的循环必须声明 `is_liability` 或 `gross_direction`
  - 断言 `has_account=False` 的循环必须两侧零命中 + 公式 NULL；反向自检「K6 强标 False 必打红」
  - 断言 K6 的 `1481`/`1482`/`2245` 在 client 侧确实存在（推翻旧记载的证据固化）
  - 预期：K4/K5/K7/K3 方向断言红、K6 的 `has_account` 断言红
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 1.8, 1.9, 13.4_

- [x] 3. 建源模板事实守卫（openpyxl 直读，先打红）
  - 新建 `backend/tests/test_k_source_template_facts.py`
  - 冻结 26 张披露 sheet 的：逐字 sheet 名（**6 种括号写法** + K7「国有企业」）、`sheet_state` 全 visible、两级表头 4 循环的 merged ranges、**披露 sheet 内 11 处**动态标记位置与逐字内容、账龄命中位置
  - 冻结全册 **148 处**动态标记与 **5 种写法**分布（`?`41 / `……`91 / `…`10 / `可无限量添加行`4 / `......`2），并断言 **`…` 与 `......` 确实存在**（初稿记「未出现」是错的）
  - 反向自检：断言 `预留` / `可改名` 在 K 类命中数为 0（这两种确实未出现，可作防判据扩容的锚点）
  - 冻结 8 个 workbook 的 hidden `GT_Custom`（K11/K4/K5/K6/K8/K9 无 hidden sheet）
  - 断言源模板 8 处缺陷仍复现（stale 检测：修好后打红提醒移出登记）
  - _Requirements: 8.1, 8.6, 9.1, 10.3, 13.6_

- [x] 4. 改正 `k_cycle_specs.py` 的 row_code 与方向声明
  - 逐条改正 9 处 row_code（Property 2 清单），每条 `row_code_evidence` 写原值 + 该原值实指科目 + 后果分级
  - 新增 `is_liability` / `gross_direction` / `extra_standard_codes` / `provision_row_code` / `trust_report_config` 字段（additive，默认值保持既有行为）
  - K3 补 `extra_standard_codes=('2231',)`；K6 补 `provision_row_code='IMP-007'` 且 `has_account=True`
  - K8 soe 改指 `IS-004`（非派生行）；派生行若无法避免则 `trust_report_config=False`
  - 重写文件 docstring 的「实证表」为本轮连库结果，并写明「禁信静态表、判据在 DB」
  - **删除原有那张记错的「实证表」**（它自称 DB 实证却把两侧行号整体记错一档，留着必被下轮再信一次）
  - 每条改正就地留注释：`原值 / 该原值实际指向的科目 / 后果分级`（ACTIVE_WRONG / SILENT_EMPTY / TRACE_ONLY）
  - 验证：Task 1/2 守卫全绿
  - _Requirements: 1.3, 1.4, 1.5, 1.6, 1.7, 1.10, 1.11, 1.12, 2.1, 2.2, 2.3, 2.4_

- [x] 5. 声明方向后核实 resolved_from 转为 report_config
  - 对有公式的负债类循环（K3/K5/K7）真实库直跑 `resolve_report_line_accounts`，断言 `resolved_from='report_config'`
  - K3 核实 `extra_standard_codes` 的 `2231` 单列不并入 gross
  - _Requirements: 2.5_

- [x] 6. K1/K2 纳入声明真源
  - 把 K1/K2 的私有 spec 收进 `K_CYCLE_SPECS`，保留 K1 的 `provision_row_code`/`provision_name_filter`/`extra_standard_codes=(1131,1132)` 与 K2 的 `BS-014`+兜底 `1901`
  - characterization：收进前后 render 输出（除溯源字段）逐字节相同
  - K0 显式登记豁免（函证循环、无科目余额）
  - `test_cycle_specs_row_code_evidence._all_specs()` 补入 K
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 13.2_

- [x] 7. 撞码守卫与前端科目真源
  - 跨全部循环声明求 row_code 重复，已知合法共享走白名单
    （已由 `test_cycle_specs_row_code_evidence.test_no_two_cycles_claim_same_row_code`
    + `_collide` 替身自检满足，白名单 `{BS-028, BS-029}`）
  - 新建 `k1AccountScope.ts`（运行态读 `tb_source_codes.gross_standard`，常量只作兜底+展示）；
    `k1TbSourceCodes.ts` 的重复定义改为 re-export，既有 import 路径不变
  - 新建 `composables/__tests__/kCycleAccountScopeCrossLock.spec.ts`（不扩展旧
    `kCycleAccountScope.spec.ts` —— 旧文件不校验 row_code，正是漂移未被发现的原因）：
    `stripPy` 剥注释/docstring 后括号配对抽 `K_CYCLE_SPECS`，交叉锁死 13 份 scope
  - 改正前端 12 份 scope 的 row_code 漂移：K3→BS-050 · K4→BS-053 · K5→BS-065 ·
    K6→BS-012(+IMP-007，兜底 `''`→`1481`) · K7→BS-066 · K8→IS-004 · K9→IS-005 ·
    K10→IS-010 · K11→IS-017 · K12→IS-020 · K13→IS-021；函数体兜底字面量收敛为常量引用
  - 顺带收敛 K0 侧：`k0MatrixSpec.spec.ts` 的「K3 分歧仍存在」测试按其自述翻转为
    **双向锁死**；`K1_REPORT_ROW_CODE` 改经 `k_cycle_specs.py` 取真值（render 侧已
    收敛为 `_K1_SPEC.row_code_soe`，不再是字面量）；`k0MatrixDataSources.ts` 的
    `knownGap` 理由更新（2231 走 `extra_standard_codes` **单列不并入 gross**，
    源码实证 `report_line_accounts.py` L515~518 ⇒ 缺口结论仍成立，只是理由变了）
  - 变异检验 13/13 全 RED（零 GREEN/ANCHOR-MISS/WRONG-TEST）；前端 225/225 绿；
    后端 286 passed/1 failed 与基线一致（唯一红 = K6 公式预设，属 Task 11）
  - _Requirements: 3.5, 13.3_

- [x] 8. K6 补 `adjudication_prefill`
  - 镜像 K4 的 `build_adjudication_prefill`（按叶子建行 + 全零跳过 + 降序），资产侧保留符号、负债侧 `abs()`
  - 手工优先（已有持久化审定数则返空）
  - **4.6 前端灰态**：`tb_source_codes.empty_reason` 非空时前端显示「本项目无此科目」而非 `0.00`
    （K6 实测仅 1 个 client 项目有 `1481`/`2245` ⇒ 多数项目会走该降级，是高频可见路径）
  - 反向自检：`empty_reason` 为 null 且金额确为 0 时，仍须显示 `0.00`（「余额为 0」与「无此科目」两态必须可分）
  - _Requirements: 4.1, 4.5, 4.6_

- [x] 9. K1/K2/K4/K6 补 `parent_check`
  - 调共享件 `build_parent_check`，`occurrence=False`
  - 三态：槽 `found=False` 时不产生该键
  - contra 族用 `resolve_leaf_totals`（方向自校验），断言 `diff_parent == 0`
  - _Requirements: 4.2, 4.3, 4.4_

- [x] 10. 语义驱动接线决策（先实证再定）
  - **本会话实证探明磁盘上已交付**（复选框是假红）：`to_semantic_spec` / `semantic_spec_of`
    已删除，`SEMANTIC_BRIDGE_WITHDRAWAL_REASON` + `test_k_cycle_semantic_bridge_is_withdrawn`
    已钉死「不得重新引入」
  - 实证：K 各科目码在项目间是否一致（`account_chart` 按 source 分域 + `account_mapping` 反解漂移）
  - 若基本一致 → 删 `to_semantic_spec`/`semantic_spec_of` + 守卫钉死「不得重新引入」+ 理由写实证结果
  - 若存在漂移 → 接线，且修「硬编码 `row_code_soe`」+ 多槽关闭 `allow_report_config_tier`
  - 无论哪条路都留守卫（防下个会话重新发起批量迁移）
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 11. 公式预设科目与口径改正
  - 扩展 `fix_k_cycle_prefill_presets.py`：26 块的 `account_codes`/`wp_name`/sheet 名改正
  - K8 `分析程序K8-3` 改回销售费用口径；K4/K5/K6 sheet 名保留空格
  - **12 块 / 48 个 cell** 补 `formula_type`（8 块全缺 + 4 块部分缺：K8 审定表 1/8 · K9 审定表 1/9 · K8 分析程序 1/3 · K8 实质性分析 1/5）
  - K10~K13 的「期初余额」格改 `PREV()`（实测四块的「期初余额」与「未审数」**逐字同为** `TB('6xxx','本期发生额')`，损益类无期初余额概念）
  - K5 两处 `PREV()`/`WP()` 实参补空格对齐 `block.sheet`（`审定表K5-1`→`审定表 K5-1` / `明细表K5-2`→`明细表 K5-2`）
  - K8/K9 的 `期初/期末余额` 改 `本期发生额`；未注册列名改注册名或 `PLACEHOLDER`
  - 删 K1/K3 明细块的项目专属辅助项编码；K8/K9 月度明细补到 12 月
  - round-trip 自检（`json.dumps` 不能复现原文即 exit 2）
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10, 6.11, 6.12, 6.13_

- [x] 12. 披露 sheet 预设与覆盖面
  - 新建 `fix_k_cycle_disclosure_presets.py`：26 张披露 sheet 建块
  - ~~审定表块补 `WP()` 引用明细表~~ → **改为披露块单向引审定表**（设计更正，见 Wave 4 补充实录）
  - 无预设 sheet 显式登记 + 理由（K4 两块 `_no_tb_preset_reason`）
  - cell_ref 强制带 `_上市`/`_国企` 变体后缀（`convert_prefill_presets` 二元组去重会静默丢块）
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

- [x] 13. 公式预设守卫扩展
  - 扩展 `test_k_cycle_formula_presets.py`：Property 18~27 全部断言
  - 反向自检：K8 旧值（管理费用 + 6602/6603）必打红
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.1, 7.3, 13.8_

- [x] 14. 附注 `report_row_code` 补齐（阻塞 Task 19）
  - 新建 `fix_note_k_report_row_codes.py`：**4 张**多 owner 共享主表补码（不是 26 章节，实扫更正见 Wave 8 实录）
  - 与 `report_config` **连库**对账（新建 `test_note_k_row_code_evidence.py`，码 + 行名双向锁死）
  - K1 的 `五、8`/`八、9` 与 K3 的 `五、42`/`八、42` 主汇总表逐行定码；利息行零命中故不填 + 登记
  - 单 owner 的 11 个 K 章节登记豁免（Requirement 11.5），覆盖面从 `note_workpaper_sync_registry.json` 反查
  - 顺带修共享 kit：重写 rows 时保留段首码（否则两个幂等脚本互相回退）
  - _Requirements: 11.1, 11.2, 11.5_

- [x] 15. `_row_scope` fail-closed 可诊断
  - 三种成因各配**可操作**话术 + 随返回值下发 `row_scope_unresolved_reasons`（不只进日志）
  - 前端共享文案函数 `shared/rowScopeFailure.ts`，3 个既有消费方接上（防 additive 死字段）
  - 新建 `test_row_scope_failclosed_diagnosis.py`（11 例）+ `rowScopeFailure.spec.ts`（15 例）
  - 单 owner 独占整表者登记豁免已随 Task 14 落地（`SINGLE_OWNER_EXEMPT`，覆盖面反查登记表）
  - _Requirements: 11.3, 11.5_

- [x] 16. 附注结构三向比对守卫
  - 新建 `backend/tests/services/test_note_k_structure_closure.py`（16 例，类 A/类 B 分开）
  - 源 xlsx ↔ 模板 JSON ↔ 前端 sheet 名常量三向逐字（26/26 已对齐，本轮锁死）
  - `report_row_code` 齐备（复用 Task 14 的 PLAN 真源）+ expandable 缺口**显式登记**（源 29 / 模板 0，属 Task 18）
  - _Requirements: 13.7_

- [x] 17. 披露表列头与结构对齐
  - 8.1 / 8.3 / 8.4 实测**已满足**，由 Task 16 的三向守卫锁死（26/26 sheet 名逐字、K1/K6 有 `group`、单级表全标 `flat`）
  - 新建 `test_note_k_column_variant_alignment.py`（13 例）：12 张两版分变体表**正向锁死差异** + 4 张合法共用表登记
  - 8.6 源缺陷登记 + stale 检测（K3 soe `A12='账  龄'` 逐格实证，模板按 listed 的 `项目` 实现）
  - **8.7 真缺口已修**：K11 符号翻转此前只存在于注释与界面文案，代码零实现 → 新增 `k11DisclosureAmount()` 单点翻转 + 前端 7 例
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

- [x] 18. 动态插行区标记
  - `fix_note_k_expandable_rows.py`（幂等，可扩位行唯一写者）：**26 个模板行**覆盖源侧 29 处标记，差额 3 处逐处登记（2 处源侧重复块折叠 + 1 处附注模板无对应表）
  - 逐处实证结论 = 29 处**全部作行**（都在列 A），tasks.md 原写的「作列头」分支不成立；处数也从「11 处」更正为 29 处
  - 词表统一 import `note_expandable_markers`；PL / liability 两个结构脚本的本地词表都改成 import + 本地补充 `....`
  - 共享 kit 新增 `carry_expandable_rows()`：结构脚本整表重写 rows 时按「表尾式 / 锚点式」两种落位分别还原，于是不必改 18 处行骨架
  - 多标记表用 `after_label` 位置锚点；`--check` 按**位置集合**核对（只数个数会假绿）
  - 六个 `--check` 同时归零 + 「26 + 2 + 1 == 29」闭环自检 + 变异 M89~M97 全 RED
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8_

- [x] 19. 账龄枚举与载荷收口（依赖 Task 14）
  - 新建 `backend/tests/services/test_note_k_aging_and_payload_closure.py`（16 例）
  - **K1** 账龄行集已由 `disclosureAgingLabels` 驱动（守卫钉死）；**K3 无账龄枚举表**，tasks.md 措辞过宽（见 Wave 8 实录）
  - soe 首档 `DISCLOSURE_AGING_WITHIN1_SOE` + listed 首档不带「（含1年）」**双向锁死**
  - 账龄作列的表实测 **5 处**（AC 原写 4 处），配「集合完整性」反向守卫防漏登
  - 月度细分行保留 / K3 独立表无账龄行列 / 11 个无账龄循环反向锁死（配扫描面 ≥20 张表自检）
  - 12.1~12.4 / 12.6~12.8 实测已满足，本轮补守卫；K1 无 `build*Columns` 走 AC 允许的「登记 + 守卫」路
  - 载荷补 `_removed_table_keys`（差集）+ `_note_texts` 中文 title + 标签列 key 为 `label`
  - K1 推送路径探明后补齐或登记
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 12.1, 12.2, 12.3, 12.4, 12.6, 12.7, 12.8, 11.4_

- [x] 20. 列 key 风格裁决登记
  - 同循环内列 key 语言一致；跨循环分叉登记 + 理由含「改 key 会丢已录入数据」
  - _Requirements: 12.5_

- [x] 21. 前端契约守卫
  - 新建 `composables/__tests__/kCycleNoteContract.spec.ts`：Property 42~45 + 36~38
  - 反向自检：K8~K13 旧子表名值必打红
  - 源码守卫先 `stripComments()` + 配剥注释生效的自检
  - _Requirements: 12.1, 12.2, 12.3, 12.5, 10.1, 10.6, 13.8_

- [x] 22. 变异检验
  - 新建 `backend/scripts/diagnose/mutate_k_cycle_guards.py`：≥12 变异
  - 三态判定（RED/GREEN/ANCHOR-MISS）按失败测试名集合差集，不看退出码
  - 锚点行级定位 + 命中数必须为 1；备份落 `.bak` + md5 还原核验 + `--restore`
  - targets 覆盖本 spec 全部守卫文件（漏一个 = 该文件守卫全体缺席）
  - _Requirements: 13.9_

- [x] 23. CI 与幂等脚本收口
  - `governance-checks.yml` 新增 job `k-cycle-extraction-formula-closure`（10 步）
  - 幂等脚本 `--check` **2 个**（本 spec 只产出 2 个；Task 14/18 的脚本尚不存在，不预挖占位）
  - 新建 `backend/tests/test_k_cycle_ci_wiring.py`：yml 可解析 / 无重名 job / 引用路径真实存在 / 禁假绿兜底 / 守卫覆盖面登记
  - 顺带修既有 `k-cycle-frontend` job 的两处假绿（`|| echo ::warning::` + 幽灵 vitest 过滤器）
  - _Requirements: 13.10, 13.11_

- [x] 24. 真实库只读验收
  - 新建 `verify_k_cycle_live.py`（只读）：全部在册项目 × 14 循环逐组合直跑
  - 叶子和 == 父额用独立 SQL 交叉核对（不拿被测函数证明自己）
  - 改正前后差异逐条归因到三级分类；无数据组合如实输出「本项目无此科目」
  - 零回归用「当前态 → 施加幂等改动 → 对照」（禁 HEAD-swap）
  - _Requirements: 14.1, 14.2, 14.3, 14.8_

- [x] 25. 浏览器实测与数据复原
  - 覆盖四项：审定表「从四表库带入」/ 溯源面板 / 披露表两变体渲染 / 推送落库
  - 查 `disclosure_notes` 的子表数、列元数据、`expandable` 行
  - 实测前抓基线（全文 + md5 + `jsonb_typeof`）；测后逐字节复原 + 独立只读核实
  - 无活体变体如实登记「未实测」，不用 fixture 冒充
  - _Requirements: 14.4, 14.5, 14.6, 14.7_

## Notes

### Wave 1 实录（2026-08-09，3/25）

**交付**：`backend/tests/four_table/test_k_cycle_row_code_evidence.py`（Task 1+2 合并，连库，46 例）+ `backend/tests/test_k_source_template_facts.py`（Task 3，openpyxl 直读，63 例）。

**首跑状态符合「先打红」设计**：
- row_code 守卫 **22 failed / 24 passed** —— 类 A（判据基础设施自检：快照非空 / 归一化不抹平 / 科目名可解析 / 替身自检）24 条**全绿**，类 B（被测实现）22 条**全红**
- 源模板事实守卫 **63 passed / 0 failed**（源模板是只读事实，本应全绿）

**分级输出（守卫自动产出，Wave 2 修复优先级即按此）**：

| 循环 | 字段 | 现值 | 该码实际指向 | 分级 |
|---|---|---|---|---|
| K9 | soe | `IS-023` | 减：所得税费用 | **ACTIVE_WRONG** |
| K6 | soe | `BS-024` | 长期股权投资 | **ACTIVE_WRONG** |
| K4 | soe | `BS-081` | 实收资本（或股本） | **SILENT_EMPTY** |
| K3 | listed | `BS-053` | 其他流动负债（= K4 的行） | TRACE_ONLY |
| K6 | listed | `BS-015` | 流动资产合计（ROW 派生） | TRACE_ONLY |
| K7 | listed | `BS-069` | 非流动负债合计（ROW 派生） | TRACE_ONLY |
| K8 | soe | `IS-022` | 三、利润总额（ROW 派生） | TRACE_ONLY |
| K10 | soe | `IS-030` | 五、其他综合收益的税后净额 | TRACE_ONLY |
| K11 | soe | `IS-038` | 一码两义（5.其他 / 资产减值损失） | TRACE_ONLY |

**本轮修掉 3 处守卫自身缺陷**（都属「判据写错导致假红」）：

1. `test_snapshot_is_nonempty` 阈值写 `> 500` 而 `report_config` 去重 row_code 实测 **352** ⇒ 反向自检本身假红。按实测值改 `> 300` 并注明来源。
2. 宁缺勿造判据内联在测试体内 ⇒ 若 `has_account=False` 的循环为空则整条静默通过（空转）。已抽纯函数 `_no_account_violations(specs, snap)` + 三个**无条件替身自检**（零命中替身必绿 / 有 chart 命中替身必红 / 有公式替身必红）。
3. **`data_only` 口径错**（本轮最贵一条，详见下方铁律）。

**Task 3 冻结的源模板基线（与初稿全部不同，以守卫为准）**：

| 维度 | 初稿 | 实测（守卫口径） |
|---|---|---|
| 动态标记总数 | 24 处 | **164 处** |
| 写法种类 | 3 种 | **4 种**（`……` 147 / `…` 9 / `......` 4 / `可无限量添加行` 4） |
| `…`（单字符） | 「未出现」 | **确有 9 处**（K6-6 三处 / K8·K9 合同检查表各两处 / K0-3 两处） |
| 披露 sheet 内标记 | 未记 | **29 处**（Task 18 的作业面） |
| 披露 sheet 括号写法 | 4 种 | **6 种** |
| K1 `#REF!` | 11 处 | **每版 35 处 / 两版共 70 处** |
| `?` | 41 处（列为写法之一） | **U+003F 只有 2 处且都是链接提示文字，不是标记** |

`预留` / `可改名` 在 K 类**零命中**已由 `test_absent_marker_forms_have_zero_hits` 钉死（不得加入判据，否则产生永不触发的空转分支）。

**Wave 2 起点**：Task 4（改 `k_cycle_specs.py`）。改完后上表 22 条红应全部转绿，且 `test_two_standards_use_same_row_code_where_db_says_so` 会要求「两准则同号」—— 这与既有 `test_k_cycle_specs.py::test_row_codes_match_report_config_evidence` 的「两侧行号必须不同」**直接冲突**，后者是把错误冻结成「实证」的静态表，Task 4 须一并诚实改写（不是回归）。

### Wave 2 实录 —— Task 5（2026-08-09，5/25）

**交付**：`backend/tests/four_table/test_k_cycle_resolution_live.py`（**连库真跑** `resolve_report_line_accounts`，16 例全绿）+ 变异脚本 `backend/scripts/diagnose/_wip_k_t5mut.py`（**6/6 全 RED**，md5 逐字节还原）。

判据形态刻意选「真跑 resolver 断言返回值」而非源码级断言 —— 后者对「字段声明了但共享件没消费」这类缺口结构上查不出（memory 已记：源码守卫 + 替身单测 + fail-open 三层组合本身就是缺陷模式）。

**Requirement 2.5 验收结论（真实库 8 项目 × 7 循环逐组合直跑）**：

| 循环 | row_code | resolved_from | gross | extra | 结论 |
|---|---|---|---|---|---|
| K3 | `BS-050` | **report_config** | `['2241']` | `{'2231': ['2231']}` | ✅ 转正，且 `2231` 单列**不并入** gross |
| K5 | `BS-065` | **report_config** | `['2801']` | `{}` | ✅ 转正 |
| K7 | `BS-066` | **report_config** | `['2401']` | `{}` | ✅ 转正 |
| K6 资产 | `BS-012` | **report_config** | `['1481']` | 备抵 `['1482']` 经 `IMP-007` | ✅ 转正 |
| K6 负债 | `BS-051` | **report_config** | `['2245']` | `{}` | ✅ 转正 |
| K1 | `BS-009` | report_config | `['1221']` | `{'1131','1132'}` | 本就正确（备抵 `1231-03` 在公式内，`provision_exact=True`） |
| K4 | `BS-053` | fallback | `[]` | `{}` | **符合设计**（四变体 formula 全 NULL + `has_account=False` ⇒ 宁缺勿造） |
| K2 | `BS-014` | fallback | `['1901']` | `{}` | **符合设计**（formula 全 NULL ⇒ 退兜底，属正常兜底非缺陷） |

**两处探针输出容易误判成缺陷，已在守卫里写明并断言其为正确行为**：

1. **K6 的 `provision_resolved_from` 仍是 `fallback`** —— 这是共享件的**保守口径**：`to_original_codes_with_flag` 反解 `1482` 时（多数项目 `account_mapping` 无该记录）`provision_exact=False`，共享件随即把 `provision_from` 降级为 `fallback` 以保 D1 零回归。`provision_row_code` 真正生效的证据是 **`provision_row_code='IMP-007'` 且 `provision_formula` 非空**（实测 `TB('1482', '期末余额')`），守卫按这两个字段断言，不按 `provision_resolved_from`。
2. **K3 的 `signed_codes` 含 `('2231', +1)`** —— 公式 `TB('2241') + TB('2231')` 里 `2231` 符号为正，但它**没有**进 `gross`（`extra_standard_codes` 让共享件把它单列到 `extra`）。守卫双向断言：`'2231' in extra` **且** `'2231' not in gross`，防将来有人「顺手」把它并进 gross 造成跨循环双算（`2231` 属 L2 应付利息）。

**顺带固化的 DB 事实**（守卫已连库断言，避免下轮再查）：`BS-050` 的 soe_standalone/listed_standalone 公式**都是** `TB('2241')+TB('2231')`（consolidated 两变体只有 `2241`）· `IMP-007` **只有 soe 两变体存在**且仅 `soe_standalone` 有公式 · `BS-053`/`BS-014` 四变体 formula 全 NULL · `1481`/`1482`/`2245` 三码在 `account_chart` **仅 client 侧 1 个项目**（standard 侧零命中）⇒ Task 8 的运行期降级是高频可见路径。

**变异 6 条与所抓判据**（每条都核实过红在预期断言上，不是红在无关处）：

| 变异 | 新增失败（节选） |
|---|---|
| M1 撤 K5 的 `is_liability`+`gross_direction` | `test_liability_cycles_resolve_from_report_config` / `test_credit_direction_propagates_to_report_line_spec` |
| M2 撤 K3 的 `extra_standard_codes` | `test_k3_extra_code_is_listed_separately` |
| M3 撤 K6 的 `provision_row_code` | `test_k6_provision_comes_from_independent_report_row` |
| M4 K3 `row_code_soe` 改回 `BS-075` | `test_liability_cycles_resolve_from_report_config` |
| M5 K6 `has_account` 改回 `False` | `test_no_account_flag_matches_db_evidence` |
| M6 K9 `row_code_soe` 改回 `IS-023` | `test_declared_row_codes_belong_to_own_account` |

**Task 5 收口后 K 类全域** = 342 passed / 1 failed，唯一红是 `test_k_cycle_formula_presets::test_main_block_account_codes_correct[K6]`（`account_codes` 应含 `1481` 实际 `[]`）= **Wave 4 Task 11 的作业面**，属预期红不是回归。

**Task 6 起点提示**：K1/K2 已在 Task 4 随声明表一并纳入 `K_CYCLE_SPECS`（本轮真跑已验证两者行为与既有私有 spec 一致），故 Task 6 剩余作业面收窄为 —— ①两个 render 改读共享声明（characterization：除溯源字段外逐字节相同）②`test_cycle_specs_row_code_evidence._all_specs()` 补入 K（**该处 `i-cycle` spec 也要改，需先看它 mtime**）③K0 豁免登记的守卫（声明侧 `CYCLES_EXEMPT_FROM_ACCOUNT_SPEC` 已写，缺守卫钉死）。

### Wave 3 实录 —— Task 6/7/10 状态更正 + Task 8/9（2026-08-12，9/25）

**先更正状态**：Task 6 / 7 / 10 的产物本会话实扫**已在磁盘上**（复选框是假红，前轮中断未回填）。逐条核实并跑绿后回填：

| Task | 产物 | 守卫 |
|---|---|---|
| 6 | K1/K2 已在 `K_CYCLE_SPECS`；两个 render 已改读 `_K1_SPEC`/`_K2_SPEC`；`_all_specs()` 已含 K（配 `test_multi_row_code_extraction_actually_covers_k` 防「裸读 `.row_code` 空转」） | `test_k1_k2_are_in_single_source` / `test_k1_keeps_its_semantics` / `test_k2_keeps_its_semantics` / `test_k0_is_explicitly_exempt` |
| 7 | `k1AccountScope.ts` + `kCycleAccountScopeCrossLock.spec.ts`（420 行，读后端 py 源码交叉锁死 13 份 scope，含剥注释生效自检） | 前端 88 例全绿；撞码走 `test_no_two_k_cycles_claim_same_row_code` + `test_k_row_codes_do_not_collide_with_other_cycles` |
| 10 | 语义桥接已撤回，`SEMANTIC_BRIDGE_WITHDRAWAL_REASON` 含实证（`2241` standard 10/client 8、`2801` 8/5、`2401` 9/6、`6601`/`6602` 10/8 全项目同码同名） | `test_semantic_bridge_is_withdrawn_and_stays_withdrawn` |

**一处原假设被实证推翻（据实记录）**：本会话曾判定「K6 render 自写的 `_liability_spec()` 缺 `is_liability`/`gross_direction` ⇒ 负债侧 `gross` 被判成备抵而变空（活的 SILENT_EMPTY）」。连库逐项目真跑后**不成立** —— `BS-051` 是单码公式 `TB('2245','期末余额')`，不触发 `split_gross_provision` 的备抵拆分，本地版与声明真源解析结果 **8/8 项目逐字相同**。故它是**双真源缺陷**而非活错数：仍按「单一真源 + 死代码立即删除」删本地版、改用 `liability_spec_for`（该函数此前在生产**零消费方**，本次接线后才真正生效）。

**Task 9 的关键设计决定：加共享适配层，不抄第四份。**

共享件 `build_parent_check` 的 `accounts` 形参期望 `SemanticAccountResult`（带 `.slots`），而 K 类拿到的是 `ReportLineAccounts`（扁平 `gross`/`provision`）。K3/K5/K7 各自抄了一份**只有两口径**的本地 `build_parent_check`（缺 `trial_balance` 侧），三份彼此不同。故在 `four_table/parent_check.py` 新增 `build_report_line_parent_check()` 适配器（照 `d_tb_fetch._ParentCheckView` 先例），四个 render 共用。

**第三口径当场抓到真数据问题**（这是共享件存在的全部理由）：K1 在某项目上 `leaf_sum = 88,596,839.09` / `parent = 88,596,839.09`（勾稽完全成立）而 `trial_balance = 258,028,708.86` ⇒ `diff_trial = -169,431,869.77`。**本地两口径版恒报「勾稽通过」**。另在同项目备抵侧发现 `tb_balance` 存负数（`-1,312,178.93`）而 `trial_balance` 存正数，属共享件既有跨表符号口径差（D/H 同款），本轮不改、只如实暴露。

**新增 `wide_prefix_scope` 标记**：`provision_exact=False` 时备抵前缀退化为宽口径（K1 的 `1231-03` → `1231`），而 `1231` 下 `-01/-02/-03/-05` 分属 D1/D2/K1/长期应收 ⇒ 此时 `consistent=True` 只说明「`1231` 全族自洽」，**不**说明本循环备抵已勾稽。不标这个位，审计师会把宽口径自洽误读成本循环勾稽通过。

**Requirement 4.6 的判据被改对（原实现永不触发）**：K6 原 `empty_reason` 判据是 `bool(asset.gross or liability.gross)`。但 resolver 在 `account_mapping` 无反解记录时会把**标准码本身**当原始码前缀返回 ⇒ `gross` 对所有项目恒非空（实测 8/8 项目负债侧都拿到 `['2245']`）⇒ `empty_reason` **恒 None**，用户只看到一片 `0.00` 且无从区分「本项目没这科目」与「余额确实为 0」。判据改为「`tb_balance` 里是否真有匹配叶子」（`leaf_hits`），并从 `EMPTY_REASON_NO_ACCOUNT` 改用 `EMPTY_REASON_NOT_IN_PROJECT`（K6 的 `has_account` 已在 Task 4 实证为 True，再报「标准科目表无此科目」是错的）。

**K6 render docstring 重写**：原文以「DB 只读实证」口吻断言「`BS-015`/`BS-024`/`BS-056`/`BS-079` 四行 formula 全为 None、`1481`/`2605`/`2331` 零命中 ⇒ 宁缺勿造」。实为**拿错 row_code 去查**（那四个码分别是流动资产合计/长期股权投资/△向中央银行借款/资本公积）。已按 Task 4 的正确落点改写并显式标注推翻，避免下轮再被采信 —— 与 Task 4 清理 `k_cycle_specs.py` 旧「实证表」同一性质。

**必须取全量行而非叶子**：三口径的 `parent` 侧读父科目行本身（`parent_totals` 按 `account_code == 前缀`精确取行）。预筛叶子会让 `parent` 恒 0，而共享件对 `parent == 0` 的处理是「该侧不参与 `consistent` 判定」⇒ **三口径静默退化成两口径，不报错也不打红**。故四个 render 改为 `fetch_tb_balance_all` + `select_leaves` 派生叶子；连库核对 4/4 项目叶子集逐字相同（`tb_values` 零回归）。

**真跑验收**（`_wip_k_t89render.py`，8 项目里有 K 底稿的 4 个 × 4 循环）：

| 判据 | 结果 |
|---|---|
| 四个 render 都下发 `parent_check` | K1 4/4 · K2 4/4 · K4 4/4 · K6 4/4 |
| `parent_check` 非空 | K1 4 · K2 4 · K6 4 · **K4 0** |
| K6 下发 `adjudication_prefill` | 4/4 |
| K6 `empty_reason` = NOT_IN_PROJECT | 4/4（原为恒 None） |
| 叶子集与改动前逐字相同 | 4/4 |
| render 抛异常 | 0 |

**K4 的 `parent_check` 为空 `{}` 是三态语义的正确表现**，不是缺陷 —— K4 `has_account=False`（唯一成立的宁缺勿造）⇒ 无前缀 ⇒ 槽 `found=False` ⇒ 按 Requirement 4.3 不产生该键（不得填 0）。

**守卫**：新建 `backend/tests/four_table/test_k_cycle_extraction.py`（40 例全绿）。判据形态刻意避开 grep —— 三口径与三态用**合成行真跑纯函数**断言数值，K6 的 prefill/`empty_reason` 直调纯函数断言符号与分层。

**变异检验 16/16 全 RED**（0 GREEN / 0 ANCHOR-MISS / 0 WRONG-TEST，md5 逐字节还原、基线与还原后失败集合均为空）。过程中**抓到并修掉 1 条真守卫缺陷 + 3 条脚本缺陷**：

- **GREEN（守卫缺陷）**：`test_render_fetches_all_rows_not_leaves` 原本只断言源码里同时出现 `fetch_tb_balance_all(` 与 `select_leaves(`。把 `all_rows = await fetch_tb_balance_all(ctx)` 变异成 `all_rows = select_leaves(await fetch_tb_balance_all(ctx))` 后 —— `parent` 侧当场退化成恒 0，而两个字符串都还在 ⇒ **守卫照样全绿**。这正是「grep 式守卫只查字符串存在」那条铁律的现场复现。已改为 **AST 判据**：取传给 `build_report_line_parent_check` 的第二个实参名，回溯其赋值右侧，断言调用链含 `fetch_tb_balance_all` 且**不含** `select_leaves`。改后同一变异转 RED（M3/M15/M16 三条都抓）。
- **ANCHOR-MISS ×3**：锚点用了字面 `\n` 跨行，在 CRLF 文件必失配（memory 已记此坑）。改单行锚点 + 换一处唯一锚点后全部命中。

**夹具缺陷一条**（不是生产缺陷，记下防再犯）：测试助手写成 `name: str = ""` + `account_name=name or f"科目{code}"`，导致传 `name=""` 被悄悄替换成默认名 ⇒ 「跳过无名行」那条守卫测不到真空名。改 `name: str | None = None` 区分「不关心」与「真空名」。

**全域回归**：`four_table` + `d_cycle_extraction` + K 源模板 + K0 预设 = **2686 passed / 2 failed**，两条红均非本轮引入且已核实归属：

1. `test_k_cycle_formula_presets::test_main_block_account_codes_correct[K6]` —— 会话开始即红，**Task 11 的作业面**。
2. `test_k0_formula_presets::test_known_bad_sheet_names_still_bad` —— E0 已改用「函证结果汇总表E0-1」，白名单该条须移出（规则「只许变短」）。归 **E 循环 spec 遗留**；`prefill_formula_mapping.json` 当前有并发会话未提交的 954 行插入，本轮不碰该文件。

**顺带清理**：K2 的 `ReportLineAccountSpec` 未用 import（既有死 import）已删；`test_k2_account_scope.py` 的 `fetch_tb_balance_leaves` → `fetch_tb_balance_all` 随改名同步（fail-open 语义不变）。

**登记的已知分叉**：K3/K5/K7 仍是本地两口径版。实测**无任何测试或前端消费方**锁死其扁平形状（`{prefix, leaf_sum, parent, diff}`），故技术上可迁移；但迁移不在 Task 9 作业面内，已由 `test_k357_local_parent_check_is_registered_divergence` 显式登记，避免下轮误以为「K 循环已全部走共享件」。**建议**在 Task 24（真实库验收）时一并迁移 —— 它们同样漏第三口径，而第三口径本轮已证明能抓到 1.69 亿级差异。

### Wave 4 实录 —— Task 11 + Task 13（2026-08-14，12/25）

**交付**：扩展 `backend/scripts/fix/fix_k_cycle_prefill_presets.py`（+6 个 Pass、round-trip 闸门、UTF-8 自愈）+ 新建 `backend/tests/four_table/test_k_cycle_preset_closure.py`（21 例全绿）+ 变异脚本 `_wip_k_t11mutate.py`（**14/14 全 RED**）。

**并发安全前置**：`prefill_formula_mapping.json` 已稳定 2 天多未被动（mtime 08-12 11:14），活跃并发会话在做 x3 spec 与 consolidation 组件，与 K 无交集。先做 **round-trip 自检**（Property 25）：`json.dumps(indent=2)+尾换行` **逐字复现**原文 ⇒ 写盘只产生我改动部分的 diff，不会重排 429KB 全文卷入他人成果。该闸门已固化进脚本（不一致即 exit 2 拒绝写盘）。

**改动 66 项**，分六类（每类都有实证判据，非按说法推断）：

| 类 | 项数 | 判据来源 |
|---|---|---|
| 补 `formula_type` | 46 cell / 12 块 | Property 19；按公式函数名推断 |
| 损益类期间口径 | 12 cell | `COLUMN_ALIASES` 已注册 `本期发生额` + D4/G11/G12 既有范式（6xxx 上用了 49 次） |
| K5 实参补空格 | 2 处 | openpyxl 直读源 xlsx：真名确为 `审定表 K5-1` / `明细表 K5-2`（带空格） |
| 删项目专属辅助项 | 12 cell / 2 块 | Property 22；`AUX()` 第三参精确匹配、**不支持通配** |
| 月度补 11/12 月 | 4 cell | 源模板 K8-2/K9-2 列头确为 `1月…12月 + 本期未审合计` |
| 删 K8 死块 | 1 块 | 源 xlsx **无**「分析程序K8-3」tab |
| K6 `account_codes` | 1 项 | 与 Task 4 声明真源对齐（`has_account=True` / 兜底 `1481`） |

**tasks.md 三处描述按实测更正**：① 缺 `formula_type` 是 **46** 个 cell 不是 48；② 「K4/K5/K6 sheet 名保留空格」—— 实测 K4/K6 的 `block.sheet` 本来就对，只有 K5 的**两处公式实参**丢了空格；③ 「K8 `分析程序K8-3` 改回销售费用口径」**改为删块**（见下）。

**推翻设计阶段方案一处**：K8「分析程序K8-3」原计划「改回销售费用口径」。实测该 sheet 在源 xlsx **不存在**（真名是「调整分录汇总K8-3」/「实质性分析K8-4」）⇒ 该块运行时**永不命中、已是死块**；且它 `wp_name='管理费用分析程序'`（K8 是销售费用）、`account_codes=['6601','6602','6603']`（跨销售/管理/财务三费）。把 sheet 指向真名会与既有「实质性分析K8-4」块**撞键**，而它三个 cell 语义已被那块**完全覆盖** ⇒ 按「死代码立即删除」删块，不丢任何取数能力。

**🔴 本轮最重要的发现：`PREV()` 恒返 `None`（fail-closed）。**

`prefill_engine._resolve_prev_formula` 的实现就是 `return None`，docstring 写明理由：`working_paper` / `wp_index` **都没有 `year` 列**（底稿年度维度只在 project 层），改造前的实现声称「从上年底稿取值」但查询里没有任何 year 条件、取值又走真实库零命中的 `parsed_data['cells']`。全平台 161 条 `PREV()` 里 **117 条**第三参是「审定数」—— 若哪天有人把 `cells` 链「修通」而不修年度维度，会取到**本年**值并显示在「上年数」列，那是数字级错误。跨年度取数需数据模型变更，已登记在 `prefill_anchor_map.OUT_OF_SCOPE_CHANGES['prev_year_dimension']`。

**这直接决定了本轮改动的性质**：把 K8/K9/K10~K13 六个「期初余额」格从 `TB()` 改成 `PREV()` 后，它们**取不到数**。这仍是改进 —— 改前它们与「未审数」格公式**逐字相同**（`TB('6117','本期发生额')`），即「本期发生额冒充期初数」= 错数，会被审计师当真并污染同比分析；改后是显示空、由审计师手工填，与 `PREV` 自身「宁缺勿造，绝不回退本年值」的设计一致。已由 `test_prev_is_fail_closed_and_registered_as_out_of_scope` 把这个事实钉死。

**只改 formula，不改 cell_ref** —— `cell_ref` 是**绑定键**不是展示名，三条证据：`prefill_anchor_map` 以 `(wp_code, sheet, cell_ref)` 三元组做锚点键（且注释记着「实测 34 对同 `(wp_code, cell_ref)` 跨多 sheet」）；`wp_template_init_service` 以 `sheet!cell_ref` 判用户自定义公式是否覆盖（改名会让用户已录入的公式失效）；前端 `k0MatrixSpec.spec.ts` 已把 K0 的 cell_ref 与预设逐字锁死。

**过程中修掉 5 处自己的缺陷**（都属「判据写错」，非数据问题）：

1. **`sheet_arg_mismatch` 判据错**：初版判「实参 sheet 名 ≠ `block.sheet`」，把 13 处正常的跨 sheet 引用（审定表引明细表）全报成缺陷。改判「是否存在于源 xlsx 真实 tab 集合」。
2. **探针只扫 K 目录**：把 K8/K9 引用 H1 的 `折旧分配分析表H1-13` 误报成「不存在」（H1 里确实有）。
3. **`PREV()` 第三参硬编码 `'未审数'`**：对审定表成立，但「实质性分析K8-4」块的格是「本年发生额/上年发生额/本年期初/本年期末」—— 没有「未审数」⇒ 指向不存在的锚点。改为取本块内真实存在的 cell_ref。
4. **删块顺序错**：删块放在最后 ⇒ 前面几个 Pass 先给它补 `formula_type`、改口径，再整块删掉，白做一趟且日志留误导记录。改为**最先**删块。
5. **`is_main` 判据两头摇**（本轮最典型）：原判据 `any("ADJ(" in f)` 认不出 K6 主块（它曾走「宁缺勿造」分支被剥成只剩 `PREV`），而守卫的判据是 `ADJ( or PREV(` 认得出 ⇒ **守卫红、脚本报「无需变更」，欠账永远修不掉**；放宽成 `ADJ( or PREV(` 后「实质性分析K8-4」块又被当成审定表、`wp_name` 差点被改成「销售费用审定表」。最终改用 **sheet 名含「审定表」**（结构事实，不依赖公式）。

**两处「Property 22 vs 既有守卫」意图冲突，按 Property 22 改写既有守卫**：`four_table/test_k1_formula_presets.py::test_detail_sheet_still_has_aux_formulas` 与 `formula_management/test_k1_formula_presets.py::test_k1_2_block_contains_no_wp_calls` 都以「K1-2 块非空」作反向自检，与「预设不得含项目专属辅助项编码」直接冲突。改写为「正向断言无写死编码 + 移除动作必须有 `_aux_removal_note` 留痕」，不空转。

**顺带得出的结论（已登记，不在本 spec 作业面）**：按辅助项分行的明细表（K1-2 / K3-2）**本质上不适合静态公式预设** —— 行集依项目而异，而 `AUX()` 不支持通配。正确做法是走 render 侧动态预填（读 `tb_aux_balance` 按本项目实际 `aux_code` 建行，形如 K2/K4/K6 的 `adjudication_prefill`）。

**幂等与边界验收**：`--apply` 后 `--check` 归零（exit 0）；二次 `--apply` md5 不变；**块级差异 16 块全是 K**（15 MODIFIED + 1 REMOVED，非 K 块差异为空 —— 用「对 HEAD 版跑 apply 后逐块比对」证明，而非依赖 `git diff` 上下文推断）。`git diff --stat` 显示 1091 insertions 是因为该文件本来就有并发会话未提交的 954 行插入，我的净增量是 137/170。

**全域回归**：2713 passed / 2 failed。两条红均已定性、非本轮引入：

1. `test_k0_formula_presets::test_known_bad_sheet_names_still_bad` —— E0 已改用「函证结果汇总表E0-1」，白名单该条须移出。归 **E 循环 spec 遗留**。
2. `test_preset_library::test_materialized_inventory_json_consistent`（232 vs 249）—— `inventory.json` 停在 **07-26**（19 天）未重新物化，而这期间多个 spec 往 mapping 加了块。差值**本来是 18 pages**，本轮改动让它**缩小到 17**。重新物化会把并发会话未提交的成果固化进 inventory，不该由本 spec 做。

另有 `formula_management` 目录 21 条失败，逐条定性后与本轮无关：15 条是 sqlite fixture 缺 PG 功能（`pg_advisory_xact_lock` / `wp_formula` 表不存在），2 条 N5 撞键（N 循环数据：`附注披露信息（国企` 少了右括号），2 条 PBT 数值不一致（report/balance_sheet 逻辑），1 条 inventory（同上），1 条 K1-2（本轮引入，**已修**）。

**变异检验 14/14 全 RED**（0 GREEN / 0 ANCHOR-MISS / 0 WRONG-TEST；基线与还原后失败集合均为空，md5 逐字节还原）。覆盖：丢 `formula_type` / 非法类型 / 类型贴错标签 / block.sheet 不存在 / K5 空格丢失 / 损益类余额口径回退 / 期初格回退 `TB()` / 未注册期间字面量 / 重新引入项目专属编码 / 空 cells 无留痕 / 丢 12 月 / 跨循环科目 / `wp_name` 贴错循环 / 复活 K8 死块。

### Wave 6 实录 —— Task 22（2026-08-14，13/25）

**交付**：`backend/scripts/diagnose/mutate_k_cycle_guards.py`（正式变异脚本，合并本 spec 前两轮的两个 `_wip_` 原型并补足覆盖面）。**43 条变异 / 43 全 RED / 0 GREEN / 0 ANCHOR-MISS / 0 WRONG-TEST**，还原干净、基线零漂移。

**任务选择理由**：Task 14/23 当时都不安全 —— 实测 `note_template_soe.json` **35 分钟前**被并发会话改过、`governance-checks.yml` **4.6 分钟前**被改过。Task 22 只新建文件，零冲突。

**覆盖面**：13 个守卫文件（12 后端 + 1 前端），脚本内置覆盖面自检 —— 任何守卫文件未被任何变异指向即 exit 1（漏一个 = 该文件守卫全体未经检验）。

| 变异段 | 条数 | 被变异对象 |
|---|---|---|
| A 声明真源 | M01~M12 | `k_cycle_specs.py`（row_code 回退 / 撤方向 / 撤 has_account / 撤 extra / 撤备抵行 / 撤兜底 / 撤名称过滤 / 撤 K0 豁免 / 复活语义桥接） |
| B 三口径共享件 | M13~M17 | `parent_check.py`（三态破坏 / 禁 contra 方向 / 删宽前缀标记 / 标记恒真 / 丢第三口径） |
| C render 装配 | M18~M27 | K1/K2/K6 render（不下发 prefill / 不下发 parent_check / 行集套 select_leaves / 回本地双真源 / empty_reason 恒 None / 用错常量 / 负债不取 abs / 保留无名行） |
| D 公式预设数据 | M28~M41 | `prefill_formula_mapping.json` 的 14 种 JSON 补丁 |
| E 事实守卫自检 | M42 | 改 `test_k_source_template_facts.py` 自己冻结的 `TOTAL_MARKERS`，验证它真在 openpyxl 直读源 xlsx 而非自我循环 |
| F 前端交叉锁死 | M43 | `k3AccountScope.ts` 的 `K3_REPORT_ROW_CODE_SOE` 改成 `BS-053`（K3 历史错认的码） |

**过程中踩到并修掉 4 处脚本自身缺陷 —— 每一处都会让变异检验整体失效，值得逐条记录**：

1. **🔴🔴 基线求值顺序错（最严重，11 条真 RED 被误判成 GREEN）**：把分组基线写成惰性求值，且首次调用点在 `_apply(m)` **之后** ⇒ 取基线时文件已是变异态 ⇒ 基线把变异造成的失败也算进去 ⇒ `fails - base` 差集恒空 ⇒ 判 GREEN。**基线必须在任何变异之前全部取完**。这个 bug 的可怕之处在于它让脚本「看起来在工作」（还输出了 31 RED），只有对着 `baseline_drift` 里「base=N / now=0」的异常才能发现。

2. **一次跑全部 12 个守卫文件会污染基线**：`test_cycle_specs_row_code_evidence.py` 是**连库**守卫，与其余文件同进程共跑时污染共享连接池（memory 铁律：「每测试各自 async 会让第二个起 `NoneType has no attribute send`」）⇒ 基线出现 **34 条不稳定失败**，而单独跑同样 12 个文件是 417 passed 零红。改为「每条变异只跑它 `expect` 的那几个文件」+ 按分组缓存基线。

3. **空操作变异被误判成 GREEN**：M03 初版的 `anchor` 与 `repl` 写成了同一串（本想撤 K5 的 `is_liability`），变异不改任何东西、当然不打红。已在 `_apply()` 里显式拒绝 `anchor == repl`，并给 `Mutation` 加**正则锚点**支持（K5 的 `is_liability=True` 在文件里出现 5 次，单行锚点无法定位，须用 `\s+` 跨行 —— 而**禁写字面 `\n`**，CRLF 下必失配）。

4. **前端锚点命中 2 次**：`'BS-050'` 在 `k3AccountScope.ts` 里 listed/soe 两个常量都有，锚点须带变量名。这条是靠脚本的「命中数必须恰好 1」自检抓出来的（判 ANCHOR-MISS 而非误判 RED/GREEN），说明该自检有效。

**脚本形态要点**：三态按**失败测试名集合差集**判定（不看退出码 —— 只看退出码会把 GREEN/ANCHOR-MISS/WRONG-TEST 全误判成 RED）；`.bak` 备份 + md5 还原核验，还原失败立即 exit 3；`--restore` 兜底（Ctrl+C 中断后用）；`--list` 只列清单与覆盖面；`--only M07` 单条调试；`--with-frontend` 才跑 vitest（慢）；报告落 `_k_cycle_mutation_report.json`；stdout 强制 UTF-8（Windows GBK 下 `•`/`✅` 会抛 `UnicodeEncodeError`，且它发生在打印阶段、写盘之前，表现为「报错但文件没改」）。

**收尾核验**：`.bak` 残留 0 / 变异特征串残留 0 / `.vitest-mut.json` 已清 / 43 条变异后各分组基线与开跑时逐一相等。

### Wave 6 实录 —— Task 24（2026-08-14，14/25）

**交付**：`backend/scripts/diagnose/verify_k_cycle_live.py`（**只读**）。**8 项目 × 14 循环 = 120 组合，零异常、独立交叉核对 0 不一致、叶子和 == 父额 0 不成立。**

**任务选择理由**：Task 23（CI yml **8.4 分钟前**被并发会话改过）与 Task 12（`prefill_formula_mapping.json` **6 分钟前**被改过）都在活跃编辑窗口内。先核实自己的成果没被回退（`--check` 归零 + 68 守卫全绿，确认并发会话改的是该文件的非 K 部分），再改做 Task 24 —— 新建文件、纯只读、零冲突。

**独立交叉核对是怎么做到「不拿被测函数证明自己」的**：用**纯 SQL** 重算叶子和与父额。叶子判定在 SQL 里表达为「同 `dataset_id` 内不存在以 `本码 + '.'` 开头的兄弟行」，与 `leaf_aggregation.select_leaves` 同口径但实现完全独立。两条路径的口径一致性已实证（同一项目 `all_rows=400` / `leaf_rows=297` 逐一相等）。

| 判据 | 结果 |
|---|---|
| 组合覆盖 | 120（8 项目 × 14 循环，K6 另拆负债侧） |
| render/resolver 异常 | **0** |
| 独立 SQL 与 `parent_check` 不一致 | **0**（112 个可核对组合） |
| 叶子和 ≠ 父额 | **0** |
| 归因分布 | OK 58 / ZERO_BALANCE 19 / NOT_IN_PROJECT 27 / NO_ACCOUNT 8 / EXEMPT 8 |

**归因分五档而非笼统报「无数据」**（Requirement 14.3）：`EXEMPT`（K0 函证循环无科目余额口径）/ `NO_ACCOUNT`（标准科目表就没这科目 = K4，设计期结论）/ `NOT_IN_PROJECT`（科目存在但本项目没用 = 运行期降级）/ `ZERO_BALANCE`（有该科目且金额确为 0 = 合法零值）/ `OK`。后三档的区分正是 Requirement 4.6 要求「两态可分」的验收面 —— 27 个 NOT_IN_PROJECT 与 19 个 ZERO_BALANCE 若混成一档，审计师就无法判断「是没有这项业务」还是「有业务但余额为零」。

**🔴 真实库发现：一个项目的 `trial_balance` recalc 存在父子双算。**

7 条「trial 与叶子和真差异」**全部集中在同一个项目**（重庆和平药房连锁_2025），且形态高度规律：

| 循环 | 叶子和 | trial_balance | 倍数 |
|---|---|---|---|
| K11 | 5,173,701.01 | 10,347,402.02 | **正好 2.00** |
| K12 | −274,933.77 | −549,867.54 | **正好 2.00** |
| K13 | 755,801.83 | 1,511,603.66 | **正好 2.00** |
| K1 | 88,596,839.09 | 258,028,708.86 | 2.91 |
| K8 | 133,145,053.19 | 407,087,784.75 | 3.06 |
| K9 | 28,615,584.26 | 99,635,936.46 | 3.48 |
| K3 | −110,361,076.52 | 328,148,455.95 | 符号亦反 |

「正好 2 倍」是平台铁律「recalc 只汇总叶子」被违反的典型指纹（H8 曾实测 `1651` 是叶子和的 2 倍）；2.9~3.5 倍说明该项目把多层科目都算了进去。这是**该项目的数据问题，不是本 spec 的代码缺陷** —— 且这 7 条 `leaf == parent` **全部成立**，两口径版本查不出任何异常。这就是三口径存在的全部意义，也与 Task 9 引入共享适配器时的实证互相印证。

**trial 差异必须分两类，否则真问题被符号噪声埋掉**：另有 10 条属 `trial_sign_convention_only`（`|leaf| == |trial|` 仅符号相反）—— 那是既有的跨表符号口径差（`tb_balance` 备抵/损益存负、`trial_balance` v2 正数口径），Task 9 实录已登记，不是数据错误。报告把两类分开计数。

**过程中修掉 3 处本脚本的口径缺陷**（都是「核对脚本自己算错，误报生产缺陷」，值得记录形态）：

1. **裸 SQL 求和没实现「方向定符号」约定** ⇒ K3 上 2 处误报：`py_leaf=2,189,098.79` 而 `sql=4,118,101.21`，差值正好 `2 × 964,501.21`（一个 contra 子科目被多加两倍）。`tb_balance` 存在两种符号约定且没有一种对所有项目都对，故交叉核对必须**同时算出两个候选值**，再验证被测函数选中的那个恰好与父额勾稽成立 —— 这样既独立又能判对错。
2. **损益类用了期末余额** ⇒ 34 个损益组合全被报成「与 trial 不一致」。损益科目不结转期末余额（`closing_balance` 恒 0），必须改用发生额（正方向单侧）。
3. **父额也漏了发生额口径** ⇒ 修完 ② 后 `sql_parent` 仍恒 0，42 条误报。父额同样要按 occurrence 分支取 `debit`/`credit`。

**只读性双重验证**：① 静态 —— 剥 docstring 与注释后扫 `INSERT`/`UPDATE`/`DELETE`/`TRUNCATE`/`commit()`/`flush()`/`add(`/`merge(` 零命中（并配「剥注释确实生效」的反向自检）；② 运行前后对 `tb_balance` / `trial_balance` / `ledger_datasets` / `working_paper` / `checklist_responses` / `disclosure_notes` 六张表取行数快照，**完全未变**。连接用 `NullPool` 且 finally 里 dispose。

**零回归不用 HEAD-swap**（Requirement 14.8）：本 spec 改的 `prefill_formula_mapping.json` 混着并发会话未提交的成果，换成 HEAD 版会把别人的改动一起换掉、结果无法归因。改用「当前态 → 施加幂等脚本 → 对照」：`fix_k_cycle_prefill_presets.py --check` 归零即证明当前态已是幂等收敛态（本轮已验，且并发会话改动后复验仍归零）。

### Wave 4 补充实录 —— Task 12（2026-08-12，15/25）

**交付**：`backend/scripts/fix/fix_k_cycle_disclosure_presets.py`（幂等，26 个披露块 / 91 条公式）+ `test_k_cycle_preset_closure.py` 扩到 **31 例**（Property 26/27/28）+ `test_k_cycle_formula_presets.py` 判据更正 + 变异 **M44~M53 全 RED**。

**设计更正：tasks.md 原写「审定表块补 `WP()` 引用明细表」，改为「披露块单向引审定表」。** 原设计会成环 —— 既有「审定表 → 明细表」若再叠「明细表 → 披露 → 审定表」，公式引擎解析时构成三角回路。故披露块**只许**引审定表、**禁**引明细表，并配守卫 `test_disclosure_blocks_reference_adjudication_one_way` 双向断言（缺审定表勾稽也红）。

**🔴 平台系统性缺口：`convert_prefill_presets()` 按 `(page_key, target_cell)` 二元组去重，而 `page_key` 不含 sheet。** 同循环 listed/soe 两个披露块若用同名 cell_ref，第二个被**静默丢弃**。实测 **D1/D2/G14 的既有披露块正处于这种撞键状态**（它们没有守卫，故一直没被发现）。处置：

- K 的 26 个块全部给 cell_ref 加 `_上市`/`_国企` 变体后缀，并配两条守卫（缺后缀 / 同 wp 内撞键）钉死
- **拒绝改 `convert_prefill_presets` 的去重键** —— 影响面覆盖全平台 57 个既有披露块 + 全部审定/明细块，属独立 spec 作业面
- 已在脚本 docstring 与守卫 docstring 双处登记 D1/D2/G14 的存量撞键，供后继 spec 接手

**分母必须用 `(wp_code, sheet)` 对，不能用 sheet 名集合。** K 的 26 张披露 tab 只有 **8 种**括号写法（`(上市公司）`/`（上市公司）`/`(上市公司)`/`（上市公司)`/`（国企）`/`(国企）`/`(国企)`/`（国有企业）`），拿去重后的名字集合当分母会把 26 个块误判成「多了 18 个」。这个缺陷是靠变异 **M45**（把 K1 的 `附注披露信息(上市公司）` 括号「统一」成全角）暴露的 —— 全角写法在 K10/K11 里真实存在，故**逐字校验守卫照样绿**，只有按对判的覆盖面守卫会红。

**旧守卫的两处判据缺陷（本轮一并改写，不是回归）**：

| 守卫 | 原判据 | 问题 | 改法 |
|---|---|---|---|
| `test_detail_blocks_no_wp_back_reference` | 任何块含 `WP(…审定表…)` 即红 | 披露块引审定表是本轮的正确设计，会被误杀 | 限定为**明细表**块；另加 `test_disclosure_blocks_may_reference_adjudication` 正向锁死 |
| `is_main`（`fix_k_cycle_prefill_presets.py` Pass 5） | 公式含 `ADJ(` | 认不出 K6（无 `ADJ`）；放宽到 `ADJ( or PREV(` 又会把「实质性分析K8-4」和披露块误认成审定表 | 统一改为 **sheet 名含「审定表」** |

**K4 宁缺勿造（Requirement 7.2）**：K4「其他流动负债」的 `BS-053` 四变体 formula 全 NULL，且 `account_chart` 按名（其他流动负债）、按码（2301）两侧都零命中 —— 该科目在实务中是报表行、由多个明细按性质归集，四表侧无从取数。故两个披露块**只留审定表勾稽格**、不造 `TB()`，并各写 `_no_tb_preset_reason`（≥15 字）。守卫双向锁死：含 `TB()` 红、缺理由也红（M51/M52）。

**变异检验 10/10 全 RED**（M44~M53；全量 **53/53 RED**，0 GREEN / 0 ANCHOR-MISS / 0 WRONG-TEST）。本轮给变异框架加了 `expect_test` 字段：

> 只判「文件级有新失败」会把 WRONG-TEST 混进 RED —— 同一守卫文件里常有多条测试，变异可能只踩中相邻那条（改 sheet 名既碰覆盖面又碰逐字校验），于是「我以为验的是 A，其实红的是 B」，A 仍未经检验。声明具体测试名后缺任一条即判 WRONG-TEST。

覆盖：删块 / 括号归一 / 编造 sheet 名 / 抹变体后缀 / cell_ref 撞键 / 披露引明细表（成环）/ 删审定表勾稽 / K4 补 `TB()` / 删 K4 登记理由 / 损益类回退余额口径。

**顺带修掉一处共享回归门的间歇假红**：`fix_g_cycle_disclosure_presets.py` 缺 UTF-8 stdout 自愈。守卫 `test_g_cycle_formula_presets::test_disclosure_presets_script_check` 已在**父侧**声明 `encoding="utf-8"`，但**子侧编码未钉** ⇒ Windows 上子进程按 locale（GBK）写管道，结果取决于环境里是否恰好有 `PYTHONIOENCODING=utf-8`（Kiro 终端有、裸 PowerShell 没有），表现为**同一命令时红时绿**。已在脚本内自愈（与本 spec 的 K 脚本同法），并做 HEAD 版对照变异确认：HEAD 版剥掉 `PYTHONIOENCODING` 后输出 GBK 字节（`\xcf\xee\xc7\xb7` = 项欠）⇒ 守卫必红；修后输出 UTF-8 ⇒ 恒绿。**根因修在脚本侧而非守卫侧**，因为 CI、人工执行、守卫三条调用路径都受益。

**回归**：`four_table` + `test_k_source_template_facts` + `formula_management/test_k1_formula_presets` = **2222 passed / 18 skipped / 0 failed**（Task 12 前基线 2212）。`fix_k_cycle_prefill_presets.py --check` 与 `fix_k_cycle_disclosure_presets.py --check` 双双归零。

**一处需知的基线噪声**：全量变异跑的还原后核验报了 `['cross_spec_evidence','row_code_evidence']: base=1 now=0` 漂移 —— 开跑时基线里有 1 条 `test_no_two_cycles_claim_same_row_code` 失败，还原后消失。这是连库守卫的已知不稳定（共享连接池污染），方向是「基线更脏」，对 `fails - base` 差集只会让 RED 更难达成，不会造假绿；且每个文件都过了 md5 逐字节还原校验。事后单独复跑该守卫两次均全绿。

### Wave 7 实录 —— Task 23（2026-08-12，16/25）

**交付**：`governance-checks.yml` 新增 job `k-cycle-extraction-formula-closure`（10 步）+ 新建 `backend/tests/test_k_cycle_ci_wiring.py`（13 例）+ 变异 **M54~M60 全 RED**（全量 **60/60 RED**）。

**🔴 修掉既有 `k-cycle-frontend` job 的两处假绿**（属前一个 spec `k-cycle-four-table-extraction-and-disclosure-completion` 的遗留）：

1. **`|| echo "::warning::K-cycle frontend guards not yet created (Task 22 pending)"`** —— 前端守卫真失败也只留一条 warning、job 照绿。而该 spec 的 `kCycleAccountScope.spec.ts`（44 例）**早已交付**，"尚未创建"的前提不成立，兜底子句纯属没人回来拆的脚手架。
2. **幽灵过滤器 `kCycleFourTableWiring.spec.ts` —— 该文件从未存在。** 本地实测：`npx vitest run kCycleAccountScope.spec.ts kCycleFourTableWiring.spec.ts` ⇒ `Test Files 1 passed (1)`、**exit 0**。原因是 vitest 的位置参数是**子串过滤器**而非文件路径，只要有一个命中，不命中的那个被**静默忽略**。于是 yml 读起来像跑了两组守卫、实际只跑一组，且没有任何信号。已换成真实存在的 `kCycleAccountScopeCrossLock.spec.ts`。

**这一类缺陷的共性：yml 不被任何测试解析，所以「看得见的覆盖面」可以和「真实覆盖面」长期脱钩。** 故本轮的核心交付不是那个 job，而是**看守 job 自身的守卫**。四条判据全部落到真实解析上：

| 判据 | 实现 | 拦的形态 |
|---|---|---|
| 引用路径真实存在 | 逐个 `Path.exists()`（含 `>-` 折叠块解析） | CI 引用改名/删掉的测试文件 ⇒ pytest exit 4 |
| vitest 过滤器命中 ≥1 文件 | 在前端目录逐个解析 | 幽灵过滤器（vitest 静默忽略） |
| K job 内禁假绿兜底 | 扫 `\|\| echo` / `\|\| true` / `continue-on-error: true`，跳过注释行 | 脚手架残留 |
| 无重名 job | **原始文本**逐行数（不用 `safe_load`） | `safe_load` 对重复 key 静默保留最后一个 ⇒ 前一个 job 整段消失且零报错 |

每条都配了反向自检（解析器必须真切出 3 个 K job 且每块含 `run:`；假绿检测器对三种真实形态必须命中；`total >= N` 下限防解析器返空导致空转）。

**连库守卫不进 CI —— 是登记，不是遗漏。** `test_k_cycle_row_code_evidence` / `test_k_cycle_resolution_live` 按 Property 1 要求「连不上库判红而非 skip」。实扫全部 `V*.sql`：`report_config` 与 `account_chart` **各 0 条 INSERT**（不由迁移灌数），故 CI 的 postgres service 只能给出空表 ⇒ 放进去必然全红。仓库现有连库 job 之所以能绿，是因为那些测试在表空时 skip。处置：

- 写进 `_LOCAL_ONLY_DB_GUARDS` 并各配 ≥15 字理由
- `test_db_guards_are_registered_as_local_only` **双向**锁死：名单里混进离线守卫会打红（防「登记」退化成免 CI 的后门）；连库守卫漏登记也打红
- `test_migrations_really_do_not_seed_report_config` 让**登记理由本身**受监督 —— 哪天有人加了 seed 迁移，这条打红，提醒把连库守卫**收回 CI**，而不是让名单固化成永久借口

**守卫文件清单走单一真源**：`test_every_guard_file_is_in_ci_or_registered` 从变异脚本的 `GUARD_FILES` 读清单（那边本来就有「每个文件至少被一条变异指向」的覆盖面自检）。于是新加一个守卫文件必须同时被变异覆盖、且进 CI 或进登记名单，三处联动。

**🔴 本轮踩到并修掉一个「守卫正则命中自己源码」的坑，值得单列**：连库判定初版是 `_DB_MARK = re.compile(r"create_async_engine|app\.core\.database|DATABASE_URL")` 扫文本。但**本守卫文件自己**就得写出这些标识符（清单、注释、断言消息都提到），于是它把自己判成连库守卫 ⇒ 「连库守卫未登记」在**基线上恒红** ⇒ 差集把真失败一起减掉，把 M59 污染成 WRONG-TEST、M60 污染成 GREEN。改成 **AST 结构判定**（只认 `ImportFrom` 到 `app.core.database`/`sqlalchemy.ext.asyncio`、引用 `create_async_engine` 等构造名、`os.environ[...]`/`getenv(...)` 读 `DATABASE_URL`）后 7/7 转 RED。并加 `test_db_guard_detector_is_structural_not_textual` 三向反向自检（本文件必判 False、两个真连库必判 True、离线守卫必判 False）。

这也是 `expect_test` 字段（本 spec Task 12 引入）第一次真正起作用：**若只判「文件级有新失败」，M59 会因为踩中相邻那条守卫而被记成 RED，缺陷就此漏过**。

**依赖装法从「挑包」改成「装全量 requirements」**：本 job 的守卫 import 真实生产模块（`app.routers.wp_render_strategies` / `app.services.prefill_engine` / `app.services.formula_engine`），import 闭包含 FastAPI、pydantic-settings、SQLAlchemy。挑包装会在 CI 上以 `ImportError` 收场而本地全绿 —— 又是一类「只有 CI 才暴露」的假绿。`PyYAML`（CI 接线守卫要用）与 `openpyxl`（源模板事实守卫要用）均已在 `backend/requirements.txt` 内。同理把守卫里的 `pytest.importorskip("yaml")` 改成硬 `import yaml`：PyYAML 缺失时必须打红，`skip` 会让 Requirement 13.11 的两条判据静默空转。

**回归**：`four_table` + `test_k_source_template_facts` + `test_k_cycle_ci_wiring` + `formula_management/test_k1_formula_presets` = **2243 passed / 18 skipped / 0 failed**。`yaml.safe_load` 解析通过（147 个 job），新 job 10 步、无 `continue-on-error`。

### Wave 8 实录 —— Task 14（2026-08-12，17/25）

**交付**：`backend/scripts/fix/fix_note_k_report_row_codes.py`（幂等，补 6 个段首码）+ `backend/tests/four_table/test_note_k_row_code_evidence.py`（**连库**，10 例）+ `backend/tests/services/test_note_structure_kit_row_codes.py`（8 例）+ 共享 kit 新增 `carry_row_codes()` + 变异 **M61~M69 全 RED**（全量 **69/69**）。

**作业面从「26 章节」更正为「4 张表」。** tasks.md 原稿按章节数估工，实扫 `note_workpaper_sync_registry.json` 后：13 个 K 循环占 26 个章节，但**只有两对章节是多 owner 共享**的 —— `五、8`/`八、9`（K1 + G2 + G3）与 `五、42`/`八、42`（K3 + M1）。其余 11 个 K 章节单 owner 独占整表，按 Requirement 11.5 登记豁免即可，**根本不需要段**（`report_row_code` 是切段依据，单 owner 表切段没有意义）。

覆盖面**不靠这个结论硬编码**：脚本的 `_check_coverage()` 从同步登记表反查每个 K 章节的 owner 数 —— >1 个必须出现在补码计划里，恰好 1 个必须出现在豁免名单里，且名单里的条目必须**确实**还是单 owner。将来任何一个 K 章节被别的循环挤进来共用，`--check` 立刻打红。

**判据全部来自 `report_config` 连库实查**（Requirement 11.2 明令「SHALL NOT 按行名猜」），查出两条必须逐变体分开处理的事实：

| 行 | listed | soe |
|---|---|---|
| 其他应收款 | `BS-009` | `BS-009`（模板行名带「项」，按 owner 映射不按字面） |
| 其他应付款 | `BS-050` | `BS-050`（soe 侧另有同名 `BS-075` 但 formula 为 NULL，取有公式者） |
| 应付股利 | `BS-055`（`应付股利`） | `BS-076`（`其中：应付股利`） |
| 应收股利 | **零行 → 不填** | `BS-016`（`其中：应收股利`） |
| 应收利息 / 应付利息 | **四侧零行 → 不填** | **四侧零行 → 不填** |

- **利息行不造码**：CAS 2019 修订后资产负债表已无「应收利息／应付利息」两行（并入其他应收款/其他应付款），`report_config` 四个准则下零命中。造一个码等于造假勾稽。它们在主表里位于**首个段首之前**，`split_segments` 本就不把这段并入任何 owner ⇒ 无码不影响 K1/K3 写自己的段，也不会被谁覆盖。守卫用 `LIKE` 计数**正面举证**「该行名确实零命中」；哪天 `report_config` 补了这行，守卫打红，提醒去补码而不是让它继续空着。
- **`BS-016` 只能写进 soe 模板**：它是平台已知的**两侧异义**码（listed 侧 `BS-016` 是「一年内到期的非流动资产」）。写进 listed 就是错行。这也是守卫为什么不只校验「码存在」、还要校验「码指向声明的 `report_row_name`」—— 平台已有 `BS-016` 异义与 `BS-022/025/026` 连续偏移一位两个先例。

**修好的到底是什么：从「整表 fail-closed」到「可定位段」。** 补码前 `五、8`/`八、9`/`八、42` 三张主表的 `report_row_code` 全缺 ⇒ 段数 0 ⇒ owner 带 `_row_scope` 推送时 `find_segment` 返 None ⇒ **整表跳过写入**（`_merge_rows_by_scope` 返 `owner_row_code_not_in_template`）。这正是 Task 19 的硬前置。守卫不满足于「模板里有这个字符串」，直接调生产函数 `resolve_segment_window()` 验「运行期定位得到可写段」，并另断言 `合计` 行落在可写区之外（owner 推送不得删表级合计）。

**🔴 副作用与共享件修复：两个幂等脚本原本会互相回退。**

`fix_note_k_complex_structure.py`（K1/K6 结构对齐）会**整表重写** `五、8 其他应收款` 的 `rows`，而它的行骨架（`data_row(...)`）不带段首码 ⇒ 一跑就把我补的码抹掉、我的脚本再跑又补回来，两个 `--check` **永远不可能同时归零**。实测形态是 `rows：4 → 4 项` —— 行数一模一样、只差一个键，看日志极易忽略。

修在**共享 kit** `_note_structure_kit.apply_plan()`：新增 `carry_row_codes()`，重写 rows 时按 **label**（不是下标 —— 结构修订会插删行导致串位）搬运既有 `report_row_code`；同名行 >1 时不搬并记 warning（猜错段归属比不搬更糟）。修在 kit 而非逐个脚本，因为所有 `fix_note_*_structure.py` 都走 `apply_plan`，谁重写 rows 都会遇到同一个问题。配套守卫含**接线自检**（打桩确认 `apply_plan` 真的经过搬运函数 —— 否则函数写得再对也可能是死代码）与**反向自检**（绕过搬运必然丢码）。

**牵动另一个 spec 的三处冻结基线**（`disclosure-note-row-level-merge`，spec 目录已归档、三个文件 git-clean 且 5~12 天未动，故可安全修改）：共享表数 `listed 23→24 / soe 6→8`（合计 29→32）、可写区窄于段区间的段数 `15→18`（三张新共享表末行都是 `合计`，各自末段 `data_end` 收窄一行 —— 正是期望行为）。三处都写明了新增的是哪三张表与原因，并重跑 `gen_note_shared_table_segments.py --write` 同步了清单。`五、8`（listed）**有意只有 1 个段首码**，故不计入共享表 —— 变异 M67 把基线改错 1 来验证清单真按模板重算而非自我循环。

**零回归用「隔离判据」而不是 HEAD-swap**：两份附注模板混着并发会话大量未提交改动（`_aligned_at` 时间戳、列 key 重命名等），换 HEAD 版会把别人的改动一起换掉、结果无法归因。做法是写一次性脚本**只撤掉我加的这 6 个键**跑基线、再复原：`backend/tests/services` **47 failed → 49 failed → （修 kit 后）47 failed**，逐个 nodeid 差集为空。那 47 条是并发会话的既有欠账，与本 spec 无关。

**回归**：`four_table` + K 源模板事实 + CI 接线 + 共享表段 + kit 搬运 + K1/K6 结构 + K1 预设 = **2362 passed / 18 skipped / 0 failed**。三个 `--check`（`fix_k_cycle_prefill_presets` / `fix_k_cycle_disclosure_presets` / `fix_note_k_report_row_codes`）与 `gen_note_shared_table_segments --check` 全部归零，且 `fix_note_k_complex_structure --check` 同时归零（互相回退已解除）。

**顺带修掉第二个 GBK 假红**：`gen_note_shared_table_segments.py` 成功分支打印 `✓`（U+2713），Windows GBK 控制台下 `--check` 会以 `UnicodeEncodeError` 崩掉、退出码非 0 ⇒ 命令行看「清单明明最新却报失败」。既有守卫 `test_check_passes` 是**进程内**调 `main()`（monkeypatch argv），pytest 捕获的 stdout 不是 GBK 控制台，故一直没暴露 —— 典型的「守卫覆盖了逻辑但没覆盖调用形态」。已按同一 `_utf8_stdout()` 范式在脚本内自愈。本会话这已是第二例（前一例是 `fix_g_cycle_disclosure_presets.py`），**建议单开一个 spec 横扫全部幂等脚本的 stdout 编码**。

### Wave 8 实录 —— Task 15（2026-08-12，18/25）

**交付**：`wp_disclosure_sync_service` 新增 `describe_row_scope_error()` + `_ROW_SCOPE_ERROR_HINTS`（三成因话术）+ 返回值 additive 加 `row_scope_unresolved_reasons` + 前端共享文案 `composables/shared/rowScopeFailure.ts` + 3 个既有消费方接上 + `test_row_scope_failclosed_diagnosis.py`（11 例）+ `rowScopeFailure.spec.ts`（15 例）+ 变异 **M70~M74 全 RED**（全量 **74/74**）。

**先实证再定作业面：fail-closed 本身早已做对，缺的是「为什么」。** `_merge_rows_by_scope` 返 `(rows, error)`、调用方跳过写入并保留既有数据、`row_scope_unresolved` 也已进返回值且**前端真在消费**（E1/D1/受限资产三处 `ElMessage.warning`）。真正的缺口是：界面只说「这张表没同步成功」，而三种成因的**修法完全不同** ——

| 错误码 | 该找谁改什么 |
|---|---|
| `variant_unresolved` | 项目设置里把适用准则填对（**不是**附注模板的问题） |
| `template_table_not_found` | 底稿声明的表名与附注模板不一致（改底稿或改模板） |
| `owner_row_code_not_in_template` | 附注模板缺段首码（跑 `fix_note_k_report_row_codes.py --apply` 那一类脚本） |

把三条岔路合成一条死胡同，就是「静默」的另一种形式 —— 审计师看不到后端日志。故原因必须**随返回值下发**并显示在界面上。

**守卫判据不用「字符串存在」**：从 `_merge_rows_by_scope` 源码里抽出它**真正会返回**的错误码字面量，逐个要求有话术，且话术表里不许有源码已不返回的死码（双向）。将来加第 4 种成因忘配话术会打红，而不是静默落到兜底。另加「话术必须含动作词、长度 ≥20」防止退化成「把错误码翻成中文」。

**additive 字段最常见的死法是「加了没人用」**，所以前端侧同时做了两件事：①把三处各写一份的提示文案收敛成共享函数 `rowScopeFailureMessage()`（含后端未给原因时的显式兜底）②守卫逐个消费方断言「真的读了 `row_scope_unresolved_reasons`」「走共享函数」「不再自拼『段边界解析失败）：』文案」。变异 M74 把消费方改回自拼文案 ⇒ 打红。

**🔴 本轮自己写的守卫被变异抓出一处假绿，形态值得单列：**

```python
assert _ROW_SCOPE_ERROR_FALLBACK in msg    # ← 把常量改成 "" 依然通过
```

空串是任何字符串的子串。变异 M73 把兜底常量改成 `""`（正是这条要拦的「静默」）却判 GREEN。这属于 memory 已记的「守卫把错值当基线锁死」的变种 —— **自我引用**：拿被测常量当判据，常量怎么变判据就怎么变。改成不自我引用的写法（`len(常量) >= 10` + 断言消息里含**字面量**「段边界解析失败」「日志」）后转 RED。

**🔴 另一处过程事故：变异脚本被 Ctrl-C 中断后生产文件停在变异态。** 现象是随后 `test_row_scope_failclosed_diagnosis` 4 例红、报 `KeyError: '其他应付款'` —— 因为 M72 当时的实现是**删掉** `reasons[key] = ...` 赋值，而紧随其后的 `logger.warning(..., reasons[key])` 还在。两个教训：

1. **判「是不是自己刚改坏的」要查文件实际内容，不能只看 `restored_clean: true`** —— 那是上一次完整跑的结论，中断的那次不会写报告。本轮靠「变异报 ANCHOR-MISS（锚点 0 命中）」反推出「代码已经是变异态」。
2. **变异的落点要选「不会连带崩」的那一处**：M72 已改为把 `return scoped, unresolved, reasons` 换成 `return scoped, unresolved, {}` —— 精确复现「原因不进返回值」，而不是让代码抛 `KeyError`（那测出来的是「崩了」不是「缺原因」）。

**回归**：`four_table` + K 源模板事实 + CI 接线 + 共享表段 + 行级合并 + 同步 characterization + kit 搬运 + K1 预设 = **2394 passed / 18 skipped / 0 failed**；前端 6 个套件 **188 passed**；`backend/tests/services` **47 failed = 并发会话既有基线，净增 0**。

**另一笔账（登记不做）**：`_drop_removed_tables` 返回的 `dropped` 至今只进日志、未进返回值（`test_disclosure_sync_characterization` 里有 `assert "dropped_tables" not in result` 明确登记）。形态与本轮修的完全同类，但属另一个 spec 的作业面，本轮不动。

### Wave 8 实录 —— Task 16（2026-08-12，19/25）

**交付**：`backend/tests/services/test_note_k_structure_closure.py`（16 例，**全绿**）+ 变异 **M75~M80 全 RED**（全量 **80/80**）。

**先实测三向现状，结论推翻了 Task 17 的作业面预估。** 立项时以为「13 个 `X_DISCLOSURE_SHEET_NAME` 需逐字对齐源 xlsx」，实测**26/26 已经逐字对齐**（含全部 6 种括号写法：`(上市公司）`/`（上市公司）`/`(上市公司)`/`（上市公司)`/`（国企）`/`(国企）`/`(国企)`/`（国有企业）`），同步登记表的 26 条 sheet 名也全对。模板侧 `columns` 26 个章节 **一处不缺**（前一个 spec 的批 1~3 结构脚本已做完）。所以 Task 16 的价值不是「先打红」，而是**把已经对的东西锁死**，防后续「顺手统一括号」把它改坏。

真正剩下的缺口只有一个：**模板侧 `expandable` 行数 = 0，而源 xlsx 披露 sheet 内有 29 处动态插行标记**（Task 3 已逐处冻结坐标）。这是 Task 18 的作业面。

**缺口的处置方式（不是「锁住错值」）**：登记常量 `TEMPLATE_EXPANDABLE_ROWS_PENDING_TASK18 = 0`，**两侧数字都现场实测** —— 源侧取 Task 3 冻结的 `DISCLOSURE_MARKERS`（并配「逐处清单数 == 总数」「坐标形态合法」的自检，防源侧判据空转），模板侧现扫。Task 18 一落地本条即打红，必须连同逐处判定结论（作行 / 作列头）一起更新。再加一条反向守卫：模板里若在**源 xlsx 没有标记**的循环上标了 `expandable`，打红（防凭空标）。

**类 A / 类 B 分开写，且类 A 有下限自检。** 平台已有多处教训：抓不到东西的比对器永远「零不匹配」。本轮**当场踩了一次** —— 写探针时正则只截到行尾，而前端 sheet 名常量是多行 `Record<Variant, string>` 对象 ⇒ 一个值都没抓到 ⇒ 报告「不匹配 0 处」，看起来像三向已对齐。改成**花括号配对**截取后才抓到 26 个值。故守卫里钉了三条下限：前端常量 ≥26 个值 + 每个循环都抓到 ≥1 个、遍历表数 ≥50、`headers` 实际比对数 ≥40（`headers` 可缺省，若全缺省那条循环一次都不比 = 恒绿）。

**另修掉一处自己写的空断言**：`assert (源, 模板) == (源, 登记值)` 里第一项自己跟自己比，等于只比了第二项。已改成只比模板侧一个数，源侧由独立的反向自检覆盖。这与 Task 15 那条「拿被测常量当判据」是同一族形态 —— **判据里出现被测对象本身，就要停下来想它是否恒真**。

**变异 6/6 全 RED**：前端括号归一 / 登记表 sheet 名脱钩 / 模板表 columns 清空 / 两列同标 `is_label` / 单级表头凭空加 `_column_groups` / 缺口登记值被上调（假装 Task 18 已收口）。其中登记表那条**必须走 JSON 补丁**：`"sheet_soe": "附注披露信息（国有企业）"` 在登记表里出现 **20 次**（多循环共用写法），文本锚点必 ANCHOR-MISS，改按 `wp_code` 定位。

**回归**：**2410 passed / 18 skipped / 0 failed**。

### Wave 8 实录 —— Task 17（2026-08-12，20/25）

**交付**：`backend/tests/services/test_note_k_column_variant_alignment.py`（13 例）+ `k11NoteSectionMap.k11DisclosureAmount()`（**新增实现**）+ `k11DisclosureSign.spec.ts`（7 例）+ 变异 **M81~M88 全 RED**（全量 **88/88**）。

**七条 AC 逐条实测，只有一条是真缺口。**

| AC | 实测状态 |
|---|---|
| 8.1 sheet 名逐字 | **已满足**（26/26，Task 16 已锁） |
| 8.2 两版分变体 | **已满足**（16 张同名表里 12 张两版列头确实不同），缺的是守卫 |
| 8.3 两级表头用 group | **已满足**（K1/K6 有 `_column_groups`，Task 16 已锁） |
| 8.4 单级表标 `flat` | **已满足**（模板侧逐表实扫零缺口） |
| 8.5 两侧表态 | **已满足**（K2~K7 推 columns 且都表态；K1/K8~K13 **不推 columns**，列头来自模板 seed，没有第二侧可表态） |
| 8.6 源缺陷登记 | **缺登记**（只有 K1 `#REF!` 在 Task 3 登记过；K3 soe 标签列这处没登记） |
| **8.7 K11 符号翻转** | **🔴 未实现** |

**8.7 是本轮唯一的行为修复，且它的原状正是「文档说了、代码没做」的标本。** 源 xlsx 两版末行注「本科目明细表按照正数填列、披露表按照负数填列」，`k11NoteSectionMap.ts` 的文件头注释抄了这句、`K11TabDisclosureListed/Soe.vue` 的界面提示也写了「披露表按负数（"—"号）填列」—— 但**全链搜不到任何一处翻转代码**（`* -1` / `negate` / `flipSign` 全零命中）。于是附注里的资产减值损失以**正数**出现，与利润表口径相反，而且没有任何测试会红。

修法：在**唯一载荷构造口** `buildK11SyncPayload()` 里单点翻转，新增 `k11DisclosureAmount()`。三条边界都写进实现与守卫：

- `0` 翻转后仍是 `0` —— 不得产出 `-0`（`-0 === 0` 为真，只有 `Object.is` 能区分，而界面会显示「-0.00」）
- 非有限值（`NaN`/`Infinity`）原样返回，**不伪造成 0**（那是造数据）
- **负数输入照常翻成正数** —— 本函数是口径转换，不是「取负绝对值」。底稿里若录了负数说明录入口径错了，应在录入侧修，这里悄悄吸收会把录入错误藏起来
- 不就地改写入参（组件后续还要用原数组渲染底稿的正数）

配 `test_k11_flip_is_single_point`：组件里再翻一次会**翻回正数且不会报错**，故扫 `K11*.vue` 禁出现第二处翻转（跳过注释行）。再配「源 xlsx 两版确实写着『负数填列』」的反向自检 —— 否则上面几条就是「按注释办事」，而注释本身可能抄错。

**8.2 的守卫方向是「必须保持不同」而不是「必须相同」。** 12 张表两版用语真的不一样（`上年年末余额` vs `期初余额`、`项目（或被投资单位）` vs `项目`、K3 soe 主表标签列是 `类别`、K5/K7/K10 两版列数都不同）。一旦有人「统一成一份常量」，一侧用语整体错掉，而**列数相同的那几张不会有任何报错**。另配 4 张「两版确实相同」的登记（K1 重要逾期利息 / K11~K13 损益三列表）+ 两份登记表不得交集的自检。

**8.5 的「两侧」要先确认第二侧存在。** K1/K8~K13 前端根本不推 columns（列头由模板 seed 提供），对它们要求「载荷侧也表态」是无对象可查的空转。故按实测把「推 columns 的循环」列成清单（K2~K7），并加反向守卫：**清单外的循环若其实推了 columns，打红** —— 防清单与代码脱钩后 8.5 判据静默失效。

**变异 8/8 全 RED**，其中一条踩到框架限制值得记：`frontend=True` 的变异只会跑前端守卫，所以 M83 里写后端测试名会判成 WRONG-TEST（前端确实红了、但不是声明的那条）。同一条变异**不能横跨两个 runner**，故拆成 M83（前端，验载荷金额真变负）+ M88（后端，验静态守卫抓出「未实现」）。

**回归**：后端 **2423 passed / 18 skipped / 0 failed**；`backend/tests/services` **47 failed = 既有基线，净增 0**；前端相关 5 个套件 **279 passed**（含 `kPlNoteSubtableContract` 169 例，证明 K11 翻转没破坏 K8~K13 共享 PL 契约）。

**🔴 顺带发现一处与本 spec 无关的既有断裂（未修，登记备查）**：`composables/useK11FormulaEngine.ts`（947 字节，**git-clean，即 HEAD 就是坏的**）里 `parseNum` 只被使用、**既未定义也未导入**，导致 `useK11ImpairmentSummaryEngine` 及 `k11-unit.test.ts` 共 **53 例前端测试常红**（`parseNum is not defined`）。属 spec `k11-asset-impairment-loss` 的作业面；`parseNum` 的正确来源无法从现有代码推定（猜一个可能改错口径），故只登记不擅自修。

### Wave 8 实录 —— Task 18 第一批（2026-08-12，20/25 + 半）

**交付**：`backend/scripts/fix/fix_note_k_expandable_rows.py`（幂等，补 11 处）+ 结构脚本词表改 import 平台服务 + 两写者 `--check` 交叉守卫 + `_strip_placeholder_rows` 行为守卫 + 变异 **M89~M91 全 RED**。

**逐处实证推翻了 tasks.md 的两处描述。** ①处数不是「11 处」而是 **29 处**（Task 3 早已冻结坐标，tasks.md 正文没跟着更新）。②「逐处判定作行/作列头」的两支分支里，**作列头那支不成立** —— 29 处全部在列 A、且每一处都紧邻其数据区的 `合  计` 行之前，语义清一色是「此处可无限量增行」。

**🔴 撞上两个 spec 的正面冲突，且冲突方向是「功能消失而非报错」。**

`fix_note_k_pl_structure.py` 有一套 `PLACEHOLDER_ROW_LABELS` + `_strip_placeholder_rows()`，把 label 为 `……`/`......` 的行**一律当垃圾删掉**（前一个 spec 的诉求：那些行会渲染成一行空披露数据）。而本 spec 的 R9.2 要求把同样的行标 `row_type='expandable'` 作为「在这里加行」的落点。两者直接对立：我插 11 行，对方 `--check` 立刻报 11 条「仍为占位说明行」。

裁决依据不是「谁的 spec 新」，而是**平台自己的口径**：`_note_structure_kit.data_row()` 是 marker-aware 的（`data_row("……")` 直接产出 `row_type='expandable'`）、平台有 `note_expandable_markers` 服务作唯一词表、`note_shared_table_segments` 的既有测试明写「`……` 是段内合法可扩行，不得当无主行剔除」。⇒ **同一个 `……` 有两种语义，取决于 `row_type`**：

| `row_type` | 语义 | 处置 |
|---|---|---|
| `data` / 缺省 | 占位说明行（渲染成一行空披露数据） | 删（前一个 spec 的本意） |
| `expandable` | 可扩位行（审计师的加行落点） | **保留** |

改法：`_strip_placeholder_rows()` 与 validator 都加 `_is_expandable_row()` 例外；本地词表改成 `import LABEL_MARKERS` + 本地补充 `....`（4 点，平台词表没有但本脚本实测过）；前一个 spec 的 `test_no_leaked_or_placeholder` 同步加同一例外并写明理由。

**两条变异暴露了「只读数据的断言查不出」的形态**，值得单列：

- **M90**（把 `_strip_placeholder_rows` 改回一刀切删）初判 **GREEN**。原因：删除只发生在 `--apply` 路径，`--check` 的 validator 走另一条分支 ⇒ **当下数据一个字节都不变**，任何只读模板的断言都全绿，直到某天有人跑一次 apply，11 处加行落点无声消失。判据只能落在**函数行为**上（直接调 `_strip_placeholder_rows([expandable, junk, total])` 看谁活下来）。
- **M91**（闭环登记少一条）初判 GREEN、补了 `--check` 交叉守卫后转 RED。闭环自检写在脚本里，不真跑脚本就等于没写。

这两条合起来说明一件事：**「插入/删除」类的逻辑不能只用「产物快照」当判据** —— 产物是上一次 apply 的结果，而缺陷在下一次 apply 才显形。

### Wave 8 实录 —— Task 18 第二批（2026-08-12，17/29）

**交付**：`fix_note_k_expandable_rows.py` PLAN 扩到 **17 处**（+K1 4 +K3 2）+ 共享 kit 新增 `carry_expandable_rows()` + liability 结构脚本同款口径更正 + kit 侧 6 例新守卫 + 变异 **M89~M94 全 RED**（全量 **94/94**）。

**放弃「改 18 处行骨架」，改为在共享 kit 里搬运 —— 这是本轮最重要的设计判断。**

第一批的结论是「K1/K3/K6 的 rows 被结构脚本整表重写，必须把 `data_row("……")` 写进对方的行骨架」。真要动手时发现代价不对：要改两个脚本（46 KB + 33 KB）里 18 处骨架，而且**以后每个新写的结构脚本都得自己记得**这件事 —— 那不是收口，那是把义务摊给所有未来的作者。

改法收敛到 `_note_structure_kit.carry_expandable_rows()`：整表重写时把既有可扩位行搬到新骨架的**末尾合计行之前**。与 Task 14 的 `carry_row_codes()` 是同一个道理 —— **可扩位行是源模板事实，与结构骨架正交**；骨架说「这张表有哪些固定行」，可扩位行说「审计师可以在哪儿加行」。于是：

- `fix_note_k_expandable_rows.py` 成为可扩位行的**唯一权威**（PLAN 缺的补、多的删）
- 结构脚本不需要知道可扩位行的存在，改一处受益全局
- 六个 `--check` 同时归零

搬运的边界都配了守卫：插在合计**之前**（M93 改成 append 即打红：合计会被推到表中间）、`row_type='data'` 的占位垃圾行**不搬**（M94 去掉类型过滤即打红：垃圾行永生）、同名已存在时不重复插（否则每跑一次多一行）、以及**接线自检**（打桩确认 `apply_plan` 真经过它 —— 函数写得再对也可能是死代码）。

**同一处口径冲突在 liability 脚本上第二次出现**：`test_no_leaked_names_or_placeholder_rows` 与 `_strip_placeholder_rows` 同样一刀切删。两个脚本 + 三个测试文件（pl / liability / complex）都补上了「`expandable` 例外」并各写理由。三处的本地词表也都改成 `import LABEL_MARKERS` + 本地补充 `....`（4 点，平台词表没有）。

**为什么 K6 的 12 处必须单独做**：同一张表内有 2~4 处 `……`，label 全一样。若强行塞进当前模型，`_total_index` 只会在合计前插**一行**，4 处压成 1 处 —— 而 `--check` 因为「label 已存在」照样归零，**是个不会报错的假绿**。故拆为独立子问题（需 `after_label` 位置锚点），由 `PENDING_MULTI_MARKER_TABLES` 登记，闭环自检钉住「17 + 12 == 29」。Task 16 的缺口常量同步 `11 → 17`。

**回归**：全域 **5956 passed / 47 failed**，47 条逐个 nodeid 等于并发会话既有基线，**净增 0**；六个 `--check`（expandable / pl / liability / complex / report_row_code / shared_table_segments）全部同时归零；四个附注结构测试文件 **159 例全绿**。

### Wave 8 实录 —— Task 18 收口（2026-08-12，21/25）

**交付**：K6 的 12 处补齐（PLAN 加 `after_label` 位置锚点）+ kit 的落位分两类还原 + `--check` 改按**位置集合**核对 + kit 侧 3 例新守卫 + 变异 **M95~M97** 全 RED（全量 **97/97**）。

**最终账目：模板侧 26 行 ↔ 源侧 29 处标记，差额 3 处逐处登记。**

| 登记项 | 处数 | 原因 |
|---|---|---|
| `COLLAPSED_SOURCE_MARKERS` | 2（K6!A71 / A77） | 源 xlsx 的「持有待售的处置组」按处置组**逐个重复整块**（① 子公司A、② 分公司B），每块资产段末与负债段末各一处标记；附注模板按平台铁律把示例名收成**一个通用块** ⇒ 4 处源标记落到同 2 处模板行 |
| `NO_TEMPLATE_TARGET` | 1（K6!A54） | soe 源 xlsx 有「持有待售负债附注」表，而 `note_template_soe` §八、12 的 4 张表里没有它（listed 侧有「持有待售负债」）。缺的是**整张表**，属 Requirement 8 的表集合作业面 |

**位置锚点是必需的，而「只数个数」会假绿 —— 变异 M95 连着骗过两版判据。**

K6 一张表内有 2~4 处 `……`，label 全一样。抹掉某条的 `after_label` 后它退回「合计前」，与同表另一条的期望位置**塌成同一个**，但磁盘上的行还在原处、**数目照样对**：

1. 初版 `--check` 只数个数 ⇒ GREEN；
2. 二版改成逐条比位置，可 A37 的期望位置塌到 9、而 9 确实有一行 ⇒ 仍 GREEN；
3. 三版改成**按位置集合比**（期望 `{3,9}` vs 实际 `{3,9}`）⇒ 抹锚点后期望塌成 `{9}` ≠ 实际 `{3,9}` ⇒ RED。

**kit 的还原也要分两类落位，否则两个写者永远打架。** `carry_expandable_rows()` 初版一律「插在合计之前」，结果结构脚本一跑就把 K6 表中间那几处挤到表尾 ⇒ `fix_note_k_complex_structure --check` 报 `rows：11 → 11 项`（行数一样、只差顺序）。改成：

- 原本**贴在表尾合计之前** → 新骨架里仍放数据区末尾（哪怕骨架加了新数据行，也不该被挤到中间）
- 原本在**表中间** → 按**前一行 label** 还原相对位置

**顺带踩到一个「测试自己走了 fallback 分支」的坑**：我给锚点分支写的单测一开始是 GREEN（变异掉锚点分支仍全绿）。根因是造的数据形态不真实 —— 把可扩位行直接挨着 `（二）…`（`row_type='subtotal'`）放，而 `_tail_total_start` 从尾部回溯时把连续的 total/subtotal 都算作「表尾汇总块」⇒ 那一行被判成「贴在表尾」，走的是 fallback 而不是锚点。照 K6 真实形态（`（二）` 之后还有空白录入行再到 `合计`）重造数据后才真正测到锚点分支。**造测试数据要照真实形态，否则测的是另一条分支。**

**回归**：全域 **5959 passed / 47 failed**，47 条逐个 nodeid 等于并发会话既有基线，**净增 0**；六个 `--check` 全部同时归零；变异 **97/97 RED**，21 个守卫文件全覆盖，零漂移。Task 16 的缺口常量最终 `0 → 11 → 17 → 26`。

### Wave 8 实录 —— Task 19（2026-08-12，22/25）

**交付**：`backend/tests/services/test_note_k_aging_and_payload_closure.py`（16 例，全绿）+ 变异 **M98~M103 全 RED**（全量 **103/103**）。

**逐条实测：14 条 AC 里 12 条已满足，缺的全是守卫。** 前一个 spec 的批 1~3 已把子表名常量清干净（K7 两个常量填好、K8~K13 没有混入表头文字或英文 key）、K1 已接账龄共享真源、soe 首档字面已是 `1年以内（含1年）`、月度细分行在、K3 独立表干净。所以本轮的交付是**把这些锁死**，而不是再改一遍。

**两处对 tasks.md / AC 的更正**：

1. 「K1/K3 账龄行集都由 `disclosureAgingLabels` 驱动」—— **K3 没有账龄枚举表**。它两版的「账龄超过1年的重要其他应付款」是**逐项列示表**（行 = 债权单位，表内既无账龄行也无账龄列），正是 AC 10.5 要求保持独立的那张；K3 侧涉及账龄的只有底稿 K3-2 的「3年以上笔数/金额」，不进披露行集。故 10.1 只落在 K1。
2. 「账龄作列的表共 4 处」—— 实测 **5 处**：listed 3 张（重要的账龄超过1年的应收股利 / 前五名 / 应收政府补助情况）+ soe 2 张（前五名 / 涉及政府补助的应收款项）。守卫按 5 处登记，并配**集合完整性**反向断言（模板里凡有账龄列的 K 表都必须在登记表里）防漏登。

**两条判据刻意做成「数据驱动的豁免」而不是白名单**：

- 12.6（载荷须带 `_removed_table_keys`）：只有**多张表**的循环才有条件表、才有孤儿可清。实测 K5/K10 两版各 1 张表 ⇒ 不强制。判据按模板表数现算，并配反向自检「被豁免的循环确实只有一张表」。
- 10.6（11 个无账龄循环反向锁死）：配「扫描面 ≥20 张表」下限 + 「K1 确实有账龄行」的正向自检 —— 否则章节定位一错，「零命中」就成了空转全绿。

**12.4 走 AC 允许的第二条路**：K1 确实是唯一没有 `build*Columns` + `build*SyncPayload` 的循环（它 21/19 张表、含三阶段快照与账龄矩阵，单函数装不下），故按「显式登记 + 加守卫」收口 —— 守卫钉死其现有路径（`k1DisclosureModel.ts` + `k1DisclosureSyncPayload.ts`）真实存在且真导出载荷构造函数，改成统一范式属独立重构。

**过程中两处「解析器/变异器缺陷冒充产品缺陷」**，都是本会话反复出现的形态：

- 子表名提取器只抓字符串字面量，而 K7 两个变体常量写的是**引用**（`deferredIncome: K7_SUBTABLE.deferredIncome`）⇒ 读成空数组 ⇒ 把「已填好」误报成「12.3 违规」。补了引用解析。
- 变异 M99 初版按**下标**改列（`columns[1]`），而那不是账龄列 ⇒ 守卫照样看得见「账龄」⇒ 判 GREEN。改成按 label 定位后转 RED。**变异器定位错目标 = 变异空转**，与守卫锚点错行同源。

**回归**：全域 **5975 passed / 47 failed**，47 条逐个 nodeid 等于并发会话既有基线，**净增 0**；变异 **103/103 RED**，22 个守卫文件全覆盖，零漂移。

### Wave 9 实录 —— Task 20 + Task 21（2026-08-12，24/25）

**交付**：`test_note_k_aging_and_payload_closure.py` 扩到 **21 例**（Task 20 的列 key 裁决登记 + 12.8 例外登记）+ 新建 `composables/__tests__/kCycleNoteContract.spec.ts`（**77 例**）+ CI 的 `k-cycle-frontend` job 加一步 + 变异 **M104~M108 全 RED**。

**Task 20 的实测：同循环内 13/13 风格一致，分叉只在 K1 与其余之间。**

| 循环 | 数据列 key 风格 | 个数 |
|---|---|---|
| K1 | **中文**（`期末余额` / `逾期时间（月）`…） | 151 |
| K2~K13 | **snake_case**（`end_amount` / `current_amount`…） | 145 |

裁决 = **保持分叉**，写进 `COLUMN_KEY_STYLE_DIVERGENCE`。理由不是「懒得改」而是可证的数据风险：列 key 是 `sub_table_data[表名][行].{key}` 的**数据键**，也是 `_cell_meta`/`_cell_modes` 的索引键。改 key 后渲染器按新键取值取到 `undefined`，旧值仍在库里但**再也读不出来** —— 表现是数据凭空消失、不报错。守卫三向锁死：同循环内混用打红 / 两个集合各自变动打红 / 登记理由必须含「改 key 会丢已录入数据」。

**🔴 12.8（标签列 key 一律 `label`）实测出 3 处违规，按连库举证分头处置 —— 不一刀切。**

| 处 | key | `disclosure_notes` 落库行数 | 处置 |
|---|---|---|---|
| K4 listed `短期应付债券` | `bond_name` | **0** | **改成 `label`** |
| K4 listed `短期应付债券（续）` | `bond_name` | **0** | **改成 `label`** |
| K7 soe `其中：递延收益-政府补助情况` | `grant_item` | **2** | 登记 `LABEL_KEY_EXEMPTIONS`，不改 |

判据是**只读连库实查**（`table_data::text LIKE`）而不是「觉得风险大」。一刀切改名会让那 2 个附注的该列数据读不出来且不报错；一刀切不改则放着两处零风险的违规。K4 侧改了 3 个文件（`fix_note_k_liability_structure.py` 的 `_col()` 2 处 + `k4NoteSectionMap.ts` 的列定义 2 处与**载荷行键** 2 处 —— 行键不跟着改，列头对了值也读不出来）。例外配 stale 检测：哪天 K7 那处改成 `label` 或该表没了，守卫打红要求把登记移出，**登记不许长期失效地挂着**。

**Task 21 的分工判断：seed 侧与推送侧必须两边都判。**

后端 `aging_payload` 守卫读的是模板 JSON（seed 侧），前端这份读的是源码（推送侧）。只判 seed 会漏掉「模板列头对了、载荷推来的键名不对」⇒ 附注里那几列**永远空着**且不报错。

**🔴 `stripComments()` 当场抓出一处真判据错误 —— 这就是 Requirement 13.8 存在的理由。**

剥注释前「多表循环必须声明 `removedTableKeys`」对 K1 是绿的；剥注释后**转红**，因为 K1 的 `_removed_table_keys` 只出现在**注释里**。查明后是**登记项而不是缺陷**：K1 十张表全为无条件推送（无条件表 ⇒ 无孤儿），且其汇总表「其他应收款」与 G2/G3 共享，越权上报 `_removed_table_keys` 会打断对方推送。

于是判据从「多表」改成「**有条件表**」，并把手写清单换成「必须清 10 个 + 登记豁免 3 个（K1/K5/K10）+ 完备性断言（两者并集必须等于 13 个循环）」。K1 的豁免另配前提校验：其载荷仍是对象字面量无条件推送（`[K1_*_SUBTABLE.x]:` ≥5 处）且确实不上报 removed —— 哪天加了条件表，豁免前提失效即打红。

**title 判据必须按链路解析，只读单文件会误判。** 13 个循环的中文 title 有三种落法：

| 落法 | 循环 | 位置 |
|---|---|---|
| 字面量直写在 map 里 | K3~K7 | `title: '其他应付款说明'` |
| 元组直写在独立载荷文件 | K1 | `['listed-audit-note', '审计说明', auditNote]` |
| 调用方 `.vue` 穿透进来 | K2 | map 里只有 `title: t.title` |

初版只读 `{c}NoteSectionMap.ts` + 只抓单引号 ⇒ K2 报「找不到中文 title」（假红）。改为解析链路：map 文件 + 独立载荷/建模文件 + 按 `import` 实际解析出的共享 kit（K8~K13 走 `kPlDisclosureShared.buildPlPayload`）+ 调用 `build{C}SyncPayload` 的 `.vue`。

**空文本闸门有六种真实形态，检测器逐种认 + 逐种反向自检。** 不过滤空文本 ⇒ 用户没填的叙述段被推成空披露段落、覆盖附注既有正文。六种：辅助函数体内过滤（K1）/ 就地 `.filter(...text...trim())`（K2、PL kit）/ `if (xxx.trim())` 守赋值（K4/K5/K7）/ `if (texts.length)` / 闸门变量先被 trim（K3）/ 闸门变量来自辅助函数且函数体内过滤（K6）。两处设计细节：

- 用 `every` 而非 `some` —— 只要有一处赋值没闸门，那一处就会推空段，「别处有闸门」救不了它
- 窗口在**上一处 `_note_texts` 位置**截断 —— 否则两处相邻、只有一处有闸门时，**后一处会借用前一处的闸门**而假绿（自检 `every 语义失效` 专门拦这条）

**变异 5 条全 RED**，其中 M108 是**守卫打自己**：把 `stripComments` 改成恒等函数（= 注释即可满足判据的总开关）必须让三条剥注释自检同时打红。M107 与 M102 共用锚点但分开登记 —— 同一条变异不能横跨两个 runner（`frontend=True` 时脚本只跑 vitest），沿用 Task 17 的 M83/M88 拆法。

**回归**：`kCycleNoteContract` **77/77** + `test_note_k_aging_and_payload_closure` **21/21** + `test_k_cycle_ci_wiring` **13/13**；`fix_note_k_liability_structure --check` 归零。

### Wave 10 实录 —— Task 25 浏览器实测（2026-08-12，25/25）

**交付**：四项实测全过 + **抓到并修掉 1 处真缺陷**（`isTbSourceAbsent` 漏判 `empty_reason`）+ 共享件守卫扩到 **29 例** + 变异 **M109/M110 全 RED** + 数据逐字节复原（md5 独立只读核实）。

**实测环境**：`start-dev.bat`（后端 9980 `/api/health` 200 / 前端 3030）；两变体都有活体项目 —— listed = 重药控股安徽_2025（323 个附注章节）、soe = 重庆和平药房_2025（213）/ 宜宾临港店_2025（162）/ 陕西华氏_2025（160）。基线抓 26 行 `disclosure_notes`（全文 + md5 + `jsonb_typeof` + 子表数）。

| 项 | 结果 |
|---|---|
| ① 审定表「从四表库带入」 | ✅ K6-1 溯源面板显示 `报表行 BS-012` / `1481 | 1481` 两口径、`减值准备` 列在场；K4-1 如实显示「本项目无此科目」 |
| ② 溯源面板 | ✅ 三口径 `parent_check` 齐（`leaf_sum`/`parent`/`trial_balance`/`diff_*`）+ 备抵侧 `wide_prefix_scope: true` |
| ③ 披露表两变体渲染 | ✅ K4 listed 4 段（含「短期应付债券明细」「（续）」）、soe 4 段；**两版列头确实不同** |
| ④ 推送落库 | ✅ `sync-from-workpaper` 200，`section_id=八、48`、`rows_synced=7` |

**🔴 缺陷一：K6 的「本项目无此科目」在界面上被伪装成「余额为 0」。**

后端**已经算对了**：K6-1 的 render-config 下发 `empty_reason=EMPTY_REASON_NOT_IN_PROJECT`（连库核实该项目 `tb_balance` 里 `1481`/`1482`/`2245` **零命中**）。但界面照常展示「1481 | 1481」+ 一片 `0.00`，一个字都没提「无此科目」。

根因在平台共享判据 `isTbSourceAbsent()`：它按「四个码列表全空 + 后端算过」判定，而 K6 的 `gross=['1481']` **非空** —— resolver 在 `account_mapping` 无反解记录时会把**标准码本身**当原始码返回（Task 8 实录已记这个现象，当时只修了后端判据，没意识到前端判据是另一套）。**前端只看码列表在结构上无法得出正确结论，必须听后端的 `empty_reason`。**

修法：`empty_reason` 非空 ⇒ 直接 absent，且**优先于**码列表推断；面板另把后端原因**原文**显示出来（两层原因的下一步动作不同：`NO_ACCOUNT` 手工填是常态，`NOT_IN_PROJECT` 要先确认业务上是否真没有）。影响面实扫：只有 K4（`NO_ACCOUNT`）与 K6（`NOT_IN_PROJECT`）产出非 null 的 `empty_reason`，K3/K5/K7/PL 都显式写 None，而 K4 本就因码全空判 absent ⇒ **实际只改变 K6 的显示**，正是缺陷所在。

修后浏览器复验，面板显示：`报表行 BS-012` → `本项目无此科目` → 「本项目科目表中没有持有待售资产和负债对应科目 —— 未取数（不是余额为 0）」→ **后端原因原文** → `报表公式：TB('1481','期末余额')`。

**为什么四层守卫都没抓到它**：后端守卫断言「`empty_reason` 该非空时非空」→ 绿；前端 vitest 断言「`isTbSourceAbsent` 对码全空的形态判 true」→ 绿。两侧各自都对，缺的是**两侧判据口径不一致**，而没有任何测试同时拿真实载荷跑两侧。这是 memory 里「Vue 传不存在的 prop / 判据漂移只有浏览器挂载才暴露」那条的又一例。守卫已按 K6 真实载荷逐字补齐（含「空串不得被当成有原因」的反向自检 —— 空串是任何字符串的子串，是这类判据最常见的假绿）。

**🔴 发现二：`disclosure_notes` 全库 `expandable` 行 = 0（登记，不在本 spec 作业面）。**

模板侧 `note_template_*.json` 有 **147** 个 `row_type='expandable'`（listed 92 / soe 55，含本 spec Task 18 补的 26 个）；而 `disclosure_notes` **1031 个 note / 293 个带 `_tables` / 4557 行**里，`row_type` 取值只有 `data`/`header_label`/`subtotal`/`total`/`unowned` **五种**，`expandable` **一个都没有**。

判定：**不是本 spec 引入** —— 非 K 的既有 121 个标记也一样没进库，说明既有项目的 note 是在 `expandable` 引入**之前** seed 的，模板改动不回溯改写项目数据。消费方（`note_sub_table_projector` / `note_word_exporter`）读的是运行时 `table_data`，故对**既有 8 个项目**，Task 18 的加行落点目前不可见；新 seed 的章节不受影响。

**建议（需用户裁决，因为会改用户数据）**：写一个幂等回填脚本，按 `note_template_*.json` 把 `expandable` 行补进既有 `disclosure_notes._tables`（按 label + 位置锚点还原，复用 `_note_structure_kit.carry_expandable_rows()` 的两类落位口径），配 `--check` 与 round-trip。影响 293 个 note，属独立 spec。

**🔴 发现三：同步按钮的失败与成功都无可见提示（登记，未修）。**

- listed tab 的自动同步返回 **409 `STANDARD_MISMATCH`**：「项目适用准则为 soe_standalone，不能以 listed_standalone 同步披露数据」+ `allowed: [soe_standalone, soe, standalone]`。**后端话术完全可操作**（Task 15 的成果），但界面上只显示「尚未同步到附注」，409 的原因**一个字都没露出来**。
- 成功那次（soe tab，200 + `rows_synced=7`）**也没有** toast。

两者都属 `WpNoteSyncBanner` / 披露组件的提示缺口，不在本 spec 的 AC 内（Task 15 的 AC 是 `_row_scope` fail-closed 的三种成因，`STANDARD_MISMATCH` 是另一条路径），故只登记。**建议**：`sync-from-workpaper` 的非 2xx 一律经 `rowScopeFailureMessage()` 同族的共享文案函数弹出 —— 后端已经把话说清楚了，前端丢掉它等于白做。

**落库结构逐项核对（Requirement 14.6）**：

```
sub_table_data: { "其他流动负债": [ {label:"预提费用", end_amount:12345.67, prior_amount:0}, …, {label:"合计", is_total:true, end_amount:12345.67} ] }
_sub_table_columns: { "其他流动负债": [ {key:"label", label:"项目", is_label:true, flat:true},
                                        {key:"end_amount", label:"期末余额", format:"amount"},
                                        {key:"prior_amount", label:"期初余额", format:"amount"} ] }
_source: workpaper · _current_standard: soe_standalone · _last_sync_sheet: 附注披露信息（国企）
```

- 标签列 key = **`label`** ✓（12.8）；数据列 snake_case ✓（Task 20 登记的 K2~K13 风格）
- 列 label 是 soe 用语「期末余额/期初余额」，与 listed 的「期末数/上年年末数」**确实不同** ✓（Task 17 的 8.2）
- 单级表标 `flat: true` ✓（8.4）；合计行 `is_total` 且自动求和正确 ✓
- 我填的 `12,345.67` 界面千分符 ✓、落库 `12345.67` ✓
- `_tables` 为 0 属既有机制（`_source=workpaper` 下投影器只渲染推来的表、不与模板合并）

**数据复原（Requirement 14.7）**：仅 1 行被改（`八、48` md5 `d4ff36df → 72f67d31`）。按基线全文回写 `table_data` + `last_sync_at`/`last_sync_source`/`last_sync_wp_id` 三列 ⇒ md5 回到 `d4ff36df0c1d83926ac9edb5d458667f`，**独立只读 SQL 二次核实一致**（不拿写入脚本自证）。`working_paper` 两行 `updated_at` 全程未变（界面填值未落底稿，只经同步进了附注）。

**变异**：M109（撤 `empty_reason` 判定）+ M110（改成 `in` 存在性判定 ⇒ 空串也算「有原因」）**双双 RED**，守卫文件数 22 → **24**。

**全量收口**：变异 **110/110 全 RED**（0 GREEN / 0 ANCHOR-MISS / 0 WRONG-TEST）；后端守卫 7 文件 **177 passed**、前端 6 文件 **216 passed**；八个幂等 `--check`（prefill / disclosure / report_row_code / pl / liability / complex / expandable / shared_table_segments）**同时归零**；`--restore` 报「还原 0 个文件」。

**🔴 本轮最贵的一课：被 stop 的终端 ≠ 被杀的进程，两个变异脚本并行会互相把文件踩成变异态。**

过程：为省时间把全量变异放后台跑，中途因编辑守卫文件而 `stop` 了终端，随后又起了一次。**`stop` 只关掉了 shell，`cmd /c python` 的子进程仍在跑**（`Get-CimInstance Win32_Process` 实测到 PID 116768 存活了 20 分钟）。于是两个变异脚本对同一批文件交替「备份 → 改 → 还原」，后果连锁：

| 现象 | 真因 |
|---|---|
| M01 判 GREEN | 取基线时文件已被对方改成变异态 ⇒ 差集恒空 |
| 13 条 ANCHOR-MISS | 对方正把锚点改掉，我这边读到中间态 |
| 6 条 WRONG-TEST | 对方的变异让别的测试先红 |
| `restored_clean: false` | 双方的 `.bak` 互相覆盖，谁都还原不回去 |

**代价**：9 个文件停在变异态（K8 死块复活、K1 披露块 sheet 名全角化、K7 登记表 sheet 名脱钩、K4 塞进账龄行、K11 组件二次翻符号、`provision_name_filter` 被撤、CI 少一步 `--check`、段首码搬运改按下标、结构 kit 一刀切删占位行），守卫从全绿掉到 **21 failed**。

**恢复用的是既有资产，不是手工改**（memory 那条「幂等脚本 `--check` + 契约测试是唯一可靠恢复手段」正是为此）：① 写反向还原脚本枚举 `MUTATIONS`，凡「`repl` 命中且 `anchor` 缺失」即判未还原 ⇒ 自动修回 4 处纯文本变异；② 数据文件跑 7 个幂等脚本 `--apply` ⇒ 21 failed 降到 5 failed；③ 剩 4 处 JSON 补丁 + 1 处 `.vue` 按失败消息精确定位后单独修。最终 177 + 216 全绿、八个 `--check` 归零。

**过程中差点造成二次破坏，值得单列**：修 M101（给 K4 塞账龄行）时第一版按 `label == '1至2年'` 全库匹配 —— dry-run 报「命中 13 处」，而 `1至2年` 是**真实账龄档**（应收账款按账龄披露 / 预付款项 / 应付账款 / 十二、母公司各表都合法拥有），只有 §八、48「其他流动负债」那一处是变异塞的。**幸好先跑了 dry-run。** 教训：删除类修复必须**双重定位**（章节号 + 表名），只按 label 全局匹配等于拿正确数据当垃圾清。

**规程更正（已写进 `#conventions`）**：
1. 后台跑变异/长任务后，判「是否结束」看 `Get-CimInstance Win32_Process | Where CommandLine -like '*脚本名*'`，**不看终端状态**；`stop` 之后必须复查并 `Stop-Process` 兜底。
2. **同一时刻只允许一个变异脚本在跑**，起之前先扫进程（含并发会话的 `mutate_*.py`）。本轮另一个真实干扰源是并发会话的 `mutate_guard_attribution.py --all`。
3. 变异被中断后，判「有没有留下变异态」不能只看 `--restore` 报「还原 0 个文件」（`.bak` 可能已被对方清掉）—— 要跑**守卫**，红了再用「反向还原脚本 + 幂等 `--apply`」两级恢复。
4. 变异脚本的 stdout 才是本次判定的权威；`_k_cycle_mutation_report.json` 可能是**上一次**（被污染那次）的残留，看它前先核 mtime。

### 与并发 spec 的边界

| spec | 交集 | 处置 |
|---|---|---|
| `e-cycle-…`（17/24 在跑） | `prefill_formula_mapping.json` | 只改 K 前缀块，改前查 mtime；不并行编辑该文件 |
| `g7-column-alignment-…`（4/24） | `note_template_*.json` 列元数据 | 只改 K 章节；`--check` 归零判据独立 |
| `i-cycle-…`（0/24，刚建） | `k_cycle_specs` 无交集；`test_cycle_specs_row_code_evidence` 有 | 该守卫的 `_all_specs()` 两侧都要加，协调后再改 |
| `h-cycle-…`（Task 18 `[-]` 驻留） | 无 | 不碰 |
| `procedure-trimming-…`（12/26） | 无 | 不碰 |

### 六条已知不做

1. **列 key 中英文统一** —— 改 key 丢已录入数据（`_cell_meta` 按 key 索引），只登记
2. **K0 纳入科目定位** —— 函证循环无科目余额，显式豁免
3. **`report_config` 数据修正** —— 本 spec 只改声明侧对齐它；若发现 `report_config` 自身错码另立（归 `report-config-account-code-integrity` 半径）
4. **源模板 11 处 `#REF!` 修复** —— 源模板缺陷，只登记 + 数据靠底稿录入
5. **附注 `五、8` 表数 21 vs 源模板 10 的差异对齐** —— 附注侧多出的 11 张是「应收利息/应收股利」两科目的表，属正确设计（该章节承载三科目）
6. **K8 附注主表仅 1 行 `total`** —— 源模板明细在「个别报表」段，附注按费用性质列示，需业务裁决行集，本轮只登记

### 真实库现状（Wave 1 前实测，供判据参考）

- `account_chart` client 侧项目数 8、standard 侧 10（分母不同，覆盖率要按 source 各算）
- K6 的 `1481`/`1482`/`2245` 仅 **1 个** client 项目有 ⇒ 多数项目仍会走「本项目无此科目」降级
- `2231 应付利息` standard 9 / client 6 项目 ⇒ K3 的 `extra_standard_codes` 在多数项目可命中
- 附注侧 K 类 26 章节 `columns` 全齐、`guidance` 全有、`report_row_code` **全 None**
- 附注侧 K 类章节 `expandable` 行数 **0**（平台 121 行分布在 listed 28 / soe 12 个非 K 章节）

### 待用户裁决（不阻塞 Wave 1~4）

1. **K8/K9 附注「个别报表 / 合并报表」两段** —— 源模板两段同构，附注模板只有 1 张表。是按 `report_scope` 二选一推送，还是拆两张表？倾向按 scope 二选一（与 `note_applies_to_report_scope` 既有机制一致）
2. **K6 三科目仅 1 个项目有** —— 是否值得把 `has_account` 改 True 后再补 `IMP-007` 备抵行；倾向改（结构正确性优先，运行时降级已覆盖无科目场景）
