# Implementation Plan: Workpaper Maintainability Convergence Follow-up

## Overview

四波实施：Wave 0 修复 Ledger 漂移 + Generator 增强（最小最关键），Wave 1 Legacy Provider 批量删除（按循环），Wave 2 FormData 工厂迁移（按循环），Wave 3 CI strict + 最终验证 + 报告。每波 ≤5 文件/叶子任务。

## Tasks

- [x] 1. Wave 0: Ledger 漂移修复 + Generator 增强
  - [x] 1.1 修复 generate_coverage_ledger.py 漏掉 J1/J2/J3/K14-K18
    - 排查 `get_distinct_root_codes()` 为何这 8 个 root code 未被提取
    - 检查 `wp_code_overrides.json` 中 J1/J2/J3/K14-K18 的条目是否存在且非 skip
    - 检查 `find_main_entry_files()` 是否能匹配到对应的 GtJ1/GtJ2/GtJ3/GtK14-K18 入口文件
    - 修复逻辑使这 8 个 root code 出现在生成结果中
    - _Requirements: 1.1, 1.2_

  - [x] 1.2 添加 WorkpaperRuntimeContextKey 自动标记逻辑
    - 在 `DETECTION_PATTERNS` 或新增独立检测逻辑中加入 `inject\s*\(\s*WorkpaperRuntimeContextKey` 模式
    - 当文件匹配该模式时，自动将 displayPrefs/agingConfig/version/review/ai 5 项标记为 covered
    - evidence 字符串格式：`{relative_path}:inject(WorkpaperRuntimeContextKey)`
    - 不含该模式且无其他检测模式命中的能力保持 unknown
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x]* 1.3 编写属性测试 Property 1 + Property 2 + Property 3
    - **Property 1: Ledger completeness — all dedicated roots present**
    - **Property 2: Runtime Boundary auto-marking consistency**
    - **Property 3: Runtime Boundary absence preserves unknown**
    - **Validates: Requirements 1.2, 2.1-2.6**

  - [x] 1.4 运行 generate_coverage_ledger.py --check 验证输出
    - 确认 J1/J2/J3/K14-K18 全部出现
    - 确认含 inject(WorkpaperRuntimeContextKey) 的主入口其 5 项能力为 covered
    - 确认不含该模式的主入口能力保持 unknown（或由其他模式标记）
    - _Requirements: 1.1, 1.2, 2.1-2.6_

