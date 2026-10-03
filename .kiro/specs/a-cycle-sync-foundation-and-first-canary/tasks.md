# A 循环双向回写地基与首张 canary — 任务

约定：`[ ]` 待办 · `[ ]*` 受外部依赖阻塞（不计入完成率，理由须写明）。任务引用 `_Requirements:` 与 `_AC/AF-P:` 双轴。

## 🔴 2026-09-30 外部通告（由 G 域双向回写 lane 写入，未改本 spec 任何复选框/代码）

**一句话**：manifest 已重生成，**A 域 entry 由 24 条降到 7 条**，`xlsx/gt-a51-cashflow-audit`
与 `xlsx/gt-a3-consolidation-console` 等 17 条**已不在 manifest 内**；你们的
`backend/tests/workpaper_sync/test_a_entry_connection_blockers.py` 因此新增 **2 条红**。

### 发生了什么

G 域 13 个主入口的双向回写只差 manifest 重生成，而重生成被两道门卡住：
①`approved_source_digest`（挂点 diff 待复核）②`stale overlay overrides:
[GtA51CashflowAudit.vue]`。第二道门的成因是**本 spec 工作内部的一处矛盾**：

- 你们把 A51 等 **17 个 A 类宿主**改成只挂 `WorkpaperSyncEditorHost`、删掉了
  `<GtOnlyOfficeSheet`（现算这 17 个文件 **17/17 未提交**）；
- 同时在 overlay 的 `overrides` 里加了一条 `component: "GtOnlyOfficeSheet"` 的 a51
  `bidirectional` 裁决（现算该条**不在 HEAD**，是在途产物）。

第一道门一直先跳闸，所以这个矛盾此前没暴露。

🔴 **根因不是这条 override 写错，而是发现契约缺口**：entry 只能由
`_group_source_facts(discovery)` 从发现到的挂点派生，而 discoverer 的组件白名单只有
`GtOnlyOfficeSheet` / `OnlyOfficeWordDialog` / `WorkpaperWordEditor`，**不认
`WorkpaperSyncEditorHost`** ⇒ 宿主一旦迁移彻底、删掉 legacy 标签，它的 entry
**直接不存在**，overlay 里写什么都无法挽回。现算全平台 **51 个「仅 EditorHost」宿主**
（34 个 `d4/**` tab + 这 17 个 A 类）落在缺口里，**且 d4 那批早已真实退出过 manifest 一次**。

### 我们做了什么 / 没做什么

- **做了**：经用户明确授权，把 a51 裁决**原文逐字**移入 overlay 新键 `deferred_overrides`
  （附 `deferred_reason` / `restore_action`），**不是删除**；恢复是机械动作（移回 `overrides`）。
  守卫 `test_g_cycle_bidirectional_overlay_adjudication.py::TestDeferredOverrideStaysRestorable`
  5 条判据锁住「原文在 / 与 overrides 互斥 / 推迟理由仍成立 / 后果如实 / 批准留痕」，
  **理由一旦不成立（glob 重新匹配上挂点）就会打红并指示移回**。
- **没做**：没有修改你们的任何测试、源码、spec 复选框。那 2 条新红留给你们按自己的设计意图处置。

### 你们这 3 条红的逐条归因（内存 A/B，把 HEAD manifest 喂进同一入口复算）

| 判据 | HEAD manifest | 重生成后 | 归因 |
|---|---|---|---|
| `test_only_canary_is_bidirectional` | **FAIL**（`bidi=[]`，a51 当时是 `single_onlyoffice`） | FAIL | **预存**，与本轮无关 |
| `test_a3_console_capability_stays_single_onlyoffice` | PASS | **FAIL**（entry 已不存在） | **本轮引入** |
| `test_canary_registration_plan_is_unblocked` | PASS（`blocked_reason=None`） | **FAIL**（plan 里无 canary，`StopIteration`） | **本轮引入** |

🔴 **值得注意**：前者此前之所以 PASS，是因为磁盘 manifest **stale**（冻结在你们改宿主之前的
源码态）。也就是说这两条判据此前是**靠过期产物通过的**；重生成只是让已存在的不一致变得可见。
这两个测试文件现算均为 `git ??`（未入库）⇒ **不影响 CI**。

