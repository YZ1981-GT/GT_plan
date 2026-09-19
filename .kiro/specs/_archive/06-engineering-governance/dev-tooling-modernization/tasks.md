# Tasks: 开发工具链现代化（uv / Docling / gitleaks / SQLFluff / DSPy）

## Overview

五模块独立分组，按 ROI 排序，可单独实施或裁剪：组① gitleaks → 组② SQLFluff → 组③ uv → 组④ Docling（评估后定）→ 组⑤ DSPy（探索）。Docling/DSPy 子任务标 `*` 可选。

**勘察结论（实施前必读）**：
- `.git-hooks/` 现有 `pre-push`（bash 脚本）+ `install.ps1`。pre-push 风格：shebang `#!/usr/bin/env bash` + `set -e` + Python 路径探测（`.venv/Scripts/python.exe` → `.venv/bin/python` → `python`）+ `--no-verify` 救急说明。**新 pre-commit 必须同风格**（bash + 二进制缺失优雅降级 + 救急提示）。`install.ps1` 负责把 hooks 软链到 `.git/hooks/`——新 pre-commit 要确认被 install.ps1 覆盖或手动加。
- migrations：`backend/migrations/V*.sql` + `R*.sql`（D6 MigrationRunner），当前最高 V052。SQLFluff dialect=postgres（与 sqlglot pg_only 契约一致）。
- 知识库降级链：`backend/app/routers/knowledge_folders.py` 的 `_extract_text_with_ocr`（已重构为 MarkItDown→MinerU→PyPDF2/python-docx 三级，markitdown spec 产物）。Docling 若纳入插在 MarkItDown 之后、MinerU 之前（仅 PDF）。
- markitdown 已装（onnxruntime/torch 生态已在仓库，Docling 评估须看与之冲突）。
- `.env.example` 有占位符（gitleaks allowlist 要豁免）；`.env` 在仓库根（不可入库，gitleaks 重点防护对象）。
- CI：`.github/workflows/`（gitleaks/sqlfluff job 加于此）。
- `build_exe.py` 在仓库根（PyInstaller 打包，uv 加速候选）。

## Tasks

### 组 ① gitleaks secret 扫描（最高优先）

- [x] 1. `.gitleaks.toml` 配置
  - extend default rules + allowlist：`.env.example` 占位符（如 `not-needed` / `postgres:postgres` / `admin123` 测试密码）/ 测试 fixture 假密钥 / `.hypothesis/` 等
  - 规则覆盖：`sk-` / `ghp_` / `AKIA` / PEM 私钥 / `postgresql://user:pass@` 真实密码
  - _Requirements: 1.3_

- [x] 2. `.git-hooks/pre-commit`（bash，同 pre-push 风格）
  - shebang + `set -e`；检测 `gitleaks` 二进制（`command -v gitleaks`），缺失 → `echo "[pre-commit] ⚠️ gitleaks 未安装，跳过（CI 兜底）"; exit 0`
  - 有：`gitleaks protect --staged --config .gitleaks.toml --redact`；非 0 退出 → 提示 + `--no-verify` 救急说明
  - 更新 `.git-hooks/install.ps1` 把 pre-commit 一并软链到 `.git/hooks/`（与 pre-push 并列）
  - _Requirements: 1.1, 1.4_

- [x] 3. CI gitleaks job
  - `.github/workflows/` 加 gitleaks（`gitleaks/gitleaks-action` official，push/PR 全量 `gitleaks detect`）
  - 用同一 `.gitleaks.toml`
  - _Requirements: 1.2_

- [x] 4. 拦截验证
  - 临时造假 secret（如 `FAKE_KEY="sk-test1234..."`）staged → 跑 pre-commit 确认拦截 → 验证后删除假 secret
  - 确认 `.env.example` 现有占位符不被误报（allowlist 生效）
  - _Requirements: 1.5_

- [x] 5. 检查点 — gitleaks 拦截生效 + allowlist 不误报现有 .env.example + install.ps1 软链 pre-commit

### 组 ② SQLFluff 裸 SQL lint

- [x] 6. `.sqlfluff` 配置
  - `[sqlfluff] dialect = postgres` + `templater = raw`（V*.sql 无 jinja）
  - 规则集：缩进/关键字大小写（大写）/逗号风格；排除过严规则避免存量噪音
  - _Requirements: 2.1_

