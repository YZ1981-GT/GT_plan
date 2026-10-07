# 设计：公式推送全科目接入

> 需求见 requirements.md。本设计**不新增第五套公式系统**：求值仍走 `formula_engine.execute`（L1 单内核），
> 推送编排仍是 `formula_push.engine`，规则仍登记在 `formula_push_rules.json`，界面仍是公式管理「📤 公式推送」页签。
> 本 spec 只做两件事：把引擎从「E1 专用」改成「按科目注册」，并按底稿形态分族铺开。

## 一、分层与边界

```
                  ┌──────────── 公式管理（唯一入口 F-SHELL，已交付） ────────────┐
                  │  编辑 / 查看：wp_formula · 预设库 · prefill_formula_mapping   │  ← L0 / L1（不改）
                  │  📤 公式推送页签：规则 · 最近运行 · 差异 · 试跑 / 推送 / 采用   │  ← 本 spec 改：按科目隔离
                  └───────────────────────────────────────────────────────────────┘
 事件（TB 重算 / 调整审批 / 底稿保存 / 手动）
        │
        ▼
 formula_push.triggers ──► engine.run(project, year, trigger, codes?, wp_id?)
                               │  对每个「相关」主编码：
                               ├─ binding.load_sources(strict)        ← 科目差异只在这里
                               ├─ binding.workpaper_targets(rule)     ←
                               ├─ binding.apply(overlay, target)      ←
                               ├─ policy.decide（三态，通用）
                               ├─ WorkpaperMutationAdapter CAS（通用，整张底稿一个保存点）
                               ├─ note_writer（通用，按规则声明的章节 / 表 / 字段）
                               └─ formula_push_state / run + SSE formula.pushed（通用）
```

科目差异**只允许**出现在 binding 模块与规则清单里；引擎、触发器、面板、写入适配器、附注写入器、前端提示条与独占键过滤都是通用代码，新增科目零改动（需求 5.6）。

## 二、binding 协议（正式化现有鸭子类型）

现状：`E1Binding` 是鸭子类型，引擎靠调用约定使用它。本 spec 把约定写成 `Protocol` 并加注册时校验（`register_binding` / 模块导入期），否则第二个科目接入时只能靠运行时报错发现缺方法。

```python
class PushBinding(Protocol):
    wp_code: str                          # 主编码，与注册表键一致
    account_prefixes: tuple[str, ...]     # 触发相交判定（已有）
    derivations: frozenset[str]           # 本 binding 实现的派生名（已有）
    four_table_slots: frozenset[str]      # 新：本 binding 认的四表槽名（取代全局 FOUR_TABLE_SLOTS）
    tb_columns: frozenset[str]            # 新：本 binding 的试算表上下文会装载的列（需求 5.4）
    paper_codes: tuple[str, ...]          # 新：要推的底稿编码，缺省 (wp_code,)；分册见 §3.3

    async def load_sources(self, db, project_id, year, wp_id) -> Any: ...      # 必须 strict
    def workpaper_targets(self, rule, overlay, sources) -> tuple[list[WorkpaperTarget], list[TargetSkip]]: ...
    def apply(self, overlay, target, value) -> bool: ...                        # 返回存储值是否改变
    def note_rows(self, overlay, template_type, rule) -> list[dict]: ...        # 新增 rule 参数（多附注表）
    def entry_warnings(self, overlay) -> list[str]: ...
```

- `note_rows` 增加 `rule` 参数：一个科目可能有多条附注规则（多张表）。E1 只有一条，按签名适配即可，行为不变。
- `four_table_slots` / `tb_columns` 供规则校验按 binding 校验（需求 5.1、5.4），取代 `rules.FOUR_TABLE_SLOTS` 全局常量。
- 注册时校验：`isinstance(binding, PushBinding)`（`runtime_checkable`）+ 属性非空 + `wp_code` 等于注册键。

### 2.1 族 binding（需求 7.2 批 C / D）

同族科目共用一个实现类、按科目规格实例化，SHALL NOT 每科目复制一份：

```python
class BalanceAdjudicationBinding:           # 资产负债类审定表族
    def __init__(self, spec: KCycleSpec | ...): ...

_REGISTRY = {
    "E1": "app.services.formula_push.bindings.e1:E1Binding",
    "K1": "app.services.formula_push.bindings.k1:K1Binding",
    "K2": "app.services.formula_push.bindings.families.balance:binding_for('K2')",   # 族 binding 工厂
    ...
}
```

注册表值允许「模块:工厂(参数)」形态由 `_factory` 解析，或直接登记可调用对象；判据仍是「注册表是唯一清单」。

## 三、触发正确性（需求 2）

### 3.1 防抖合并丢事件（S14、S22）

实测：`EventBus.publish` 的去重键是 `事件类型:项目:年度`，500ms 内两张底稿保存只派发最后一张。合并逻辑只合并 `account_codes`，而 `WORKPAPER_SAVED` 的身份在 `extra`（`wp_id` / `wp_code` / `item_ids` / `publish_confirmed`），被后一个事件**整体覆盖** ⇒ 这不是推送独有的问题：

- 现扫 19 处 `WORKPAPER_SAVED` 订阅（跨行容忍的字面量口径）对被覆盖的那张底稿全部不执行（一致性比对、stale 传播、附注过期、循环联动 …）。
- 「发布到试算表」的确认事件也走这条路（S22）：被随后的条目保存覆盖后，试算表回写 handler 根本收不到确认，端点却已返回成功。

| 方案 | 做法 | 裁定 |
|---|---|---|
| A | 去重键对携带 `extra.wp_id` 的事件加入 `wp_id`、对携带 `extra.publish_token` 的事件加入 `publish_token`（同一底稿的连续保存、同一确认的重复提交仍合并） | **采纳** |
| A' | 发布门端点改用 `publish_immediate` | 否决作主修：只修一个发布点，且把试算表重算 + 报表 + 推送整条级联拉进 HTTP 请求内同步执行；A 已覆盖该场景 |
| B | 只让推送绕开：推送改订阅不防抖的通道 | 否决：其余订阅与发布确认继续丢事件，是绕开不是修复 |
| C | 推送 handler 收到事件后再查「最近有保存的已接入底稿」补推 | 否决：同上，且多一次查询掩盖根因 |

A 不引入新的事件形态：两张底稿保存间隔超过 500ms 时，订阅者本来就各收一次；A 只是去掉「间隔小于 500ms 时前一个事件被吞」这一意外。发布确认的幂等仍由 `tb_publish_ack`（`ON CONFLICT (publish_token) DO NOTHING`）保证，与去重键无关。

