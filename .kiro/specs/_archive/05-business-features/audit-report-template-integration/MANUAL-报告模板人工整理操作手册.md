# 报告正文模板人工整理操作手册

## 目标

将 `backend/data/audit_report_templates/report_body/` 下 17 个 docx 从致同**原始范例**转为**可机器填充的资产**。

## 前置条件

- Word 或 WPS（能正常编辑 .docx 保留格式）
- 已完成的 POC 参考：`1.1 模板A-无保留意见审计报告模板（…）-简版.docx`

## 总览：17 个文件

| # | 文件 | opinion_type | company_subtype | variant |
|---|------|-------------|-----------------|---------|
| 1 | 1.1 模板A…简版 | unqualified | type_a | simple |
| 2 | 1.2 模版A…详版 | unqualified | type_a | detailed |
| 3 | 1. 模板A-保留…简版 | qualified | type_a | simple |
| 4 | 1. 模板A-否定…简版 | adverse | type_a | simple |
| 5 | 2.1 模板B…简版 | unqualified | type_b | simple |
| 6 | 2.2 模板B…详版 | unqualified | type_b | detailed |
| 7 | 2. 模板B-保留…简版 | qualified | type_b | simple |
| 8 | 2. 模板B-否定…简版 | adverse | type_b | simple |
| 9 | 3.1 模板C…简版 | unqualified | type_c | simple |
| 10 | 3.2 模板C…详版 | unqualified | type_c | detailed |
| 11 | 3. 模板C-保留…简版 | qualified | type_c | simple |
| 12 | 3. 模板C-否定…简版 | adverse | type_c | simple |
| 13 | 4.1 模板D…简版 | unqualified | type_d | simple |
| 14 | 4.2 模板D…详版 | unqualified | type_d | detailed |
| 15 | 4. 模板D-保留…简版 | qualified | type_d | simple |
| 16 | 4. 模板D-否定…简版 | adverse | type_d | simple |
| 17 | 1.4.1 无法表示…简版 | disclaimer | _all | simple |

---

## 操作步骤（每个文件重复）

### 第一步：替换占位符

用 Word 的「查找替换」(Ctrl+H) 批量做：

| 查找 | 替换为 | 说明 |
|------|--------|------|
| `ABC股份有限公司` 或类似全称 | `{{company_full_name}}` | |
| `ABC公司` 或类似简称 | `{{company_short_name}}` | |
| 具体年度如 `2025`/`2026`（审计年度上下文） | `{{audit_year}}` | 注意：只改「XX年度」语境的年份 |
| 上年年度如 `2024`/`2025`（上年语境） | `{{prior_year}}` | |
| `2025年1月1日` 或期间起始 | `{{audit_period_start}}` | |
| `2025年12月31日` 或期间结束 | `{{audit_period_end}}` | |
| 报告落款日期 | `{{report_date}}` | |
| `致同会计师事务所（特殊普通合伙）` | `{{firm_name}}` | |
| 事务所地址 | `{{firm_address}}` | |
| 签字合伙人姓名（空白或范例名） | `{{signing_partner}}` | |
| 注册会计师姓名 | `{{signing_cpa}}` | |
| 报表清单那句长句 | `{{financial_statements_list}}` | 如「合并及公司资产负债表…」 |
| 治理层（董事会/管理层） | `{{responsibility_organ}}` | 仅在有【二选一】的位置 |
| 报告编号 `致同审字（20XX）第110ASXXXX号` | `{{report_number}}` | |

**注意**：
- 不要改页眉页脚里的「致同会计师事务所」logo 文字（那是格式不是占位）
- 年份在多处出现，逐一判断语境再替换
- 参考已完成的 `1.1` 文件对照确认

### 第二步：标记可选段落 `##OPT:`

找到以下段落（每个模板不一定都有），用标记包裹：

```
##OPT:emphasis:强调事项段##
（强调事项的全部正文段落）
##/OPT:emphasis##
```

