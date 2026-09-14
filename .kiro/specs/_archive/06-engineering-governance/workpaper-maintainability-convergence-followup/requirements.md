# Requirements Document

## Introduction

承接已完成的 `workpaper-maintainability-convergence` spec，本 spec 处理其遗留的四类技术债：Ledger 漂移修复、unknown→covered 自动标记、Legacy Provider 物理删除、同构 FormData 工厂实迁。目标是将 94 个同构 FormData composable 替换为 `createChecklistFormData` 工厂调用、物理删除 159 个已被 Runtime Boundary 覆盖的 Legacy Provider 代码、修复 8 个 Ledger 漂移条目、并扩展 `generate_coverage_ledger.py` 实现 unknown→covered 自动标记。

## Glossary

- **Coverage_Ledger**: `coverage-ledger.json`，能力级覆盖记录（schemaVersion=2），记录每个 wp_code 根入口对 8 项全局能力的接入状态（covered/unknown/exempt）
- **Ledger_Generator**: `generate_coverage_ledger.py`，扫描主入口文件生成 Coverage Ledger 的零依赖 Python 脚本
- **Legacy_Provider**: 指 D~N 循环主入口中通过 `useWorkpaperVersionToolbar`/`useWorkpaperReviewProvide` 本地 provide 的 version/review 能力接线代码，已被 Runtime Boundary（GtWpRenderer 一次性 provide）功能覆盖
- **Runtime_Boundary**: GtWpRenderer 组件在渲染专属底稿时一次性 provide 全部横切能力（displayPrefs/agingConfig/version/review/ai），子组件通过 inject 消费
- **WorkpaperRuntimeContextKey**: Runtime Boundary 注入的统一上下文 InjectionKey，子组件通过 `inject(WorkpaperRuntimeContextKey)` 获取 wpId/projectId/year 等运行时信息
- **FormData_Factory**: `createChecklistFormData` 工厂函数，参数化统一 checklist 持久化 composable，替代 94 个同构的 useXFormData 自建网络实现
- **Homogeneous_FormData**: 结构同构的 FormData composable（仅 itemPrefix/accountCodes/forceComponentType/label 四常量不同），由 `check_homogeneous_formdata.py` 检测
- **CI_Guard**: 持续集成守卫脚本，report 模式输出违规报告不阻断，strict 模式违规时 exit 1 阻断合并
- **Vite_Transform**: 前端构建工具对 .vue/.ts 文件的编译转换，HTTP 200 表示编译成功，500 表示存在语法/导入错误

## Requirements

### Requirement 1: Ledger 漂移修复

**User Story:** As a platform maintainer, I want all dedicated wp_code root entries registered in the Coverage Ledger, so that coverage tracking is complete and CI drift detection has no blind spots.

#### Acceptance Criteria

1. WHEN the Ledger_Generator is executed, THE Ledger_Generator SHALL produce entries for J1, J2, J3, K14, K15, K16, K17, and K18 in the output Coverage_Ledger
2. WHEN the Coverage_Ledger is generated, THE Coverage_Ledger SHALL contain capability records for all wp_code roots that have a dedicated main entry file and a non-skip componentType in wp_code_overrides.json
3. IF a wp_code root has a main entry file but is missing from the generated Coverage_Ledger, THEN THE `check_coverage_ledger.py` SHALL report it as a drift violation in strict mode

### Requirement 2: Unknown → Covered 自动标记

**User Story:** As a platform maintainer, I want the Ledger Generator to automatically mark capabilities as covered when a main entry injects WorkpaperRuntimeContextKey, so that Runtime Boundary coverage is accurately reflected without manual annotation.

#### Acceptance Criteria

1. WHEN a main entry file contains `inject(WorkpaperRuntimeContextKey)`, THE Ledger_Generator SHALL mark the displayPrefs capability as covered with source evidence
2. WHEN a main entry file contains `inject(WorkpaperRuntimeContextKey)`, THE Ledger_Generator SHALL mark the agingConfig capability as covered with source evidence
3. WHEN a main entry file contains `inject(WorkpaperRuntimeContextKey)`, THE Ledger_Generator SHALL mark the version capability as covered with source evidence
4. WHEN a main entry file contains `inject(WorkpaperRuntimeContextKey)`, THE Ledger_Generator SHALL mark the review capability as covered with source evidence
5. WHEN a main entry file contains `inject(WorkpaperRuntimeContextKey)`, THE Ledger_Generator SHALL mark the ai capability as covered with source evidence
6. WHEN a main entry file does not contain `inject(WorkpaperRuntimeContextKey)` and has no other matching detection patterns, THE Ledger_Generator SHALL keep the capability status as unknown

### Requirement 3: Legacy Provider 物理删除

**User Story:** As a developer, I want Legacy Provider code removed from main entries that already consume Runtime Boundary capabilities, so that the codebase has a single authoritative source for version/review functionality and no dead code confuses future maintainers.

#### Acceptance Criteria

