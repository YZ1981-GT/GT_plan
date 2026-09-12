# Requirements Document

## Introduction

本 spec 把 **D4 营业收入「主营业务收入明细表 D4-2」** 做实到 `bidirectional_verified`，并借此验证一条尚未被任何 canary 走通的通用能力：**位置数组（positional array）行形态的 cell 映射**。

D 循环已有 5 个 canary（D1/D3/D5/D6/D7）全部 `bidirectional_verified`，它们覆盖的是**字段键行**的四种表结构（单级表头 / 两级表头 nested 账龄 / 两级表头 FLAT 账龄 / 两级表头无账龄普通列分组），共同前提是「一列 ↔ 一个 camelCase 字段」。D4-2 打破这个前提：

- store 行形态 = `{rowId, product, months: [m1..m12], periodTotal, auditAdjustment, priorUnadjusted, priorAdjustment, remark}`（真源 `audit-platform/frontend/src/components/workpaper/composables/useD4RevenueDetail.ts`，`STORAGE_KEY = 'D4-2-rows'`）。**B~M 十二列由 `months` 数组的下标决定，不是字段名**。
- 已做实的 5 个 canary 里，D3/D7 的 nested 是 **dict 键**（`agingPrior/within1`），从未验证 **list index** 作为 json_pointer 分段能否在 extract/materialize 两侧往返等值。
- 前置差异（只读实测，见 `evidence/g5-1-canary-feasibility-and-wave-census.md` §11）：D4 权威模板 `D/D4 收入底稿.xlsx` 有 **46 sheet / 17 外链 / 270 个 `[n]` 公式格**；而 D3/D5/D6 均为 0 个 `[n]` 公式格，D7 仅 6 处且都在非受管 sheet。D4-2 的 N 列本身是 `=SUM(B:M)` **合法内部公式**，与外链公式混在同一批 270 个里。
- **D4-2-rows 有真载荷**（真库实测 2 行 / 最大 1739 B，落 wp_code=D4），不是前三张的空首版。

本 spec 不新建第二条双向路径：它复用 Phase 5 既有八步范式与共享 infra（`ExcelInstrumentationSpec` / `DefinitionPublisher` / `build_excel_adapter` / `published_identity_observer` / Task 76 provisioner / `fix_projection_first_publication`），只补「位置数组」这一形态缺口。

## Requirements

### Requirement 1: 位置数组 cell 映射的往返等值先验证

**User Story:** 作为维护者，我要先证明「list index 作为 cell 映射」在 extract/materialize 两侧往返等值，再动 D4 的发布链，避免把未验证形态直接推到真库。

#### Acceptance Criteria

1. WHEN 契约声明 `json_pointer` 为 `/rows/{row_uuid}/months/0` 形式 THEN `parse_contract` 必须接受该路径且不把 `0` 当 dict 键静默转字符串
2. WHEN 对最小 fixture（1 行 × 12 月）跑 materialize → extract THEN 反读出的 12 个值必须与写入值逐个等值，且 `months` 仍是长度 12 的数组而非 dict
3. WHEN `months` 数组长度 ≠ 12 THEN 必须 fail closed 并给出显式错误，不得截断或补零静默通过
4. WHEN 数组下标越界（如 `/months/12`）THEN 必须打红，不得回落到最后一个元素或 None
5. WHEN 该往返验证未通过 THEN 本 spec 后续任务全部阻塞，不允许对 D4 执行 provisioner/first_publication
6. WHEN 生产链路校验位置数组 THEN 必须通过 `parse_contract → build_excel_adapter → materialize → extract → merge_projection_into_store_rows` 的真实调用链；仅测试 provider 私有 helper 不得解除本阻塞门

### Requirement 2: 270 个公式格的精确净化（区分外链 vs 内部公式）

**User Story:** 作为审计底稿维护者，我要 D4 模板过 OOXML 外链门，但不能误伤 D4-2 的 `=SUM(B:M)` 这类合法内部公式。

#### Acceptance Criteria

