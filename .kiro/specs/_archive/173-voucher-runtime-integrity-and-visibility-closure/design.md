# 凭证运行完整性与可见性收口 — 设计

## §1 R1：单笔挂凭归属校验

### 现状 grep 确认

```
backend/app/routers/voucher_links.py
  L196  sample_voucher()  — body.working_paper_id 直接写入 SampledVoucher，无归属校验
  L225  row.sampling_record_id = body.sampling_record_id  — 直接赋值
  L334  _project_workpapers()  — 批量端点用它校验 wp 归属（单笔不用）
```

### 设计

在 `sample_voucher()` 函数体内、`_resolve_voucher_key` 之前插入两段校验：

**1a. working_paper_id 校验**

```python
if body.working_paper_id is not None:
    wps = await _project_workpapers(db, project_id, [body.working_paper_id])
    if body.working_paper_id not in wps:
        raise HTTPException(status_code=422, detail={
            "error_code": "WP_NOT_IN_PROJECT",
            "message": "目标底稿不在本项目（或已删除、未生成）",
        })
```

复用已有的 `_project_workpapers()`（L334），与批量端点同口径。用 422（而非 403/404），与批量端点的 `WP_NOT_IN_PROJECT` 错误码一致。

**1b. sampling_record_id 校验**

```python
if body.sampling_record_id is not None:
    from app.models.workpaper_models import SamplingRecord
    sr_exists = (await db.execute(
        sa.select(sa.literal(1)).where(
            SamplingRecord.id == body.sampling_record_id,
            SamplingRecord.project_id == project_id,
            SamplingRecord.is_deleted == sa.false(),
        )
    )).scalar_one_or_none()
    if sr_exists is None:
        raise HTTPException(status_code=422, detail={
            "error_code": "SAMPLING_RECORD_NOT_IN_PROJECT",
            "message": "抽样记录不在本项目（或已删除）",
        })
```

SamplingRecord 有 `project_id` 列和 `is_deleted` 列，直接查。

**改动范围**：仅 `voucher_links.py` 的 `sample_voucher()` 函数，约 +15 行。

---

## §2 R2：凭证链接查询底稿可见性

### 现状 grep 确认

```
voucher_links.py  L436~L494  query_voucher_links()
  — outerjoin working_paper 只做信息丰富，不做可见性过滤
  — grouped 结果直接返回，不调 _visible_wp_ids

voucher_evidence.py  L63~L76  _visible_wp_ids()
  — 对每个 wp_id 调 try_gate_wp(entrypoint="attachment.read", action="attach_read")
  — 不可见的静默排除
```

### 设计

将 `_visible_wp_ids` 从 `voucher_evidence.py` 提取为共享工具（或直接 import），在 `query_voucher_links()` 返回结果前过滤：

```python
# 在 grouped 构建完成后、return 之前
all_wp_ids = {
    UUID(wp_id) for entries in grouped.values()
    for (wp_id, *_), _ in entries.items() if wp_id is not None
}
if all_wp_ids:
    from app.services.voucher_evidence import _visible_wp_ids
    visible = await _visible_wp_ids(db, current_user, all_wp_ids)
else:
    visible = set()

# 过滤：wp_id 为 None 的保留（无底稿的旧登记），不可见的排除
filtered = {}
for key, entries in grouped.items():
    kept = {}
    for compound_key, entry in entries.items():
        wp_id_str = entry.get("working_paper_id")
        if wp_id_str is None:                     # 无底稿 → 保留
            kept[compound_key] = entry
        elif UUID(wp_id_str) in visible:           # 可见 → 保留
            kept[compound_key] = entry
        # else: 不可见 → 静默排除
    if kept:
        filtered[key] = kept
```

**关键决策**：
- 复用 `_visible_wp_ids` 而非重写（同一判定口径）
- `_visible_wp_ids` 当前是模块私有（`_` 前缀），改为从 `voucher_evidence` 显式导出，或提取到 `services/wp_visibility/voucher_wp_filter.py`。**选择前者**（只加导出，不新建文件），因为该函数只被两处调用且逻辑简单
- `wp_id=None` 的记录（旧手工"抽中本凭证"无底稿）不受影响，对所有项目成员可见

