"""Backend test environment configuration. Validates: Requirements 2.8"""
import os
from collections.abc import AsyncGenerator
#: pytest 启动时的环境变量（本文件最先被导入）。起子进程跑 pytest 的用例用它，不继承之后被改过的环境 ——
#: 如 tests/e2e/conftest.py 导入时 setdefault 的 sqlite DATABASE_URL，子进程导入本文件时建引擎即 TypeError。
ENVIRON_AT_START: dict[str, str] = dict(os.environ)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")
# 🔴 load_test.py 是 locust 压测脚本（无测试函数），但文件名命中 pytest 默认的 `*_test.py` 会被收集：
#    `import locust` 即 `gevent.monkey.patch_all()`，把整个 pytest 进程的 threading / socket / select / time 换成
#    gevent 版，此后 TestClient（anyio 线程门户）与 asyncio 用例会卡死，全量 `pytest tests` 跑不完。
#    压测脚本照旧 `locust -f backend/tests/load_test.py` 运行（守卫 test_pytest_import_isolation.py）。
collect_ignore = ["load_test.py"]

# ─── Hypothesis 全局「fast」profile：减少 example 数量、加快属性测试 ──────────────
# 统一把 PBT 的 max_examples 收敛到较小值（默认 5，可用 HYPOTHESIS_MAX_EXAMPLES 覆盖），
# 关闭 deadline 并抑制「输入生成过慢 / 数据过大」健康检查（此前偶发 FailedHealthCheck
# 导致 test_audit_throttle 等用例不稳定）。注意：单个测试用 @settings(max_examples=N)
# 显式指定的值优先于本 profile，故此处只降低未显式配置用例的开销并保证稳定。
try:  # pragma: no cover - 测试环境配置
    from hypothesis import HealthCheck, settings as _hyp_settings

    _HYP_MAX_EXAMPLES = int(os.environ.get("HYPOTHESIS_MAX_EXAMPLES", "5"))
    # Feature: procedure-delegation-visibility-isolation Task 14 —— 同源双 profile 机制。
    # smoke（=5，本地快速冒烟，不得作为完成证据）与 correctness（≥100 有效样例/property，
    # CI 正确性验收）收集**同一批**属性函数：property 测试不再硬编码 max_examples，改由
    # 当前加载 profile 驱动例数（`@settings(deadline=None)` 只固定 deadline，max_examples
    # 继承活动 profile）。三者共享同一 health-check 抑制集，语义仅差 max_examples。
    _CORRECTNESS_EXAMPLES = int(os.environ.get("HYPOTHESIS_CORRECTNESS_EXAMPLES", "100"))
    _SUPPRESS = [
        HealthCheck.too_slow,
        HealthCheck.data_too_large,
        HealthCheck.function_scoped_fixture,
    ]
    _hyp_settings.register_profile(
        "fast", max_examples=_HYP_MAX_EXAMPLES, deadline=None, suppress_health_check=_SUPPRESS,
    )
    _hyp_settings.register_profile(
        "smoke", max_examples=5, deadline=None, suppress_health_check=_SUPPRESS,
    )
    _hyp_settings.register_profile(
        "correctness", max_examples=_CORRECTNESS_EXAMPLES, deadline=None,
        suppress_health_check=_SUPPRESS,
    )
    _hyp_settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "fast"))
except Exception:  # hypothesis 未安装或版本差异时不阻断测试收集
    pass

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from app.core.database import get_db  # noqa: E402
from app.core.redis import get_redis  # noqa: E402
from app.models.base import Base  # noqa: E402

#: ``fakeredis`` 是**可选**测试依赖：全量 requirements 里有它，但几十个 governance
#: job 只 `pip install pytest`（+openpyxl），装不到它。conftest 顶层硬 import 会让
#: 这些 job 在收集阶段就 ``ModuleNotFoundError`` ⇒ 整片门禁假红（2026-11-14 实测
#: 102/183 个 job 因此失败）。
#:
#: 本文件对它的唯一用法是按模块名判断「用例是否把 redis 换成了 fakeredis」
#: （见下方 ``_is_fake_redis``），不需要真的 import 它。故这里降级为软探测：
#: 装了就记下模块名，没装就只影响「假 redis 不写共享链路」那条守卫的可用性，
#: 其余测试不受影响。
try:  # pragma: no cover - 环境探测
    import fakeredis.aioredis  # noqa: F401,E402
    _FAKEREDIS_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - 精简依赖环境
    _FAKEREDIS_AVAILABLE = False