### 建议的解除路径（需你们裁决，我们不越界）

1. 另立 spec 裁决 `WorkpaperSyncEditorHost` 的发现 / entry 归并方案 ——
   直接并入会让 **45 个双挂宿主**撞 `stable entry_id collision`
   （`_entry_id` 只按 document_type + source_file 取键），属设计级变更。
2. 缺口修好后把 `deferred_overrides[a51]` 移回 `overrides`、重跑生成器，上述守卫会自动提醒。
3. 在此之前，若要让这 2 条判据如实反映现状，可考虑改为「断言 entry 缺席 + 指向缺口」
   并配反向锁 —— 但**这是你们的设计判断，我们不代劳**。

完整执行表、方法论沉淀与其余归因见
`.kiro/specs/g5-nested-sections-and-template-defects/tasks.md` 的 2026-09-30 最终结果节。

## 阶段 1 — 扫描器地基与域切分

- [x] 1. 建 A 域扫描器模块 `backend/scripts/analyze/a_cycle_scanner.py`
  - 实现域切分：按 `wp_code_patterns[0]` 首字母，断言 46 = A 20 / B 10 / C 1 / S 10 / 无码 5；🔴 禁按 entry_id 猜域（`xlsx/gt-c-control-test` 反例）
  - 实现 strict 域四路取并（目录段 / `^(?:use|Gt)?A\d` / **`^a\d` 小写** / `^a\d+-`），断言 148（生产 79）；变异证明：去掉小写分支应漏 34
  - 统一行数口径 `len(text.split("\n"))`，注释剥离保留行号
  - 🔴 扫归档区带 `errors="replace"`（`report-view-slimdown/tasks.md` 非 UTF-8）
  - 落地口径差对照表全部 9 行（含 3 处「我自己的口径错误」：footer 解析失败 / `modeOptions` 结构误读 / 门控两次迭代）
  - _Requirements: 1, 16_
  - _AC/AF-P: AC-1 · AC-5 · AC-11 · AC-29 · AF-P2 · AF-P3 · AF-P5_

- [x] 2. slice 自相矛盾与 pilot 排除守卫
  - 登记 4 处矛盾：B 11→10 · C 2→1 · 共享 4→5 · 通道 5→4；另 `*DualMode*.ts` 正文 115 vs 字段 114
  - 断言 `excluded_pilot_entry_count` = **1**（首次非 0）· `in_scope_parent_duplicate_count` = **0**（🔴 与 N 反转，条件节不触发）
  - 引用 `excluded_from_slice` 两条否决原文（「不为它硬指一本册」/「不得为凑字段编一个码」）
  - _Requirements: 1_
  - _AC/AF-P: AC-1 · AC-31 · AC-47 · AF-P4 · AF-P6 · AF-P7_

- [x] 3. entry_groups 二维分组复算
  - 第一维按 `htmlRendererRegistry.ts` **模块边**匹配（🔴 须同时认提升的 `const` 与内联 `defineAsyncComponent`，只认一种漏 94/211）；断言 `componentType:` 行数 **211**
  - 第二维扫宿主 **import 闭包深度 3** 的 HTTP 站点，断言通道 4 种、A 域涉 3 种
  - 断言 13 组 / 9 家族 / 4 通道；A 域 GRP-01 15 / GRP-02 1 / GRP-03 3 / GRP-10 1 = 20
  - _Requirements: 12_
  - _AC/AF-P: AC-43 · AF-P11 · AF-P33_

## 阶段 2 — 门控与载体判据

- [x] 4. 门控判据最终版（递归回溯）+ 两中间版本变异证明
  - 实现 `effective_conds`：自身 `v-*`/`:` 绑定 + `v-else`/`v-else-if` 的兄弟链头回溯；对挂点**及全部祖先**逐节点求并
  - mode token 正则 `\b\w*[Mm]ode\b`（覆盖 mode/renderMode/activeMode/dualMode/editorMode）
  - 断言 OO 挂点 **20** · segmented **19** · mode 门控 **19** · 无门控恰 1（a3-console）
  - 🔴 变异证明：版本 1（只看自身属性）应得 **14**；版本 2（自身 + 自身链头）祖先命中应得 **3** ⇒ 两者都不可照抄
  - 登记三形态：v-else 兄弟链 14 · 祖先元素 3 · 三层嵌套 2（a171/a177）
  - _Requirements: 4_
  - _AC/AF-P: AC-13 · AF-P13 ~ AF-P16_

