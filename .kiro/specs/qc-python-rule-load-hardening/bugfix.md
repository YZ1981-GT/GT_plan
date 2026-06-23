# Bugfix Requirements Document

## Introduction

QC 规则执行器（`qc_rule_executor.py`）对 `expression_type='python'` 的规则通过 `importlib.import_module` 按 dotted path **加载代码库中任意类**并调用 `.check(context)`。所谓"沙箱"**仅是 `asyncio.wait_for(timeout=10s)` 超时保护**——被加载代码对 DB / 文件系统 / 网络无任何限制。

若非 admin 用户可通过 `create_rule` API 创建 `expression_type='python'` 的规则并指定任意 dotted path，等价于"在进程内触发任意类的实例化 + .check() 调用"（受限 RCE 面）——虽不能注入新代码，但可调用有副作用的既有类（如 `DataLifecycleService`、`ImportJobRunner`）。

已通过代码阅读核实（docs/architecture-improvement-proposals.md §11.1）：`_load_class_from_dotted_path` 无路径前缀限制；`qc_rule_definition_service.create_rule` 无 expression_type 维度的角色限制。

受影响代码：
- `backend/app/services/qc_rule_executor.py`：`_load_class_from_dotted_path`（~L71）、`execute_python_rule`（~L100）
- `backend/app/services/qc_rule_definition_service.py`：`create_rule`、`update_rule`
- `backend/app/routers/qc_rules.py`（创建/编辑规则端点的角色校验）

### 边界声明

**纳入**：dotted-path 前缀白名单；python 类型规则创建/编辑限 admin；注释/文档去"沙箱"误导。

**排除**：真正的进程隔离沙箱（子进程 + seccomp）——成本过高，本 bugfix 做到前缀白名单 + admin 限制即可将风险收到可接受范围。sql/regex expression_type 半实现问题（§11.2）不在本 spec。

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN 用户（任意角色）通过 `POST /api/qc/rules` 创建 QC 规则且 `expression_type='python'` + `expression='app.services.data_lifecycle_service.DataLifecycleService'` THEN the system 创建成功且执行时加载该类并调用 `.check(context)`，可能触发非预期副作用（如归档/删除操作）

1.2 WHEN `_load_class_from_dotted_path` 收到 dotted path 如 `app.services.import_job_runner.ImportJobRunner` THEN the system 无任何限制地 `importlib.import_module('app.services.import_job_runner')` 并 `getattr(module, 'ImportJobRunner')` 返回该类——可加载代码库内 5000+ 任意类

1.3 WHEN QC 规则执行时被加载的类在 `.check()` 或 `__init__()` 中执行了写操作（如 DB update/insert/delete，文件操作，网络请求） THEN the system 不做任何隔离，操作直接在主进程的 DB session 上执行

1.4 WHEN 注释写"沙箱 timeout=10s" THEN 开发者可能误以为有安全隔离，实际仅有超时保护

### Expected Behavior (Correct)

2.1 WHEN `_load_class_from_dotted_path` 收到 dotted path THEN the system SHALL 校验 path 必须以 `_ALLOWED_RULE_PREFIXES` 中某一前缀开头（如 `app.services.qc_engine.`、`app.services.qc_rules.`），不匹配则 raise `ImportError("Disallowed rule class path: ...")`

2.2 WHEN 用户（非 admin）通过 API 创建/编辑 QC 规则且 `expression_type='python'` THEN the system SHALL 返回 403，仅 admin 角色可创建/编辑 python 类型规则

2.3 WHEN 用户（任意角色）创建 `expression_type='jsonpath'` 规则 THEN the system SHALL CONTINUE TO 允许（jsonpath 为只读安全操作，不受本限制影响）

2.4 WHEN `_load_class_from_dotted_path` 加载的类不符合 `QCRule` 协议（无 `check` 方法或签名不匹配） THEN the system SHALL raise 明确错误（已有 `isinstance` 检查或 `getattr` 保护即可，确认无遗漏）

2.5 WHEN 注释/文档提及执行模式 THEN the system SHALL 使用 "timeout-only execution (NOT a security sandbox)" 替代 "沙箱" 措辞

### Unchanged Behavior (Regression Prevention)

3.1 WHEN 既有 20 条内置 QC 规则（QC-01~QC-28，path 均为 `app.services.qc_engine.*`）被 QCEngine 执行 THEN the system SHALL CONTINUE TO 正常加载、实例化、执行 `.check(context)` 并返回 findings

3.2 WHEN `expression_type='jsonpath'` 或 `scope='audit_log'` 规则执行 THEN the system SHALL CONTINUE TO 走原有路径不受前缀白名单影响

3.3 WHEN admin 用户创建 python 类型规则且 path 在白名单内 THEN the system SHALL CONTINUE TO 创建成功并可正常执行

3.4 WHEN `expression_type='sql'` / `'regex'` 执行 THEN the system SHALL CONTINUE TO 抛 `NotImplementedError`（未实现行为不变）

3.5 WHEN `execute_python_rule` 超时 THEN the system SHALL CONTINUE TO 返回 `RuleExecutionResult(passed=False, error="timed out")`（超时行为不变）

## Bug Condition Derivation

```pascal
FUNCTION isBugCondition_11_1(X)
  INPUT: X = (user_role, expression_type, dotted_path)
  OUTPUT: boolean

  // (a) 非 admin 创建 python 类型规则，或
  // (b) dotted_path 不在白名单前缀内
  RETURN (expression_type = 'python' AND user_role != 'admin')
      OR (expression_type = 'python' AND NOT starts_with_any(dotted_path, ALLOWED_PREFIXES))
END FUNCTION
```

```pascal
// Fix Checking — 非法路径 / 非 admin 用户被拒
FOR ALL X WHERE isBugCondition_11_1(X) DO
  IF X.user_role != 'admin' AND X.expression_type = 'python' THEN
    ASSERT create_rule'(X).status = 403
  ELSE  // admin 但路径不合法
    ASSERT execute_python_rule'(rule_with(X)).error CONTAINS "Disallowed"
    ASSERT no_class_loaded(X)
  END IF
END FOR
```

```pascal
// Preservation Checking — 合法规则不受影响
FOR ALL X WHERE NOT isBugCondition_11_1(X) DO
  ASSERT execute_python_rule(X) = execute_python_rule'(X)
  ASSERT create_rule(X) = create_rule'(X)
END FOR
```

## Fix Verification Criteria

- `_load_class_from_dotted_path` 前缀白名单校验：非白名单路径 → `ImportError`（验证 2.1）
- 创建/编辑 `python` 类型规则限 admin：非 admin → 403（验证 2.2）
- `jsonpath` 类型规则创建不受限：任意角色可创建（验证 2.3 / 3.2）
- 既有 20 条规则（QC-01~QC-28）全部正常执行无回归（验证 3.1）
- 注释中"沙箱"措辞已替换（验证 2.5）
- 白名单可配置（初始 `["app.services.qc_engine.", "app.services.qc_rules."]`）便于后续扩展