- [x] 7. lint migrations + 存量基线
  - 对 `backend/migrations/*.sql`（V001~V052 + R*.sql）跑 `sqlfluff lint`（仅报告不 fix）
  - 存量告警：记基线数量（不强制清零，增量收敛——新增迁移不得引入新告警）
  - _Requirements: 2.2, 2.4_

- [x] 8. CI warning 级集成
  - `.github/workflows/` 加 sqlfluff lint step（warning 级：`continue-on-error: true` 或仅对新增/改动的 V*.sql 卡）
  - _Requirements: 2.3_

- [x] 9. 检查点 — `sqlfluff lint backend/migrations/V052*.sql` 可跑出报告 + CI 不卡死存量

### 组 ③ uv 装包加速

- [x] 10. uv 接入文档 + CI
  - 文档（README 或 `docs/` 开发指南）加 `uv pip install -r backend/requirements.txt` 加速路径（pin uv 版本说明）
  - CI 装包 step 改 `uv pip install`（保留 pip fallback：`uv pip install ... || pip install ...` 或条件分支）
  - **不迁移 pyproject.toml**（requirements.txt 体系保留）
  - _Requirements: 3.1, 3.2, 3.4_

- [x] 11. build_exe.py 依赖准备评估
  - 评估 `build_exe.py`（仓库根，PyInstaller）依赖准备阶段是否用 uv 加速；uv 不可用回退 pip
  - 仅文档/可选改造，不强制（PyInstaller 本身打包阶段不受 uv 影响）
  - _Requirements: 3.3_

- [x] 12. 检查点 — `uv pip install -r backend/requirements.txt` 在干净 venv 全装成功（与 pip 结果一致，含 markitdown/instructor 等新依赖）

### 组 ④ Docling PDF 增强（评估后决定）

- [x]* 13. Docling 依赖评估
  - 评估 Docling 的 torch/模型依赖与现有 `onnxruntime`(markitdown 带)/`mineru[core]` 是否冲突 + 安装体积影响（pip install docling 干净 venv 试装）
  - 产出"纳入/裁掉"结论（写入本 tasks 末尾决策记录）
  - _Requirements: 4.1, 4.4_

- [x]* 14. （评估通过才做）Docling 接入降级链
  - `backend/app/core/config.py` 加 `DOCLING_ENABLED: bool = False`
  - `knowledge_folders.py._extract_text_with_ocr`：在 MarkItDown 之后、MinerU 之前插 Docling 分支（仅 `.pdf` 且 MarkItDown 输出空/不足时触发，`DOCLING_ENABLED` 真才走）
  - 降级链单测：DOCLING_ENABLED 开关 + PDF markitdown 空→Docling→MinerU 顺序
  - _Requirements: 4.2, 4.3_

- [x]* 15. 检查点 — Docling 纳入则降级链单测绿；裁掉则评估结论记录在案

### 组 ⑤ DSPy prompt 工程化（探索性）

- [x]* 16. DSPy 可行性评估
  - 评估 DSPy 与现有两套 LLM 客户端（llm_client.chat_completion / AIService）+ spec `llm-structured-output` 的 Instructor/Pydantic 整合成本
  - DSPy 配 vLLM（OpenAI 兼容 endpoint `settings.LLM_BASE_URL`）；评估学习曲线/收益
  - 产出"落地/仅文档"结论
  - _Requirements: 5.1, 5.4_

- [x]* 17. （评估值得才做）DSPy PoC 样板
  - 选 1 个高频 prompt 场景（如某审计循环 LLM 复核）做 DSPy Signature + Module 改造
  - 输出与原 prompt 等价性对比；Signature 输出对接 spec-1 的 Pydantic `response_model`（如 TsjReviewResult）
  - _Requirements: 5.2, 5.3_

- [x]* 18. 检查点 — DSPy PoC 等价对比通过 或 可行性评估文档产出

### 组 ⑥ 收尾

- [x] 19. 最终检查点
  - 必做模块（gitleaks/SQLFluff/uv）全部生效：pre-commit 拦截 + sqlfluff lint 可跑 + uv 装包成功
  - 可选模块（Docling/DSPy）结论明确（纳入并测试 / 裁掉并记录）
  - 验证五模块互相独立：任一模块裁剪不影响其他（gitleaks > SQLFluff > uv > Docling > DSPy 优先级顺序成立）
  - _Requirements: 6.1, 6.2_

