# Design: 开发工具链现代化（uv / Docling / gitleaks / SQLFluff / DSPy）

## Overview

五个独立的工具链改进合一个 spec，各为独立子任务、互不依赖、可单独取舍。按 ROI 与侵入度排序：gitleaks（安全，低侵入）→ SQLFluff（裸 SQL lint）→ uv（装包提速）→ Docling（扫描件 PDF 增强，markitdown 补充）→ DSPy（LLM prompt 工程化，中长期、最大投入）。

**定位**：这是"工具链卫生 + 长期可维护性"spec，不是业务功能。每个子任务可独立 ship，也可只做其中几个。

## 子模块设计

### 模块 A：gitleaks — secret 泄漏扫描（最高优先，低侵入）

现状：`.git-hooks/` 已有 pre-push（git 工作流 spec 产物），但无 secret 扫描；`.env` 在仓库根。

```
.git-hooks/pre-commit  →  gitleaks protect --staged
.github/workflows/     →  gitleaks CI job（push/PR 全量扫描）
.gitleaks.toml         →  规则配置 + allowlist（.env.example 占位符豁免）
```

- pre-commit 拦截：暂存区含 `sk-` / `ghp_` / `AKIA` / 私钥 / 数据库密码 等
- allowlist：`.env.example` 的占位符、测试 fixture 的假密钥
- 与现有 `.git-hooks/` 集成，不替换现有 pre-push
- 安装：gitleaks 是单二进制（Go），CI 用 official action，本地 hook 调本地二进制（缺失时 warning 不阻断，避免开发者环境差异卡死提交）

### 模块 B：SQLFluff — 裸 SQL lint

现状：大量裸 SQL（`test_raw_sql_schema_contract` / `test_raw_sql_column_contract` 守护的那批 + migrations/V*.sql）。

```
.sqlfluff           →  dialect=postgres + 规则集（缩进/关键字大小写/逗号风格）
target              →  backend/migrations/*.sql（迁移文件先行，风险最低）
CI                  →  sqlfluff lint（warning 级，不强卡，增量收敛）
```

- dialect=postgres（与 sqlglot pg_only 契约一致）
- 范围：先 lint `migrations/V*.sql` / `R*.sql`（独立文件，最适合）；service 内嵌 SQL 字符串暂不纳入（提取困难）
- 模式：先 `lint`（报告）不 `fix`（自动改写有风险），人工 review 后逐步收紧
- 与现有契约测试互补：契约测试管"SQL 引用的表/列存在"，SQLFluff 管"SQL 风格规范"

### 模块 C：uv — 依赖安装提速

现状：pip 装依赖；`build_exe.py`（PyInstaller）前置依赖准备阶段慢。

```
uv pip install -r requirements.txt    # 替代 pip install，10-100× 提速
```

- **保守接入**：uv 作为**可选加速器**，不强制改 venv 创建流程（memory.md：Python 3.12 仓库根 .venv）
- 不引入 `pyproject.toml` 迁移（现状 requirements.txt 体系保留，避免大改）
- 切入点：`build_exe.py` 依赖准备 + CI 装包步骤 + 文档说明"可用 uv pip install 加速"
- pin uv 版本（uv 迭代快）
- 降级：uv 不可用 → 回退 pip（命令层 try/fallback 或文档双写）

### 模块 D：Docling — 扫描件/复杂表格 PDF 增强（markitdown 补充）

现状：markitdown 已接入知识库上传（spec markitdown 收尾中）；扫描件 PDF 走 MinerU OCR 降级。

Docling（IBM 开源）对扫描件 PDF / 复杂表格的版面解析比 markitdown 准（但慢）。定位：**markitdown 输出空/质量差时的 PDF 增强档**，插入现有降级链：

```
知识库 _extract_text_with_ocr 降级链（现状）:
  MarkItDown → MinerU OCR(PDF) → PyPDF2/python-docx

加入 Docling 后:
  MarkItDown → Docling(PDF 复杂表格/扫描件) → MinerU OCR → PyPDF2/python-docx
```

