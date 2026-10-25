# G4-1 · H1-8 host unified path（接线 + §9.6 硬绿）

> 状态：**HOST WIRED** + **ONLYOFFICE 真栈硬绿**（2026-09-11）· 以本目录 `network-and-callback.json` 谓词为准  
> entry：`xlsx/gt-h1-fixed-assets` · managed：`H1-8` / `h18-managed` · adapter：`h1.disposal_check`  
> canary：project `2aa00f57…` · wp `c71b7c54…`（不用已删 `f663b18c`）

## 谓词（本轮 Playwright `1 passed`）

| 谓词 | 结果 |
|---|---|
| USER_SYNC / 无 `/d2-sync/*` | ✅ |
| materialize 200 + room-bound callback keys | ✅ |
| `confirm_descriptor_200` | ✅ |
| forcesave `cs_error=0` | ✅（op `628f44bf…`） |
| checklist `store_mirrored` | ✅（marker `g4h1669524`） |
| HTML DOM `marker_visible` | ✅（`input_prop_hits=1`） |

## 本轮修复 / 取证动作

1. **extract 空串→null**（金额等类型；否则 L13 `net_value` materialize 500）
2. **OO→HTML store 镜像**扩到 `h1.disposal_check`（`H1-8-rows`）
3. **复跑阻塞**：同 gen-1 room 上已有 confirm 与当前 published representation identity 漂移 → confirm `422 scope_integrity_violation`；canary 使该 room 旧 confirm `invalidated_at=NOW()` 后 confirm 恢复 200
4. e2e DOM 断言改为 `.h1-tab-disposal-check`（去掉误留的 D2 选择器）

## 诚实边界

- **不得**据此物理删除 `/d2-sync/*`（DEC-08）
- G0-4 / HOST-CONSUMES 分母扩收须走里程碑程序，不单靠本目录 README 宣称
- `doc_editor_called` 探针仍常为 false（hook 竞态）；权威判据是 confirm/CS0/store/DOM

## 验收

```text
npx vitest run src/components/workpaper/__tests__/h1SyncHostWiring.spec.ts
npx playwright test e2e/g4-1-h1-unified-path.spec.ts --reporter=line --workers=1
```
