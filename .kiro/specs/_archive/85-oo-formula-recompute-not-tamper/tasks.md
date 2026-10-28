# 任务：OnlyOffice 重算公式格不再当成篡改

> 需求 / 设计见同目录。标记纪律：`[x]` 必须有代码 + 测试通过证据；外部依赖或待环境如实标 `[ ]*`。

- [x] 1. 公式证据模块 `formula_recompute_evidence.py`（R2.1）—— `test_formula_recompute_evidence.py` 43 passed
  - `formula_signature(text, *, own_row)`：调 `excel_row_shift._rewrite_formula_refs`（只读），本行引用 → `{r}`，原文含哨兵数字串时原样返回
  - `FormulaEvidence` 六类 + `classify_formula_evidence(base, incoming, key)`；`union_formula_signatures(parts)`；同列公式族 `formula_families` / `signature_in_family`；冲突原因文案（无证据时与现有原因逐字相同）
  - 单测：签名表驱动（同行 / `$` / 区间 / 他行 / 跨表 / 字符串字面量 / 结构化引用 / `LOG10(` / 哨兵）、插行前后签名相同、分类六类各一例
  - 模块不 import merge / conflicts（不成为 merge 域消费方）

- [x] 2. 提取产出证据并随 projection 交给合并（R2.2 / R2.3）—— 判据在 `test_formula_recompute_extract_and_store.py`（13 passed，与 4 / 5 同文件）
  - `Projection.formula_signatures`（`compare=False, repr=False`，默认 None）
  - `excel_extract._collect_fields` 在记 `formula_inventory` 处算签名；两个 `extract_projection` 分支挂到 projection
  - `ExcelSyncAdapter._merge_projections` 并上各 binding 签名（单 part 原样返回）
  - 判据（真 D4 world）：签名覆盖 ≥2 个 binding 的键；`projection_canonical_digest` 带签名 = 去掉签名；P9 命中返回的 projection 带同一份签名；Word / store 投影为 None
  - 行数：`excel_extract.py` ≤ 4616、`adapters/excel.py` ≤ 1078

- [x] 3. 合并规则（R1.1~R1.7）—— `test_merge_formula_recompute.py` 21 passed；`test_merge_recomputed_formula_values.py` 修订后通过
  - `FieldVerdict.took_recomputed`，计入 `auto_merged_keys`
  - 受保护分支：R10 之后按证据分类，完好 ⇒ 候选、merged = i；否则按分类写原因的 protected 冲突
  - OO 新增行（`added_by_incoming`）公式字段：签名属同列公式族 ⇒ 候选
  - 输入一致复核：`current_only`（kept_current 且 c ≠ b）、任何冲突、搁置 ⇒ 候选转 protected 冲突（点名第一处差异）/ 新增行候选转 took_incoming
  - 单测：采纳 / 输入不一致三种来源 / 四类篡改 / 无证据（逐字原因）/ 自动取数 / R10 / 遮罩格 / 新增行三种 / 不要求重载 / R1.7「采纳集合 ⊇ 现状采纳集合」性质测试（hypothesis max_examples=5）
  - 修订 `test_merge_recomputed_formula_values.py`：「差一分就是篡改」限定为无证据，文件内写明原判据与改判理由
  - 行数：`merge.py` ≤ 1944；merge 域纯度守卫（task14）保持通过

- [x] 4. 真文件端到端（R1 + R2）—— `test_formula_recompute_extract_and_store.py`
  - 真 D4 world：base = 某 D4-2 行填月份 + `period_total` 缓存值；incoming 分四种 —— 改月份并按公式更新缓存值（OO 重算）/ 公式格敲数字 / 公式改写 / 另加一处服务器侧改动（current ≠ base）
  - 走生产 `adapter.extract`（oo_to_html 方向）+ `merge_projections`：第一种 0 冲突且 period_total 判 took_recomputed，其余三种为 protected 冲突且原因对应

- [x] 5. store 视图与下游（R3）—— `test_formula_recompute_extract_and_store.py`
  - `cleared_field_view.store_view_with_recomputed_formulas` + `RecomputedFieldValue`；`oo_to_html._apply_committed` 在 R17 视图之后套用
  - `template_skeleton_baseline.pure_template_skeleton_rows` 按 mode 跳过公式字段
  - `merge.RETIRED_DEFERRALS` 中 cleared_field_view 那条补第二个函数
  - 判据（真 D2 契约 + 真 D2 store 合并）：采纳重算的 Q/S/AB 写进 store、未采纳不写、发布 projection 不变、骨架行不因重算值进 store、无可换时返回同一对象；AST：镜像拿到的是两层视图后的 `store_view`

