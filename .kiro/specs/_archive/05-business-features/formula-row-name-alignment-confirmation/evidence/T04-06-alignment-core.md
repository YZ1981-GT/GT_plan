# Task 4/5/6 — 名称对齐核心（候选生成 / classify 四态 / resolve_amounts）

产物：`backend/app/services/four_table/row_name_alignment.py`
守卫：`backend/tests/four_table/test_row_name_alignment.py`（21 passed）

## 复用既有科目定位（红基线 3：不重写定位）

`build_candidates` 只调用既有共享件，**不复制** `ReportLineAccountSpec` / `SemanticAccountSpec` 定位逻辑：
- aux 侧：`aux_aggregation.aggregate_aux_by_name`（已锁单一 aux_type、走 `get_active_filter` 只取 active dataset、防维度冗余双算）
- account 侧：`tb_query.fetch_tb_subtree` + `leaf_aggregation.select_leaves` + `filter_by_prefixes`

`account_prefixes` 由调用方从上游定位解析传入，本函数内不重新定位科目。

## 版本化参数（改动即 bump 并更新本 evidence）

| 参数 | 值 | 说明 |
|---|---|---|
| `NORMALIZATION_VERSION` | `norm-v1` | 归一规则版本 |
| `SIMILARITY_VERSION` | `sim-v1` | 相似度算法版本 |
| `SIMILARITY_THRESHOLD` | `0.55` | >= 阈值纳入相似候选 → ambiguous（不当精确命中） |
| `CANDIDATE_LIMIT` | `20` | 单行候选上限（排序后截断） |

### 归一规则（`normalize_name`，仅用于候选匹配，不用于出数/不改展示名）
1. `unicodedata.normalize("NFKC", s)`：全角→半角折叠（字母/空格/罗马数字）
2. 去所有空白（含中文空格）+ lowercase
3. 剥常见机构后缀（最长优先）：`有限责任公司 / 有限公司 / 股份有限公司 / 分公司 / 总公司 / 公司`；
   仅当 `len(s) > len(suffix)` 才剥（名字本身是「公司」不剥空）

### 相似度算法（`similarity`）
- 字符二元组（bigram）Dice 系数：`2 * |A∩B| / (|A| + |B|)`
- 无第三方依赖；归一名相等 → 1.0；空串/无公共二元组 → 0.0
- 单字符名回退相等判定

## 四态状态机（`classify`，Property 1 / 2）

优先级：
1. 有已落库映射 → 先判 stale（目标身份是否仍在 active 候选身份集）
   - 全部有效 → `USER_CONFIRMED`
   - 任一失效（dataset 变化 / 科目或维度不一致 / 名称消失）→ stale ⇒ `UNMATCHED` + `stale_reason`
2. 无映射 → 归一名匹配
   - 归一后唯一精确命中 → `AUTO_MATCHED`
   - 归一后多命中 / 相似度 >= 阈值（非唯一精确）→ `AMBIGUOUS`
   - 零命中 → `UNMATCHED`

🔴 归一后非唯一命中一律 `AMBIGUOUS`，绝不当精确命中出数（Requirement 5.2）。
目标身份比对用 `identity_tuple()`（source_kind + account_code + aux_type + dimension_key + dataset_id），
**名称仅作展示**，仅名称存在不能解除 stale（Property 2）。

## 多对一口径与无值语义（`resolve_amounts`，Property 3 / 6，DEC-3）

- 多对一（不同 row_key 目标身份交集非空）：**不自动去重**，各行各自聚合，但涉及行全标 `duplicate_reference=True`
- `unmatched` / `ambiguous` / stale 行：`amount is None`（无值语义），**绝不是 0 或上期值**（Requirement 5.1）

## 守卫覆盖（21 passed）

- 归一/相似度纯函数 5 例
- Property 1：唯一精确=auto / 归一多命中=ambiguous / 相似非精确=ambiguous / 零命中=unmatched + 2 PBT（四态合法 + 多命中永不 auto）
- Property 2：valid=user_confirmed / dataset 变=stale unmatched / 名称消失=stale unmatched
- Property 3：多对一全标 duplicate + 无共享不标 + PBT（n 个共享全标）
- Property 6：stale 行 None / unmatched 行 None + PBT（confirmed 行 == 目标和）
