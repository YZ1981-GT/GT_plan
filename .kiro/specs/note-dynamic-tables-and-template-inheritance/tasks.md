# 附注模块全维度增强 — 任务列表

> 版本：v0.3（草稿，2026-05-28）
> 92 验收 / 22 人天 + 外部 3 人天 / 12 Sprint
> 关联：requirements.md / design.md
> 原则：能不写死就不写死，全部支持动态调整

## 前置（外部依赖，3 人天）

- [ ] **P-1** 审计师标注 60+ 章节动态区域（行+列，1 人天）
- [ ] **P-2** 审计师标注 30+ 章节 wp_data 绑定（1 人天）
- [ ] **P-3** 审计师标注 20+ 段落 Jinja 模板（0.5 人天）
  - 重点章节：公司基本情况、会计政策、税项政策、合并范围说明
  - 输出：`backend/data/note_text_templates.json`（section → template_str + required_vars）
- [ ] **P-4** 致同 PDF 视觉基线（0.5 人天）

## Sprint 1：数据模型 + Migration（2 人天，A1~A15）

- [ ] **1.1** row_type/列 sidecar 模型（A1-A5）
- [ ] **1.2** binding 多源 fallback 模型（A6-A8）
- [ ] **1.3** is_empty / lineage / is_local_override / text_template_vars 字段（A9-A12）
- [ ] **1.4** group_note_template_baseline 表 V019（A13）
- [ ] **1.5** note_section_version_tree 表 V020（A14）
- [ ] **1.6** Sprint 1 验收（CI-1/CI-2/CI-3/CI-14）

## Sprint 2：动态行/列引擎（2.5 人天，B1-B11）

- [ ] **2.1** _expand_dynamic_regions 行展开
- [ ] **2.2** _expand_dynamic_columns 列展开 + 合并表头处理
- [ ] **2.3** aux_balance 行 explode
- [ ] **2.4** **wp_data _extract_wp_table / _extract_wp_cell / _extract_wp_column_sum**（核心，单测 15 用例）
- [ ] **2.5** **多源 fallback 链 _resolve_with_fallback**（单测 12 用例 + CI-9/CI-10）
- [ ] **2.6** _cell_provenance 记录
- [ ] **2.7** 动态行 label 自动填充
- [ ] **2.8** 合计公式自动适配
- [ ] **2.9** update_note_values + note_cell_merge 行+列三态合并 PBT 6 不变量
- [ ] **2.10** is_empty 计算
- [ ] **2.11** Sprint 2 验收

## Sprint 3：公式 + auto_trim v2（1 人天，B12 + 公式)

- [ ] **3.1** REGION + WP 公式函数完善
- [ ] **3.2** PRIOR 跨年动态匹配
- [ ] **3.3** auto_trim_v2 三级裁剪 + Word 空表替换 + 空章节跳过（CI-8）
- [ ] **3.4** Sprint 3 验收

## Sprint 4：文字段落 Jinja（1.5 人天，B18 + D7 全栈）

- [ ] **4.1** note_text_template_engine.py 新建（Jinja env + 自定义 filter format_amount/cn_number/date_cn）
- [ ] **4.2** _render_text_paragraph 接入 generate_notes 管线
- [ ] **4.3** 段落变量自动收集（wizard_state + client master + consolidation + prior_notes）
- [ ] **4.4** 段落 Word 渲染（保留致同字号字体）
- [ ] **4.5** 模板 JSON 加载 P-3 输出（20+ 段落）
- [ ] **4.6** CI-11 必有变量声明
- [ ] **4.7** 单测 18 用例（含 missing var / nested / consol_level 切换）

## Sprint 5：集团模板继承（2.5 人天，B13/B14 + E1-E10）

- [ ] **5.1** group_note_baseline_service.py（save/apply/diff/sync）
- [ ] **5.2** 多层级 lineage（parent_baseline_id 链）
- [ ] **5.3** apply_group_baseline 复制文字+表样+vars
- [ ] **5.4** local_override 标记
- [ ] **5.5** 基线版本管理 v{major}.{minor}
- [ ] **5.6** 基线升级通知
- [ ] **5.7** 多 child 批量同步
- [ ] **5.8** child 反哺基线建议
- [ ] **5.9** 新 router group_note_baseline.py（5 端点）
- [ ] **5.10** Sprint 5 验收（CI-7）