- [x] 2. Wave 0 Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Wave 1: Legacy Provider 批量删除
  - [x] 3.1 创建 remove_legacy_providers.py 脚本骨架
    - 位于 `backend/scripts/migration/remove_legacy_providers.py`
    - 扫描 `workpaper/Gt*.vue` 主入口文件
    - 前置检查：文件含 `inject(WorkpaperRuntimeContextKey` 才处理
    - 不含则跳过并报告 "not eligible"
    - 输出 unified diff 模式（`--apply` 写入，默认 dry-run）
    - _Requirements: 3.1, 3.2, 3.6_

  - [x] 3.2 实现 Legacy Provider 删除逻辑
    - 识别并删除 `import { useWorkpaperVersionToolbar } from ...` 行
    - 识别并删除 `useWorkpaperVersionToolbar(...)` 调用行及其返回值解构
    - 识别并删除 `import { useWorkpaperReviewProvide } from ...` 行
    - 识别并删除 `useWorkpaperReviewProvide(...)` 调用行
    - 清理悬空空行（连续 >2 空行压缩为 1）
    - 保留 `inject(WorkpaperRuntimeContextKey` 等 Runtime Boundary 代码
    - _Requirements: 3.1, 3.2, 3.3_

  - [x]* 3.3 编写属性测试 Property 4
    - **Property 4: Legacy Provider removal preserves Runtime Boundary**
    - **Validates: Requirements 3.3**

  - [x] 3.4 Wave 1 Batch D 循环: 执行删除 (D1-D7, ≤7 文件)
    - `python remove_legacy_providers.py --apply --cycle D`
    - get_diagnostics 验证 0 errors
    - Vite transform curl 验证 HTTP 200
    - _Requirements: 3.1, 3.2, 3.4, 3.5, 6.1, 6.2_

  - [x] 3.5 Wave 1 Batch E/F 循环: 执行删除 (E1, F1-F5, ≤6 文件)
    - `python remove_legacy_providers.py --apply --cycle E,F`
    - get_diagnostics + Vite transform 验证
    - _Requirements: 3.1, 3.2, 3.4, 3.5, 6.1, 6.2_

  - [x] 3.6 Wave 1 Batch G 循环: 执行删除 (G1-G14, ≤14 文件)
    - `python remove_legacy_providers.py --apply --cycle G`
    - get_diagnostics + Vite transform 验证
    - _Requirements: 3.1, 3.2, 3.4, 3.5, 6.1, 6.2_

  - [x] 3.7 Wave 1 Batch H/I 循环: 执行删除 (H1-H10, I1-I6, ≤16 文件)
    - `python remove_legacy_providers.py --apply --cycle H,I`
    - get_diagnostics + Vite transform 验证
    - _Requirements: 3.1, 3.2, 3.4, 3.5, 6.1, 6.2_

  - [x] 3.8 Wave 1 Batch J/K 循环: 执行删除 (J1-J3, K1-K13, ≤16 文件)
    - `python remove_legacy_providers.py --apply --cycle J,K`
    - get_diagnostics + Vite transform 验证
    - _Requirements: 3.1, 3.2, 3.4, 3.5, 6.1, 6.2_

  - [x] 3.9 Wave 1 Batch L/M/N 循环: 执行删除 (L1-L8, M1-M10, N1-N5, ≤23 文件)
    - `python remove_legacy_providers.py --apply --cycle L,M,N`
    - get_diagnostics + Vite transform 验证
    - _Requirements: 3.1, 3.2, 3.4, 3.5, 6.1, 6.2_

  - [x] 3.10 Wave 1 Batch A/B/C/S 循环: 执行删除 (剩余主入口)
    - `python remove_legacy_providers.py --apply --cycle A,B,C,S`
    - get_diagnostics + Vite transform 验证
    - _Requirements: 3.1, 3.2, 3.4, 3.5, 6.1, 6.2_

- [x] 4. Wave 1 Checkpoint
  - Ensure all tests pass, ask the user if questions arise.
  - 验证所有 Legacy Provider import/调用已从含 Runtime Boundary 的主入口中删除
  - 总修改文件数统计