- [x] 5. mode 载体二分判据
  - 形态 1（17 条）：字符串数组 + **中文标签作 mode 值**，`mode === '结构化视图'` 18 处 ⇒ 登记为「改文案即破坏逻辑」，与 BP-14 同型
  - 形态 2（2 条 a112/a38）：对象数组 `{label, value}` + `activeMode` + `ref<'html'|'docx'>` ⇒ 正面样板
  - 🔴 扫 `modeOptions` 须区分字符串数组与对象数组（本轮踩过「4 值混排」误读）
  - 断言 `'onlyoffice'` 字面量 **0**、`mode === 'structured'` **1** 处混用、localStorage 无 mode 键
  - _Requirements: 5_
  - _AC/AF-P: AC-16 · AC-41 · AF-P17 ~ AF-P19_

## 阶段 3 — 写路径、模板与真库

- [x] 6. 写路径与通道守卫（含空分母声明）
  - 🔴 断言 `publish-to-tb` 在 A 域 = **0** 并声明**空分母**（前十一轮首次），禁写「已验证发布门唯一」
  - 断言 `trial-balance/writeback` = 0（反向断言仍有效）· `field-overrides` 4/2 文件 · 确认门 7/3 文件独立存在
  - 🔴 断言宿主内 `/checklist-responses` = **0** ⇒ 判据须走 import 闭包（AC-42）
  - _Requirements: 3_
  - _AC/AF-P: AC-3 · AC-4 · AC-42 · AF-P8 ~ AF-P12_

- [x] 7. 权威册 format 分流 + sha256 前置门
  - sha256 + size 18/18 match 置于测试最前，失败即中止；断言 A 目录 97 本 = xlsx 65 + docx 32
  - 分流：docx 16 走 `python-docx` · xlsx 2 走 `openpyxl` · 无册 2 声明空分母
  - 🔴 保留反证：openpyxl 读 docx 抛 `InvalidFileException`
  - 断言 xlsx 公式格 **120**（63+57）· 带 fx sheet 7 · `data_only=True` 反证 **0**
  - 双射降级为单射：只 18 本归属，79 本写 `excluded_reason`
  - _Requirements: 7_
  - _AC/AF-P: AC-38 · AC-44 · AF-P26 ~ AF-P29 · AF-P31_

- [x] 8. footer 读 raw XML（禁用 openpyxl）
  - 🔴 用 `zipfile` 读 `xl/worksheets/sheet*.xml` 的 `<oddFooter>`；断言三态 **2 有内容 + 7 有容器无 oddFooter + 4 无容器 = 13**
  - 锁定内容值：`第 &P 页，共 &N 页`（中文）· `Page &P`（英文无 `&N`）
  - 🔴 在注释中记录「第一版用 `ws.oddFooter` 读出全空是解析失败，不是事实」
  - _Requirements: 7, 8_
  - _AC/AF-P: AC-36 · AF-P30_

- [x] 9. 契约字段与真库守卫（asyncpg）
  - 断言 A 域 28 行 · `conclusion` 非空 **24** > `remark` **4** ⇒ NC-34 连续第二轮成立，映射须覆盖 `conclusion`
  - 分布断言 A21 19 / A1 5 / A17 3 / A15 1；全域 1,034,702 行 / conclusion 非空 130
  - 🔴 `*-review-session-*` 白名单排除（第三轮出现，261 B）⇒ 沉淀为跨循环通用规则
  - 断言跨 entry 污染 **0**（28/28 对齐），变异证明取 L 域 1 条 / N 域 4 条 G8 污染
  - 生产契约 4 份无一属 A 域（BP-2）；`_example.candidate.json` 的 `review.entry_id` 为 null 是反例分母
  - 无库环境 skip 并标原因，禁静默 pass
  - _Requirements: 10_
  - _AC/AF-P: AC-19 · AC-34 · AF-P23 ~ AF-P25_

