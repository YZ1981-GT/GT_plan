#!/bin/bash
# 部署步骤 2：后端依赖安装（pip install，幂等）
set -e
cd /opt/gt-new-plan
echo "--- venv 确认 ---"
.venv/bin/python --version
echo "--- pip install（升级式，已装的不动）---"
.venv/bin/pip install -r backend/requirements.txt -q --default-timeout=300 2>&1 | tail -5
echo "--- pip install 完成，抽查关键包 ---"
.venv/bin/python -c "import fastapi, sqlalchemy, openpyxl, jose; print('fastapi', fastapi.__version__)"
