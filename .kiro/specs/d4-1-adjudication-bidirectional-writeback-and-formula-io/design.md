# D4-1 设计

## Overview
D4-1 营业收入审定表的 HTML/OnlyOffice 双向回写、F-SHELL 公式治理与导入导出设计。核心是「运行时模板核定后的单一 descriptor + 内容表征统一经 ContentMutationService + 公式 preset/custom effective definition 单一真源」。

## Architecture

## 架构原则
D4-1 采用运行时模板核定后的单一 entry/sheet descriptor。HTML、OnlyOffice 和 checklist snapshot 都是内容表征，统一进入 `ContentMutationService`；`useWorkpaperSyncBridge` 只作为适配层，不另造协议。版本冲突走三方合并，失败 fail-closed。

## 决策
- **DEC1 模板先行**：finder/index/源 xlsx 核定前不写死同册、sheet、列号、行数或 UUID 列。
- **DEC2 公式统一**：F-SHELL 保存 `wp_formula` effective definition；表达式、refs、params 一起版本化。preset/custom/revert/Excel formula edit 都走同一入口。
- **DEC3 mask 边界**：OO formula mask 只禁止普通值 projection 覆盖，不禁止授权公式定义编辑。
- **DEC4 取数边界**：四表全部复用 `four_table` 的 scope/叶子聚合；缺码拒绝或人工，不回退猜测。
- **DEC5 发布边界**：D4-1 快照审定值与 TB 发布分离；模式切换只同步内容，不发布 TB。
- **DEC6 导入模型**：`D4-1-rows` + 六个 per-field 键为唯一新写模型，保留旧项目只读迁移但不再写旧键。

## Components and Interfaces

## Data Models

## 数据流
1. 模板核定生成 descriptor，记录真实 sheet、行身份、受管字段、formula mask 和 scope。
2. HTML 编辑写入 store projection；Excel 编辑通过 bridge 提交 projection；两者均带版本交给 ContentMutationService 三方合并，再 durable callback 更新 snapshot。
3. 公式 UI 从 F-SHELL 取得 effective definition；后端权威校验和执行，前端只做同定义预览。纯取数读取 render snapshot，表内计算按定义求值。
4. 导入先校验 rowId/accountCode/scope，再原子写清单与六字段；派生列永不接受文件值。
5. “确认审定”读取 D4-1 snapshot，差异确认后调用既有人工 TB 发布服务；该调用不挂在 mode switch、flush 或 reload 回调。

## 组件职责
- 后端：模板 descriptor、four_table scope、导入导出、公式 effective definition、ContentMutationService adapter、真库快照。
- 前端：D4-1 rows UI、F-SHELL 宿主、tooltip/source、只读与冲突态、人工发布确认。
- 守卫：真跑 projection/merge/公式执行/round-trip/浏览器 DOM，不以字符串存在替代行为。

## Error Handling
写入失败/行身份缺失或重复/公式不支持/缺码/求值失败一律 fail-closed：保留原内容、标记 failed/blocked、展示中文错误，绝不 markSynced、绝不 null 转 0、绝不臆测科目。

## Testing Strategy

## 验证策略
使用模板实测证据锁定 descriptor；变异测试删除 scope 校验、改回旧键、绕开 F-SHELL、改为 last-write-wins、将发布挂到切换入口，均必须打红。验证缺码拒绝、D4-1 快照来源、OO formula mask 字节稳定、effective definition hash、任务 DAG 唯一性。

## Correctness Properties
### Property 1: 内容表征统一与投影安全
**Validates: Requirements 1.1, 1.2, 1.3**
所有写操作共享 descriptor、版本和 ContentMutationService，普通投影不覆盖公式，冲突显式保留。
### Property 2: 四表取数与动态行键稳定
**Validates: Requirements 2.1, 2.2, 2.3**
D4-1 数据读取经过四表 scope/叶子聚合，dynamic rows 键和字段保持稳定。
### Property 3: TB 发布人工触发且来源可追溯
**Validates: Requirements 2.4, 3.2**
TB 发布只能由人工确认触发且读取 D4-1 快照；公式定义版本/hash 可追溯。
### Property 4: 导入缺码拒绝与 round-trip 一致
**Validates: Requirements 3.3, 4.1, 4.2**
导入缺码拒绝，完整字段 round-trip，派生列由定义重算。