**改动范围**：`voucher_links.py` 的 `query_voucher_links()` 约 +15 行；`voucher_evidence.py` 无改动（`_visible_wp_ids` 保持原名，跨模块 import 私有函数是该仓库既有模式）。

---

## §3 R3：已抽凭证列表底稿可见性

### 现状 grep 确认

```
voucher_links.py  L251~L283  list_sampled_vouchers()
  — 只按 project_id / year / is_deleted 过滤
  — working_paper_id 参数可选，但不做可见性判定
```

### 设计

分两种情况处理：

**3a. 指定了 `working_paper_id`（底稿拉取自己的凭证）**

不额外过滤。调用方是底稿本身（如 D2 凭证检查），已有底稿级鉴权（`require_wp_edit_permission` 或页面级门禁），这里只需 readonly 级别即可读。

**3b. 未指定 `working_paper_id`（项目级凭证概览）**

查询结果后按可见性过滤：

```python
if working_paper_id is None:
    # 项目级概览：按底稿可见性过滤
    from app.services.voucher_evidence import _visible_wp_ids
    all_wp_ids = {r.working_paper_id for r in rows if r.working_paper_id is not None}
    visible = await _visible_wp_ids(db, current_user, all_wp_ids) if all_wp_ids else set()
    rows = [r for r in rows if r.working_paper_id is None or r.working_paper_id in visible]
```

- `working_paper_id=NULL` 的记录对所有项目成员可见（项目级登记，无归属底稿）
- 指定了 `working_paper_id` 时不走可见性（底稿自取）

**改动范围**：`voucher_links.py` 的 `list_sampled_vouchers()` 约 +8 行。

---

## §4 R4：投影 SAVEPOINT 加固

### 现状 grep 确认

```
sampling_registry_service.py
  L321  register_sampling_batch()       — try/except Exception，无 begin_nested
  L378  register_sampled_vouchers()     — try/except Exception，无 begin_nested
  L466  undo_sampling_registration()    — try/except Exception，无 begin_nested
  L539  update_sampling_record_evaluation() — try/except Exception，无 begin_nested
```

### 设计

四个函数统一改为 SAVEPOINT 模式：

```python
async def register_sampling_batch(db, *, log, created_by=None):
    try:
        async with db.begin_nested():   # ← 新增 SAVEPOINT
            # ... 原有逻辑不变 ...
            await db.flush()
        return record.id                 # SAVEPOINT 已释放，flush 成功
    except Exception:
        logger.warning(
            "抽样批次登记失败（sampling_records 投影未写入）"
            " workpaper=%s batch=%s error=%s",
            getattr(log, "workpaper_id", None),
            getattr(log, "batch_id", None),
            # R4.2：日志包含异常类名和消息
            f"{type(__import__('sys').exc_info()[1]).__name__}: {__import__('sys').exc_info()[1]}",
            exc_info=True,
        )
        return None
```

实际改法更简洁——异常类名用 `except Exception as exc` 获取：

```python
    except Exception as exc:
        logger.warning(
            "抽样批次登记失败 workpaper=%s batch=%s error_type=%s error=%s",
            ..., type(exc).__name__, exc, exc_info=True,
        )
```

**四个函数的改动模式完全相同**：在 try 块内加 `async with db.begin_nested():`，except 捕获为 `as exc` 并在 warning 中输出 `type(exc).__name__` 和 `exc`。

**关键约束**：
- `begin_nested()` 创建 SAVEPOINT，异常时自动 ROLLBACK TO SAVEPOINT，主事务保持 active
- 调用方的 `await db.commit()` 不受投影失败影响
- `register_sampled_vouchers` 使用 `pg_insert ... on_conflict_do_nothing`，正常情况下不会触发异常（冲突只返回 rowcount=0），SAVEPOINT 主要防 schema 不匹配或表达式索引偏差