- [x] 10. 结构性零 23 项 + 变异证明
  - 逐项实现「零断言 + 变异证明」成对结构
  - 🔴 特别登记三处「我自己的口径错误」作为案例：footer 解析失败 / `modeOptions` 结构误读 / 门控两次口径迭代
  - `per-entry dual-mode composable = 0` 的变异证明 = 同一正则全域跑出 **114** 个模块
  - 🔴 **逐条落地 11 条 ❌ 不适用项的空分母声明**（历轮最多，须写出现算证据而非静默省略）：AC-7（`removeRow` 0）· AC-16（无 mode 分区键）· AC-17（合计标签全在首列 + xlsx 仅 2 本）· AC-22（A 类非科目底稿，无借贷方向）· AC-23（无 `SHEET_MAP` 形态）· AC-24（册名含「原底稿/历史」0）· AC-27（同 AC-24）· AC-30（abcs slice 无 `transport_key_resolution` 节）· AC-31（in-scope parent_duplicate 0，**与 N 反转**）· AC-32（超列引用 0，A 码带连字符不成合法 A1 引用）· AC-35（xlsx 最宽 33 列，无 256 列形态）
  - _Requirements: 8_
  - _AC/AF-P: AC-7 · AC-16 · AC-17 · AC-20 · AC-22 · AC-23 · AC-24 · AC-27 · AC-30 · AC-31 · AC-32 · AC-35 · AF-P32_

## 阶段 4 — canary a51 闭环

- [x] 11. canary 选型与三轮轨迹登记
  - 断言 a51 五项替代判据全中且全域唯一：零区分项（BP 仅 6 项）· xlsx 册 · 主组 GRP-01 · redeemable · `literal_sheet_name`
  - 🔴 写明三轮轨迹：**M 偏离（M 域零载荷）→ N 收回（N4-1-rows 1665 B）→ A 再偏离（唯一命中是 E2E seed）**
  - 断言 A 域真库 28 行与 20 条 entry 交集仅 **1**（`A17-1-ch01`）且含 `（E2E seed）` 标记
  - 登记排除理由：a3-console（无 segmented + 无门控，「双」不存在）· a177（运行时册名）· a38（无册 + BP-14）
  - _Requirements: 6_
  - _AC/AF-P: AC-18 · AF-P20 ~ AF-P22_

- [x] 12. canary 读路径：A5-1 册 9 sheets 结构固化
  - 现读 9 个 sheet 名（`表头（请先填写）` / `A5-1现金流量审计程序` / `A5-1-1列示于现金流量表的现金及现金等价物` / `A5-1-3相关报表勾稽关系核对` / `A5-1-4现金流量核查` / `A5-1-5现金流量核查` / `A5-1-6其他现金流量` / `会计提示` / `GT_Custom`），🔴 按原始字面量锁定禁归一化
  - 断言 hidden 恰 1（`GT_Custom`）· 公式格 57 · 「合计」标签 4 处全在 A 列
  - 登记 `definedName` 22 / broken 14（形态与 N 域同源）为记录型断言
  - 行身份族现算：A 族持久化键 **0** · M 式 `row-${n}` **0** · B 数组位置寻址 **8**/5 文件 · **C 展示序号 64**/5 文件 · D 熵键 **2** · **E 稳定身份 21**/8 文件；🔴 `removeRow` **0**（删行函数用别名如 `addTeamMember`/`addThreatRow` 的对应形态，正则须扩展）⇒ 改造方向 = 把 C 族 `$index` 收敛到 E 族稳定身份
  - `derived_total` 双正则：A 域宿主 TAIL **4** : MID **2** / 3 文件（全域 764 : 268 / 431 文件）· `prefill` **11** 命中 / **2** 文件（分母非空，同 N 轮结论）
  - _Requirements: 7, 16_
  - _AC/AF-P: AC-6 · AC-8 · AC-9 · AC-10 · AC-14 · AC-17 · AC-37 · AF-P31_

