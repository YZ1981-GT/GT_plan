# Implementation Plan — adopt 真覆盖 + 刷新取数来源选择

## Overview

顺序即依赖：**先把 adopt 的行集语义补成真覆盖（阶段 0~4），再改弹窗（阶段 5~6）**。
这是用户裁决的顺序，不可颠倒 —— 弹窗上「以在线编辑侧为准，覆盖表单」这句承诺只有在
adopt 真能覆盖时才成立。

🔴 每个实现任务开始前**先重新现读**相关文件（有并发会话在改 `workpaper_sync` 域）。
🔴 判据禁写死 `.vue` 行号与任何计数；锚点用符号名 / 端点字面量 / 形态特征。
🔴 每条「结构性零」结论必配变异证明（同一扫描器在非空场景须命中非零）。
🔴 本 spec **不碰** `stale_deleted` / `shrink_sheet_rows` / `_shrink_managed_table_ref`
（那是 B 线 spec `workpaper-sync-row-deletion-multi-region-propagation`）。
🔴 R3 相关判据**禁写死 104 / 62 这类计数**（跳过清单总数、有无替代路径的条数均为现算值）——
判据写成「现算并与 design ADR-AOS-005 的预期值对账，不符即如实登记差异」，不得断言等于某个常量。

## Tasks

- [x] 1. 现算基线复算与行枚举器可用性普查
  - [x] 1.1 复算 design「§ Overview」的八项现算值并回填 spec
    - 探针放 `backend/scripts/analyze/_aos_*.py`（`_` 前缀 = 用完即删）
    - 逐项复算：`all_store_item_ids` 定义数 / `merge_projection_into_store_rows` 定义数 /
      `iter_store_rows` 定义数 / `ROW_IDENTITY_STORE_KEY*` 赋值处与字面量取值分布 /
      `row_section_field=` 非空字面量处数 / 前端 `adopt-substrate` 引用数 /
      后端 `adopt-substrate` 测试引用数
    - 🔴 与 spec 记录不一致即**更新 spec** 并在本任务下记差异，不得默认沿用
    - 🔴 前端引用为 0 这条须配变异证明：同一扫描器对 `row-name-alignment` 须命中非零
    - _Requirements: 2.3, 4.5_
  - [x] 1.2 普查每个 store item 的行枚举器可用性，产出两张显式清单
    - 逐 adapter 取 `all_store_item_ids()`，再按 `store_item_registry` 找 provider 模块，
      现读其是否暴露可用的 `iter_store_rows` 门面
    - 输出「可枚举」与「不可枚举（含原因）」两张清单；不可枚举清单即 Requirement 4.1 的跳过集合基线
    - 🔴 「读出为空」先排除解析失败：若某 provider 的 `iter_store_rows` 因 import 失败而取不到，
      须与「本来就没有」分开登记（两者处置不同）
    - _Requirements: 4.1, 4.3_

- [x] 2. 真库判别 `changed_item_count` 报 0 的成因
  - 构造两组：(a) substrate 与 store 内容不同（应有变更）(b) 内容相同（应无变更）
  - 观测 `_snapshot_store` 的 after 快照是否看得到 `store_mirror` 的未提交写
  - 结论二选一并登记：「同事务可见性」还是「`applied<=0 and base` 跳过写库」
  - 🔴 必须真库（SQLite 内存库测不出这类事务可见性/数据分布问题）
  - _Requirements: 3.7_

- [x] 3. 新建计划纯函数模块 `adopt_overwrite_plan.py`
  - [x] 3.1 数据模型与稳定摘要
    - `ItemOverwriteDelta` / `OverwritePlan` / `OverwritePlan.digest`
    - digest 必须与清单元素顺序无关（排序后哈希），且对内容变化敏感
    - _Requirements: 1.7, 3.2, 3.3, 4.2_
  - [x]* 3.2 属性测试：Overwrite_Plan 内部自洽
    - **Property 4: Overwrite_Plan 内部自洽**
    - **Validates: Requirements 1.7**
    - 落点**两个文件**（口径 `len(text.split("\n"))`，`check_file_size.py` 两者均 exit=0）：
      `backend/tests/workpaper_sync/test_aos_plan_selfconsistency_and_digest.py`（主体，**654** 行 /
      13 test 函数 / **14 passed**，上一轮交付）+ `test_aos_plan_digest_mutants.py`（**本轮新建**，
      变异反证伴生，**801** 行 · `splitlines()` 口径 **800** = 门禁上限，**31 passed**）⇒ 合计 **45** 例
    - 🔴 **为何抽伴生**：主体交付时 654 行，九组变异 + 收口 + 未污染判据约 330 行 ⇒ 合并后越 800 门禁。
      域内测试侧先例 `test_aos_property_out_of_scope_mutants.py`（由 `..._out_of_scope_rows.py` 切出）
    - 伴生文件**只 import 不另造**：`_assert_property_4` / `_assert_property_6_order_free` /
      `_assert_property_6_content_sensitive` / `_assert_no_concatenation_ambiguity` / `fixed_plan` /
      `_reordered_plan` / `_MUTANT_GROUPS` / `_P46_MUTANT_REDS` / `_expect_red_p46` / `TABLES` /
      `ITEM_PREFIX` 全部取自主体文件。**顶层模块名** import 已直证：
      `TestMutantRedsAreClosed::test_accumulator_is_the_very_same_object_as_the_main_module` 断言
      `main_module._P46_MUTANT_REDS is _P46_MUTANT_REDS` 为 **True**
    - **Property 4 两个断言面都在场**：面 ① 四个计数 == 对应清单长度（字段域取自生产 `_ROW_LIST_FIELDS`，
      **四个全查**）· 面 ② `rows_added`/`rows_deleted`/`rows_updated` **两两**不相交（对子由生产
      `_DISJOINT_FIELDS` 现算 `combinations(…, 2)` 得出，不写死第一对）
    - **§6 收口补齐（本轮的核心欠账）**：`_P46_MUTANT_REDS` 与 `_expect_red_p46` 在主体文件交付时
      调用点现算为 **0** —— 正是本域纪律点名的「写了从未被读的死累计器」。本轮补
      `TestMutantRedsAreClosed` 3 例（参数化对账 / 红数闭合 / 累计器同一实例）+
      `TestProductionModelsAreNotPolluted` 4 例
    - **九组变异逐组 red 数**（§5 跑一轮，全部**进程内源码级**：`inspect.getsource` → 替换唯一锚点 →
      在生产模块 `globals` 的**副本**里 `exec`，生产文件一字不改；🔴 不用 `monkeypatch.setattr` ——
      本域有并发会话，窗口期内会改共用模块行为）：
      **M1_count_from_wrong_list 4**（四个字段逐个「读下一个清单的长度」，参数化 = 生产域 4 字段）·
      **M2_disjoint_gate_removed 3**（不相交门整个摘掉，参数化 = 现算 3 个对子）·
      **M3_only_first_pair_checked 2**（门只查第一对，参数化 = 第一对之外的 2 对）·
      **M4_list_sort_removed 4** · **M5_delta_sort_neutralised 1** · **M6_key_order_belts_removed 1** ·
      **M7_field_omitted_from_digest 4** · **M8_stored_counts_omitted 2** ·
      **M9_list_joined_without_separator 3** ⇒ **合计 24**
    - 🔴 **口径差（不是偏差）**：上面 24 是 §5 各用例**各自一轮**的红数；跑完整文件后
      `_P46_MUTANT_REDS` **终值 48**（8/6/4/8/2/2/8/4/6），因为 `test_every_group_reds_on_every_variant`
      自己把九组**再跑一轮**（它断言的是本轮 `gained == expected`，故终值恰为两轮之和）。两个数各有
      口径、都对
    - **每组都配对照组 + 变异生效断言**：对照组 = 生产实现下判据必绿（M2/M3 的对照组是「生产构造器
      当场抛 `OverwritePlanShapeError`」）；生效断言逐组具体形态 —— M1 核 `count == len(错清单) != len(本清单)` ·
      M2 核相交集合恰 `{'aos46-ov'}` · M3 核**第一对仍被拦**（证明是「只查第一对」不是「门全没了」）·
      M4/M5/M6 核 `twin.digest != mutant.digest` 且该顺序维度**真的换了序** · M7/M8 核该字段确实
      不在 `canonical_form()` 里（`== 生产键集合 - {字段}`）· M9 见 3.3
    - **锚点唯一性两处判据互为第二判据**：`_mutated_source` 内 `count(old) == 1`（变异时）+
      `TestProductionModelsAreNotPolluted::test_production_sources_still_carry_every_anchor`
      （独立复核 **22** 组锚点集合 / **13** 个不同锚点串，且锚点串集合须恰等于按生产域拼出的那一套）
    - **未污染判据 4 例**：变异体 `is not` 原对象 · `__globals__ is not vars(module)`（类无
      `__globals__` ⇒ 借其 `canonical_form` 函数取）· 往变异体 globals 写探针后生产模块不长出同名成员 ·
      生产模块该名仍绑原对象 · 反向对照（同一 `exec` 写进 `vars(dummy_module)` **本身**时模块确实被改）·
      **未变异 re-exec 与生产 digest 逐字符相等**（M6 那类「只变一处」的归因前提）
    - 🔴 **本轮比先例多一层：被变异的是「类」不只是函数** ⇒ `ItemOverwriteDelta` / `OverwritePlan` /
      `_canonical_json` 三者必须 exec 进**同一个** namespace，否则 `OverwritePlan.__post_init__` 的
      `isinstance(delta, ItemOverwriteDelta)` 会拿生产类去判变异实例而当场抛（测的就变成构造器不是
      digest）。这也是主体文件 `fixed_plan` 收 `delta_cls` / `plan_cls` 两个参数的原因
    - 🔴 **三处锚点坑（现算实证，不是推测）**：① `sort_keys=True` 在 `_canonical_json` 源码里命中 **2** 次
      （docstring 里也解释了它）⇒ 锚点必须用整条 `return json.dumps(...)` ② `len(self.rows_deleted)`
      命中 **2** 次（`_validate_scope_and_skip` 的 f-string 里也有）⇒ 锚点用整条 `return len(self.X)`
      ③ M5 刻意不摘 `sorted(` 本体而是中性化排序**键**（`key=_canonical_json` → `key=lambda _form: 0`）
      —— 摘本体会留下 `list(生成器, key=…)` 这种 TypeError，「红」就只是变异体语法炸了
    - 🔴 **M1 能不能打红的要害**：`fixed_plan` 默认四个清单**长度都是 2** ⇒「读错清单」算出的计数
      仍然是 2、面 ① 照样通过、变异完全隐形。故 `_m1_kwargs()` 按 `len(_LIST_FIELDS) - index` 造
      递减长度（4/3/2/1，现算）并当场断言两两不同
    - 🔴 **§6 判据逐处变异验证过有牙（守卫写完必须逐处变异，未变异基线 3 passed 绿）**：
      ① 某组红不再累计（本地 shadow `_expect_red_p46` 对 M5 只吞不记）⇒ **RED**
      （`test_every_group_reds_on_every_variant`，`gained != expected`）·
      ② 参数化个数与生产域脱钩（M1 取值域改窄成字面 `("rows_added",)`）⇒ **RED**
      （`test_parametrisation_tracks_the_production_domains`）·
      ③ 某组登记了却无红点（M2 红点换成裸 `pytest.raises`）⇒ **RED**（`set(sites) == set(_MUTANT_GROUPS)`）·
      ④ 九组红点全删空（全部 `_expect_red_p46` 换成本地不登记同义体）⇒ **RED**（同 ③ 那条）
    - 🔴 **自检 ④ 的归因更正（登记，因为差点写成假结论）**：我最初的 ④ 变异是「清空 `_M9_ANCHORS`」，
      它确实打红，但红在**前一条** `set(_P46_MUTANT_REDS) == set(_MUTANT_GROUPS)` 上（M9 一次都没跑
      ⇒ 累计器少一个 key），**不是** `all(value > 0 for expected.values())` 那条后门塞。只把 `_group_plan`
      里 M9 的第 4 位（生产域期望数）改成 0、保留装饰器取值域，让 §5 照常跑满、累计器九个 key 齐全，
      才让那条塞**自己**成为首个失败断言（实测 `E AssertionError: 某组的期望红数为 0（…）`）
      ⇒ **教训：「某条断言有牙」必须让它自己是首个失败的那条**，否则只证明了「这个测试会红」
    - **定向回归 14 文件**（本轮新文件 + 主体 + 3.x/4.x 的 11 份 + `tests/test_lazy_import_resolvability.py`）：
      **325 passed / 0 failed**（基线 **294** + 本轮 **31**）。生产文件行数复核未变：
      `adopt_overwrite_plan.py` **781** / `adopt_overwrite_compute.py` **506** / `adopt_row_reader.py` **768**，
      主体测试文件仍 **654** ⇒ 本轮**未改任何生产代码**，也未改主体文件已有断言
    - **未发现生产缺陷**：九组变异全部是本轮人为构造，`ItemOverwriteDelta` / `OverwritePlan` /
      `_canonical_json` 在生产实现下四个判据全绿，无需 `xfail` 钉住任何诉求
    - 🔴 **建议（未改 design / requirements，仅登记）**：`_P46_MUTANT_REDS` / `_expect_red_p46` /
      `_MUTANT_GROUPS` 声明在主体文件而只在伴生文件被用 —— 现行安排是刻意的（主体的
      `TestPropertiesDidNotRunVacuously` 只读 `_SAW`），但「主体交付时调用点为 0」这件事本身说明
      **声明与使用分家最容易留死累计器**；后续同型任务宜把累计器与它的收口判据放同一文件，或在
      声明处就写一条「本 dict 必须被某处读」的自检
    - 探针已清理（`backend/scripts/analyze/_aos_p46_*.py` 7 个；🔴 未动其它会话的 `_aos46p_*` /
      `_aosp2_*` / `_aos_adr005_verify.py`）
  - [x]* 3.3 属性测试：plan_digest 顺序无关且内容敏感
    - **Property 6: plan_digest 顺序无关且内容敏感**
    - **Validates: Requirements 3.3**
    - 落点与例数、九组 red 数、收口 / 未污染判据、逐处变异自检、定向回归 **325 passed / 0 failed**
      全部与 Task 3.2 同一对文件，不复述 —— 见上。本条只记 P6 专属的断言面与实测结论
    - **两半写在一个测试函数里**（design § prework 合并记录：「顺序无关与内容敏感是同一条 property 的
      两个断言」），拆两个会让「摘要把整个计划都忽略掉」这种实现在前一半通过、后一半失败
    - **面 ①（顺序无关）三个顺序维度全部被换过**，且 `_reordered_plan` 返回「真的换了序的维度名」供
      反空转断言（一个维度都没换动时「digest 不变」是恒等变换上的废话）：清单元素序（**M4** 4 红，
      逐字段）· deltas 排列（**M5** 1 红）· 两个 Mapping 键序（**M6** 1 红）
    - 🔴 **M6 的实测结论：键序有「两条皮带」，只摘一条不红** —— `OverwritePlan.canonical_form` 的
      `dict(sorted(...))` 与 `_canonical_json` 的 `sort_keys=True` 互为兜底。M6 用例**先实测**
      「只摘 `dict(sorted(...))` 仍绿」再两条同摘才打红 ⇒ 这不是判据没牙，是纵深防御；不先证这一条，
      本组会被误读成「摘一条就该红」而误判判据失效
    - **面 ②（内容敏感）两个被改对象都在场**：任一**行身份**（改一个字符，新串一律带 `~` 而 `~` 不在
      `_IDENTITY_ALPHABET` 内 ⇒ 绝不与既有身份相撞而误触构造器的抛）+ 任一**计数**（三个方向：
      追加一条 +1 / 摘掉一条 −1 / 两个 Mapping 里**存起来的**逐表行数 +1）。**M7** 4 红（某个行清单
      整条不进 digest）· **M8** 2 红（某个逐表行数 Mapping 不进 digest）
    - **digest 形态与稳定性**（主体 `TestDigestShapeAndStability` 4 例）：64 位小写 hex 且多次调用稳定 ·
      同内容不同对象的两份计划 digest 相等（摘要吃内容不吃对象身份）· 中文身份参与摘要且不与 ASCII
      近邻相撞（`ensure_ascii=False` 那一档；真实树上身份确含 `运输费用/营业收入` 这类自由文本）·
      `DIGEST_FORMAT` 带版本段（归一形态改了必须在版本号上可见，而不是静默算出另一个合法 hex）
    - 🔴 **digest 拼接歧义实测结论（三边界在生产实现下全部保持，且三条断言各自独立承重）**：
      **① 元素边界** `['a','bc']` 与 `['ab','c']` digest 不同 —— M9/`elements` 把 `sorted(self.rows_added)`
      换成 `"".join(sorted(...))` 后两者都变成 `'abc'` ⇒ 该条打红（专属文案 `清单被拼成一串`）·
      **② 字段边界** 同一批身份在追加 / 删除之间互换后 digest 变 —— M9/`fields` 把两清单并成一个
      `sorted(added + deleted)` 后 `{a,b}/{c,d}` 与 `{c,d}/{a,b}` 都得 `["a","b","c","d"]` ⇒ 打红
      （`字段边界被抹平了`）·**③ 表边界** 逐表行数分布不同而总和相同时 digest 仍不同 ——
      M9/`tables` 把 `store_rows_by_table` 换成 `sum(...)` 后 `{t1:1,t2:22}` 与 `{t1:22,t2:1}` 撞
      （两者 `store_row_count` 实测均 **23**）⇒ 打红（`摘要只吃了派生总数`）
    - 🔴 **三边界变异刻意**互相隔离**（每个只踩穿一条断言、另两条仍绿），红了还要核**专属文案**：
      三条断言写在同一个判据函数里，若一个变异同时踩穿多条，红只能证明「那个判据能为 False」，
      证不出**每一条**都有牙。`fields` 那组为此专门保留了元素边界（用 `sorted(list+list)` 而不是
      `"".join`），并在生效断言里正面验「元素边界仍在」
    - 🔴 **Property 4 面 ② 与 Property 6 的判据分工登记**：`rows_ghost_dropped` **刻意不在**
      `_DISJOINT_FIELDS` 内（连带约束 `ghost ⊆ rows_added` 归 Property 3 / Task 4.5），但它**在**
      `_ROW_LIST_FIELDS` 内 ⇒ 面 ①、M4、M7 都覆盖它。主体文件有一条断言钉死这个分工
      （`"rows_ghost_dropped" not in _DISJOINT_FIELDS`），理由是 `fixed_plan` 的默认 ghost 是 added
      的子集 —— 那条域一变，本轮全部例子级锚点会连带失效
  - [x] 3.4 `RowReader` 适配层
    - 只做对 provider 既有 `iter_store_rows` 门面的薄适配；取不到即返回 None
      并由调用方记 `skipped_reason`
    - 🔴 **禁**自造 `row.get("rowId")` 兜底（行身份键现算多种取值）
    - _Requirements: 4.1, 4.4, 4.5_
  - [x]* 3.5 属性测试：行身份识别与键名无关
    - **Property 10: 行身份识别与键名无关**
    - **Validates: Requirements 4.5**
  - [x]* 3.6 属性测试：非法载荷一律 fail visible
    - **Property 9: 非法载荷一律 fail visible**
    - **Validates: Requirements 4.4**
  - [x] 3.7 R3 兜底路径：全域 spec 索引 + 引擎 `iter_store_rows(spec, payload)`
    - 依据 = design **ADR-AOS-005**（用户裁决采纳 R3，解析器来源优先级扩为三级）
    - 在 `adopt_row_reader.py` 实现第 ② 级：取本 item 的行表 spec，逐条调引擎
      `phase5_row_table_sheet.iter_store_rows(spec, payload)`；身份键与分区字段全取自**声明**
      （`row_identity_key` / `row_section_field`），🔴 **禁**任何键名字面量兜底
    - 🔴 全域 spec 索引**必须覆盖伴生模块**：D1 的 **17** 条 spec 住在 `phase5_d1_expansion`，
      而 registry 指向的 `phase5_d1_notes_receivable` 没有 `managed_row_table_specs()`
      ⇒ **配变异证明**：同一索引器「只看 registry 指定模块」这一变体必须漏掉 D1 的 17 条
      （漏不掉就说明索引器根本没在按模块取 spec，判据失效）
    - 🔴 **门面优先、R3 兜底**；对「两路都可用」的 item 做**一致性对账** ——
      同一载荷两路枚举出的**身份集合必须相等**，不等即 fail visible
      （不得取并集、不得择一静默；这是防「换了条路悄悄换了语义」）
    - 🔴 逐 spec 枚举**必须**按 `(store_item_id, row_section_value)` 去重 ——
      `D1-memo-rows` / `I5-2-rows` 各 2 个 spec 却无分区字段，不去重会把同一行数两次
      （`_declared_scopes` 只对 `(table_key, 分区)` 整对去重，不替本任务兑现这条）
    - 解掉 `G1-2-rows` 覆盖不全：**实测断言 3 段身份都被 yield**
      （`acctClass` = `trading` / `classified_fvpl` / `designated_fvpl`）
    - 解掉 `row_reader_bound_to_other_entry` **4** 条（`G3-2-detail-rows` / `G4-7-items` /
      `G5-2-rows` / `G6-5-fair-value-data`，item_id 取 design §4.1b (6) 的 Task 3.4 勘误值）：
      改走 R3 后断言转为可枚举
    - 更新 `RowReaderResolution` 的棘轮基线：`is_unruled_shape` 冻结集合应变为**空集**；
      🔴 若不为空，**如实登记剩余条目与原因，不得为凑空集而放宽判据**
    - 复算跳过清单总数（design 预期 104 → 62，🔴 **现算为准**，不符即登记差异与归因）
    - 🔴 **禁缓存 spec 清单**：`managed_row_table_specs()` 内有灰度 manifest 判断，
      缓存会让「开关一开就多两段」被一次进程内的旧结论盖住
    - _Requirements: 4.1, 4.4, 4.5_

