# Requirements Document

## Introduction

F2 存货的「四表库 → 底稿 → 披露表 → 附注」链路存在一处**结构性**缺陷：
**存货分类是按科目编码硬编码的，而存货科目的编码↔名称在本平台内并不唯一。**

postgres 只读实证（`account_chart` 表 `source='standard'`，9 个真实项目）：同一套「标准科目表」
在库里**并存两个互不兼容的变体**，且冲突恰好落在 F2 最核心的几个科目上：

| 科目码 | 变体 A（3 个项目） | 变体 B（5 个项目） |
|---|---|---|
| `1405` | 自制半成品 | **库存商品** |
| `1406` | **库存商品** | 发出商品 |
| `1407` | 发出商品 | **商品进销差价** |
| `1408` | **商品进销差价** | 委托加工物资 |
| `1409` | 周转材料 | —— |
| `1411` | 委托加工物资 | **周转材料** |
| `1416` | **存货跌价准备**（5 项目） | —— |
| `1451` | 包装物 | 损余物资 |
| `1461` | —— | **存货跌价准备**（6 项目） |

变体 B 是 CAS 2006 官方口径（1405 库存商品 / 1406 发出商品 / 1407 商品进销差价 /
1408 委托加工物资 / 1411 周转材料）；变体 A 是本地化改编。

**结论：不存在一组「写死就对」的存货科目编码。** 而现实现三处都在写死：

1. 后端 `_f2_inventory_main.F2_CATEGORIES` —— 把 13 个分类顺序绑到 `1401..1412` + `1471`，
   与两个变体**都不一致**（如 `原材料→1401`，而 1401 两个变体都是「材料采购」；
   `周转材料→1403`，而 1403 两个变体都是「原材料」）；
2. 后端 `f2_extraction.build_default_bindings` 直接消费同一份 `F2_CATEGORIES`
   → 灰度开关打开后走的仍是错科目；
3. 前端 `f2AccountModel.F2_ROW_KEY_ACCOUNT` / `F2_ACCOUNT_TO_ROW_KEY` /
   `F2_INVENTORY_ACCOUNTS` 与后端镜像同一份错映射（AJE 科目下拉、写回 TB、溯源面板均用它）。

实测后果（`tb_balance` 全库 14xx 汇总）：现映射把「原材料」指到 `1401 材料采购`
（全库期末合计 **0.00**）、把「库存商品」指到 `1406`（**恰好在变体 A 项目上对**、
在变体 B 项目上取到的是「发出商品」）、把「跌价准备」指到 `1471`
（6 个项目该码是**合同取得成本**，1 个项目才是跌价准备；真正的跌价在 `1416`，
全库期末 **−4,149,232.42**）。

另有两处独立缺陷：

4. **`_row_depth` + 取最深层级** —— 与 K1 已修的同款 bug：客户科目树参差时
   `max(by_depth)` 会整段丢一级叶子。K1 spec 已把正确实现沉淀为共享件
   `app/services/four_table.select_leaves`（严格点号边界判叶子），F2 未委托。
5. **`workpaper:F2` 的 71 条公式预设科目码几乎全错**（运行态 `convert_prefill_presets()` 实测）：
   `原材料_期初=TB('1401',…)`、`在产品_期初=TB('1402',…)`、`库存商品_期初=TB('1403',…)`、
   `工程物资_期初=TB('1405',…)`、`委托加工物资_期初=TB('1408',…)`、
   `存货跌价准备_期初=TB('1461',…)`、`LEDGER('1403','期末数量')` 标「库存商品」、
   `AUX('1403','仓库',…)`、`TB_SUM('1401~1461')` 当存货合计（报表行是 `1401~1499`）。

## Requirements

### Requirement 1: 存货分类改为按科目名称归类（单一真源）

**User Story:** 作为审计助理，我在两个不同客户的项目上打开 F2 审定表，都应该看到
「库存商品」行取到库存商品的数、「原材料」行取到原材料的数，
而不是因为客户用了另一版科目表就整表错位。

#### Acceptance Criteria

1. SHALL 新建后端纯函数 `classify_f2_category(account_name)`，按**科目名称**把 14xx
   科目归入 F2-1 审定表分类 rowKey；顺序即优先级，长词先判（如「存货跌价准备」
   必须先于「存货」、「自制半成品」先于「半成品」）。
2. 归类 SHALL 覆盖两个标准变体的全部 14xx 名称，以及客户自定义子科目名
   （实证如 `库存商品_外购商品（零售）`、`存货跌价准备_库存商品`）。
3. 未命中任何关键字的科目 SHALL 归入 `other` 桶（不丢科目）。
4. `F2_CATEGORIES` 的 `account` 字段 SHALL 降级为**兜底/展示用**，运行时取数
   SHALL NOT 依赖它。
5. 备抵（存货跌价准备）SHALL 由名称识别并单独成一个 block（`impairment`），
   聚合结果取绝对值（两种符号约定同解）。

### Requirement 2: 叶子聚合委托平台共享件

**User Story:** 作为质量控制复核合伙人，我需要 F2 的取数和 K1/D1/F1 用同一套叶子判定，
避免「参差科目树整段丢叶子」这类只在特定客户上暴露的错。

#### Acceptance Criteria

1. `_build_adjudication_prefill` SHALL 改用 `app.services.four_table.select_leaves`
   判叶子，删除本地 `_row_depth` 与 `max(by_depth)` 取最深层级的逻辑。
