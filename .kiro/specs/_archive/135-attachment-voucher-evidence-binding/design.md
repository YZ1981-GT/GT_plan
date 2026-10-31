# 设计：抽凭证据绑定（attachment-voucher-evidence-binding）

需求见 `requirements.md`（F 表为现状）。ADR 编号 ADR-AVE-NN；变异编号见 §6。

## 1. 决策

**ADR-AVE-01 凭证证据挂在证据链接上（`evidence_links.voucher_key`），不挂抽凭登记行。** 登记行（`sampled_vouchers`）随撤销抽凭软删、随重抽重建，抽凭与挂凭各一行；凭证键是账套重导后不变的身份（ADR-VK-01）。证据链接已经接入统一视图、可见性隔离（`_linked_wp_ids`）、破坏性守卫（被引用即不能彻底删除）、解除整稿关联连带删除、归档清单 —— 加一列全部继承。样本与证据的对应关系 = 同一底稿内按凭证键连接，不需要外键。否决：新表 `voucher_evidence`（上述五处都要重做）；登记表加附件列（撤销即丢证据）。

**ADR-AVE-02 跨底稿复用 = 引用，不复制，须源底稿可见。** 引用建一条本底稿的凭证级链接（表页、单元格为空），指向源附件。能引用的人本来就能下载源附件再上传，所以不放宽数据访问；引用后看得到本底稿的人也看得到这份附件，这是引用人有意把它作为本底稿证据。否决：同一凭证的证据自动对全项目可见（破坏底稿可见性隔离）。

**ADR-AVE-03 入口放在「来源」列。** `VoucherRowMetaCell` 已经由 76 个文件渲染、拿得到行（`_gt.vk`）与项目；底稿 id 与只读从 `WorkpaperRuntimeContextKey` 注入取。改一个组件覆盖全部宿主，不逐宿主加列。

**ADR-AVE-04 行内识别带凭证键靠共享函数的第四个参数。** `appendRowEvidence(form, sheet, cell, row?)` / `useRowEvidence().append(…, row?)` / `buildLinkedOcrFormData(…, { voucherKey })`：行带 `_gt.vk` 时追加表单字段 `evidence_voucher_key`。识别端点经依赖 `ocr_intake_options` 收字段，26 个识别路由与按单据类型识别路由不必逐个改签名。不在 http 拦截层按行 id 反查凭证键（行 id 字段名各宿主不同，K1 还带表前缀）。

**ADR-AVE-05 带凭证键的缺省证据类型是「凭证 / 原始单据」。** 显式传了类型照用；否则不再按底稿声明或端点本循环类型取（F7 的 F1 记成函证）。

**ADR-AVE-06 声明口径不变，逐笔统计只展示与归档非阻断。** 凭证检查的审计证据是检查行上的核对记录，影像留档是补强；函证不同（缺回函且没做替代程序 = 程序没完成，Spec C 因此逐笔判满足）。逐笔统计用新键 `samples`，不复用函证的 `breakdown`（归档完整性与抽屉按 `breakdown` 当函证处理）。是否改为逐笔全满足（会让 D2 / D3 的 QC-17 阻断）待拍板。

**ADR-AVE-07 他稿查询放在项目级端点。** 底稿统一门按 HTTP 方法判读写，挂在底稿路由下的 POST 查询会被当成写（复核人 404）；键里有中文主体名，500 个键放进查询串超长（与 `voucher-links/query` 同因）。端点放在序时账路由组 `POST /api/projects/{pid}/ledger/voucher-evidence/query`（项目 readonly），逐张底稿过 `try_gate_wp(attach_read)` 只留可见的；本底稿已有的链接仍走底稿证据列表（共享仓，单飞）。

**ADR-AVE-08 序时账凭证层不改 `LedgerPenetration.vue`。** 该文件 5257 行，超白名单 4682 的 5%，碰即被行数门拒。凭证层模板调的是 `useVoucherLinkTags().linksOfKey(凭证键)` ⇒ 在这里并入凭证证据（来源为「凭证证据」的条目，经凭证证据索引按需查），`VoucherLinkTags` 照常渲染。明细层 📎（`flagOfRow` / `linksOfRow`）不并入：逐行查证据会让明细层查询翻倍。