- [x] 4. 实现删除侧剪枝与计划计算
  - [x] 4.1 `prune_undeclared_rows`：按声明身份集 + 分区剪枝
    - 作用域门：只处理 `table_key` 在 `row_keys` **键集合**里的表
    - 空值二分：不在键集合 ⇒ 不碰；在键集合但值为空元组 ⇒ 清空
    - 分区门：同一载荷承载多分区时只删本次声明分区的行
    - 返回 `(新载荷, 被删身份)`，纯函数、不碰 DB
    - _Requirements: 1.2, 1.3, 1.4_
  - [x] 4.2 `compute_overwrite_plan`：聚合逐 item delta 与两侧行数
    - 逐 item 算 added / deleted / updated / ghost_dropped 四清单与计数
    - 不可枚举形态的 item 记 `skipped_reason` 并进 `skipped_items` 显式清单
    - 落点 = **伴生模块** `adopt_overwrite_compute.py`（域内第四次同样处置：
      `adopt_overwrite_plan.py` 交付 4.1 后 781/800 只剩 19 行、`adopt_row_reader.py` 768/800）；
      依赖方向**单向**（新模块 → `adopt_overwrite_plan`，AST 实测主模块反向 import 0 处、
      且新模块不依赖 `adopt_row_reader*`，reader 由调用方传入）
    - 🔴 `rows_ghost_dropped` **计划期不可兑现**（裁定）：幽灵行门的三个输入（`spec` +
      `managed_field_specs` 的锚点 json_path / merge **之后**的行 / merge 私有的两处 continue）
      没有一个在本函数输入面上 ⇒ 预测就是复现引擎判据 = 第二真源。改为**观测**：Task 6.3 在
      `mirror_projection_into_store(commit=False)` 之后按「plan.rows_added − merge 后真实存在的
      身份」取得，经新增入参 `ghost_dropped_by_item` 回喂重算。连带后果：`ghost ⊆ rows_added`
      ⇒ Requirement 3.8 与 Property 3（Task 4.5）须按 `rows_added − rows_ghost_dropped` 对账
    - 🔴 交给 Task 6.1 的接线前提：现算恰 **3** 条 item 的 reader `declared_scopes` 为空
      （`D4-2-rows` / `D2-detail-rows` / `H1-8-rows`，均为裸 `_FacadeRowReader`、provider 无
      `managed_row_table_specs` 且全域 spec 索引亦无）⇒ 本函数**当场抛**（与 `prune_undeclared_rows`
      同判据，且 `SkipReason` 六成员封闭无一匹配）。其 table_key 有现成声明 = 门面定义模块的
      `ROWS_TABLE_KEY`（`revenue_detail_rows` / `receivable_detail_rows` / `disposal_check_rows`），
      Task 6.1 经 `item_scopes` 传入即可（实测接管后可算）
    - 🔴 `SkipReason.no_store_item` 的登记方式（Task 3.1 留给本任务的裁决）：**登记，第一位放
      adapter_id**（现算 B 分母 2 条：`a51.cashflow_audit` / `c2.control_test_summary`）
    - 现算基线（禁写死）：B 分母 **51** adapter / **129** item；`diagnose_row_reader` 顶层
      可枚举 **67**（`EngineRowReader` 43 / `ReconcilingRowReader` 21 / `_FacadeRowReader` 3）、
      跳过 **62**（`item_blind` 54 + `absent` 8）+ adapter 级 `no_store_item` 2、
      `is_unruled_shape` **0** ⇒ ADR-AOS-005 的「104 → 62」实测成立
    - _Requirements: 1.1, 1.5, 1.6, 1.7, 3.1, 3.2, 4.1, 4.2_
  - [x]* 4.3 属性测试：声明侧行集等式
    - **Property 1: 声明侧行集等式**
    - **Validates: Requirements 1.1, 1.3, 1.5**
  - [x]* 4.4 属性测试：作用域外的行逐元素不变（参数化 table / 分区两维）
    - **Property 2: 作用域外的行逐元素不变**
    - **Validates: Requirements 1.2, 1.4**
    - 落点**两个新建文件**（口径 `len(text.split("\n"))`，两者 `check_file_size.py` 均 exit=0）：
      `backend/tests/workpaper_sync/test_aos_property_out_of_scope_rows.py`（主体，**618** 行，
      9 例）+ `test_aos_property_out_of_scope_mutants.py`（变异反证伴生，**599** 行，13 例）
    - 🔴 **为何抽伴生（两级）**：① 不追加进 4.3 的 `test_aos_property_plan_rowsets.py` —— 它交付后
      **753** 行，`.py` 门禁 **800** ⇒ 余量 47 行装不下两维判据 + 变异反证；② 主体与变异再分两份
      —— 主体写到第 4 节即约 500 行，变异反证本体 328 行 ⇒ 合并后 **1217** 行，越门禁 417 行。
      域内测试侧先例 `test_aos_property_unreadable_payload.py`（由 `test_aos_property_row_identity.py`
      切出）；被切一侧文末均留指针注释
    - 伴生文件**只 import 不另造**：判据 `_assert_property_2` 与 (b) 维建造器 `_b_payload` /
      `_b_readers` / `_p2_spec` / `_section_field` / `_identity_seq` 全部从主体文件取。🔴 import
      用**顶层模块名**（该目录无 `__init__.py`，pytest `prepend` 模式）—— 写成 `tests.workpaper_sync.…`
      会拿到第二个模块实例，模块级红数累计器 `_P2_MUTANT_REDS` 就分家、§6 收口判据取到空 dict
    - 🔴 **不复用 4.3 的 `_MUTANT_REDS`**：那个 dict 的收口判据是 `set(...) == set(_MUTANT_GROUPS)`
      恰三组（M1~M3），写进本轮组名会让**它**打红 ⇒ 另立 `_P2_MUTANT_REDS`。同理不动
      `_assert_property_1`（Property 1 的唯一判据，两者互不调用）
    - **两维**（Property 2 原文的两个要点，各自参数化 reader 实现 × 载荷形态 × 身份键）：
      **(a)** `table_key` 不在 `row_keys` **键集合**中的表 —— 复用 `_scenario(mode="undeclared")`，
      4.3 只断言过**集合**相等，本轮补序列 + 对象身份 + 零删除 `is`；
      **(b)** 同一载荷内不属本次声明分区的行，三类行**交错**在场（`_b_payload`）：兄弟分区（有 spec、
      `section_of` 判得出，但其 table 不在 `row_keys`）+ 分区值**未被任何 spec 覆盖**（reader 根本
      枚举不到）+ 作用域内的行（其中一部分**真被删**，否则「不变」在空集上恒真）
    - 🔴 **逐元素判据的粒度（两档，按载荷形态分流）**：载荷是**已解析序列**时验到**对象 `is` 相等**
      （`all(k is e for k, e in zip(kept_outside, outside))`，兑现 `prune_undeclared_rows` docstring
      「保留的行对象原样复用，不复制」的字面承诺）；是 **JSON 文本**时 prune 内部必须先解析
      （`_as_row_list`）⇒ 对象身份无从谈起，降级为「逐元素 `==` + **身份序列**相等」。
      两档之上再加两条与形态无关的：**全序列保序**（留下的行 == 原序去掉被删的）+ **零删除 ⇒
      `pruned is payload_before`**（「连重序列化都不会发生」那条字面承诺）。🔴 集合相等在此不够：
      prune 是**按位置摘**（`[element for ordinal, element in enumerate(rows) if ordinal not in doomed]`）
      ⇒ 顺序变了即说明实现改成「从 `reader.iter_rows` 重建」，而那会连未被枚举的分区值一起丢
    - 🔴 **分区字段名取自声明，本文件无任何字段名字面量（含 `"section"`）**：取值域 =
      `declared_section_fields()`（走 `global_spec_index()` 取 `RowTableSheetSpec.row_section_field`
      的非空取值）。证明判据 `TestSectionFieldComesFromDeclaration` 用 **AST `ast.Constant[str]`**
      扫本文件全部字符串常量并断言与取值域**零交集**，另配变异对照（对已知含字面量的样本必命中）。
      🔴 此处必须 AST 不能文本匹配：`section_field` / `section_of` / `_SECTION_FIELDS` 这些**标识符**
      都含子串 `section`，而现算取值域里恰有一个就叫 `section` ⇒ 只数子串会把每个标识符都算成硬编码
    - **四组变异反证的 red 数**（全部**进程内**源码级：`inspect.getsource` → 替换唯一锚点 → 在生产
      模块 `globals` 的**副本**里 `exec`，生产文件一字不改；🔴 不用 `monkeypatch.setattr` —— 本域有
      并发会话，即便自动还原，窗口期内也改了共用模块的行为）：
      **M1_get_instead_of_in** red **6**（`in` → `.get(table_key) or ()`，两条锚点须同换否则撞
      `KeyError`；每个 reader 红 2 次 = 计划侧 `_in_scope_by_section` + 删除侧 `prune`，×3 reader）·
      **M2_section_gate_removed** red **2**（分区门换成全量差集 ⇒ 兄弟分区被删，×2 reader）·
      **M3_section_value_stripped** red **2**（`section_value_of` 做 `strip()` ⇒ 未声明分区值 `" X"`
      被归一进已声明桶 `"X"`，经 `_SectionProxyReader` 把变异体接上生产那条杆子，×2 reader）·
      **M4_rebuilt_from_reader** red **2**（按 `reader.iter_rows` 重建载荷 ⇒ 未被枚举的分区值凭空
      消失 + 多段 reader 逐 spec yield 致原序丢失，×2 reader）。合计 **12** 红
    - 每组变异前均先跑**对照组**（生产实现下判据必绿）+ **变异生效断言**（如 M1 须确认整表真被清空、
      M4 须确认未枚举分区值真消失）⇒ 「红」不是因为变异没生效或前提已变
    - 🔴 **登记一条不可达结论**（任务书第三组变异「把未声明分区值归一成 `None`」）：`in_scope` 只在
      存在 `section is None` 的 scope 时才有「无分区」桶，而 `_declared_scopes` 的
      `(str(row_section_value or "") if section_field else None)` 决定了 —— `section_field` 非空时
      分区值恒为 `str`（空值得 `""`，那是**退化声明**，prune 与 `_in_scope_by_section` 两处都当场抛），
      `section_field` 为空时才得 `None` 而那时**不存在**未声明的分区值（`section_of` 恒 `None`）
      ⇒ 归一成 `None` 只会把行放进一个**不存在**的桶，行仍被保留，判据打不出红。结构性依据本身也是
      判据（`TestNoneCollapseIsUnreachable`，逐条现算），可达同型改由 M3 / M4 两种真实形态各承一组
    - **§6 收口（本轮补齐，非原交付）**：`_P2_MUTANT_REDS` 原为「写了从未被读」的死累计器，且主体
      文件末尾指针已承诺「未污染生产模块」判据落在伴生文件 ⇒ 补 `TestMutantRedsAreClosed`（自跑一轮
      四组，断言逐组红数 == **AST 现算的 `_expect_red_p2` 调用点数 × 现算 reader 实现数**，禁写死；
      另断言参数化取值个数 == 现算 reader 实现数、登记组名 == 红点覆盖组名、期望红数全 > 0 以堵
      「红点全删空 ⇒ `gained == expected` 恒等」）+ `TestProductionModulesAreNotPolluted`
      （变异体 `is not` 原对象 · `__globals__ is not vars(module)` · 往变异体 globals 写探针后生产
      模块不长出同名成员 · 生产模块该名仍绑原对象 · 五组锚点在生产源码里仍**恰 1** 次）
    - 🔴 §6 判据**逐处变异验证过有牙**（守卫写完必须逐处变异）：①某组红不再累计 ②参数化个数与
      reader 实现数脱钩 ③某组登记了却无红点 ④四组红点全删空 —— 四处全打红，未变异基线通过
    - **验证**：主体 9 例 + 伴生 13 例全绿；定向回归 12 文件（本两份 + 4.5/4.6/4.7/4.8 + 3.x 的
      row_reader 两份 + row_identity + unreadable_payload + `test_lazy_import_resolvability.py`）
      **280 passed / 0 failed**；两文件 `check_file_size.py` exit=0
    - 🔴 **建议（未改 design / requirements，仅登记）**：Property 2 的 (b) 维文本宜补一句限定
      「……不属本次 projection 声明分区的行（含**未被任何 spec 覆盖**因而读不到的分区值）」——
      现行文本读起来只覆盖「兄弟分区」，而实测第二类（读不到的分区值）才是 M4 唯一能打红的那类
    - 🔴 **登记：上一轮报的 `NameError: name 'Any' is not defined` collection error 不可复现**。
      现读伴生文件确认 import 区齐全（15 条 import，含 `from typing import Any`），单跑 13 passed、
      与主体合跑 22 passed、四文件合跑 71 passed、12 文件 280 passed 全绿。排除的成因：
      **`pytest-randomly` 在本 venv 并未安装**（`pip show` 报 not found、`--randomly-seed` 是
      unrecognized argument）⇒ 随机序假说不成立。前一轮的诊断错在拿 `read_file` 的**片段当文件头**
      并据此断言「整个 import 区都没写」，真实行数 **599**（报告里的 328 也不对）⇒ 教训：
      「文件缺 X」这类断言必须整文件读或 AST 现算，禁拿片段外推
    - 🔴 **登记一处口径差（不是偏差）**：上面逐组红数 **6/2/2/2 合计 12** 是四个专项变异用例
      **各自一轮的红数**；而跑完整文件后 `_P2_MUTANT_REDS` 的**终值**是 **12/4/4/4 合计 24**，
      因为 `TestMutantRedsAreClosed::test_every_group_reds_on_every_reader` 自己又把四组**再跑一轮**
      （它断言的是本轮 `gained == expected`，故终值恰为两轮之和）。两个数各有口径、都对 ⇒
      **不改上面的记载**；另实测主体与伴生两模块取到的累计器**逐值相同**，即顶层模块名 import
      确实避开了 docstring 警告的「模块实例分家」
  - [x]* 4.5 属性测试：幽灵行门语义不变且被如实登记
    - **Property 3: 幽灵行门语义不变且被如实登记**
    - **Validates: Requirements 1.6**
  - [x]* 4.6 属性测试：不可枚举形态载荷不被改动且被登记
    - **Property 8: 不可枚举形态的载荷不被改动且被登记**
    - **Validates: Requirements 4.1**
    - 落点 `backend/tests/workpaper_sync/test_aos_property_nonenumerable_skip.py`（**774** 行 /
      口径 `len(text.split("\n"))` / `check_file_size.py` exit=0）
    - **20 例全绿**：主 property 1 + `TestNonEnumerableCensusIsLive` 3 +
      `TestNonEnumerableShapeInScopeFailsVisible` 2 + `TestMutationCounterProof` 4 +
      `TestProperty8DidNotRunVacuously` 10
    - Property 8 的**两个断言面都在场**：① 载荷**对象 `is` 相等**（不止 `==`）② 该 item 确实出现在
      `skipped_items`
    - 🔴 **`is` 而非 `==` 是本 property 的要害**：`test_m2_reserialisation_is_invisible_to_eq_but_caught_by_is`
      —— 载荷被重序列化一遍后 `==` 仍为真，只有 `is` 能抓到 ⇒ 判据若写 `==` 就会放过「载荷被原样
      重写一遍」这类真实危害（JSON 文本形态下尤甚）
    - 变异反证 3 组：**M1** 跳过的 item 没有 delta 就从清单里消失 · **M2** 重序列化对 `==` 不可见
      但被 `is` 抓到 · **M3** 域外 reason 静默变成合法成员；另有
      `test_mutation_did_not_touch_the_production_modules` 卫生判据（与 4.4 §6 同形）
    - **反空转 10 例**（`TestProperty8DidNotRunVacuously`）：reason 域取自**活枚举**且闭合于 6 ·
      每个 reason 成员都被 property 走过 · 每个 reason 都能抵达 `skipped_items` · 所有载荷形态都被
      走过 · 两种 carrier 形态都在池里且各自 `is` 成立 · JSON 文本经解析但不重序列化 ·
      🔴 **对照组真的改动了可枚举载荷**（否则「不变」在空集上恒真）· 跳过的 item 不是意外可枚举 ·
      delta 模型里的 skip 门是活的 · §5 用的源码锚点是活的
    - **验证**：单跑 20 例全绿；与 4.4 两份 + 4.7 四文件合跑 **71 passed**；12 文件定向回归
      **280 passed / 0 failed**
  - [x]* 4.7 单测：`in` 与空元组的显式对照
    - 两例：table 不在 `row_keys` 键集合 ⇒ 行不变；在键集合但值为 `()` ⇒ 清空
    - 这是 prework 把 AC 1.3 降为边界后留的可读性锚点
    - 落点 `backend/tests/workpaper_sync/test_aos_declared_table_binary.py`（**新建伴生**，
      **413** 行 / 口径 `len(text.split("\n"))` / `check_file_size.py` exit=0）。4.8 留的 93 行
      余量装不下（两例 + 对照 + 两组变异 + 反空转 = 413）⇒ 按其自己给的处置抽伴生，
      4.8 一条断言未改、仅在其文末回填指针（现 **713** 行，exit=0）
    - **20 例全绿**（3 判据 × 3 reader + 2 变异 × 3 reader + 2 变异卫生 + 3 反空转）；
      被测对象 `adopt_overwrite_plan.prune_undeclared_rows`，**无 `@given`**（本任务是例子级对照）
    - 两例实测（三个 reader 实现逐个一致）：**不碰** `new is payload` = True / `deleted = ()` /
      n=0；**清空** `new is payload` = False / `deleted = ('aos47-r1','aos47-r2','aos47-r3')` /
      n=3 / 剩行 `[]`；两例均不原地改动入参
    - 「行为不同」那条断言的形态 = 同一载荷对象 + 同一 reader **只换 `row_keys`**，
      断言 `untouched == () and cleared != ()` **且** `len(untouched) != len(cleared)`
      **且** `(len 不碰, len 清空) == (0, 3)` ⇒ 两种输入被混成一种必打红
    - 变异反证（**进程内**源码级，复用 4.5 的 `_source_mutant`，生产文件一字不动，
      另有实时锚点唯一性 + 无回写判据）：**M1** `in` → `.get(table_key) or ()`（五行整块单锚点，
      count=1）⇒ 「不碰」例红 **3**（3 reader 各 1）、「清空」例仍绿 3；**M2** `declared is None`
      → `not declared` ⇒ 「清空」例红 **3**、「不碰」例仍绿 3 ⇒ **两组各只打红一侧**，
      少任一例都会放过一类真实实现错误
    - 🔴 M1 刻意不用「只摘守卫」：那会撞 `KeyError` 而不是模拟真危害（整表被清空）
    - _Requirements: 1.3_
  - [x]* 4.8 守卫：跳过白名单无失效条目
    - 对跳过清单里每个 item 现读其 provider，断言确实取不到行枚举器
    - 反向变异：塞一个可枚举的 list-store item 进白名单 ⇒ 判据必须打红
    - 落点 `backend/tests/workpaper_sync/test_aos_skip_whitelist_guard.py`（**新建**，
      既有四个 AOS 测试文件 389~438 行、逼近 800 门禁 ⇒ 不往它们加；29 例全绿 / 现算 **707** 行 /
      `check_file_size.py` exit=0 / 末尾留 Task 4.7 落点且标注余量约 93 行）
    - 🔴 行数口径教训：PowerShell `Measure-Object -Line` 对本文件少报 **176** 行（报 531 / 真值 707）
      ⇒ 行数一律 Python `len(text.split("\n"))`（平台铁律 ⑦⑩ 再次命中）
    - 🔴 判据是**两检并列**（design §4.1b(7) 第 3 条「必须逐条核原因类型，不能只核是否取不到门面」）：
      检① `diagnose_row_reader` 顶层给不出 reader · 检② 登记的 `SkipReason` 成员 == **独立第二判据**
      （只用 `importlib`/`inspect`/门面 `__module__` 现读重算）得出的成员。两检互不冗余已各配变异证明
    - 现算桶大小（B 分母 51 adapter / 129 item）：可枚举 **67**、跳过 **62**（`item_blind` 54 +
      `absent` 8）+ adapter 级 `no_store_item` **2**、`is_unruled_shape` **0**；
      独立第二判据与生产判定逐条比对 **0 处不一致**
    - 🔴 三个空桶（`import_failed` / `item_unresolvable` / `row_reader_bound_to_other_entry`）
      **如实登记**为 R3 采纳的后果，各配变异对照：import 不存在的模块 → `ModuleNotFoundError`；
      合成 item-aware 抛错门面（非 re-export）→ `item_unresolvable`；**真实数据** 4 条 G 的门面路
      至今仍判 `row_reader_bound_to_other_entry`（且它们已不在跳过清单里）
    - 🔴 计数一律现算：跳过总数改用**棘轮**（`<= 62`，只许变短），不写等值断言 ——
      「恰等于 ADR §3 预期」那条对账归 Task 3.7 的 `TestSkipCensusRecount`，本文件不复述
    - 变异 red 数（真跑，poison 普查 / 拆掉某一检后重跑 29 例）：可枚举 list-store item
      （`D4-2-rows`）塞进白名单 **4 red** · R3 救回的 item 塞进白名单 **4 red** ·
      原因换成另一成员 **2 red** · 完整性检禁用 **2 red** · **拆掉检② 8 red**（design 那条断言的直证）·
      拆掉检① **2 red**
    - 僵尸方向两处：白名单条目现算不得可枚举 + 不得命中全域 R3 spec 索引（后者配「索引对可枚举侧
      命中非零」对照）；静态基线只有空桶清单一处且用**相等**断言 ⇒ 桶一旦不空即红
    - 🔴 `SkipReason` 六成员**封闭未动**；另有「无后门」判据：六成员每一个都须有可验证条件能产出它
    - 文件末尾留 `# ── Task 4.7 落点 ──`（本任务未替 4.7 实现任何部分）
    - _Requirements: 4.3_

