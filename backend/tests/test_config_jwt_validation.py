"""Q5: 生产环境强制校验 JWT_SECRET_KEY 的 unit test。

用 subprocess 隔离测试，因 config.py 的 raise 是 module-level 执行，
在 pytest 同一进程内会污染。
"""
import subprocess
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent.parent


def _run_config_import(env: dict) -> tuple[int, str]:
    """用子进程 import config 返回 exitcode + stderr。"""
    result = subprocess.run(
        [sys.executable, "-c", "from app.core.config import settings; print('OK')"],
        capture_output=True, text=True, env={**env}, cwd=str(BACKEND_DIR),
    )
    return result.returncode, result.stderr + result.stdout


def test_dev_weak_key_warns_but_allows():
    """dev 模式默认弱密钥只告警不阻止启动。"""
    import os
    env = {
        **os.environ,
        "APP_ENV": "dev",
        # 不设 JWT_SECRET_KEY 走默认
    }
    env.pop("JWT_SECRET_KEY", None)
    code, out = _run_config_import(env)
    assert code == 0, f"dev 模式应启动成功，实际 exit={code}, output={out[:500]}"
    assert "OK" in out


def test_production_weak_key_raises():
    """production 模式弱密钥必须 raise，阻止启动。"""
    import os
    env = {
        **os.environ,
        "APP_ENV": "production",
    }
    env.pop("JWT_SECRET_KEY", None)
    code, out = _run_config_import(env)
    assert code != 0, "production + 弱密钥应启动失败"
    assert "APP_ENV=production" in out
    assert "JWT_SECRET_KEY" in out


def test_production_strong_key_allows():
    """production 模式 + 强密钥应正常启动。"""
    import os
    env = {
        **os.environ,
        "APP_ENV": "production",
        "JWT_SECRET_KEY": "a-very-strong-random-secret-32chars-minimum-length",
    }
    code, out = _run_config_import(env)
    assert code == 0, f"production + 强密钥应启动成功，实际 exit={code}, output={out[:500]}"
    assert "OK" in out


def test_staging_weak_key_allows():
    """staging 模式只告警（和 dev 一致），方便应急使用弱密钥。"""
    import os
    env = {
        **os.environ,
        "APP_ENV": "staging",
    }
    env.pop("JWT_SECRET_KEY", None)
    code, out = _run_config_import(env)
    assert code == 0
    assert "OK" in out
