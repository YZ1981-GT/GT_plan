# Task 47 —— 逐一迁移 E 循环 Excel 独立 entry

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` · Wave 5
Requirements: 6.5, 12.1, 12.4, 12.10, 12.11, 12.12, 14.1
Properties: 23 / 69 / 70

## 一句话结论

E 循环在冻结 manifest 里只有 **1 个**独立 Excel entry（`xlsx/gt-e1-monetary-fund`），
诚实裁决 **`single_onlyoffice`**，evidence 保持 **UNVERIFIABLE**；本任务**没有**为它
伪造 per-entry contract，也**没有** finalize 任何 candidate 或 published representation。

## 裁决

| entry | 裁决 | 理由摘要 |
|---|---|---|
| `xlsx/gt-e1-monetary-fund` | `single_onlyoffice` | 无 bidirectional adapter / 无 per-entry contract / 无 authority model / 无 non-null definition bundle / 无 Task 17 instrumentation candidate / 无 durable forcesave+ack。HTML 侧走 `checklist_responses`，OO 侧只按 sheet_name 打开模板副本 |

不是 `single_html` 的依据：OO 挂载真实可达（宿主两处 `GtOnlyOfficeSheet` 由 `dualMode`
门控，后端 `/api/workpapers/{wp}/sheets/{sheet}/onlyoffice-config` 存在，doc_key 为 wp
维度服务端 key，`scenario_profile.doc_key_defects` 为空），不属 12.9 的「空白模板切换入口」。

E0 函证（`E0 货币资金 - 函证.xlsx` + `confirmation/e0-send-list/*`）是跨循环共享模块、
纯 HTML 无 OO 挂载点，不在 186 条 source manifest entry 内 ⇒ 显式排除、归 Task 57。

## finalize / UNVERIFIABLE

- finalize 出 published representation 的 entry：**0**
- 保持 UNVERIFIABLE 的 entry：**1**，原因逐条登记在 slice 的
  `evidence.unverifiable_reasons`（无 instrumentation candidate / 无 approved contract /
  无 non-null approved bundle / 无真实 OO 9.4 探针 / 无 published representation）。

## 权威模板

只读 `backend/wp_templates/E/`（运行时权威）。工作树根下 **`基础数据/` 目录不存在** ⇒
参考副本无法做两处 size 比对，这一事实如实登记在
`authoritative_templates.reference_copy_status = absent_from_working_tree`，并由守卫与
磁盘现状双向核对。枚举跳过 `~$` 锁文件。五个 xlsx 的 size + sha256 全部冻结进 slice，
守卫用 `hashlib` 现算比对（模板漂移 fail closed）。

## 「防 variant 切换抹零」的落地

两条独立判据，缺一不可：

1. **源侧**（本任务新增）：两个 E1-3 variant 的 identity 列在权威模板里逐字相同
   （`A..D`，账号在 `C` 列），只有金额列集不同（`max_column` 28 vs 41；「原币币种/
   期末汇率/原币」三个 label 只在 multi 版出现）。守卫用 `openpyxl` 真读比对 ⇒
   「stable field key 与 variant 解耦」是派生事实，不是声明。
2. **行为侧**（本任务新增 `e1SyncEntryRowIdentity.spec.ts`，27 例）：真挂载
   `useE1BankDetail`，把「种子的 variant」与「消费它的 Tab 的 variant」四种组合串起来
   断言行 id 逐项保留；`rmb` 种子被 `multi` Tab 消费时身份与金额同时保住。

抹零缺陷本体（`recalcRow` 在 multi 下无条件由「原币 × fxRate」派生）**已被修复**：
`useE1BankDetail.classifyFxForm` 先按 `fxCurrency` 判 `base-identity` /
`foreign-pending` / `fc-authoritative` 三态，`base-identity` 保留本位币输入值。既有
`e1BankVariantIntegrity.spec.ts`（29 例，写入 variant × 消费 variant 全组合的金额守恒）
已锁住金额侧；本任务补的是**身份侧**（Property 23 的原文判据），两者互相独立可红。

## 已登记未修的阻断项

`BP-4`：E1 的 OO sheet 名解析复用 G1 专属解析器（`useG1DualMode.resolveOoSheetName`
在 `currentSheet` 为空时返回 `sheetName || 'G1-1'`；`resolveG1SheetLabel` 的
`availableSheets` 被宿主传成 `computed(() => [])`；`extractG1SheetCode` 把含「调整分录」
的 sheet 名归一成 `G1-3`）。状态 `REGISTERED_NOT_FIXED`，`must_fix_before` = 标
bidirectional 或注册 adapter 之前。行为侧对侧是 `e1SyncEntryRowIdentity.spec.ts` 末节的
characterization（**断言的是缺陷实况**）—— 缺陷一变本节即红，逼登记表跟着更新。

## 删除

| 文件 | 动作 | 依据 |
|---|---|---|
| `composables/useE1DualMode.ts` + 其 spec | **已删** | 生产入边 0（宿主 import 的是 `useG1DualMode`），`auto-imports.d.ts` 未收录，模式词汇 `structured\|online-edit` 与平台在用的 `html\|onlyoffice` 是两套值 |
| `composables/useG1DualMode.ts` | **延后** | 与 G1 共享（两处生产宿主）；本 entry 真实 OO 场景未执行；承载 BP-4 |

## 测试与变异

| 项 | 命令 | 结果 |
|---|---|---|
| 后端守卫 | `python -m pytest backend/tests/workpaper_sync/test_task47_e_cycle_migration.py -q` | 53 passed |
| 后端辐射面 | 见 `radiation.json`（按引用关系反查得 2 个文件） | 84 passed |
| 前端辐射面 | 见 `radiation.json`（9 个 spec） | 196 passed |
| 变异 be | `--run be` | **21/21 RED** |
| 变异 fe | `--run fe` | **9/9 RED** |

30 条变异**全 RED**，0 GREEN / 0 ANCHOR-MISS / 0 WRONG-TEST，全部 `restored=True`。
锚点自检 30/30 命中唯一。原始报告见 `mutation_report_be.json` / `mutation_report_fe.json`。

变异覆盖两侧：`be` 打登记表（slice/deletion plan）与被登记的真实源码符号，验证「登记 ↔
源码/模板」双向锁；`fe` 打真实 composable 的行身份实现，验证 Property 23 的行为侧判据
真的在跑 composable。只做单侧会分别漏掉「登记漂亮但实现用下标」与「实现对但登记指向空气」。

## 并发边界

- 未读、未改、未暂存 `backend/data/amount_input_migration_status.json`。
- 未改 `workpaper_sync_entry_overlay.json` / `adapters/registry.py` / `excel_entry_gate.py`
  —— 裁决为 single 不注册 adapter，这三个共享文件本次零改动。
- 变异运行前，仓库里有并发会话遗留的
  `backend/scripts/check/check_task44_oo94_excel_pilot_gate.py.mutbak`（比其 live 文件旧
  22 分钟、内容差一行且那一行是真实代码改进，判为已废弃残留）。**没有**用 `--restore`
  （那会用陈旧备份覆盖并发会话的改动），而是临时移出仓库、跑完原样移回，sha256 逐字一致；
  对应 live 文件全程未被本任务触碰。