- 仅 PDF 且 markitdown 输出不足时触发（避免 Docling 慢拖累正常文档）
- 配置开关 `DOCLING_ENABLED`（默认 False，按需开——Docling 依赖重，含 ML 模型）
- 与 MinerU 职责区分：Docling 偏版面/表格结构化，MinerU 偏 OCR；二者都是 PDF 增强，按可用性串联
- **风险提示**：Docling 依赖较重（torch/模型），评估是否与现有 onnxruntime/mineru 冲突——design 阶段标为"评估后决定是否纳入"，可能裁掉

### 模块 E：DSPy — LLM prompt 工程化（中长期，最大投入）

现状：审计 LLM prompt（B 控制了解 / D 销售收入等循环 + wp_llm_prompts/role_ai/pm）以字符串散落 service 内。

DSPy 把 prompt 当"可编译/可优化的程序"而非硬编码字符串：定义 Signature（输入→输出契约）+ Module，可对 prompt 做系统化优化与版本管理。

- **定位为探索性 PoC**，不全量迁移：选 1 个高频 prompt 场景（如某循环的 LLM 复核）做 DSPy 改造样板
- 与 spec-1（Instructor 结构化输出）协同：DSPy Signature 的输出可对接 Pydantic response_model
- 依赖本地 vLLM（DSPy 支持 OpenAI 兼容 endpoint）
- 风险：DSPy 学习曲线 + 与现有两套 LLM 客户端的整合成本——**标为最低优先，可只产出可行性评估文档不落代码**

## 配置

```python
DOCLING_ENABLED: bool = False   # PDF 复杂表格增强（依赖重，按需）
```

其余（gitleaks/sqlfluff/uv/dspy）为开发期工具，不入运行时 config。

## 跨 spec 依赖体积影响（本 spec 承载统一评估）

5 个 spec 累计向 `backend/requirements.txt` 引入：`instructor`+`openai`（spec-1）、`schemathesis`、`opentelemetry-*` 全家桶、`bm25s`（spec-4）、潜在 `docling`+torch（本 spec 组④）。memory.md 铁律"本地优先轻量方案"+ `build_exe.py` PyInstaller 打包对体积/启动时间敏感（markitdown 已带入 onnxruntime ~12MB+）。

本 spec 在收尾加一个**打包体积回归检查**：装全部新依赖后跑 `build_exe.py`，对比引入前的产物体积 + 冷启动时间，超阈值（如 +30%）则评估哪些依赖可设为可选 extra / 懒加载（如 OTel 仅 OTEL_ENABLED 时 import、docling 默认关）。

## Error Handling

| 场景 | 处理 |
|------|------|
| gitleaks 二进制缺失（本地） | hook warning 不阻断（CI 强卡兜底） |
| gitleaks 误报 | .gitleaks.toml allowlist |
| SQLFluff 大量存量告警 | warning 级 + 增量收敛，不一次性卡 CI |
| uv 不可用 | 回退 pip |
| Docling 依赖冲突/过重 | 评估后可裁掉（DOCLING_ENABLED 默认关，不影响主链路） |
| DSPy 整合成本高 | 降级为可行性文档，不强制落代码 |

## 测试策略

- gitleaks：CI job 自身即验证；造一个假 secret 验证拦截（测试后删）
- SQLFluff：CI lint 报告；不写额外测试
- uv：装包成功 + requirements 一致性（手工验证 + 文档）
- Docling：若纳入，补降级链单测（markitdown 空 → Docling → MinerU）；不纳入则只留评估结论
- DSPy：PoC 样板的输出与原 prompt 等价性对比（若落代码）；否则评估文档

## 与现有能力的关系

| 能力 | 复用 | 新增 |
|------|------|------|
| git hooks | `.git-hooks/pre-push` | pre-commit gitleaks |
| SQL 契约 | raw_sql contract 测试 | SQLFluff 风格 lint |
| 装包 | requirements.txt + .venv | uv 可选加速 |
| 文档转换 | markitdown + MinerU 降级链 | Docling PDF 增强档 |
| LLM prompt | 两套 LLM 客户端 + Instructor(spec-1) | DSPy PoC（探索） |
