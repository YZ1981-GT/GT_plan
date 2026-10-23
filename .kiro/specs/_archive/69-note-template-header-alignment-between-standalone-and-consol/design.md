# 单体与合并附注模板列名统一对齐 — 技术方案

## §1 修复策略

**只改单体模板 JSON，不改合并模板，不改数据库已有数据。**

合并模板的列路径是「期间前缀/分组/属性」三级全路径（如 `期末余额/账面余额/金额`），已被公式推送种子、标题行库、公式管理引用。单体模板的列名只影响编辑器显示和 `note_writer` 的表头渲染——`note_writer` 按位置写 `values[]` 数组，不按列名定位，所以改列名不影响写入。

读取层 `consol_note_standalone_reader` 在认列时会：
1. 解析两侧列路径（合并用 `headers` 全路径，单体用 `headers` + `_column_groups` 组合）
2. 去掉期间前缀后逐列比较

改完单体列名后，去掉期间前缀的结果应与合并完全一致。

## §2 修复清单

### 2.1 B 类：科目名 → 属性名（约 30 处）

**上市版 `note_template_listed.json`**

| 章节 | 子表名 | 现值列名 | 改为 |
|------|--------|---------|------|
| 应收账款 | 组合计提项目：应收中央企业客户 | `应收账款` × 2（期末/上年年末各一列） | `账面余额` |
| 应收账款 | 组合计提项目：应收地方国有企业客户 | `应收账款` × 2 | `账面余额` |
| 应收账款 | 组合计提项目：应收海外企业客户 | `应收账款` × 2 | `账面余额` |
| 应收账款 | 组合计提项目：组合4 | `应收账款` × 2 | `账面余额` |
| 应收账款 | 组合计提项目：组合5 | `应收账款` × 2 | `账面余额` |
| 应收票据 | 按单项计提坏账准备的应收票据 | `应收票据` × 2 | `账面余额` |

上市版母公司章节（chapter-16-*）与合并报表章节（chapter-05-*）结构相同，一并修复。

**国企版 `note_template_soe.json`**

| 章节 | 子表名 | 现值列名 | 改为 |
|------|--------|---------|------|
| 应收账款(八、5) | 组合计提项目 × 3 | `应收账款` × 2 | `账面余额` |
| 应收票据(八、4) | 组合计提项目 × 3 | `应收票据` × 2（如适用） | `账面余额` |
| 其他应收款(八、9) | 组合计提项目 × 3 | `其他应收款` × 2（如适用） | `账面余额` |
| 营业收入/成本(八、64/65) | 分产品/地区 | `收入`/`成本` | `主营业务收入`/`主营业务成本` |

### 2.2 C 类：期间词归一（约 15 处）

只改**单体模板中与合并模板不一致的表**：

| 场景 | 现值 | 改为 | 文件 |
|------|------|------|------|
| 上市版表头中用「期末数/期初数」而合并用「期末余额/期初余额」 | `期末数`/`期初数` | `期末余额`/`期初余额` | listed |
| 国企版变动表用「年初余额」而合并用「期初余额」 | `年初余额` | `期初余额` | soe |
| 上市版续表用「上年年末数」而合并用「上年年末余额」 | `上年年末数` | `上年年末余额` | listed |

### 2.3 D 类：分组层级补齐（约 15 处）

单体模板 `_column_groups` 定义了分组名（如 `{"group": "账面余额", "start": 1, "span": 2}`），但 headers 中第 2 列写的是 `比例(%)`，而合并模板全路径是 `账面余额/比例(%)`。

修正方式：**不改 headers 也不改 _column_groups**——读取层 `standalone_col_paths` 已经把两者组合成全路径。实际差异是分组名本身不一致（如单体分组名 `账面金额` vs 合并路径中 `账面余额`），需把单体 `_column_groups[].group` 改为与合并一致。

涉及：
- listed 五-16-2 系列：`账面余额-金额` → `账面余额/金额`（分隔符 `-` → `/`）
- soe 五-5-4/五-5-5 系列：`_column_groups.group` 的名字与合并路径对齐
- soe 十一-关联交易：`本期发生额` 分组名中包含的子列名对齐

## §3 读取层词表扩充

在 `consol_note_standalone_reader.py` 的 `_PERIOD_SYNONYMS` 中补全以下同义对：

```python
_PERIOD_SYNONYMS = {
    # 现有...
    # 新增
    "期末数": "期末余额",
    "期初数": "期初余额",
    "年初余额": "期初余额",
    "上年年末数": "上年年末余额",
    "本年数": "本期发生额",
    "上年数": "上期发生额",
}
```

这确保即使用户的 `disclosure_notes` 是用旧版单体模板写入的（列名仍是旧值），读取层也能正确匹配。

## §4 守卫测试

新建 `backend/tests/test_note_template_header_alignment.py`：

```python
def test_standalone_consol_header_alignment():
    """单体与合并模板列名对齐守卫。
    
    扫描两版（listed/soe）单体模板的全部子表，
    与合并模板按表名匹配后逐列对比（去掉期间前缀）。
    
    允许的差异：
    - A/E 类（列数不同 / 完全不同的列语义）→ 登记在 _KNOWN_STRUCTURAL_DIFFS
    - B/C/D 类（列名不一致）→ 必须为 0
    """
```

守卫逻辑：
1. 按表名匹配两侧子表
2. 列数不同的 → 检查是否在 `_KNOWN_STRUCTURAL_DIFFS` 白名单里
3. 列数相同的 → 逐列去掉期间前缀后比较，不一致的累计为 `naming_diffs`
4. 断言 `naming_diffs == 0`
5. 白名单不允许有失效条目（白名单里的表如果两侧列数已一致，说明被修好了，条目要删）

## §5 修复脚本

一次性脚本 `backend/scripts/fix/_fix_standalone_header_alignment.py`：
- 读取两份单体模板 JSON
- 按 §2 的替换规则逐表修改 `headers` 和 `_column_groups`
- 写回 JSON（保持 ensure_ascii=False + indent=2）
- 打印修改统计：每张表改了哪些列、总计多少处
- `--dry-run` 模式只打印不写

修复后删除脚本（`_` 前缀 = 用完即删）。

## §6 涉及文件

| 文件 | 操作 |
|------|------|
| `backend/data/note_template_listed.json` | 改：headers/column_groups 列名 |
| `backend/data/note_template_soe.json` | 改：headers/column_groups 列名 |
| `backend/app/services/consol_note_standalone_reader.py` | 改：期间词表扩充 |
| `backend/tests/test_note_template_header_alignment.py` | 新：守卫测试 |
| `backend/scripts/fix/_fix_standalone_header_alignment.py` | 新→删：一次性修复脚本 |

### 不改

| 文件 | 理由 |
|------|------|
| `backend/data/consol_note_sections_listed.json` | 合并模板不动（被大量引用） |
| `backend/data/consol_note_sections_soe.json` | 同上 |
| `backend/data/formula_push_rules.json` | 按合并列路径建的推送规则不受影响 |
| `backend/data/note_table_header_library.json` | 按合并表头建的标题行库不受影响 |

## §7 风险与回退

- **已有 `disclosure_notes` 数据不受影响**：数据存的是 `values[]` 位置数组，不含列名。改模板列名只影响下次打开编辑器时的表头显示和下次写入时的 headers 值。
- **读取层词表是兜底**：即使有漏改的旧数据，词表保证期间归一后能匹配。
- **回退**：`git revert` 单个提交恢复两份 JSON 即可。