## 2. 数据（迁移 V{n} / R{n}，实施时现扫取号）

```sql
ALTER TABLE evidence_links ADD COLUMN IF NOT EXISTS voucher_key TEXT;
CREATE INDEX IF NOT EXISTS idx_evidence_links_voucher_key ON evidence_links (voucher_key) WHERE voucher_key IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_evidence_links_voucher_position ON evidence_links
  (wp_id, voucher_key, attachment_id, COALESCE(sheet_name, ''), COALESCE(cell_ref, ''))
  WHERE voucher_key IS NOT NULL;
```

唯一索引带位置：按序号挂附件的表删行时「先建新位置、再删旧位置」（`shiftIndexedRowEvidence`），只按（底稿, 凭证, 附件）去重会让新位置撞上旧位置。ORM `EvidenceLink.voucher_key: Mapped[str | None]`（Text）。R{n} 删两个索引与列。真库 0 行，不回填。

凭证键校验：`VoucherKey.from_str`，凭证号非空、日期可解析，存规范串（`to_str()`），超过 600 字 400。

## 3. 接口

| 接口 | 改动 |
|---|---|
| `POST /api/projects/{pid}/workpapers/{wp}/evidence/upload` | 表单加 `voucher_key` |
| `POST …/evidence/link`、`…/batch-link` | 请求体加 `voucher_key`（附件仍须已在本底稿） |
| 识别端点（经 `ocr_intake_options`） | 表单加 `evidence_voucher_key` |
| `GET …/evidence` | 每条链接带 `voucher_key` |
| `POST …/evidence/voucher-reuse`（新） | `{voucher_key, attachment_id}` → `{link, existed}`；本底稿 edit + 统一门写 + 归档 423；源 = 同项目另一张未删底稿上同凭证键的链接、附件未删、`try_gate_wp(attach_read)` 放行，否则 404；证据类型取源链接的，源为空记 voucher |
| `POST /api/projects/{pid}/ledger/voucher-evidence/query`（新） | `{year, keys ≤500}` → `{evidence: {凭证键: [{working_paper_id, wp_code, wp_name, attachments: [{id, file_name, file_type, ocr_status, evidence_type}]}]}}`；年度不符的键丢弃；超过 500 个 422 `TOO_MANY_VOUCHER_KEYS` |
| 底稿统一视图 / 声明 | `evidence_positions[]` 加 `voucher_key`；「凭证」类声明加 `samples: {total, with_evidence, missing, missing_items[{voucher_key, label, phase, source}], truncated}` |

服务：新模块 `services/voucher_evidence.py` —— 凭证键校验、他稿查询、引用、逐笔样本统计（登记样本按凭证键去重；旧登记没记主体或凭证字的列按通配比，与 `voucher-links/query` 同口径；没记日期的登记列为缺证据并注明「旧登记缺日期」）、归档章节用的样本证据清单。`EvidencePosition` 加 `voucher_key`，`is_row_level` 认它；`create_evidence` / `WpEvidenceService.create_link` 透传并按唯一索引幂等（先查、撞索引时回读已有）。

## 4. 前端