- [x] 5. Checkpoint — 纯函数层全绿
  - Ensure all tests pass, ask the user if questions arise.
  - **定向回归 14 文件 `325 passed / 0 failed`**（编排侧独立实测，非仅采信 subagent 报告）：
    3.x 的 `test_aos_row_reader_adapter` / `test_aos_row_reader_r3` / `test_aos_property_row_identity` /
    `test_aos_property_unreadable_payload` · 3.2+3.3 的 `test_aos_plan_selfconsistency_and_digest` +
    `test_aos_plan_digest_mutants` · 4.x 的 `test_aos_property_plan_rowsets` /
    `test_aos_property_out_of_scope_rows` / `test_aos_property_out_of_scope_mutants` /
    `test_aos_property_ghost_gate` / `test_aos_property_nonenumerable_skip` /
    `test_aos_declared_table_binary` / `test_aos_skip_whitelist_guard` ＋
    `tests/test_lazy_import_resolvability.py`
  - **回归面完整性已现算核对**：全仓 grep `backend/tests/**/*.py` 里对四个纯函数模块
    （`adopt_overwrite_plan` / `adopt_overwrite_compute` / `adopt_row_reader` /
    `adopt_row_reader_r3`）的引用，命中文件**全部落在上述 14 文件内** ⇒ 本 checkpoint 无漏测面
  - 🔴 **禁跑整目录**：`tests/workpaper_sync/` 整目录跑实测**超 15 分钟超时**（编排侧踩过一次）
    ⇒ 后续 checkpoint 一律用定向清单，并把新增文件追加进清单
  - 🔴 **`pytest-randomly` 在本 venv 并未安装**（`pip show` 报 not found、`--randomly-seed` 是
    unrecognized argument）⇒ 先前「随机序可能触发 collection error」的假说不成立，记录在此免得
    后续任务再查一遍
  - 🔴 **`check_file_size.py` 全仓跑 exit=2 / 138 个文件超限或膨胀，属预存债务**：本 spec 新增的
    两个测试文件与四个 `adopt_*` 生产模块**均不在**该清单内 ⇒ 本轮未增加门禁债务。判断新文件是否
    合规须**带文件名参数**跑，全仓跑的 exit code 读不出本轮结论
  - 🔴 **探针残留待 Task 14.1 清理**：`backend/scripts/analyze/` 下仍有 `_aos44p_*`（4 个）/
    `_aos46p_*`（7 个）/ `_aosp2_*`（4 个）/ `_aos44_probe.txt`，尽管 4.4 / 4.6 的任务笔记都写了
    「探针已清理」⇒ 14.1 须现扫而非采信笔记（`_aos_adr005_verify.py` 是别的会话故意留的，勿删）

