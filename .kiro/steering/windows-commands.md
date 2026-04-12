# Windows 命令执行规范

## Python 执行路径

在 Windows 上执行 Python 相关命令时：

- **始终使用 `python`** 而非 `python3`
- **禁止使用 `&&`** 连接多条命令。Windows 原生命令分隔符是 `;` 或换行。
  - ❌ `python -m pytest backend/tests/ && python -m mypy backend/`
  - ✅ `python -m pytest backend/tests/ ; python -m mypy backend/`
- 执行目录固定的命令时使用 `cwd` 参数，**禁止使用 `cd`** 切换目录：
  - ❌ `command: "cd backend && python -m pytest"`
  - ✅ `command: "python -m pytest"`, `cwd: "backend"`
- 长命令超时建议设为 `120000ms`（2分钟），以便完整测试套件运行

## Shell 类型

当前环境 `shell: bash`，但底层平台 `platform: win32`。执行外部命令时：

- CMD/PowerShell 命令可直接执行（如 `dir`, `Get-ChildItem`）
- Bash 命令在 Git Bash / WSL 环境下运行
- 混用时注意路径格式：`\`（CMD）vs `/`（Bash）

## 测试执行

- 运行 pytest：`python -m pytest`
- 运行单个测试文件：`python -m pytest backend/tests/test_file.py`
- 带详细输出：`python -m pytest backend/tests/ -v --tb=short`
- 使用 `;` 而非 `&&` 连接多个测试命令

## 文件操作

- Windows 不区分大小写路径，但代码中应保持一致的大小写
- 路径分隔符统一用 `/`（Python 自动处理）