变更前清单（需求 2.1）：Task 1 列出 19 处订阅，逐个确认「同一窗口内收到两张不同底稿的事件」无害（预期只有计算量增加），结论写进 tasks 证据栏；同时现扫其余带 `extra.wp_id` / `publish_token` 发布的事件类型（现扫得 `WORKPAPER_ASSIGNED`），一并列入。

> 🔴 顺序约束：K1 现在的独占键过滤**恰好**挡住了「发布后立即保存审定合计」那次请求，所以 K1 的发布确认眼下不会被吞；Task 2 取消过滤会让它复现。⇒ Task 1（本节修复）必须先于 Task 2 合入。

### 3.2 事件缺 `wp_code`（S15）

推送触发器在 `extra.wp_code` 缺失时按 `extra.wp_id` 反查 `wp_index.wp_code` 取主编码（A13 handler 已有同类兜底，复用其查询形态）。**不**改 `after_save` 的载荷：给载荷补 `wp_code` 会让 C/F/D/B/H/I 等十余个按 `wp_code` 分支的 handler 开始响应 HTML / OnlyOffice 保存，属行为变化，不在本 spec 范围（记入「后续」）。

### 3.3 子码归并与相关性

- `wp_code` → 主编码：`^([A-Z]\d+)`（`K1-1` → `K1`）。不在注册表的主编码直接返回。
- 推哪张底稿：引擎现按主编码找底稿（`_find_workpapers`，一个项目一个编码至多一张）。真库有 1214 张子码分册底稿，少数科目把条目写在分册上（S20）。⇒ binding 增加可选声明 `paper_codes`（缺省 = 只认主编码），canary 前按需求 2.3 现查条目落点后填写；声明了分册的，引擎按「主编码 + 分册编码」找底稿，每张一个保存点。
- `TRIAL_BALANCE_UPDATED`：只跑 `account_prefixes` 与事件科目相交的 binding（现状已按前缀判断是否跑，但一旦跑就跑全部 binding ⇒ 改为把相交的主编码集合传进 `engine.run(codes=…)`）。
- `WORKPAPER_SAVED`：只跑该底稿的 binding（现状已如此，保持）。

### 3.4 失败隔离到底稿级（需求 2.4）

现状：任一 binding 的 `load_sources` 抛错 ⇒ 整次运行回滚并记 failed。多科目后一个科目的取数故障会拖垮全部科目。

改为：每张底稿一个保存点（`_write_entries` 已有底稿级保存点，扩到「取数 + 写入 + 附注」整段），取数失败 ⇒ 该底稿零写入、结果记 `status=failed` + 中文原因，其余底稿照常；整次运行状态 = `partial`。**strict 语义不变**：失败仍不降级为 0，只是失败范围收窄到底稿。

> 🔴 PG 事务坑（memory 铁律）：PG 里一条语句失败会让整个事务 aborted，后续语句全挂、COMMIT 等价 ROLLBACK。取数失败若发生在保存点之外，「其余底稿照常」就是假的。⇒ 取数必须在该底稿保存点**之内**执行，异常后先 `rollback` 到保存点再继续下一张；测试必须真 PG（一次性 schema）跑「第一张取数抛 SQL 错 ⇒ 第二张照常写入」，SQLite 不作数。

## 四、面板按科目隔离（需求 3）

| 接口 | 变更 | 兼容 |
|---|---|---|
| `GET /states?year=&wp_code=` | 新增可选 `wp_code`，按 `rule_id` 前缀 `{code}.` 过滤 | 缺省 = 全部（旧行为） |
| `GET /latest?year=&wp_code=` | 新增可选 `wp_code`：返回最近一次**涉及该底稿**的运行，`detail.wp` 只保留该段 | 缺省 = 旧行为 |
| `POST /run` body `{year, dry_run, wp_codes?}` | 新增可选 `wp_codes`；传入时只推这些主编码 | 缺省 = 全部 |

- `formula_push_state.rule_id` 已带主编码前缀（`E1.tb_amount.ending`），过滤不需要新列；`formula_push_run` 的「涉及哪些底稿」在 `detail.wp` 里（JSONB），按 `wp_code` 过滤用 JSONB 包含查询，PG/SQLite 两套写法，SQLite 走 Python 侧过滤。
- 前端 `FormulaPushPanel` 三处调用都带 `wp_code`；「立即推送」带 `wp_codes: [当前]`。项目级「全部推送」放在公式管理弹窗顶部（非页签内），点击前列出将影响的底稿清单并二次确认。

## 五、后端独占键单一真源（需求 4）

### 5.1 生成

`backend/scripts/gen/gen_formula_push_owned_keys.py`：读规则清单 + 各 binding 的目标展开描述，生成
`audit-platform/frontend/src/generated/formulaPushOwnedKeys.ts`：

```ts
// @generated DO NOT EDIT — 由 gen_formula_push_owned_keys.py 生成
export const FORMULA_PUSH_OWNED: Record<string, { exact: readonly string[]; patterns: readonly string[] }> = {
  E1: { exact: ['E1-adj-tb-amount-ending', ...], patterns: [] },
  K1: { exact: [...], patterns: [] },
}
```

- 范围 = `policy ∈ {system, derived}` 的底稿目标 `item_id`（需求 4.1）。行集目标（`four_table_leaves`）是行内字段级三态写入，**不进**独占集合（用户可编辑同一行的其它字段）。
- 族 binding 的目标若依赖项目数据展开（如动态行），只允许出现在 `patterns`，且每条 pattern 须在 binding 里有同名常量（守卫比对）。
- 幂等：内容不变则文件字节不变（无时间戳）；`--check` 漂移 exit 2 并点名（沿用平台 `--check` 约定，见 disclosure-payload 轮教训：禁 `--write` + `git diff`）。

### 5.2 强制点在后端写入口（需求 4.3）

前端直写 `checklist-responses` 的文件 241 个 / 调用 275 处（S21），只在前端过滤不可能完整。单一写入方在后端写入口强制：

- `checklist_responses` 批量保存：按 `context.wp_code` 取主编码 → 若已接入推送，则把 `item_id ∈ owned(主编码)` 的条目从本批剔除、不落库；其余条目照常保存。响应体加 `skipped_owned_keys: [...]`，日志计数（便于发现仍在回写独占键的宿主）。
- `owned(主编码)` 由后端规则现算（与生成文件同源同口径），进程内按规则文件 mtime + 注册表版本缓存。
- 推送引擎自身经 `WorkpaperMutationAdapter` 写入，不经该端点，不受影响。
- 「整批拒绝」否决：一个宿主一次保存常混有用户键与旧缓存里的独占键，整批拒绝会让用户输入丢失。

