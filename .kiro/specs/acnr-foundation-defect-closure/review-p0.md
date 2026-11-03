# ACNR 身份判定与目录契约单一化（P0 批次 T02/T03）

本批相对 `b5fc200e0` 实际落地的 ACNR-foundation 内容只有两个提交：`0d0ca8f24`（T02 `exact_identity` + `reasons`，T03 `catalog_contract` + schema 单一来源）与 `d1da8ea95`（tasks.md 标注）。其余 diff（advanced-query-linkage、s-cycle、m2 脚本删除）属并发会话，不在本评审范围。交付面：新增 `exact_identity.py`（全平台「名称/编码→sheet 身份」的唯一判定）、`reasons.py`（错误码→中文文案集中表）、`catalog_contract.py`（schema 唯一机器可读来源 + `build_schema()`）、由契约生成的 `global_catalog.schema.json`（强制 LF）、删除手写 schema 脚本 `_build_schema.py`/`_verify_schema.py`、`requirements.txt` 钉 `jsonschema==4.26.0`、`.gitattributes` 固定 schema 行尾。

Watch for：

- 任务 prompt 的四个焦点（acnr_targets 取值闭环与鉴权、解析不到/无权/不支持一律 422、孤儿清零不静默丢弃、release `--check` 幂等）对应的是 P0 的 **T05/T07/T14 等尚未交付的任务**——这些模块（`acnr_target_values`/`catalog_release`/`sheet_verdicts`/`generate_catalog --check`）在当前树中不存在。本批只交付 T02/T03，无法就这四点给出代码级结论（confirmed，已 `git ls-files` 核实）。
- `cell_of` 的 A1 正则 `^[A-Z]{1,3}[0-9]{1,7}$` 与 schema 里 `cell_address` 的 `^[A-Z]+[0-9]+$` 不同口径，存在边界不一致（likely）。
- 测试把同名组数硬编码为 `78`、唯一归属 `70`，任何目录变动都会红——是基线锁而非缺陷，但耦合较紧（confirmed）。
- 结构性零（真实目录 `forbidden_aliases` 为空 ⇒ 第 3 步与不相交不变量在真实目录恒触不到）已由合成索引 + 变异用例覆盖，处理得当（confirmed）。

**Verdict**: APPROVED

## High-level view

T02/T03 把两类「全平台应当只有一份」的逻辑收敛成独立纯函数模块，方向与 design §6.2/§4.2 一致，且只依赖标准库+jsonschema，不给 CI 增负。身份判定按 7 步规则实现（design 文字写「6 步」，代码把 design 第 6 步的 ambiguous 分支拆成独立第 7 步，行为等价），文本逐字比较、不做归一，这是正确的——归一会把「借名父级」和「名称所属 sheet」混为一谈。

契约单一化的关键守卫是「磁盘 schema 字节 == `build_schema()`」。这条在 `core.autocrlf=true` 的 Windows 本机本来会因 CRLF 转换而红，新加的 `.gitattributes eol=lf` 规则把它按住了；我实测磁盘文件为纯 LF、与 `schema_json()` 逐字节相等（10624 B，366 个 LF、0 个 CRLF），`git ls-files --eol` 确认 `attr/text eol=lf` 生效。这个此前被 `.gitattributes` 注释自己点名的风险点已清除。

结构性零的处理是本批的亮点：真实目录当前 sheet 条目没有 `aliases` 字段（禁止别名由尚未交付的 T06 loader 产出），所以第 3 步 `alias_forbidden` 和「禁止集合不相交」不变量在真实目录上永远触不到。两条都用合成索引构造了非零命中并配了「注入违反项→必红」的反向用例，符合「结构性零须配变异证明」的纪律。

删除手写 schema 脚本是安全的：全仓 grep 残留的 `_build_schema`/`_verify_schema` 都是同名的测试函数或另一个域（xlsx diff）的局部函数，无真实调用方。

本批不含任何起子进程的测试、不含消费方扫描器，故「AST 而非文本匹配」「子进程断言输出内容」两条纪律在本批无适用对象；它们适用的是后续 T07/T24。

<details>
<summary>Issues (4)</summary>

