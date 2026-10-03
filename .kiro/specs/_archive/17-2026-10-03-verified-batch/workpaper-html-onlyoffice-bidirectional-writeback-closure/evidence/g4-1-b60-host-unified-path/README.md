# G4-1 · B60 simple-checklist host unified path（接线 + §9.6 硬绿）

> 状态：**HOST WIRED** + **ONLYOFFICE 真栈硬绿**（2026-09-11）· 以本目录 `network-and-callback.json` 谓词为准  
> entry：`xlsx/b60/gt-b60-bundle` · managed：`B60-1工时预算与控制表` / `b601-managed` · adapter：`b60.hour_budget`  
> canary：project `0ec33ac9…` · 打开主稿 B60 `8c258d1c…` → B60-1 tab；sync/representation 在子 wp `afb9201a…` · OO cell **G7** · store `B60-1-hour-budget-rows`

## 谓词（本轮 Playwright `1 passed`）

| 谓词 | 结果 |
|---|---|
| USER_SYNC / 无 `/d2-sync/*` | ✅（`d2_sync_hits=0`） |
| materialize 200 + room-bound callback keys | ✅ |
| `confirm_descriptor_200` | ✅ |
| forcesave `cs_error=0` | ✅（op `bf9c9599…`，room `e4c46326…`） |
| store `store_mirrored` | ✅（marker `77903116`） |
| HTML DOM `marker_visible` | ✅（`input_or_text_hits=1`） |

## 本轮修复 / 取证动作

1. **DEC-11**：不放宽 `allow_external_relationships`；净化权威模板孤儿外链后首版 representation
2. **`b60-strategy` 进 `DEDICATED_COMPONENT_TYPES`**：多 sheet B60 否则落到 `univer`，「配置未就绪暂用表格模式」永远挂不上 `GtB60Bundle`
3. **`GtB60Bundle` wpIdMap**：直接打开 B60 时无 GtBIndex/`cycle_workpapers`；改走项目级 `/api/projects/{pid}/wp-index` 映射 `B60-1`
4. **`GtB60HourBudgetPanel` checklist 路径**：项目前缀 404 → 改 `/api/workpapers/{wpId}/checklist-responses`（与 e2e store 探针一致）
5. **复跑 confirm 422**：同 gen-1 room 旧 confirm identity 漂移（H1 同类）；canary 将该 room `invalidated_at` 后 confirm 恢复 200

## 诚实边界

- **不得**据此物理删除 `/d2-sync/*`（DEC-08）
- G0-4 / HOST-CONSUMES 分母扩收须走里程碑程序，不单靠本目录 README 宣称
- `doc_editor_called` 探针仍常为 false（hook 竞态）；权威判据是 confirm/CS0/store/DOM
- 主稿章节「在线编辑」仍走 `usePilotBridgeAdapter`（sheet=`B60`）；统一路径 canary **仅** B60-1 工时表
- canary `2aa00f57` **无** B60-1；真栈用 `0ec33ac9`

## 验收

```text
npx vitest run src/components/workpaper/__tests__/b60SyncHostWiring.spec.ts
npx playwright test e2e/g4-1-b60-unified-path.spec.ts --workers=1
```