### 5.3 前端预过滤（优化，非正确性来源）

- `useChecklistPersistence` 新增可选参数 `wpCode`；`save` / `saveDebounced` / 批量保存在发请求前过滤 `FORMULA_PUSH_OWNED[主编码]` 命中的键（内存照常更新，供页面实时计算），避免「保存成功」提示覆盖了实际未落库的键。
- E1 的 `e1BackendOwnedKeys.ts`、K1 的 `k1BackendOwnedKeys.ts` 改为从生成文件派生（保留导出名，调用方不改）；其余宿主随各批接入时接 `wpCode`。
- 推送提示条：新纯函数 `formulaPushNotice(event, wpId, wpCode)`，判定 = 本底稿 ∈ `wp_ids` ∧ 非试跑 ∧ `changed_items ∩ OWNED[wpCode]` 非空；E1 / K1 两个旧函数改为薄转发（需求 4.8）。

> 🔴 E1 迁移的预期内行为变化（需求 4.5 已登记）：`E1-*-detail-*-unaudited` 今天由 `useE1CashDetail` / `useE1BankDetail` 的 `saveImmediate` 持久化，与后端派生规则**双写**。后端写入口强制（§5.2）上线后，前端这些写入会被剔除。以 `e1FormulaPushParity` 夹具证明两侧值逐位相同 ⇒ 已推送项目的持久化结果不变；但「后端推送尚未跑过的项目」打开页面后这些键不再落库 ⇒ 依赖它们的读方在首推前读不到值。实施时先现扫这些键的后端读方，有读方则在上线前对存量项目跑一次推送（需用户授权写库），或把 E1 的强制推迟到首推完成。

### 5.4 其余写入方（需求 4.6）

- 后端直写独占键的站点（如 K1-1 导入 handler 写审定合计 / FS 的分支）：AST 扫描 `_upsert_*`/`INSERT INTO checklist_responses` 中 `item_id` 字面量或 f-string 前缀命中某主编码独占集合的站点，冻结为基线、只许减少。
- OnlyOffice 同步契约：契约里映射到独占键的单元格必须在公式掩码内（只读），否则 OO 编辑会经回写链改写独占键；守卫比对契约 JSON。

### 5.5 守卫（需求 4.7）

- `owned(前端生成文件) == owned(后端规则现算)`（生成器 `--check`）。
- 端点级真请求：混合批次（用户键 + 独占键）⇒ 用户键落库、独占键不落库且出现在 `skipped_owned_keys`；未接入主编码的批次行为逐字不变。
- 前端任一宿主 / composable 里以字面量读取的 `{code}-...` 键，若属于该主编码的系统值 / 派生值**命名空间**（按 binding 声明的前缀），则必须在 `OWNED[code]` 中（防 S13：读 `K1-1-audited-bad-debt` 而写入方只有 `K1-1-audited-baddebt`）。扫描用 AST / 字面量提取，不用文本 `in`（方法论 ㉖）。

## 六、规则与附注通用化（需求 5）

### 6.1 规则校验改为按 binding

`parse_rules` 现在用全局 `FOUR_TABLE_SLOTS` 与全局派生集合校验。改为：解析到 `page_key=workpaper:{code}` 后取 `get_binding(code)`，用该 binding 的 `four_table_slots` / `derivations` / `tb_columns` 校验（需求 5.1、5.4、5.5）。`load_rules` 的缓存键已包含注册表版本，保持。

### 6.2 试算表上下文支持发生额（需求 5.4、S19）

- `FORMULA_CONTEXTS["tb"]` 新增 `trial_balance_audited_occurrence`：期末余额 / 年初余额之外装载「本期发生额」，口径 = 报表引擎审定模式（`report_engine._COLUMN_MAP` 的 `_period_amount` 特殊分支）。实施时现读该分支确定是「审定数」还是「借方 − 贷方」，与报表 `IS-*` 行逐值对拍（同 ADR-PUSH-002 修订二的做法）。
- 校验：公式里 `TB(code, col)` 的列名必须 ∈ 上下文装载列，否则整份拒收 —— 现状取不到列返回 0 并只记 trace，推送会静默写 0。

### 6.3 附注写入通用化（需求 5.2、5.3）

- 删 `note_writer._SECTION_MAP`：章节由规则 `target.section_by_template` 给出（E1 规则已声明）。
- `build_main_skeleton(template_type, section, table)`：签名增加章节参数，从附注模板按章节 + 表名取行与列。E1 调用改为传规则里的章节，逐字节对拍 `e1_note_skeleton.json` 夹具。
- 字段：规则 `target.fields` 声明要写的附注字段（如 `end_amount` / `prior_amount` / `current_amount`），`NOTE_FIELDS` 从常量改为「字段 → (取值键, addr 期间后缀)」的登记表，未登记字段整份拒收。E1 规则补 `fields: ["end_amount","prior_amount"]` 后行为不变。

## 七、接入等级清册（需求 6）

`backend/scripts/gen/gen_formula_push_coverage.py` → `backend/data/formula_push_coverage.json`（`--check` 幂等）。

- 分母 = `wp_account_mapping.json` 有科目映射的主编码（需求术语）；逐码字段：等级、宿主、渲染预填形态、灰度开关**名**（不写现值——现值随环境变，写进去会让 `--check` 在不同机器上漂移；现值由面板运行时读取展示）、binding、规则数、附注同步注册、前端同步载荷数、「不适用」原因。
- 真库底稿数**不进**生成文件（随数据变化），由一次性探针在每批验收时现算并写进该批 tasks 的证据栏。
- 守卫：L3 集合 == 注册表；L3 码必须存在 `backend/tests/test_formula_push_{code}_*.py` 集成测试；声明 L4 的码必须满足需求 9（清册里逐项给证据路径，守卫校验路径存在）。
- 公式管理弹窗：底稿未接入时页签显示中文说明 +「当前等级」（来自 `/bindings` 返回的清册摘要），替代现在的静默隐藏（需求 6.4）。

## 八、K1（需求 1，批 A）