1. **任务焦点与交付面错配** — prompt 要求评审的 acnr_targets 闭环/鉴权/422/孤儿清零/release `--check` 属 T05/T07/T14，当前树中无对应模块，本批无法就这些点给结论。非本批缺陷，但需让编排层知晓这些焦点要落到后续批次评审。
2. **A1 口径双写不一致** — `exact_identity._A1_RE`（`[A-Z]{1,3}[0-9]{1,7}`）比 schema `cell_address`（`[A-Z]+[0-9]+`）窄。4 字母列或 8 位行号能过 schema 却被 `cell_of` 判 `bad_a1`。建议两处共用同一常量，或在 design 显式记录两者口径差异与理由。
3. **同名组基线硬编码** — `test_exact_identity.py` 断言 `len(groups)==78`、`unique==70`、`_EXPECTED_NONE_GROUPS` 固定 8 组。目录任何增删即红，且红在断言上不自带「为什么变」。可接受（基线锁），但建议把期望值来源注释清楚或改成夹具，降低与目录演进的耦合。
4. **`cell_of` 的 `in_catalog=false` 语义未在本批被消费方约束** — `cell_of` 对未登记 A1 返回 `ok + in_catalog=False`，这是 R2-F8 追溯路径要用的行为；本批无调用方，正确性只由单测保证，等 T20 接线时需确认消费方按 `in_catalog` 分流而非按 `ok`。属跨批提示，非本批阻塞。

</details>

<details>
<summary>Details</summary>

### 身份判定的 7 步实现与 design 的「6 步」对表

`sheet_of` 按父级定位→sheet_code 精确→禁止别名→sheet_name 唯一→别名唯一→编码词元最长唯一→歧义/未找到实现。design §6.2 把最后的 ambiguous 归在第 6 步文字里，代码拆出独立的第 7 步（`len(multi_hits) >= 2` 时 ambiguous，否则 not_found），行为与 design 等价。文本逐字比较、`cell_of` 仅对 A1 做大写归一而对 sheet 名不归一，这与「不做空白/全半角归一」的设计一致，避免把借名父级与名称所属 sheet 混淆。

编码词元裁决 `_code_token_in` 要求 code 左右相邻字符都不是 `[A-Za-z0-9-]`，这是防止 `H1` 误命中 `H1-1` 文本片段的关键；配套的「最长且唯一」+ 并列即 ambiguous 逻辑正确区分了 `审定表H1-1` 归属到 `H1-1` 而非借名父级 `H1`（`test_step6_code_token_picks_longest_unique` 覆盖）。

候选池选择 `pool_for_token = multi_hits if len(multi_hits) >= 2 else pool` 与 design「第 4/5 步命中≥2 取这些 sheet，否则取 P 内全部」一致。第 5 步别名匹配受 `if not name_hits` 保护，不会与 sheet_name 命中叠加，`multi_hits` 的二选一（`name_hits` 优先）因此不会漏态。

### 契约单一来源与字节相等守卫

`catalog_contract` 把 4 类受控约束（`FUNCTIONAL_TYPES` 10 词表、`PURPOSE_PATTERN` 受控模式、`REGISTRY_VERSION_PATTERN`、三个枚举集合）定义一次，schema 由 `build_schema()` 生成、`schema_json()` 确定性序列化（indent=2、保留中文、尾换行）。`test_controlled_constants_match_schema` 逐值把常量与 schema 节点绑死，`test_controlled_values_match_current_real_catalog` 反向保证词表覆盖真实取值（否则 enum/additionalProperties 会误拒真实数据）——这两条一起避免了「契约收窄把真实目录判红」和「契约放宽成摆设」。

字节相等守卫 `test_schema_file_byte_equal_to_build_schema` 是契约单一化的落地闸门。它在 `autocrlf=true` 的 Windows 上本会被 CRLF 转换打红，`.gitattributes` 的注释自己点了名。实测结论：磁盘文件纯 LF、与 `schema_json()` 逐字节相等，`git ls-files --eol` 返回 `i/lf w/lf attr/text eol=lf`——规则已生效、守卫在本环境成立。该潜在脆弱点已闭合。

四类产物副本变异（词表外 functional_type / `2026.1.1` 旧版本号 / 删 sheet_code / cell 加 project_id+wp_id）各自断言被拒且点名 JSON 路径，覆盖了 enum、pattern、required、`not` 四种约束通道。

### 结构性零的变异覆盖

真实目录 sheet 条目当前无 `sheet_name_aliases`，`_forbidden_aliases(真实目录)` 为空集。由此 `sheet_of` 第 3 步（`alias_forbidden`）与 `forbidden_disjoint_violations(真实目录)` 在真实目录上恒为零——是真实的结构性零。`test_step3_forbidden_alias` 用 D1/D1-1 共享「应收票据审定表」的合成索引触发非零 `alias_forbidden`，`test_forbidden_disjoint_detects_violation` 构造「禁止别名同时是 sheet_name」触发非零违反。两条结构性零都配了可打红的非零用例，符合纪律；真实目录侧则用 `== []` 钉住「当前确实为空」。

