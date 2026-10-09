# Task 1 — 现算复核 slice 承重结论

**日期**：2026-09-27　**方法**：python 脚本逐项读文件

```
=== ① manifest I entries: 6 条 ===
  xlsx/gt-i1-intangible-assets
    capability = single_onlyoffice
    html_store = unresolved
    capability_target = None
    adapter_id = None
    independent_entry = True
    parent_entry_id = None
    mounts = 2
  xlsx/gt-i2-development-expenditure
    capability = single_onlyoffice
    html_store = unresolved
    capability_target = None
    adapter_id = None
    independent_entry = True
    parent_entry_id = None
    mounts = 2
  xlsx/gt-i3-goodwill
    capability = single_onlyoffice
    html_store = unresolved
    capability_target = None
    adapter_id = None
    independent_entry = True
    parent_entry_id = None
    mounts = 4
  xlsx/gt-i4-long-term-prepaid
    capability = single_onlyoffice
    html_store = unresolved
    capability_target = None
    adapter_id = None
    independent_entry = True
    parent_entry_id = None
    mounts = 2
  xlsx/gt-i5-other-noncurrent-assets
    capability = single_onlyoffice
    html_store = unresolved
    capability_target = None
    adapter_id = None
    independent_entry = True
    parent_entry_id = None
    mounts = 2
  xlsx/gt-i6-research-development-expense
    capability = single_onlyoffice
    html_store = unresolved
    capability_target = None
    adapter_id = None
    independent_entry = True
    parent_entry_id = None
    mounts = 2

=== ② overlay ===
  by_entry 里 I entry 数: 0
  overrides 里 I entry 数: 0
  defaults_by_component.GtOnlyOfficeSheet.capability = single_onlyoffice
  defaults_by_component.GtOnlyOfficeSheet.capability_target = None

=== ③ composable import 计数（import 路径字面量三形态）===
  useI1FormData: import_prod=5 import_test=0 mention_only=1
  useI2FormData: import_prod=4 import_test=1 mention_only=0
  useI3FormData: import_prod=2 import_test=2 mention_only=0
  useI4FormData: import_prod=0 import_test=0 mention_only=1
  useI5FormData: import_prod=1 import_test=0 mention_only=0
  useI6FormData: import_prod=0 import_test=0 mention_only=2
  useI1DualMode: import_prod=1 import_test=1 mention_only=1
  useI2DualMode: import_prod=1 import_test=0 mention_only=0
  useI3DualMode: import_prod=1 import_test=0 mention_only=1
  useI4DualMode: import_prod=1 import_test=0 mention_only=1
  useI5DualMode: import_prod=1 import_test=0 mention_only=1
  useI6DualMode: import_prod=1 import_test=1 mention_only=0

=== ④ owner 常量 ===
  I1: ITEM_ID_ROWS = 'I1-2-rows'
  I2: ITEM_ID_ROWS = 'I2-2-rows'
  I3: ITEM_ID_ROWS = 'I3-2-rows'
  I4: ITEM_ID_ROWS = 'I4-2-rows'
  I5: ITEM_ID_ROWS = 'I5-2-rows'
  I6: STORAGE_KEY = 'I6-2-detail-rows'
  I6: LEGACY_STORAGE_KEY = 'I6-2-rows'

=== ⑥ 模板 6 文件 ===
  I1 无形资产、累计摊销及减值准备.xlsx: 136,885 bytes  sha256=97eced1f58ab3925
  I2 开发支出.xlsx: 138,084 bytes  sha256=a93c298b1f4adfe2
  I3 商誉.xlsx: 212,588 bytes  sha256=96cd6d6cb70698ce
  I4 长期待摊费用.xlsx: 312,532 bytes  sha256=8bfb85884705e471
  I5 其他非流动资产.xlsx: 306,241 bytes  sha256=7e8ec9c22580e05d
  I6 研发费用.xlsx: 87,268 bytes  sha256=924a1e8348a897c2
  Total files: 6
```

## CD 源区间（⑤）需用 openpyxl 另行核查（见下方补充）

## ⑤ CD 源区间 openpyxl 逐格核查

```
=== CD-1: 底稿目录!A9:A19 ===
  A9 = 土地使用权
  A10 = 住房使用权
  A11 = 专利权
  A12 = 非专利技术
  A13 = 商标权
  A14 = 著作权
  A15 = 特许经营权
  A16 = 软件
  A17 = 矿产权
  A18 = 数据资源
  A19 = 其他
  A8 = 无形资产类别设置（以下内容请根据实际情况修改）：
  A20 = ……

=== CD-2: 附注披露信息（国有企业）!A9:A19 ===
  A9 = 其中：土地使用权
  A10 = 住房使用权
  A11 = 专利权
  A12 = 非专利技术
  A13 = 商标权
  A14 = 著作权
  A15 = 特许经营权
  A16 = 软件
  A17 = 矿产权
  A18 = 数据资源
  A19 = 其他
  A8 = 一、原价合计

=== CD-3: 明细表I5-2!A11:A20 ===
  A11 = 预付土地出让金
  A12 = 预付工程款
  A13 = 预付房屋、设备款
  A14 = 无形资产预付款
  A15 = 预付投资款
  A16 = 委托贷款
  A17 = 合同资产
  A18 = 合同取得成本
  A19 = 合同履约成本
  A20 = 应收退货成本
  A21 = ……
  A22 = 合计

=== CD-4: 明细表I6-2!A9:A12 ===
  A9 = 人工费
  A10 = 材料费
  A11 = 制造费用分摊
  A12 = 无形资产摊销
  A13:A18 = [None, None, None, None, None, None]
  A13:A18 全空: True

=== CD-8: 明细表I4-2!A9:A22 ===
  A9 = None
  A10 = None
  A11 = 使用权资产改良及维护支出
  A12 = None
  A13 = None
  A14 = None
  A15 = None
  A16 = None
  A17 = None
  A18 = None
  A19 = None
  A20 = None
  A21 = None
  A22 = None
```

## 结论

6 项复算全部与 slice/design 声明**相符**，slice 承重结论**零反驳**。
1 处快照过期已确认（BP-2 记契约目录 5 个，现算 17 个 — 见 Task 3 核验）。