| 文件 | 改动 |
|---|---|
| `components/workpaper/voucher-sampling/VoucherEvidenceTag.vue`（新） | 「来源」列里的凭证证据：本底稿份数 + 弹出列表（小眼睛预览、移除）+ 上传 + 他稿提示与引用；只读 / 锁定行只读 |
| `VoucherRowMetaCell.vue` | 行带 `_gt.vk` 且有运行时上下文时渲染上面的组件 |
| `composables/useVoucherEvidenceIndex.ts`（新） | 他稿证据仓：按（项目, 年度）缓存；同一时刻登记的键合成一次请求（≤500 分段）；引用 / 上传后只重查这几个键；晚到的旧响应不覆盖 |
| `composables/useWpEvidenceLinks.ts` | 链接类型加 `voucher_key`；`linksOfVoucher(vk)` |
| `components/attachment/workpaperEvidence.ts` | 上传带 `voucherKey`；位置标签按凭证键显示「凭证 FY-0003（2025-01-07）」 |
| `components/attachment/rowEvidence.ts` | `appendRowEvidence` / `useRowEvidence().append` 第四参数行；`rowVoucherKey(row)`；`shiftIndexedRowEvidence` 保留凭证键 |
| `components/workpaper/composables/ocrAttachmentLinkage.ts` | `buildLinkedOcrFormData` 透传 `voucherKey` |
| `ItemAttachment.vue` | 新 prop `voucherKey`，上传时带上；F1 / F3 / F4 凭证检查弹窗传行的凭证键 |
| 凭证检查宿主的行内识别 / 上传（约 30 个文件） | 调用共享函数时把行传进去 |
| F6 的 6 个文件 | 接行内位置（表页 = 本页编码、`row:{行 id}`）、小眼睛、凭证键；豁免清单删 6 条 |
| `h1/stocktake/H1TabStocktakeSummary.vue`、`h1StocktakeSummaryEnhance.ts` | 差异证据行带 H1-10 行 id，「照片」列改小眼睛 |
| `WorkpaperAttachmentsDrawer.vue` | 「凭证」类声明下显示逐笔统计与缺证据样本 |
| `views/ledger/useVoucherLinkTags.ts`、`VoucherLinkTags.vue` | 证据条目（来源「证据」，标签「D2-4 · 凭证证据 2 份」） |

## 5. 权限

| 操作 | 编制人 / 经理 / 合伙人 | 复核人（底稿只读） | 非成员 |
|---|---|---|---|
| 查看本底稿凭证证据、他稿提示 | 允许 | 允许 | 403 |
| 上传、移除、引用 | 允许 | 404（统一门） | 403 |
| 他稿查询 | 只列自己可见的底稿 | 同左 | 403 |
| 归档项目上的写 | 423 | — | — |

## 6. 守卫与变异

前端守卫 `__tests__/VoucherEvidenceKeyGuard.spec.ts`：扫描范围 = 凭证检查宿主（渲染 `VoucherRowMetaCell` 或调 `useVoucherCheckFill` 的文件）及其直接引用的组件 / 组合式函数；其中调用 `appendRowEvidence(` / `rowEv.append(` / `buildLinkedOcrFormData(` / `uploadWorkpaperEvidence(` 的语句须带行（第四参数）或 `voucherKey`；`<ItemAttachment` 须带 `voucher-key`。豁免 `voucherEvidenceKeyExemptions.json` 只许删、条目须确实违规、带可核对的 `verify`；扫描器自检（合成违规源码须被抓到，扫描面不得塌缩）。

| # | 变异（磁盘注入，逐字节恢复） | 预期红 |
|---|---|---|
| 1 | `build_position` 不认 `voucher_key`（不算行级） | 带凭证键只写链接用例 |
| 2 | 凭证键不校验 | 格式错 400 用例 |
| 3 | 带凭证键仍按声明取缺省类型 | F1 缺省类型用例 |
| 4 | `create_link` 不幂等 | 重复上传 / 引用只一条用例 |
| 5 | 引用不校源底稿可见 | 不可见源 404 用例 |
| 6 | 引用不校同凭证 | 凭证键不符 404 用例 |
| 7 | 他稿查询不过可见性 | 不可见底稿不列用例 |
| 8 | 他稿查询不排除已删附件 | 已删附件不列用例 |
| 9 | 声明不看链接证据类型 | 引用附件满足声明用例 |
| 10 | 逐笔统计不按凭证键去重 | 两批抽到同一凭证计一笔用例 |
| 11 | 归档章节不列缺证据样本 | 章节文本用例 |
| 12 | `appendRowEvidence` 忽略行 | 共享函数单测 + 守卫 |
| 13 | 他稿仓逐键发请求 | 合批用例 |
| 14 | 证据标签对锁定行显示写操作 | 只读用例 |
| 15 | `shiftIndexedRowEvidence` 丢凭证键 | 移位用例 |
| 16 | 守卫扫描器只认 `appendRowEvidence(` | 扫描器自检 |

