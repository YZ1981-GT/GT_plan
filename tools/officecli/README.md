# OfficeCLI（Office 文档结构检查 / 渲染质检工具）

单二进制 CLI，读写并渲染 `.docx` / `.xlsx` / `.pptx`，无需安装 Office。用于**交付物质检与源模板对照**，不参与审计数值计算。

- 上游：<https://github.com/iOfficeAI/OfficeCLI>（Apache-2.0）
- 依赖仅 3 个且均 MIT：DocumentFormat.OpenXml（微软官方 SDK）、System.CommandLine、.NET Runtime（self-contained 打包）
- 无 headless 浏览器、无 LibreOffice、无遥测组件、**不执行 VBA 宏**

> **🔴 只用 `iOfficeAI/OfficeCLI`。** GitHub 上存在多个同名仿冒/镜像仓库；其中 `officecli/officecli` 是**另一个产品**（需 hosted trial + 外部 LLM endpoint，会联网），不可混用。本目录的 `officecli.lock.json` 已锁定上游仓库、版本与官方 SHA-256。

## 安装（拉取仓库后执行一次）

二进制约 32 MB，**不入库**（已在 `.gitignore` 忽略 `tools/officecli/bin/`）。按版本锁自动下载并校验 SHA-256：

```powershell
# Windows
powershell -NoProfile -ExecutionPolicy Bypass -File tools\officecli\install.ps1
```

```bash
# Linux / macOS（自动识别 glibc / musl(alpine) / arm64）
bash tools/officecli/install.sh
```

已安装且哈希匹配时脚本直接跳过；加 `-Force`（PS）或 `FORCE=1`（bash）可强制重装。校验失败会删除临时文件并非零退出，**不会留下未验证的二进制**。

装好后：`tools/officecli/bin/officecli.exe`（Windows）或 `tools/officecli/bin/officecli`。

## 升级版本

改 `officecli.lock.json` 的 `version` 与对应 `sha256`（从 release 的 `SHA256SUMS` 取），提交该文件，其他人重跑安装脚本即可。**不要**手动替换 bin 里的二进制。

## 🔴 关键约束：谁是版式权威

| 渲染路径 | 是否权威 | 说明 |
|---|---|---|
| `--render native`（Win + 已装 Word） | ✅ **权威** | 走真实 Word 渲染；`stats --page-count` 是 Word repagination 真实页数 |
| `--render html`（跨平台自研引擎） | ⚠️ 仅参考 | Linux 容器只有这条路径，分页可能与 Word 不一致 |
| OnlyOffice 在线预览 | ❌ **不是权威** | CJK 行高偏大，实测存在「预览 2 页、真实 Word 1 页」的差异 |
| MuPDF / PyMuPDF | ❌ 不是权威 | 对分节符处理较松，会合并页 |

**已实测案例（2026-07-26）**：审计报告封面在 OnlyOffice 预览是 2 页，下载后真实 Word 是 1 页。此前曾据 OnlyOffice 判断"落款被挤到第 2 页"并改了 32 个报告模板的落款行距 —— 后经 Word COM 复测，落款改前改后**都在第 1 页**、总页数都是 8，改后距正文底 97.4pt → 71.9pt（更贴页底），无回归。**结论：分页/版式问题一律以真实 Word 为准，不要为 OnlyOffice 预览差异改源模板。**

## 常用命令

```bash
officecli view <file> stats --page-count --json   # 真实页数（需 Win+Word）
officecli view <file> issues --json              # 结构/格式/内容问题
officecli view <file> text --json                # 纯文本（断言占位符残留用）
officecli query <file> <css-like-selector>       # 定位元素
officecli view <file> screenshot --render native --page 1 -o p1.png
officecli view <file> screenshot --render html --grid auto -o all.png
officecli validate <file>                        # OpenXML schema 校验
```

`view issues` 的可用子类型（`--type`）：`field_not_evaluated` / `field_cache_stale`（docx 域未计算）、`formula_not_evaluated` / `formula_cache_stale` / `formula_ref_missing_sheet` / `definedname_broken` / `chart_series_ref_missing_sheet`（xlsx）、`low_contrast` / `broken_part_ref`（pptx）。

## 适用场景

可进 CI（不依赖 Word）：

1. **交付物质检**：断言导出 docx 无 `{{...}}` / `【...】` 占位符残留、表格数量符合预期、每张表行数 > 0、关键列头逐字匹配
2. **附注 Word 导出回归**：锁定 `note_word_exporter` 的表头投影结果（如第 N 张表列头 = `项目 / 本期发生额 / 上期发生额`）
3. **xlsx 体检**：`formula_not_evaluated` 验证交付导出已把公式压成静态值；`definedname_broken` / `formula_ref_missing_sheet` 批量体检 `wp_templates/`
4. **源模板对照取数**：替代一次性 openpyxl 脚本，用 `view text --range` / `query --json` 直接拿 sheet 结构
5. **word-template 占位符清单**：扫全量模板，防新增模板漏接占位符

只能在有 Word 的 Windows 机器上做：

6. **权威分页判定** / **OnlyOffice 预览差异基线**（同时跑 `--render native` 与 `--render html` 对比）

## 边界（不要越线）

- **不替换** OnlyOffice：在线协同编辑与 WOPI 回写仍走 OnlyOffice
- **不替换** openpyxl / python-docx：文档生成侧不变
- **绝不**让它的 xlsx calc engine 参与审计数值 —— 报表/试算表/审定表的计算链（`report_engine` / `formula_engine` / `trial_balance` recalc）是自研单一真源，第三方引擎不进这条链
- **渲染出的 PNG 需要人眼判断**：AI 只能自动化结构化输出（`text` / `query` / `issues` / `--page-count`），"渲染成图让 AI 检查版式"不成立
