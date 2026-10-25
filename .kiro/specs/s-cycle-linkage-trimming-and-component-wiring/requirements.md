# S 类底稿联动、裁剪与组件接线 — 需求

> spec: s-cycle-linkage-trimming-and-component-wiring
> 权威证据: `.agents/tasks/s-cycle-investigation/findings.md`（六维打分表）
> 评审修订: `.agents/tasks/s-cycle-investigation/s-cycle-spec-review.md`（MEDIUM-1~3 / NIT-1~2）

## 摘要

S 类（专项/IPO/再融资）底稿在组件实现层面三种状态并存：10 个单项 + 4 个 bundle 有真实现，
但 S1/S8/S9/S10/S17 的 12 个子 sheet 组件已写未接线（孤儿），S2/S11/S16 纯走通用兜底。
全类 92 条 `linked_workpapers` 为 None、无事件订阅、裁剪执行链声明与执行双向断裂。
本 spec 分三阶段修复：P0 打通裁剪 + 孤儿接线，P1 关联联动，P2 风险导向 + 委派展示。

## P0 — 裁剪执行链 + 孤儿接线

### R-P0-1 applicable_when 从声明到执行全链路生效
- **已有**：映射表 S32~S35 子码声明了 `applicable_when: {business_category: [...]}`（findings §3.3）
- **缺口**：`match_workpapers` 不识别 `applicable_when`（dict），只处理 `applies_when`（str）；
  `chain_orchestrator` 的 SELECT 不含 `Project.business_category`
- **要做**：后端生成匹配器增加 `applicable_when` dict 全键遍历（business_category / industry 等，
  键间 OR，本次实现 business_category + industry 两种键）；调用方传入项目分类
- **验收**：IPO 项目自动生成 S32~S35、普通年审不生成

### R-P0-2 前端 applicable_when 裁剪覆盖全渲染路径
- **已有**：`useAProgramData.isNotApplicable` 只认 `'consolidated'`（findings §3.3）
- **缺口**：不解析 `business_category` dict；S32~S35 走 bundle 专属组件不经 GtAProgramConsole；
  **S32/S33/S34/S35 父码的 `applicable_when=None`**（只有子码有），GtWpRenderer 按父码查会漏过
- **要做**：① 扩展 isNotApplicable 解析 business_category dict（通用组件路径）；
  ② GtWpRenderer 层增加 applicable_when 拦截——组件分发前检查适用性，不匹配渲染覆盖层
  （一次到位覆盖 bundle + 通用组件）；③ `_WP_APPLICABLE_WHEN` 加载时须**从子码向上聚合到
  父码**：bundle 父码自身 applicable_when=None 但全部子码有相同 business_category 限制时继承之
  （或直接在 `wp_account_mapping.json` 给 S32/S33/S34/S35 父码补上 applicable_when——声明层缺漏）
- **验收**：普通年审项目打开 S32 系列底稿时显示「不适用」覆盖层
- **边界声明**：本 spec 的裁剪覆盖底稿生成 + 底稿渲染两个入口；底稿列表页的适用性标记属于
  范围外（列表页展示全部已生成底稿，由底稿渲染层做最终拦截）

### R-P0-3 收敛 IPO 可见性判定为统一工具函数
- **已有**：D4 `isIpoGroupVisible` / F2 `IPO_CATEGORIES` 等 ≥4 处分散实现
- **要做**：抽取统一 `isIpoProject(ctx)` 工具函数，各消费方改为调用
- **验收**：全仓 IPO/business_category 可见性判定收敛到单一来源

### R-P0-4 12 个 s-checklist 孤儿组件接线到渲染层
- **已有**：`s-checklist/` 目录 12 个 .vue，全仓无活动代码引用（findings §2.4）
- **缺口**：7 个已在 overrides 有独立 wp_code；5 个是内部 sheet 无独立 wp_code
- **要做**：组 A 改 overrides componentType；组 B 通过 per-sheet override 机制路由；
  全部 12 个在 htmlRendererRegistry 注册
- **验收**：S1/S8/S9/S10/S17 底稿子检查表 sheet 使用专属组件渲染

