# Requirements: 开发工具链现代化（uv / Docling / gitleaks / SQLFluff / DSPy）

## Introduction

五个独立工具链改进合并管理（各为独立子任务、互不依赖、可单独取舍）：
- **gitleaks**：pre-commit + CI secret 泄漏扫描（安全卫生，最高优先）
- **SQLFluff**：裸 SQL（migrations）风格 lint
- **uv**：依赖安装提速（pip 替代加速器，build_exe/CI 受益）
- **Docling**：扫描件/复杂表格 PDF 解析增强（markitdown 补充，依赖重需评估）
- **DSPy**：LLM prompt 工程化探索（中长期 PoC，可能仅产出可行性文档）

定位为工具链卫生 + 长期可维护性，非业务功能。每个子任务可独立 ship 或裁剪。

## Glossary

- **gitleaks**: Go 单二进制 secret 扫描工具，扫描代码/暂存区中的密钥泄漏
- **SQLFluff**: SQL 方言感知的 linter/formatter
- **uv**: Rust 实现的 Python 包管理器，pip 兼容、快 10-100×
- **Docling**: IBM 开源文档解析库，擅长扫描件/复杂表格版面结构化
- **DSPy**: 把 LLM prompt 作为可编译/可优化程序的框架（Signature + Module）
- **降级链**: 知识库文档提取的多级 fallback（MarkItDown → MinerU → PyPDF2）
- **增量收敛**: 存量告警不一次性卡 CI，逐步修复

## Requirements

### Requirement 1: gitleaks secret 扫描

**User Story:** As a 安全负责人, I want 提交/CI 时自动拦截密钥泄漏, so that .env/凭据不被误提交。

#### Acceptance Criteria
1. THE `.git-hooks/pre-commit` SHALL 调用 `gitleaks protect --staged`，与现有 pre-push 共存不冲突。
2. THE CI SHALL 有 gitleaks job（push/PR 全量扫描）。
3. THE `.gitleaks.toml` SHALL 配置规则 + allowlist（.env.example 占位符、测试假密钥豁免）。
4. WHEN 本地 gitleaks 二进制缺失, THE pre-commit hook SHALL warning 不阻断（CI 强卡兜底）。
5. THE 系统 SHALL 用一个临时假 secret 验证拦截生效（验证后删除）。

### Requirement 2: SQLFluff 裸 SQL lint

**User Story:** As a 后端开发者, I want migrations SQL 有统一风格 lint, so that V*.sql 缩进/大小写/逗号风格一致。

#### Acceptance Criteria
1. THE `.sqlfluff` SHALL 配 `dialect=postgres` + 规则集，与 sqlglot pg_only 契约一致。
2. THE lint 范围 SHALL 先覆盖 `backend/migrations/*.sql`（独立文件，不含 service 内嵌 SQL 字符串）。
3. THE CI SHALL 以 warning 级跑 `sqlfluff lint`（增量收敛，不一次性卡死）。
4. THE 系统 SHALL NOT 自动 `fix`（避免改写风险），仅报告。

### Requirement 3: uv 装包加速

**User Story:** As a 开发者, I want 用 uv 加速依赖安装, so that build_exe 和 CI 装包更快。

#### Acceptance Criteria
1. THE 系统 SHALL 在文档/CI 提供 `uv pip install -r requirements.txt` 加速路径。
2. THE 接入 SHALL 保留 requirements.txt 体系（不强制迁移 pyproject.toml）。
3. WHEN uv 不可用, THE 流程 SHALL 回退 pip（命令层 fallback 或文档双写）。
4. THE uv 版本 SHALL pin。

### Requirement 4: Docling PDF 增强（评估后决定）

**User Story:** As an 审计助理, I want 扫描件/复杂表格 PDF 解析更准, so that 知识库入库的复杂 PDF 内容更完整。

#### Acceptance Criteria
1. THE 系统 SHALL 先评估 Docling 依赖（torch/模型）是否与现有 onnxruntime/mineru 冲突及体积影响。
2. IF 评估通过, THEN Docling SHALL 插入知识库 `_extract_text_with_ocr` 降级链（MarkItDown → Docling(PDF) → MinerU → PyPDF2），仅 PDF 且 markitdown 输出不足时触发。
3. THE 系统 SHALL 提供 `DOCLING_ENABLED`（默认 False，依赖重按需开）。
4. IF 评估不通过（依赖冲突/过重）, THEN 该模块 SHALL 裁掉并记录评估结论（不影响主链路）。

### Requirement 5: DSPy prompt 工程化（探索性）

**User Story:** As a 开发者, I want 评估 DSPy 把审计 prompt 工程化的可行性, so that 长期 prompt 可优化/可版本管理。

#### Acceptance Criteria
1. THE 系统 SHALL 产出 DSPy 可行性评估（与现有两套 LLM 客户端 + Instructor 的整合成本/收益）。
2. IF 评估值得落地, THEN SHALL 选 1 个高频 prompt 场景做 DSPy PoC 样板，输出与原 prompt 等价性对比。
3. THE DSPy Signature 输出 SHOULD 可对接 spec `llm-structured-output` 的 Pydantic response_model。
4. WHERE 整合成本过高, THE 模块 SHALL 仅留评估文档，不强制落代码。

### Requirement 6: 独立可取舍

#### Acceptance Criteria
1. 五个模块 SHALL 互相独立，任一裁剪不影响其他。
2. THE 优先级 SHALL 为 gitleaks > SQLFluff > uv > Docling > DSPy。

### Requirement 7: 跨 spec 打包体积回归（本 spec 统一承载）

**User Story:** As a 运维, I want 5 个 spec 累计新增依赖不显著拖累打包体积/启动, so that 本地优先轻量原则不被破坏。

#### Acceptance Criteria
1. THE 系统 SHALL 在 5 spec 依赖全部落定后，跑一次 `build_exe.py` 打包，对比引入前的产物体积 + 冷启动时间。
2. WHEN 体积/启动增幅超阈值（如 +30%）, THE 系统 SHALL 评估将重依赖设为可选 extra 或懒加载（OTel 仅 `OTEL_ENABLED` 时 import / docling 默认关 / bm25s 懒加载）。
3. THE 检查 SHALL 标 `[ ]*`（依赖前序 spec 实施完成 + PyInstaller 环境）。