```
##OPT:going_concern:持续经营重大不确定性##
（持续经营相关段落）
##/OPT:going_concern##
```

```
##OPT:key_audit_matters:关键审计事项##
（KAM 整块，含标题到具体事项描述）
##/OPT:key_audit_matters##
```

```
##OPT:other_matter:其他事项##
（其他事项正文）
##/OPT:other_matter##
```

```
##OPT:comparative:比较数据/其他审计师##
（比较数据相关段落）
##/OPT:comparative##
```

```
##OPT:other_information:其他信息##
（其他信息段落，如年报中非财务信息相关）
##/OPT:other_information##
```

**技巧**：
- 标记放在段落最前（开始标记自成一行）和最后（结束标记自成一行）
- 标记行格式用 Normal，不影响后续段落样式
- 不确定是否可选的段落 → 不标（宁可少标不多标）

### 第三步：标记指引注释 `##NOTE:`（少数需保留的提示）

如果有「给项目组看但不出品」的提示文字，且你认为保留参考价值：

```
##NOTE:项目组提示:KAM 至少填写一项具体事项##
```

**大多数情况直接删除即可**，不需要标 NOTE。

### 第四步：删除编制说明和提示材料

**直接删除**（不标记、不保留）：

- 文首的「审计报告格式说明」或「使用说明」段落
- 所有 `【…】` 括号内的披露要求/选用指引
- 所有 `（…删除）`、`（有限，删除）` 编辑提示
- 范例公司 `XXXX`、`XX有限公司` 残留
- 国资委披露原文抄录
- IPO/再融资等特殊场景的选用规则文字

### 第五步：保存并校验

1. Ctrl+S 保存（确保格式为 `.docx`）
2. 肉眼检查：
   - 页眉页脚完好
   - 段落样式/字体没变
   - 没有裸露的 `ABC`、`XXXX`、`【`

---

## 校验命令（整理完后跑一次）

```bash
# 仓库根目录执行
python backend/scripts/validate_template_manifest.py --strict
```

无 warning 即通过。

---

## 完成标志

- [ ] 17 个 docx 全部处理完毕
- [ ] 无裸 ABC / XXXX / 【 残留（校验脚本通过）
- [ ] 每个文件至少有 `{{company_full_name}}` 和 `{{audit_year}}`
- [ ] 无保留意见（4个）至少有 `##OPT:key_audit_matters:` 段
- [ ] Word 打开格式与原件一致（页眉页脚、字体、间距）
- [ ] `template_manifest.json` 中 report_body 路径全部指向 `.docx`

完成后告诉我，我来更新 manifest 路径映射 + 跑 CI 校验 + 标记 task 0.6.1 完成。

---

## 附：POC 参考对照

打开 `1.1 模板A-无保留意见审计报告模板（…）-简版.docx`（已整理完），对照你要处理的文件逐段比对。关键差异点：

- 保留意见/否定意见/无法表示意见模板的**意见段**措辞不同 → 不要替换意见段本身的法定措辞
- 详版比简版多「关键审计事项」详细模板 → 详版的 KAM `##OPT:` 块会更长
- 无法表示意见（disclaimer）模板可能没有 KAM 段 → 无需标 `##OPT:key_audit_matters:`

## 附：批量操作建议

如果你觉得逐文件太慢，可以：
1. 先处理 4 个「无保留简版」（1.1/2.1/3.1/4.1）— 结构最相似
2. 再处理 4 个「无保留详版」（1.2/2.2/3.2/4.2）— 在简版基础上多 KAM 详细模板
3. 再处理 4 个「保留意见」（结构类似无保留，少了 KAM）
4. 再处理 4 个「否定意见」（与保留意见结构几乎相同）
5. 最后处理 1 个「无法表示意见」（最简短）


---

# 附注模板人工清理操作手册

## 当前状态

4 个附注 docx 已经由脚本 `tag_note_sections_full.py --write` 完成了 `##SECTION:code##...##/SECTION:code##` 自动打标（覆盖率 86-97%）。