### R-P0-5 S 段侧边栏路由
- **已有**：`resolveProcedureSheetKey.ts` 有 D~N 段路由，无 S 段
- **要做**：增加 S 段路由；S16/S11 显式 fallback 到 e1a（在 S1 之前，避免 startsWith 误匹配）；
  **S8 需显式路由**（S8AdjudicationSheet 从 render-config 取数据，需要侧边栏数据源入口）；
  S2/S3/S4/S5/S6/S9/S21 无专属程序表数据源，落默认 e1a
- **验收**：有专属组件的 S 底稿侧边栏状态正确显示；S11/S16 落 e1a 不被 S1 捕获

## P1 — 关联联动

### R-P1-1 linked_workpapers 补齐关键 S 底稿关联声明
- **已有**：S 类 92 条 `linked_workpapers` 全 None（findings §3.1）
- **要做**：S20↔D4、S15↔D4/M2、S17↔K12/K13、S6↔K1、S33-5↔D4/F5
- **消费方**：需确认 D~N 循环 linked_workpapers 的现有前端消费组件（grep `linked_workpapers`
  找到消费路径），确保 S 类底稿也走同一展示路径
- **验收**：关键 S 底稿在底稿面板展示关联底稿链接

### R-P1-2 补缺失取数 resolver
- **已有**：11 个 S 相关 resolver（评审 G7 现算校正）
- **缺口**：S6 关联方余额、S33-5 收入毛利、S14 减值估计
- **要做**：补 3 个 resolver；签名统一 `async (db, project_id, year, **kwargs)`；
  **同时在对应 render-schema YAML 中补 auto_data_source 声明**（否则 resolver 注册了无人调用）
- **铁律**：S 类只取数不回写 trial_balance

### R-P1-3 S34 公式引擎完整化
- **已有**：`useS34FormulaEngine` 仅覆盖 S34-16-1/S34-16-2（findings §2.5）
- **要做**：逐表补 FORMULA 定义，复用现有工厂函数
- **验收**：12 张 hasSubTable 子表全部有公式自动计算

### R-P1-4 S34/S35 跨引用展示关联数值
- **已有**：`useS34CrossRef` / `useS35CrossRef` 仅导航跳转
- **要做**：chip hover 时展示关联底稿只读审定数/TB 数
- **验收**：S34 内跨引用 chip hover 显示目标底稿关键数值

## P2 — 风险导向 + 委派

### R-P2-1 风险评估驱动 S 清单适用性
- **已有**：S34 清单适用性仅看底稿是否生成（findings §3.2）
- **要做**：读取 `risk_assessments` 表结论，为 S32~S34 生成适用性建议
- **验收**：高舞弊风险项目自动标记 S32 系列「建议适用」

### R-P2-2 S34 checklist 适用性升级
- **要做**：结合风险评估 + 底稿生成状态双重判定
- **验收**：风险指向事项即使底稿未生成也标「建议生成」

### R-P2-3 bundle 内按 tab 展示负责人
- **已有**：委派仅循环级（findings §3.4）
- **要做**：bundle UI 层按 `wp_index.assigned_to` 展示各 tab 负责人
- **验收**：S34 bundle 各 tab 标签显示负责人姓名

## 验收标准

- AC-1: IPO 项目创建后自动生成 S32~S35 系列底稿
- AC-2: 普通年审项目不生成 S32~S35；已有的在 GtWpRenderer 层显示「不适用」覆盖层
- AC-3: S1/S8/S9/S10/S17 底稿子 sheet 使用专属组件而非通用兜底
- AC-4: S20/S15/S17/S6/S33-5 底稿面板展示关联底稿链接
- AC-5: S34 全部 12 张 hasSubTable 子表公式自动计算
- AC-6: S 类 resolver 只读不回写 TB
- AC-7: 全仓 IPO 可见性判定收敛到 ≤2 个函数
- AC-8: S 段路由 S11/S16 显式 fallback e1a（不被 startsWith('S1') 误捕获）

## 范围外

- S 类底稿 trial_balance 回写（归档 design 已确认不做）
- bundle 子底稿独立 componentType 拆分（保持通用程序表中控台）
- S12A/S33-REV/S34-1-1 docx 模板渲染（已走 word-template）
- S17 .xls 旧格式迁移（保持 openpyxl 兼容读取）
- assignment_service 底稿级委派粒度改造（仅 UI 层展示）
- 底稿列表页/目录树的适用性标记（裁剪覆盖底稿生成+渲染两个入口,列表页属后续）