- [x] 5. Wave 2: FormData 工厂迁移
  - [x] 5.1 创建 migrate_formdata_factory.py 脚本骨架
    - 位于 `backend/scripts/migration/migrate_formdata_factory.py`
    - 内嵌 `FORMDATA_MIGRATION_MAP` 配置（94 个 composable 的 prefix/label/componentType/accountCodes）
    - 内嵌 `SKIP_LIST`（非同构文件：useD2FormData、useD4-D7FormData、useG4EclFormData 等）
    - 输出模式：`--apply` 写入 / `--dry-run` 仅报告 / `--cycle K` 按循环过滤
    - _Requirements: 4.1, 4.6_

  - [x] 5.2 实现 FormData 迁移模板生成逻辑
    - 对每个目标 composable 文件：
      1. 读取原始文件提取 normalizeResponse/afterSave 钩子（如有）
      2. 生成替换内容：import factory + 导出同名函数 + 返回 createChecklistFormData(config)
      3. 保持文件编码 UTF-8，保持相同 export 函数签名
    - _Requirements: 4.1, 4.2, 4.3_

  - [x]* 5.3 编写属性测试 Property 5 + Property 6
    - **Property 5: FormData factory migration preserves public API**
    - **Property 6: FormData migration eliminates self-built network**
    - **Validates: Requirements 4.3, 4.4**

  - [x] 5.4 Wave 2 Batch K1-K13 迁移 (13 文件)
    - `python migrate_formdata_factory.py --apply --cycle K`
    - get_diagnostics 验证 0 errors
    - Vite transform 验证 HTTP 200
    - `python check_homogeneous_formdata.py` 验证 K 循环 0 violations
    - _Requirements: 4.1, 4.3, 4.4, 4.5, 6.1, 6.2_

  - [x] 5.5 Wave 2 Batch M1-M10 迁移 (10 文件)
    - `python migrate_formdata_factory.py --apply --cycle M`
    - get_diagnostics + Vite transform + guard 验证
    - _Requirements: 4.1, 4.3, 4.4, 4.5, 6.1, 6.2_

  - [x] 5.6 Wave 2 Batch H1-H10 迁移 (10 文件)
    - `python migrate_formdata_factory.py --apply --cycle H`
    - get_diagnostics + Vite transform + guard 验证
    - _Requirements: 4.1, 4.3, 4.4, 4.5, 6.1, 6.2_

  - [x] 5.7 Wave 2 Batch I1-I6 迁移 (6 文件)
    - `python migrate_formdata_factory.py --apply --cycle I`
    - get_diagnostics + Vite transform + guard 验证
    - _Requirements: 4.1, 4.3, 4.4, 4.5, 6.1, 6.2_

  - [x] 5.8 Wave 2 Batch G10-G14 迁移 (16 文件, 21 skipped complex)
    - `python migrate_formdata_factory.py --apply --cycle G`
    - get_diagnostics + Vite transform + guard 验证
    - _Requirements: 4.1, 4.3, 4.4, 4.5, 6.1, 6.2_

  - [x] 5.9 Wave 2 Batch N1-N5 迁移 (5 文件)
    - `python migrate_formdata_factory.py --apply --cycle N`
    - get_diagnostics + Vite transform + guard 验证
    - _Requirements: 4.1, 4.3, 4.4, 4.5, 6.1, 6.2_

  - [x] 5.10 Wave 2 Batch L2-L8 迁移 (7 文件)
    - `python migrate_formdata_factory.py --apply --cycle L`
    - get_diagnostics + Vite transform + guard 验证
    - _Requirements: 4.1, 4.3, 4.4, 4.5, 6.1, 6.2_

- [x] 6. Wave 2 Checkpoint
  - Ensure all tests pass, ask the user if questions arise.
  - `python check_homogeneous_formdata.py` 全量扫描确认 0 violations
  - 总迁移文件数统计（预期 53 同构 + 跳过非同构 ≈ 94 目标中的 53 个同构文件）

- [x] 7. Wave 3: CI Guard Strict + Final Ledger + Report
  - [x] 7.1 切换 check_homogeneous_formdata.py 到 strict 模式
    - 修改 `governance-checks.yml` 中的调用参数添加 `--strict`
    - 验证 CI 配置语法正确
    - _Requirements: 5.1, 5.2, 5.3_

  - [x]* 7.2 编写属性测试 Property 7
    - **Property 7: CI guard strict mode blocks new violations**
    - **Validates: Requirements 5.2**

  - [x] 7.3 最终 Ledger 重新生成
    - `python generate_coverage_ledger.py`
    - `python check_coverage_ledger.py --strict` 验证 drift=0
    - 统计 unknown 能力数量，确认较 578 基线减少
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 7.4 生成迁移报告
    - 创建/更新 `.kiro/specs/workpaper-maintainability-convergence-followup/migration-report.md`
    - 记录：Legacy Provider 删除文件数 / FormData 迁移文件数 / Ledger before/after (covered/unknown/exempt) / guard violation before/after
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [x] 8. Final Checkpoint
  - Ensure all tests pass, ask the user if questions arise.
  - 确认全部 guard exit 0
  - 确认 Coverage Ledger drift = 0
  - 确认 check_homogeneous_formdata.py --strict exit 0

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each wave has verification (get_diagnostics + Vite transform) before proceeding
- Wave 1 batch sizes: D(7) / E+F(6) / G(14) / H+I(16) / J+K(16) / L+M+N(23) / A+B+C+S(剩余)
- Wave 2 batch sizes: K(13) / M(10) / H(10) / I(6) / G(5) / N(5) / L(4)
- FormData 迁移仅覆盖 `createChecklistFormData.ts` 文档注明的 53 个同构文件（非全部 94 个 violation 文件，部分有业务差异需手工处理）
- 所有脚本使用 Python stdlib（零依赖），UTF-8 显式编码，遵守 Windows 命令规范