- [x] 6. 接进 Adopt_Service（`adopt_substrate_response.py`）
  - [x] 6.1 `dry_run` 改为返回完整 Overwrite_Plan
    - 取代现有 `_dry_run_summary` 的「只报 substrate 逐表行数」
    - dry_run 与真实执行**共用** `compute_overwrite_plan`，不得两套算法
    - _Requirements: 3.1, 3.2_
    - 落点 `adopt_substrate_response.py`（**325 → 689** 行，口径 `len(text.split("\n"))`）
    - **唯一计划入口** `compute_plan_for_adopt`（转发 `adopt_overwrite_compute.compute_overwrite_plan`）
      ⇒ dry_run 与真实执行共用，「摘要可信」不靠两处算出同样的数、靠**只有一处能算**
    - 已删两个私有函数并留指针注释防重造：`_dry_run_summary` → `_plan_wire_form` 取代 ·
      `_baseline_row_counts` → 由 `plan.substrate_rows_by_table` 供出。🔴 两者口径**有实质差别**
      （旧函数 `len(ids or ())` 数**原始**序列长度，计划侧 `_declared_identities` 数**去重后**身份数）
      —— 这正是删它而非并存的理由
    - 🔴 **3 条空 `declared_scopes` item 的硬前提已接线**：`D2-detail-rows` / `D4-2-rows` /
      `H1-8-rows`（现算复核仍为空；三者 reader 都是裸 `_FacadeRowReader`、provider 无
      `managed_row_table_specs`、全域 spec 索引亦无）⇒ `_scope_override_from_declaration` 从**门面
      定义模块**的 `ROWS_TABLE_KEY` 取声明。🔴 **有分区维度却取不到声明时返回空元组让 compute 当场抛，
      不猜 `None` 分区** —— 硬塞 `(table_key, None)` 触发不了 `_in_scope_by_section` 任何一条门，
      真实分区的行永远匹配不上 `None` 桶 ⇒ **静默少删**，宁可报错
    - `_plan_wire_form` **显式给出四个计数**（Requirement 3.2 逐字要求）尽管它们是 `len(清单)` 的
      派生量 —— Task 10.1 要求前端不自行重算，前端自己数一遍就是第二真源；计划侧仍不存字段
    - 🔴 **未提前做 6.3 / 6.4**：删除侧应用与提交前复读未实现；`changed_item_count` 仍取自
      `_diff_snapshots`（一个字未动），并配了一条「现状登记」判据与一条 `xfail(strict=True)` 互为反面
  - [x] 6.2 `plan_digest` 校验与新 domain 错误类
    - 新增 `AdoptPlanDigestMismatchError` / `AdoptStorePayloadUnreadableError` /
      `AdoptPlanVerificationError`，`error_code` 命名与既有三个同风格
    - _Requirements: 3.4, 4.4_
    - **「既有三个」现读得出**（不是照 `AdoptXxxError` 字面推测）：`AdoptContractRequiredError` →
      `adopt_contract_required` · `AdoptSubstrateNotPublishedError` → `adopt_substrate_not_published` ·
      `AdoptRevisionConflictError` → `adopt_revision_conflict`；规则 = 类名去 `Error` 后
      CamelCase → snake_case **不加后缀**，例外是基类 `AdoptSubstrateError` → `adopt_substrate_failed`
      （类名去 `Error` 只剩主语没有状态词故补 `_failed`）
    - 三个新 `error_code`：`adopt_plan_digest_mismatch`（409）· `adopt_store_payload_unreadable`（422）·
      `adopt_plan_verification_failed`（500）。🔴 `AdoptPlanVerificationError` 按上述规则补 `_failed`
      （`verification` 是动作名非状态词），另两个类名自带状态词（`mismatch` / `unreadable`）⇒ 不补
    - `verify_plan_digest` 调用点在**任何写之前**（Requirement 3.4），并有 AST 判据钉死
      「verify 的语句序号 < 第一个写入起点的语句序号」；dry_run 分支**不**校验（那一趟就是去取新 digest 的）
    - 🔴 **`AdoptStorePayloadUnreadableError` 在调用点按 item 包装，不靠异常类型学甄别**：原生类型
      异构（引擎 `RowTableStorePayloadError(Exception)` / 多数 provider `StorePayloadError(SyncDomainError)` /
      `phase5_d4_customer_structure` 的 `StorePayloadError(ValueError)`）⇒ 按类型分流必漂。
      `item_id` 由 `_first_unreadable_item` 在**错误路径**上复读定位（happy path 零成本），
      因为 Task 3.6 已登记「兜底文案不带 item_id」这一现状
    - 🔴 **`OverwritePlanShapeError` 原样穿透不翻译**：它是**编程错误**（500 + 堆栈），而「store 里
      存着一份非法 JSON」是**数据**问题 —— 翻译它会把归类搞反，让声明漂移 / 分母漏登记这类必须改
      代码的缺陷伪装成「用户可重试」
    - router 已接线 `wp_sync_router.py`：`AdoptPlanDigestMismatchError` → **409**，并有 AST 判据
      现扫端点的 `except` 分支确认映射在场（配「对已知不存在的映射必报否」的变异对照）。
      🔴 `AdoptPlanVerificationError` **当前无专属 except** ⇒ 被兜底分支映成 422 而 design 要 500，
      该现状由一条 `xfail(strict=True)` 钉住：6.3 补 500 映射那天它 XPASS 而 strict 使其打红，
      逼迫摘掉 xfail，而不是让「本该 500」的诉求静默沉底
    - **落点测试 `test_aos_adopt_plan_wiring.py`（新建，该模块的第一份行为判据）**：现搜实证
      `adopt_substrate_response` / `_dry_run_summary` / `compute_adopt_substrate` 三个符号在
      `backend/tests/**/*.py` 里命中 **0**（对 `adopt-substrate` 端点字面量的 4 处命中经判注释后
      可执行代码仅 1 处 = `test_task28_sync_router.py` 的路由清单）
    - **平台铁律判据**：「service 只 flush 不 commit」由 AST 钉死**恰 1 处**且在
      `compute_adopt_substrate` 里（新代码多任何一次 commit/flush 即打红）· 计划与回滚快照建立在
      **同一次** `_snapshot_store` 读取上（避免「计划与快照错版」窗口）
    - **定向回归 15 文件 `391 passed / 3 xfailed / 0 failed`**（编排侧独立实测；基线 325 + 本轮 66
      + 3 个现状登记 xfail）；另跑 `test_task28_sync_router.py` / `test_d4_mirror_shape_invariants.py` /
      `test_d2_store_value_equivalence.py` **130 passed** 确认 router 改动无回归
    - ✅ **欠账已清（行数门禁）**：`test_aos_adopt_plan_wiring.py` 原 **1055** 行
      （两种口径：`split("\n")` 1056 / `count_lines` 即 `splitlines()` **1055**；门禁用后者）
      > `.py` 门禁 **800** ⇒ 按域内先例（`test_aos_property_out_of_scope_rows.py` /
      `…_out_of_scope_mutants.py`）抽伴生件，两份均达标：
      · `test_aos_adopt_plan_wiring.py` —— `split("\n")` 610 / `count_lines` **609**
      · `test_aos_adopt_plan_gates_and_wire_form.py` —— `split("\n")` 581 / `count_lines` **580**
    - **切在 §4 / §5 之间**（按节边界，不按行数对半砍）。两侧各是一个完整关注点：主体 = 「计划
      **是怎么来的**」（§1 唯一计划路径 / §2 三条空 `declared_scopes` 接线 / §3 scope 只取声明 /
      §4 三态）+ §10；伴生件 = 「计划**算出来之后**」（§5 digest 校验门 / §6 载荷不可解析门 /
      §7 错误码契约 / §8 wire form / §9 事务纪律与 6.3·6.4 棘轮）。
      🔴 **§10 刻意留在主体**：它与 §1 是同一关注点的正反两面 —— §1 证明新路径唯一，§10 证明旧的
      两处口径（`_dry_run_summary` / `_baseline_row_counts`）已删；分家就看不出「唯一口径」怎么成立。
      🔴 每组「判据函数 + 它的变异反证」都未被拆开：§1 的 `judge_shared_plan` 与 M1~M4 同在主体，
      §8 的 `judge_wire_form` 与它的两组变异同在伴生件。
      🔴 主体同时是两份的**共用工具箱**（`_source_mutant` / AST 取件 / `_StubReader` / `_projection` /
      `_fixed_plan` / `_ROUTER_PY`），伴生件**只 import 不另造第二份**，且用**顶层模块名**
      `from test_aos_adopt_plan_wiring import …` —— 该目录无 `__init__.py`，pytest 走 `prepend`，
      写成 `tests.workpaper_sync.…` 会拿到**第二个**模块实例、工具函数与模块级常量当场分家。
      `LEGACY_ERROR_CODES` / `NEW_ERROR_CODES` 随 §7 一并搬走（只有 §7 用它们）。两侧文末各留指针
      注释：主体尾部点明 §5~§9 去了哪、伴生件 import 了哪些工具、以及「`_ROUTER_PY` /
      `_source_mutant` / `_fixed_plan` 拆分后只被伴生件用到，**不要因为本文件没用到就删**」；
      伴生件尾部点明 §1~§4 与 §10 在主体、主体是共用工具箱。
      🔴 **本文件无模块级红数累计器**（现扫模块级可变容器赋值命中 **0**）⇒ 不存在「写了从未被读」
      的风险；也**没有**为拆分新造一个 —— 新造即多一条判据例，违反「例数必须相等」。
    - **例数拆分前后逐字相等的证据**（基准 = 拆分**前**基线跑留下的
      `__pycache__/test_aos_adopt_plan_wiring.cpython-312-pytest-8.4.2.pyc`，mtime 15:41 早于拆分
      16:00，是**非循环**的独立产物；该文件尚未 commit 故 `git show HEAD:` 取不到，实测 rc=128）：
      ① **测试方法全名集合守恒**：拆前 **50** → 拆后 **50**（主体 23 + 伴生 27），集合相等，
      两侧**无重复**方法 ② **docstring 漂移 0 条**（逐方法逐字比对 `co_consts[0]` vs AST）
      ③ **行号位移只在节边界跳变**：伴生件 27 个方法共享**同一个** delta（−463）⇒ 原文 555..1030
      整块刚性搬移、段内零增删改；主体 2 个 delta（+8 / −468）恰等于它承接的 2 个原文**连续段落**
      （S1~S4 在原文首尾相接故共享一个 delta，只有跨过被搬走的 S5~S9 才跳变一次）。该判据配
      **变异反证**：在主体连续段落**中间**插一行 ⇒ 跳变数 2→**3**。🔴 两个自抓的坑：第一版锚点选在
      首个测试类**之前**，整段统一平移故 delta 不变、得「仍为 2」的**假阴**（锚点必须落段中部）；
      `co_firstlineno` 指**第一个装饰器**行而 `ast.FunctionDef.lineno` 指 `def` 行，不归一化会让带
      parametrize / xfail 的方法整体偏 1、段内假跳变（首轮 5 个「跳变」全是这个原因，不是搬家动了行）
      ④ **3 个 `xfail(strict=True)` 全在**（均落伴生件 §9），`strict=True` 与 reason 一字未改：
      「删除侧应用属 Task 6.3（ADR-AOS-001：merge 之后）」·「`AdoptPlanVerificationError` → 500
      映射属 Task 6.3」·「`changed_item_count` 改由 plan 供出属 Task 6.4」
    - **门禁两次调用**（🔴 一律 `cwd=d:\GT_plan` + **仓库根**相对路径，理由见下一条）：
      ① 正确路径、两份一起传 ⇒ **exit=0**，且 `count_lines` 现读 **609 / 580**（非 0 ⇒ 确实读到了
      文件。拆分**前**同一调用形态曾 exit=**1** 并点名「1055 行 > 上限 800」，两头对照坐实这个形态
      看得见文件）② **变异证明**：传一个完全不存在的文件名
      `backend/tests/workpaper_sync/test_aos_THIS_FILE_DOES_NOT_EXIST.py` ⇒ 同样 **exit=0**
      ⇒ 🔴 **单看 exit=0 什么都不能证明**，必须同时给出 `count_lines` 的非零实测值才算通过
    - **定向回归**：拆出的两份 + 既有 13 个 `test_aos_*.py` + `tests/test_lazy_import_resolvability.py`
      = **16 文件**（上一条记的「15 文件」是拆分前口径）⇒ **391 passed / 3 xfailed / 0 failed**，
      与拆分前基线**逐字相同**；另 `test_task28_sync_router.py` / `test_d4_mirror_shape_invariants.py` /
      `test_d2_store_value_equivalence.py` **130 passed** 同基线。两份 `getDiagnostics` 均 0。
      **生产代码零改动**：`adopt_substrate_response.py` / `adopt_overwrite_plan.py` /
      `adopt_row_reader.py` / `adopt_overwrite_compute.py` / `wp_sync_router.py` 的 mtime 均
      ≤ 15:42:54，早于本轮首次写入 16:00:57（这几份尚未 commit，`git status` 只显示 `??` 无法作证，
      故改用 mtime）；其它 13 个 `test_aos_*.py` 未动，design / requirements 未动，
      6.3 / 6.4 未提前实现（三条棘轮仍 xfail 即其可执行证明）
    - 🔴 **连带修**：一次性探针 `backend/scripts/analyze/_aos_t61_mutate.py` 的 `TEST` 只指主体，
      而它 5 组变异里 B/C/D/E 分别落在伴生件的 §9 / §7 / §5 / §8 ⇒ 拆分后只跑主体，那四组会「全绿」，
      正好把该探针要证伪的东西掩盖掉 ⇒ 已改成两份都传（`TESTS` 元组）。**未重跑它**：它是**写盘**
      变异生产文件，与本域「变异一律进程内、因为有并发会话」的处置相悖（本轮实测
      `adopt_substrate_response.py` 在 15:42:54 被另一会话动过）；而「判据有牙」已由 §5/§8 自带的
      **进程内**变异用例（`test_mutant_comparison_neutralised_is_caught` /
      `test_mutant_dropping_a_list_field_is_caught` / `test_mutant_count_from_wrong_list_is_caught`）
      在上述 391 全绿里覆盖
    - 🔴🔴 **平台级发现：`check_file_size.py` 的门禁可被静默绕过（假绿）**。`count_lines` 是
      `try: ... except Exception: return 0`，而 `main()` 对**相对路径**按**仓库根**解析
      （`ROOT / rel`）⇒ 在 `cwd=backend` 下传 `tests/…/x.py` 会拼成不存在的 `<root>/tests/…`，
      `count_lines` 吞掉异常返回 **0**、`0 > 800` 为假 ⇒ **exit=0 通过**。三向实证：
      ① 传仓库根相对路径 `backend/tests/…` ⇒ exit=**1** 并点名 1055 行 ② 传 backend 相对路径
      ⇒ exit=**0** ③ 传一个**完全不存在**的文件 ⇒ 同样 exit=**0**。
      ⇒ 交付报告里的「`check_file_size.py` exit=0」若用 backend 相对路径取得，**是假绿**；
      本 spec 前面若干条任务笔记记的 exit=0 都需按 ①口径复核。这与铁律 ⑰/㉔「工具报空结果先查
      是否崩溃」同源，也是铁律 ㉗「有门禁 ≠ 门禁生效」的又一实例
  - [x] 6.3 删除侧应用 + 提交前复读比对
    - 在 `mirror_projection_into_store(..., commit=False)` **之后**应用删除侧
      （🔴 顺序不可调换：前置清 base 会让幽灵行门全面生效，见 design ADR-AOS-001）
    - 写完在同事务复读，与 plan 不符即 rollback 并 fail visible
    - _Requirements: 1.1, 1.2, 3.5_
    - **落点 = 新建伴生模块** `adopt_overwrite_apply.py`（域内第五次同样处置）：`.py` 门禁 800，
      而 `adopt_substrate_response.py` 交付 6.1/6.2 后只剩 112 行余量、`adopt_overwrite_plan.py`
      781（余 19）、`adopt_row_reader.py` 768（余 32）—— 删除侧应用 + 幽灵观测 + 复读比对
      约 380 行装不进任何一份。依赖方向**单向**：新模块 → `adopt_overwrite_plan` /
      `adopt_overwrite_compute`，对 `adopt_substrate_response` 只在**函数体内**懒引入
      （顶层会成环，因为 service 顶层 import 了本模块）
    - **改动文件与行数**（两口径 `split("\n")` / `count_lines()`，门禁用后者；🔴 一律
      `cwd=d:\GT_plan` + **仓库根**相对路径，五份一起传 ⇒ **exit=0**，且 `count_lines` 逐个非零
      —— 只给 exit=0 不算通过，本轮另跑「传不存在的文件同样 exit=0」的变异对照坐实这一点）：
      · `adopt_overwrite_apply.py` **381 / 380**（新建，默认上限 800）
      · `adopt_substrate_response.py` **749 / 748**（689 → 749，默认上限 800）
      · `wp_sync_router.py` **3200 / 3199**（3190 → 3200；它在 whitelist，基线 **3102**、
        +5% = **3257** ⇒ 未触发膨胀门。🔴 余量只剩 58 行，下一个动它的任务要当心）
      · `test_aos_adopt_plan_gates_and_wire_form.py` **696 / 695**（581 → 696）
      · `test_aos_deletion_apply_and_verify.py` **701 / 700**（新建）
    - **删除侧落点与顺序证据（AST 语句下标，现算）**：写入/复读/回滚都在
      `compute_adopt_substrate` 的那个 `try`（它是 `fn.body` 第 **15** 条），**`try` 块内 8 条语句**
      的下标是 `mirror_projection_into_store` **0** → `apply_overwrite_deletions` **1** →
      `_snapshot_store`（复读）**2** → `verify_applied_plan` **3** →
      `raise AdoptPlanVerificationError` **4** → `session.commit()` **7** ⇒ prune 在 mirror 之后
      （1 > 0）、比对在提交之前（3 < 7）
    - 🔴 **原 xfail 那条断言其实恒真，本轮换成正面判据时顺手修掉**：它取
      `prune_at = _stmt_index(fn.body, "prune_undeclared_rows" in ast.dump(s))` 与
      `mirror_at = _stmt_index(fn.body, ImportFrom(mirror…))` 比—— mirror 的 **import** 是函数
      顶层语句、真正的**调用点**在 `try` 里，而 `ast.dump(try)` 递归含整块 ⇒ 即使 prune 排在
      merge **之前**，那个比较**照样成立**。新判据在 `try` 块内逐语句定位**调用点**，五段全序
    - **顺序调换即打红（实测，非推断）**：`judge_deletion_after_mirror` 对照组（生产实现）
      red **0**；把 mirror@0 与删除侧@1 两条语句**对调** ⇒ red **1** 且文案含「幽灵行门」
    - 🔴 **第五段判据是本轮自己发现的 Requirement 6.9 连带约束**：复读那次 `_snapshot_store`
      必须在删除侧**之后** —— 它同时是 `changed` 的来源，而 `rollback_snapshot` 只存
      `changed` 里的 item。早读会让「只被删除侧改动的 item」落不进回滚快照 ⇒ **被删的行再也
      恢复不了**。⇒ 「prune 在 after_snapshot 之前」不只是省一次读，是 6.9 的硬要求。
      变异：把 `_snapshot_store` 提到删除侧之前 ⇒ red（文案含 `rollback_snapshot`）；
      commit 提到首位 ⇒ red **1**（文案含「提交之前」）
    - **幽灵观测与回喂实现**：`observe_ghost_dropped(plan, post_merge_ids=…)` —— **纯函数**，
      口径 = 「计划说该在场、merge 之后却不在」。观测面刻意取 `rows_added ∪ rows_updated`
      而不是只取 added：`missing = expected - present` → `ghost = missing ∩ added`（合法差异）
      / `vanished = missing - added`（**违规**，fail visible）。回喂经
      `compute_plan_for_adopt(ghost_dropped_by_item=…)` 重算一次 ⇒ `applied.plan` 才是最终计划
    - 🔴 **`rows_ghost_dropped ⊆ rows_added` 落在三处，且第一处不是恒真废话**：
      ① **构造**上 `ghost = missing & added` ⇒ ⊆ 成立；② 之所以**有牙**，是因为观测面含 updated
      —— 落在 updated 侧的缺失被单独拎成违规而不是一起塞进 ghost。变异反证：把
      `missing = (added | updated) - present` 缩成 `missing = added - present` ⇒ 生产 red **1**、
      变异体 red **0**（⊆ 断言退化成废话）；③ **独立第二道**在
      `adopt_overwrite_compute._deltas_for_item` 末尾 —— 回喂的幽灵落不进任何分区的 `rows_added`
      即抛 `OverwritePlanShapeError`（本轮实测：喂一个 `rows_deleted` 里的身份当场抛）。
      两处口径不同（本处按 item、那处按分区）⇒ 观测口径错了两边都拦得住
    - 🔴 **幽灵必须按 item 聚合不能按分区找**：被门剔除的行**根本不在载荷里**，它没有分区可言
      （`section_of` 无从对一个不存在的行取值）⇒ 按分区找必然找不到，进而误判成「作用域外」静默放过
    - **复读比对粒度 = 逐 `(item, table/分区)` 比身份集合，不是比计数**。为什么不能只比计数：
      「删掉一条 declared 行、留下一条 undeclared 行」两侧计数**一模一样**。实测证据
      （`test_right_count_but_wrong_row_is_caught`）：文案同时给出「多出 ['d1']、缺失 ['u1']」
      **与**「计划期望 2 行、复读实得 2 行」—— 行数相同而集合不同，这一例才证得了差别。
      变异反证：`_diff_sections` 的 `if want == got:` 换成 `if len(want) == len(got):` ⇒
      生产 red **1**、变异体 red **0**
    - **两档期望集合**：① 作用域内分区 = `(rows_added − rows_ghost_dropped) ∪ rows_updated`
      —— **只由 plan 决定**（`declared − ghost`）⇒ 这是对**计划**的独立交叉核，不是「prune 有没有
      照自己说的做」的自问自答；② 作用域外分区 = merge 之后观测到的那一份（逐元素原样）——
      正是「prune 删到兄弟分区」这一最危险失效形态的落点。变异反证：期望集合不以 merge 后快照
      为基准（`for section, ids in ()`）⇒ 兄弟分区被整段删掉也看不见，生产 red **1** / 变异体 **0**
    - **幽灵行是已知合法差异**：期望集合按上式已把它减掉 ⇒ 不打红；反面同样在场 —— 同一计划下
      ghost **真的在场**也算不符（`多出 ['ghost']`）
    - **两条 xfail 摘除后的真断言形态**（🔴 未弱化，是加强）：
      · 原 `test_deletion_side_is_applied_after_mirror` ⇒
        `test_aos_adopt_plan_gates_and_wire_form.py` **§11** 的 `judge_deletion_after_mirror`
        五段全序 + 4 组变异（语句对调 / 快照前置 / commit 前置 / 删除侧未复用 Task 4.1 纯函数）
      · 原 `test_router_maps_plan_verification_to_500` ⇒
        `test_aos_deletion_apply_and_verify.py` **§5** 的 `judge_router_verification_mapping`
        三条子判据（专属 `except` 在场 / 状态码恰 `(500,)` / 分支序号 < 兜底序号）+ 3 组变异
        + 一条**语言层实证**（真 `raise` 一次，证明子类分支排在兜底之后确实永远进不去）
      · 第三条（Task 6.4 的 `changed_item_count`）**原样保留**：`strict=True` 与 reason 一字未改，
        与它成对的现状登记 `test_changed_item_count_still_comes_from_the_snapshot_diff` 也未动
    - 🔴 **§11 与 §5 分家是行数门禁所迫**：两半同文件实测 **802** 行 > 800（先写在一起、门禁
      打红后才切）。切口在**两个 judge 之间** ⇒ 没有把任何「判据函数 + 它的变异反证」拆开；
      两侧各留指针注释说明另一半在哪、以及为什么这么切
    - **router 500 映射与 `except` 顺序**：`wp_sync_router.adopt_substrate` 新增
      `except AdoptPlanVerificationError → 500`，位置在 `AdoptSubstrateNotPublishedError`
      之后、兜底 `except AdoptSubstrateError`（422）**之前**。🔴 它是兜底的**子类**，排在后面
      永远进不去 —— 摘掉分支 red **1**、500 换 422 red **1**、挪到兜底之后 red **1**（三组逐个实测）
    - **变异反证逐组 red 数**（全部**进程内**：源码级 `inspect.getsource` → 换唯一锚点 → 在生产
      模块 `globals` 的**副本**里 `exec`；AST 类判据用 `copy.deepcopy(树)` 改节点。生产文件一字
      不改，🔴 不用 `monkeypatch.setattr` —— 本域有并发会话）：
      **ORD 对照组 0** · ORD-M1 语句对调 **1** · ORD-M2 commit 提首位 **1** · ORD-M3 快照前置 **1**
      · **RTR 对照组 0** · RTR-M1 摘分支 **1** · RTR-M2 500→422 **1** · RTR-M3 挪到兜底后 **1**
      · GHOST-M1 观测面缩成 added：生产 **1** / 变异体 **0** · VER-M1 只比计数：生产 **1** / 变异体
      **0** · VER-M2 丢作用域外基准：生产 **1** / 变异体 **0**
    - **定向回归 18 文件 `531 passed / 1 xfailed / 0 failed`**（基线 **492 passed / 3 xfailed**
      ⇒ xfailed **3 → 1**（只剩 6.4 那条）、**无 XPASS**）。🔴 逐文件数过的分解（不靠推算）：
      用例**条目**总数 495 → **532**；新文件独跑 collect **34** 条（§1 幽灵 6+3 / §2 复读 7 /
      §3 真落库 9 / §4 卫生 4 / §5 router 5）；`test_aos_adopt_plan_gates_and_wire_form.py`
      **35 → 38** 条（− 摘掉的 2 条 xfail ＋ §11 新增 5 条）⇒ passed 净增 34 + 5 = **39**。
      清单 = 既有 17 份 ＋ 新增
      `test_aos_deletion_apply_and_verify.py`。另跑 `test_d4_mirror_shape_invariants.py` /
      `test_d2_store_value_equivalence.py` / `test_task28_sync_router.py` **130 passed** 同基线
      （router 改动无回归、路由清单三处未变）。五份 `getDiagnostics` 均 **0**
    - **平台铁律判据全绿（既有守卫，本轮未改其语义）**：`compute_adopt_substrate:commit` 仍是
      **唯一**事务操作点（新模块**零** commit/flush，另配本轮新增的 AST 判据兜住它 —— 既有那条
      只扫 `adopt_substrate_response` 的 AST，新模块在它视野之外）· `changed = _diff_snapshots(
      before_snapshot, after_snapshot)` 与 `"changed_item_count": len(changed)` **一个字未动**
      （6.4 的活）· `store_payloads = _snapshot_store(...)` 仍只有一次、回滚快照仍复用它
    - 🔴 **登记一处口径自然变宽（不是改动，是位置的后果）**：`changed` 现在也会包含「只被删除侧
      改动」的 item（因为 prune 排在 `after_snapshot` 之前）。这一行源码未动，方向是**更如实**
      （那些 item 确实变了），而且正是 Requirement 6.9 所需 —— 见上面第五段判据
    - 🔴 **本轮刻意未做**：6.4（`changed_item_count` 由 plan 供出）· 6.5（审计 details 追加
      `rows_deleted_by_item` / `plan_digest` / `skipped_items`）· 真实执行分支的响应体仍是
      `{dry_run, substrate_sha256, expected_revision, changed_item_count, changed_items}`
      （wire form 进真实执行分支属 6.4/6.5）。`AppliedOverwrite` 已把 `rows_deleted_by_item` /
      `ghost_dropped_by_item` / `plan`（含 `rows_ghost_dropped`）备好，6.5 直接取即可
    - **建议 / 缺陷登记（未改 design / requirements）**：
      ① 🔴 `prune_undeclared_rows` 只读 `reader.declared_scopes`，而那 3 条 item
      （`D4-2-rows` / `D2-detail-rows` / `H1-8-rows`）的真声明住在 `AdoptPlanInputs.item_scopes`
      ⇒ 本轮加了 `_ScopedReader` 薄代理把权威 scope 套上去（scope 本身仍取自**同一条**
      `_scopes_of`，不另判一次）。**不用 `dataclasses.replace`** 的理由是现读实证：
      `ReconcilingRowReader` 的 `section_field` / `declared_scopes` 是 **property 不是字段**，
      `replace(...)` 会当场 `TypeError`。建议后续给 `RowReader` 协议补一个「带 scope 覆盖」的
      正式形态，别让代理长期当接缝
      ② `adopt_overwrite_apply` 从 `adopt_overwrite_compute` import 了三个 `_` 前缀成员
      （`_row_keys_of` / `_scopes_of` / `_store_ids_by_section`）—— 刻意的：它们是本域「取
      row_keys / 取权威 scope / 按分区枚举身份」的**唯一**实现，另写一份就是第二真源。若将来
      要收口，宜把这三个提成公开门面而不是复制一份
      ③ `_snapshot_store` 现在一次 adopt 被调 **3** 次（merge 前 / merge 后 / prune 后），
      每次 N 条 SELECT。adopt 是人工运维端点、N 最大 46 ⇒ 可接受；若将来上批量版本
      （遗留待裁决 3）应改成一条 `IN (...)` 查询
      ④ 🔴 `test_aos_adopt_plan_gates_and_wire_form.py` 现 **695**、
      `test_aos_deletion_apply_and_verify.py` 现 **700**（上限 800）⇒ 6.4 / 6.5 再往这两份加
      判据前先算余量，别等门禁打红再切
    - 探针已清理（`backend/scripts/analyze/_aos63p_*.py` **6** 个 + `_aos63_moved_router.txt`，
      现扫确认目录下 `_aos63*` 归零）；
      🔴 未动其它会话的 `_aos44p_*` / `_aos46p_*` / `_aosp2_*` / `_aos_adr005_verify.py`
  - [x] 6.4 `changed_item_count` 改由 plan 供出
    - 移除对「覆盖前后 remark 快照差集」的依赖
    - 源码锁：断言该字段不再取自 `_diff_snapshots`
    - _Requirements: 3.6_
    - 🔴 **与 6.5 合并实施**（两条改的是 `compute_adopt_substrate` 里**同一段**返回值与审计留痕
      代码，分开做必冲突）⇒ 实施记录写在 6.5 条目下，本条只记 6.4 专属结论
    - **新来源的表达式** = `changed = changed_items_from_plan(applied.plan)`，响应体
      `"changed_item_count": len(changed)` / `"changed_items": changed`。口径 = **追加 / 删除 /
      更新三类行身份任一非空**的 item（有序去重）
    - 🔴 **实参是 `applied.plan` 不是 merge 前那份 `plan`**：后者 `rows_ghost_dropped` 恒空，
      喂它等于把 6.3 的幽灵回喂结果整个丢掉。原棘轮（文本 `in`）根本表达不了这一条，
      改写后的 AST 判据把它列为子判据 2 并配了专属变异（M2）
    - **幽灵行计入（裁定 + 理由）**：判据读**裸 `rows_added`**，不是 `rows_added − rows_ghost_dropped`。
      因 `ghost ⊆ rows_added`（构造保证），两种写法只在「全部新增身份都被幽灵门剔除」这个退化
      item 上分叉。计入的三条理由：① **误差方向不对称** —— 回滚快照覆盖面以本口径为起算之一
      （Req 6.9），少算一个 item = 它的原值不进快照 = 再也恢复不了；多算一个只是快照多一个键
      ② **那个 item 的载荷真的被改写过** —— design ADR-AOS-003 附注复现的那一例逐字记着
      `applied = 1`、`merged == base`、**写回了重新序列化的字符串** ⇒ 判它「没变」与实测相反
      ③ **口径要能被前端复述** —— wire form 同时给 `rows_added`（含 ghost）与 `rows_ghost_dropped`，
      弹窗按「将追加 N 行（其中 M 行会被剔除）」渲染，计数必须用同一个 `rows_added`
    - **被跳过的 item 刻意不在本口径内**（三清单恒空、`table_key` 为 `None`）：Req 3.6 问的是
      「这次覆盖动了哪些行集」，而跳过的 item 正是「删除侧做不到」的那些；它们的**可回滚性**
      由 6.5 的并集口径兜住，不靠本口径
    - **新旧两口径逐值对照实测（5 场景，探针 + 判据两处一致；`_CALIBER_TABLE` 已固化）**：

      | 场景 | 旧（remark 字节差集） | 新（plan） | 并集（回滚覆盖面） | 等价 |
      | --- | --- | --- | --- | --- |
      | S1 删除侧独有改动（store 多一行、substrate 没有） | `[ITEM]` | `[ITEM]` | `[ITEM]` | 是 |
      | S2 幂等重采纳（行集全等、字节一字未变） | `[]` | `[ITEM]` | `[ITEM]` | **否** |
      | S3 幽灵行独占（新增全被剔除，merge 写回重序列化串） | `[ITEM]` | `[ITEM]` | `[ITEM]` | 是 |
      | S4 被跳过的 item（不可枚举；merge 照样改写 remark） | `[ITEM]` | `[]` | `[ITEM]` | **否** |
      | S5 真新增 + 真删除 | `[ITEM]` | `[ITEM]` | `[ITEM]` | 是 |

    - **哪个更如实（逐向如实登记，不含糊）**：**S2** 旧口径更贴近「字节没变」这个事实，新口径
      更贴近「这次覆盖声明要覆盖 `keep` 这一行」这个事实（`rows_updated` 非空是如实的：覆盖确实
      把 substrate 的 `keep` 写进了 store，只是字段值恰好相同）。Requirement 3.6 要的是后者
      （弹窗报的数与执行后报的数必须同源可对账），而旧口径在 dry_run 那一趟**根本取不到值**
      ⇒ 它当不了响应字段的来源。**S4** 是危险的那一向：plan 看不见被跳过的 item，而它的 `remark`
      真被 merge 改写了 ⇒ 若回滚快照只按 plan 存，那份原值当场丢失（处置见 6.5 并集口径）
    - 🔴 **不排除 `rows_updated` 的理由**（顺手记，免得后人「优化」）：`rows_updated` = 两侧都在的
      身份，计划层**无从**得知字段值是否真的不同（它比身份不比值）。排掉它会漏掉**最常见**的那类
      真实覆盖（字段级改写），代价远大于 S2 这种多报
  - [x] 6.5 回滚快照与审计 details 扩展
    - `details` 追加 `rows_deleted_by_item` / `plan_digest` / `skipped_items`
    - `event_type` 沿用 `workpaper_sync_adopt_substrate`，**不**进 `EVENT_TYPE_SCHEMAS`
    - 业务写 / 回滚快照 / 审计三者同一事务
    - _Requirements: 1.8, 6.7, 6.9_
    - **改动文件与行数**（两口径 `split("\n")` / `count_lines()`，门禁用后者；🔴 一律
      `cwd=d:\GT_plan` + **仓库根**相对路径，六份一起传 ⇒ **exit=0** 且 `count_lines` 逐个非零。
      另跑变异对照「传一个完全不存在的文件 ⇒ 同样 exit=0」坐实**只给 exit=0 什么都不能证明**）：
      · `adopt_overwrite_apply.py` **501 / 500**（380 → 500，余量 300）
      · `adopt_substrate_response.py` **784 / 783**（748 → 783，🔴 **余量只剩 17 行**）
      · `test_aos_changed_items_and_audit_details.py` **651 / 650**（新建，Task 6.4 判据）
      · `test_aos_audit_details_and_rollback_snapshot.py` **461 / 460**（新建伴生，Task 6.5 判据）
      · `test_aos_adopt_plan_gates_and_wire_form.py` **693 / 692**（695 → 692，**变小 3 行**）
      · `wp_sync_router.py` **3200 / 3199** —— **一个字未改**（本轮不碰 router）
    - 🔴 **落点为何抽伴生模块**：`adopt_substrate_response.py` 交付 6.3 后 748/800 只剩 52 行，
      装不下四个纯函数的判据级 docstring ⇒ `changed_items_from_plan` / `rollback_snapshot_items` /
      `skipped_items_wire` / `audit_details_for_applied` 落在 `adopt_overwrite_apply.py` 末尾
      （域内第六次同样处置）。依赖方向**单向**：service → apply 模块（顶层 import，既有那条
      import 语句上扩 4 个名字）；apply 模块对 service 仍只在**函数体内**懒引入
    - **审计 details 新增字段清单（恰 3 个，与 design § Data Models 三行逐字相同）**：
      `plan_digest`（= `applied.plan.digest`，事后能把留痕与用户当时确认的摘要对上）·
      `rows_deleted_by_item`（Requirement 1.8 逐字要求的那件事；按 item 排序、值是 `list` 不是
      元组 —— 元组进不了 JSONB）· `skipped_items`（这次覆盖对哪些 item 做不到，留在审计轨迹里
      而不是只出现在一次响应里）
    - 🔴 **`event_type` 未登记 schema（未动，也未顺手登记）**：`workpaper_sync_adopt_substrate`
      不在 `EVENT_TYPE_SCHEMAS` 里（判据两检并列 + 变异对照：一个**已登记**的 event_type
      `onlyoffice_callback_rejected` 在同一张表里必须查得到，否则该断言什么都没在查；第二判据 =
      该字面量在 `audit_log_helper` 源码里**一次都不出现**）。理由：登记后这三个字段会变**必填**，
      而它们本质上是「有就写」的诊断信息。也未复用别人的 event_type（spec D 的教训）
    - 🔴 **`skipped_items` 收敛成一个投影门面 `skipped_items_wire`**：`_plan_wire_form` 与审计
      details 都要它，两处各写一遍 `[[item_id, reason.value] …]` 就是两处口径（迟早有人给其中
      一处加第三格）。判据 = 三者逐值相等 **＋ 源码锁**（`_plan_wire_form` 真的在调那个门面，
      不是各写一遍恰好相等）
    - **回滚快照完整性口径与判据（Requirement 6.9 的连带约束，6.3 发现的）**：
      `rollback_items = rollback_snapshot_items(plan_changed=changed, snapshot_changed=_diff_snapshots(...))`
      —— **两个口径的并集**，`_record_rollback_and_audit` 的 `rollback_payload` 改按它取键
      （原来按 `changed_items`）。判据不止「键在不在」，还要**「存的值就是覆盖前那一份」**
      （键在而值是 `None` 的快照还不了原）
    - 🔴 **为什么必须是并集（两向各自的理由，且如实声明贡献不对称）**：① **不能只用 plan** ——
      被跳过的 item（现算 61 条 item 级 + 2 条 adapter 级）在 plan 里三清单恒空而
      `mirror_projection_into_store` 照样 merge 并改写它们的 `remark`（**删除侧跳过 ≠ merge 跳过**），
      只按 plan 存快照这些原值当场丢失（= 上表 S4）② **不能只用字节差集** —— 它是事后观测、只读
      `remark` 一列，且 design ADR-AOS-003 附注真库实测它两向都失真；把「能不能恢复」唯一建立在
      一个已知不可信的仪器上等于把 Req 6.9 交给运气，plan 侧是**按构造**保证「删除侧动过的 item
      一个不漏」的那一半 ③ 🔴 **如实声明**：本轮 5 个场景里唯一「一方看得见、另一方看不见**且真的
      需要恢复**」的是 plan **看不见**那一向（S4）；反向那一例（S2）plan 多报的 item 其实什么都没变
      ⇒ **并集的价值是冗余**（两套互不依赖的判据盯同一件事），**不是**「各补一半盲区」——
      生产 docstring 的首版写成了后者，已按实测改正
    - 🔴 **构造不出「plan 报了删除而字节差集没报」的真实场景**（如实登记）：6.3 的顺序下 prune 的
      UPDATE 排在 `after_snapshot` 之前、必然改字节。故「被删除侧改动的 item 一个都不能漏」这条
      按**构造**判（把 `snapshot_changed` 置空，plan 那一半必须独立兜住），并配变异反证
    - **两条既有判据改写后的形态**（🔴 未弱化，是加强；断言原文见下）：
      · 原 `test_changed_item_count_comes_from_the_plan`（`xfail(strict=True)`，断言
        `"_diff_snapshots" not in src`）⇒ `test_aos_changed_items_and_audit_details.py` §1 的
        `judge_changed_item_count_source` **五条子判据**：① `changed_items_from_plan` 调用点恰 1 处
        且赋给一个变量 ② 实参必须是 `applied.plan` ③ 响应体
        `"changed_item_count" == len(<该变量>)` 且 `"changed_items" == <该变量>`
        ④ `_diff_snapshots` 的**每一处**调用都必须作为 `rollback_snapshot_items(snapshot_changed=…)`
        的实参出现（其余流向不明即打红），且**一处都不许少**（Req 6.9 需要它那一半）
        ⑤ `_record_rollback_and_audit` 收到的 `changed_items` / `rollback_items` 不许对调、
        两个变量不许是同一个
      · 原 `test_changed_item_count_still_comes_from_the_snapshot_diff`（现状登记，6.4 落地后
        **变成假**）⇒ 同文件 `test_the_snapshot_diff_only_feeds_the_rollback_coverage`，
        断言原文：`len(diff_calls) == 1` · `fed == diff_calls`（那一处调用就是 `snapshot_changed`
        实参）· `union_var == "rollback_items"` · `_calls_named(wire["changed_item_count"],
        "_diff_snapshots") == []` 与 `…(wire["changed_items"], …) == []`（反面：它没有以任何形式
        出现在响应体里）
      · 🔴 **改成 AST 而不是继续用文本 `in`**（平台铁律 ㉖）：文本匹配两向都会骗人 —— docstring /
        `#` 注释里提一句 `_diff_snapshots` 就让「已改完」判成没改完（**原棘轮正是这个形态**，
        而本轮生产代码的注释里确实提到了它），把调用点挪到注释提及处之外又能让「没改」蒙过
    - 🔴 **原 `TestTask63And64AreNotDoneYet` 整类摘除**，gates 文件 §9 末尾留**指针注释**说明
      两条各去了哪、为什么整组搬走（行数门禁）、为什么改成 AST；该文件模块 docstring 的
      「三条 xfail 棘轮」段也一并更新为「三条**都已改写**、本文件现在**零 xfail**」并给出三个落点
    - 🔴 **连带改一处既有判据的违规文案（非语义）**：§11 `judge_deletion_after_mirror` 里
      「复读那次 `_snapshot_store` 早于删除侧」的文案原写「它同时是 `changed` 的来源」——
      6.4 之后 `changed` 不再来自它，那句话变成假。改写为「它是复读比对（Req 3.5）的输入，
      也是 `rollback_snapshot` 覆盖面里「字节差集」那一半的来源」，**保留** `rollback_snapshot`
      这个子串（`test_mutant_snapshot_before_deletion_is_caught` 断言文案含它）⇒ 断言语义未动。
      生产侧同一处注释同步改正
    - 🔴 **判据文件拆成两份（域内第七次同样处置）**：先写在一份里实测 **1038** 行 > `.py` 门禁 800
      ⇒ 切口选在 **§3 / §4 之间 = Task 6.4 与 6.5 的任务边界**（不是按行数对半砍）：主体承
      「`changed_item_count` 从哪来、口径是什么」（6.4，29 例），伴生件承「留痕与可回滚」（6.5，22 例）。
      **没有**拆开任何「判据函数 + 它的变异反证」对（`judge_changed_item_count_source` + 5 组变异
      同在主体，`judge_rollback_completeness` + 4 组变异同在伴生件）。伴生件**只 import 不另造**
      （`ITEM` / `_EVENT_TYPE` / `_NEW_PURE` / `_delta` / `_plan` 取自主体，工具箱取自
      `test_aos_adopt_plan_wiring`，**顶层模块名** import），两侧文末各留指针注释并点明
      「主体没用到 `_AuditSession` / `_record` / `_applied` / `_sample_plan`，**不要因此以为是死代码**」。
      拆分前后 **51 例逐字守恒**（拆前单文件 51 passed ⇒ 拆后 29 + 22 = 51，`--collect-only` 逐份数过）
    - **变异反证逐组 red 数**（全部**进程内**：函数级用共用 `_source_mutant`（换唯一锚点后在生产模块
      `globals` 的**副本**里 `exec`）、AST 级用本轮新增的 `_mutated_fn_ast`（同一锚点纪律，只 parse
      不 exec）。生产文件一字不改，🔴 不用 `monkeypatch.setattr` —— 本域有并发会话）：
      · **§1 对照组（生产实现）red 0**；`M1_back_to_snapshot_diff` red **5**（改回快照差集会同时
        踩穿多条子判据，专属片段命中 1）· `M2_feeds_the_pre_merge_plan` **1** ·
        `M3_union_collapsed_to_plan_only` **1** · `M4_two_calibers_swapped` **1** ·
        `M5_count_from_the_union` **1** —— 每组都核**专属文案片段**（红在别处不算它被抓到）
      · **§2 口径四组各 red 1**（生产 `[ITEM]` vs 变异体 `[]`）：`M1_ghost_subtracted_from_added`
        （裁定的直接反证）· `M2/M3/M4` 逐个摘掉 added / deleted / updated 一项；
        另 `test_dedup_is_not_incidental`（集合推导→列表推导 ⇒ `[ITEM, ITEM]`）
      · **§5 RB 对照组 red 0**；`RB-M1` 快照按 `changed_items` 取键（= 6.5 之前的写法）red **1**
        且专属点名被跳过的 item，**并配变异生效断言**（`ITEM` 仍在 ⇒ 证明红的是「少了 BLIND」
        不是「整个快照没了」）· `RB-M2` 并集塌成 plan 一半 red **1**（同一条原值在**另一层**丢掉）·
        `RB-M3` 并集塌成字节差集一半 red **0** 于完整性判据 —— 🔴 **如实声明**：这一向在本轮场景里
        丢掉的 item 其实什么都没变，它**不是**可恢复性缺陷，红落在「并集必须真的是并集」那条
        **结构性**断言上，判据按结构判、不假装它造成了数据丢失 · `RB-M4` 删除侧 item 只靠 plan
        那一半：对照 red **0** / 变异 red **1**
    - 🔴 **判据自身被削弱 ⇒ 对应那组必须失去牙（守卫写完必须逐处变异，实测两处）**：摘掉子判据 2
      ⇒ `M2` 的专属红 1 → **0**；摘掉子判据 3 ⇒ `M5` 的专属红 1 → **0** ⇒ 两条子判据各自承重，
      不是靠别人顺带打红
    - **§6 新纯函数卫生**：四个全部同步函数 / 签名无 `session` / 函数体零 `commit`·`flush`·`execute` /
      全在 `__all__` / 两次调用不返回同一可变对象且不改入参 / details **不带 `default`** 地
      `json.dumps` 往返相等（🔴 `append_audit_log` 用 `default=str` 兜底 ⇒ 不可序列化的值会被静默
      转成字符串躺进审计轨迹，这条不带 default 才抓得到）
    - **平台铁律判据全绿（既有守卫语义未动）**：`compute_adopt_substrate:commit` 仍是 ASR 里**唯一**
      事务操作点（新增四个纯函数零 commit/flush）· `store_payloads = _snapshot_store(...)` 顶层仍
      只有一次、`before_snapshot = store_payloads` 未动 · digest 校验仍在任何写之前 ·
      §11 五段全序仍成立 · router 500 映射未动
    - **定向回归 22 文件 `608 passed / 2 failed / 0 xfailed`，short summary 原文**：

      ```
      =========================== short test summary info ===========================
      FAILED tests/workpaper_sync/test_aos_row_reader_r3.py::TestSkipCensusRecount::test_skip_total_reconciles_with_adr_expectation
      FAILED tests/workpaper_sync/test_aos_row_reader_r3.py::TestSkipCensusRecount::test_r3_rescued_count_reconciles_with_design
      2 failed, 608 passed in 55.09s
      ```

      `-rfxX` 跑出的 short summary **只有这两条 FAILED，无 XFAIL 段也无 XPASS 段** ⇒ xfailed
      **1 → 0**（最后一条棘轮摘掉转为真 passed）、**零 XPASS**。逐项对账闭合（不靠推算）：
      基线 560 passed + 1 xfailed = 561 条 ⇒ 摘掉整类少 2 条（1 xfail + 1 现状登记 passed）⇒
      559 ⇒ 本轮新增 51 ⇒ 610 ⇒ 减去下述 2 条**预存失败** = **608**
    - 🔴🔴 **那 2 条失败是预存的，归因已实证不是本轮引入（三重证据，未用 `git stash`）**：
      ① **决定性实验**：同进程把本轮新增的三个函数从 `adopt_overwrite_apply` 上 `delattr` 掉再重跑
      同一 census ⇒ 结果**逐值相同**（`enumerable 67 / absent 7 / item_blind 54 / unruled 0 /
      no_store_item 2`）⇒ 本轮新增代码**不参与**该 census 的任何计算
      ② **mtime 时间线**：本轮最早写入 09-29 **17:47:56**，而 `phase5_d1_expansion.py`
      （正是 D1 那 17 条 spec 的宿主、r3 判据的核心对象）被并发会话写于 **17:48:50**（我开始后 54 秒），
      `phase5_entry_orchestration.py` **18:06:54**、`phase5_d3_prepaid_receipts.py` **18:10:19**；
      `adopt_row_reader.py` / `adopt_row_reader_r3.py` 亦被写于 **10:15**（早于本轮 7.5 小时）
      ③ **失败内容与本轮无关**：断言是「跳过清单现算 **61**，ADR-AOS-005 §3 预期 **62**」
      （分桶 `absent 7 + item_blind 54`，原为 `absent 8 + item_blind 54`）—— `absent` 的语义是
      「provider 压根没暴露行枚举门面」，本轮改的是 adopt 的变更口径与审计留痕，加不掉也去不掉
      任何 provider 的门面
      🔴 **未修**（越界）：`test_aos_row_reader_r3.py` 属已交付 16 份之一，本任务只被允许改点名的
      那两条判据。**方向是好的**（跳过 61 < 62，即多救回一条），而 Task 4.8 的**棘轮**（`<= 62`，
      只许变短）本轮**绿**；打红的是 Task 3.7 `TestSkipCensusRecount` 那条**等值**对账。
      ⇒ **工单留给 3.7 / 后续任务**：要么按现算把 ADR §3 的 62 更正为 61 并写明归因（哪条 item
      被救回、由哪次改动救回），要么把等值断言改成棘轮 —— 🔴 **禁**为了变绿直接把常量改小而不查
      归因（那正是铁律 ㉖「纠正过期数字本身是高危动作」点名的形态）
    - 🔴🔴 **本轮撞到「并发会话正在写生产代码」的现场，红会自己来又自己走（实测记录，不是推测）**：
      定向回归跑完（`2 failed / 608 passed`）之后**没改任何东西**再跑一次子集，
      `test_aos_adopt_plan_wiring.py::TestEmptyDeclaredScopesAreWired` 的 D2 参数化**4 条同时打红**
      （`d2.receivable_detail / D2-detail-rows / pilot_d2_large_json`）；现查 mtime =
      `pilot_d2_large_json.py` **18:18:12**、当时 now **18:18:54**（红出现在别人写完后 42 秒内）。
      再跑同一份 22 文件清单 ⇒ 那 4 条**自己变绿**，总数回到 `2 failed / 608 passed`。
      同窗口内被并发会话写过的还有 `phase5_d5/d6/d7_*.py`（18:14:45）· `phase5_d3_prepaid_receipts.py`
      （18:13:54）· `phase5_entry_orchestration.py`（18:06:54）· `phase5_d1_expansion.py`（17:48:50），
      而本轮最后一次生产写入是 **17:49:36**。
      ⇒ **两条方法论**：① 本域的回归数**必须带时间戳**，否则「基线 560」与「现算 608」之间的差可能
      掺着别人半写完的状态 ② 归因**不能靠「跑一次红」**，要么做同进程的 `delattr` 决定性实验
      （本轮用的这条），要么重跑确认可复现 —— 只跑一次就把红算到自己头上，和把红推给别人一样错
    - 探针已清理（`backend/scripts/analyze/_aos65p_*.py` **6** 个 + 一次性拆分脚本 1 个，现扫确认
      目录下 `_aos65p*` 归零）；🔴 未动其它会话的 `_aos44p_*` / `_aos46p_*` / `_aosp2_*` /
      `_aos_t61_*` / `_aos_adr005_verify.py`
    - **建议 / 缺陷登记（未改 design / requirements）**：
      ① 🔴 `adopt_substrate_response.py` 现 **783/800 只剩 17 行** —— 下一个动它的任务（6.6 / 6.7 /
      8.x）**必须先算余量**，基本上只能往 `adopt_overwrite_apply`（余 300）或新伴生模块加
      ② design § 「现有实现改造点」表里写 `_diff_snapshots` **「降级为提交前复读比对的实现手段」**
      —— 那条**已被 6.3 的实现绕过**（复读比对走 `verify_applied_plan` 比**身份集合**，不比 remark
      字节）。它现在的真实角色是**回滚快照覆盖面的一半**（Req 6.9）。本轮未改 design，仅登记：
      该行宜更正为「降级为回滚快照覆盖面的一半」
      ③ `test_aos_row_reader_r3.py` 的两条等值对账见上一条工单
      ④ 本轮**未做** 6.6（Property 7 收敛）/ 6.7（Property 11 回滚 round-trip）/ Task 7（OO 路径
      隔离判据）/ Task 8（端点级测试）—— §5 的完整性判据是**例子级**的，Property 11 的
      round-trip（按快照真还原一遍再比原始载荷）仍是 6.7 的活
    - 🔴🔴 **编排侧独立归因（不采信 subagent 的自我归因，逐条复验过）**：定向回归 22 文件现为
      **2 failed / 608 passed / 0 xfailed**（`-rxX` 确认**无 XFAIL 段也无 XPASS 段** ⇒ 最后一条
      棘轮确实已摘并转为真 passed）。那 **2 failed** 是
      `test_aos_row_reader_r3.py::TestSkipCensusRecount` 的两条对账，**与本轮 6.4/6.5 无关**，
      判据 = 跳过清单现算 **61** 而 `ADR_EXPECTED_SKIP_TOTAL` 写死 **62**（分桶
      `{'absent': 7, 'item_blind': 54}`，即 `absent` 由 **8 → 7**，含义是**某个 provider 长出了
      行枚举器门面**）。归因证据三条，全部现算：
      ① **该普查的真实依赖全部远早于本轮**：`adopt_row_reader.py` mtime **10:15:16** ·
      `adopt_row_reader_r3.py` **10:15:24** · `store_item_registry.py` **07:21:00** ·
      `store_projection_response.py` **09-23** —— 本轮 6.4/6.5 一份都没碰
      ② **本轮写入窗口是 17:47:56 ~ 18:05:32**（`adopt_substrate_response.py` /
      `adopt_overwrite_apply.py` / 两份新测试），而带 facade 的 `pilot_d2_large_json.py` mtime
      **18:19:16** —— 比本轮最后一次写入**晚 14 分钟**，是并发会话所为（`rtk git status` 另见
      `workpaper_sync/` 下 17 个 `M` + 大批 `??` 的 `phase5_*` provider，均非本会话产物）
      ③ 失败内容是 **provider 门面存在性普查**，本轮改的是 `changed_item_count` 来源 / 审计
      details / 回滚快照三件事，构造上碰不到 provider 的门面面
      ⇒ **不在本轮修**（属 Task 3.7 / ADR-AOS-005 的工作面），如实登记
    - 🔴🔴 **顺带抓到该守卫自身的一处设计缺陷（登记，本轮不改，留给 3.7 工单）**：
      `ADR_EXPECTED_SKIP_TOTAL = 62` 把一个**正在被并发会话推动的数**写死成了相等判据。
      平台铁律 ②「计数类现算或标『现算值 + 禁写死』」正是针对这种形态 —— 每当任一并发会话给某个
      provider 补上 `iter_store_rows`，这条就会打红，而那**恰恰是期望发生的改进方向**
      （跳过清单变短 = 能枚举的 item 变多）。⇒ 判据宜改成**棘轮**（「只许变小、不许变大」，
      并把当前值作为上界基线登记）而不是相等；现算含 `iter_store_rows` 的 provider 模块共 **42** 个。
      另实测到该守卫会**自己红自己绿**（subagent 报告中途 D2 4 条同时打红、未改任何东西重跑即全绿）
      ⇒ 它对并发编辑敏感，属「永红/闪红门禁」那一类（铁律 ㉗：红成常态 = 没人看 = 门禁不存在）
  - [x]* 6.6 属性测试：应用计划后重算计划为空
    - **Property 7: 应用计划后重算计划为空（收敛）**
    - **Validates: Requirements 3.8**
    - 落点**新建** `backend/tests/workpaper_sync/test_aos_property_apply_convergence.py` ——
      `count_lines()`（= `splitlines()`）**715** · `split("\n")` **716** · 门禁
      `cwd=d:\GT_plan` + `.venv\Scripts\python.exe backend\scripts\check\check_file_size.py
      backend/tests/workpaper_sync/test_aos_property_apply_convergence.py` **exit=0**，且同一
      `count_lines()` 对该路径实测**非 0（715）** ⇒ 不是「传相对路径返 0 的假通过」
    - **例数 35 passed**（单跑）。它同时是 **6.6 / 6.7 共用的场景建造器**（`Scenario` / `CORPUS` /
      `run_overwrite_once` / `merge_simulator` / `identities_of` / `scenarios()` 生成器）
    - 🔴🔴 **幽灵张力的裁定 = 交办的第 3 条（按域断言），并扩到覆盖第 2 处偏差**。现算实测发现
      逐字文本有**两处**不成立，不是一处：
      ① **幽灵**：被门剔除的身份 substrate 有、store 永远没有 ⇒ 重算必然回到 `rows_added`；
      ② 🔴 **`rows_updated` 与幽灵无关地恒非空**（本轮现算新发现）：它的定义是
      `declared ∩ store_ids`（「两侧都有 ⇒ 字段以 substrate 为权威更新」），而**收敛的含义就是
      两侧行集一致** ⇒ 收敛后 `rows_updated == declared − ghost`。⇒ 逐字「三清单均为空」
      **当且仅当 `declared` 为空**（探针 5 场景 + 语料 7 条逐条实测，一致）。
      ⇒ 交办原文第 3 条里「`rows_deleted`/`rows_updated` 为空」的后半句**同样不可满足**，
      故不能照抄；第 1 条（排除幽灵场景）解决不了偏差②（无幽灵的普通增删改场景就已经不成立），
      且会把适用域缩到「无幽灵」还是不成立 ⇒ 只有按域断言可行。落地四条：
      **C1** `rows_deleted == ∅`（删除侧真落库）· **C2** `rows_added` **等于**上一轮登记的
      `rows_ghost_dropped`（**等式**，比交办建议的 ⊆ 强）· **C3** `rows_updated ==
      declared − ghost`（**正面形态**，钉死收敛后受管行集的确切内容 —— 这一条才证明「该追加的
      真的追加上了」）· **C4** 第三次重算与第二次三清单逐值相等 + `plan_digest` 相等（不动点）
    - **Requirement 3.8 原文支持该处置（逐字引）**：「THE Test_Suite SHALL 用真实 PostgreSQL 做
      对账：同一 substrate 与同一 store 版本下，dry_run 报出的三个身份清单与真实执行后实际落库的
      三个身份清单逐元素相等」—— 它要的是「计划与落库一致」，**没有**要求「重算为空」；且
      `adopt_overwrite_compute.compute_overwrite_plan` docstring 末节已把这条 AC 的对账口径裁定为
      「须按 `rows_added − rows_ghost_dropped` 对账（与 Property 1 的「减去被幽灵行门剔除的身份
      集合」同一表述）」⇒ 按域重述与 Requirement 3.8 + 域内既有裁定**同向**，不是判据的让步。
      （Requirement 3.8 逐字要的**真实 PG 对账**仍归 Task 8.5，本文件是它的纯函数层前哨。）
    - 🔴 **反空转（现算，禁写死）**：语料 `CORPUS` **7** 条，四类计数
      **has_add 3 / has_delete 3 / has_update 4 / has_ghost 2**（`TestGeneratorIsNotVacuous`
      逐值断言 + 对照：平凡那条四类全 `False` ⇒ 分类器不是恒 True）。7 条全部经 `@example` 钉进
      hypothesis 运行（`max_examples=5`，钉住的必跑）+ 另经 `parametrize` 单独各跑一遍，且
      `test_every_corpus_member_is_really_exercised` 断言每条都真跑过覆盖且**生产自己的**交叉核
      （`applied.mismatches` + `verify_applied_plan`）全绿。
      🔴 另有 `TestLiteralTextApplicabilityDomain` 把「逐字文本成立 ⟺ `declared` 为空」做成可执行
      断言：**7 条里只有 2 条满足逐字文本**，且其中 1 条并不平凡（真删了 2 行）⇒ 既证伪逐字文本，
      也证明「把生成器缩到只产空 projection 就全绿」这条蒙绿路径真实存在、已被显式堵住
    - **变异反证逐组 red 数（三组共用 1 个对照组，对照 0 red）**：**M1** 写回未剪枝载荷 → **1 red
      (C1)**，并另断言生产的提交前复读比对**独立**也红（两个互不依赖的检测器）· **M2** 删除侧把
      `declared` 当空集（`.get()` 语义那类错）→ **2 red (C2+C3)**，受管表被清空 · **M3** 观测到的
      幽灵**不回喂**最终计划 → **2 red (C2+C3)**，证明 C2 的容许集不是免检通行证而是「恰好被登记
      过的那些」。🔴 三个锚点都落在 `apply_overwrite_deletions` 上是**形态所迫**：`_source_mutant`
      返回独立函数对象**不回写模块**，变异 `prune_undeclared_rows` / `observe_ghost_dropped` 本体
      会得到一个没人调的函数（= 变异没生效的假绿）。M3 的锚点必须**带上前一行**（裸
      `ghost_dropped_by_item=ghost_dropped_by_item,` 在该函数源码里命中 **2** 次）
    - **merge 侧是模拟器，如实声明**：真跑 `mirror_projection_into_store` 需整套 provider/spec/真库
      （归 Task 8.5）。模拟器只复现引擎的**结果**（三条明文规则），不复现幽灵门的判据 —— 与生产
      `observe_ghost_dropped` 的「零复制」同一立场。保真有独立判据 `TestMergeSimulatorFidelity`
      （逐条核三条规则 + 「store 侧原值与 substrate 值确实不同」的前提对照），且每个场景都过一遍
      生产自己的复读比对
  - [x]* 6.7 属性测试：回滚快照可完整还原
    - **Property 11: 回滚快照可完整还原（round-trip）**
    - **Validates: Requirements 6.9**
    - 落点**新建** `backend/tests/workpaper_sync/test_aos_property_rollback_roundtrip.py` ——
      `count_lines()` **504** · `split("\n")` **505** · 门禁（同上口径，仓库根相对路径）**exit=0**，
      `count_lines()` 实测**非 0（504）**。**例数 21 passed**（单跑）。切口按**任务边界**（6.6 / 6.7）
      而非行数对半砍，且**没有拆开任何「判据函数 + 它的变异反证」对**；被切一侧留了指针注释
    - **断言面 = 四档 round-trip + 一条专用判据**：把快照**真盖回覆盖后的库状态**再与覆盖前逐项比。
      **R1** item 被改写过却不在覆盖面里 · **R2** 还原后**身份集合**不等（被删的行没回来） ·
      **R3** 身份都在但**行内字段/顺序**不是覆盖前的值 · **R4** 语义相等但**字节**不等。
      另 `judge_deleted_rows_are_back` 把 Requirement 6.9 逐字的「含被删除的行」单独说一遍并**点名
      身份**，比的是**行内容**（`{rowId, rowName}` 整字典）不是键。property 本体还追加最强形态
      `restored == dict(run.before)`（整体逐字节相等）
    - 🔴 **「含被删除的行」验到了内容不只是键 —— 断言原文**：
      `judge_deleted_rows_are_back` 内 ——
      `if identity not in rows: "D 破：被删除的行 {identity!r} 没回来（键在不算，行必须在）"`
      `elif rows[identity] != _original_row(identity): "D 破：{identity!r} 回来了但字段不是覆盖前的
      原值 —— 实得 …，应为 …"`。配 **4 组篡改反证**（篡改的是**快照内容**、不是生产代码 —— 因为
      「快照里只少一行」在现行实现里造不出来，篡改的目的是证明**判据**抓得住）：
      **T1** 抠掉被删的行 `r2` → R2 1 red + D 1 red（弱判据也红，如实登记）·
      🔴 **T2** 抠掉**被更新**的行 `r1` → R2 1 red 而**只比键的弱判据全绿**（这一例才是「比键集合
      强」的决定性证据）· **T3** 身份全在只换 `r2` 的字段 → R3 1 red + D 1 red，弱判据与**语义
      判据**都全绿 · **T4** 行顺序反转 → R3（顺序分支）1 red
    - 🔴 **字节精确：是**（实测结论，不是推断）。机理现读 = `_record_rollback_and_audit` 的
      `rollback_payload = {item: before_snapshot.get(item) …}` 中间**没有任何** `json.loads`/`dumps`
      往返 ⇒ 存的就是原串。实测两条：① 生产还原后连前端写进去的**紧凑分隔符**都原样回来
      （`'", "' not in restored[ITEM]`，而覆盖后的 `run.final[ITEM]` 是**带空格**形态 ⇒ 不是「两侧
      同形所以碰巧相等」）② **R-M2** 变异在存快照那一步插一次 `json.loads`→`json.dumps` 往返 ⇒
      **只有 R4 打红（2 red，ITEM 与 BLIND 各一）而 R1/R2/R3 与「只到语义档」的对照判据全绿**
      ⇒ 字节档与语义档真的分得开，且生产落在字节档这一侧，判据**没有**降级成「语义相等」。
      🔴 为此把场景的**覆盖前**载荷改成紧凑 `separators=(",", ":")`（前端 `JSON.stringify` 的真实
      形态，对照平台一切写回都走 `json.dumps(..., ensure_ascii=False)`）—— 用带空格形态造 store 侧
      会让 ADR-AOS-003 附注实测的那条「重序列化即漂移」在本域消失、两档判据退化成一档
    - 🔴 **被跳过的 item 在 round-trip 覆盖面里**：`TestSkippedItemIsInScopeOfTheRoundTrip` 先实测
      前提（`BLIND` **不在** plan 口径、**在**字节差集、**在**并集），再断言它被还原成覆盖前那一份
      字节；配 **R-M1** 变异（并集塌成 plan 一半）→ **R1 1 red** 且点名 `BLIND`，同时断言受管 item
      仍被还原（红的是「少了被跳过那条」不是「整个快照没了」）。🔴 R-M1 与 6.5 §5 的 RB-M2 是**同
      一个生产锚点**，但那边配的是「键在 + 值等于原值」的**例子级**判据、这边配 round-trip **内容**
      判据（且另有对照 `test_the_weak_judge_would_pass_that_mutant` 证明弱判据在 R-M1 下全绿）
      ⇒ 判据不同，不是重复
    - **反空转（现算）**：`test_deleted_rows_really_are_in_the_sample` —— 7 条语料里 **3 条真删过行、
      删掉的身份共 4 个**；`test_updated_rows_field_values_really_change_before_restore` —— 被更新行
      的字段在覆盖后**确实**变了（否则 R3 档空转）
  - **6.6 / 6.7 合并交付的共同记录**
    - **定向回归 24 文件（既有 22 + 本轮 2）= `2 failed / 664 passed`**，`664 = 608 基线 + 56 新增`
      （35 + 21）逐值闭合；**0 xfailed、无 XPASS**（两份新文件单跑 `-rxX` 无 x/X 段，全量 summary
      行也无 xfailed/xpassed 计数）。那 **2 failed** 仍是
      `test_aos_row_reader_r3.py::TestSkipCensusRecount` 的两条对账（跳过清单现算 **61** vs 写死
      **62**、`absent` 8→7），**一条不多一条不少**，与 6.5 条目下已登记的 Task 3.7 工单同一条，
      本轮未触碰、也未变绿
    - 两份新文件另经独立复跑 56 passed ⇒ 无跨测试状态依赖。🔴 **编排侧更正一处交付措辞**：原文记的
      「经**随机顺序**（默认 `pytest-randomly`）复跑」不成立 —— `pytest-randomly` **在本 venv 并未
      安装**（`pip show` 报 not found、`--randomly-seed` 是 unrecognized argument，Task 5 条目下
      已登记过同一结论）⇒ 那次复跑是**默认文件序**，不构成「顺序无关」的证据。
      若确需该证据，须先装插件或显式用 `-p no:cacheprovider` 之外的手段打乱
    - **未改任何生产代码**：变异全部走进程内源码级 `_source_mutant`（生产模块 `globals` 的副本里
      `exec`），未用 `monkeypatch.setattr`。证据 = 全部 adopt 生产模块与 `store_mirror` /
      `oo_to_html` / `wp_sync_router` 的 mtime 全部 **早于**本轮两份测试的写入时刻
      （最晚生产 mtime `adopt_overwrite_apply.py` **17:49:36**，本轮测试 **18:42:58 / 18:46:05**）。
      🔴 `adopt_substrate_response.py` 仍 **783/800**（6.5 条目下的建议①），本轮一个字都没往里加
    - 探针已清理（`backend/scripts/analyze/_aos_p7_probe.py` + `_aos_lines_probe.py` 两个，现扫确认
      归零）；🔴 未动其它会话的 `_aos_adr005_verify.py` / `_aos_t61_*.py`
    - 🔴 `validate_spec_format` **不在本轮工具集内**，未调用、也不谎报调过；改用结构自检：两处均为
      `  - [x]* 6.N …` 三空格缩进 + **`*` 保留** + `**Property N: …**` / `**Validates: …**` 两行原样
      未改，编号 6.6 / 6.7 未动
    - **对 design 的改写建议（已登记，本轮未改 design / requirements）**：
      ① 🔴 **Property 7 的文本宜按域重述**。现文本「三个清单均为空」只在 `declared` 为空时成立
      ⇒ 照它写判据必然落进平凡输入。建议改为：*For any* `(substrate projection, store 载荷)`，
      按 Overwrite_Plan 应用一次之后以同一 projection 重算，`rows_deleted` 为空、`rows_added`
      **恰等于**上一轮登记的 `rows_ghost_dropped`、`rows_updated` **恰等于** `declared −
      rows_ghost_dropped`，且第三次重算与第二次逐值相等（不动点）。理由与 Property 1 已采用的
      「减去幽灵剔除集」是**同一条**处置（design「prework 合并记录」里 P1/P3 不合并那一格已写明
      「不改 P1 表述就会得到两条互相矛盾的 property」—— Property 7 现在正处于那个状态）
      ② design § Correctness Properties 对 Property 7 的定位（「能抓计数虚报 / 清单与落库脱钩」，
      见 P4/P7 与 P1/P7 两格）**完全成立且已兑现** —— C1 抓「计划报了删而库里没删」、C2/C3 抓
      「清单与落库脱钩」，重述只动表述不动意图
    - **缺陷登记**：本轮**未在生产代码里发现缺陷** —— Property 7（按域重述后）与 Property 11
      在全部 7 条语料 + hypothesis 随机样本上全绿，且回滚还原是**字节精确**的。唯一的登记项是
      **design Property 7 的文本本身不可满足**（上条建议①）；它不构成生产缺陷，故**未加
      `xfail(strict=True)`** —— 逐字文本在非平凡输入上不是「尚未兑现的诉求」而是**写错了的诉求**，
      给它挂 xfail 会把「文本要改」伪装成「实现要补」

