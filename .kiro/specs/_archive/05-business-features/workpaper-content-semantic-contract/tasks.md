# 实施计划：底稿内容语义契约

## 任务总览

- [x] 1. 定义语义类型
  - [x] 1.1 后端新增 `backend/app/schemas/workpaper_semantic_contract.py`，定义 `SheetContentType`、`FieldSourceContract`、`ProgramStatusContract`
  - [x] 1.2 前端新增 `audit-platform/frontend/src/types/workpaperSemanticContract.ts`，定义对应 TypeScript 类型
  - [x] 1.3 明确 `sheet_type` 与 `componentType` 分层注释
  - [x] 1.4 增加前后端类型一致性 fixture，确保 `SheetContentType`、`FieldSourceContract`、`ProgramStatusContract` 字段同步
  - [x] 1.5 单元测试：枚举序列化、非法枚举拒绝、前后端 fixture 一致
  - _Requirements: 1.1, 1.4, 2.1, 3.1_

- [x] 2. 扩展 render config
  - [x] 2.1 后端 `render-config` 返回 `sheet_type`
  - [x] 2.2 后端返回关键字段 `field_sources`
  - [x] 2.3 前端 `SheetRenderConfig` 接收可选 `sheet_type` 和来源契约
  - [x] 2.4 前端新增 `resolveSheetType(sheet)`
  - _Requirements: 1.2, 1.3, 5.1, 5.2_

- [x] 3. D1/D2 inventory 与口径对账前置 gate
  - [x] 3.1 输出 `docs/reference/workpaper-d1-d2-inventory.md`，列明 D1/D2 生产 schema、generated 草稿、sheet inventory、映射和 cross-ref 口径
  - [x] 3.2 对账 `wp_account_mapping.json`、`wp_template_metadata_seed.json`、`cross_wp_references.json`、附注 schema 中的 D1/D2 report_row 与 note_section
  - [x] 3.3 明确 `generated/D1.yaml`、`generated/D2*.yaml` 仅作 inventory，不直接作为生产 schema 真源
  - [x] 3.4 标记 D1/D2 的 report_row、note_section、cross_ref_note_code 冲突，未对账项输出 `mapping_status=pending_inventory_reconciliation`
  - [x] 3.5 测试：inventory 报告能区分 production schema、generated 草稿、registry 建议和已确认映射
  - _Requirements: 1.2, 2.2, 4.1_

- [x] 4. D1/D2 schema / registry 试点标注
  - [x] 4.1 D1 生产 schema / registry 标注控制台、审定表、明细、披露、调整、结论
  - [x] 4.2 D2 生产 schema / registry 标注审定表、明细、坏账/ECL、调整、分析程序、检查程序、C-D2-disclosure 披露、结论
  - [x] 4.3 将 D2 函证识别为外部卡片 `confirmation_summary`，不得误标为 D2-5 sheet
  - [x] 4.4 为审定表关键金额配置 `field_sources`
  - [x] 4.5 测试：schema 显式值优先于启发式
  - [x] 4.6 测试：`generated/*.yaml` 只能出现在 inventory/report，不得出现在 production registry 的 `schema_ref`
  - _Requirements: 1.2, 2.2, 4.1, 4.5, 4.6_

- [x] 5. 程序状态契约与接口
  - [x] 5.1 定义 `ProgramStatusContract` 字段、枚举和序列化格式
  - [x] 5.2 定义项目级程序状态存储接口，要求支持 applicable/status/evidence/conclusion/review_status
  - [x] 5.3 定义 not_applicable_reason、reviewer、reviewed_at 等留痕字段
  - [x] 5.4 明确实际持久化由 `workpaper-account-package-d1-d2-pilot` 的 `account_package_program_status` 落地
  - [x] 5.5 测试：契约字段完整性、状态枚举合法性和不适用理由必填
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 6. Schema lint/check
  - [x] 6.1 新增 `check_wp_semantic_schema.py`
  - [x] 6.2 检查 `sheet_type` 枚举合法性
  - [x] 6.3 检查 `field_sources.source_ref` 可解析
  - [x] 6.4 检查 generated schema 是否被误作为生产真源引用
  - [x] 6.5 检查缺失 `sheet_type` 的历史 schema 输出 warning 且不阻断渲染
  - [x] 6.6 输出 D1/D2 迁移报告
  - _Requirements: 4.2, 4.3, 4.4_

- [x] 7. 前端来源面板最小接入
  - [x] 7.1 在审定表关键字段提供来源入口
  - [x] 7.2 展示来源、编辑权限、人工确认、stale 策略
  - [x] 7.3 缺失来源时显示结构化 unknown，不报错
  - [x] 7.4 历史 schema 缺少 `sheet_type` 时，导航回退启发式且不破坏现有渲染
  - _Requirements: 2.2, 2.4, 5.2_

## P0-MVP

- [x] MVP-1. 类型定义和前后端枚举一致
- [x] MVP-2. D1/D2 inventory 与口径对账表完成
- [x] MVP-3. D1 至少 6 类 `sheet_type` 可被 render-config 或 registry 返回
- [x] MVP-4. D1 审定表关键金额字段有来源契约
- [x] MVP-5. 程序状态契约可被 D1/D2 工作包持久化服务消费
- [x] MVP-6. schema check 脚本可输出 warning 报告
- [x] MVP-7. D2 函证作为外部卡片、披露作为 `C-D2-disclosure` 的口径在 inventory 中明确

## 验收与回归

- [x] CI-1 pytest：语义 schema、render-config、程序状态契约通过
- [x] CI-2 pytest / Vitest：前后端语义类型 fixture 一致
- [x] CI-3 检查：D1/D2 inventory 标记 generated schema 非生产真源
- [x] CI-4 检查：production registry 的 `schema_ref` 不得引用 `generated/*.yaml`
- [x] CI-5 Vitest：`resolveSheetType` schema 优先、启发式回退通过
- [x] CI-6 手工 UAT：D1 导航按 `sheet_type` 分组
- [x] CI-7 手工 UAT：字段来源面板显示试算表来源和 stale 策略
- [x] CI-8 回归：未配置 `sheet_type` 的历史底稿仍可打开