## 7. 测试

后端新目录 `backend/tests/attachment_voucher_evidence/`：`test_voucher_key_position.py`（校验、缺省类型、只写链接、幂等）、`test_voucher_reuse.py`（引用：可见性、同凭证、归档 423、统一门）、`test_voucher_evidence_query.py`（他稿查询：可见性、已删附件、年度、500 上限）、`test_voucher_samples.py`（逐笔统计、声明类型、归档章节与完整性）、`test_voucher_evidence_pg.py`（唯一索引、移位不撞索引、查询计划）。前端：`VoucherEvidenceTag.spec.ts`、`useVoucherEvidenceIndex.spec.ts`、`rowEvidence.spec.ts` 补用例、守卫。

## 8. 实施记录

在远端线候选树（分离头 worktree `tmp_attachment_spec_b/remote_wt`）上实施：先在 `434e87972` 上做完与验证，提交前换到 `a7aebb935`（远端新增的 4 个提交与本 spec 没有同名文件）。改动 99 个文件：后端代码 10（新 1）、迁移 2、后端用例 8（新 7）、前端代码 68（新 2）、前端用例与清单 11（新 4）。

### 8.1 落地要点

- 迁移 **V230 / R230**：V227~V229 已被并发工作树 `tmp_formula_suite/wt` 的未推送迁移占用，取 230；55 个远端分支都没有 V227 以后的迁移。两个索引只写在迁移里，ORM 只加列。共享开发库已执行 V230（只放这一个文件的独立目录 + 与启动同一路径的 `MigrationRunner`，不顺带别人待执行的迁移）。
- 后端：新模块 `services/voucher_evidence.py`（凭证键规范化、他稿查询、引用、逐笔样本统计、归档章节清单）；`workpaper_evidence_intake`（`EvidencePosition.voucher_key`、`build_position`、带凭证键的缺省类型）、`wp_evidence_service`（按唯一索引幂等）、`routers/wp_evidence.py`（表单 / 请求体收凭证键，`POST …/evidence/voucher-reuse`）、`routers/voucher_links.py`（`POST …/ledger/voucher-evidence/query`）、`attachment_wp_view`（位置带凭证键、`samples`）、`workpaper_evidence_requirements`（链接类型参与判定）、`archive_completeness_evidence`、`archive_generators/sampling_records_generator`。
- 逐笔统计的样本在 Python 里排序（有日期的按日期、凭证号在前，旧登记缺日期的排最后）：PG 与 SQLite 的 NULL 排序方向相反，交给 SQL 会让两个库结果不同。
- 前端：新 `VoucherEvidenceTag.vue`、`useVoucherEvidenceIndex.ts`；改 `VoucherRowMetaCell`、`useWpEvidenceLinks`（`voucher_key`、`voucherEvidenceOf`）、`workpaperEvidence.ts`（上传带 `voucherKey`、`voucherKeyLabel` / `splitVoucherKey` / `voucherKeyYear`）、`rowEvidence.ts`（第四参数、`rowVoucherKey`、移位保留凭证键）、`ocrAttachmentLinkage`、`ItemAttachment`（`voucherKey`）、抽屉、序时账 `useVoucherLinkTags` / `VoucherLinkTags`；凭证检查宿主 58 个组件文件按「调用共享函数时把行传进去」改（脚本按调用形态分批改，余下手改）。
- 守卫 `VoucherEvidenceKeyGuard.spec.ts` 14 例：现算范围宿主 80、扫描文件 361、含行内识别 / 上传调用的 47（下限 72 / 320 / 42，防扫描面塌缩）；豁免 3 条。

### 8.2 偏离设计与实施中的发现