2. 自检不变量：各分类桶期末之和 SHALL 等于 14xx 全部叶子期末之和
   （不重不漏，Property 1）。
3. `1401~1499` 区间口径下跌价准备（贷方为负）天然抵减 SHALL 保持，
   `impairment` block 另行单列以供披露表「跌价准备」列使用。

### Requirement 3: 项目实际科目表下发前端

**User Story:** 作为审计助理，我在 F2-14 录调整分录时，科目下拉应该列出**本项目**
真实存在的存货科目（含客户自定义子科目），而不是一份写死的可能不存在的清单。

#### Acceptance Criteria

1. F2 render SHALL 输出 `project_context.inventory_accounts`
   = `[{code, name, row_key}]`（取自本项目 `account_chart` 的 14xx 科目，
   `row_key` 由 R1 的名称归类给出）。
2. 前端 AJE 科目下拉与 `F2_ACCOUNT_TO_ROW_KEY` 的消费点 SHALL 优先用它，
   为空时回退既有静态清单（零回归）。
3. `F2_ROW_KEY_ACCOUNT` 的写死映射 SHALL 保留但标注为兜底，
   并 SHALL 有守卫断言「运行时消费点不得只依赖它」。

### Requirement 4: 公式预设重写

**User Story:** 作为审计助理，我在 F2 各页打开公式管理时，看到的公式必须是本项目能取到数的；
一条写死错科目的公式比没有公式更糟，因为它会让我以为取过数了。

#### Acceptance Criteria

1. `workpaper:F2` 的预设 SHALL 只保留**项目无关**的口径：
   区间合计 `TB_SUM('1401~1499',…)`（报表行 `BS-010`）、
   `ADJ` / `PREV` / 底稿间 `WP()` 链接。
2. 凡依赖「某个具体 14xx 编码 = 某个分类」的预设 SHALL 删除
   （编码语义项目间冲突，写死必错 —— 宁缺勿造）；
   跌价准备保留但 SHALL 同时给出 `1416` 与 `1461` 两条并在 `description`
   写明「按项目科目表二选一」。
3. SHALL 新增覆盖底稿间联动的 `WP()` 预设：
   F2-1 ← F2-2 明细汇总；F2-2 ← F2-3~F2-13 各分类明细表；
   两个披露 sheet ← F2-1 / F2-2；F2-47 跌价测试 ← F2-1。
4. `cell_ref` SHALL 在 `workpaper:F2` 页内唯一（`page_key` 忽略 sheet）。
5. 新增/保留的公式 SHALL 通过 `validate_formula`（prefill 专属词汇 `ADJ`/`TB_SUM`/`LEDGER` 豁免）。

### Requirement 5: 披露表与附注结构核查

**User Story:** 作为审计助理，我在披露表点「同步到附注」后，附注 §五、9 / §八、10
的表结构和列头应与源模板一致。

#### Acceptance Criteria

1. SHALL 用 openpyxl 直读 `backend/wp_templates/F/F2存货.xlsx` 的两个披露 sheet，
   把关键结构断言固化为守卫（上市 (1) 分类表 7 列两级 + 9 数据行 + 合计；
   (2) 跌价准备变动表 7 列两级；(3) 按组合 二选一；(5)(6) 房企开发成本/开发产品）。
2. 上市 (1) 分类表由 11 行改回**源模板 9 行 + 房企增列**的口径 SHALL NOT 执行
   —— 源模板 R20 红字明确「房地产开发企业应增加'开发成本''开发产品'等种类」，
   现 11 行属源模板授权的扩展，保留（写入 spec Notes 防复盘重复提议）。
3. 若发现底稿列常量 / 附注模板 `columns` / 源 xlsx 三方不一致 THEN SHALL 以源 xlsx
   为准修正，并更新 `fix_note_inventory_structure.py` 与契约测试。

### Requirement 6: 守卫与实测

**User Story:** 作为质量控制复核合伙人，我需要「按名称归类」这个口径被两个变体的样本钉住，
避免有人日后又改回按编码写死。

#### Acceptance Criteria

1. SHALL 有后端守卫用真实 `account_chart` 的**两个变体**样本断言
   `classify_f2_category` 在两版下都归类正确，且含反向自检
   （把关键字顺序打乱必失败）。
2. SHALL 有守卫断言 `F2_CATEGORIES` 不再被取数路径按 `account` 消费
   （源码级正则 + `stripComments`）。
3. SHALL 有守卫断言 `workpaper:F2` 预设无 `cell_ref` 撞键、
   且不含被判定为「编码语义冲突」的写死映射。
4. SHALL 在真实项目上直跑 render 验证：变体 A 项目与变体 B 项目
   各分类桶金额正确、桶之和 == 14xx 叶子合计。

## Glossary

| 术语 | 含义 |
|---|---|
| 变体 A / 变体 B | 库内并存的两版标准存货科目表（见 Introduction 表格） |
| rowKey | F2-1 审定表分类行标识（`raw-materials` / `finished-goods` / …） |
| block | F2-1 的两个区块：`gross`（原值）/ `impairment`（跌价准备） |
| F2-2 | 明细汇总表（各分类的跌价准备计提/转回明细，披露 (2) 表的数据源） |
| F2-3~F2-13 | 各分类明细表（原材料 / 材料采购在途 / 周转材料 / … / 消耗性生物资产） |
