# E1 披露表 ↔ 附注（五、1 / 八、1）

## 章节与结构（严格对齐附注模板）

| 变体 | 章节 | 表结构 |
|---|---|---|
| 上市 | `五、1` | 单表「货币资金」：项目 / 期末余额 / 上年年末余额（8 行含合计 `is_total`） |
| 国企 | `八、1` | 主表「货币资金」：项目 / 期末余额 / 期初余额；+「受限制的货币资金明细」：项目 / 期末 / 期初 / 受限原因（含合计） |

说明文字经 `_note_texts` 同步为附注 `text_content`。

**外币性质货币资金表按模板归属 `五、81`，不并入五、1**（附注模块只渲染扁平单级表头，多级表头表要么拍平列名要么按模板归属其他节；不得自造）。

## 推送链

`buildE1SyncPayload`（`e1NoteSectionMap.ts`）→ `POST sync-from-workpaper`
（`sub_table_data` 各子表键 ↔ `columns` 键**同名**，投影器按名匹配）
→ `disclosure_notes.table_data` + `_sub_table_columns`
→ `GET note detail` 时 `note_sub_table_projector` 投影成 `_tables[]`。

emit `disclosure:note-text-updated` 携 `accountCode: '1001'` + `sectionIds: ['五、1']`
→ `useNoteRefresh` 的 `matched(sectionIds)` 路径自动刷新当前节。

## 期初数自动预填

披露表期末数从审定表跨 sheet 键 `E1-adj-total-{code}` 取；
期初数从 `E1-adj-total-{code}-opening` 取（本年期初 = 上年年末），
**手工覆盖优先**（`key in map` 显式判断，0 是合法值），预填的格子带绿色「预填」tag。

## 双向跳转

- 正向（附注 → 披露表）：`isE1MonetaryFundNoteSection` 精确匹配 `五、1` / `八、1`（**禁 `startsWith`**，否则串 `五、10`~`五、19`，其中 `五、18` 是 G7 长期股权投资）
- 反向（披露表 → 附注）：`buildNoteJumpRoute` → `?section=五、1&noteTemplate=listed`
- E1 披露 sheet 的真实 tab 名是 `附注披露信息(上市公司)` / `附注披露信息(国企)`（**半角括号**，与 D1 的全角不同），跳转常量必须用真实 tab 名，用 OnlyOffice 的 sheet-name 映射（`附注上市`）会精确匹配失败回退到底稿目录