## Sprint 6：合并附注衔接 D8（1.5 人天，B19-B21 + F1-F5）

- [ ] **6.1** 改造 ConsolDisclosureService 不再 sort_order=100
- [ ] **6.2** 子公司清单实时拉取（generate 时重查 consolidation_subsidiaries）
- [ ] **6.3** 抵销前后双列（new column "抵销前/后" 自动展开）
- [ ] **6.4** 商誉/MI/外币章节绑 H/G/M wp_data
- [ ] **6.5** 多层级合并 lineage（孙合并 → 子合并 → 总合并）
- [ ] **6.6** integrate_with_standalone_notes V2
- [ ] **6.7** Sprint 6 验收（CI-12）

## Sprint 7：协作锁集成 D9（0.5 人天，B22 + G1-G2）

- [ ] **7.1** 4 入口集成 NoteSectionLockService（动态行/列/基线/auto_trim）
- [ ] **7.2** 前端章节列表锁可视化
- [ ] **7.3** 锁冲突弹窗 + 抢占
- [ ] **7.4** Sprint 7 验收（CI-13）

## Sprint 8：AI 辅助 D10（1 人天，B23 + G3-G5）

- [ ] **8.1** suggest_dynamic_rows（基于 aux_code 数量）
- [ ] **8.2** generate_paragraph_from_workpaper（从 H/G 摘要 LLM 生成）
- [ ] **8.3** check_wp_tb_consistency 校核
- [ ] **8.4** 前端 AI 建议侧栏
- [ ] **8.5** 单测 + UAT

## Sprint 9：章节版本图 D11（1.5 人天，B24/B25 + G6-G10）

- [ ] **9.1** note_section_version_tree_service.py（fork/merge/diff）
- [ ] **9.2** 跨年合并范围变化高亮
- [ ] **9.3** 章节 fork（独立分支）
- [ ] **9.4** 多版本 merge（ours/theirs/manual）
- [ ] **9.5** 前端版本树可视化（git-like 分支图）
- [ ] **9.6** Sprint 9 验收（CI-14）

## Sprint 10：前端编辑器（3 人天，C1-C22）

- [ ] **10.1** 6 个 composable 新建（useNoteDynamic / useGroupBaseline / useNoteText / useNoteAI / useNoteVersion / useNoteSectionLock）
- [ ] **10.2** NoteTableEditor.vue 动态行视觉
- [ ] **10.3** 动态列视觉 + 拖动调宽 + 合并表头 + 冻结列
- [ ] **10.4** 「+ 添加明细行/列」按钮
- [ ] **10.5** 删除右键 + 公式栏多源选项 + 数据源 chip
- [ ] **10.6** 集团基线对话框 + 版本对比 + diff
- [ ] **10.7** 段落变量编辑器 + 实时预览
- [ ] **10.8** 协作锁可视化
- [ ] **10.9** AI 建议侧栏
- [ ] **10.10** 上年对比侧栏 + 章节版本树
- [ ] **10.11** vue-tsc + vitest 通过
- [ ] **10.12** Playwright 实测全链路

## Sprint 11：Word 导出（1.5 人天，D1-D12）

- [ ] **11.1** GTNoteDynamicRow / GTNoteDynamicCol 样式
- [ ] **11.2** 合并表头 docx 渲染
- [ ] **11.3** 「（不适用的项目请删除）」+ 「本期无此项业务」+ 空章节跳过
- [ ] **11.4** Jinja 段落 Word 输出
- [ ] **11.5** 合并附注独立章节集 + 抵销双列 Word 表
- [ ] **11.6** 27 项视觉断言（19+8 新增）
- [ ] **11.7** 多公司基线对比 PDF 工具
- [ ] **11.8** Sprint 11 验收

## Sprint 12：模板数据 + UAT（2 人天）