| 目标 | 现前端键 | 策略 | 来源 |
|---|---|---|---|
| 性质行 n0~n4 原值 期初、未审 | `K1-1-nature-gross-n{0..4}-{begin,unadj}` | **editable** | 四表叶子按科目名归类（`_classify_nature`，前后端同源规则）；审计师可改类、「从 K1-2 同步」也写这些键 ⇒ 不能是系统值 |
| 账龄组合 r1 原值 / 坏账 期初、未审 | `K1-1-{receivable,baddebt}-r1-{begin,unadj}` | **editable** | 四表总额兜底进账龄组合（`_build_adjudication_prefill`：「客户科目表无信用风险组合维度」）；r0/r2/r3 无四表口径 ⇒ **不推送** |
| 与报表核对三项 | `K1-1-fs-{interest,dividend,other-total}` | **editable** | `_build_fs_reconciliation`；界面就是 `el-input-number` |
| 审定合计 | `K1-1-audited-{receivable,baddebt,net}` | derived | 复刻 `useK1Adjudication.persistAuditedTotals`（各段 `subtotalRow.audited`） |

性质行坏账（`K1-1-nature-prov-*`）四表无口径（渲染预填只按原值叶子归类），**不推送**，由「从 K1-2 同步」与用户维护。

⇒ K1 的后端独占集合只剩**审定合计 3 键**（现前端手写 42 键）。实施时现读 `K1_NATURE_ROW_DEFS` / `K1_PORTFOLIO_ROW_DEFS` 确认 syncKey 与行号对应，结果写进 tasks 证据栏。

> 🔴 与 phase3 design §六的差异（如实登记）：phase3 把性质行、组合行与 FS 三项都写成系统值推送目标，前端据此把它们列为独占键（S10）。现读证实：组合行只有「总额进 r1」一种可推口径、其余组合是审计判断；性质归类审计师可改、且有第二个用户操作入口（从 K1-2 同步）；FS 三项界面是可编辑输入框 ⇒ 三者改为 `editable`（三态：用户值保留并在面板显示差异），**不进独占集合**。这修正了 S10 的根因，而不只是补一个写入方。

- 取数：`_k1_other_receivables` 内层纯函数 `_build_adjudication_prefill` / `_build_fs_reconciliation` 加 `strict`（不经 `render()`，它有「已持久化就不预填」的门）。
- 「从 K1-2 同步未审数」「从四表带入」：写入的都是 editable 键 ⇒ 照常持久化（推送记为人工值、面板可「采用公式值」），按钮语义不变。
- 导入（S12）：`_k1_1_import_handler` 写 system / derived 键的分支删除，导入完成后 `run_and_commit(trigger=manual, wp_codes=['K1'])`；editable 键照常写入。
- 键名漂移（S13）：`K1TabBadDebtDetail` 改读 `K1-1-audited-baddebt`；守卫见 §5.3。
- 双侧夹具：`backend/tests/fixtures/formula_push_k1_parity.json`，vitest 用真 `useK1Adjudication` 产出。

**交付顺序约束（需求 1.8）**：止血分两步。Task 1 先修事件总线去重键（§3.1），Task 2 再把 `k1SaveItemIds` 恢复为**完全不过滤**（回到 2026-10-03 前「前端写全部键」的状态；审定合计 3 键此时由前端写，因为后端还没有写入方）。颠倒顺序会让 K1「发布到试算表」重新被吞（S22）。K1 binding 与独占键生成器都上线后，再由持久化层按生成集合过滤审定合计 3 键。任何时刻都不存在「无人持久化」的键。

## 九、批 B：Tier A 单公式族

- 存量：18 码 21 条锚点（S7），表达式全是 `TB(...)`（19 条单项、D1 / D2 两条「原值 − 坏账」），目标是 `checklist_responses.item_id`，渲染期 transient seed（不落库、不随四表刷新）。
- 迁移：每条锚点生成一条 `source/formula` 规则（`policy=system`，`context.tb=trial_balance_audited`），由一个通用 `TierAAnchorBinding(code)` 承载（族 binding：只有单值目标、无派生、无附注）。
- 口径核对：`wp_formula_eval_service._COLUMN_MAP` 的「期末余额 → audited_amount」与推送 `trial_balance_audited` 同口径；但 **4** 条（D4-1 两条、H10、I6）用 `TB(code,'审定数')` —— 「审定数」在推送规则里是**禁用列名**（`BANNED_COLUMNS`，内核别名把它与期末余额折叠）⇒ 迁移时改写为 `TB(code,'期末余额')` 并在规则说明里注明等价依据（这 4 条都是损益类科目，`audited_amount` 存审定发生额，见 D4 预设说明），或等需求 5.4 的发生额上下文落地后改为发生额口径。逐条现读该锚点在审定表上的语义后再定，结论写进 tasks 证据栏。
- D1 / D2 的减项码是 `1231-01` / `1231-02`（坏账准备子目）：真库 `trial_balance.standard_account_code` 里这两个带连字符的码**原样存在**（各 9 行），推送 `load_tb_audited` 的前缀取数能命中；但父码 `1231` 也有 10 行，前缀 `'1231-01%'` 不会误吞父行。迁移测试须同时造父码与 `-01`/`-02` 子目，断言减项只取子目。
- 渲染期 seed 保留（未推送过的项目打开页面仍有值），推送落库后以持久化值为准（与 E1 的 persist-first 同规则）。
- canary：真库 21 个锚点键只在重药控股安徽 D4 上有真实数据 ⇒ 首选 D4（损益类、2 条锚点，正好覆盖「审定数」改写）；若 D4 现读发现锚点语义不是审定发生额，改选有底稿的 H8 / H9 并用合成数据验收，写明理由。

## 十、ADR

- **ADR-FPA-001 按形态分族铺开，不按循环字母**：同一循环内形态差异大（D 循环既有单公式核对行也有动态明细行），按族共用 binding 才能「一次实现、多科目接入」；否决「逐科目复制 E1 binding」（89 份实现无法维护）与「全部用通用规则表达」（明细行身份、多币种、组合拆分等不是公式能表达的，见 disclosure-payload ADR-DPA-001「载荷是计算不是常量」）。
- **ADR-FPA-002 独占范围 = system + derived**：editable 目标由后端三态写入但用户可改，若进独占集合则用户输入被前端静默丢弃（S10）。否决「凡后端写的都独占」。
- **ADR-FPA-007 单一写入方在后端写入口强制，前端过滤只是优化**：241 个前端直写点（S21）逐个改不现实且会漏；端点按主编码剔除独占键并回报，正确性不依赖每个宿主都改对。否决「只靠前端过滤」与「整批拒绝」。
- **ADR-FPA-008 推送底稿按 binding 声明，不默认只推主编码册**：真库条目有落在子码分册上的（S20）；默认只推主册会让这些科目「推送成功」而用户看到的册不变。缺省仍是主编码（E1 / K1 现状成立），分册须现查后显式声明。
- **ADR-FPA-003 防抖丢事件按去重键修（含 `wp_id` / `publish_token`）**：根因在事件总线、影响全部订阅者与「发布到试算表」确认，只修推送一侧或只改一个发布点都是绕开；见 §3.1。
- **ADR-FPA-004 失败隔离到底稿级**：多科目后整次回滚的爆炸半径不可接受；strict 语义（不降级）不变。
- **ADR-FPA-005 清册只放结构事实，不放数据计数与环境开关现值**：否则 `--check` 随数据 / 机器漂移成永假门禁（disclosure-payload 五轮 T29 教训）。
- **ADR-FPA-006 K1 性质行、账龄组合与 FS 三项改 editable，独占只留审定合计**：修正 phase3 design §六，依据见 §八。