### 中文原因与错误码集中表

`reasons.py` 把身份判定、acnr_targets 拒绝分类、取值状态、V2/stale 节点、版本锁快照五组错误码的中文文案收在一处，只依赖标准库（供仅标准库的 `check_ccr_resolve` 等脚本复用）。本批只有 `SHEET_REASONS`/`CELL_REASONS` 被 `exact_identity` 实际消费，其余（`TARGET_REJECT_REASONS`、`CELL_VALUE_REASONS`、`NODE_UNRESOLVED_REASONS`、版本锁文案）是为 T14/T12/T21/T17 预置的常量，当前无消费方——属前置铺垫，不构成问题，但其正确性要等对应批次接线后才被真正验证。

### 删除手写 schema 脚本

`docs/acnr/schemas/_build_schema.py`、`_verify_schema.py` 删除后，全仓 `git grep` 残留项为 `test_catalog_schema_single_source.py` 的测试函数名与 `backend/tests/exports/test_xlsx_diff.py` 的同名局部函数 `_build_schema`（openpyxl xlsx 域，与 ACNR 无关）。无真实外部调用方，删除安全，与 schema 由契约生成的单一来源目标一致。

### 不在本批的任务焦点

`git ls-files` 确认 `acnr_target_values.py`、`strict_model.py`、`catalog_release.py`、`sheet_verdicts.json`、`wp_cell_target.py`、`project_registry_lock.py`、`v2_canonical.py`、`scripts/acnr/generate_catalog.py` 均不在树中。因此：

- **acnr_targets 取值闭环是否真复用公式引擎、鉴权是否正确**：对应 T13/T14/T15，未交付，无代码可评。
- **解析不到/无权/不支持是否一律 422 中文原因**：拒绝分类表 `TARGET_REJECT_REASONS` 已在 `reasons.py` 预置，但编排与端点（T14/T15）未交付。
- **孤儿清零是否未静默丢弃被引用项**：对应 T05 `sheet_verdicts` + T07 发布门禁，未交付。tasks.md T05 明确要求「实施前以 HEAD 现算复核 25 个 addr_id 是否被公式/真库/CCR 引用，被引用不得静默消失」——该纪律尚未到执行点。
- **schema 契约与 `--check` 是否幂等不含时间戳**：`build_schema()` 的输出本身确定、不含时间戳（已验），但 `--check` 入口（T07 `generate_catalog.py --check` / `catalog_release`）未交付，幂等性无法端到端验证。

这些需在后续 P0/P1 批次的评审中落实，不作为本批阻塞项。

</details>

<details>
<summary>File map</summary>

本批 ACNR-foundation 相关改动（提交 `0d0ca8f24`、`d1da8ea95`）：

- `backend/app/services/acnr/exact_identity.py`（新增）——全平台唯一的 sheet/cell/name_owner 精确身份判定，纯函数。
- `backend/app/services/acnr/reasons.py`（新增）——错误码→中文文案集中表，五组常量（本批仅 sheet/cell 两组被消费）。
- `backend/app/services/acnr/catalog_contract.py`（新增）——schema 唯一来源 `build_schema()` + 4 类受控常量 + 确定性序列化。
- `docs/acnr/schemas/global_catalog.schema.json`（重写，LF）——由契约生成。
- `docs/acnr/schemas/_build_schema.py`、`_verify_schema.py`（删除）——手写脚本，无调用方。
- `backend/requirements.txt`——新增 `jsonschema==4.26.0`。
- `.gitattributes`——固定 schema 文件 `text eol=lf`。
- `backend/tests/acnr/test_exact_identity.py`（新增，17 例）——7 步规则逐例 + 真实目录 78 组现算 + cell_of + 不相交不变量 + 变异。
- `backend/tests/acnr/test_catalog_schema_single_source.py`（新增，10 例）——字节相等 + 常量绑定 + 真实目录 0 错误 + 4 快照加载 + 4 变异。
- `.kiro/specs/acnr-foundation-defect-closure/tasks.md`——T02/T03 标完成。

完整 diff：`git diff b5fc200e0 -- backend/app/services/acnr backend/tests/acnr docs/acnr/schemas .gitattributes backend/requirements.txt`

</details>
