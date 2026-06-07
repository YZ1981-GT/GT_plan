# uv 加速安装指南

## 什么是 uv

[uv](https://github.com/astral-sh/uv) 是 Astral（Ruff 作者团队）用 Rust 编写的 Python 包管理器，兼容 pip 接口，安装速度提升 10-100×。

本项目**仅将 uv 作为 pip 的可选加速替代**，不迁移 `pyproject.toml`，保留 `requirements.txt` 体系。

## 安装 uv

```bash
# 推荐 pip 安装（pin 版本 ≥0.7）
pip install "uv>=0.7"

# 或 pipx 全局安装
pipx install "uv>=0.7"
```

> **版本说明**：uv 迭代快，建议 pin `>=0.7` 以确保 `uv pip install --system` 等子命令稳定可用。

## 本项目用法

```bash
# 加速安装（uv 可用时）
uv pip install -r backend/requirements.txt

# uv 不可用时回退 pip
pip install -r backend/requirements.txt
```

带 fallback 的一行写法（CI / 脚本中推荐）：

```bash
uv pip install --system -r backend/requirements.txt || pip install -r backend/requirements.txt
```

## 注意事项

- **requirements.txt 体系保留**：不迁移到 `pyproject.toml`，uv 仅加速安装环节
- **运行时无影响**：uv 只加速包下载/安装，不影响 Python 运行时行为
- **虚拟环境内使用**：本地开发在 `.venv` 内直接 `uv pip install -r backend/requirements.txt`
- **CI 使用 `--system`**：GitHub Actions ubuntu-latest + `setup-python` 不默认创建 venv，需加 `--system` 标志
- **build_exe.py**：PyInstaller 打包前的依赖准备阶段亦可用 uv 加速（打包本身不受 uv 影响）。当前 build_exe.py 尚未建立，待打包脚本就位后，依赖准备阶段可直接替换为 `uv pip install -r backend/requirements.txt`（fallback pip），无需额外改造

## CI 集成模式

CI 中采用 uv 加速 + pip fallback 模式：

```yaml
- name: Install dependencies (uv accelerated)
  run: |
    pip install "uv>=0.7"
    uv pip install --system -r backend/requirements.txt || pip install -r backend/requirements.txt
```

若 uv 安装失败或 `uv pip install` 出错，自动回退 pip 保证 CI 不因 uv 问题挂掉。