**但块内仍残留致同编制提示**：
- 【根据XX准则…】披露要求
- 使用说明段落
- （…删除）/ （有限，删除）编辑提示
- 范例数据（XXXX年、XX公司）

这些需要人工清理。

## 文件位置

```
backend/data/audit_report_templates/disclosure_notes/
├── soe_standalone.docx      ← 国企单体
├── soe_consolidated.docx    ← 国企合并
├── listed_standalone.docx   ← 上市单体
└── listed_consolidated.docx ← 上市合并
```

## 操作步骤

### 第一步：删除文首「使用说明」

打开每个 docx，找到文档开头（第一个 `##SECTION:` 之前）的「使用说明」/「编制说明」段落，**整段删除**。

### 第二步：清理 SECTION 块内的【】提示

**在每个 `##SECTION:code##` 块内**，删除：

| 要删的内容 | 示例 |
|-----------|------|
| 【…】披露要求 | `【根据企业会计准则第30号…应当披露…】` |
| （…删除）提示 | `（无此项业务的，删除）` |
| 选用指引 | `【适用于…时增加以下披露】` |
| 范例年份 | `XXXX年`、`XX月XX日` |

**保留不动的**：
- `##SECTION:code##` 和 `##/SECTION:code##` 标记本身
- `##STYLE_REF:table:code##` 参考表标记
- 账户标题（如「货币资金」「应收账款」）
- 表格结构（表头、边框、合并格）— 保留作样式参考

### 第三步：封面占位符

文档最前面的封面区域（SECTION 块外），替换为：

```
{{company_full_name}}
财务报表附注
（{{audit_year}}年度）
```

### 第四步：确认格式完整

- 页眉页脚没动
- 表格边框/样式完好
- SECTION 标记成对且完整

---

## 校验命令

```bash
# 检查残留【、使用说明、XXXX
python backend/scripts/validate_note_template.py

# 检查 SECTION 打标与 seed 一致性
python backend/scripts/validate_section_code_index_consistency.py
```

两个都 exit 0 即通过。

---

## 注意事项

1. **不要动 SECTION 标记**——那些是脚本自动打的，位置已验证正确
2. **不要删表格**——即使表格里是范例数据，保留结构作为样式参考（生成时程序会用真实数据替换）
3. **4 份独立处理**——不要从一份复制粘贴到另一份（单体/合并章节不同，国企/上市编号不同）
4. 如果看到 `{{section:code}}` / `{{table:code}}` / `{{seq:prefix}}` 这些占位符，**保留不动**（那是程序填充用的）
5. 如果 SECTION 块内**没有** `{{section:}}` / `{{table:}}` 占位符（大概率目前没有），不用管——当前 template 模式只做裁剪+标记清理，数据填充占位符是后续 Phase 做的事

---

# 报表模板状态（无需手动操作）

4 个 xlsx 已由脚本完成：
- `prepare_financial_templates.py` 注入了 752 个 `{{row:CODE:current/prior}}` 内联占位
- `export_cell_mapping_from_xlsx.py` 导出了完整 `cell_mapping.json`
- 表头 `{{company_full_name}}` / `{{period_end_date}}` 等已替换
- 公式格（=SUM 等）未被覆盖

**不需要手动修改报表 xlsx。**

---

## 总结：你需要手动做的

| 品类 | 文件数 | 工作内容 | 预计耗时 |
|------|--------|---------|----------|
| 报告正文 | 17 个 docx | 占位符替换 + OPT 标记 + 删说明 | ~1-2 天 |
| 附注 | 4 个 docx | 删【】/使用说明（SECTION 已打好） | ~半天 |
| 报表 | 0 | 已完成，无需操作 | — |

**做完后告诉我**，我来：
1. 更新 `template_manifest.json` 路径映射
2. 跑 `validate_template_manifest.py --strict` + `validate_note_template.py` 确认绿
3. 标记 task 0.6.1 / 0.7 完成
4. 切换 `USE_TEMPLATE_FILL_SERVICE=true`（task 17.3）收尾整个 spec