# ─── 模型注册：自动导入 app.models 全部子模块 ────────────────────────────────────
# 🔴 原先是 44 行显式 import 清单，漏一个模块就让 `Base.metadata.create_all` 在解析跨模块外键时
#    抛 NoReferencedTableError，而报错指向的是**引用方**的表，根因（被引用模块没注册）不在信息里。
#    实测代价：清单漏 `asset_blob_models` ⇒ `attachment_versions.blob_id → asset_blobs.id` 解析失败
#    ⇒ 合并附注子树汇总等 22 个用例全部 ERROR。清单里第 71 行原本就留着同类事故的注释
#    （evidence_governance_models 漏序曾阻断全套 DB 集成测试）—— 同一个坑踩了两次。
#    现算对比：显式清单 44 模块 / 332 表（无 asset_blobs）；本写法 111 模块 / 365 表，是严格超集。
#
# 故意不加 try/except：某个模型模块 import 失败时必须当场炸，静默跳过就是重现「漏注册」本身。
# 仓库已有同写法先例（test_model_server_default_portability.py 等）。
# spec: note-disclosure-pull-regression-and-headless-backend 任务 1（R2.4）
import importlib  # noqa: E402
import pkgutil  # noqa: E402

import app.models as _models_pkg  # noqa: E402

for _model_module in pkgutil.walk_packages(_models_pkg.__path__, prefix="app.models."):
    importlib.import_module(_model_module.name)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid
# PG ARRAY 类型 → SQLite TEXT 兜底（避免 CompileError: can't render element of type ARRAY）
# 实际查询里 ARRAY 列只读不写就足够，写入需求由真实 PG 测试覆盖
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


# ---------------------------------------------------------------------------
# Evidence-governance aggregation marker (Task 8.3)
#
# Spec: attachment-ocr-ai-evidence-governance-hardening
# Single aggregation entrypoint for the whole evidence-governance backend suite:
#     python -m pytest -m evidence_governance
# Membership is decided by:
#   1) path — files under tests/evidence_governance/, tests/test_evidence_governance_*.py,
#      or tests/attachment_ocr_ai_evidence_governance_hardening/ (the named wave locations); OR
#   2) content — any test file that embeds the spec slug
#      "attachment-ocr-ai-evidence-governance-hardening" in its header (wave 3/4/5
#      ref/OCR/AI files such as test_evidence_ref_*, test_ocr_governance_*,
#      test_ocr_retry_service_task5_2, test_ai_evidence_gate, etc.).
# This auto-discovers spec files (including future ones) without hardcoding a
# fragile list, and never fake-greens: it only tags existing tests.
# ---------------------------------------------------------------------------

_EVIDENCE_GOVERNANCE_SLUG = "attachment-ocr-ai-evidence-governance-hardening"
_evidence_membership_cache: dict[str, bool] = {}


def _is_evidence_governance_file(path_str: str) -> bool:
    """Return True if the test file belongs to the evidence-governance spec."""
    cached = _evidence_membership_cache.get(path_str)
    if cached is not None:
        return cached
    norm = path_str.replace("\\", "/")
    result = False
    # 1) named wave locations by path
    if (
        "/tests/evidence_governance/" in norm
        or "/tests/attachment_ocr_ai_evidence_governance_hardening/" in norm
    ):
        result = True
    else:
        base = norm.rsplit("/", 1)[-1]
        if base.startswith("test_evidence_governance_"):
            result = True
        else:
            # 2) related wave files by embedded spec slug
            try:
                from pathlib import Path as _P

                head = _P(path_str).read_text(encoding="utf-8", errors="ignore")[:4000]
                result = _EVIDENCE_GOVERNANCE_SLUG in head
            except Exception:
                result = False
    _evidence_membership_cache[path_str] = result
    return result


