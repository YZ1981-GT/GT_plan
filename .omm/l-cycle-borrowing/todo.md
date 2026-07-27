# 待办（L 循环）

## 需核实 / 需决策

- **L5 与 K5 共用 2701**：确认单一回写方，避免互相覆盖
- **L4 应付债券 IE 前后端 detail 模型不匹配**：后端 `L4-detail-rows` + 摊余成本字段 vs 前端 beginCostPrincipal 三分解 +
  movement → round-trip 需二选一重构（deferred）

## 已知未做

- **L1-2 明细补账项/重分类调整列**（源模板 30 列）；L1 国企/上市披露从 bank-level 改 category-level SUMIF + 逾期表（部分已做）
- **L3-5 资本化利息 / L3-6 关联方判断**等源模板列富化
- **L4/L5/L6/L7 审定表从明细「带入」增强**（L4 已加，L5/L6/L7 审定表可加 SUMIF 带入按钮）
- **L3-5 逾期票据重分类未落地**（对齐 F3）：只有文字提示，未生成 RJE、未发 L1/F4 信号
- **L 循环附注结构化推送**：部分已有 buildL{n}SyncPayload + columns 并进覆盖率守卫，
  但生产环境 `sub_table_data` 为 0（全平台"披露同步未跑起来"问题）

## 已完成（本平台历史）

- **L1 逐 sheet 打磨**：检查表 hydration（getItemsByPrefix）+ 结论回读 + AI 真实接入（useL1AiNote）+ 列设置 wire +
  报告期修复 + L1-1 双期重建（含审计说明 4 要点）
- **L2 逐 sheet 复盘**：L2-1 审定表双期重建 + L2-4 凭证检查重建 + 附注 category-level 重建
- **L3 全模块**：P0 模块级崩溃修复（provide l3FormData）+ 审定表双期重建 + L3-9 凭证检查重建 +
  L3-2/5/6 数据丢失修复 + 后端 IE 键对齐 + project_id 修复 + Playwright 全 sheet 实测
- **L4 P0**：L4-2/5/6 数据丢失修复（JSON-array + hydrate）
- **L5 P0**：L5-1/2/3/6 数据丢失 + lossy 序列化修复
- **L6/L7/L8**：核实组件已有 restore wired（architecturally sound）
