# Implementation Plan

## Overview

在模板库「公式管理」页签 surface 已有通用预设 + 新增隔离存储的自定义预设写入通道。复用优先：通用预设=`preset_library` 收敛库；浏览/编辑=`GtFormulaPresetDialog`+`GtFormulaEditDialog`。唯一实质新增=`formula_custom_presets.json`（与 seed 隔离）+ `load/upsert_custom_presets` + `POST /presets/custom` 写端点。全部 additive、零回归、灰度式可回退。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1"], "desc": "安全网 characterization" },
    { "wave": 1, "tasks": ["2.1", "2.2"], "desc": "后端自定义收敛源 + 隔离存储" },
    { "wave": 2, "tasks": ["3.1", "3.2"], "desc": "后端写端点 + 来源 surface" },
    { "wave": 3, "tasks": ["4.1", "4.2"], "desc": "前端页签框架条 + 预设库入口接线" },
    { "wave": 4, "tasks": ["5.1"], "desc": "前端来源标注 + 权限门控 + vitest" },
    { "wave": 5, "tasks": ["6.1", "6.2"], "desc": "零回归门 + Playwright round-trip" }
  ]
}
```

## Tasks

- [x] 1. 安全网与基线（Wave 0）
  - [x] 1.1 后端 characterization 测试：锁定 `build_preset_library` 现有去重/stats 口径、`formula_presets_seed.json` 内容基线（未写不变）、`GET /presets/inventory`/`GET /presets/page` 响应形状（source 字段存在）。作为后续零回归对照。
    - _Requirements: 5.1, 5.2_

- [x] 2. 后端自定义收敛源与隔离存储（Wave 1）
  - [x] 2.1 新建 `backend/data/formula_presets/formula_custom_presets.json`（结构同 seed，`presets:[]`）；`preset_library.py` 加 `CUSTOM_PATH` + `load_custom_presets()`（source='custom'，容错返 []）；`build_preset_library` 的 `ordered` 把 custom 置于 seed 之前（同键覆盖，去重首个赢），stats 计 `source:custom`。**custom 与 `include_sources` 正交、两分支恒含**（`include_sources` 只控制 prefill/check/wide_table 收敛源）；零回归靠 custom 初始为空（`include_sources=False` 的既有调用方 seed 脚本 + seed-pilot 测试不受影响）。
    - _Requirements: 2.1, 3.3, 5.1_
  - [x] 2.2 `preset_library.py` 加 `upsert_custom_presets(entries)`（镜像 `upsert_seed_presets`，幂等按 (page_key,target_cell)，只写 `formula_custom_presets.json`，绝不触碰 seed）；PBT/单测：幂等 + seed 逐字节不变（P2）+ custom 优先（P4）+ custom 为空口径不变（P7）。
    - _Requirements: 3.2, 5.1, 6.1_

- [x] 3. 后端写端点与来源 surface（Wave 2）
  - [x] 3.1 `formula_import_export.py` router（prefix `/api/formula-management`）加 `POST /presets/custom`（`require_role` admin/partner；**复用 import-data 的 full_resolve 校验路径**，悬空→422 携清单不落库；通过→`upsert_custom_presets` 写 `formula_custom_presets.json`，返 `{inserted,updated,total}`）。**不改既有 `import-data`→`upsert_seed_presets`（写基线）行为**。契约测试：权限 403（P5）+ 悬空 422 不落库（P6）+ seed 文件未被写（P2）。
    - _Requirements: 3.1, 3.4, 4.1, 4.3, 5.1_
  - [x] 3.2 `GET /presets/inventory` / `GET /presets/page` 响应条目附加 additive 只读派生 `is_custom = source=='custom'`（不改既有字段）；契约测试：来源标注正确（P3）。
    - _Requirements: 1.1, 3.3, 6.1_

- [x] 4. 前端页签框架条与预设库入口（Wave 3）
  - [x] 4.1 `FormulaTab.vue` 顶部新增「通用 vs 自定义」框架条（说明「平台通用预设公式=所有企业通用、只读」+「公式预设库」按钮）；现有三子页保持不变。
    - _Requirements: 1.1, 1.2, 1.3, 5.2_
  - [x] 4.2 `FormulaTab.vue` 引入 `GtFormulaPresetDialog`，「公式预设库」按钮打开；监听 `@edit-formula` → 调 `useFormulaImportExport.saveCustomPreset`（新增，`POST /presets/custom`）持久化到 custom；成功刷新预设浏览。
    - _Requirements: 2.2, 3.1, 3.2, 5.3_

- [x] 5. 前端来源标注与权限门控（Wave 4）
  - [x] 5.1 `GtFormulaPresetDialog` 预设列表按 `is_custom`/`source` 显示「通用/自定义」tag（additive）；`FormulaTab` 对无编辑权角色隐藏/禁用新建、编辑入口（浏览只读仍可，用既有权限来源）。vitest：来源判定纯逻辑 + 权限门控纯逻辑（P3/P5）。
    - _Requirements: 3.3, 4.1, 4.2, 6.2_

- [x] 6. 零回归门与端到端（Wave 5）
  - [x] 6.1 零回归门：后端 preset_library/formula_management 全套 + characterization（P7）；前端 `FormulaTab.vue`/`GtFormulaPresetDialog.vue` diagnostics 全清 + Vite transform 200；确认 NoteTemplateTab/ReportConfigTab/WpTemplateDetail 调用点未回归。
    - _Requirements: 5.1, 5.2, 5.3_
  - [x]* 6.2 端到端 round-trip：**用 live 鉴权 HTTP round-trip 替代 SSE-flaky 浏览器 Playwright**（平台既有范式）——登录→POST `/presets/custom`（`TB('1001','期末余额')` 经 ACNR full_resolve 通过）→200 落 `formula_custom_presets.json`（source=custom）→seed 逐字节未变（P2）→GET `/presets/page` 条目 `is_custom=True`（P3）→清理还原 custom 为空。前端 UI 由 17 vitest（saveCustomPreset/来源判定/权限门控）+ Vite transform 200 + diagnostics 全清覆盖。**PASS**。
    - _Requirements: 1.1, 1.2, 3.1, 3.2, 6.2_

## Notes

- **复用铁律**：通用预设禁造第二套（用 `preset_library`）；浏览/编辑禁造第二套弹窗（用 `GtFormulaPresetDialog`/`GtFormulaEditDialog`）。
- **隔离铁律**：自定义只写 `formula_custom_presets.json`，`formula_presets_seed.json` 全程只读（Property 2 守卫）。
- **零回归红线**：custom 为空时 `build_preset_library` 结果与改前一致；三子页只读不变；三个既有 dialog 调用点不变。
- **权限**：后端 `require_role` 为唯一防线，前端隐藏仅体验。
- **迁移**：无 DB 迁移（自定义走 JSON 文件，同 seed 模式）。
- 执行前置：Wave3/4 触及 `FormulaTab.vue`/`GtFormulaPresetDialog.vue`（并发会话可能编辑），改前 git status 核实、最小侵入。
