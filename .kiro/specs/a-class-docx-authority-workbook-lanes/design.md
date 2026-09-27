# A 类 docx 权威册车道 — 设计

## 概述

本 spec 是 A 循环三份 sync spec 的 **lane2**，承担 **16 条权威册为 `.docx` 的 entry**。共同判据 **AC-1 ~ AC-48** 已在 `a-cycle-sync-foundation-and-first-canary`（foundation）裁定，本文**只引用编号**。

**主题**：docx 权威册（BP-9）+ 合并单元格定位去重 + 单宿主多 componentType（BP-11）。

**切分依据**：现算 **`BP-9 集合 == docx 集合` 为 `True`**（16 == 16）⇒ 本 spec 恰是 BP-9 的完整成员集，**BP-11 亦完整内聚**，横跨 **0**。

## 本 spec 归属份额（须与 foundation 算术自检表逐行对齐）

| 量 | 本 spec | 全 A 域 | 占比 |
|---|---|---|---|
| entry 条数 | **16** | 20 | 80% |
| docx 册 | **16** | 16 | **100%** |
| xlsx 册 | **0** | 2 | 0% |
| 无册 | **0** | 2 | 0% |
| GRP-01 | 13 | 15 | 87% |
| GRP-02 | **1**（a115） | 1 | 100% |
| GRP-03 | 1（a112） | 3 | 33% |
| GRP-10 | **1**（a91） | 1 | 100% |
| OO 挂点 | 16 | 20 | 80% |
| segmented | 16 | 19 | 84% |
| mode 门控 | 16 | 19 | 84% |
| BP 数合计 | **113**（15×7 + 1×8） | 140 | 81% |
| mode 形态 1（中文标签作值） | **15** | 17 | 88% |
| mode 形态 2（label/value 分离） | **1**（a112） | 2 | 50% |
| 归档欠账份数 | **5**（6 条任务） | 6（7 条） | 83% |
| 真库行数 | 1（a171，E2E seed） | 1 | 100% |
| Property 22 站点 | **0** | 1 | 0% |

🔴 本 spec 在 **docx 册（100%）** 与 **BP 数（81%）** 上是绝对主体，但在 **Property 22（0%）** 与 **xlsx 相关判据（0%）** 上完全空分母。

## BP 收口路线

| BP | 成员 | 本 spec 动作 | 收口后 |
|---|---|---|---|
| **BP-9** | 16 条（== 本 spec） | docx 侧定位模型 + format 分流判据落地 | **空集** |
| **BP-11** | {a91} | 裁定「每 componentType 各一份契约」还是「共享一份」 | **空集** |
| BP-1 ~ BP-5 | 全 46 条 | 平台级，标 `[ ]*` | 不变 |
| BP-7 | 全 46 条 | 依 foundation 裁定为 16 个宿主新增 notice 挂载 | 见 foundation |
| BP-6 / BP-8 / BP-10 | — | 🔴 **本 spec 空分母**（成员全在 lane3） | 不涉及 |

BP 计数校验：15 条 = 公共 6 + BP-9 = **7** 项 · a91 = 公共 6 + BP-9 + BP-11 = **8** 项 ⇒ 15×7 + 8 = **113** ✓

## docx 侧定位模型（本 spec 核心产出）

```
读取：docx.Document(path)          # 🔴 禁 openpyxl（抛 InvalidFileException，依 AC-38）

表格级定位（13 条 entry）：
    for t_idx, table in enumerate(doc.tables):
        seen = {}
        for r_idx, row in enumerate(table.rows):
            for c_idx, cell in enumerate(row.cells):
                key = id(cell._tc)                      # 🔴 合并单元格去重，依 AC-39
                if key in seen:
                    continue                            # 同一 <w:tc> 只登记一次
                seen[key] = (t_idx, r_idx, c_idx)       # 首次出现的 grid 坐标作锚
        # 逻辑位置数 = len(seen)，远小于 rows × cols

段落级定位（3 条：a181 / a91 / a81）：
    for p_idx, para in enumerate(doc.paragraphs):
        if para.text.strip():
            yield ('para', p_idx)                       # 🔴 无表格或表格退化为 1x1
```

**反例对照**：`a115` 的 `rows × cols` = **3174**，但不同 `tc` 只 **15** 个（3159 个是重复引用）⇒ 若按 (row, col) 建位置表，会产出 3174 个「可写位置」，其中 3159 个会写到同一个单元格上。

**两种路径的判定**：`len(doc.tables) == 0` 或 所有表格均为 `1×1` ⇒ 走段落级；否则走表格级。本 spec 现算 **13 表格级 + 3 段落级**。

## 模板层缺陷台账（本 spec 份额，只登记不修改）

