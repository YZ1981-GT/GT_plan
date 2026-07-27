# D2 关注点

## 1. 账龄口径曾出现"读写不同源"静默返 0

`sumAgingBands` 早期只读迁移前的扁平字段（`auditedAging1Year`…），而明细表已改存 nested `agingAudited.{segKey}` → 审定表账龄组合表与分析表对新数据一律 0；且旧结构无 `over3` 键，3 年段项目"3年以上"恒 0。现已统一为 `agingCellValue` / `sumAgingBySegments`（nested 优先 + legacy 回退 + `over3` 合成）。

**教训**：判断某循环账龄是否已统一看三处——明细是否 nested + `useAgingConfig`、crossSheet 是否 `aggregateAgingByKeys`、审定表是否 `segments.map` 生成行。

## 2. 曾有三套并存的账龄段清单

D2-1 审定表自建 `AgingMode`、D2-5 分析表本地 `AGING_PRESET_3Y/5Y`、明细表 `useAgingConfig` —— key 与 label 双分歧（`within1Year` vs `within1`、「一年以内」vs 段 label），跨表聚合恒 0。已删除前两套，统一注入项目口径。

## 3. 披露键改版后旧数据不自动迁移

新键前缀 `D2-disc-{variant}-`，旧 `D2-disclosure-*` 不做批量迁移脚本，改为**检测旧数据 → 一键带入可映射区块**（前五名、账龄段期末值），自由文本行不迁移并提示人工核对。已录旧披露的项目首次打开会看到空表 + 带入提示。

## 4. 导入导出的范围边界

D2 披露导入导出只覆盖**手工录入明细表 + 7 段说明文本**；账龄表 / 分类表 / 坏账变动是取数派生 + 手工覆盖，明确不在范围（写进编制说明）。导入采用 **no-wipe** 语义：工作表存在但无有效行不清空既有数据，只 warning。

## 5. 保理终止确认是"逐份合同"而非单份

判断数据存 `{byContract:{[rowId]:{steps,conclusion}}}`，旧单份格式经 `__legacy__` 键兼容并归入首份合同。改这块要注意 legacy 迁移会 persist（避免孤儿）。
