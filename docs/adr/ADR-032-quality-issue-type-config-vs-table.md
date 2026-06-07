# ADR-032: 质量问题类型用配置文件而非新表

## 状态

已接受 (2026-06-07)

## 上下文

平台需要建立质量问题类型库，支持复核/QC 问题归类、重复问题统计和培训材料导出。
需要决定问题类型数据的存储方案：

### 方案 A：配置文件（JSON）

- 优点：
  - 零 migration 成本，无 schema drift 风险
  - 版本管理天然由 git 跟踪
  - 修改无需重启服务（hot-reload 友好）
  - 适合相对稳定、变更频率低的配置数据
  - 与现有 `gt_template_library.json` 模式一致
- 缺点：
  - 不支持运行时用户自定义新类型（需代码发版）
  - 多实例部署时配置同步依赖部署流程

### 方案 B：新建 DB 表 `quality_issue_types`

- 优点：
  - 支持运行时 CRUD（管理员可在线新增类型）
  - 与问题记录表 FK 关联，RI 约束强
  - 支持统计查询（GROUP BY type_code）
- 缺点：
  - 新增 migration + ORM + schema
  - 初始数据需要 seed
  - 对于相对固定的审计质量问题类型，过度设计

### 方案 C：混合方案（配置为主 + DB 统计引用）

- 配置文件定义类型 code 和元数据
- 问题记录中存 `issue_type_code` 字段（VARCHAR）引用配置中的 code
- 统计时按 code 聚合，类型元数据从配置 JSON 查
- 优点：兼顾稳定性和统计能力，无新表

## 决策

**选择方案 C：混合方案（配置 JSON + 问题记录引用 code）**

理由：
1. 审计质量问题类型是相对固定的分类法（程序遗漏、证据不足等），不需要频繁在线修改
2. 与项目现有模式一致（`gt_template_library.json`、`wp_account_mapping.json`）
3. 无需新建 DB 表，避免 migration/ORM 维护成本
4. 问题记录中的 `issue_type_code` 字段足够支持统计和归类
5. 培训材料导出基于配置 JSON 读取即可

## 实现

- 配置文件：`backend/data/quality_issue_types.json`
- Service：`backend/app/services/quality_issue_type_service.py`
  - `get_all_types()` → 读取配置
  - `classify_issue(issue_id, type_code)` → 给问题归类
  - `count_by_type(project_id)` → 统计重复问题
  - `export_training_candidates(project_id)` → 导出培训材料候选

## 后果

- 不需要 V061 migration（无新表）
- 新增类型需修改 JSON 配置并重新部署
- 未来若需运行时动态增删类型，可再评估迁移到 DB 表（成本低：仅需一张表+seed）