def pytest_collection_modifyitems(config, items):
    """Skip pg_only tests when DATABASE_URL is not PostgreSQL, and tag the
    evidence-governance aggregation suite (Task 8.3).

    spec procedure-chain-hardening-and-java-contracts R20：PG 判定认 ``postgres://``（原先只认含 ``postgresql`` 的地址）；
    设 ``GT_REQUIRE_PG=1`` 时地址不是 PG 而收集到了 pg_only 用例 ⇒ ``UsageError``，不再静默跳过。
    """
    from tests._pg_url import is_pg_url, pg_requirement_error

    db_url = os.getenv("DATABASE_URL", "sqlite")
    error = pg_requirement_error(db_url, os.getenv("GT_REQUIRE_PG"),
                                 [item.nodeid for item in items if "pg_only" in item.keywords])
    if error:
        raise pytest.UsageError(error)
    skip_pg = pytest.mark.skip(reason="requires PostgreSQL")
    tag_pg = not is_pg_url(db_url)
    for item in items:
        if tag_pg and "pg_only" in item.keywords:
            item.add_marker(skip_pg)
        try:
            fspath = str(getattr(item, "fspath", "") or "")
            if fspath and _is_evidence_governance_file(fspath):
                item.add_marker(pytest.mark.evidence_governance)
        except Exception:
            pass


def pytest_configure(config):
    """登记「用例不得改写已跟踪文件」守卫（详见 tests/_tracked_write_guard.py）。"""
    from tests import _tracked_write_guard as _guard

    if not config.pluginmanager.is_registered(_guard):
        config.pluginmanager.register(_guard, _guard.PLUGIN_NAME)


def pytest_collection_finish(session):
    """在最终选择集上执行全局收集期安全检查。

    ``pytest_collection_modifyitems`` 运行时，pytest 的 ``-m`` 过滤尚未必完成。
    写性能测试闸门必须放在这里，否则 ``-m 'pg_only and not perf'`` 也会先被未选中的
    ``perf`` 用例触发，导致 CI 的功能 PG job 在收集阶段退出码 4。
    """
    from tests._perf_gate import perf_write_gate_error

    db_url = os.getenv("DATABASE_URL", "sqlite")
    perf_error = perf_write_gate_error(
        db_url,
        os.environ,
        [item.nodeid for item in session.items
         if "perf" in item.keywords and "pg_only" in item.keywords],
    )
    if perf_error:
        raise pytest.UsageError(perf_error)

    # 收集阶段若有模块（直接或经辅助模块）触发了 gevent 猴子补丁，在跑任何用例之前就报错。
    # 补丁一旦打上，后续 TestClient / asyncio 用例会静默卡死；报错比挂起好查得多。
    import sys as _sys

    monkey = _sys.modules.get("gevent.monkey")
    if monkey is not None and monkey.is_module_patched("threading"):
        raise pytest.UsageError(
            "收集阶段有模块触发了 gevent.monkey.patch_all()（多半是导入了 locust），"
            "本进程的 threading / socket 已被替换，继续运行会卡死；"
            "把压测脚本加进 tests/conftest.py 的 collect_ignore，或别在测试模块里导入 locust。"
        )


# ---------------------------------------------------------------------------
# Task 4: 模型注册完整性测试
# ---------------------------------------------------------------------------

def test_all_models_registered():
    """反射遍历 backend/app/models/ 下所有 .py，断言每个继承 Base 的模型的
    __tablename__ 已注册到 Base.metadata.tables。

    Validates: Requirements 7 AC5
    """
    import ast
    from pathlib import Path

    models_dir = Path(__file__).resolve().parent.parent / "app" / "models"
    assert models_dir.exists(), f"models dir not found: {models_dir}"

    # 收集所有 .py 文件中继承 Base 的类及其 __tablename__
    expected_tables: dict[str, str] = {}  # tablename -> "file:class"

    for py_file in sorted(models_dir.glob("*.py")):
        if py_file.name.startswith("_") or py_file.name.endswith("_schemas.py"):
            continue
        # 跳过纯枚举文件（无 ORM 模型）
        if py_file.name.endswith("_enums.py"):
            continue

        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            # 检查是否继承 Base（直接或间接通过名称匹配）
            inherits_base = any(
                (isinstance(b, ast.Name) and b.id == "Base")
                or (isinstance(b, ast.Attribute) and b.attr == "Base")
                for b in node.bases
            )
            if not inherits_base:
                continue

            # 提取 __tablename__
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name) and target.id == "__tablename__":
                            if isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
                                expected_tables[item.value.value] = f"{py_file.name}:{node.name}"

    # 确保我们至少找到了一些模型（防止空集误判通过）
    assert len(expected_tables) > 10, (
        f"Only found {len(expected_tables)} models, expected many more. "
        f"Check AST parsing logic."
    )

    # 获取已注册的表名
    registered_tables = set(Base.metadata.tables.keys())

    # 断言每个模型的 __tablename__ 都已注册
    missing = {
        tbl: loc
        for tbl, loc in expected_tables.items()
        if tbl not in registered_tables
    }
    assert not missing, (
        f"以下模型的 __tablename__ 未注册到 Base.metadata.tables:\n"
        + "\n".join(f"  {tbl} (定义于 {loc})" for tbl, loc in sorted(missing.items()))
    )


