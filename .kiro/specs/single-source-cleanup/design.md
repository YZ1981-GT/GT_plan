# Design Document

## Overview

6 项独立的"去重/收口"改动，每项 5~30 行，互不依赖，可并行实施。无架构风险、无 DB 迁移、无前后端契约变更（除 §6.2 前端文件合并）。

## Architecture

Pure refactoring — no architectural changes. 6 项独立改动均为同层级代码收口，不改变模块边界或数据流。

## Components and Interfaces

- **`backend/app/services/formula_grammar.py`** — 新建，集中定义所有公式 token 正则 + 函数名 + arity
- **`backend/app/routers/wp_render_strategies/_utils.py`** — 新建，共享 `_has_grid_cells` 工具函数

## Data Models

N/A — 纯重构，无数据库变更。

## Changes

### 1. 合并函证枚举（§6.2）

- 删除 `audit-platform/frontend/src/components/workpaper/confirmation/confirmationEnums.ts`
- 全局搜索 `confirmationEnums` → 替换为 `confirmationDicts` 的对应导出
- `MATCH_STATUS` key（旧版独有）如仍被引用则迁移到 `confirmationDicts.ts` 或确认已废弃删除

### 2. parse_to_ast 加 lru_cache（§4.6）

```python
# formula_engine.py
@functools.lru_cache(maxsize=2048)
def parse_to_ast(formula: str) -> Any:
    ...
```
- AST 节点为 frozen dataclass / namedtuple → hashable、immutable → 可安全缓存
- 注意：`_tokenize` 返回列表不可 hash，cache 应加在 `parse_to_ast` 而非 `_tokenize`

### 3. _has_grid_cells 共享（§2.5）

- 新建 `backend/app/routers/wp_render_strategies/_utils.py`
- 移入 `_has_grid_cells` 函数
- `_univer_grid.py` 和 `_c_note.py` 改为 `from ._utils import _has_grid_cells`

### 4. build_preparation_info 去重（§2.9）

- 删除 `wp_render_config.py` 中的 `_build_preparation_info`（~L355）
- 其调用处改为 `from app.services.wp_preparation_info_service import build_preparation_info`

### 5. formula_grammar.py（§9.2）

- 新建 `backend/app/services/formula_grammar.py`
- 从 `formula_engine.py`/`report_engine.py`/`address_registry.py` 提取所有 `_TB_PATTERN`/`_SUM_TB_PATTERN`/... 正则 + 函数名 + arity 集中定义
- 三方改为 `from app.services.formula_grammar import TB_PATTERN, ...`

### 6. componentType 白名单去重（§2.15）

- `useEditorMode.ts` 删除内部 `HTML_COMPONENT_TYPES` Set
- 改为 `import { HTML_COMPONENT_TYPE_SET } from '../components/workpaper/htmlRendererRegistry'`
- 别名保持（`const HTML_COMPONENT_TYPES = HTML_COMPONENT_TYPE_SET`）以减少下游改动

## Correctness Properties

Property 1: 每项改动后既有测试全部通过（`pytest` + `vitest` + `tsc --noEmit`），证明行为无变更。

Property 2: 无新的运行时行为变更——所有改动仅为 import 路径变更或代码位置移动。

## Testing Strategy

- 后端：`python -m pytest backend/tests/ -x` 全量通过
- 前端：`npx vitest --run` + `npx tsc --noEmit` 全量通过
- 无需新测试（纯重构，行为不变）
