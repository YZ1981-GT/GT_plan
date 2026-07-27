# 约束（G 循环）

平台通用铁律见 `.omm/d-cycle-sales/constraint.md`。以下为 G 循环必须遵守的附加约束。

1. **科目码只从 `g{n}Constants.ts` / `g{n}AdjudicationItems.ts` 取**，禁止在 Tab 组件里硬编码金融资产科目码
   （已存在的码与标准科目表有偏差，硬编码会让偏差扩散且无法一处修）。
2. **TB 取数必须容错**：优先精确码 → 前缀匹配 → 科目名称回退（G9 的 `g9TbResolve` 是范式），
   金融资产科目在不同客户账套码差异极大。
3. **拆分入口的结论回流走共享存储契约**（`g{n}StorageContract.ts` / `g{n}CrossHelpers.ts`），
   不在某一入口私自新起键名。
4. **附注 sheet 名必须是 `workpaper_sheet_classification` 的真实 tab 名**（全角括号），
   不得用 OnlyOffice sheet-name 映射值。
5. **附注章节号纯数字一律精确 `===`**（五、3 ≠ 五、30+，五、2 ≠ 五、20+）；
   G13/G14 上市版关键词标题需模糊→精确解析（DB 标题可能被截断）。
6. **附注分类行若无单一科目映射，`account_codes` 必须显式 `[]`**（手工/由披露同步），
   不能留空让 binding 生成器退化成全科目并集求和。
7. **公允变动进损益还是 OCI 由分类决定**：FVPL → 6101（G13）；FVOCI → 4002（OCI）。
   调整分录对方科目不得混用。
8. **变动率阈值按科目常量**（多数 0.3，G11/G12 为 0.2），不硬编码 30%。
9. **审定表回写 TB 只在显式保存动作触发**（G7-1 曾在 mount 回写，属缺陷）。
10. **手册 / 审计文本卡片 / 状态条 / 导入导出下拉四件套复用既有组件**
    （`G{n}PreparationHandbookDialog` / `G{n}AuditTextCards` / `G{n}SheetStatusBar` / `G{n}ImportExportDropdown`），
    新科目包不另造同类组件。