1. WHEN a main entry file contains `inject(WorkpaperRuntimeContextKey)`, THE migration tool SHALL remove local `useWorkpaperVersionToolbar` import and invocation from that file
2. WHEN a main entry file contains `inject(WorkpaperRuntimeContextKey)`, THE migration tool SHALL remove local `useWorkpaperReviewProvide` import and invocation from that file
3. WHEN Legacy_Provider code is removed from a main entry, THE main entry SHALL retain all `inject(WorkpaperRuntimeContextKey)` statements and Runtime Boundary consumption code intact
4. WHEN Legacy_Provider code is removed from a main entry, THE main entry SHALL continue to pass Vite_Transform verification with HTTP 200
5. WHEN Legacy_Provider code is removed from a main entry, THE main entry SHALL continue to pass `get_diagnostics` with zero errors
6. IF a main entry file does not contain `inject(WorkpaperRuntimeContextKey)`, THEN THE migration tool SHALL skip that file and report it as not eligible for Legacy Provider removal

### Requirement 4: FormData 工厂实迁

**User Story:** As a developer, I want the 94 homogeneous FormData composables replaced with `createChecklistFormData` factory calls, so that duplicate network I/O, debounce, and hydrate code is eliminated and future checklist persistence changes only need to be made in one place.

#### Acceptance Criteria

1. WHEN a homogeneous FormData composable is migrated, THE migrated composable SHALL call `createChecklistFormData` with the correct itemPrefix, label, forceComponentType, and accountCodes parameters
2. WHEN a homogeneous FormData composable is migrated, THE migrated composable SHALL preserve any existing normalizeResponse or afterSave hooks by passing them to the factory config
3. WHEN a homogeneous FormData composable is migrated, THE migrated composable SHALL export the same public API (allResponses, isLoading, loadData, save, debouncedSave, flush, cancel) so that consuming components require zero changes
4. WHEN all composables in a batch are migrated, THE `check_homogeneous_formdata.py` guard SHALL report zero violations for those files
5. WHEN a migrated composable is loaded at runtime, THE Vite_Transform SHALL return HTTP 200 for both the composable file and all consuming Vue components
6. IF a composable has significant business differences (listed in MIGRATED_ALLOWLIST or complex htmlData logic), THEN THE migration tool SHALL skip that composable

### Requirement 5: CI Guard 模式升级

**User Story:** As a CI pipeline owner, I want the homogeneous FormData guard switched to strict mode after all 94 files are migrated, so that no new self-built checklist network implementations can be introduced.

#### Acceptance Criteria

1. WHILE all 94 homogeneous FormData composables are migrated, THE `check_homogeneous_formdata.py` SHALL be switched from report mode to strict mode in CI configuration
2. WHEN `check_homogeneous_formdata.py` runs in strict mode, THE CI_Guard SHALL exit 1 if any new homogeneous FormData violation is detected
3. WHEN `check_homogeneous_formdata.py` runs in strict mode, THE CI_Guard SHALL exit 0 if zero violations are detected

### Requirement 6: 批次验证

**User Story:** As a platform maintainer, I want each migration batch validated through diagnostics and Vite transform before proceeding to the next batch, so that regressions are caught incrementally and rollback scope is minimized.

#### Acceptance Criteria

1. WHEN a migration batch is completed, THE developer SHALL run `get_diagnostics` on all modified files and confirm zero errors before proceeding
2. WHEN a migration batch is completed, THE developer SHALL verify Vite_Transform returns HTTP 200 for all modified .vue and .ts files
3. IF a migration batch introduces diagnostics errors or Vite_Transform failures, THEN THE developer SHALL revert the batch and fix before proceeding

### Requirement 7: Coverage Ledger 更新

**User Story:** As a platform maintainer, I want the Coverage Ledger regenerated after Legacy Provider deletion and factory migration, so that the ledger accurately reflects the new coverage state with reduced unknown slots.

#### Acceptance Criteria

1. WHEN all Legacy_Provider deletions and factory migrations are complete, THE Ledger_Generator SHALL be re-executed to produce an updated Coverage_Ledger
2. WHEN the updated Coverage_Ledger is generated, THE Coverage_Ledger SHALL show zero Ledger drift entries
3. WHEN the updated Coverage_Ledger is generated, THE unknown capability count SHALL be reduced compared to the pre-migration baseline of 578

### Requirement 8: 迁移报告

**User Story:** As a project stakeholder, I want a migration report documenting before/after metrics, so that the impact of this follow-up work is quantifiable and auditable.

#### Acceptance Criteria

1. WHEN all migrations are complete, THE migration report SHALL document the number of Legacy_Provider call sites removed
2. WHEN all migrations are complete, THE migration report SHALL document the number of FormData composables migrated to factory calls
3. WHEN all migrations are complete, THE migration report SHALL document the before/after Coverage_Ledger statistics (covered/unknown/exempt counts)
4. WHEN all migrations are complete, THE migration report SHALL document the before/after `check_homogeneous_formdata.py` violation count
