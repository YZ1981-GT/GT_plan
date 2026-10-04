# `wp_account_mapping.json` 科目映射勘误登记（2026-09-28）

> 来源 spec：`.kiro/specs/voucher-sampling-account-scope-and-attach-closure/`（Requirement 5，任务 6.1）
> 状态：**已修复（2026-09-28 同日处置完成）**。登记规模 4 族，处置时触类旁通扩为 **5 族 37 项**。
> 修复脚本：`backend/scripts/fix/fix_wp_account_mapping_wrong_codes.py`（`--check` / `--dry-run` / `--apply`，幂等）
> 处置记录见文末「处置记录」节。

## 结论摘要

抽凭科目真源接线过程中，把三方（底稿真实名 / 前端科目真源 / `wp_account_mapping.json`）逐条对账，
登记时发现该 json 有 **4 处科目映射错误**。四处均已在运行态被前端真源覆盖，**当时不影响底稿行为**，
但它是平台级参考数据，留错会让后人「照 json 修正」把已经正确的组件改坏
（本 spec 实施中即为此在 K10/K12/H5 的接线注释里写了防误伤说明）。

🔴 **处置阶段按「触类旁通 grep」扩面后，真实规模是 5 族 37 项**：登记的 4 族只是**主条目**，
每族还有 `{code}-1`…`{code}-n` 同族子条目沿用同一错码；且 grep 全表时发现**第 5 族 H3**
（登记时未发现，与 G4 撞同一个错码 `1501`）。明细见下表。

## 勘误明细（处置后口径：5 族 37 项）

| wp 族 | 条数 | 底稿真实名（`wp_index`） | json 原值 | 原值在 `account_chart` 中实为 | 改后值 | 改后值实为 |
|---|---|---|---|---|---|---|
| **G4**, `G4-1`~`G4-8` | 9 | 债权投资 | `1501` | 持有至到期投资（7 条） | `1504` | **债权投资**（6 条） ✓ |
| **H3**, `H3-1`~`H3-6` | 7 | 投资性房地产 | `1501` | 持有至到期投资 | `1521` | **投资性房地产**（16 条） ✓ |
| **H5**, `H5-1`~`H5-4` | 5 | 油气资产 | `1606` | 固定资产清理 | `1631` | **油气资产** ✓ |
| **K10**, `K10-1`~`K10-4` | 5 | 其他收益 | `6301` | 营业外收入（= K12 的） | `6117` | **其他收益**（19 条） ✓ |
| **K12**, `K12-1`~`K12-4` | 5 | 营业外收入 | `6001` | 主营业务收入（= D4 的） | `6301` | **营业外收入**（19 条） ✓ |
| 小计 `account_codes` | **31** | | | | | |
| `report_row` 连带修正 | **6** | 见下节 | | | | |
| **合计** | **37** | | | | | |

### `report_row` 连带修正 6 项

`account_codes` 改了但 `report_row` 仍指向旧科目对应的报表行，属同一处错误的第二面：

| wp | `report_row` 原值 | 原值实为 | 改后值 | 依据 |
|---|---|---|---|---|
| **G4** | `BS-030` | 生产性生物资产 | `BS-021` | `report_config`：`BS-021 债权投资 = TB('1504','期末余额')` |
| **H3** | `BS-026` | 其他非流动金融资产 | `BS-027` | `report_config`：`BS-027 投资性房地产` |
| **H3-1** | `BS-026` | 同上 | `BS-027` | 同上 |
| **H5** | `BS-031` | 使用权资产 | `None` | 🔴 `report_config` **无**资产负债表「油气资产」行，与前端 `H5_ACCOUNT_DEF.reportRowCode = null` 一致 ⇒ **宁缺勿造**，不编码 |
| **K10** | `None` | — | `IS-010` | `report_config`：`IS-010 其他收益` |
| **K12** | `None` | — | `IS-020` | `report_config`：`IS-020 营业外收入` |