- [ ] **12.1** generate_note_template_bindings.py 三扩展（dynamic + wp_data + jinja）
- [ ] **12.2** 60+ 章节 _dynamic_regions 入库
- [ ] **12.3** 30+ 章节 wp_data binding 入库
- [ ] **12.4** 20+ 段落 Jinja 模板入库
- [ ] **12.5** 1 个集团基线 demo（首汽租车 → 重庆和平药房 应用基线）
- [ ] **12.6** UAT 全链路（首汽租车 + 重庆和平药房 + 1 个合并项目）
  - 行/列动态加删
  - wp_data 取数
  - fallback 链触发
  - 集团基线 apply
  - 段落变量预览
  - 合并附注衔接
  - 协作锁
  - AI 建议
  - 上年对比
  - Word 导出
- [ ] **12.7** UAT 报告 `docs/uat/note-full-enhancement-uat-{date}.md`

## 收尾

- [ ] **F-1** 全量回归（不破坏现有 173 章节）
- [ ] **F-2** memory.md 沉淀（11 维度铁律）
- [ ] **F-3** ADR-011~ADR-016 撰写 + INDEX.md
- [ ] **F-4** v2 backlog 写入：跨章节联动 / fork-merge / AI 全自动撰写

## CI 卡点汇总（14 项）

| ID | 描述 | Sprint |
|----|------|--------|
| CI-1 | _dynamic_regions idx/col_id 有效 | 1 |
| CI-2 | row_type=dynamic_* 在 region 内 | 1 |
| CI-3 | column_id 全表唯一 | 1 |
| CI-4 | REGION/WP 解析 | 3 |
| CI-5 | 动态删除合计 PBT | 2 |
| CI-6 | round-trip PBT | 12 |
| CI-7 | apply_baseline lineage | 5 |
| CI-8 | auto_trim v2 三级互斥 | 3 |
| CI-9 | fallback 链 ≤ 3 级 | 2 |
| CI-10 | _cell_provenance 必有 source | 2 |
| CI-11 | Jinja 模板必有变量声明 | 4 |
| CI-12 | 合并章节序号不冲突 | 6 |
| CI-13 | 锁释放必触发 | 7 |
| CI-14 | 版本树无环（DAG） | 9 |

## 任务依赖图

```
P-1/P-2/P-3/P-4 (外部)
        ↓
Sprint 1 (数据模型) → 2 (引擎) → 3 (公式+trim)
                              ├→ 4 (Jinja)
                              ├→ 5 (集团基线)
                              ├→ 6 (合并衔接) → 11 (Word)
                              ├→ 7 (锁)
                              ├→ 8 (AI)
                              ├→ 9 (版本图)
                              └→ 10 (前端) ─→ 12 (UAT) → F
```

## 风险登记册

| 风险 | 影响 | 缓解 |
|------|------|------|
| wp_data 跨循环格式不统一 | 取数失败 | 每循环 adapter，不通用化 |
| 集团基线误覆盖 | 数据丢失 | is_local_override + 预览 diff + 事务回滚 + 强制确认 |
| 动态列影响其他章节 | 表样不一致 | column_id 仅 per-table |
| auto_trim v2 误剔 | 输出不全 | feature flag + 三级互斥 + 手工恢复 |
| Jinja 模板缺变量 | 段落显示 undefined | strict mode + CI-11 + fallback 字符串 |
| 合并章节序号冲突 | 排序混乱 | uniq check + 段落级互斥 + CI-12 |
| 锁未释放 | 章节锁死 | with 退出 + 5min 超时 + 手动解锁 API |
| 版本树成环 | 死循环 | DAG 校验 CI-14 + 拒绝合并 |
| AI 建议错误 | 误导 | 仅"建议"不"自动应用"，用户必须确认 |
| 多源 fallback 慢 | 性能下降 | 并发解析 + 缓存 |
| 子公司清单频繁查询 | 合并附注卡顿 | Redis 缓存 60s |
| 22 人天工作量风险 | 延期 | 12 Sprint 拆分 + 各 Sprint 独立 commit + feature flag 渐进上线 |
