# Requirements Document

## Introduction

代码库中存在多处"同一事实多处定义"的问题——函证枚举两份前端文件已漂移、公式 parse 未缓存、工具函数重复定义、公式 token 正则三处维护、componentType 白名单双重维护。本 spec 批量清理这些单一真源缺失问题，每项均为低风险小改动。

覆盖条目：§6.2/§4.6/§2.5/§2.9/§9.2/§2.15。

## Glossary

- **单一真源（Single Source of Truth）**：同一事实在代码库中只有一处规范定义，其余处通过 import 复用
- **lru_cache**：Python 标准库 LRU 缓存装饰器

## Requirements

### Requirement 1: 合并函证枚举定义（§6.2）

**User Story:** As a 前端开发者, I want 函证枚举只有一份定义, so that 不因 import 错文件导致 key 拼写不一致。

#### Acceptance Criteria

1. WHEN 删除 `confirmationEnums.ts` 后 THEN 所有引用收口到 `confirmationDicts.ts`（11 类统一版）
2. WHEN 前端编译 THEN 无 TypeScript 错误（所有 import 路径已更新）

### Requirement 2: 为 parse_to_ast 加 lru_cache（§4.6）

**User Story:** As a 报表生成场景, I want 重复公式不重新 parse, so that 性能提升。

#### Acceptance Criteria

1. WHEN 同一公式字符串多次调用 `parse_to_ast` THEN 第 2 次起从缓存返回 AST（不重复 tokenize+parse）
2. WHEN 不同公式调用 THEN 各自正确 parse（缓存 key = formula 字符串）
3. WHEN 缓存大小超 2048 THEN 最旧条目 LRU 淘汰

### Requirement 3: 提取共享 _has_grid_cells（§2.5）

**User Story:** As a 后端开发者, I want 重复函数只写一份, so that 改一处不漏改。

#### Acceptance Criteria

1. WHEN `_univer_grid.py` 和 `_c_note.py` 的 `_has_grid_cells` 函数 THEN 改为从共享 `_utils.py` 导入
2. WHEN 行为不变 THEN 既有测试全部通过

### Requirement 4: 删除 build_preparation_info 重复（§2.9）

**User Story:** As a 后端开发者, I want 编制信息构建只有一处, so that 逻辑修改不遗漏。

#### Acceptance Criteria

1. WHEN `wp_render_config.py` 的 `_build_preparation_info` 被删除 THEN 所有调用改为 `wp_preparation_info_service.build_preparation_info`
2. WHEN 行为不变 THEN 既有测试全部通过

### Requirement 5: 公式 token 正则单一来源（§9.2）

**User Story:** As a 公式模块维护者, I want TB/SUM_TB/ROW 等正则只定义一处, so that 变更不需三处同步。

#### Acceptance Criteria

1. WHEN 新建 `formula_grammar.py` 集中定义所有函数名+正则+arity THEN `report_engine.py`/`formula_engine.py`/`address_registry.py` 改为 import 复用
2. WHEN 函数签名变更（如新增参数） THEN 只改 `formula_grammar.py` 一处

### Requirement 6: componentType 白名单去重（§2.15）

**User Story:** As a 前端开发者, I want componentType HTML 白名单只在 htmlRendererRegistry 定义一份, so that 新增类型不漏改 composable。

#### Acceptance Criteria

1. WHEN `useEditorMode.ts` 的 `HTML_COMPONENT_TYPES` 被删除 THEN 改为直接引用 `htmlRendererRegistry` 的 `HTML_COMPONENT_TYPE_SET`
2. WHEN 新增 componentType THEN 只改 registry 一处