1. 标签不收年度：年度取凭证键自带的年度（`voucherKeyYear`），`VoucherRowMetaCell` 不再传 `year`。13 个宿主给「来源」列传 `year ?? 0`，按传入年度查，后端以年度不符把键全部丢掉，「他稿已有」恒不出现（变异 D17 钉住）。否决：改用运行时上下文的年度（凭证键才是这张凭证的身份，两者不一定同年）。
2. 取凭证证据的函数叫 `voucherEvidenceOf(vk)`，按附件分组返回（同一附件在本行与凭证级各有链接时算一份），不是 §4 的 `linksOfVoucher`。
3. 位置标签写「凭证 2025-03-15 记-0012」，与缺证据样本清单、归档章节同一写法（日期在前，凭证字-号与序时账一致），不是 §4 的「凭证 FY-0003（2025-01-07）」。
4. 他稿查询用例并入 `test_voucher_reuse.py`（与引用共用场景），没有单独的 `test_voucher_evidence_query.py`。没写查询计划用例：真库 `evidence_links` 0 行，小表上规划器一律顺序扫描，断言走索引只能关掉顺序扫描硬凑，证明不了真实负载；唯一索引的行为由 `test_unique_index_allows_other_position_only` 覆盖。
5. 守卫范围比 §6 宽：宿主 + 宿主的父组件以 `:row=` 渲染的兄弟组件（`rowReceivers`，逐笔核对弹窗）+ 一层直接引用。只看宿主及其直接引用时，F3 / F4 凭证检查弹窗里没带行的 `appendRowEvidence` 扫不到（弹窗不是宿主的直接引用，由宿主的父组件渲染）；扩范围后抓到，改成 `appendRowEvidence(…, props.row)`。另加两条规则：位置对象 `{sheet, cell}` 作参数传出时须带 `row`（`return {…}` 不算）；`runWorkpaperOcr` 算行内识别调用。规则按语义判：没有单元格的表页级调用不要求凭证键，所以不按文件豁免。
6. 豁免 3 条，全是不在行上的附件槽位（`item-attachment`）：F1SheetAttachments、F2TabContractCostCheck 的 F2-56 槽位 1、F5SheetAttachments；每条用 `itemAttachmentOutsideRows` 核对（槽位实际绑了行就报出，变异 D20）。
7. 就地预览留下的 6 个文件：D1 / D4 凭证检查（表页 `D1-13` / `D4-14`）、D3（组合式函数、弹窗、表格共用导出的 `D3_7_EVIDENCE_SHEET` / `d3VoucherEvidenceCell(section, rowId)`）、D2 凭证识别核对（`D2_7_EVIDENCE_SHEET`，`useD2VcOcrCheck` 加可选 `projectId`）；E1 银行流水核对（对账单是整页附件）与 E1 大额收付（识别后才建行）用表页级位置 + 表页级小眼睛，不带凭证键。`attachmentEyeExemptions.json` 11 → 5。
8. H1 盘点汇总：`buildDiffEvidence` 原本就带 H1-10 行 id，`h1StocktakeSummaryEnhance.ts` 未改；「照片」列删去 `<a :href="photoUrl">`，手填文字按普通文字显示 + 行内小眼睛；`NativeLoadBearerGuard` 登记里 H1 `row.photoUrl` 一条随之删去（守卫要求删失效登记）。
9. tasks 9 原写「凭证层与明细层带证据」，与需求 7.1 / ADR-AVE-08（明细层照旧）不一致；按后两者实施，tasks 9 写法已改。
10. 收尾核对发现 §5 权限表的「非成员」「复核人」两列没有端点级用例，补 `test_query_and_reuse_require_membership`（非成员查询 / 引用 403 / 403；只读成员查询 200、引用 403）与 `test_reuse_by_role`（真 PG + 生产注册参数：负责人 200、编制人 200、复核人 404 且统一门记一次 `action_denied`），变异 D29~D31。
11. 受影响的既有用例与登记：`test_wp_attachment_view.py` 的位置期望加 `"voucher_key": None`；`components.d.ts` 加 `VoucherEvidenceTag` 一行（走查开发服务器重生成的其余 El* 增删未带入）。
12. 已知现象（未改）：本底稿证据列表加载完成前，「来源」列标签先显示为可上传的空状态，加载完变为份数；走查「移除」一步首读即遇到。

