# 复盘修复 — 5 项缺陷（交付后自查发现并修复）

交付后主动复盘（实读代码而非凭记忆）发现 5 个问题，逐一修复。回归全绿。

## #1 弹窗 eventBus 监听器泄漏（真 bug）

- **问题**：`GtRowNameAlignmentDialog.vue` 在 setup 顶层 `eventBus.on('open-row-name-alignment', open)`，无 `onUnmounted` 反注册。GtWpRenderer 每次切底稿重挂弹窗 → 监听器累积 → 一次事件触发多个陈旧实例。
- **修**：移入 `onMounted` 注册 + `onUnmounted(() => eventBus.off(...))`。
- **守卫**：`test 复盘 #1 unmount 后事件不驱动旧实例`（挂→卸→触发→挂新，断言只驱动新实例）。

## #2 候选双源可能双算（口径隐患）

- **问题**：`build_candidates` aux 候选 dim=`前缀|aux_type|归一名`、account 候选 dim=`叶子码|None|归一名`，两者 `dimension_key` **永不相等** → 只按 dim 去重等于不去重。同一明细的往来单位名与科目名会各出一条候选，用户各选即金额双算。
- **修**：跨源去重改按**归一名**（`seen_norms`）：aux 优先保留（更细粒度），account 侧同归一名一律跳过。
- **守卫**：`test_cross_source_dedup_by_normalized_name`（同名只出一条 aux）+ `test_distinct_names_both_kept`（异名都留）。

## #3 dataset_id 全链断链（stale 判定生产未生效）

- **问题**：`aggregate_aux_by_name` 不返回 dataset_id、render-config 不下发 → 候选目标身份 dataset_id 恒 null → stale 指纹里 dataset 恒空 → Property 2（dataset 变化判 stale）**生产环境永不触发**。交付时守卫用手造 `ds-active` 证明逻辑正确，但生产链路没接上。
- **修**：`build_candidates` 调用方未显式传 dataset_id 时，主动查 `DatasetService.get_active_dataset_id(db, project_id, year)` 注入 `effective_dataset_id`（取失败降级为空 + WARNING，不阻断）。
- **真栈验证**（`T14b-rerun-after-fixes.json`）：候选 dataset_id = 真实 active `38bf9d9c`（非 null）；把映射目标 dataset 改 `ds-OLD-gone` → classify 正确判 unmatched + stale_reason（此前恒 null 时永不触发）。

## #4 getRowNameAlignmentRows 子组件契约悬空（前端无真实入口）

- **问题**：「刷新取数」按钮依赖子组件暴露 `getRowNameAlignmentRows()`，但无任何真实 SFC 实现 → 生产环境点按钮全走「暂不支持」降级 → spec 用户可见价值为 0。
- **修**：接线样板底稿 **D3-2 预收账款明细**（真实按客户名取数）：
  - `D3TabDetail.vue` expose `getRowNameAlignmentRows()` → 返回 `{row_key=rowId, row_label=customerName, account_prefixes=[]}`
  - `GtD3PrepaidAccounts.vue`（顶层 bundle，`activeComponentRef` 实际指向它）持 `detailRef` 并按 `currentSheet==='D3-2'` 转发（两层接线，避免接错层假接线）
- **附带修正设计瑕疵**：前端不再传 `account_prefixes`（科目定位是后端职责，红基线 3）。端点 `/row-name-alignment` 新增 `_resolve_account_prefixes(wp_code, sheet_code)`，按 `wp_account_mapping.json` 兜底解析（D3→2203 / D1→1121 / K1→1221，实扫确认）。
- **守卫**：源码结构断言（D3TabDetail expose + 客户名 + 空前缀；bundle detailRef + 转发 + expose）—— 落到「唯一消费方 + 有渲染宿主」判据。

## #5 build_candidates fail-open 吞异常

- **问题**：两个 `except Exception` 把取数失败吞成空列表 + WARNING → 「取数出错」与「真无候选」不可区分（memory 反复警告的 fail-open 掩盖接线错误）。
- **修**：改抛 `CandidateSourceError(source, cause)`（记 ERROR）；端点 `row_name_alignment` 捕获返回 HTTP **502** + `{source}`，不伪装成 unmatched。
- **守卫**：`test_source_error_raises_not_swallowed`（源异常抛 CandidateSourceError）+ `test_empty_sources_return_empty_not_error`（真空返 [] 不抛）。
- **🔴 未穿透的限制（如实记录）**：底层共享件 `aggregate_aux_by_name` / `fetch_tb_subtree` 自身仍 fail-open（内部 `except: return []`），本层 raise 只能捕获归一/select_leaves 等纯函数层异常。穿透底层 fail-open 需改共享件（影响 4+ 其它消费者，属越界，不在本次修复范围）。同期 `four-table-extraction-entry-completion` spec 已规划给底层加 `reason` 码。

## 回归

- 后端 **41 passed**（原 36 + candidates 5）
- 前端弹窗 **9 passed**（原 6 + #1 生命周期 1 + #4 接线 2）
- 变异 **4 锚点全 RED**，`pass:true`（改动未削弱守卫）
- 真栈端到端复测 **PASS**（`T14b-rerun-after-fixes.json`，含 #3 dataset_id 接通 + stale 生效 + 非零真实值）
- 全部改动文件零诊断
- 临时脚本已清理
