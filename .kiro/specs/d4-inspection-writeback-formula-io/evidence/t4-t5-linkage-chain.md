# T4 / T5 — 发现→人工认定链 + A13/D4-1 联动 核定与守卫证据

> 依据：`useD4InspectionWriteback.ts`（推送共享件）+ `useA13MisstatementBridge.ts`（A13 唯一消费者）+ 四个 inspection 组件（D4TabErpCheck/Occurrence/Completeness/Export.vue）。
> 相关 Requirement：3.1（发现≠错报）/ 3.2（人工确认方向金额证据）/ 3.3（durable ack）/ 3.4（D4-1 独立重试幂等）。

## T4 发现→人工认定链（Requirement 3.1 / 3.2 / 3.4）

### 结论：四表的「发现≠自动错报」链路已就位，本 spec 补守卫锁死

| 表 | 推送触发 | 过滤条件（发现→候选） | 金额来源（人工认定） |
|---|---|---|---|
| D4-13 | 按钮 `@click="handlePushToA13"` | 无结构化行，审计师 `ElMessageBox.prompt` **手填差异金额** | 人工输入；`if (!amount) 不推送` |
| D4-14 | 按钮 `@click` | `conclusion === '存在重大异常' \|\| isAnomalous`（人工结论/标记） | 行金额，仅重大异常项 |
| D4-15 | 按钮 `@click` | `isConsistent === false`（公式/人工判定不一致） | 三维中有值者，不把凭证全额自动当错报 |
| D4-16 | 按钮 `@click` | `portsDiff !== 0 \|\| taxDiff !== 0`（差异非零） | `abs(portsDiff)+abs(taxDiff)`；reason 仅入描述 |

### 守卫（test_d4_inspection_io_roundtrip.py 无关，前端 d4InspectionWriteback.spec.ts T4 段）

- **A13 推送必须人工触发**：扫四组件，断言 `pushToA13(` 不出现在 `watch/watchEffect/onMounted/setTimeout/setInterval/debounce*` 回调体窗口内；模板必须 `@click="handlePushToA13"`（对齐 `check_tb_publish_confirm_gate` 门控纪律）。
- **金额/方向人工认定**：D4-13 断言 `ElMessageBox.prompt` + `if (!amount)` 短路；D4-16 断言过滤条件是 `portsDiff/taxDiff !== 0` 而**非** reason 非空（`.filter(...portsReason...)` / `.filter(...taxReason...)` 必不存在）。
- **amount ≤ 0 不入 A13**（定性事项/零额）：由 `normalizeMisstatementPushPayload` 的 `if (amount <= 0) continue` 保证，已由 `useA13MisstatementBridge.spec.ts::金额 ≤0 的行不生成错报` 覆盖（非本 spec 新增，实证复用）。

## T5 A13 + D4-1 独立持久链（Requirement 3.3 / 3.4）

### 已就位并有守卫（复用既有测试，非本 spec 新造）

- **source identity 幂等去重**：`useA13MisstatementBridge` 的 `draftHash = wpCode|description|amount|accountCode|misstatementType`（含 misstatementType 维度，CAS 1251 事实/推断错报不互吞）+ `DEDUP_WINDOW_MS=5000` 时间窗去重。守卫：`a13MisstatementType.spec.ts::Property 9 — 去重 hash 含类型维度`（含反向自检：同款描述的 factual/projected 是两笔）。
- **source_wp_code 溯源**：`createMisstatement(..., source_wp_code: wpCode.slice(0,20))`。
- **D4-1-adj-note 去重追加**：`appendToD41Note` 写 `item_id='D4-1-adj-note'`，累加不覆盖（`prev ? prev+line : line`），经 `d4:save-items` 独立落库；与 A13 成功状态**独立**（appendToD41Note 在 emit 之后无条件调用，不依赖 A13 ack）。守卫：`d4InspectionWriteback.spec.ts::appendToD41Note 追加 / append 是累加不是覆盖`。
- **只读态不推送 / 空项不 emit**：`d4InspectionWriteback.spec.ts` 覆盖。

### 🔴 遗留（如实登记，非假绿）：durable ack 是 best-effort，非持久队列

- **现状**：`useA13MisstatementBridge.handler` 是 `for (const d of fresh) { try { await createMisstatement(...); ok+=1 } catch { fail+=1 } }` + `ElMessage.success/error`。
  - ✅ 有：逐笔 try/catch 隔离（单笔失败不拖垮整批）、ok/fail 计数、中文提示、窗口内幂等去重。
  - ❌ 无：**持久 ack 回执**（无 outbox/ack 表落地成功凭证）、**失败重试队列**（fail 仅弹错，刷新即丢）、**跨会话去重**（`recentHashes` 是内存 Map，页面刷新重置）。
- **定性**：Requirement 3.3「durable ack」「独立重试」在**平台层尚未提供**该基础设施（A13 写入是同步 POST，无 outbox/重试框架）。这与治理 spec `c3_linkage_contract` 的 durable ack 冻结契约是**平台级待建项**，非本四表 spec 可独立落地 → 归 **B3 [blocked]**（见 tasks.md Governance Addendum）。
- **不伪称**：本 spec 不把 best-effort try/catch 标称为「durable ack 已实现」。T5 交付 = 幂等去重 + D4-1 独立追加 + source 溯源做实；durable 持久化/重试如实转 B3 blocked。

## gate 结论

- T4：四表发现→人工认定链**做实 + 守卫锁死**（人工触发 + 金额人工认定 + reason 非空不构成异常 + amount≤0 不入 A13）。
- T5：source identity 幂等 + D4-1 独立去重追加 + 溯源**做实（复用既有守卫）**；durable ack 持久化/重试**如实登记为 B3 blocked**（平台级基础设施待建）。
