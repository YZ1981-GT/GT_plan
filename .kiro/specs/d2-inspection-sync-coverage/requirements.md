# D2 检查底稿双向回写覆盖 — Requirements

## 背景

D2 应收账款底稿分布在 3 本 Excel 工作簿中：

| 工作簿 | wp_code | 包含 sheet | 当前双向状态 |
|---|---|---|---|
| D2-1至D2-4 审定表明细表 | D2 | D2-1/D2-2/D2-3/D2-4 | **D2-1/D2-2/D2-3 已全通** |
| D2-5 分析程序 | 待确认 | D2-5 | 未覆盖 |
| D2-6至D2-13 检查 | 待确认 | D2-6~D2-13 (8张) | 未覆盖 |

本 spec 目标：让 D2-5 分析表 + D2-6~D2-13 检查底稿走真双向回写。

## 勘测结果（2026-10-12 实测）

### Excel sheet 结构

| Sheet | 行×列 | 公式数 | 公式列 | 合计行 | 形态 |
|---|---|---|---|---|---|
| D2-5 分析表 | 54×9 | 63 | A~H | R48 | 多区公式表 |
| D2-6 关联方 | 31×14 | 17 | C/D/E/F/G/H/L | R16 | 动态行表 |
| D2-7 检查表 | 52×17 | 20 | A/E/F/G/H/J/Q | R43 | 凭证级检查 |
| D2-8 坏账政策 | 46×22 | 6 | A/C/F | 无 | 文字描述+少量公式 |
| D2-9 坏账测算 | 50×14 | 57 | A~F | R39 | 多区公式表 |
| D2-10 ECL | 110×10 | 198 | A~H | R60 | 最复杂 |
| D2-11 核销 | 29×8 | 10 | A/C/E/F/H | R22 | 动态行表 |
| D2-12 质押 | 43×12 | 13 | A~E/G | R19 | 动态行表 |
| D2-13 业务模式 | 30×5 | 12 | A~D | 无 | 文字+公式 |

### 前端子组件

| Sheet | 子组件 | 读 allResponses | 写 save | store item_id |
|---|---|---|---|---|
| D2-5 | D2TabAnalysis | ✅ | ✅ | 待确认 |
| D2-6 | D2TabRelatedParty | ✅ | ❌ | 待确认 |
| D2-7 | D2TabVoucherCheck | ✅ | ❌ | D2-7-001/002/1 |
| D2-8 | D2TabPolicyCheck | ✅ | ❌ | 待确认 |
| D2-9 | D2TabEcl（?） | ✅ | ❌ | 待确认 |
| D2-10 | D2TabEcl（?） | ✅ | ❌ | 待确认 |
| D2-11 | D2TabWriteoffCheck | ✅ | ❌ | 待确认 |
| D2-12 | D2TabPledgeCheck | ✅ | ❌ | 待确认 |
| D2-13 | D2TabBizModel | ✅ | ❌ | 待确认 |

### 真库数据

和平药房项目的 `checklist_responses` 中 D2-6~D2-13 相关 item_id **零行**。
唯一数据是 `D2-detail-rows`（D2-2 明细表 555KB）。

## 前置条件（本 spec 实施前必须确认）

1. D2-6~D2-13 工作簿在 `wp_index` 里的 `wp_code` 是什么？（可能是 D2-1 或其他）
2. 该 `wp_code` 是否已在 manifest 的某个 entry 覆盖范围内？如果不是，需要新建 manifest entry
3. 每个子组件的实际 store 持久化路径——是 `handleChildSave` 回调还是组件内部直写
4. D2-8 和 D2-13 几乎全是文字描述（公式仅 6/12 个），是否需要双向？

## 需求

1. 为 D2-6~D2-13 的 Excel sheet 建立逐字段的双向映射（provider + 契约 + instrumentation）
2. 前端子组件实现 store 持久化（如果当前没有）
3. 前端接桥（走 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`）
4. 每张 sheet 的 roundtrip 验证（HTML→OO→HTML 数据不丢不错）
