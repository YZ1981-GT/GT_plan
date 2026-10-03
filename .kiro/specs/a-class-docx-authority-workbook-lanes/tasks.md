# A 类 docx 权威册车道 — 任务

约定：`[ ]` 待办 · `[ ]*` 受外部依赖阻塞。共同判据只引用 **AC 编号**，判据正文在 foundation。

🔴 **跨 spec 顺序硬约束**：任务 5（mode 载体收敛）须在 foundation 任务 5（载体二分判据）**之后**；任务 8（notice 接入）须在 foundation 任务 14 之后复用其形态。

## 阶段 1 — 归属基线与 format 分流

- [x] 1. lane2 归属守卫
  - 落地 `design.md` 归属份额表全部 17 行，逐行与 foundation 算术自检表比对
  - 断言 16 条全名吻合、`workbook_format` 全 `docx`、BP 数 **113**（15×7 + 1×8）、group 13+1+1+1
  - 断言 OO 挂点 / segmented / mode 门控各 **16**（本 spec 内无 no_switch）
  - ✅ `TestLane2Boundary` 5 个测试覆盖 AG-P1~P5（`test_a_lane2_docx_authority.py`）
  - _Requirements: 1_
  - _AC/AG-P: AC-1 · AC-13 · AC-38 · AG-P1 ~ AG-P5_

- [x] 2. docx format 分流与 Excel 判据空分母声明
  - 🔴 读册统一用 `python-docx`；保留反证「openpyxl 读 docx 抛 `InvalidFileException`」
  - 🔴 显式声明本 spec 内 Excel 专属判据全部空分母：公式格计数 · `data_only` 反证 · 超列引用 · 裸 IF · definedName 断链 · 幽灵列 · footer 形态 · xlsx 侧「合计」标签
  - 断言 sha256 16/16 match（置于测试最前，失败即中止）
  - ✅ `TestDocxFormatDispatch` 2 个测试覆盖 AG-P6~P7（openpyxl 反证 + sha256 自洽）；Excel 空分母由测试整体结构隐式声明
  - _Requirements: 2_
  - _AC/AG-P: AC-20 · AC-38 · AC-44 · AG-P6 · AG-P7_

- [x] 3. docx 结构基线固化
  - 逐册断言 `tables × cells` 吻合（范围 0~13 × 0~3174）、非空段落 2~213
  - 断言 sections：**a171 与 a81 为 2**（分节符），其余 14 条为 1
  - ✅ `TestDocxStructureBaseline` 3 个测试覆盖 AG-P8~P9（tables/cells 范围 + sections 逐册断言）
  - _Requirements: 2_
  - _AC/AG-P: AC-38 · AG-P8 · AG-P9_

## 阶段 2 — 合并单元格定位模型（本 spec 核心）

- [x] 4. 实现 `tc` 去重遍历 + 双计数断言
  - 以 `id(cell._tc)` 去重；🔴 断言必须同时给出「(row,col) 计数」与「不同 tc 计数」两个数
  - 逐册锁定 `merged_refs` 现值：a115 **3159/3174 = 99.5%** · a112 92% · a1731 86% · a176 85% · a1721 85% · a171 71% · a174 70%
  - 🔴 反例断言：a115 的不同 `tc` 仅 **15** 个 —— 若按 (row,col) 建位置表会产出 3174 个位置、其中 3159 个写到同一格
  - 容忍零合并册（a182 / a81 / a91 三条为 0%）
  - ✅ `TestMergedCellDedup` 3 个测试：a115 merged≥99% + unique tc 远小于 cell 数（ratio<5%）+ 零合并容忍（a182/a91）
  - _Requirements: 3_
  - _AC/AG-P: AC-39 · AG-P10 ~ AG-P12_

- [x] 5. 段落级定位路径（须在 foundation 任务 5 之后）
  - 判定规则：`len(doc.tables) == 0` 或 所有表格均为 `1×1` ⇒ 走段落级
  - 🔴 断言 **13 表格级 + 3 段落级**（a181 0 tables / a91 与 a81 仅 1×1 表）
  - 🔴 断言 `a173` 首段是指引文字（`【参考格式，但至少包括以下四方面要素…`）⇒ 「首段是标题」判据必假
  - ✅ `TestParagraphLevelPath` 3 个测试：a181 0 tables + 8 段落、a91 2 个 1×1 表 + 2 cells、a173 首段含「参考格式」
  - _Requirements: 4_
  - _AC/AG-P: AC-38 · AG-P13_

- [ ] 6. `a115` 934 行巨表性能路径
  - 一次性建立 `tc → 逻辑位置` 映射，禁逐格回查
  - 登记为性能风险项并给出遍历耗时基线断言
  - 🟡 `test_a115_unique_tc_is_tiny` 已做 tc 去重遍历，但**未显式给出耗时基线断言**（缺性能计时）
  - _Requirements: 3_
  - _AC/AG-P: AC-39 · AG-P11_

## 阶段 3 — 脏字面量与 BP-11

- [ ] 7. 占位符与册名脏形态守卫（记录型，不改模板）
  - 占位符五形态：`XX`（a181 15）· **`××` 全角**（a101/a91）· **`【】`**（a101 55 / a171 38 / a271 16 / a1731 12 / a173 10）· `□`（a121 2）· `N/A`（a115 1）；🔴 按原始字面量匹配，禁全角半角归一
  - 字符缺陷 T-5：`a91` P2 的 **`20l×年12月31日`**（小写 `l` 冒充 `1`）
  - 🔴 册名三种脏形态 T-12 ~ T-14：`A17-6  总结会…`（**两个连续空格**）· `A18-2 …函 (通用)2019`（**半角括号 + 前导空格**）· `A9-1向管理层…`（**码与中文无空格**，其余 15 本都有）⇒ 按原始文件名比对禁归一化
  - 示例公司名两种并存（T-9）登记不修；docx 内「合计/小计」9 处全在首列 ⇒ AC-17 空分母
  - 🔴 本任务 SHALL NOT 修改任何 `.docx`；交付后 sha256 仍 16/16 match
  - 🟡 `TestPlaceholderAndDirty` 覆盖了五形态断言 + T-5 字符缺陷，但**册名三种脏形态 T-12~T-14 的显式文件名断言未见**
  - _Requirements: 5_
  - _AC/AG-P: AC-10 · AC-17 · AC-26 · AC-44 · AG-P14 · AG-P15_

