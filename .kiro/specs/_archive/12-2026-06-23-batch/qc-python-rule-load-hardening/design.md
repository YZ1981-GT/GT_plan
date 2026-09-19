# QC Python Rule Load Hardening — Bugfix Design

## Overview

`_load_class_from_dotted_path` 在 `qc_rule_executor.py` 中通过 `importlib.import_module` 加载任意 dotted path 类，无前缀限制。同时 `POST /api/qc/rules` 和 `PATCH /api/qc/rules/{id}` 允许 `qc` 角色（非 admin）创建/编辑 `expression_type='python'` 规则，等价于受限 RCE。

修复策略：(1) 在 `_load_class_from_dotted_path` 添加前缀白名单校验；(2) 在 router 层对 python 类型规则的创建/编辑限定 admin 角色；(3) 清除"沙箱"误导性注释。

## Glossary

- **Bug_Condition (C)**: 非法类路径被加载，或非 admin 用户创建/编辑 python 类型规则
- **Property (P)**: 非白名单路径 → `ImportError`；非 admin 用户 python 类型 → 403
- **Preservation**: 既有 20 条规则（QC-01~QC-28，路径 `app.services.qc_engine.*`）正常执行；jsonpath 规则创建不受限；超时行为不变
- **`_load_class_from_dotted_path`**: `qc_rule_executor.py` ~L71，从 dotted path 加载类的函数
- **`_ALLOWED_RULE_PREFIXES`**: 新增模块常量，限定可加载类的包路径前缀
- **`execute_python_rule`**: `qc_rule_executor.py` ~L100，执行 python 类型规则的入口函数
- **`require_role`**: `app/deps.py` 提供的 FastAPI 角色校验依赖

## Bug Details

### Bug Condition

当非 admin 用户创建 `expression_type='python'` 规则，或 dotted path 不在允许前缀列表内时，系统无任何防护直接执行加载。当前 router `require_role(["qc", "admin"])` 对 expression_type 无差异化校验。

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input = (user_role, expression_type, dotted_path, action)
  OUTPUT: boolean

  // 条件 a: 非 admin 创建/编辑 python 类型规则
  cond_a := (action IN ['create', 'update']
             AND expression_type = 'python'
             AND user_role != 'admin')

  // 条件 b: dotted_path 不以任何允许前缀开头
  cond_b := (expression_type = 'python'
             AND NOT any(dotted_path.startswith(p) FOR p IN _ALLOWED_RULE_PREFIXES))

  RETURN cond_a OR cond_b
END FUNCTION
```

### Examples

- 用户 role='qc' POST `expression_type='python', expression='app.services.data_lifecycle_service.DataLifecycleService'` → 当前：201 成功；期望：403
- `_load_class_from_dotted_path('app.services.import_job_runner.ImportJobRunner')` → 当前：成功加载；期望：`ImportError("Disallowed rule class path: ...")`
- `_load_class_from_dotted_path('app.services.qc_engine.ConclusionNotEmptyRule')` → 当前：成功；期望：继续成功（白名单内）
- 用户 role='admin' POST `expression_type='python', expression='app.services.qc_rules.CustomRule'` → 当前：成功；期望：继续成功

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- 既有 20 条内置 QC 规则（路径 `app.services.qc_engine.*` / `app.services.qc_rules.*`）正常加载执行
- `expression_type='jsonpath'` 规则的创建/编辑/执行不受任何限制
- `expression_type='sql'` / `'regex'` 继续抛 `NotImplementedError`
- `execute_python_rule` 超时行为不变（`RuleExecutionResult(passed=False, error="timed out")`)
- admin 用户创建/编辑 python 类型规则且路径合法时继续成功
- 规则列表 / 详情 / 删除 / dry-run 端点行为不变

**Scope:**
所有不涉及 `expression_type='python'` 的操作完全不受影响。涉及 python 类型但用户为 admin 且路径在白名单内的操作也不受影响。

## Hypothesized Root Cause

1. **`_load_class_from_dotted_path` 无路径校验**: 函数仅校验格式（`rsplit(".", 1)` 是否得到两部分），不校验路径是否在允许范围内。任何 `module.ClassName` 格式的字符串都可触发 `importlib.import_module`。

2. **Router 角色校验粒度不足**: `create_rule` 和 `update_rule` 的 `require_role(["qc", "admin"])` 对所有 expression_type 一视同仁。python 类型本质上是代码执行，应限定 admin-only，但当前 qc 角色也可操作。

3. **"沙箱"误导**: 注释和变量命名暗示有安全沙箱（如 `# 沙箱 timeout=10s`），但实际仅 `asyncio.wait_for` 超时保护，无进程隔离/权限降级。

## Correctness Properties

Property 1: Bug Condition - Disallowed Path Rejected

_For any_ input where `dotted_path` does NOT start with any prefix in `_ALLOWED_RULE_PREFIXES`, the fixed `_load_class_from_dotted_path` function SHALL raise `ImportError` containing "Disallowed rule class path" without invoking `importlib.import_module`.

**Validates: Requirements 2.1**

Property 2: Bug Condition - Non-Admin Python Rule Creation Rejected