### 8.3 变异（磁盘注入；CRLF 文件按运行器口径归一后比；逐字节复原 + sha256；32 / 32 红，复原后原文都在）

| # | 变异 | 红的用例 |
|---|---|---|
| D1 | 带凭证键不算行级 | 位置与缺省类型、带凭证键只写链接 |
| D2 | 凭证键不校验 | 规范化、格式错 400 |
| D3 | 带凭证键仍按声明取缺省类型 | 缺省类型三例 |
| D4 | 凭证链接不幂等 | 重复建链接、重复引用 |
| D5 / D6 | 引用不校源底稿可见 / 不校同凭证 | 引用 404 三例 |
| D7 / D8 | 他稿查询不过可见性 / 不排除已删附件 | 只列可见底稿（含真 PG）、已删附件不列 |
| D9 | 声明不看链接证据类型 | 引用附件满足声明 |
| D10 | 逐笔统计不按凭证去重 | 两批抽到同一凭证计一笔 |
| D11 / D11b | 归档章节 / 完整性不列缺证据样本 | 章节文本、证据缺口 |
| D12 | `appendRowEvidence` 忽略行 | 共享函数两例 |
| D13 | 他稿仓逐键发请求 | 合批 |
| D14 | 标签对锁定行显示写操作 | 只读 |
| D15 | 移位丢凭证键 | 移位 |
| D16 | 守卫只认 `appendRowEvidence(` | 扫描器自检 |
| D17 | 他稿查询用宿主传的年度 | 本底稿按附件计数（年度 0 时他稿为空） |
| D18~D21 | 守卫漏看兄弟弹窗 / 不查位置对象 / 豁免核对恒通过 / 不查识别选项 | 扫描器自检各一 |
| D22 / D23 | 凭证层不并入证据 / 明细层也查证据 | 序时账标签 |
| D24 | 抽屉不显示逐笔统计 | 抽屉 |
| D25 / D26 | 他稿查询不看年度 / 不限键数 | 年度不符丢弃、超 500 个 422 |
| D27 | 逐笔统计改用函证的 `breakdown` 键 | 声明带 `samples` |
| D28 | 统一视图位置不带凭证键 | 统一视图位置 |
| D29 / D30 | 引用端点只要求只读 / 他稿查询不校项目成员 | 鉴权 |
| D31 | 引用端点漏过底稿统一门 | 只红复核人一格（负责人 / 编制人照旧 200） |

§6 计划的 16 条即 D1~D16。D31 首版写成「统一门把 POST 当读」，红在负责人 / 编制人两格（读动作配 POST 被拒），没红复核人，形态不对；改成上表写法后只红复核人。

### 8.4 回归与门禁

- 本 spec 后端用例 21 例 + `test_wp_attachment_view.py` 4 例全过（含真 PG 5 例）。
- 相关后端用例：候选树 49 个文件 717 过 / 2 红，基线树 45 个文件（少本 spec 新增的 4 个）701 过 / 1 红。共同红 `test_settings_patch_isolation[dsh_agent_panel/test_task30_capabilities]`；只在候选红的 `test_wp_attachment_view` 是位置期望要加 `voucher_key`，已改，复跑通过。
- 相关前端 141 个 spec（基线 138，少本 spec 新增的 3 个）：只在候选树红 2 条（`NativeLoadBearerGuard` 失效登记已删；`noteHeadlessProviders` 负载下加载超时，单跑通过）；基线另有 46 条红、候选同一批通过（全仓扫描类守卫为主，未逐条查因；方向是基线更红，不会掩盖本 spec 的红）。换到新基线后复跑本 spec 相关 11 个 spec 共 126 例全过。
- 单区域 vue-tsc：候选 99 = 基线 99，新增 0；注入 `number = string` 后两个新文件报 TS2322（101）。ESLint 76 个文件 271 = 271。行数门 95 个代码文件 exit 0。ruff 18 个后端文件通过。
- 治理脚本候选对基线：除领域边界外逐项相同。领域边界在基线已红（649 条新增身份），候选 670，多 21 条：后端 3 条（`workpapers` / `import-export` 引用 `services/voucher_evidence.py`，被判 `backend-services`），前端 18 条（凭证检查宿主引用 `components/attachment/` 的 `rowEvidence.ts` / `RowEvidenceEye.vue` / `AttachmentEyeButton.vue` / `workpaperEvidence.ts`，判 `workpapers → evidence`）。没改 `docs/architecture/domain-boundaries.json` 与基线（文档禁 `--write-baseline`；给模块改名只是挪违规），列待拍板。

