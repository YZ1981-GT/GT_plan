# G4-1 就绪评估（其余三类 Excel pilot）

> 日期：2026-09-11（G0-4 分母扩收后更新）  
> 前置：`HOST-CONSUMES-UNIFIED-PATH` 分母 **4** entry 均为 **`ONLYOFFICE_VERIFIED`**（D2-2 + H1 + G7 + B60）

## Pilot 分母（总控 Phase 4）

| Pilot | entry（示意） | 宿主现状 | G4-1 / G0-4 |
|---|---|---|---|
| D2 large JSON | `xlsx/gt-d2-accounts-receivable` | `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost` | ✅ G4-0d + G0-4 |
| H1 grouped dynamic | `xlsx/gt-h1-fixed-assets` | ✅ H1-8 统一 bridge/host | ✅ §9.6 + G0-4 |
| G7 two-level dynamic | G7 long-term equity | ✅ 国企附注统一 bridge/host | ✅ §9.6 + G0-4 |
| Simple checklist | `xlsx/b60/gt-b60-bundle` | ✅ B60-1 统一 bridge/host | ✅ §9.6 + G0-4 |

## 裁决

1. **不得**把 Task 40/42/43 的历史 `[x]` 当成 G4-1 完成——那些勾选早于统一路径 / 真 OO 往返。
2. G4-1 每个 pilot 必须复制 D2-2 的最低证据：`USER_SYNC_PREFIX` network、无 `/d2-sync/*`、room-bound callback、`application.applied`、HTML DOM / store 可见值。
3. 扩 `HOST-CONSUMES` denominator 时按 entry 追加 G0-4 正例通道，禁止跨 entry 复用 D2-2 digest。
4. `/d2-sync/*` **仍不删**：legacy `useD2SyncBridge` + `d2_sync_router` 仍被耐久门守卫引用；删前需退役守卫并确认无生产调用。
5. **DEC-11**：B60 不放宽 `allow_external_relationships`；净化权威模板孤儿外链（bak 保留为门负例）。

## 建议开工顺序

1. ~~G7 / H1 / B60 真栈 Playwright~~ ✅  
2. ~~G0-4 分母扩收~~ ✅（`ONLYOFFICE_VERIFIED=4`）  
3. 其后才谈 `/d2-sync/*` 退役（DEC-08）；G5-1 全量分批须另开里程碑