## 十一、测试与变异

| 判据 | 测试 | 关键变异 |
|---|---|---|
| binding 协议 | 注册缺方法 / 属性为空的假 binding 被拒 | 去掉注册校验 |
| 新科目零改动 | 临时注册 Z9（含附注规则与独占键）：规则校验、触发、面板、生成器、提示条全部生效；撤销后全部消失 | 任一处写死 E1 |
| 防抖不丢 | 两张底稿 50ms 内保存 ⇒ 两张都派发；同一底稿连续保存仍合并为一次 | 去重键去掉 `wp_id` |
| 发布确认不被吞 | 发布门后 50ms 内一次条目保存 ⇒ 确认事件与保存事件都派发、试算表被更新、`tb_publish_ack` 有行 | 去重键去掉 `publish_token` |
| 缺 wp_code 反查 | 事件只带 wp_id ⇒ 仍推 | 去掉反查 |
| 失败隔离 | K1 取数抛错 ⇒ E1 照常写入、K1 零写入、运行 partial | 恢复整次回滚 |
| 面板隔离 | 两科目有差异 ⇒ 各页签只见本科目 | 去掉 wp_code 过滤 |
| 独占键生成 | `--check` 漂移 exit 2；editable 目标不在集合 | editable 进集合 |
| 后端写入口强制 | 混合批次：用户键落库、独占键跳过并回报；未接入主编码零变化 | 去掉剔除逻辑 / 改成整批拒绝 |
| 读写键漂移 | 宿主读未登记的独占命名空间键 ⇒ 红 | 恢复 `audited-bad-debt` |
| 发生额口径 | 损益类规则与报表 `IS-*` 逐值相等；用未装载列的公式整份拒收 | 上下文缺列时放行 |
| 附注通用 | E1 骨架逐字节对拍；未登记字段拒收 | 恢复写死章节 |
| K1 闭环 | SQLite 真 ORM：四表 → 性质 / 组合 r1 / 审定合计；人工改性质行与组合行保留；FS 手填保留；r0/r2/r3 不被推送 | 任一 editable 目标改回 system |
| Tier A 迁移 | 21 条锚点值与渲染期 seed 逐值相等 | 改列名口径 |

## 十二、风险

| 风险 | 缓解 |
|---|---|
| 去重键加 `wp_id` 后 19 处订阅在密集保存时多执行几次 | §3.1 变更前清单逐个判定；只增加计算量、不改变「每次保存一次」的既有语义 |
| E1 迁移到统一过滤后，未推送过的项目派生键不再落库 | §5.2 先扫后端读方，再决定是否先跑一次推送或保留双写 |
| 多会话并发改同一批文件（`useChecklistPersistence`、`checklist_responses.py`、`engine.py`） | 每个任务动手前 `git status` 核对目标文件无他人改动；共享文件按块暂存 |
| 族 binding 覆盖不到个别科目的特殊口径 | 族 binding 允许按规格声明「不推送的目标」，清册标出；canary 先行 |

## 十三、批 C 族 binding 预设计（ADR-FPA-009）

> 本节是批 C（资产负债类审定表族）的**预设计**——为后续独立 spec 提供可执行的数据结构、边界与实施路径。
> 批 C spec 将细化本节并覆盖逐科目验证；本节的数据结构名、字段名在 spec 细化阶段允许调整。
> 交叉引用：需求 7.2 批 C · ADR-FPA-001（按形态分族）· §二（binding 协议）· §八（K1，批 A 先例）。

### 13.1 覆盖范围与共同形态

批 C 的入选标准 = **资产负债类审定表**且含「期初 / 未审 / AJE / RJE → 审定合计」栏位结构。
候选科目（需求 7.2 列举 + 实施前现算复核）：

| 循环 | 候选码 | 审定表 sheet | 备注 |
|---|---|---|---|
| K | K2~K7 | `{code}-1` | K4 `has_account=False`（宁缺勿造），推送只落派生合计 |
| G | G1~G10 | `{code}-1` | G10 结构最复杂（8 个子表），canary 不选它 |
| H | H1~H10 | `{code}-1` | H5~H10 同时有 Tier A 锚点（批 B）；批 C 只管审定表其余行 |
| I | I1~I5 | `{code}-1` | I6 是损益类（归批 D） |
| J | J1~J2 | `{code}-1` | J3（股份支付）渲染策略不取四表，暂不入 |

共同形态（从 K1、F2、N1~N5 的 `_build_adjudication_prefill` 模式提炼）：
1. 从试算表按科目码前缀汇总「期末余额 / 年初余额」（资产负债类，走 `load_tb_audited`）
2. 可选：子科目分类进组合行（K1 的 r0~r3）或性质行（K1 的 n0~n4）
3. 审定合计 = Σ(unadj + aje + rje) 按组合行——这是 `k1_calc` 的模式，全部审定表同形
4. 可选：「与报表核对」区（FS reconciliation，读报表行金额对比审定合计）

### 13.2 族规格数据结构

一个实例描述一个科目的审定表推送结构：