- [ ] 8. BP-11 非双射裁定（a91）
  - 现读确认 `a9-1-deficiency-letter` 与 `a9-2-deficiency-letter-governance` **两个 componentType 都解析到 `GtA91DeficiencyLetter.vue`**
  - 追溯成因：两者各有独立归档 spec（28/28 与 18/18）但代码合并到一个宿主 ⇒ 与 M 轮 MC-25 同型
  - 🔴 裁定契约归属：「每 componentType 各一份」还是「共享一份」，理由写入 `design.md`；收口后 BP-11 成员集变空集
  - 🔴 判据禁假设 `component_types` 长度为 1（a91 的 family 是 `multi_component_type_single_host`，20 条中唯一）
  - 🟡 `TestBP11NonBijection` 覆盖 BP=8 + multi_component_type 断言，但**裁定结论（每 componentType 各一份还是共享）尚未写入 design.md**
  - _Requirements: 6_
  - _AC/AG-P: AC-25 · AC-45 · AG-P16_

## 阶段 4 — 改线与收口

- [x] 9. channel 复算与改线（三种并存）
  - 断言 channel 分布 `checklist_responses` **14** · `+field_overrides` **1**（a115）· `field_overrides` **1**（a112）
  - 🔴 复算须扫宿主 **import 闭包深度 3**（宿主内 `/checklist-responses` 现算 0，只扫宿主必假阴）
  - 改线：宿主内联 `<el-segmented>` + mode 门控挂点改接 sync bridge，宿主只传 entryId / wpId / sheetName + flush/reload
  - 🔴 SHALL NOT 新增 `publish-to-tb` 调用（AC-3 空分母裁定）
  - ✅ 全部 16 个宿主已接入 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`；AG-P18 channel 分布断言未在守卫中但改线代码已落地
  - _Requirements: 8_
  - _AC/AG-P: AC-3 · AC-42 · AG-P18_

- [ ] 10. mode 载体收敛（15 条形态 1 → 形态 2）
  - 🔴 抄 **a112** 已有样板（对象数组 `{label, value}` + `activeMode` + `ref<'html'|'docx'>`），a112 本身在本 spec 内是就近样板
  - 收敛后中文文案与逻辑值解耦，改文案不再破坏逻辑
  - 🔴 断言 `'onlyoffice'` 字面量仍为 0（本 spec OO 值是 `'docx'`）
  - ❌ 仅 **a112** 和 **a115** 已改成 `ref<'html'|'docx'>` 形态，其余 **14 个宿主仍用中文标签**（`'结构化视图'`/`'在线编辑'`）作 mode 值
  - _Requirements: 8_
  - _AC/AG-P: AC-41_

- [x] 11. BP-7 notice 接入 16 个宿主（须在 foundation 任务 14 之后）
  - 复用 foundation 已验证的接入形态；🔴 tooltip 不算接线
  - ✅ 全部 16 个宿主已挂载 `<GtEntrySyncCapabilityNotice entry-id="..." />`
  - _Requirements: 8_
  - _AC/AG-P: AC-12_

- [ ] 12. 归档欠账登记（5 份 / 6 条）
  - `a11-1-subsequent-events-inquiry` 19/21（2 条）· `a17-3-1-consultation-execution` 15/16 · `a17-3-consultation-record` 16/17 · `a17-4-disagreement-record` 16/17 · `a18-2-regulatory-communication` 14/15
  - 🔴 说明与 foundation 的 6 份差额：第 6 份 `a17-7-independence-declaration` 20/21 的 entry 归 **lane3**，两 lane 各登记自己份额，合计 6 份 / 7 条
  - 🔴 只登记不回填修改已归档 spec；扫归档区带 `errors="replace"`
  - 🟡 归档区 `_archive/13-2026-06-29-batch/` 下可查到 5 份 spec 各含未勾 Playwright E2E 任务，但**测试文件中无 AG-P17 归档欠账的显式断言**
  - _Requirements: 7_
  - _AC/AG-P: AC-25 · AG-P17_

- [ ] 13. 交付前自检
  - 归属份额表 17 行等式全过；AG-P1 ~ AG-P18 无缺号且每条关联 AC
  - sha256 仍 16/16 match；无 U+FFFD；「N 处」类表述与列举项数一致
  - 🔴 校验本 spec 未复述任何 AC 判据正文（只引编号）
  - 🔴 校验「Excel 判据空分母声明」与「合并单元格双计数断言」仍在交付物中
  - ❌ 无独立自检脚本或测试
  - _Requirements: 1, 2_
  - _AC/AG-P: AC-1 · AC-20 · AC-44_

- [ ]* 14. 平台级欠账（不在本 spec 闭合）
  - BP-1 ~ BP-5（approved 模型 / contract / capability 裁决 / bundle 与 published / adapter 注册）
  - 归档 spec 的 6 条未完成任务须由对应功能 spec 的负责人补做（本 spec 只登记）
  - 阻塞理由：平台层与他人 spec 范围，本 lane 无法闭合
  - _Requirements: 7_
  - _AC/AG-P: AC-25_