1. WHEN 净化前扫描 THEN 必须逐 sheet 分类 270 个公式格：含 `[n]` 外链引用的（可删）vs 纯内部引用的（必须保留），并输出可复核清单
2. WHEN 净化脚本删除公式 THEN 只允许删除**含 `[n]` 外链引用**的 `<f>`，保留其 `<v>` 缓存值；任何纯内部公式（含 `=SUM(B:M)`）的 `<f>` 必须逐字节不变
3. WHEN 净化完成 THEN 受管 sheet `主营业务收入明细表D4-2` 的逐格快照与 merge 范围必须 0 diff，且 N 列公式仍为 `=SUM(B12:M12)` 形态
4. WHEN 净化完成 THEN 真 OOXML 门 `validate_ooxml_artifact(path, document_type='xlsx')` 必须 PASS，且 `.preclean.bak` 必须仍 REJECT（门负例可用）
5. WHEN 净化脚本的判据被变异（改坏净化、只删部件保留 `_rels`、破坏受管格）THEN 每条变异必须打红对应判据（变异检验四态，不得出现 GREEN）

### Requirement 3: 有真载荷的首版发布（非空 projection）

**User Story:** 作为审计师，我要 D4 首版发布带上已有的 2 行真实业务数据，而不是发一个空表把我录的内容冲掉。

#### Acceptance Criteria

1. WHEN wp_code 裁决 THEN 必须以 `D4-2-rows` 的**真实载荷落点**定码（真库实测落 wp_code=D4），不得使用 manifest 的 CamelCase 幻影码
2. WHEN first_publication 现算 projection THEN `row_keys` 必须等于 store 的真实行数（非 0），且每行的 12 个月值必须全部进入 projection
3. WHEN materialize 写入 D4-2 THEN 12 月列必须落在 B~M 对应列，`periodTotal` 由模板 `=SUM` 自算（不得由 projection 覆盖公式列）
4. WHEN roundtrip 校验 THEN `_assert_roundtrip_equivalent` 必须通过；不通过时必须落显式 `blocked_roundtrip_divergence`，禁止降级发布
5. WHEN 首版发布完成 THEN `working_paper_content_representation` 必须出现 generation=1 且 `definition_bundle_id` 与 Task 76 产出的 bundle 一致

### Requirement 4: 八步接线与 §9.6 真栈验证

**User Story:** 作为维护者，我要 D4 与已做实的 5 个 canary 走完全同一条路径，便于统一复核。

#### Acceptance Criteria

1. WHEN 注册 provider THEN `registry.py` 的两处白名单（`_ALLOWED_PROVIDER_MODULES` + `DELIVERED_PER_ENTRY_CONTRACTS`）与 `workpaper_sync_entry_wp_code_adjudication.json` 必须同时登记 D4
2. WHEN 宿主接线 THEN 只有受管 sheet D4-2 走 `WorkpaperSyncEditorHost`，D4 其余 40+ sheet 必须保留既有 dualMode，不得整体切换
3. WHEN OO→HTML 镜像 THEN `oo_to_html.py` 必须为 `d4.revenue_detail` 增加分支，且 12 月数组写回必须保持数组形态（不得被写成 `{"0":..,"1":..}`）
4. WHEN 跑 §9.6 e2e THEN 四条硬断言必须全绿：confirm-descriptor 200 / forcesave `cs_error=0` / checklist 镜像含 marker / 结构化视图 DOM 可见 marker
5. WHEN e2e 通过后查库 THEN 三谓词必须成立：`working_paper_content_application` state=applied、`checklist_responses` 的 `D4-2-rows` 含 marker、`working_paper_content_version` 出现 `source=onlyoffice` 且 `operation_id` 与 e2e 跟踪值逐字一致

### Requirement 5: 46 sheet 大模板的 e2e 稳定性

**User Story:** 作为维护者，我不要一个偶发红的 e2e——D4 模板体积与 sheet 数远超前 5 张，OO 加载更慢。

#### Acceptance Criteria

1. WHEN e2e 等待 OO settle THEN 等待判据必须是**可观测状态**（`data-bridge-state` / confirm-descriptor 200），不得只靠固定 sleep 撑过加载
2. WHEN OO 写受管格 THEN 必须先按 sheet 名精确切到 `主营业务收入明细表D4-2` 并在证据里记录 `activeSheet` 实测值
3. WHEN 写入目标列 THEN 必须选**文本列**（A 列 `product`）而非 12 个数值月列，避免类型不匹配掩盖真实回写
4. WHEN e2e 失败 THEN 证据 JSON 必须保留足以定位的现场（cs_error / store_mirrored / marker_visible 逐条 + `oo_cell_edit_probe`），不得只留一个断言失败