- [ ] 13. canary 写路径：改线到 sync bridge
  - 宿主内联的 `<el-segmented>` + mode 门控 `GtOnlyOfficeSheet` 挂点改接 sync bridge，宿主只传 entryId / wpId / sheetName + flush/reload 回调
  - 🔴 SHALL NOT 新增 `publish-to-tb` 调用（A 类底稿无审定数语义）
  - 🔴 mode 载体从形态 1（中文标签作值）收敛到形态 2（label/value 分离），抄 a112/a38 已有样板
  - 持久化走 `checklist_responses` 通道（经 import 闭包，非宿主内直调）
  - _Requirements: 3, 5_
  - _AC/AF-P: AC-3 · AC-41 · AC-42_

- [ ] 14. BP-7 接入 `GtEntrySyncCapabilityNotice`
  - A 域现算 0 挂载（全域 41 条非本 slice 宿主在用）⇒ 须新增；🔴 tooltip 不算接线
  - _Requirements: 13_
  - _AC/AF-P: AC-12_

- [ ] 15.* canary 端到端闭环（阻塞：真库无业务载荷）
  - 🔴 阻塞理由：`A5-1` 前缀在真库 28 行里**不存在**（0 行）⇒ 闭环验证须自建夹具，无法用既有数据
  - 自建夹具后须能证明 HTML 侧 ↔ docx/xlsx 侧双向一致
  - _Requirements: 6_
  - _AC/AF-P: AC-18 · AF-P22_

## 阶段 5 — 收口与平台级欠账

- [x] 16. 模板层缺陷台账 T-1 ~ T-11 记录型守卫
  - 逐项锁定现状：T-1 AE 列除零（10:1）· T-2 `F6-10` 跨循环码 · T-3 A3-3 definedName 261/190（含 `.dbf` 与中文名）· T-4 A5-1 22/14 · T-5 `20l×年` · T-6 934 行巨表 99.5% 合并 · T-7 纯信函 0 表格 · T-8 指引文字占标题位 · T-9 示例公司名两种 · T-10 A3-8 无册 · T-11 写死 5 列 + 裸下标 key
  - 🔴 本任务 SHALL NOT 修改任何模板文件；交付后 sha256 仍须 18/18 match
  - _Requirements: 7_
  - _AC/AF-P: AC-9 · AC-21 · AC-26 · AC-40 · AC-46 · AC-48_

- [x] 17. 归档 spec 边界与欠账登记
  - 宽关键词扫出 35 份；断言 **6 份未 100%**（7 条欠账：a11-1 19/21 · a17-3-1 15/16 · a17-3 16/17 · a17-4 16/17 · a17-7 20/21 · a18-2 14/15）⇒ 🔴 与 N 轮（16 份全绿）反转
  - 断言 **4 份 0/0**（有 tasks.md 零编号任务）⇒ 「159/159」表述须附此说明
  - 追溯 BP-11 成因：a9-1 与 a9-2 各有独立归档 spec 但共用宿主 `GtA91DeficiencyLetter.vue` ⇒ 与 M 轮 MC-25 同型
  - 登记 a177 变体轴丢失（归档 spec 名 `a17-7`，pattern 只 `A177I`，实际 `A17-7`/`A17-7A` 双变体）
  - 🔴 不回填修改任何已归档 spec
  - _Requirements: 11_
  - _AC/AF-P: AC-25 · AF-P34_

- [x] 18. 路由接入状态登记（三轮三态）
  - 断言 `resolveProcedureSheetKey.ts` **91 行且无 A 分支**
  - 🔴 三轮三态一并登记：**M 缺 4 条（M1/M3/M7/M8）· N 完备 5/5 · A 整段缺失**
  - 判定是否需为 A 域新增分支（A 类底稿是否走程序表路由 —— 须业务确认，暂标登记）
  - _Requirements: 16_
  - _AC/AF-P: AC-28 · AF-P35_