### 8.5 走查（候选树后端 9988 + 前端 3038 + 独立无头浏览器；【测试】抽凭证据绑定走查_2025）

数据：D2 / D4 两张底稿，序时账 6 行；凭证 0012 挂到 D2 与 D4，0025 只挂 D2。

1. 挂凭导入：D2-7 4 行（两张凭证按对方科目拆行，与配对结果一致），D4-14 1 行，「来源」列都有凭证证据标签。
2. 上传：D2 凭证 0012 上传原件 200，标签「已有证据 1 份」，链接带凭证键、类型「凭证」。
3. 引用：D4 同一凭证的面板显示「其他底稿已有 D2 voucher_evidence.png」，引用 200，附件 id 与 D2 相同（不复制文件）。
4. 抽屉：D2「✓ 记账凭证/原始单据影像」下「登记抽凭样本 2 笔：已取得凭证证据 1、缺 1」，缺 2025-05-20 记-0025。
5. 只读：同一用户第二个标签页打开 D4（多窗口编辑锁强制只读）：面板只有小眼睛，没有上传 / 移除 / 引用，提示「只读：可查看，不能上传或移除」。
6. 归档：向导完整性「证据缺口 2 项」，D2 一行「1 笔抽凭样本未取得凭证证据（共 2 笔）：2025-05-20 记-0025」（D4 一行是既有的合同影像声明）。「06-抽样记录汇总」按走查数据只读生成（事务回滚；不跑归档作业，免得锁项目）：「抽凭样本证据」列出 D2 2 笔、D4 1 笔，证据文件 `b285d7a6 voucher_evidence.png` 与缺证据样本。
7. 序时账凭证层：凭证 0012「已挂底稿」= D2 挂凭、D4 挂凭、D2 凭证证据 1 份、D4 凭证证据 1 份；0025 只有 D2 挂凭。走查数据没有生效数据集，明细层窗口账簿 409（`LEDGER_ACTIVE_DATASET_REQUIRED`，平台既有口径），凭证层经穿透深链进入。
8. 移除：D4 移除引用来的证据（确认框写明只移除本底稿的链接）⇒ D4 0 条、D2 仍 1 条，D4 标签变为「他稿 1」。

各步页面报错 0；截图在 `tmp_attachment_spec_b/shots/d_*.png`（不入库）。

### 8.6 清理与对账

平台路径：取消挂凭 3 条 → 删证据链接 → 解除整稿关联（不存在的关联 no-op 200）→ 删除附件 → 回收站彻底删除（`file_cleanup.deleted=1`）→ 删项目（软删）；按 id 删走查插入的试算表 / 余额表 / 序时账 3 / 3 / 6 行。对账：附件 0、整稿关联 0、证据链接 0（全库带凭证键的 0）、挂凭未软删 0（软删 3 条随项目在回收站）、底稿 2 张与检查表 6 行随项目软删保留、项目附件目录 0 个文件、主树 storage 无该项目目录。走查服务已停，拷进候选树的 `vite.wt.config.ts` 已删。

### 8.7 待拍板

- 领域边界清单：`workpapers.may_depend_on` 是否加 `evidence`；`services/voucher_evidence.py` 归哪个领域。
- 「凭证」类声明是否改为每笔样本都要有证据（会让 D2 / D3 的 QC-17 阻断，ADR-AVE-06）。