**改动范围**：`sampling_registry_service.py` 四个函数各 +2~3 行（缩进 + `async with` + except 改名）。

---

## §5 R5：D2 合并口径对齐

### 现状 grep 确认

```
useD2VoucherCheckEnhanced.ts  L152~L176  mergeVoucherRows()
  L159  const existingNos = new Set(existingRows.map(r => r.voucherNo).filter(Boolean))
  — 只按 voucherNo 去重

shared/voucherCheckFill.ts  L435  mergeVoucherCheckRows()
  — 按分录指纹 (lfp) 去重，仅用于抽凭/挂凭回填场景
```

### 设计

将 `mergeVoucherRows` 的去重键从 `voucherNo` 改为 `voucherNo + voucherDate` 联合：

```typescript
export function mergeVoucherRows(
  existingRows: VoucherCheckRow[],
  incomingRows: VoucherCheckRow[]
): VoucherCheckRow[] {
  // 联合键：voucherNo + voucherDate（同号不同日是不同凭证）
  const existingKeys = new Set(
    existingRows
      .filter(r => r.voucherNo)
      .map(r => `${r.voucherNo}|${r.voucherDate || ''}`)
  )
  const result = [...existingRows]

  for (const incoming of incomingRows) {
    const key = `${incoming.voucherNo}|${incoming.voucherDate || ''}`
    if (!incoming.voucherNo || !existingKeys.has(key)) {
      result.push({ ...incoming, seq: result.length + 1 })
      if (incoming.voucherNo) existingKeys.add(key)
    }
    // 已存在的凭证 → 保留原有 check1~check5，不覆盖
  }

  result.forEach((r, i) => { r.seq = i + 1 })
  return result
}
```

**为什么不用 lfp（分录指纹）**：Excel 导入行没有后端分录指纹。lfp 是后端 `single_voucher_lines()` 生成的、包含分录行 ID 的哈希，前端 Excel 导入不经过后端取分录。

**为什么不加 company_code/voucher_type**：Excel 导入行通常没有这两个字段（用户只粘凭证号和日期），加了反而会让所有行都视为不同。`voucherNo + voucherDate` 是 Excel 导入场景下能拿到的最精确去重键。

**改动范围**：`useD2VoucherCheckEnhanced.ts` 的 `mergeVoucherRows` 约改 3 行。

---

## §6 R6：存量旧身份数据治理

### 设计

脚本 `backend/scripts/fix/fix_sampled_voucher_legacy_identity.py`：

**流程**：
1. 读 `sampled_vouchers` 中 `voucher_date IS NULL OR company_code IS NULL OR voucher_type IS NULL` 且 `is_deleted=false` 的行
2. 对每行按 `(project_id, year, voucher_no)` 查 active `tb_ledger` 账套
3. 按 `(voucher_date, company_code, voucher_type)` 分组去重
   - 唯一匹配 → 标为 `auto_resolve`，补全三列
   - 多个匹配 → 标为 `ambiguous`，列出候选
   - 零匹配 → 标为 `no_match`（账套可能已重导）
4. `working_paper_id IS NULL` 的行 → 标为 `legacy_orphan`（`--apply` 时在 note 追加标记，不删除）
5. 输出 JSON 报告到 stdout / 指定文件

**参数**：
- `--dry-run`（默认）：只输出报告不改库
- `--apply`：执行补全和标记
- `--project-id <uuid>`：只治理指定项目（可选，默认全部）

**数据安全**：
- `--apply` 前要求用户确认（stdin `y/n`）
- 每行修改前记录原值到报告的 `before` 字段
- 不物理删除任何行

---

## §7 R7：守卫设计

### 7.1 后端归属校验测试

文件：`backend/tests/test_voucher_links_ownership.py`