| # | 位置 | 形态 | 性质 |
|---|---|---|---|
| T-5 | `A9-1向管理层通报内部控制缺陷-沟通函.docx` P2 | **`20l×年12月31日`** | 🔴 小写字母 `l` 冒充数字 `1` |
| T-6 | `A1-15 企业会计准则有关财务报表列报及披露核对表20141021.docx` | 表格 `934x3`，cells 3174，merged **99.5%** | 定位与性能双风险 |
| T-7 | `A18-1 向监管部门报送审计小结的函.docx` | **0 tables / 8 段落** | 纯信函型，「有表格」判据必假 |
| T-8 | `A17-3 业务咨询记录-XX公司-XXX事项.docx` 首段 | `【参考格式，但至少包括以下四方面要素…` | 指引文字占标题位 |
| T-9 | 16 本 docx | 示例公司名 `XX股份有限公司` vs `ABC公司` 两种并存 | 文案不统一 |
| T-12 | `A17-6  总结会会议记要.docx` | 🔴 文件名含**两个连续空格**（`表A17-6` 与 `总结会` 之间） | 册名脏字面量 |
| T-13 | `A18-2 与监管层沟通函 (通用)2019.docx` | 🔴 **半角括号 + 前导空格** `函 (通用)` | 册名脏字面量 |
| T-14 | `A9-1向管理层通报内部控制缺陷-沟通函.docx` | 🔴 **码与中文之间无空格**（其余 15 本都有） | 册名脏字面量 |

🔴 **T-12 ~ T-14 是册名层的三种脏形态**（与 N 轮 sheet 名脏形态同型但发生在文件名上）⇒ 判据 SHALL 按**原始文件名字面量**比对，禁归一化空格与括号（依 AC-10 · AC-26）。

## Property 清单（AG-P1 ~ AG-P18）

| # | 断言 | 现算值 | 关联 AC |
|---|---|---|---|
| AG-P1 | 16 条 entry 全名吻合且 `workbook_format` 全 `docx` | 16 | AC-38 |
| AG-P2 | 归属份额 17 行与 foundation 算术表对齐 | 见份额表 | AC-1 |
| AG-P3 | BP-9 16/16 全覆盖 · BP-11 1 条 · BP 数 113 | 113 | AC-38 · AC-45 |
| AG-P4 | group 归属 13 + 1 + 1 + 1 = 16 | 16 | AC-43 |
| AG-P5 | OO 挂点 / segmented / mode 门控 各 16（无 no_switch） | 16 | AC-13 |
| AG-P6 | 读册用 python-docx；openpyxl 抛 InvalidFileException（反证） | 16 | AC-38 |
| AG-P7 | 🔴 判据内无 Excel 专属项（公式格/definedName/footer/超列/裸 IF） | 空分母 | AC-20 · AC-38 |
| AG-P8 | 逐册 `tables × cells` 吻合，范围 0~13 × 0~3174 | 见范围 | AC-38 |
| AG-P9 | sections：a171 与 a81 为 2，其余 14 条为 1 | 2 / 1 | AC-38 |
| AG-P10 | `merged_refs` 逐册吻合，最高 a115 99.5%（3159/3174） | 99.5% | AC-39 |
| AG-P11 | 遍历以 `id(cell._tc)` 去重；a115 不同 tc 仅 15 个 | 15 vs 3174 | AC-39 |
| AG-P12 | 零合并册容忍（a182 / a81 / a91 三条为 0%） | 3 | AC-39 |
| AG-P13 | 表格级 13 + 段落级 3 两路径并存 | 13 / 3 | AC-38 |
| AG-P14 | 占位符五形态按原始字面量匹配（禁全角半角归一） | 5 | AC-26 |
| AG-P15 | T-5 ~ T-14 缺陷台账记录型锁定；sha256 交付后仍 match | 16 | AC-26 · AC-44 |
| AG-P16 | BP-11 非双射已裁定（每 componentType 契约归属） | 1 | AC-45 |
| AG-P17 | 归档欠账 5 份 / 6 条已登记且未回填修改 | 5 / 6 | AC-25 |
| AG-P18 | channel 14 / 1 / 1 且经 import 闭包复算 | 16 | AC-42 |

**编号完整性**：AG-P1 ~ AG-P18 连续 **18** 条，无缺号无重号，每条关联至少一个 AC 编号。

## 测试策略

**测试文件**：`backend/tests/workpaper_sync/test_a_class_docx_lanes.py`（新建）。

| 类名 | 覆盖 |
|---|---|
| `TestLane2Attribution` | AG-P1 ~ AG-P5 |
| `TestDocxFormatDispatch` | AG-P6 · AG-P7 |
| `TestDocxStructureBaseline` | AG-P8 · AG-P9 |
| `TestMergedCellDeduplication` | AG-P10 ~ AG-P12 |
| `TestParagraphLevelFallback` | AG-P13 |
| `TestDocxDirtyLiterals` | AG-P14 · AG-P15 |
| `TestBp11NonBijection` | AG-P16 |
| `TestArchivedDebtLane2` | AG-P17 |
| `TestChannelsViaImportClosure` | AG-P18 |

**原则**（沿用 foundation 测试原则 1 ~ 6）：期望值现读得出禁写死 · 结构性零配变异证明 · sha256 断言置前失败即中止 · 真库用 asyncpg 且无库时 skip · 扫归档区带 `errors="replace"` · 🔴 **docx 册禁跑 openpyxl，且不写「公式格计数」类判据**。

🔴 **本 spec 额外原则**：合并单元格断言必须同时给出「(row,col) 计数」与「不同 tc 计数」两个数，只给前者等于没测出去重效果。