> G4 一条是字面量清理批次追加发现的：接线前用探针把「真源兜底值」与「组件现值」逐个比对时暴露
> （`gCycleScope('G4').queryCodes()` = `1504` 而组件写 `1501`），`report_config` 的
> `BS-021 债权投资 = TB('1504','期末余额')` 佐证。若直接按「值正确」机械接线就会漏掉。
>
> 🔴 H3 族（第 5 族）的发现路径**不是** grep 错码，而是**产物 diff 的不对称**：改完 4 族主条目后重新
> 生成 `note_template_bindings.json`，diff **只有新增、没有删除** ⇒ 说明旧码 `1501` 仍被别处引用
> ⇒ 顺着旧码回查，才挖出 G4 的 8 个子条目与整个 H3 族。**「只增不删」是错码残留的可靠信号。**

判据来源（三者一致指向前端真源）：

1. `wp_index.wp_name` —— 底稿自身的名称；
2. `account_chart` —— 科目**定义**表（🔴 权威源，见下方方法论提醒）；
3. 前端 `composables/*AccountScope.ts` 的文件头实证记录（含 `report_config` 公式引用）。

## 为什么登记时不在本 spec 内修（历史裁决，已由后续批次执行）

`wp_account_mapping.json`（现算 **1025** 条映射，版本 `2025-R5`）被多处消费，改动需逐消费方回归：

| 消费方 | 用途 |
|---|---|
| `scripts/generate_note_template_bindings.py` | 附注模板 binding 生成（按 `note_section` 聚合 `account_codes`） |
| `app/services/address_registry.py` | 地址库 V1 的 **wp 域**条目构建（公式选址/校验/跳转） |
| `note_formula_generator._load_cross_table_data` | 附注账龄分桶的 `account_code → account_name` 反查 |
| `scripts/validate_seed_files.py` | 种子文件 schema 校验（`WpAccountMappingSeed`） |
| `app/routers/row_name_alignment_router._resolve_account_prefixes` | 行名对齐的科目前缀解析 |

⇒ 改 3 个值本身是小事，但要保证上述五类消费方不回归，属独立工作量。本 spec 范围是抽凭链路，
故按 Requirement 5.2 明确排除，并按 5.4 规定「前端真源与 json 冲突时以前端真源为准」。

## 方法论提醒（供后续处置该勘误时遵循）

🔴 **查「某科目码是什么科目」必须用 `account_chart`（定义表），不能用 `tb_balance` / `tb_ledger`
的 `MIN/MAX(account_name)` 聚合。** 后者是各项目账套的**实际用法**，同一码在不同项目可挂不同名称，
聚合函数会随机取到其中一个。

本 spec 实施中我自己踩过这个坑：用 `tb_balance` 的 `MIN(account_name)` 得出「`6604` = 勘探费用」，
据此怀疑 `i6AccountScope` 的真源值有错；改查 `account_chart` 后发现 `6604` 共 7 条里
**6 条是「研发费用」**、仅 1 条被某项目用作「勘探费用」，与 I6 底稿名「研发费用」一致
⇒ 真源正确，是我的判据用错了数据源。详见该 spec `design.md` 的「实证更正节 · 更正 5」。

## 关联修复（本 spec 已完成，不依赖本勘误的处置）

| 底稿 | 原硬编码 | 该码实为 | 改后 |
|---|---|---|---|
| K5（6 处） | `2701` | 长期应付款（L5 循环） | `k5AccountScope` → `2801` 预计负债 |
| G1（2 处） | `1501` | 持有至到期投资（G4） | `g1AccountScope` → `1101` / 衍生品用 `1102` |
| I2（9 处） | `1717` | 全库零命中 | `i2AccountScope` → `1704` 开发支出 |
| I6（5 处） | `6602` | 管理费用（K9） | `i6AccountScope` → `6604` 研发费用 |
| I5 / K4 / F2合同履约成本 | `1911` / `2245` / `1410` | 零命中 / 持有待售负债 / 零命中 | 走 `useSamplingAccountGate` 降级禁用 |

---

## 处置记录（2026-09-28 同日完成）

### 修复方式

正式脚本 `backend/scripts/fix/fix_wp_account_mapping_wrong_codes.py`（非一次性，保留供复验）：

```powershell
.venv\Scripts\python.exe backend\scripts\fix\fix_wp_account_mapping_wrong_codes.py --check     # 只报告
.venv\Scripts\python.exe backend\scripts\fix\fix_wp_account_mapping_wrong_codes.py --dry-run   # 预演
.venv\Scripts\python.exe backend\scripts\fix\fix_wp_account_mapping_wrong_codes.py --apply     # 落盘
```

