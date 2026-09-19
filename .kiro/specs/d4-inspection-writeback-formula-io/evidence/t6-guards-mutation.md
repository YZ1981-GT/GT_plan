# T6 — 行为守卫 + 四态变异 证据

> 四态判定：RED（打红且命中预期测试）/ GREEN（守卫缺陷，改坏仍绿）/ ANCHOR-MISS（锚点未命中）/ WRONG-TEST（红了但非预期项）。

## 守卫清单（行为/结构级，非「字符串存在」）

### 后端（不连库，驱动真实 parser/exporter 纯函数）
- `backend/tests/test_d4_inspection_io_guards.py`（既有，6 passed）：D4-15 嵌套结构逐字段、item_id=D4-15-items（≥2 次）、D4-16 英文 key+差异重算、往返重算自洽、D4-13 登记+双 item helper、import 分发走专用 parser。
- `backend/tests/test_d4_inspection_io_roundtrip.py`（本 spec T3 新增，7 passed）：D4-14/15/16 PBT 往返（poison 差异/一致性/分数被重算覆盖，证派生列单源）+ item_id 双侧一致 + D4-13 文本锚点 + 四表专用 header 非 generic。

### 前端（行为 + 源码结构）
- `audit-platform/frontend/src/components/workpaper/__tests__/d4InspectionWriteback.spec.ts`（21 passed，含 T4 段 9 条）：推送人工触发、金额人工认定、reason 非空不构成异常、幂等/去重追加/只读/空项。

## 变异检验结果

### 后端 `mutate_d4_inspection_io_guards.py`（既有，本次复跑确认）
```
verdicts: M1_item_id_back_to_rows=RED / M2_dispatch_back_to_generic=RED / M3_diff_read_from_file=RED
green_count=0, restored_ok=true, pass=true
```
- M1：D4-15 item_id 改回 D4-15-rows → item_id 守卫 RED
- M2：import 分发 D4-16 改回 generic parser → 分发守卫 RED
- M3：D4-16 taxDiff 从 `book-tax` 重算改成读文件「申报差异」列（造假入口）→ 重算守卫 RED

### 前端 `mutate_d4_inspection_t4_guards.py`（本 spec T6 新增）
```
verdicts: M1_push_in_debounce_auto=RED / M2_filter_by_reason_not_diff=RED / M3_d4_15_push_all=RED
green_count=0, pass=true
```
- M1：把 `handlePushToA13()` 塞进 D4-16 的 `setTimeout(debounceSave)` 自动回调 → 「推送必须人工触发」守卫 RED
- M2：D4-16 过滤条件从 `portsDiff/taxDiff !== 0` 改成 `portsReason || taxReason`（reason 非空当异常）→ 守卫 RED
- M3：D4-15 过滤从 `isConsistent === false` 改成 `true`（推全部）→ 守卫 RED

### 🔴 变异过程真实发现并修复的守卫缺陷（非假绿）
- **首轮 M1 = GREEN**：初版 T4 守卫只扫 `pushToA13\s*\(`（composable 直调），漏了按钮 wrapper `handlePushToA13(`。变异把 wrapper 塞进 debounce 回调后守卫仍绿 → 暴露守卫承重不足。
- **修复**：T4 守卫在自动回调窗口内同时禁 `\bpushToA13\s*\(` 与 `\bhandlePushToA13\s*\(`（两条绕过人工触发的路都堵）。修后 M1 转 RED，基线 21 passed 不回归。
- 教训沿用 memory：mutation 抓假绿的价值正在此——静态「字符串存在」判据会漏 wrapper 层。

## 结论
后端 3 锚点 + 前端 3 锚点，全 RED、green_count=0、pass=true；守卫真在承重，含一处经变异发现并修复的真实缺陷。