- [x] 6. 前端期末余额族对齐（R4）—— `periodEndFromPriorUnadjusted.spec.ts` 16 passed；D 相关 995 个文件失败 36 = 改前 36、G2 / G5 / K1 / D2 相关 514 个文件失败 6 = 改前 6（内存换回改前版本对照）⇒ 新增失败 0
  - D1-2 / D1-3 / D2-2 / D3-2 / D5-2 / D6-2 / D7-2 七张表调用改用期初未审，D1-7「明细账(D1-2)」行同改，D5-2 期末审定改取期末余额；注释同步
  - 触类旁通（实施期补，全仓扫「期初审定作滚动起点」逐个对照模板）：D2-3 / G2-3 / G5-3 / K1-3 坏账准备滚动表与 G2-2 同改，含 G2-3 / G5-3 的合计行与两处跨表读取；真库这五张表 0 条存数
  - 单测：每处一例「期初调整非 0 时期末余额 = 期初未审 ± 发生额」；既有用例若钉住旧口径，改写并注明理由（D3 P5 / D5 P10 / D7 P10 / D6 P10 / D1-3 / D1-2 镜像）
  - design §11 登记其余口径不一致清单（不改）

- [x] 7. 磁盘变异（隔离副本，R5.1）—— 后端 40 条首轮 6 存活，补 6 条判据后全红；P2 比较面 2 条全红；前端 19 条全红（明细见 design §13）
  - 后端：去掉输入一致复核 / 证据分类判反 / 签名不归一 / 全部行号归一 / 适配器漏并兄弟表 / 签名进摘要 / 视图不换值 / 视图换了非公式字段 / 骨架判据回退 / 新增行不查公式族 / auto_merged_keys 漏收
  - 前端：八处任一处退回旧口径
  - 每条须打红，存活的补判据后复跑

- [x] 8. 真实历史冲突重放（真库只读，R5.2）—— 14 次保存 / 297 条现存冲突：复现的 20 条（D4 17、D2 3）新规则下全部采纳、0 冲突，其余 277 条按现行规则本就不再出现（原因见 design §13）；R1.7 全部成立；签名开销 D2 大表 ≈ 1%
  - 每次留下受保护冲突的保存（D2 5 次、D4 9 次）：当时的 base 与 OO 文件，按当前注册的 D2 / D4 适配器重提取（current 取 base），新旧规则各合并一次
  - 记录：新旧冲突数、took_recomputed 数、剩余冲突的原因分布；无法重放的如实写原因；签名计算开销（D2 每次提取）

- [x] 9. 回归（R5.4）—— 后端 junit 逐条对比抓到 1 例新增失败（P2 比较面未覆盖 `formula_signatures`），按根因补比较面 + 判据后为 0；前端三组对照新增 0；golden digest 242 条不变；行数门 0 违规；`check_staged_tree_self_consistency.py` 在提交树上跑（见任务 11）
  - 后端：workpaper_sync 相关测试文件在隔离 worktree 改前 / 改后逐条对比，新增失败 0
  - 前端：七个 composable 的单测 + sync 目录（基线 17 例既有失败）+ 单区域 vue-tsc
  - golden digest、行数门、`check_staged_tree_self_consistency.py`

- [x] 10. 浏览器实测（新建【测试】项目，R5.3）—— 改借方发生 0 冲突、表单 / store / D2-1 为新值；Q 敲数字 3 条受保护冲突；项目已软删、残留对账一致。console 非 0：3 类 error 均不在本次改动的代码路径上（如实登记于 design §13，未用改前代码对照）
  - D2-2 加一行（期初账项调整非 0），表单期末余额按期初未审算；切在线编辑改借方发生 → 保存回表单：application applied、0 冲突，表单 Q/S/AB 与 D2-1 期末未审为新值
  - 再进在线编辑往 Q 敲数字保存 → 受保护冲突；console error 0
  - 结束经平台删除项目，库里残留对账

- [x] 11. 收尾
  - design §13 记录、INDEX.md 本 spec 行（字节保留 CRLF）、memory
  - 删 `C:\Users\Administrator\ofr_probe` 与临时 worktree
  - 只提交本 spec 的文件与改动块，fetch 后从分离头 worktree 推送到当前分支，中文汇报（含 R4 口径确认与 §11 待拍板）