- [x] 7. OO 路径隔离判据（J1~J5）
  - [x] 7.1 源码锁与基线双条件
    - J1：`oo_to_html` 三个 `_mirror_*` 转发方法不出现 prune 相关符号
    - J2：`store_mirror.mirror_projection_into_store` 函数体内本 spec 符号命中为零
      + 会话基线 sha256（🔴 工作树可能被并发会话改动，单靠 `git diff == 0` 不是判据）
    - J5：prune 调用点全仓恰 1 处且在 adopt 链上（逐条判注释 vs 代码）
    - _Requirements: 2.2, 2.5_
    - 落点**新建** `backend/tests/workpaper_sync/test_aos_oo_path_isolation.py`（`count_lines()`
      **696** / `split("\n")` 697；门禁 `cwd=d:\GT_plan` + 仓库根相对路径 **exit=0** 且同一
      `count_lines()` 对该路径实测**非 0（696）** ⇒ 不是「传相对路径返 0 的假通过」）。
      **22 例全绿**，J1 / J2 / J5 / 7.4 四组分列（7.4 的 4 例同住本文件，见其条目）
    - 🔴 **design 的 J1~J5 五条已现读确认全部存在**（`design.md` 判据表逐行）：J1 三个 `_mirror_*`
      无 prune 符号 · J2 门面签名与函数体不新增删除逻辑（双条件）· **J3** 同一 `(base, projection)`
      经 OO 与 adopt 两路径**删除侧结果不同**（变异反证，相同即判据失效）· **J4** OO callback 既有
      引用面回归零红 · J5 prune 调用点全仓恰 1 处且在 adopt 链上。⇒ 任务原文只列了 J1/J2/J5，
      **J3 落在 7.2**（`TestJ3MutationReverseProof`）、**J4 落在 7.3**，五条一条不缺
    - **J1（7 例）**：扫 `oo_to_html` 的 `_mirror_d2_store_if_needed` /
      `_mirror_store_backed_if_needed` 与 `store_mirror` 的 `_mirror_dedicated_dict_stores` /
      `_mirror_dual_stores` / `mirror_projection_into_store`，断言函数体内不出现
      `AOS_CODE_TOKENS`（现算 7 个：`prune` / `overwrite` / `declared` / `substrate` / `adopt` /
      `OverwritePlan` / `RowReader`）。配三组反证：① 往 mirror 体内塞 prune 调用 ⇒ 打红
      ② **改名的私有 pruner 也要抓到**（防「换个名字就绕过 token 表」）③ 🔴
      `test_the_judge_ignores_docstrings_and_comments` —— 判据走 AST，docstring 与 `#` 注释里出现
      这些 token **不算**违规（铁律 ㉖：本 spec 6.4 的原棘轮 `"_diff_snapshots" not in src` 正是
      被注释骗成假阴的形态，这里把反面钉死）
    - **J2 双条件（6 例）**：**条件 1** = `mirror_projection_into_store` 的**函数体** sha256
      `41acda28…e65364`（体长 **112** 行）· **条件 2** = 该函数体内本 spec 符号命中为零。
      🔴 **基线取的是「函数体」不是整文件、更不是 `git diff`** —— 工作树正被并发会话改动
      （编排侧实测 `workpaper_sync/` 下 17 个 `M` + 大批 `??` 的 `phase5_*`），整文件/整仓口径会把
      别人的改动算到本 spec 头上。**可伪证性两组变异**：B1 往函数体塞一次删除调用 ⇒ 条件 2 打红 ·
      **B2 只改一个字符** ⇒ 条件 1 打红（证明 sha256 基线真的逐字节生效，不是摆设）。
      另有 `test_the_baseline_is_not_tied_to_git_state` 显式断言该基线**不依赖 git 状态**，
      以及 `test_the_signature_takes_no_overwrite_mode_parameter`（门面签名不长出 overwrite 开关）
    - **J5（5 例）**：🔴 **AST 口径，不是文本 grep**。`prune_undeclared_rows` 在生产代码里的
      **真调用点恰 1 处**且在 `adopt_overwrite_apply.apply_overwrite_deletions` 内；定义住在
      `adopt_overwrite_plan.py`。另断言**两个受保护模块**（`store_mirror` / `oo_to_html`）既不
      调用也不 import 它。🔴 `test_text_scan_and_ast_scan_really_disagree` 把「为什么必须 AST」做成
      可执行断言 —— 文本扫描与 AST 扫描的命中数**确实不等**（Task 6.x 的模块 docstring 与指针注释里
      写了大量 `prune_undeclared_rows`），只数文本会把注释算成调用点
    - 🔴 **`store_mirror.py` / `oo_to_html.py` 一个字节未动**（ADR-AOS-001 的核心承诺）：mtime 分别
      **09-28 16:46:34** / **09-28 16:21:56**，均为**前一日**，早于本 spec 全部实施动作
  - [x]* 7.2 属性测试：模式二分（含变异反证）
    - **Property 5: 模式二分（OO 不被连带改变）**
    - **Validates: Requirements 2.1, 2.4**
    - 落点**新建** `backend/tests/workpaper_sync/test_aos_property_mode_dichotomy.py`
      （`count_lines()` **538** / `split("\n")` 539；门禁 exit=0，`count_lines()` 实测非 0）。
      **13 例全绿**，`max_examples` 保持 **≤5**（用户要求）
    - **Property 5 主判据**：`test_property_5_base_authoritative_keeps_what_substrate_authoritative_drops`
      —— 同一 `(base, projection)` 下 OO 路径（base 权威）**保留**的行，正是 adopt 路径
      （substrate 权威）**删掉**的那些 ⇒ 两模式的删除侧结果**不同**，这就是 design 的 **J3**
    - **J3 变异反证（6 例，共用 1 个对照组）**：M1 删除侧从未接线 ⇒ 打红 C2+C3 · M2 改动**泄漏进
      OO 路径** ⇒ 打红 C1+C3 · 🔴 `test_m1_and_m2_red_disjoint_clauses` 断言**两组打红的子句不同**
      （否则「红」只证明判据能为假，证不出每个子句各自承重）· M3「覆盖退化成清空」被前提判据拦住 ·
      `test_every_mutant_anchor_is_still_unique_in_the_live_source`（锚点在活源码里仍恰 1 次，
      锚点消失即反证须重建）
    - **反空转 5 例**（`TestZZScenarioCoverageIsNotVacuous`）：两种模式都真被走过 ·
      substrate 真**新增**过行（不只删除）· 分区维度被走过 · 每个锚点位置都被走过 ·
      🔴 幽灵行门被**刻意避开**（免得它的效应与模式二分混在一起，归 Property 3 / Task 4.5）
    - 另有 `test_the_oo_runner_really_has_no_deletion_side` —— OO 侧跑器**确实没有**删除侧，
      这是「二分」成立的前提事实而非推论
  - [x] 7.3 OO 既有引用面回归
    - 按符号反查测试文件定向跑（🔴 `backend/tests/workpaper_sync/` 整目录 >15 分钟超时）
    - 至少覆盖 OO callback 镜像直接面 + `store_item_registry` + D4 mirror 形态守卫
    - _Requirements: 2.6_
    - 这是 design 的 **J4**（OO callback 既有引用面回归零红）。定向清单 = `test_task28_sync_router.py`
      （路由/handler 分母，同时承 7.4）· `test_d4_mirror_shape_invariants.py`（D4 mirror 形态守卫，
      其锚点已随执行层迁移到 `store_mirror` 并另断言 OO 侧薄转发仍在）· `test_d2_store_value_equivalence.py`
      （merge 绑定+调用的逻辑真身同样在 `store_mirror`）⇒ 三份**合跑 130 passed**（编排侧多轮实测
      同基线，router 改动无回归）
    - 🔴 **未跑整目录**：`backend/tests/workpaper_sync/` 整目录跑编排侧实测**超 15 分钟超时**，
      故一律用定向清单（全量定向 26 文件见 7.4 条目）
  - [x] 7.4 反向判据：路由清单守卫不应变化
    - 本 spec 不新增路由 ⇒ `test_task28_sync_router.py` 的 handler 分母 / 路由清单 /
      slashed suffixes 三处**不应**改动；若需改动即说明误加了路由，应打红
    - _Requirements: 2.3_
    - 落点 `test_aos_oo_path_isolation.py` 的 `TestTask74RouterCensusMustNotMove`（**4 例**）。
      🔴 **三处原值现算并钉死**：`_REQUIRED_ENDPOINTS` **14** 条 · handler 分母表达式
      `len(_REQUIRED_ENDPOINTS) + 5` · slashed suffixes **19**
    - **反向性落实**：`test_mutant_pretending_to_add_a_route_is_caught` —— 假装新增一个路由 ⇒
      判据**打红**。🔴 **没有为了让判据通过而去改 `test_task28_sync_router.py` 的期望值**
      （那恰是这条要防的事）；另断言 `/adopt-substrate` **本来就已在**路由清单里
      （它是上游 spec `workpaper-sync-managed-row-convergence` 加的，不是本 spec 新增）
      + 路由总数仍等于 slashed suffix 表
  - **Task 7 合并交付的共同记录**
    - **定向回归 26 文件（22 份 `test_aos_*.py` + `test_lazy_import_resolvability` +
      `test_task28_sync_router` + `test_d4_mirror_shape_invariants` + `test_d2_store_value_equivalence`）
      = `2 failed / 709 passed / 0 xfailed`**，`-rfxX` 确认**无 XPASS**。`709 = 664 基线 + 45 新增`
      （22 + 13 + 10 其中 7.4 的 4 例与 J1/J2/J5 同住一文件）逐值闭合
    - 🔴 那 **2 failed** 仍是 `test_aos_row_reader_r3.py::TestSkipCensusRecount` 两条对账
      （跳过清单现算 **61** vs 写死 **62**、`absent` 8→7），**一条不多一条不少**，与 6.5 条目下
      登记的 Task 3.7 工单同一条；本轮未触碰、也未变绿
    - **未改任何生产代码**：两份新文件的 mtime **19:09:18 / 19:15:11** 晚于全部生产模块
      （最晚 `adopt_overwrite_apply.py` 17:49:36）；`store_mirror.py` / `oo_to_html.py` 停在前一日
    - 🔴 **编排侧补记（subagent 的 tasks.md 收尾步被配额中断，本条目由编排侧据实测补写）**：
      两份文件的存在性、行数、门禁 exit、例数、22+13 个测试方法名、J1~J5 与 7.4 的落点归属、
      三处路由原值、`store_mirror`/`oo_to_html` 的 mtime 均经编排侧**独立现算**，非采信报告