# ─── 单例替身的 shadow 清理（跨文件污染防护）──────────────────────────────────
# 背景（实测踩过）：多处测试用
#   monkeypatch.setattr(ownership_guard, "assert_target_accessible", fake)
# 或「读出原绑定方法 → finally 赋回实例」的方式给**单例实例**打替身。两种写法在恢复时
# 都会往实例 ``__dict__`` 里留下一个同名属性（哪怕值就是原绑定方法）——
# monkeypatch 的 undo 是 ``setattr(实例, name, 保存的绑定方法)``，不是删除。
#
# 该残留属性会**遮蔽类属性**，于是之后任何
#   patch("app.routers.disclosure_notes.OwnershipGuard.assert_target_accessible")
# （类级替身）都打不上 —— 越权用例静默变成「真去查库」。症状是「单跑某文件全绿、
# 合跑时另一个文件里的 5 条 trace 用例莫名变红」，最难定位的一类假绿/假红。
#
# 逐处改成「patch 类」当然更正确，但那要求每个作者都记得；这里做一道兜底：每个测试
# 结束后把这类单例上的实例级覆盖删掉，回落到类属性。
# 配套结构守卫见 test_disclosure_notes_project_gate_contract.py
# ::TestOwnershipGuardPatchabilityNotShadowed。
_SINGLETON_SHADOW_TARGETS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "app.services.custom_query.ownership_guard",
        "ownership_guard",
        ("assert_target_accessible",),
    ),
)


@pytest.fixture(autouse=True)
def _drop_singleton_method_shadows():
    """测试结束后清掉单例上的实例级方法覆盖（详见上方注释）。"""
    yield
    import importlib

    for module_path, attr, methods in _SINGLETON_SHADOW_TARGETS:
        try:
            module = importlib.import_module(module_path)
        except Exception:  # pragma: no cover - 模块不可导入时无需清理
            continue
        singleton = getattr(module, attr, None)
        if singleton is None or not hasattr(singleton, "__dict__"):
            continue
        for method in methods:
            singleton.__dict__.pop(method, None)


# ─── 测试里的审计日志不进开发环境共享 Redis ─────────────────────────────────────────
# `audit_logger.log_action` 把条目推进 Redis 队列，由共享后端（9980）的审计 worker 写进共享库审计链。测试默认连的
# 正是那个 Redis ⇒ 测试条目被写进共享库的项目链，或因 user_id 不是 UUID 永久滞留隔离区、让健康端点一直 degraded
# （2026-11-04 实测两条假项目链 39 条 `user_id='user-001'`；spec enterprise-embedding-rerank-closure R9.3）。
# 这里把 `_get_redis` 包一层：用例把 `app.core.redis.redis_client` 换成 fakeredis 时照旧走原逻辑（可测队列），
# 否则返回 None（降级到进程内队列），一条都不进共享 Redis。用例自己按实例 / 类替换 `_get_redis` 的照旧优先。
def _is_fake_redis(client: object) -> bool:
    return type(client).__module__.split(".")[0] == "fakeredis"


@pytest.fixture(autouse=True)
def _audit_queue_stays_out_of_shared_redis(monkeypatch):
    from app.services.audit_logger_enhanced import AuditLoggerEnhanced

    original = AuditLoggerEnhanced._get_redis

    async def _guarded(self):
        import app.core.redis as core_redis

        if not _is_fake_redis(core_redis.redis_client):
            return None
        return await original(self)

    monkeypatch.setattr(AuditLoggerEnhanced, "_get_redis", _guarded)
