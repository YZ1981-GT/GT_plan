# Task 6 证据：跨 spec 协调登记（2026-09-30 现算）

## 现算结论：两条「跨 spec」载体的消费方**都已归零**

| 载体 | spec 原文 | 2026-09-30 现算生产 import 边 | 归属 |
|---|---|---|---|
| `composables/useH6DualMode.ts` | 在 H4→H6→H8→H9 链式复用链上，**不得单方面改** | **0** | `h2-h6-h10-pilot-cross-reference-lanes` |
| `composables/useH9DualMode.ts` | 「实测消费 1，**不得删**」 | **0** | foundation（canary 链路） |

🔴 **`useH9DualMode` 那条原文已过期**：H9 宿主已接 `useHSyncMode`，legacy dual-mode
不再被任何生产文件 import。`useH6DualMode` 同理 —— 当初的「链式复用、改它要跨 spec 协调」
顾虑随接桥一并消失。

## 本 spec 的处置：只登记，不删

两个文件都已是零消费孤儿，但**不在本 spec 删**，理由三条：

1. **归属不在本 spec**（Task 6 原文就是「只登记」）；
2. 删旧代码铁律要求「删前 grep 0 调用方 + 删前后测试全绿 + **独立 commit**」——
   混在本轮的子入口/载体改动里会让回归面不可分辨；
3. 本 spec 的 `useH8DualMode`（子 Tab 唯一切换实现，消费 1）与 `useH4DualMode`
   （两个子 Tab，消费 2）是**禁删项**，与上面两个孤儿形态相反，放一起删极易误伤。

## 仍被消费的载体（现算，禁删）

| 载体 | 生产 import 边 |
|---|---|
| `useH4DualMode.ts` | `h4/impairment/H4TabImpairment.vue` · `h4/impairment/H4TabRecoverable.vue` |
| `useH8DualMode.ts` | `h8/impairment/H8TabRecoverable.vue` |

🔴 `useH8DualMode` 这条正是本 spec Task 5 点名「最易漏」的那条：**H8 宿主内联了自己的
实现，只有这个子 Tab 用 legacy 载体** ⇒ 按「删 composable + 改宿主」的常规套路会完全
漏掉它。守卫 `test_h_lane2_sub_entries_and_carriers.py` 为它单独立了一条判据。