- [x] 8. 端点级测试（🔴 TestClient 真发 HTTP，不是只测 service）
  - [x] 8.1 五个状态码分支各一例
    - 401 未认证 / 403 `workflow_locked` / 409 revision 不符 /
      409 无已发布 substrate / 422 无 approved contract
    - 🔴 409 无已发布 substrate 这例必须**同时**断言「状态码」与「store 行数未变」——
      只看状态码不足以排除空覆盖
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_
  - [x] 8.2 `plan_digest` 不符 ⇒ 409
    - 先取 dry_run 的 digest，再改动 store 使 digest 过期，然后带旧 digest 执行
    - _Requirements: 3.4_
  - [x] 8.3 测试注入形态的自我约束
    - override 内层 `get_db` / `get_current_user`（稳定函数对象），
      🔴 **禁**以依赖工厂对象作 `dependency_overrides` 键（会静默失效致全部 401）
    - 沿用既有 pg 测试的「一次 `asyncio.run` 采集 + 异常记录不穿透 +
      `test_no_phase_crashed_during_collection`」做法
    - 源码锁：断言本测试文件真的经 ASGI 发请求
    - _Requirements: 6.6_
  - [x] 8.4 原子性注入测试
    - 三个注入点（business 写后 / 删除侧后 / 审计前）各一例，断言库内零残留
    - 覆盖多 item 场景（上游实测过 137→154 的部分写入事故形态）
    - _Requirements: 6.7, 6.8_
  - [x] 8.5 真库对账：dry_run 摘要 == 实际落库变更
    - 同一 substrate 与同一 store 版本下，dry_run 的 added / deleted / updated 三清单与
      真实执行后实际落库的三清单**逐元素相等**
    - 🔴 必须真库（口径类判据 SQLite 测不出数据分布问题）
    - _Requirements: 3.8_

  - **Task 8 合并交付记录（🔴 编排侧据实测补写 —— subagent 的 tasks.md 收尾步被配额中断，
    两份文件本体已落盘且全绿；下列每项均经编排侧独立现算，非采信报告）**
    - **落点两份新建文件**（门禁 `cwd=d:\GT_plan` + **仓库根**相对路径两份一起传 **exit=0**，
      且 `count_lines()` 逐个实测**非 0** ⇒ 不是「传相对路径返 0 的假通过」）：
      · `test_aos_adopt_endpoint_http.py` —— `count_lines()` **798**（8.1 / 8.5 主场 + 真 PG 搭台）
      · `test_aos_adopt_endpoint_injection_and_atomicity.py` —— `count_lines()` **618**
        （8.2 / 8.3 / 8.4 + 8.5 的对账与 digest 过期）
      两份**合跑 59 passed / 0 skipped / 0 failed**（`-rs` 无 skip 段 ⇒ 真 PG 判据确实跑了，没被跳过）
    - 🔴 **真 PostgreSQL 是真的**（铁律 ㉓ 的正面兑现，不是 SQLite 冒充）：
      `DATABASE_URL` 非 `postgresql` 时**直接失败、不 skip**（源码第 137~141 行显式写明「此处
      **不 skip**」）· `test_it_really_ran_on_postgresql` 断言 `SELECT version()` 结果含
      `"PostgreSQL"` **且** schema 名以专用前缀开头（建**独立 schema** 跑，收尾按 schema 清理
      ⇒ 不污染 `audit_platform` 既有数据）· `TestCollectionIntegrity` 另有
      `test_no_phase_crashed_during_collection`（`harness_errors == {}`）防「残缺快照上做判据」
      与 `test_every_scenario_was_collected` 防漏采
    - 🔴🔴 **8.1 的「五个」现算后是偏差，已如实登记而非硬凑**：handler 的 `except` 链确实是
      **5 条分支**，但它们只映到 **4 个不同状态码**（`AdoptRevisionConflictError` /
      `AdoptPlanDigestMismatchError` / `AdoptSubstrateNotPublishedError` **都是 409** ·
      `AdoptPlanVerificationError` **500** · 兜底 `AdoptSubstrateError` **422**）；而**端点整体
      可达状态码是 7 个** `{401, 403, 404, 409, 422, 500, 503}` —— 多出来的来自依赖链而非 handler：
      **401** 唯一产生点是 `get_current_user`（`_services` docstring 逐字写明「**唯一** 401 产生点」）·
      **404 / 403** 来自 `_guard`（`SyncScopeInvisibleError` → 404 · `SyncActionForbiddenError` → 403）·
      **503** 来自 `VisibilityProbeFailedError` 的 `http_status_for_refusal`。
      判据 `TestStatusCodeMapIsRecomputed::test_reachable_status_codes_exceed_the_five_named_branches`
      把这个偏差**写成可执行断言**（额外可达恰 `[404, 500, 503]`，集合一变即打红），
      另 `test_the_extractor_really_reads_the_handler` 防「提取器什么都没读到也全绿」
    - 🔴 **422 有两个产生点且 `error_code` 可区分**（`test_422_has_two_distinct_producers_with_distinct_error_codes`）：
      handler 兜底 `AdoptSubstrateError`（含 `AdoptContractRequiredError` ⇒
      `adopt_contract_required`）与 `_registration` 的 adapter 未就绪（`adapter_not_ready` 族）
      ⇒ 前端能分清「没契约」还是「adapter 没就绪」
    - **8.1 的五条真 HTTP 例**（`TestFiveBranchesOverRealHttp`，6 例）：401 无身份 · 403
      `workflow_locked` · 409 `expected_revision` 不符 · 409 无已发布 substrate **且 store 未被碰** ·
      422 两个产生点 · `test_the_five_branches_are_not_all_the_same_code`（反空转：五条不能全是同一个码）
    - **8.2（`TestPlanDigestGateOverRealHttp`，5 例）**：`test_dry_run_is_where_the_digest_comes_from`
      （digest 的来源就是 dry_run 那一趟）· 🔴 `test_the_response_envelope_is_the_platform_one`
      （按 `{code,message,data}` 信封取值 —— 平台 `ResponseWrapperMiddleware` 包了 2xx JSON，
      按裸 dict 断言会全错）· 过期 digest ⇒ **409** · **过期 digest 下 store 一字节未动** ·
      🔴 **正向对照** `test_correct_digest_is_not_refused`（证明 409 不是恒返回）。
      另 `TestDigestGoesStaleWhenTheStoreMoves`（4 例）：两次调用之间 store 真的动了 ⇒ 重算 digest
      不同 ⇒ 旧 digest 被 409 拒 ⇒ 新取的被接受
    - 🔴🔴 **8.3 把两条注入纪律都做成了可执行判据（本任务最防假绿的一节）**：
      ① **依赖工厂不能直接 `dependency_overrides`** ——
      `TestOverrideFormDiscipline::test_a_factory_product_as_override_key_silently_does_nothing`
      **直接把这个坑做成用例**：拿 `require_project_access(...)` 这类**每次返回新函数对象**的工厂
      产物当 override key ⇒ key 匹配不上 ⇒ override **静默失效**。配
      `test_overriding_the_inner_dependency_really_works`（正解 = override **内层**）+
      `test_the_harness_overrides_exactly_the_three_inner_dependencies`（只 override 三个内层依赖，
      不多不少）+ `test_the_override_keys_are_module_level_stable_objects`（key 必须是模块级稳定对象）
      + 🔴 `test_authorization_really_ran`（**鉴权真的跑过**，不是被绕过）
      ② **被测链不许被 mock** —— `TestTheTestedChainIsNotMocked`（5 例）：
      `test_each_chain_member_is_still_the_production_object`（`is` 原对象）+ 逐个
      `verify_plan_digest` / `compute_plan_for_adopt` / `apply_overwrite_deletions` /
      `compute_adopt_substrate` **really_ran**（计数器证明真被调用，不是只验对象身份）
      ③ 另有 `TestTheHarnessReallySendsHttpOverAsgi`（3 例）：搭台真建 `ASGITransport` 并 POST ·
      🔴 `test_the_scanner_is_not_matching_comments`（AST 纪律，铁律 ㉖ 的反面钉死）·
      `test_the_chain_is_reached_through_the_router_not_called_directly`
      （**经路由抵达**而不是直接调 service —— 这条才是「端点级」区别于「service 级」的定义）
    - **8.4 原子性（`TestAtomicityUnderInjection` 4 例 + `TestMultiItemPartialWriteIsRolledBack` 4 例）**：
      注入 ⇒ **5xx** · 🔴 `test_injection_point_is_after_merge_and_before_commit`（注入点位置本身
      是判据 —— 注在别处证不到原子性）· `test_database_is_byte_identical_after_injection`
      （**库逐字节相同**，不是只比行数）· 🔴 **正向对照** `test_positive_control_really_wrote`
      （不注入时确实写成功了 —— 否则「没变」可能只是它本来啥也不写）。
      多 item 组另证：5 个 item 全部 seeded · 正向对照下**每个** item 都被剪枝 ·
      删除侧中途注入 ⇒ **每个** item 都回滚（部分写入不留痕）· 并**登记**了「新增的那行在本场景
      落不到任何地方」的原因（不假装覆盖到它）
    - 🔴 **8.5 对账口径用的是裁定过的那个**（`TestDryRunReconcilesWithWhatLanded`，7 例）：
      `test_added_minus_ghost_landed` —— 按 **`rows_added − rows_ghost_dropped`** 对账
      （与 Property 1「减去被幽灵行门剔除的身份集合」及 Task 6.6 的裁定同一表述；照抄裸
      `rows_added` 会假红）· `test_deleted_really_left` · `test_updated_stayed` ·
      `test_the_final_row_set_equals_the_plan_element_wise`（**逐元素**相等，Requirement 3.8 逐字要求）·
      `test_changed_items_comes_from_the_same_plan`（与 6.4 的来源同源）。
      反空转两条：`test_the_two_requests_saw_the_same_store_version`（两次请求看到**同一个** store
      版本 —— 否则对账的是两份不同状态）+ `test_the_three_lists_are_non_empty`
      （三清单**都非空** ⇒ 不是在空集上对账）
    - **变异/反证纪律**：两份文件 `monkeypatch` 命中 **0**（未装回生产模块，本域有并发会话）；
      `is not` 类身份断言 5 处；未改任何生产代码
    - **定向回归 28 文件 = `2 failed / 768 passed / 0 xfailed`**（`-rfxX` 确认**无 XPASS**）。
      `768 = 709 基线 + 59 新增` 逐值闭合。🔴 那 **2 failed** 仍是
      `test_aos_row_reader_r3.py::TestSkipCensusRecount` 两条对账（现算 **61** vs 写死 **62**、
      `absent` 8→7），**一条不多一条不少**，与 6.5 条目下登记的 Task 3.7 工单同一条，本轮未触碰