```
TestSampleVoucherOwnership:
  test_wp_belongs_to_project_succeeds       — 本项目底稿 → 201
  test_wp_belongs_to_other_project_rejected — 别的项目底稿 → 422 WP_NOT_IN_PROJECT
  test_wp_deleted_rejected                  — 已删除底稿 → 422 WP_NOT_IN_PROJECT
  test_wp_none_allowed                      — 不传 wp → 正常创建
  test_sampling_record_other_project        — 别的项目 sampling_record → 422 SAMPLING_RECORD_NOT_IN_PROJECT
  test_sampling_record_deleted              — 已软删 sampling_record → 422
  test_sampling_record_none_allowed         — 不传 sr → 正常创建
```

### 7.2 后端可见性测试

文件：`backend/tests/test_voucher_links_visibility.py`

```
TestVoucherLinksQueryVisibility:
  test_visible_wp_included                  — 可见底稿的挂凭记录在返回中
  test_invisible_wp_excluded                — 不可见底稿的挂凭记录被排除
  test_null_wp_always_included              — wp=NULL 的旧记录始终可见

TestSampledVouchersVisibility:
  test_project_level_filters_by_visibility  — 未指定 wp：不可见的排除
  test_wp_specific_no_filter                — 指定 wp：不额外过滤
  test_null_wp_always_visible               — wp=NULL 始终可见
```

### 7.3 变异检测

每个校验/过滤点配磁盘变异：

| 靶点 | 变异 | 预期 |
|------|------|------|
| sample_voucher 的 wp 校验 | 删除校验块 | test_wp_belongs_to_other_project_rejected 打红 |
| sample_voucher 的 sr 校验 | 删除校验块 | test_sampling_record_other_project 打红 |
| query_voucher_links 的 visible 过滤 | 删除过滤块 | test_invisible_wp_excluded 打红 |
| list_sampled_vouchers 的 visible 过滤 | 删除过滤块 | test_project_level_filters_by_visibility 打红 |

### 7.4 D2 合并口径 PBT

文件：`audit-platform/frontend/src/components/workpaper/composables/__tests__/mergeVoucherRows.spec.ts`

```
describe('mergeVoucherRows', () => {
  it('同号不同日 → 两行都保留', ...)
  it('同号同日 → 只保留第一行', ...)
  it('已有行 check1~check5 不被覆盖', ...)
  it('PBT: seq 始终连续且从 1 开始', fc.property(...))
  it('PBT: 输出行数 <= 输入去重后行数', fc.property(...))
})
```

---

## §8 改动文件清单

| 文件 | 改动类型 | 估算行数 |
|------|----------|----------|
| `backend/app/routers/voucher_links.py` | 修改 | +38 |
| `backend/app/services/sampling_registry_service.py` | 修改 | +12 |
| `audit-platform/frontend/src/components/workpaper/composables/useD2VoucherCheckEnhanced.ts` | 修改 | +3 |
| `backend/scripts/fix/fix_sampled_voucher_legacy_identity.py` | 新建 | ~120 |
| `backend/tests/test_voucher_links_ownership.py` | 新建 | ~100 |
| `backend/tests/test_voucher_links_visibility.py` | 新建 | ~100 |
| `audit-platform/frontend/src/components/workpaper/composables/__tests__/mergeVoucherRows.spec.ts` | 新建 | ~60 |
| **合计** | | ~433 |

---

## §9 风险与降级

| 风险 | 概率 | 影响 | 降级 |
|------|------|------|------|
| `_visible_wp_ids` 按底稿逐个调用 `try_gate_wp`，大量底稿时慢 | 低（项目内底稿通常 <200） | 查询延迟 | 如 >50 个底稿，改用批量查询 `project_assignments` 表做一次性可见性判定 |
| SAVEPOINT 在高并发下增加 PG 负载 | 极低（抽凭是低频操作） | 无明显影响 | 无需降级 |
| 存量治理脚本误补全（账套重导后同号对应不同凭证） | 低 | 个别行数据错误 | dry-run 先跑，ambiguous 行不自动补，人工确认 |
| D2 合并口径改后旧的无日期 Excel 数据按空串匹配 | 低 | 空日期行全视为同一张 | 与改前行为一致（空号不入 Set），无退化 |