```python
@dataclass(frozen=True)
class PortfolioRowDef:
    """组合行定义（r0~rN）。"""
    row_key: str                   # syncKey 后缀，如 "r0"、"r1"
    pushable: bool                 # 是否由推送写入（K1 r0/r2/r3 无四表口径 ⇒ False）
    tb_source: str | None = None   # 非空 = TB 取数口径名（"aging"/"credit_risk"/…）

@dataclass(frozen=True)
class AuditedTotalKeys:
    """审定合计三键（policy=derived，后端独占）。"""
    receivable: str    # 如 "K2-1-audited-receivable"
    baddebt: str       # 如 "K2-1-audited-baddebt"
    net: str           # 如 "K2-1-audited-net"

@dataclass(frozen=True)
class AdjudicationSpec:
    """审定表族 binding 规格——一个实例描述一个科目的审定表结构。

    spec: formula-push-all-subjects-rollout · design §十三 · 需求 7.2
    """
    wp_code: str
    account_codes: tuple[str, ...]         # TB 取数的科目码前缀（与 KCycleSpec.fallback_standard 同源）
    sheet_code: str                        # 审定表 sheet 编码（如 "K2-1"）

    # 组合行
    portfolio_rows: tuple[PortfolioRowDef, ...]  # r0~rN；空 = 该科目无组合维度
    portfolio_prefixes: tuple[str, str]          # ("receivable", "baddebt") — item_id 命名空间前缀

    # 派生规则
    audited_total_keys: AuditedTotalKeys

    # ── 可选扩展 ──
    nature_rows: tuple[str, ...] | None = None       # 性质行 syncKey（K 循环有，G/H 可能没有）
    fs_reconciliation_keys: tuple[str, ...] | None = None  # 「与报表核对」键（editable）
    extra_derivations: frozenset[str] = frozenset()  # 科目独有派生（如 K6 资产+负债两侧合计）
    note_sections: dict[str, str] | None = None      # template_type → 附注章节
    has_provision: bool = True                        # 有坏账准备 / 减值维度
    is_liability: bool = False                        # 负债侧（K3/K4/K5/K7）
```

设计依据：
- `account_codes` 从 `KCycleSpec.fallback_standard`（K 循环）、`g_cycle_specs`（G 循环）、`h_cycle_specs`（H 循环）、`i_cycle_specs`（I 循环）、`j_cycle_account_scope`（J 循环）现读取得，**禁按命名习惯推**（方法论 ⑭）。
- `portfolio_rows` 复用 K1 的 r0~r3 模式。不是所有科目都有组合行（K2 其他流动资产、K7 递延收益可能只有一个兜底行），此时 `portfolio_rows` 为单元素元组。
- `audited_total_keys` 的三键命名统一为 `{code}-1-audited-{receivable,baddebt,net}`（K1 先例），baddebt 键使用 `baddebt` 而非 `bad-debt`（修 S13 教训）。
- `nature_rows` 只有 K 循环可能存在（K1 有 n0~n4 性质行），G/H/I/J 审定表无此维度 ⇒ 字段可选。
- `fs_reconciliation_keys` 是 editable 键（ADR-FPA-006 先例），有 FS 核对区的科目声明，无的留 None。

### 13.3 族 binding 实现类

```python
class BalanceAdjudicationBinding:
    """资产负债类审定表族 binding。

    通过 AdjudicationSpec 实例化，一个类服务全部批 C 科目。
    """
    def __init__(self, spec: AdjudicationSpec) -> None:
        self.wp_code = spec.wp_code
        self.account_prefixes = spec.account_codes
        self.derivations = frozenset({
            f"{spec.wp_code.lower()}_audited_total",
            *spec.extra_derivations,
        })
        self.four_table_slots = frozenset()          # 批 C 不消费四表叶子
        self.tb_columns = frozenset({"期末余额", "年初余额"})
        self.paper_codes = (spec.wp_code,)
        self._spec = spec
```

共享逻辑（复用 K1 已验证的模式）：

| 方法 | 共享 / 覆盖 | 说明 |
|---|---|---|
| `load_sources` | **共享** | `load_tb_audited(db, project_id, year, spec.account_codes)` → `FormulaSources`；与 K1 / Tier A 同源 |
| `workpaper_targets` | **共享** | 按 `rule.source.kind` 分派：`formula` 走 `formula_engine.execute`，`derivation` 走 `_derive` |
| `_derive` | **共享框架 + 按 spec 分派** | `{code}_audited_total` 的 receivable/baddebt/net 三键复用 `_row_audited` 模式（Σ组合行 `unadj+aje+rje`）；`extra_derivations` 按科目分派 |
| `apply` | **共享** | 与 K1 / Tier A 一致：`js_number_to_string(float(value))` |
| `note_rows` | **共享** | 按 `spec.note_sections` 声明的章节 + 规则 `target.section_by_template` 生成；无声明 = 空 |
| `entry_warnings` | **共享** | 检查 `spec.account_codes` 在试算表是否有行（`has_account` 检测） |

科目级覆盖点（只在 `AdjudicationSpec` 里声明，不在 binding 类里加 `if code ==`）：
- **组合行定义不同**：K1 有 r0~r3（其中 r0/r2/r3 不推），K2 可能只有 r0（全部进一个兜底行），G2 可能有按证券类别的组合行 ⇒ `portfolio_rows` 描述差异。
- **有无备抵维度**：K7 递延收益无坏账准备，`has_provision=False` ⇒ 审定合计只有 receivable + net（net = receivable），baddebt 键不生成、不进独占集合。
- **有无性质行**：只有 K 循环部分科目有（K1 有，K2~K7 须逐科目现读确认）。
- **负债方向**：K3/K4/K5/K7 是负债类（`is_liability=True`），金额符号取反（与 `KCycleSpec.is_liability` / `gross_direction` 对齐）。

### 13.4 注册与工厂

```python
# bindings/__init__.py _REGISTRY 新增示例
"K2": "app.services.formula_push.bindings.balance_adj:binding_for('K2')",
"K3": "app.services.formula_push.bindings.balance_adj:binding_for('K3')",
# ...
"G1": "app.services.formula_push.bindings.balance_adj:binding_for('G1')",
# ...
```

工厂函数（与 Tier A 的 `binding_for` 同模式）：

```python
# bindings/balance_adj.py
_SPECS: dict[str, AdjudicationSpec] = { ... }  # 按科目声明

def binding_for(wp_code: str) -> BalanceAdjudicationBinding:
    if wp_code not in _SPECS:
        raise KeyError(f"底稿 {wp_code} 不在审定表族规格中")
    return BalanceAdjudicationBinding(_SPECS[wp_code])
```

`_SPECS` 的每条声明都必须有现读实证（方法论 ⑭⑮）：`account_codes` 经 `k_cycle_specs` / `g_cycle_specs` / `h_cycle_specs` / `i_cycle_specs` / `j_cycle_account_scope` 取得并与真库 `trial_balance.standard_account_code` 前缀核对；`portfolio_rows` 从对应渲染策略的 `_build_adjudication_prefill` 现读 syncKey 模式提取。