三条设计约束：

1. **幂等** —— 已是新值则 `[skip]`，可反复跑；
2. **拒绝盲目覆盖** —— 若现值既不是期望原值也不是期望新值，报 `[BAD]` 并以退出码 2 中止，不猜；
3. **只改码不改名** —— 5 族的 `wp_name` / `account_name` 本就正确，脚本内以 `assert` 保护，
   避免「改错码时顺手把对的名字也改了」。

### 改动规模

`git diff --stat backend/data/wp_account_mapping.json` = **37 insertions / 37 deletions**，
无格式漂移（缩进、键序、尾随换行均未变）。

### 验证证据

| 项 | 结果 |
|---|---|
| 种子 schema 校验 `scripts/validate_seed_files.py` | `PASS wp_account_mapping.json` |
| 脚本幂等复验 `--check` | `[OK] 4 条错误均已修正（37 项幂等）` |
| 后端回归（G4/H3/H5/K10/K12 五族 + 通用消费方，21 个测试文件 924 test） | **零回归**：修复前后 failed 集合**逐 ID 完全相同**（277 预存失败 / 647 passed，新增 0、修好 0） |
| 前端回归（抽凭科目真源 4 个 spec） | **65 passed**（4 文件全绿） |

🔴 **零回归的判定方法**：本仓库工作树存在大量前序未完工作导致的预存失败（277 个），
直接看「有没有 failed」会被噪声淹没。改用**差集法**：同一组测试跑两遍
（`git show HEAD:...` 取基线 json vs 当前修复版），比较 failed **测试 ID 集合**的差集，
只有「修复版新增的 failed」才算本次引入。探针用完即删。

### 下游产物影响（隔离实验实测）

`backend/data/note_template_bindings.json` 由 `scripts/generate_note_template_bindings.py`
从本 json 派生。直接重新生成会得到 **3662 insertions / 7672 deletions** 的巨大 diff ——
但这**绝大部分是产物本身陈旧**（上游 json 早已多轮变更而产物未重新生成），与本次 37 项无关。

⇒ 改为**隔离实验**测真实影响：把基线 json 与修复版 json 各自生成一份产物再互相 diff，
得本次改动的真实影响面 **54 行（新增 32 / 删除 22）**：

| 方向 | 科目码 × 出现次数 |
|---|---|
| 新增 | `1504` × 10、`1521` × 10、`1631` × 8、`6301` × 4 |
| 删除 | `1501` × 10、`1606` × 8、`6001` × 4 |

全部为预期修正，无意外波及。

🔴 **产物未随本次提交**：`note_template_bindings.json` 与 `scripts/note_template_bindings_report.txt`
已 `git checkout --` 复原到基线。理由是重新生成会把「产物陈旧」这笔无关的历史欠账混进本次 diff，
无法区分哪些变更来自本次修复。**产物重新生成应另起一次独立提交**（届时 diff 全部是陈旧欠账，
一目了然）。在此之前：**运行态读的仍是旧产物，需重新生成 + 重启后端才生效。**

### 未连带修改的部分（已核实无需改）

| 对象 | 核实结论 |
|---|---|
| `note_template_listed.json` / `note_template_soe.json` | 对这 5 族 label **零污染**，无需连带改 |
| `WpAccountMappingEntry.report_row` schema | 类型是 `str \| None`，**无格式校验**（不拦 `BS-xxx` 形态错误）⇒ schema 校验通过不代表值对，这也是本次错误能长期存活的原因之一 |
| `backfill_note_seed_account_codes.py` | 会把本 json 的 `account_codes` / `report_row` 回填到 note_template，**下次跑它时会把本次修正带过去**，无需现在动 |

### 遗留

- `note_template_bindings.json` 产物重新生成（独立提交）；
- `test_note_report_row_code_alignment.py` 有 **6 个预存失败**（`note_template_{listed,soe}.json`
  残留 95 / 23 处陈旧 `report_row_code`），已确认与本次改动无关（基线同样红），属另一笔欠账，
  修复入口是 `backend/scripts/fix/remap_note_report_row_codes.py --apply`。
