# G4-1 · G7 SOE host unified path（接线 + §9.6 硬绿）

> 状态：**HOST WIRED** + **ONLYOFFICE 真栈硬绿**（2026-09-11）· 以本目录 `network-and-callback.json` 谓词为准  
> entry：`xlsx/gt-g7-long-term-equity-main` · managed：`附注披露信息（国企）` / `g7n-managed` · adapter：`g7.soe_subsidiary_disclosure`  
> canary：project `2aa00f57…` · wp `354e060f…` · OO cell **C64** · store `G7-main-disclosure-soe-v2`

## 谓词（本轮 Playwright `1 passed`）

| 谓词 | 结果 |
|---|---|
| USER_SYNC / 无 `/d2-sync/*` | ✅（`d2_sync_hits=0`） |
| materialize 200 + room-bound callback keys | ✅ |
| `confirm_descriptor_200` | ✅ |
| forcesave `cs_error=0` | ✅（op `6efd5fa2…`，room `cf7f7185…`） |
| store `store_mirrored` | ✅（marker `88412589`） |
| HTML DOM `marker_visible` | ✅（`input_or_text_hits=1`） |

## 本轮修复 / 取证动作

1. **禁止手改 published immutable artifact**：digest 漂移曾致 store-projection 500；从 `.pre-noif.bak` 恢复冻结 digest
2. **OO `editor_error_-82`**：zip 级剥离裸 `IF()` + 丢 `calcChain`；检测用 OOXML 词界 IF（忽略 SUMIF/COUNTIF）；verify_unmanaged 对比前同样 neutralize
3. **同 `doc_key` 缓存 -82**：G7 generation 用 entry-global `max+1`；有 crash IF 或 stuck `opening` 时跳过 business-identity reuse
4. **rematerialize `excel_materialize_footer_anchor_drift`**：`_find_marker_row` 对 OO 自闭合空格 `<c r="A84" s="168"/>` 误吞 footer；attrs 改为 `[^>/]*` 并区分 `/>` vs `>(body)</c>`

## 诚实边界

- **不得**据此物理删除 `/d2-sync/*`（DEC-08）
- G0-4 / HOST-CONSUMES 分母扩收须走里程碑程序，不单靠本目录 README 宣称
- `doc_editor_called` 探针仍常为 false（hook 竞态）；权威判据是 confirm/CS0/store/DOM
- simple checklist pilot ✅（`evidence/g4-1-b60-host-unified-path/`）

## 验收

```text
npx vitest run src/components/workpaper/__tests__/g7SyncHostWiring.spec.ts
npx playwright test e2e/g4-1-g7-unified-path.spec.ts --workers=1
```