### 13.5 与批 B（Tier A）的边界

同一 `wp_code` 可同时出现在批 B 和批 C（如 H5~H10、I1~I5）。两批的规则写不同的 `item_id`：

| 批次 | 目标类型 | item_id 示例 | 来源 |
|---|---|---|---|
| 批 B（Tier A） | 试算表核对行（1 条锚点） | `H8-1-tb-reconcile-ending` | `d_cycle_extraction_presets.json` 的 `expression` |
| 批 C（审定表族） | 组合行期初/未审 + 审定合计 | `H8-1-receivable-r0-begin` / `H8-1-audited-receivable` | `AdjudicationSpec.portfolio_rows` + `audited_total_keys` |

**目标唯一性约束**（需求 7.3）：同一 `item_id` 只能出现在一个批次的规则中。守卫 = 规则解析后检查 `target.item_id` 在全部规则里唯一（已有 `_validate_target_uniqueness`，不需新机制）。实施时现扫两批候选 `item_id` 集合确认零交集，结论写进 tasks 证据栏。

🔴 两批的 binding 是**独立实例**（Tier A 的 `TierAAnchorBinding` 和批 C 的 `BalanceAdjudicationBinding`），但共享同一个 `load_tb_audited` 取数路径。引擎按规则的 `page_key=workpaper:{code}` 找到该码所有规则后，按 binding 实例分别处理 ⇒ 同一码两个 binding 不可能发生（注册表一个码一个 binding）。⇒ 批 C 的 binding **须兼容执行 Tier A 锚点规则**（`source.kind=formula`），否则 H5~H10、I1~I6 的 Tier A 锚点会因 binding 替换而丢失。做法 = `BalanceAdjudicationBinding.workpaper_targets` 的 `formula` 分支与 `TierAAnchorBinding` 逻辑等价（实际就是 `formula_engine.execute` + `js_number_to_string`），迁移后以双侧夹具证明锚点值不变。

### 13.6 canary 选择

canary 须满足：①真库有条目数据（S20 口径）②审定表结构最简单（少特殊分支）③与批 B 无交叉（首选纯批 C 科目，避免同时处理 Tier A 迁移）。

| 候选 | 真库条目 | 审定表结构 | 批 B 交叉 | 裁定 |
|---|---|---|---|---|
| K2 | 有（S20 口径，实施前现算） | 简单：无性质行、无坏账维度可能、单兜底行 | 无（K2 不在 Tier A 18 码内） | **首选** |
| K3 | 有 | 简单但负债类（符号取反） | 无 | 备选——验证负债方向 |
| G1 | 有（长期股权投资，最常见 G 循环） | 中等：有减值维度 | 无 | 备选——验证 G 循环形态 |
| K7 | 有 | 简单、无坏账 | 无 | 备选——验证 `has_provision=False` |

建议 canary = **K2**（其他流动资产）：`KCycleSpec` 声明已存在（`k_cycle_specs.py`）、`account_codes=("1901",)`、无性质行、无备抵、`is_liability=False`，是最小验证集合。canary 验收通过后，按以下顺序铺开：
1. K3/K5/K7（负债方向验证）→ K4（`has_account=False` 仅落派生合计）→ K6（资产+负债两侧）
2. G1~G10（按真库条目数排序，条目最多的先做）
3. H1~H10（H5~H10 须同时接管 Tier A 锚点，放在纯审定表科目之后）
4. I1~I5、J1~J2

### 13.7 审定合计计算模式

所有批 C 科目的审定合计复用 K1 的 `k1_calc` 模式，提炼为通用函数：

```python
def audited_total(
    entries: Mapping[str, Any],
    prefix: str,                      # "receivable" / "baddebt"
    row_keys: tuple[str, ...],        # ("r0", "r1", "r2", "r3") 或该科目实际行
    item_id_template: str,            # "{code}-1-{prefix}-{row_key}-{suffix}"
) -> float:
    """通用审定合计 = Σ row_audited(unadj + aje + rje)，舍入 Math.round(n*100)/100。"""
```

净值 = `audited_total(entries, "receivable", ...) - audited_total(entries, "baddebt", ...)`。
`has_provision=False` 时，baddebt 合计恒 0、净值 = 原值合计。

🔴 计算必须与前端 `persistAuditedTotals`（K1 先例）/ 各科目宿主的审定合计 composable 同口径：
- 舍入对齐 `Math.round(n*100)/100`（JS Number 精度范围内与 Python `round(n, 2)` 等价，K1 已验证）
- 行键模式：`{code}-1-{prefix}-{row_key}-{suffix}`，其中 suffix ∈ `{begin, unadj, aje, rje}`
- 审定数 = `_round2(unadj + aje + rje)`（与 K1 的 `_audited` 一致）
- 双侧夹具对拍（需求 9.2）：vitest 用真 composable 产出期望值，pytest 用通用 `audited_total` 产出实际值，逐位比对

### 13.8 独占键与可编辑键

沿用 ADR-FPA-002 / ADR-FPA-006 原则：

| 目标类型 | policy | 独占 | 说明 |
|---|---|---|---|
| 审定合计（receivable/baddebt/net） | derived | ✅ | 后端计算，前端不保存 |
| 组合行 期初/未审（pushable=True 的行） | editable | ❌ | 用户可改、「从 X-2 同步」也写这些键 |
| 性质行（若存在） | editable | ❌ | 归类可由审计师调整 |
| 「与报表核对」（若存在） | editable | ❌ | 界面是 el-input-number |
| 组合行（pushable=False） | — | — | 不推送、不进独占集合 |

⇒ 每个科目的独占键集合预期极小（仅审定合计 2~3 键），与 K1 的经验一致（42→3 的收缩）。生成器（§5.1）按 `AdjudicationSpec.audited_total_keys` + `extra_derivations` 的规则目标展开。

### 13.9 测试策略

- **参数化 fixture**：一个 `@pytest.fixture(params=ALL_BATCH_C_CODES)` 遍历全部批 C 科目，每个科目用该科目的 `AdjudicationSpec` 构造 binding 并跑同一组断言（协议校验、目标展开、审定合计计算、独占键集合）。
- **K2 canary 专属测试**：SQLite 真 ORM 集成（`test_formula_push_k2_integration.py`），覆盖需求 9.1~9.3。
- **双侧夹具**：`formula_push_{code}_parity.json`，vitest 用真 composable 产出（K1 先例）。
- **与 Tier A 锚点共存测试**（H5~H10、I1~I5）：同一科目的两批规则同时存在时，`_validate_target_uniqueness` 通过 ∧ 两批目标值都正确。
- **变异**：①任一 editable 目标改回 system ⇒ 独占键集合错误 ②审定合计公式改错 ⇒ 双侧夹具红 ③注册表删一个科目 ⇒ 参数化测试少跑一个码并打红

