# 需求：多 sheet 底稿非核心 Sheet 切换到 OnlyOffice 渲染

## 背景

D0（收入循环函证）等多 sheet 底稿包含 11 个 tab，其中函证检查表、替代程序表、舞弊风险评价表等属于**表格型可编辑底稿**，当前走 GtGridSheet 只读网格渲染，存在以下问题：
- 不可编辑（只读）
- 格式丢失（合并单元格不完美、公式/数据验证全丢）
- 渲染慢（纯前端逐单元格渲染）

平台已有 OnlyOffice Docker 9.4.0（AGPL 自部署免费）+ WOPI 集成（`onlyoffice_callback_service.py`），交付模块已跑通。

## 需求

### R1 - HTML 白名单不变
以下 componentType 维持 HTML 渲染，**不改动**：
- `b-index`（底稿目录）
- `a-program-console`（程序表 D0A）
- `audit-sheet`（审定表）
- `c-note-table`（附注披露）
- `d-form-table`（调整分录/检查表结构化数据）

### R2 - 非核心 Sheet 切换到 OnlyOffice
多 sheet 底稿中，无后端 renderer 且不在 R1 白名单的 sheet，改为 OnlyOffice WOPI 渲染：
- 函证检查表（D0-1 ~ D0-4）
- 替代程序表（D0-5、D0-6）
- 邮件传真回函验证（D0-7）
- 舞弊风险评价表（D0-8）
- 函证差异检查表（示例）
- 以及其他循环（F0/G0/H0/K0/L0）的同类 sheet

### R3 - OnlyOffice 编辑器集成
- 后端生成 WOPI 配置（doc_key、download_url、callback_url、JWT token）
- 前端嵌入 OnlyOffice iframe（复用 `ONLYOFFICE_URL` 配置）
- 支持编辑+保存（callback status=2 时写回文件）
- 只读模式（底稿已完成/归档时）

### R4 - 模板文件路由
- OnlyOffice 打开的是底稿对应的 xlsx 模板文件（首次）或用户编辑后的文件（后续）
- 文件存储路径：`storage/projects/{project_id}/workpapers/{cycle}/{wp_code}_{sheet_name}.xlsx`
- 首次打开时从模板目录复制到项目存储

### R5 - 性能要求
- OnlyOffice iframe 加载 < 3s（本地 Docker 环境）
- 不阻塞其他 HTML sheet 的渲染
- Tab 切换时按需加载 OnlyOffice（非一次性全部打开）

### R6 - 降级策略
- OnlyOffice 容器不可用时，回退到 GtGridSheet 只读网格渲染
- 前端检测 OnlyOffice 健康状态，不可用时自动降级 + 提示

## 约束
- OnlyOffice JWT secret = `onlyoffice-dev-2026`（与 config.py + docker-compose + local.json 三处一致）
- 不影响现有交付模块的 OnlyOffice 使用（共享同一容器）
- 现有 1101 render-config 冒烟测试零回归
