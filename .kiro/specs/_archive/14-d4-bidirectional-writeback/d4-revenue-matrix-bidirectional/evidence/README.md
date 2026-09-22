# D4 Wave 1 evidence

| Artifact | Task | Digest / key fact |
|---|---|---|
| `T01-column-field-mapping.json` | 1 | `mapping_digest=6d2f340d45ba0a24c95424c1e698be3df105252c160d174a2e4c748ec1554cc8` |
| `T03-formula-classification-census.json` | 3 | openpyxl 展开：`external_bracket=270` / `internal=951` / `total_f=1221`；外链部件 17 |
| `T04-sanitize-mutation-verdict.json` | 4 | 变异 4/4 RED；clean sha256=`b8fb92d4…167b5f`；bak 门 REJECT |
| `backend/tests/workpaper_sync/test_d4_positional_array_roundtrip.py` | 2 / 2.1 | **6 passed**（含真实 `parse_contract→build_excel_adapter→materialize→extract→merge`） |

## Task 1 几何（权威模板 `D/D4 收入底稿.xlsx`）

- 受管 sheet：`主营业务收入明细表D4-2`（A1:V32）
- 表头行 11 / 数据区 12–23 / footer 行 24 / marker 精确文本 `合计`（无额外空格）
- 契约字段 **18**：A `product` + B–M `months/0..11` + N `period_total`(formula) + O `auditAdjustment` + Q/R prior + V `remark`
- P/S/T/U 为模板内部公式列，**不进契约 18 条**，但仍须 formula mask（不得被 projection 覆盖）
- store 真源：`useD4RevenueDetail.ts` → `D4-2-rows`；持久化键含 `months: number[12]`

## Task 3 公式分类

- `[n]` 外链公式格：**270**（与 g5-1 §11 一致）—— sanitize 只删这类 `<f>`
- 内部公式（openpyxl 展开后）：**951**（含 shared 引用展开）；zip master 文本 168 + 空 shared 引用 219
- 受管 N12:N23：全部 `=SUM(B{r}:M{r})`，**无 `[n]`**，必须逐字节保留
- 受管 sheet 另有 6 个页眉 `[5]底稿目录!…` 外链公式（可删）

## Task 2 阻塞门

共享实现：`backend/app/services/workpaper_sync/json_path.py`  
（list 下标段 / 长度 12 守卫 / OOB fail-closed；稳定错误码）

重生命令：

```powershell
& .venv/Scripts/python.exe backend/scripts/diagnose/d4_wave1_census.py
& .venv/Scripts/python.exe -m pytest backend/tests/workpaper_sync/test_d4_positional_array_roundtrip.py -v
```