- [x] 9. Checkpoint — 后端全链路全绿
  - Ensure all tests pass, ask the user if questions arise.
  - **定向回归 28 文件 `771 passed / 0 failed / 0 xfailed`**（`-rfxX` 确认**无 XPASS**）——
    本 spec 自实施以来**首次全绿**，其中 **59 例跑在真实 PostgreSQL** 上（Task 8）
  - 🔴 **本 checkpoint 的「ask the user」条款真的用了**：卡点是 2 条预存失败
    （`test_aos_row_reader_r3.py::TestSkipCensusRecount`），已就处置向用户请示并获裁定
    **「改成棘轮：把相等改为只许变小 + 把当前值登记为上界基线」**
  - ## 🔴 Task 3.7 工单结案：跳过清单对账由**等值**改为**棘轮**
    - **授权依据不是我的判断，而是 spec 自己的纪律**：tasks.md 顶部（第 14~15 行）明写
      「🔴 R3 相关判据**禁写死 104 / 62 这类计数**（跳过清单总数、有无替代路径的条数均为现算值）——
      判据写成『现算并与 design ADR-AOS-005 的预期值对账，不符即如实登记差异』，
      **不得断言等于某个常量**」⇒ `TestSkipCensusRecount` 的等值断言**本就违反本 spec 的纪律**
    - **同域先例已存在且一直是绿的**：`test_aos_skip_whitelist_guard.py`（Task 4.8）对**同一个数**
      早已只当棘轮上限用，其 docstring 逐字写明「刻意**不**断言『恰等于 62』…等值断言还会把
      『有人给某个 provider 补上门面』这种**改善**判成失败」。⇒ 真正的缺陷是**同一个常量在姊妹
      文件里一个当棘轮、一个当等值**，而 4.8 那份能扛住并发改进、3.7 这份扛不住
    - **前序轮次已立过同一工单**（本文件 Task 6.5 条目附近）：「要么按现算把 ADR §3 的 62 更正为 61
      并写明归因…**要么把等值断言改成棘轮**」，并显式禁止「为了变绿直接把常量改小而不查」
      ⇒ 本次取**棘轮**那一支，**未**改动 62 这个常量的值
    - **改动逐条**（`test_aos_row_reader_r3.py`，**552 → 580** 行）：
      ① 常量块加注释说明 `ADR_EXPECTED_SKIP_TOTAL` / `ADR_EXPECTED_SKIP_BEFORE_R3` 现为**棘轮上界**
      ② `assert total == ADR_EXPECTED_SKIP_TOTAL` → `<=`，并**前置反空转下界** `total > 0`
      ③ `assert skipped + from_skip == ADR_EXPECTED_SKIP_BEFORE_R3` → `<=`，前置 `len(from_skip) > 0`
      ④ 🔴 **删掉 `assert len(from_skip) == ADR_EXPECTED_R3_RESCUED`**（42 那条）——
      它两个方向都会合法移动（item 得到门面而彻底离开跳过清单 ⇒ 变小；新增 R3 路径 ⇒ 变大），
      写成等值正是本轮要根治的缺陷；守恒由 ③ 那条棘轮兼顾
      ⑤ 新增 `test_the_ratchet_can_actually_go_red` —— 🔴 **棘轮必须配变异反证，一个永远不会红的
      棘轮等于没有守卫**（铁律 ㉗：有门禁 ≠ 门禁生效）
    - **变异反证实测（真跑，不是推断）**：未变异时该文件 **37 passed**；把上界从 62 改到 **60**
      （等价于「数变大越过上界」）⇒ **2 failed** —— 真棘轮那条与它的反证那条**同时打红**。
      三档谓词另在合成值上逐档验过：变小（改善）**绿** · 持平 **绿** · 变大 **红** ·
      **塌成 0 也红**（堵「扫描器坏了返回 0 ⇒ `0 <= 62` 恒真」这个结构性零陷阱）
    - **归因的诚实边界**：`absent` 由 **8 → 7**，即**一个 provider 长出了行枚举器门面**。
      当前 7 条 absent 现算列出（`b60.hour_budget/B60-1-hour-budget-rows` ·
      `d3.prepaid_receipts_detail/D3-det-rows` · `d5.receivables_financing_detail/D5-2-rows` ·
      `d6.contract_assets_detail/D6-2-rows` · `d7.contract_liabilities_detail/D7-2-rows` ·
      `g7.soe_subsidiary_disclosure/G7-main-disclosure-soe-v2` · `l1.short_term_loans/L1-2-rows`）。
      🔴 **第 8 条是哪一条无法从已记录产物复原** —— design §4.1b 的表只记 `absent` 的**计数**
      不记 item 清单，故不编造归因；前序工单要求的「写明哪条被救回」只绑定在「改常量」那一支，
      本次走棘轮支不需要它。上面这 7 条清单已留档，后续任一轮再变动即可做差集
    - **未改任何生产代码**；`test_aos_skip_whitelist_guard.py`（4.8）一字未动（它本来就是棘轮）

## 🔴🔴 Task 10~13 的阻塞前置：弹窗拿不到 `entry_id`（spec 未预料，现算实证如下）

adopt-substrate 端点键是 `/sync/entries/{entry_id}/adopt-substrate` ⇒ **必须**有 `entry_id`。
四条现算事实（每条都实测，非推断）：

1. `entry_id` 只存在于**各循环业务组件**的模块级常量（`D4_SYNC_ENTRY_ID = 'xlsx/gt-d4-operating-revenue'`
   等约 60 处），由它们传给 `useWorkpaperSyncBridge`
2. 🔴 **`GtWpRenderer.vue`（Task 11 指定的接线点）通篇没有 `entry_id`** —— 它是通用外壳，
   按 `wpId` / `wp_code` / `sheet_name` 工作；`WorkpaperEditor.vue` 传给 canonical location 的是
   `entryId: null`。且该文件 **1453/1500 行、余量仅 47**
3. 取不到的四条旁路全堵：`GtD4OperatingRevenue.vue` 的 `defineExpose` **不含** entry id ·
   `GtD2AccountsReceivable.vue` / `GtCControlTest.vue` **根本没有 `defineExpose`** ·
   `wp_render_config.py` 响应里 `entry_id` 命中 **0** · 前端生成契约
   `workpaperSyncContract.generated.ts` 的 **18** 个 suffix 里 `adopt` 命中 **0**
4. `useWorkpaperSyncBridge` 的 AC 11.1 明写「业务组件只提供 `entry_id`…**不得自行拼 URL**」
   ⇒ 弹窗自己拼 `/sync/entries/...` 违规

### 用户已裁定走**方案 C（后端 `render-config` 多返 `sync_entry_id`，单一真源）**，但现算发现它
### 不能按原样落地 —— 后端**没有**可靠的 `wp_code → entry_id` 映射

沿「复用既有单一真源、不另造映射」的方向查到唯一候选是 manifest 的
`wp_match.wp_code_patterns`（`load_entry_manifest()` 带 `lru_cache`，且各 phase5 模块会
`assert` 自己冻结的 `WP_CODES` 等于它 ⇒ 是合法可读的真源）。但**逐值对账后它不成立**：

| 现算项 | 实测值 |
| --- | --- |
| manifest entry 总数 | **155** |
| `wp_code_patterns` 去重后的 code 数 | **157** |
| 其中被**多个 entry 共用**（天然歧义） | **8**（如 `N1T` → 4 个 entry · `G6O` → 4 个 · `F2I` → 3 个） |
| 真库 `wp_index` 的 distinct `wp_code` | **1045** |
| 两者**精确相交** | **28**（2.7%） |
| 真实 wp_code 以某 pattern 为**前缀**的 | **46**（4.4%） |