### 13.10 实施建议（给批 C spec 的约束）

1. **先 canary 后铺开**：K2 走完 L4（需求 9 全矩阵）后，同族其余科目才能注册。
2. **逐科目现读声明**：每个科目的 `AdjudicationSpec` 必须经以下现读确认后才能写进 `_SPECS`：
   - `account_codes`：从对应循环的 `*_cycle_specs` / `*_account_scope` 取 fallback_standard，与真库 `trial_balance` 前缀命中行数核对
   - `portfolio_rows`：从对应渲染策略的 `_build_adjudication_prefill` 现读 syncKey 模式
   - `audited_total_keys`：从对应前端宿主的 `persistAuditedTotals` / 等价 composable 现读键名
   - 结论写进 tasks 证据栏（方法论 ②⑭）
3. **一个文件 `balance_adj.py`**：全部批 C 科目的 `AdjudicationSpec` 声明 + `BalanceAdjudicationBinding` 类 + `binding_for` 工厂，**禁**每科目一个文件。
4. **通用计算函数独立模块**：`balance_adj_calc.py`（对应 K1 的 `k1_calc.py`），只含纯函数，无 IO / ORM / async。
5. **H5~H10 / I1~I5 的 Tier A 迁移**：批 C 接管这些科目后，Tier A 的 `TierAAnchorBinding` 注册条目从 `_REGISTRY` 删除（被 `BalanceAdjudicationBinding` 替代）；但锚点规则保留在 `formula_push_rules.json`，由新 binding 的 `formula` 分支执行。迁移前后以双侧夹具证明 21 条锚点值不变。
6. **不改渲染策略**：批 C 的 binding 只消费渲染策略的取数口径（`_build_adjudication_prefill` 的算法逻辑），不改渲染策略本身。渲染期 seed 保留（与批 B Tier A 同策略）。
7. **K4 特殊处理**：`has_account=False`（`KCycleSpec` 已声明），推送只落 derived 合计键（如果有条目的话）；组合行全部 `pushable=False`。
8. **真库分布先行现算**：批 C spec 的 Task 0 须现算每个候选码在真库的条目数（S20 口径），决定 canary 并按条目数排序铺开顺序；**禁按字母顺序铺开**。

### 13.11 否决方案

| 方案 | 否决理由 |
|---|---|
| 每科目复制一份 binding（如 `K2Binding`、`K3Binding`…） | 40+ 份几乎一致的实现无法维护，违反 ADR-FPA-001 |
| 把组合行 / 性质行全部改为 `formula_push_rules.json` 的 formula 规则 | 组合行的分配逻辑是按子科目分类而非公式（见 K1 的 `_classify_nature`），不是 `TB()` 表达式能表达的（ADR-FPA-001「载荷是计算不是常量」） |
| 批 C 与批 B 合并为一批 | 审定表族的组合行 / 派生逻辑远比 Tier A 锚点复杂，合并会让 canary 验证周期过长；且 H5~H10 的 Tier A 接管需要批 C 先有稳定的审定表族 binding |
| 规格声明放在 `formula_push_rules.json` 而非代码内 `_SPECS` | 规格含 Python 逻辑（`extra_derivations` 映射到计算函数）和类型约束（`tuple[PortfolioRowDef, ...]`），JSON 无法表达；规则文件只放「声明式规则」（公式表达式 / 目标 / 策略） |


## 十四、测试目录重组计划（待入库后执行）

> 本节不是 ADR，是工程治理待办。当前 25 个 formula_push 测试文件平铺在 ackend/tests/ 根目录，
> 与仓库其他功能域（ormula_management/、workpaper_sync/、d_cycle_extraction/）的子目录约定不一致。
> 批 C 加入后文件数会翻倍（40+），届时必须重组。

### 14.1 目标结构

`
backend/tests/formula_push/
├── __init__.py
├── _env.py                          # 原 _formula_push_env.py
├── _binding.py                      # 原 _formula_push_binding.py
├── conftest.py                      # 共享 fixture（如 make_env）
│
├── test_binding_protocol.py         # 协议校验
├── test_engine.py                   # 引擎逻辑
├── test_triggers.py                 # 触发器
├── test_endpoints.py                # 端点真请求
├── test_rules.py                    # 规则解析与校验
├── test_note_writer.py              # 附注写入器
├── test_policy.py                   # 策略三态
├── test_js_compat.py                # JS 数字兼容
├── test_e2e.py                      # 端到端
├── test_schema_contract.py          # schema 契约
├── test_coverage.py                 # 清册守卫
│
├── owned_keys/
│   ├── __init__.py
│   ├── test_gen.py                  # 生成器
│   ├── test_baseline.py             # 基线
│   └── test_grace.py                # 宽限期
│
├── bindings/
│   ├── __init__.py
│   ├── test_e1.py                   # E1 binding
│   ├── test_e1_parity.py            # E1 双侧夹具
│   ├── test_k1_integration.py       # K1 真 ORM
│   ├── test_k1_parity.py            # K1 双侧夹具
│   ├── test_tier_a.py               # Tier A 族
│   └── test_d4_canary.py            # D4 canary L4
│
└── pg/
    ├── __init__.py
    ├── test_engine_pg.py            # 引擎失败隔离真 PG
    ├── test_k1_d4_canary_pg.py      # K1+D4 canary 真 PG
    └── test_schema_pg.py            # schema 契约真 PG
`

### 14.2 执行步骤（入库后）

1. 创建目录结构 + __init__.py
2. git mv 每个文件到目标位置（保留 git 历史）
3. 更新所有 rom tests._formula_push_env import ... → rom tests.formula_push._env import ...
4. 更新所有测试内的相对 import（rom tests._formula_push_binding import ... 等）
5. python -m pytest backend/tests/formula_push/ -v 确认全绿
6. CI python -m pytest backend/tests/ 不受影响（pytest 递归发现子目录）

### 14.3 前置条件

- 本 spec 所有文件已 commit 到分支
- 无并发会话在改 formula_push 测试文件
- 无 CI 正在跑（避免 rebase 冲突）

### 14.4 不做的事

- 不改测试逻辑、不改断言、不改 fixture 数据
- 不重命名函数/类/变量
- 纯搬迁 + 纯 import 路径更新