- [x]* 20. 跨 spec 打包体积回归检查（外部依赖：前序 spec 实施完 + PyInstaller 环境）
  - 5 spec 依赖全落定后跑 `build_exe.py`，记录产物体积 + 冷启动时间
  - 对比引入前基线；超 +30% → 评估重依赖懒加载/可选 extra（OTel 仅 OTEL_ENABLED import / docling 默认关 / bm25s 懒加载）
  - 产出体积影响结论（写入决策记录区）
  - _Requirements: 7.1, 7.2, 7.3_

## 可选模块决策记录（组④⑤评估后填写）

> Docling：**裁掉**
> - 理由：docling 2.97.0（最新）= `docling-slim[standard]` → 拉入 `docling-ibm-models`（依赖 `torch` + `torchvision` + `transformers` + `accelerate` + `safetensors` + `huggingface_hub`）。
> - **体积影响**：torch 2.x CPU-only wheel ~850MB（CUDA 版 ~2.5GB）+ transformers ~500MB + 模型权重首次运行下载 ~1-2GB = 总计 **2-4GB 新增依赖**。当前 venv 最重依赖 onnxruntime ~12MB（markitdown 带入），docling 引入后体积膨胀 100-300×。
> - **冲突风险**：①torch 版本 pin 可能与 MinerU（mineru[core] 自带 torch 约束）冲突；②onnxruntime 与 torch 共存无直接冲突，但 `docling-slim[models-onnxruntime]` extra 自带 onnxruntime 版本约束可能锁死升级路径。
> - **PyInstaller 打包致命**：torch 打入 exe 产物会从当前 ~200MB 膨胀到 1-2GB+，冷启动时间从 3-5s 变 15-30s，严重违反 memory.md "本地优先轻量方案" 铁律。
> - **收益有限**：现有 MarkItDown→MinerU→PyPDF2 三级降级链已覆盖绝大多数场景（MarkItDown 0.1.6 含 pdfplumber 处理文字 PDF，MinerU OCR 处理扫描件），docling 仅在"复杂嵌套表格 PDF"场景边际提升。
> - **结论**：DOCLING_ENABLED 保持 False（设计文档已预设），不引入 docling 依赖。如未来有强需求，可考虑 `docling-slim[models-remote]`（远程推理，不本地装 torch）或独立微服务部署。
> DSPy：**仅文档（不落代码）**
> - 理由：Instructor + vLLM guided_json（spec `llm-structured-output`）已覆盖结构化输出核心痛点（失败率 20-30%→<2%），DSPy 在此场景无增量价值。
> - **自动优化前置条件不满足**：DSPy Teleprompter 需标注数据集 + 可量化评估指标，审计复核场景缺乏系统化标注数据（输出质量靠人工判断），无法发挥 DSPy 核心差异化价值。
> - **架构碎片化**：已有 3 套 LLM 客户端（llm_client / AIService / LLMService）+ Instructor = 4 种 LLM 交互方式；DSPy = 第 5 种，1-2 人团队维护负担过重。
> - **最佳 PoC 候选是孤儿代码**：`tsj_structured_output_service`（TsjReviewResult）全仓 0 调用方，即使改造成功也无业务流量验证。
> - **学习曲线 ROI 不达标**：DSPy 2.x API 仍快速迭代（月级 breaking change），预估 2-3 周投入换取不确定收益。
> - **重新评估触发**：①prompt 优化成为瓶颈 ②积累 ≥50 对标注数据 ③团队扩大有 ML 专人 ④DSPy 与 Instructor 有官方集成 ⑤3 套 LLM 客户端统一后。
> - 完整评估文档：`docs/dspy-feasibility-evaluation.md`

## 打包体积回归检查状态（Task 20）

> **状态**：外部依赖未满足，暂缓执行
> - `build_exe.py` 当前不存在于仓库中（待建立 PyInstaller 打包脚本）
> - 前序 5 spec（llm-structured-output / pg-pooling / xlsx-read / endpoint-fuzz / dev-tooling）依赖未全部落定到 requirements.txt
> - **Docling 裁掉**后体积风险已大幅降低（最重依赖 torch 不引入）
> - 当前新增依赖仅：sqlfluff（开发期工具，不打入 exe）+ uv（CLI 工具，不打入 exe）
> - **结论**：本 spec 本身对打包体积零影响（gitleaks/sqlfluff/uv 均为开发期工具不入运行时）。跨 spec 打包体积检查待 build_exe.py 就位 + 其他 spec 实施完成后统一执行。
> - 评估日期：2026-06-04