_For any_ API request where `user_role != 'admin'` AND `expression_type = 'python'` AND action is create or update, the fixed endpoint SHALL return HTTP 403 without creating/modifying the rule.

**Validates: Requirements 2.2**

Property 3: Preservation - Allowed Path Loads Successfully

_For any_ input where `dotted_path` starts with a prefix in `_ALLOWED_RULE_PREFIXES` AND the module/class exists, the fixed `_load_class_from_dotted_path` SHALL produce the same result as the original function (class successfully loaded).

**Validates: Requirements 3.1, 3.3**

Property 4: Preservation - JsonPath Rules Unaffected

_For any_ API request with `expression_type = 'jsonpath'`, the fixed endpoints SHALL produce the same behavior as the original code regardless of user role, preserving unrestricted access for jsonpath rule CRUD.

**Validates: Requirements 3.2**

## Fix Implementation

### Changes Required

**File**: `backend/app/services/qc_rule_executor.py`

**Function**: `_load_class_from_dotted_path`

**Specific Changes**:
1. **新增模块常量 `_ALLOWED_RULE_PREFIXES`**: `("app.services.qc_engine.", "app.services.qc_rules.")` — 定义可加载类的包路径白名单
2. **前缀校验逻辑**: 在 `importlib.import_module` 调用前增加 `if not any(dotted_path.startswith(p) for p in _ALLOWED_RULE_PREFIXES): raise ImportError(...)`
3. **注释清理**: 将 `# 沙箱 timeout=10s` 等替换为 `# timeout-only execution (NOT a security sandbox)`；模块 docstring 同步修改

**File**: `backend/app/routers/qc_rules.py`

**Function**: `create_rule`, `update_rule`

**Specific Changes**:
4. **create_rule 端点**: 在 service 调用前检查 `if body.expression_type == 'python' and current_user.role != 'admin': raise HTTPException(403, "Only admin can create python-type rules")`
5. **update_rule 端点**: 同理，当 `data` 包含 `expression_type='python'` 或规则原本就是 python 类型且被编辑时，校验 `current_user.role == 'admin'`

## Testing Strategy

### Validation Approach

两阶段验证：先在未修复代码上确认 bug 存在（counterexample），再验证修复后正确性 + 无回归。

### Exploratory Bug Condition Checking

**Goal**: 在未修复代码上确认 `_load_class_from_dotted_path` 可加载任意路径、非 admin 可创建 python 规则。

**Test Cases**:
1. **任意路径加载**: 调用 `_load_class_from_dotted_path('app.services.data_lifecycle_service.DataLifecycleService')` 观察成功加载（应在修复后失败）
2. **非 admin 创建 python 规则**: 模拟 role='qc' 用户 POST python 类型规则（应在修复后返回 403）
3. **非 admin 编辑为 python 类型**: 模拟 role='qc' 用户 PATCH 规则 expression_type→python（应在修复后返回 403）

**Expected Counterexamples**:
- `_load_class_from_dotted_path` 对任意 dotted path 直接返回类对象
- Router 对 qc 角色创建 python 规则返回 201（而非 403）

### Fix Checking

**Goal**: 验证修复后，所有 bug condition 输入被正确拒绝。

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  IF input involves disallowed path THEN
    ASSERT _load_class_from_dotted_path(input.dotted_path) RAISES ImportError
    ASSERT "Disallowed" IN error_message
  END IF
  IF input involves non-admin + python type THEN
    ASSERT create_rule(input).status = 403
  END IF
END FOR
```

### Preservation Checking

**Goal**: 验证修复后，合法操作行为不变。

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT _load_class_from_dotted_path_original(input) = _load_class_from_dotted_path_fixed(input)
  ASSERT create_rule_original(input) = create_rule_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing（Hypothesis）生成随机 dotted path 字符串，验证白名单内的路径行为不变、白名单外的路径被拒。

### Unit Tests

- `_load_class_from_dotted_path` 白名单内路径（`app.services.qc_engine.X`）→ 正常加载
- `_load_class_from_dotted_path` 白名单外路径 → `ImportError`
- `_load_class_from_dotted_path` 格式非法路径（无 `.`）→ 仍然 `ImportError`（原有行为）
- `create_rule` endpoint role='qc' + expression_type='python' → 403
- `create_rule` endpoint role='admin' + expression_type='python' → 201
- `create_rule` endpoint role='qc' + expression_type='jsonpath' → 201（不受限）
- `update_rule` endpoint role='qc' 将 expression_type 改为 python → 403
- `update_rule` endpoint role='admin' 将 expression_type 改为 python → 200

### Property-Based Tests

- 生成随机 dotted path 字符串（`st.text` + `st.from_regex`），断言仅白名单前缀开头的路径不抛异常
- 生成随机 `(role, expression_type)` 组合，断言 role!='admin' + expression_type='python' 必返回 403
- 生成白名单内路径，断言与原始函数行为一致（preservation）

### Integration Tests

- 全流程：admin 创建 python 规则 → 规则执行 → findings 正确返回
- 全流程：qc 用户尝试创建 python 规则 → 403 → 数据库无新记录
- 既有 QC-01~QC-28 规则 dry-run 不受影响