- [x] 19. Property 22 判据落地（首次非空分母）
  - 按 slice `recompute_recipe` 复算：站点 **7** · label-as-key **3** · verdict **PARTIAL**
  - A 域份额 **1** 条（a38 `#L154`：`v-for="(_, i) in 5"` 写死列数 + `key="i"` 裸下标，两类缺陷同时命中）
  - 🔴 结论写 **PARTIAL**，禁写「通过」；并指出它与 AC-41 形态 1（中文标签作 mode 值）**根因同源**（label 作 identity）
  - _Requirements: 15_
  - _AC/AF-P: AC-48 · AF-P36_

- [x] 20. 删除清册一致性守卫
  - 🔴 断言口径：「现算 orphan dual-mode 模块数 == 0」**且**「`delete_after_rewire` 非空」，禁断言「删除清单非空」
  - 断言 `delete_files` **0** · `delete_after_rewire` **1**（`useWpDualMode.ts`，3 条边全在 B 域）· `latent_orphan_after_rewire` **1**（`createDualMode.ts`，barrel-only，🔴 不擅自删，barrel 入边按路径解析禁 stem 相等）
  - 断言 `must_rewire` **46**（A 域 20）· `must_not_delete` **5** · 共享基类边 **26+1**（本 slice 5 条全在 B 域，A 域贡献 **0** ⇒ 空分母）
  - 载体分布：host_inline **32** / shared_carrier **10** / no_carrier **4** / orphan **0** / per-entry composable **0**
  - _Requirements: 14_
  - _AC/AF-P: AC-2 · AF-P15 · AF-P16_

- [ ] 21.* 平台级欠账（不在本 spec 闭合）
  - BP-1 approved 权威模型未发布 · BP-2 逐 entry contract 未发布 · BP-3 capability 是 overlay 默认值非逐 entry 裁决 · BP-4 definition bundle 与 published representation 未交付 · BP-5 adapter 未注册（`adapter_id` 现算 46/46 为 null）
  - 🔴 N 轮发现的 `validate_slice_against_schema` 拒收诚实声明缺陷**仍未修**（A 轮走追加节绕开，`residual_inconsistency` 为 null）⇒ 平台层欠账继续登记
  - 归档区非 UTF-8 文件（`report-view-slimdown/tasks.md`）编码修复
  - 阻塞理由：均需平台层方案，单循环 spec 无法闭合
  - _Requirements: 11, 13_
  - _AC/AF-P: AC-33 · AF-P1_

- [x] 22. 交付前自检
  - 跑算术自检表全部 16 行等式；校验 AC-1~48 与 AF-P1~36 无缺号、每条至少被某份 tasks 引用一次
  - 校验判定分布 **8 + 13 + 5 + 11 + 11 = 48**（🔴 逐条数表格，禁凭印象）
  - 校验 sha256 仍 18/18 match、无 U+FFFD、「N 处」类表述与列举项数一致
  - 🔴 校验「canary 判据三轮轨迹」与「❌ 11 条空分母声明」仍在交付物中
  - _Requirements: 1, 2, 6, 7_
  - _AC/AF-P: AC-2 · AC-18 · AC-20 · AC-44_

---

## 外部交棒（2026-10-01，来自 spec `sync-editor-host-discovery-contract-closure` Task 16）

本 lane 有 **2 条**判据因上游改动打红，经定向 A/B 确认是**本轮引入**：

- `test_task57_abcs_and_shared_migration.py::TestAdjudicationLegality::test_manifest_mirror_divergence_is_registered_not_silently_equal`（`assert 'single_onlyoffice' == 'bidirectional'` —— a51 本轮按上游 Task 14 归位成 bidirectional，abcs slice 冻结的是旧值）
- `test_task57_abcs_and_shared_migration.py::TestSliceScopeIsRecomputable::test_parent_duplicate_section_is_absent_because_in_scope_count_is_zero`（`assert 12 == 46`）

🔴 **第二条值得按它自己的命名修**：判据名说的前提是「**域内** parent_duplicate 为 0」，而本轮新增的 34 个 parent_duplicate **全在 `d4/`**、不在 A/B/C/S 域内 ⇒ **该前提仍然成立**，红的是它顺手拿来比对的**全局** `parent_duplicate_count`（HEAD 12 → 现 46）。建议改成域内计数，与命名一致。

详见 `.kiro/specs/sync-editor-host-discovery-contract-closure/handoff-regression-attribution.md`。
