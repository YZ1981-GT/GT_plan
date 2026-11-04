"""离屏披露手工触发：拉起 Node 执行器的服务与端点（spec note-disclosure-pull-regression-and-headless-backend 任务 13，
design §5.2 / §5.4）。

子进程换成假进程（``_spawn`` 那一层），其余照生产跑：令牌真签发、真解码，env 真构造，黑名单写进 fakeredis。端点用权限世界
（SQLite）真发请求：门禁照常判定，断言子进程拉起时会话已不在事务里、各类失败映射到约定的状态码。五种身份的放行 / 拒绝
由 ``test_note_edit_gate_endpoints``（配方 C1）覆盖。
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import fakeredis.aioredis
import pytest
import pytest_asyncio

from app.core.security import decode_token
from app.routers import note_headless_refresh
from app.services import note_headless_refresh_service as svc
from tests.authz_world import TARGET_PROJECT_ID, sqlite_world

PROJECT_ID = uuid.UUID("6f1c2a5e-0d4b-4e2f-9a71-3c8b5d2e9f10")
USER_ID = uuid.UUID("0b7e5d1a-6c2f-4a83-9e14-7d5c3b2a1f09")
API = "http://127.0.0.1:9980"
RESULT = {"ok": True, "stage": "done", "outcomes": [{"wpCode": "D2", "section": "五、5", "status": "synced", "rows": 12}],
          "pending": [], "push": {"ran": True}, "push_error": None, "refresh": {"refreshed": 3}}


class _Proc:
    """一次拉起的假子进程：按自己的 ``--out`` 写结果。"""

    def __init__(self, owner: "FakeChild", args: list[str]):
        self.owner, self.args, self.pid, self.returncode = owner, args, 4242, None

    async def communicate(self):
        owner = self.owner
        if owner.hang is not None:
            await owner.hang.wait()
        if owner.result is not None:
            out = Path(self.args[self.args.index("--out") + 1])
            out.write_text(json.dumps(owner.result, ensure_ascii=False), encoding="utf-8")
        self.returncode = owner.code
        return b"", owner.stderr


class FakeChild:
    """假执行器：记下每次拉起的实参与 env，按 ``--out`` 写结果、回 stderr。"""

    def __init__(self, *, result=RESULT, returncode=0, stderr=b"", hang: asyncio.Event | None = None, on_spawn=None):
        self.result, self.code, self.stderr, self.hang, self.on_spawn = result, returncode, stderr, hang, on_spawn
        self.calls: list[dict] = []

    async def spawn(self, *args, **kwargs):
        self.calls.append({"args": list(args), **kwargs})
        if self.on_spawn:
            self.on_spawn()
        return _Proc(self, list(args))


@pytest.fixture
def runner(tmp_path, monkeypatch):
    """假执行器目录（run.mjs + dist/entry.mjs）、假 Node 路径、fakeredis 作黑名单；``killed`` 记下终止过的假进程。"""
    root = tmp_path / "frontend" / "tools" / "headless-disclosure"
    (root / "dist").mkdir(parents=True)
    (root / "run.mjs").write_text("// fake", encoding="utf-8")
    (root / "dist" / "entry.mjs").write_text("// fake", encoding="utf-8")
    monkeypatch.setattr(svc, "RUNNER_DIR", root)
    monkeypatch.setattr(svc.shutil, "which", lambda name: "C:/fake/node.exe" if name == "node" else None)
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    import app.core.redis as core_redis

    monkeypatch.setattr(core_redis, "redis_client", redis)
    monkeypatch.setattr(svc, "_running", set())
    killed: list[int] = []

    async def kill(proc):  # 假进程的 pid 不是真进程：任何路径都不许对它发 taskkill
        killed.append(proc.pid)

    monkeypatch.setattr(svc, "_kill_tree", kill)
    return SimpleNamespace(root=root, redis=redis, killed=killed)


def _use(monkeypatch, child: FakeChild) -> FakeChild:
    monkeypatch.setattr(svc, "_spawn", child.spawn)
    return child


async def _run(**kw):
    params = {"project_id": PROJECT_ID, "year": 2025, "user_id": USER_ID, "section": None, "api_base": API, **kw}
    return await svc.run_headless_refresh(**params)


@pytest.mark.asyncio
async def test_child_gets_scoped_env_and_short_lived_token_of_the_trigger_user(runner, monkeypatch):
    root, redis = runner.root, runner.redis
    monkeypatch.setenv("DATABASE_URL", "postgresql://secret@db/x")
    monkeypatch.setenv("JWT_SECRET_KEY", "platform-secret")
    child = _use(monkeypatch, FakeChild())
    started = time.time()
    result = await _run(section="五、5", timeout=120)

    call = child.calls[0]
    args = call["args"]
    assert args[:3] == ["C:/fake/node.exe", str(root / "run.mjs"), "refresh"]
    assert args[3:9] == ["--project", str(PROJECT_ID), "--year", "2025", "--section", "五、5"]
    assert args[9] == "--out" and len(args) == 11
    assert call["cwd"] == str(root.parents[1]), "在前端目录下跑（解析前端 node_modules）"
    env = call["env"]
    assert "DATABASE_URL" not in env and "JWT_SECRET_KEY" not in env, "env 从零构造，平台进程的数据库 / 密钥不进子进程"
    assert set(env) <= {"GT_HEADLESS_TOKEN", "GT_HEADLESS_API_BASE", "NODE_ENV", "NO_COLOR", "PATH", "SYSTEMROOT", "TEMP",
                        "TMP", "APPDATA", "LOCALAPPDATA", "HOME", "USERPROFILE"}
    assert env["GT_HEADLESS_API_BASE"] == API
    token = env["GT_HEADLESS_TOKEN"]
    claims = decode_token(token)
    assert claims["sub"] == str(USER_ID) and claims["type"] == "access" and claims["purpose"] == svc.TOKEN_PURPOSE
    assert claims["exp"] <= started + 120 + svc.TOKEN_GRACE_SECONDS + 5, "令牌有效期 = 超时 + 余量，不是登录令牌的 24 小时"
    assert all(token not in a for a in args), "令牌不进命令行"
    assert token not in json.dumps(result, ensure_ascii=False), "令牌不进返回值"

    assert result["ok"] is True and result["outcomes"] == RESULT["outcomes"] and result["refresh"] == {"refreshed": 3}
    assert (result["project_id"], result["year"], result["section"]) == (str(PROJECT_ID), 2025, "五、5")
    assert isinstance(result["elapsed_ms"], int)
    ttl = await redis.ttl(f"blacklist:{token}")
    assert 0 < ttl <= 120 + svc.TOKEN_GRACE_SECONDS, "跑完即吊销（get_current_user 查的同一个黑名单键）"
    assert not svc._running, "跑完释放项目锁"


@pytest.mark.asyncio
async def test_whole_refresh_passes_no_section(runner, monkeypatch):
    child = _use(monkeypatch, FakeChild())
    await _run()
    args = child.calls[0]["args"]
    assert "--section" not in args and args[3:7] == ["--project", str(PROJECT_ID), "--year", "2025"]


@pytest.mark.asyncio
async def test_error_exit_is_failed_and_token_is_masked(runner, monkeypatch):
    redis = runner.redis
    child = FakeChild(result=None, returncode=1)
    _use(monkeypatch, child)

    def leak_token():  # 子进程即使把令牌打进 stderr，错误信息里也抹掉
        child.stderr = ("Error: boom " + child.calls[-1]["env"]["GT_HEADLESS_TOKEN"]).encode()

    child.on_spawn = leak_token
    with pytest.raises(svc.HeadlessRefreshFailed) as info:
        await _run()
    token = child.calls[0]["env"]["GT_HEADLESS_TOKEN"]
    assert "退出码 1" in str(info.value) and "boom ***" in str(info.value) and token not in str(info.value)
    assert await redis.exists(f"blacklist:{token}"), "失败也吊销"
    assert not svc._running


@pytest.mark.asyncio
async def test_stale_build_exit_code_is_unavailable(runner, monkeypatch):
    _use(monkeypatch, FakeChild(result=None, returncode=svc.EXIT_BUILD_STALE,
                                stderr="[headless-disclosure] 离屏执行器构建产物已过期：构建后有 2 个源文件改动".encode()))
    with pytest.raises(svc.HeadlessRefreshUnavailable, match="构建产物已过期"):
        await _run()


@pytest.mark.asyncio
async def test_missing_result_file_is_failed(runner, monkeypatch):
    _use(monkeypatch, FakeChild(result=None, returncode=0))
    with pytest.raises(svc.HeadlessRefreshFailed, match="没有给出可读的结果"):
        await _run()


@pytest.mark.asyncio
async def test_timeout_kills_the_child_tree(runner, monkeypatch):
    _use(monkeypatch, FakeChild(hang=asyncio.Event()))
    with pytest.raises(svc.HeadlessRefreshTimeout, match="已终止"):
        await _run(timeout=0.05)
    assert runner.killed == [4242] and not svc._running


@pytest.mark.asyncio
async def test_cancelled_request_kills_the_child_and_revokes(runner, monkeypatch):
    """客户端断开（请求任务被取消）：子进程树终止、令牌吊销、锁释放。"""
    redis = runner.redis
    child = _use(monkeypatch, FakeChild(hang=asyncio.Event()))
    task = asyncio.create_task(_run())
    while not child.calls:
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    token = child.calls[0]["env"]["GT_HEADLESS_TOKEN"]
    assert runner.killed == [4242] and await redis.exists(f"blacklist:{token}") and not svc._running


@pytest.mark.asyncio
async def test_same_project_year_runs_one_at_a_time(runner, monkeypatch):
    gate = asyncio.Event()
    child = _use(monkeypatch, FakeChild(hang=gate))
    first = asyncio.create_task(_run())
    while not child.calls:
        await asyncio.sleep(0)
    # 互斥失效时第二次会拉起子进程并一直挂着：限时等待，失败即红、不挂死
    with pytest.raises(svc.HeadlessRefreshBusy, match="正在运行"):
        await asyncio.wait_for(_run(), timeout=2)
    other = asyncio.create_task(_run(project_id=uuid.uuid4()))  # 别的项目照常
    while len(child.calls) < 2:
        await asyncio.sleep(0)
    with pytest.raises(svc.HeadlessRefreshBusy, match="上限"):
        await asyncio.wait_for(_run(project_id=uuid.uuid4()), timeout=2)
    gate.set()
    assert (await first)["ok"] is True and (await other)["ok"] is True
    assert len(child.calls) == 2 and not svc._running


@pytest.mark.asyncio
async def test_unavailable_without_node_or_build(runner, monkeypatch):
    root = runner.root
    _use(monkeypatch, FakeChild())
    monkeypatch.setattr(svc.shutil, "which", lambda name: None)
    with pytest.raises(svc.HeadlessRefreshUnavailable, match="Node"):
        await _run()
    monkeypatch.setattr(svc.shutil, "which", lambda name: "C:/fake/node.exe")
    (root / "dist" / "entry.mjs").unlink()
    with pytest.raises(svc.HeadlessRefreshUnavailable, match="尚未构建"):
        await _run()


@pytest.mark.asyncio
@pytest.mark.parametrize("base", ["http://10.0.0.1:9980", "https://127.0.0.1:9980", "http://127.0.0.1"])
async def test_api_base_must_be_loopback_http_with_port(runner, monkeypatch, base):
    child = _use(monkeypatch, FakeChild())
    with pytest.raises(ValueError, match="环回"):
        await _run(api_base=base)
    assert not child.calls


def test_loopback_api_base_uses_the_serving_port():
    assert svc.loopback_api_base(("0.0.0.0", 9985)) == "http://127.0.0.1:9985"
    assert svc.loopback_api_base(None, default_port=9980) == "http://127.0.0.1:9980"


# ─── 端点 ─────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def world(monkeypatch):
    async with sqlite_world(monkeypatch) as w:
        yield w


_URL = f"/api/disclosure-notes/{TARGET_PROJECT_ID}/2025/headless-refresh"


@pytest.mark.asyncio
async def test_endpoint_commits_before_spawning_and_runs_as_the_caller(world, runner, monkeypatch):
    identity = await world.edit_member()
    seen: dict = {}
    child = FakeChild(on_spawn=lambda: seen.update(in_tx=world.db.in_transaction()))
    _use(monkeypatch, child)
    async with world.client(note_headless_refresh.router, user=identity.user) as client:
        resp = await client.post(_URL, params={"note_section": "五、5"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    body = body.get("data", body)
    assert body["ok"] is True and body["section"] == "五、5"
    assert seen == {"in_tx": False}, "子进程跑几十秒：拉起前门禁查询的事务必须已结束（不占连接）"
    claims = decode_token(child.calls[0]["env"]["GT_HEADLESS_TOKEN"])
    assert claims["sub"] == str(identity.user.id), "子进程以触发人本人的身份发请求"
    assert child.calls[0]["env"]["GT_HEADLESS_API_BASE"].startswith("http://127.0.0.1:")


@pytest.mark.asyncio
@pytest.mark.parametrize(("error", "status"), [
    (svc.HeadlessRefreshBusy("正在运行"), 409),
    (svc.HeadlessRefreshUnavailable("尚未构建"), 503),
    (svc.HeadlessRefreshTimeout("超时"), 504),
    (svc.HeadlessRefreshFailed("出错"), 502),
])
async def test_endpoint_maps_failures(world, runner, monkeypatch, error, status):
    identity = await world.edit_member()

    async def fail(**_kw):
        raise error

    monkeypatch.setattr(svc, "run_headless_refresh", fail)
    async with world.client(note_headless_refresh.router, user=identity.user) as client:
        resp = await client.post(_URL)
    assert resp.status_code == status, resp.text
    assert str(error) in resp.text


@pytest.mark.asyncio
async def test_endpoint_rejects_overlong_section(world, runner, monkeypatch):
    identity = await world.edit_member()
    child = _use(monkeypatch, FakeChild())
    async with world.client(note_headless_refresh.router, user=identity.user) as client:
        resp = await client.post(_URL, params={"note_section": "五" * 65})
    assert resp.status_code == 422 and not child.calls


# ─── 命令行（scripts/ops/note_headless_refresh.py）────────────────────────────


def _load_cli():
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "scripts" / "ops" / "note_headless_refresh.py"
    spec = importlib.util.spec_from_file_location("note_headless_refresh_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_cli_runs_as_the_named_user_after_the_same_gate(world, runner, monkeypatch, capsys):
    from contextlib import asynccontextmanager

    cli = _load_cli()

    @asynccontextmanager
    async def session():
        yield world.db

    monkeypatch.setattr(cli, "async_session", session)
    child = _use(monkeypatch, FakeChild())
    member = await world.edit_member()
    outsider = await world.non_member()

    args = cli.parse_args(["--project", str(TARGET_PROJECT_ID), "--year", "2025", "--user", member.user.username])
    assert await cli.run(args) == cli.EXIT_OK
    assert decode_token(child.calls[0]["env"]["GT_HEADLESS_TOKEN"])["sub"] == str(member.user.id)
    assert json.loads(capsys.readouterr().out)["ok"] is True

    args = cli.parse_args(["--project", str(TARGET_PROJECT_ID), "--year", "2025", "--user", outsider.user.username])
    assert await cli.run(args) == cli.EXIT_DENIED, "门禁与端点相同：非成员不能刷"
    assert len(child.calls) == 1, "门禁不通过不拉起执行器"
    args = cli.parse_args(["--project", str(TARGET_PROJECT_ID), "--year", "2025", "--user", "没有这个人"])
    assert await cli.run(args) == cli.EXIT_DENIED and len(child.calls) == 1

    monkeypatch.setattr(svc, "_spawn", FakeChild(result={**RESULT, "ok": False}).spawn)
    args = cli.parse_args(["--project", str(TARGET_PROJECT_ID), "--year", "2025", "--user", member.user.username])
    assert await cli.run(args) == cli.EXIT_FAILED, "跑完但结果 ok 为假 ⇒ 非零退出"