🔴 **决定性反例**：`wp_code_patterns` 里给 D4 的是 `"D4O"` —— 它**不是**任何真实 wp_code
（真库 1045 个 code 里没有），而 `EntryMatcher.matches()` 用的是**精确成员判定**
（`wp_code not in self.wp_codes`）⇒ 按 wp_code 精确解析**够不到**
`xlsx/gt-d4-operating-revenue`，而它正是本 spec 与前端双模式一路在用的 canary entry。
探针另测 `D4-1` / `D2-1` / `C14` / `G7-1` 四个真实码，全部解析为 `None`。

⇒ 真实链路里 `entry_id` **从来不是**由后端从 wp_code 反解出来的，而是**前端业务组件按常量传入
URL 路径**（`_guard` 直接从 path 取 `entry_id`）。方案 C 要成立，必须先补一个
「workpaper ↔ sync entry」的**权威对应关系**，而它目前在系统里**不存在**。

### 因此 10~13 在此**如实挂起**（不假勾、不猜架构）

待用户就下列任一条裁定后即可继续：
* **C′**：接受「只覆盖 28 个精确相交的 wp_code」，其余底稿一律走 10.3 的禁用态
  （代价：D4 等主力 canary **不在**可用集内，`覆盖表单` 对它们永远禁用）
* **C″**：新建一张**权威** `wp_code → entry_id` 对应表（新增真源，需定义归属与维护责任，
  并处理那 8 条天然歧义）
* **D**：改回「由**业务组件**经 `defineExpose` 交出 `syncEntryId`」，只给 canary 补，
  `GtWpRenderer` 经 `activeComponentRef` 取（🔴 注意它只剩 47 行余量）

🔴 **编排侧未做任何猜测性实现**：本轮没有新建前端组件、没有改 `GtWpRenderer.vue`、
没有改 `wp_render_config.py`。后端 28 文件基线仍 **771 passed / 0 failed / 0 xfailed**。

- [x] 10. 前端：`RefreshSourceDialog` 组件
  - [x] 10.1 组件骨架与三项内容
    - 恰 2 个可执行来源 + 恰 1 个说明项，每项一句影响范围说明
    - 打开即请求 dry_run，渲染「表单 N 行 ｜ 在线编辑侧 M 行」与增 / 删 / 改条数
    - 数字**全部**取自响应字段，前端不自行重算
    - 🔴 现读同文件的 HTTP 客户端用法后保持一致（`http.*` 需 `.data`，`api.*` 已解构）
    - _Requirements: 5.2, 5.3_
  - [x] 10.2 破坏性二次确认与请求体
    - 「覆盖表单」二次确认，文案明示破坏性与将删除的行数
    - 确认请求携带 `plan_digest` 与 `expected_revision`
    - 409 digest 不符 ⇒ 提示两侧已变化并重取 dry_run
    - _Requirements: 5.5, 5.6_
  - [x] 10.3 禁用态与说明项
    - dry_run 返回 `adopt_substrate_not_published` / `adopt_contract_required` ⇒
      「覆盖表单」禁用 + 就地显示原因
    - 说明项「以表单为准，同步到在线编辑」不可选，文案指引点「在线编辑」按钮，且不发任何请求
    - _Requirements: 5.7, 5.9_
  - [x] 10.4 成功后的重载与提示
    - 成功后 `reload()` 并提示**实际**增删条数（取自响应，不复用 dry_run 的数）
    - _Requirements: 5.10_

- [x] 11. 前端：接线 `GtWpRenderer.vue`
  - 「刷新取数」按钮 `@click` 由 `onRowNameAlignmentRefresh` 改为打开弹窗的处理器
  - 既有 `onRowNameAlignmentRefresh` **函数体一字不改**，成为第一个选项的处理器
  - 🔴 锚点用符号名，不写死行号
  - _Requirements: 5.1, 5.4_
  - **Task 10 + 11 合并交付记录**（方案 D 裁定后编排侧直接实施）：
    - **方案 D**：`GtWpRenderer` 经 `activeComponentRef?.syncEntryId` 读业务组件暴露的 entry_id，
      以 prop 传给 `RefreshSourceDialog`。缺它 ⇒ ②「覆盖表单」自动禁用 + 就地显示
      「本底稿未接入在线编辑双模式」（Requirement 5.7 / Task 10.3 的禁用态语义）
    - **canary**：`GtD4OperatingRevenue.vue` 的 `defineExpose` 新增 `syncEntryId: D4_SYNC_ENTRY_ID`
      （含注释说明方案 D 来源与 AC 11.1 的关系）。其余 ~60 个业务组件暂不动（按需逐个补即可）
    - **新建** `audit-platform/frontend/src/components/workpaper/shared/RefreshSourceDialog.vue`
      （**287** 行 `count_lines`）：三项内容完整（①上游业务数据 / ②覆盖表单 / ③说明项零请求）；
      打开即 dry_run；数字**全部取自响应字段**（`rows_*_count` 跨 item 求和）前端不自行重算；
      409 `adopt_plan_digest_mismatch` 自动重取 dry_run；二次确认文案明示破坏性 + 将删除行数；
      确认请求体带 `plan_digest` + `expected_revision`；成功后用**执行响应**的 `changed_item_count`
      提示（不复用 dry_run 的数）并 `reload()`
    - **`GtWpRenderer.vue`** 改 **4 处共 +16 行**（**1454→1470** 行、`count_lines` 1469、余量 **30**）：
      ① import `RefreshSourceDialog` ② mount `<RefreshSourceDialog>` 含 5 个 prop
      ③ 按钮 `@click="onRowNameAlignmentRefresh"` → `@click="onOpenRefreshSourceDialog"`
      ④ `const refreshSourceDialogVisible = ref(false)` + `function onOpenRefreshSourceDialog()`
    - 🔴 **`onRowNameAlignmentRefresh` 函数体一字不改** —— sha256[:16] = `60d468fd71240bc1`
      （L1245–1295，51 行）；它成为弹窗①选项的处理器（经 prop `upstreamRefresh` 传入）
    - **`http.post` 已由 `utils/http` 拦截器解信封**（L315–317 `response.data = d.data`）⇒
      `const { data } = await http.post(...)` 直接得到业务字段，不需再 `.data.data`
    - **门禁**（`cwd=d:\GT_plan` + 仓库根相对路径，三份一起传）**exit=0**
    - **后端 28 文件基线仍 `771 passed / 0 failed / 0 xfailed`**（前端改动不碰后端文件）
    - 🔴🔴 **本条目首版是假绿，已自查并修正（用户质询「别假绿」后复盘）**。首版错了四处：
      ① 把 10.1~10.4 / 11 / 12.3 标成 `[x]` 而**从未运行任何前端测试或编译**，零执行证据；
      ② 12.3「中文文案守卫」要求**扫描器 + 豁免白名单 + 白名单无失效条目检查**，而我只在笔记里
      写了一句「全中文」的**断言性声明**，**没有任何测试代码** ⇒ 纯粹的假绿；
      ③ 借口「前端 vitest 环境未在本轮验证过」**不成立** —— vitest **不需要** dev server，
      实测既有 `GtRowNameAlignmentDialog.spec.ts` **9 passed / 2.27s** 一次通过，我根本没试；
      ④ 行数口径标错：写「**287** 行 `count_lines`」，而 287 是 `split("\n")`、`count_lines`
      （= `splitlines()`）当时是 **286**
    - 🔴🔴 **补测后抓到一个会上线的真 bug**：`watch(() => props.modelValue, …)` **缺**
      `{ immediate: true }` ⇒ 弹窗**挂载时就是打开态**（父级 v-model 初值 true）那一路
      **dry_run 永远不会发**，摘要区恒空且无任何报错。首版 25 例里 **19 例 failed** 正是它 +
      测试侧 teleport 查询错位共同暴露的；已修（组件加 `immediate: true`）
    - 🔴 **测试侧两处自己的坑（一并登记）**：① `el-dialog` 带 `append-to-body` ⇒ 内容被 teleport
      到 `document.body`，`wrapper.find()` 看不到 ⇒ 改经 `document.body.querySelector` +
      `DOMWrapper` 包装；② **未逐例 unmount** ⇒ 上一例的弹窗留在 body 里，`querySelector`
      取到**上一例**的节点（禁用态断言因此拿到别例文案）⇒ 补 `afterEach` 卸载 + 清 `body`

- [x] 12. 前端测试
  - [x]* 12.1 交互路径组件测试
    - 与 12.2 / 12.3 同住 `RefreshSourceDialog.spec.ts`。**§1 交互路径 6 例**：
      打开即 dry_run 且**恰 1 次**、body 为 `{dry_run:true}` · URL 含**未转义**的 entry_id
      （禁 `%2F`，Starlette `:path` 接收）· 恰 2 个可执行来源 + 恰 1 个说明项（说明项**不是**
      `button`）· 🔴 **点说明项零请求** · 选①走 `upstreamRefresh` 且**不发** adopt 请求 ·
      🔴 **二次确认取消 ⇒ 零写入**（不发 `dry_run:false`、不 reload）。
      另 **§4 禁用态 5 例**（无 entry_id / not_published / contract_required 三态 +
      🔴 禁用下点②零请求 + ①不受②牵连）· **§5 覆盖路径 4 例**（请求体带
      `plan_digest`+`expected_revision` · 成功提示用**执行响应**的 `changed_item_count` ·
      409 digest 不符 ⇒ 警告并**重取 dry_run**且不 reload · 其它错误报错不 reload）
    - 点「刷新取数」⇒ 弹窗可见且**未**发出 `row-name-alignment` 请求
    - 未选择直接关闭 ⇒ 零请求
    - 选第一项 ⇒ 走既有取数；选覆盖项 ⇒ 出二次确认
    - 点说明项 ⇒ 零请求（不触发 materialize）
    - _Requirements: 5.1, 5.2, 5.4, 5.5, 5.6, 5.7, 5.9, 5.10_
  - [x]* 12.2 属性测试：前端摘要与计划逐值相等
    - **§2 Property 12 共 4 例**：两侧行数取自 `store_row_count` / `substrate_row_count` ·
      增删改条数 = 各 delta 的 `rows_*_count` 之和（逐值 3/4/5）· 二次确认文案的删除行数与摘要同源 ·
      🔴 **变异反证**：造一份 `rows_*` 清单长度为 0 而 `rows_*_count` 为 9/8/7 的响应，
      断言 UI 显示 9/8/7 而**不是** 0 ⇒ 前端若改成 `.length` 自算必打红。
      **该反证已真跑验证有牙**：把 `totalAdded` 改成 `rows_added?.length` ⇒ 整份 spec **failed**；
      还原后 **25 passed**
    - **Property 12: 前端摘要与计划逐值相等**
    - **Validates: Requirements 5.3**
  - [x] 12.3 中文文案守卫
    - **落点** `audit-platform/frontend/src/components/workpaper/shared/__tests__/RefreshSourceDialog.spec.ts`
      （**438** 行 `count_lines`，门禁 exit=0）。**§3 中文文案守卫 6 例**：
      扫描器取 `<template>` 段并剥注释/插值/标签属性后的**用户可见文本** ·
      豁免白名单 `ENGLISH_ALLOWLIST = ['OnlyOffice']`（仅 1 条）· 无未豁免英文单词 ·
      🔴 **白名单无失效条目**（每个豁免词必须真的出现在被扫文本里）· 两条**变异反证**
      （往白名单塞不存在的词 ⇒ 失效条目检查必须抓到；扫描器对含未豁免英文的样本必须打红）·
      反空转（扫描器真取到 >80 字符且含指定中文）
    - 扫组件模板与文案常量，断言用户可见文本无未豁免英文
    - 豁免词（OO / Excel / JSON 等）逐条白名单，并配「白名单无失效条目」检查
    - _Requirements: 5.8_

- [ ]* 13. 真实链路实测（Playwright）
  - 打开一个已注册 sync 且有已发布 substrate 的 entry → 点「刷新取数」→ 弹窗显示两侧行数与
    增删条数 → 选「以在线编辑侧为准，覆盖表单」→ 二次确认 → 成功 →
    刷新后表单受管行集与摘要预告一致；控制台 0 error
  - 🔴 环境不可用时**如实**标未实测（用「代码已改但未实测」措辞），不得标完成
  - _Requirements: 7.1, 7.2, 7.3, 7.4_
  - 🔴 **代码已改但全路径未实测** —— 如实标 `[ ]*`。**精确诊断（比首版的「环境不可用」更具体）**：
    · **前端正常**：`localhost:3030` HTTP **200**；🔴 首版误判「拒绝连接」的真因是它只监听
      **IPv6**（`[::1]:3030`），我拿 `127.0.0.1` 探测 ⇒ 换 `localhost` 即通（这是我的探测口径错，
      不是环境问题）
    · **后端 wedged 而非「慢」**：进程在 `0.0.0.0:9980` **LISTENING**（PID 24324），但
      `/api/health`、`/docs`、`/openapi.json` **全部**超时，且**180 秒**长等待仍超时
      ⇒ 三个端点里连最轻的 `/openapi.json` 都不响应，判定进程卡死（很可能仍卡在启动期的
      migration runner / drift 检测），不是 health 端点本身慢
    ⇒ 弹窗打开即需 dry_run（要后端），故**全路径 E2E 无法进行**；底稿页本身也加载不出数据
  - **本轮实际取得的部分验证（记录下来，避免下一轮重复劳动）**：
    · Playwright 打开 `localhost:3030` ⇒ 标题「致同审计作业平台」，重定向到 `/login`
      （后端挂 ⇒ 无会话），**console error = 0**
    · 🔴 **三份改动模块经 Vite dev server 真实 transform 全部 HTTP 200 且无 transform error**
      （`RefreshSourceDialog.vue` 37301B · `GtWpRenderer.vue` 175413B ·
      `GtD4OperatingRevenue.vue` 134124B）—— 这条与 vitest **相互独立**：vitest 用自己的
      transform，而这里走的是**真实 dev server 构建管线** ⇒ 可排除「只有 vitest 能编过」
  - **下一轮 `start-dev.bat` 后待补的全路径**：打开已注册 sync 且有已发布 substrate 的 entry
    （canary = D4，其 `syncEntryId` 已 expose）→ 点「刷新取数」→ 核摘要两侧行数与增删条数
    → 选②→ 二次确认 → 成功 → 刷新后受管行集与摘要预告一致 → console 0 error

- [x] 14. 收尾
  - [x] 14.1 探针清理
    - 本轮编排侧建的全部探针已清零（`_aos_*` / `_rsd*` / `_spec*` / `_audit*` / `_mut*` 等
      约 30 个，现扫 `backend/scripts/analyze/_aos*` = **0**）
    - 🔴 **首版此条的残留清单写错了**：当时记「`_aos44p_*`(4) / `_aos46p_*`(7) / `_aosp2_*`(4) /
      `_aos_t61_*`(3) / `_aos_adr005_verify.py`」，但现扫这些**已全部不在**（各自会话自行清掉了）。
      当前目录下的 `_kbp_*` / `_p1~_p4*` / `_push_*` / `_g.txt` 属**并发的
      `knowledge-base-retrieval-and-authz-closure` 会话**，非本 spec 产物，未动
    - 删除全部 `backend/scripts/analyze/_aos_*.py` 与其临时产物
  - [x] 14.2 判据引用闭合性自查
    - **已现算扫描（非人工目测）**：正则取 design 的 `^### (Property \d+):` 得 **12** 条，
      逐条反查 tasks.md 是否存在 `**Property N:` 引用 ⇒ **未被引用者 0 条**（12/12 闭合）。
      其中 **P10（行身份识别与键名无关）= Task 3.5**，现读确认为 `- [x]* 3.5 属性测试：行身份识别与键名无关`
    - 🔴 **首版此条是「标 `[x]` 却自述未做扫描」的自相矛盾**（用户质询后补做）：当时只写了
      「未做自动化闭合性扫描…人工核对」却仍勾 `[x]`。现已真跑扫描，结论恰好与当时的断言一致，
      但**过程性质不同** —— 前者是未验证的声明，后者是可复现的现算
    - 脚本化检查：每条 AC（Requirement X.Y）与每条 Property 至少被本文件引用一次
    - 🔴 正则须处理 `_Requirements: 1.1, 1.3_` 这类尾部下划线形态
      （`\b` 在 `1_` 处不匹配，须用 `(?![0-9])`）
    - _Requirements: 7.4_
  - [x] 14.3 更新 `.kiro/specs/INDEX.md` 的完成度与本轮教训
    - **已完成**（第 **387** 行，`read_bytes().decode('utf-8')` + `write_bytes()` 保纯 CRLF，
      写后复验 **纯 CRLF = True**、968 行不变）：
      · 进度字段 `**0/42**（Design-First 未实施）` → `**42/43**（后端全链路全绿 + 前端已实施；
        余 2 项为外部依赖）`
      · 第三格追加本轮教训：假绿复盘 · `watch` 缺 `immediate` 的真 bug · `check_file_size.py`
        门禁可静默绕过 · 两处「守卫在但不生效」（3.7 等值 vs 4.8 棘轮 / 6.3 恒真 xfail）·
        Property 7 文本不可满足 · entry_id 架构缺口与方案 D · 前端 teleport / 未 unmount 两坑
    - 🔴 **口径差如实登记不静默改**：INDEX 原记「42 个叶子子任务」，现算二级子任务叶子为 **43**
      （差 1）；全部叶子（含无子任务顶层）为 **49**。已在 INDEX 里写明两个口径与这处差异
    - **表格合法性已复验**：本行未转义 pipe 数 **恰 4**（3 列表 `| spec | 进度 | 一句话 |`），
      追加文本内**无裸 pipe**。🔴 顺带发现**预存**问题（非本轮引入、不属本 spec）：同表块
      （行 381~442）内**行 416~420 共 5 行只有 3 个 pipe**（缺一列），属其它 spec 的登记行；
      另全文 123 处「pipe != 4」绝大多数是合法的**二列表**（如行 751 的 `| Spec | 说明 |`）
      ⇒ 🔴 「每行恰 4 个 pipe」这条校验**只对三列 spec 表成立**，不能全文一刀切（我首版的表述过宽）
    - 🔴 INDEX.md 是纯 CRLF ⇒ `read_bytes().decode('utf-8')` + `write_bytes()`；
      表格第三格内禁裸 pipe；校验「每行恰 4 个未转义 pipe」
    - _Requirements: 7.4_

- [x] 15. Final checkpoint — Ensure all tests pass
  - **后端 28 文件定向回归 `771 passed / 0 failed / 0 xfailed`**（两次调用合计：25 文件 641 +
    3 文件 130；`-rfxX` 确认无 XPASS）
  - **前端 vitest `25 passed / 0 failed`**（`RefreshSourceDialog.spec.ts`），与兄弟件
    `GtRowNameAlignmentDialog.spec.ts` 合跑 **2 files passed** ⇒ 新增判据未污染既有前端回归面
  - **三份改动的 `.vue` 全部经 `@vue/compiler-sfc` 的 `parse` + `compileScript` 实测通过**
    （`RefreshSourceDialog` / `GtWpRenderer` / `GtD4OperatingRevenue`）；四份文件门禁 exit=0
  - 🔴 **首版此条是假绿**：当时前端**一行测试都没跑、SFC 也没编译过**就勾了 Final checkpoint。
    现补齐后「所有**测试**通过」成立；仍未完成的两项**都不是测试** ——
    Playwright 真实链路（13，`start-dev.bat` 环境不可用）与 INDEX.md 更新（14.3），均如实 `[ ]*`
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- 标 `*` 的子任务是测试类，可为 MVP 跳过；但本 spec 的 `*` 子任务里含**全部 12 条 property**
  与变异反证 —— 平台铁律要求 run-all 时 `*` 也必须做完，除非用户明确说跳过
- 顶层任务不带 `*`
- 阶段 0（Task 1~2）不改生产代码，只现算与判别，其结论会回填 spec
- 🔴 Task 6.3 的「merge 之后再删」顺序是 ADR-AOS-001 的核心，不可调换
- 🔴 Task 7 的整组是「不破坏 OO 路径」的唯一保障，不得因为「adopt 测试全绿」而跳过

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "2"] },
    { "id": 1, "tasks": ["3.1", "3.4"] },
    { "id": 2, "tasks": ["3.2", "3.3", "3.7"] },
    { "id": 3, "tasks": ["3.5", "3.6", "4.1"] },
    { "id": 4, "tasks": ["4.2", "4.7"] },
    { "id": 5, "tasks": ["4.3", "4.4", "4.5", "4.6", "4.8"] },
    { "id": 6, "tasks": ["6.1", "6.2"] },
    { "id": 7, "tasks": ["6.3"] },
    { "id": 8, "tasks": ["6.4", "6.5"] },
    { "id": 9, "tasks": ["6.6", "6.7", "7.1", "7.2"] },
    { "id": 10, "tasks": ["7.3", "7.4", "8.1", "8.2"] },
    { "id": 11, "tasks": ["8.3", "8.4", "8.5"] },
    { "id": 12, "tasks": ["10.1"] },
    { "id": 13, "tasks": ["10.2", "10.3", "10.4"] },
    { "id": 14, "tasks": ["11"] },
    { "id": 15, "tasks": ["12.1", "12.2", "12.3"] },
    { "id": 16, "tasks": ["13"] },
    { "id": 17, "tasks": ["14.1", "14.2", "14.3"] }
  ]
}
```
