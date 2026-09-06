# -*- coding: utf-8 -*-
"""模板覆盖层解析判据 —— 零回归与多层优先级。

spec: .kiro/specs/excel-template-override-layer-and-onlyoffice-template-editor/
Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
Properties: 6, 7, 8

═══ Property 6 是本 spec 最重要的一条顺序约束 ═══

tasks.md Task 7 明写「**接线前必须先绿**」：先证明改解析器不产生回归，再动既有解析器
（Task 8 把三个公开入口改薄封装）。

做法是**真的把 HEAD 版本跑起来**逐条对比，而不是比对某份人工誊抄的期望值清单：

1. `git show HEAD:backend/app/services/wp_template_finder.py` 取 HEAD 源码
2. 加载成独立模块（并修正它按 `__file__` 推导的路径常量 —— tmp 目录会算错）
3. 对索引里全部 180 个 wp_code 逐个调用三个入口，逐条 `==`

⚠ 口径说明：只有 `wp_template_finder.py` 本身取 HEAD，它局部 import 的
`workpaper_sync.word_resolution` 仍是工作树版本。这是有意的 —— 本 spec 只改 finder，
把 word_resolution 也换成 HEAD 反而会把别人的在途改动算进我的回归。

═══ 分母（防判据在空集上恒真）═══

| 分母 | 值 |
|---|---|
| `_index.json` 条数 | 476 |
| 去重 wp_code 数（含 `_ref` 伪码） | 180 |
| 格式分布 | xlsx 349 / docx 107 / xlsm 17 / doc 2 / xls 1 |
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from app.services.wp_template_override import (
    CURRENT_STEM,
    OVERRIDE_ROOT,
    SCOPE_PRIORITY,
    TemplateResolution,
    resolve_all_templates,
    resolve_template,
    resolve_template_any,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_DIR = _REPO_ROOT / "backend"
_TEMPLATES_DIR = _BACKEND_DIR / "wp_templates"
_FINDER_REL = "backend/app/services/wp_template_finder.py"

_EXPECTED_INDEX_ENTRIES = 476
_EXPECTED_WP_CODES = 180
#: 索引外但生产/存量测试在用的 wp_code 数（见 `_off_index_wp_codes` 的派生规则）。
_EXPECTED_OFF_INDEX_CODES = 187
_EXPECTED_FORMAT_DISTRIBUTION = {
    "xlsx": 349, "docx": 107, "xlsm": 17, "doc": 2, "xls": 1,
}


def _load_index_entries() -> list[dict]:
    payload = json.loads((_TEMPLATES_DIR / "_index.json").read_text(encoding="utf-8"))
    return payload["files"]


def _all_wp_codes() -> list[str]:
    return sorted({e["wp_code"] for e in _load_index_entries()})


def _off_index_wp_codes() -> list[str]:
    """索引**外**但生产/存量测试在用的 wp_code。

    🔴 为什么必须单列：`_index.json` 的 `wp_code` 值域只有 180 个，而生产代码大量使用
    索引外的码 —— 程序表码（`D4` → `D4A`）、被拆出的主码（`D2-1` → `D2`）、G7 试点的
    `G7L` / `G7E`、自定义底稿 `ZZT26A` 等。只按索引取分母，接线是否改变了这些码的解析
    **测不出来**，而它们恰好是回退分支最密集的一批（`find_template_file_any` 的前缀
    回退、A 子码严格分支、范围式命名回退都在这里生效）。

    本函数机械派生，不手工誊抄清单：清单会随索引演进而过时。
    """
    derived: set[str] = set()
    for entry in _load_index_entries():
        code = entry["wp_code"]
        derived.add(f"{code}A")            # 程序表码：D4 → D4A
        if "-" in code:
            derived.add(code.split("-")[0])  # 子码 → 主码：D2-1 → D2
    # 存量测试/生产代码点名、但派生规则覆盖不到的：
    # * `D4A` / `F2A`  —— 程序表码（`test_wp_template_finder_d4_prefix.py`）
    # * `D4-1` / `F2-2` —— 范围式命名回退的边界用例（同上，`F2-2` 不得命中 `F2-29至F2-35`）
    # * `G7L` / `G7E`  —— G7 试点码，`pilot_g7_two_level_dynamic` 断言它们「零回退」
    # * `ZZT26A`       —— 自定义底稿（模板库里根本不存在）
    # * `B2-3`         —— Word 域双封沟通函（BP-19），一个 wp_code 对两份权威 docx
    # * `S33-REV`      —— 模板库零载体，`word_resolution` 拿它做 template_missing 用例
    derived.update({
        "D4A", "F2A", "D4-1", "F2-2", "G7L", "G7E", "ZZT26A", "B2-3", "S33-REV",
    })
    return sorted(derived - set(_all_wp_codes()))


@pytest.fixture(scope="module")
def head_finder():
    """HEAD 版本的 `wp_template_finder` 模块（路径常量已修正到真实 backend/）。"""
    proc = subprocess.run(
        ["git", "show", f"HEAD:{_FINDER_REL}"],
        cwd=_REPO_ROOT, capture_output=True, timeout=60,
    )
    if proc.returncode != 0:
        pytest.skip(f"无法从 HEAD 取 finder 源码：{proc.stderr.decode('utf-8', 'replace')[:200]}")

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        mod_path = Path(td) / "head_wp_template_finder.py"
        mod_path.write_bytes(proc.stdout)  # bytes 直写，不经解码/换行转换

        spec = importlib.util.spec_from_file_location(mod_path.stem, mod_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
            # 🔴 顶层按 `Path(__file__)` 推导的 BACKEND_DIR 指向 tmp 目录，必须修正，
            #    否则它读不到 _index.json，三个入口会齐刷刷返回 None ⇒ 判据在空集上恒真。
            module.BACKEND_DIR = _BACKEND_DIR
            module.TEMPLATES_DIR = _TEMPLATES_DIR
            module.INDEX_FILE = _TEMPLATES_DIR / "_index.json"
            module._index_cache = None
            assert module._load_index(), "HEAD 版 finder 读不到索引 —— 路径常量修正失败"
            yield module
        finally:
            sys.modules.pop(spec.name, None)


# ═══════════════════════════════════════════════════════════════════════════
# 分母
# ═══════════════════════════════════════════════════════════════════════════


class TestDenominators:
    def test_index_and_wp_code_counts(self):
        entries = _load_index_entries()
        assert len(entries) == _EXPECTED_INDEX_ENTRIES
        codes = _all_wp_codes()
        assert len(codes) == _EXPECTED_WP_CODES, (
            f"去重 wp_code 数 {len(codes)} != {_EXPECTED_WP_CODES} —— 零回归判据的分母变了"
        )
        by_fmt: dict[str, int] = {}
        for e in entries:
            by_fmt[e["format"]] = by_fmt.get(e["format"], 0) + 1
        assert by_fmt == _EXPECTED_FORMAT_DISTRIBUTION

    def test_head_finder_is_actually_loaded(self, head_finder):
        """HEAD 模块真的可用 —— 否则下面的逐条比对是在拿 None 比 None。"""
        assert head_finder.TEMPLATES_DIR == _TEMPLATES_DIR
        assert len(head_finder._load_index()) == _EXPECTED_INDEX_ENTRIES
        for fn in ("find_template_file", "find_all_template_files", "find_template_file_any"):
            assert callable(getattr(head_finder, fn)), f"HEAD 模块缺 {fn}"


# ═══════════════════════════════════════════════════════════════════════════
# Property 6 —— 覆盖层为空时解析零回归（Requirement 2.3）
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty6ZeroRegression:
    """覆盖层为空时，三个公开入口对 180 个 wp_code 的返回值与 HEAD 版本逐条相同。

    🔴 前置：本机 `OVERRIDE_ROOT` 必须为空（或不存在）。非空则跳过并说明 ——
    在有覆盖文件的机器上跑这条判据，"不同"是正确行为，不是回归。
    """

    @staticmethod
    def _require_empty_override_root():
        if OVERRIDE_ROOT.is_dir() and any(OVERRIDE_ROOT.iterdir()):
            pytest.skip(
                f"OVERRIDE_ROOT 非空（{OVERRIDE_ROOT}）—— 零回归判据要求覆盖层为空"
            )

    def test_find_template_file_zero_regression(self, head_finder):
        self._require_empty_override_root()
        from app.services import wp_template_finder as current

        diffs: list[str] = []
        compared = 0
        for code in _all_wp_codes():
            expected = head_finder.find_template_file(code)
            actual = current.find_template_file(code)
            compared += 1
            if expected != actual:
                diffs.append(f"{code}: HEAD={expected} 现={actual}")

        assert compared == _EXPECTED_WP_CODES
        assert not diffs, "find_template_file 出现回归：\n" + "\n".join(diffs[:20])

    def test_zero_regression_on_off_index_codes(self, head_finder):
        """索引**外**的 wp_code 同样零回归 —— 补 180 个分母的覆盖面盲区。

        这批码走的正是回退分支最密集的路径（前缀回退 / A 子码严格分支 /
        范围式命名回退），只测索引内的码等于放过它们。
        """
        self._require_empty_override_root()
        from app.services import wp_template_finder as current

        codes = _off_index_wp_codes()
        assert len(codes) == _EXPECTED_OFF_INDEX_CODES, (
            f"索引外 wp_code 数 {len(codes)} != {_EXPECTED_OFF_INDEX_CODES} —— 分母变了"
        )

        entries = (
            ("find_template_file", "find_template_file"),
            ("find_all_template_files", "find_all_template_files"),
            ("find_template_file_any", "find_template_file_any"),
        )
        diffs: list[str] = []
        resolved_total = 0
        for head_name, cur_name in entries:
            head_fn = getattr(head_finder, head_name)
            cur_fn = getattr(current, cur_name)
            for code in codes:
                expected = head_fn(code)
                actual = cur_fn(code)
                if expected:
                    resolved_total += 1
                if expected != actual:
                    diffs.append(f"{cur_name}({code}): HEAD={expected} 现={actual}")

        assert not diffs, "索引外 wp_code 出现回归：\n" + "\n".join(diffs[:20])
        # 反向自检：这批码里必须有一部分**真能解析出**模板，否则整条判据在 None==None 上恒真
        assert resolved_total > 0, (
            "索引外 wp_code 在 HEAD 版下全部解析为空 —— 判据在空集上恒真，"
            "派生规则需要复核"
        )

    def test_find_all_template_files_zero_regression(self, head_finder):
        self._require_empty_override_root()
        from app.services import wp_template_finder as current

        diffs: list[str] = []
        compared = 0
        nonempty = 0
        for code in _all_wp_codes():
            expected = head_finder.find_all_template_files(code)
            actual = current.find_all_template_files(code)
            compared += 1
            if expected:
                nonempty += 1
            if expected != actual:
                diffs.append(f"{code}: HEAD={expected} 现={actual}")

        assert compared == _EXPECTED_WP_CODES
        assert nonempty > 0, "HEAD 版对全部 wp_code 都返回空 —— 判据在空集上恒真"
        assert not diffs, "find_all_template_files 出现回归：\n" + "\n".join(diffs[:20])

    def test_find_template_file_any_zero_regression(self, head_finder):
        self._require_empty_override_root()
        from app.services import wp_template_finder as current

        diffs: list[str] = []
        compared = 0
        resolved = 0
        for code in _all_wp_codes():
            expected = head_finder.find_template_file_any(code)
            actual = current.find_template_file_any(code)
            compared += 1
            if expected is not None:
                resolved += 1
            if expected != actual:
                diffs.append(f"{code}: HEAD={expected} 现={actual}")

        assert compared == _EXPECTED_WP_CODES
        assert resolved > 0, "HEAD 版全返回 None —— 判据在空集上恒真"
        assert not diffs, "find_template_file_any 出现回归：\n" + "\n".join(diffs[:20])

    def test_public_entry_signatures_unchanged(self):
        """签名与返回类型不变（Requirement 2.3 的另一半）。"""
        import inspect

        from app.services import wp_template_finder as current

        assert list(inspect.signature(current.find_template_file).parameters) == ["wp_code"]
        assert list(inspect.signature(current.find_all_template_files).parameters) == ["wp_code"]
        assert list(inspect.signature(current.find_template_file_any).parameters) == ["wp_code"]


class TestOverrideLayerIsActuallyWired:
    """🔴 零回归判据的**反向自检** —— 覆盖层必须真的接上了。

    这是本 spec 最容易出的假绿：若模块末尾的重绑定失效（比如被 `import *`、被
    reload、或被后来的赋值覆盖），三个公开入口仍是纯权威实现 ⇒ Property 6 的零回归
    照样全绿，而覆盖层从头到尾是**死代码**（平台铁律的「additive 注入即死代码」）。

    所以必须有两条正向判据：结构上 wrapper 在位，行为上覆盖文件真被解析到。
    """

    def test_public_entries_are_override_wrappers(self):
        """结构：三个公开名都是包过的，且 `__wrapped__` 指向权威实现。"""
        from app.services import wp_template_finder as finder

        pairs = [
            (finder.find_template_file, finder.find_template_file_unresolved),
            (finder.find_all_template_files, finder.find_all_template_files_unresolved),
            (finder.find_template_file_any, finder.find_template_file_any_unresolved),
        ]
        for public, authoritative in pairs:
            assert public is not authoritative, (
                f"{public.__name__} 仍是权威实现本身 —— 覆盖层重绑定没生效"
            )
            assert getattr(public, "__wrapped__", None) is authoritative, (
                f"{public.__name__}.__wrapped__ 没指向权威实现"
            )

    def test_override_actually_wins_through_public_entry(self, isolated_override_root):
        """行为：种一份事务所级覆盖，公开入口必须返回它而不是权威文件。

        走 `firm_default` 层是因为公开入口只收 `wp_code`，拿不到 project/group id。
        """
        from app.services import wp_template_finder as finder

        wp_code = "A1"
        authoritative = finder.find_template_file_unresolved(wp_code)
        assert authoritative is not None and authoritative.is_file()

        planted = _plant_current(
            isolated_override_root, "firm_default", wp_code, authoritative, b"firm-override"
        )
        assert finder.find_template_file(wp_code) == planted, (
            "公开入口没返回覆盖文件 —— 覆盖层没接上（死代码）"
        )
        assert finder.find_template_file_unresolved(wp_code) == authoritative, (
            "权威侧入口被污染 —— 它必须始终只看权威目录"
        )
        assert finder.find_template_file_any(wp_code) == planted
        assert planted in finder.find_all_template_files(wp_code)


# ═══════════════════════════════════════════════════════════════════════════
# Property 7 / 8 —— 多层优先级与逐层回落（Requirement 2.4 / 2.5）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def isolated_override_root(tmp_path, monkeypatch):
    """把 OVERRIDE_ROOT 指到 tmp，避免污染真实覆盖层。"""
    from app.services import wp_template_override as mod

    fake_root = tmp_path / "template_overrides"
    fake_root.mkdir()
    monkeypatch.setattr(mod, "OVERRIDE_ROOT", fake_root)
    return fake_root


def _plant_current(
    root: Path, scope_seg: str, wp_code: str, authoritative: Path,
    payload: bytes, *, suffix: str | None = None,
) -> Path:
    """在覆盖层种一份当前版本。

    🔴 布局必须与 `wp_template_override.override_dir_for` 一致：
    `{scope_seg}/{wp_code}/{authoritative.stem}/current{ext}`。少一级 stem 目录会让
    解析恒不命中，于是「应回落」类判据全部**假绿** —— 本文件第一版就栽在这里。

    :param suffix: 只在故意构造扩展名不符的用例里给；默认取权威文件的扩展名。
    """
    ext = suffix if suffix is not None else authoritative.suffix
    target = root / scope_seg / wp_code / authoritative.stem / f"{CURRENT_STEM}{ext}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return target


class TestProperty7And8ScopePriority:
    """四层同时命中取项目级；逐层撤掉依次回落。每步断言 origin 与 sha256。"""

    #: 取一个索引里真实存在、且权威侧解析得到 xlsx 的 wp_code。
    WP_CODE = "A1"

    def _authoritative(self):
        from app.services import wp_template_finder as finder

        path = finder.find_template_file(self.WP_CODE)
        assert path is not None and path.is_file(), f"{self.WP_CODE} 权威模板不存在"
        return path

    def test_four_layers_take_project(self, isolated_override_root):
        authoritative = self._authoritative()
        project_id, group_id = uuid4(), uuid4()

        _plant_current(isolated_override_root, "firm_default", self.WP_CODE,
                       authoritative, b"firm-payload")
        _plant_current(isolated_override_root, f"group_custom/{group_id}", self.WP_CODE,
                       authoritative, b"group-payload")
        proj = _plant_current(isolated_override_root, f"project/{project_id}", self.WP_CODE,
                              authoritative, b"project-payload")

        res = resolve_template(self.WP_CODE, project_id=project_id, group_id=group_id)
        assert isinstance(res, TemplateResolution)
        assert res.origin == "override:project"
        assert res.path == proj
        assert res.scope is SCOPE_PRIORITY[0]

    def test_fallback_step_by_step(self, isolated_override_root):
        """逐层撤掉，依次回落到 group_custom → firm_default → authoritative。"""
        import hashlib

        authoritative = self._authoritative()
        project_id, group_id = uuid4(), uuid4()

        firm = _plant_current(isolated_override_root, "firm_default", self.WP_CODE,
                              authoritative, b"firm-payload")
        group = _plant_current(isolated_override_root, f"group_custom/{group_id}",
                               self.WP_CODE, authoritative, b"group-payload")
        proj = _plant_current(isolated_override_root, f"project/{project_id}",
                              self.WP_CODE, authoritative, b"project-payload")

        def sha(p: Path) -> str:
            return hashlib.sha256(p.read_bytes()).hexdigest()

        steps = [
            (proj, "override:project", proj),
            (group, "override:group_custom", group),
            (firm, "override:firm_default", firm),
            (None, "authoritative", authoritative),
        ]
        for to_remove, expected_origin, expected_path in steps:
            res = resolve_template(self.WP_CODE, project_id=project_id, group_id=group_id)
            assert res is not None
            assert res.origin == expected_origin, f"应为 {expected_origin}，实为 {res.origin}"
            assert res.path == expected_path
            assert res.sha256 == sha(expected_path), f"{expected_origin} 的 sha256 不符"
            if to_remove is not None:
                to_remove.unlink()

    def test_missing_scope_id_skips_that_layer(self, isolated_override_root):
        """不给 project_id 时项目层不参与解析（而不是拿别的项目的覆盖）。"""
        authoritative = self._authoritative()
        other_project = uuid4()
        planted = _plant_current(isolated_override_root, f"project/{other_project}",
                                 self.WP_CODE, authoritative, b"other-project-payload")
        # 反向自检：文件确实种在了解析器会查的位置，否则本判据恒真
        assert planted.is_file()

        res = resolve_template(self.WP_CODE)
        assert res is not None
        assert res.origin == "authoritative"
        assert res.path == authoritative

    def test_extension_must_match_authoritative(self, isolated_override_root):
        """Requirement 2.6：不同扩展名的 current 不参与解析。"""
        authoritative = self._authoritative()
        assert authoritative.suffix == ".xlsx"
        project_id = uuid4()
        planted = _plant_current(isolated_override_root, f"project/{project_id}",
                                 self.WP_CODE, authoritative, b"wrong-extension",
                                 suffix=".docx")
        # 反向自检：种在解析器会查的目录里，只是扩展名不符 —— 否则判据恒真
        assert planted.is_file()
        assert planted.parent == (
            isolated_override_root / "project" / str(project_id)
            / self.WP_CODE / authoritative.stem
        )

        res = resolve_template(self.WP_CODE, project_id=project_id)
        assert res is not None
        assert res.origin == "authoritative", "跨扩展名的 current 不该被解析到"

        # 同扩展名时必须命中 —— 证明上面的"不命中"是扩展名门造成的，不是路径根本没查
        correct = _plant_current(isolated_override_root, f"project/{project_id}",
                                 self.WP_CODE, authoritative, b"right-extension")
        planted.unlink()
        res2 = resolve_template(self.WP_CODE, project_id=project_id)
        assert res2 is not None
        assert res2.origin == "override:project"
        assert res2.path == correct

    def test_origin_is_readable_not_bare_path(self):
        """Requirement 2.2：解析结果带来源标记，不是裸 Path。"""
        res = resolve_template(self.WP_CODE)
        assert res is not None
        assert res.origin == "authoritative"
        assert res.is_override is False
        assert res.scope is None
        assert res.wp_code == self.WP_CODE
        assert res.version_id is None


class TestResolveAnyAndAll:
    def test_resolve_template_any_matches_finder_when_empty(self):
        """覆盖层为空时 `resolve_template_any` 与权威入口同结果。"""
        if OVERRIDE_ROOT.is_dir() and any(OVERRIDE_ROOT.iterdir()):
            pytest.skip("OVERRIDE_ROOT 非空")
        from app.services import wp_template_finder as finder

        checked = 0
        for code in _all_wp_codes():
            expected = finder.find_template_file_any(code)
            res = resolve_template_any(code)
            actual = res.path if res is not None else None
            assert expected == actual, f"{code}: {expected} != {actual}"
            checked += 1
        assert checked == _EXPECTED_WP_CODES

    def test_resolve_all_templates_matches_finder_when_empty(self):
        if OVERRIDE_ROOT.is_dir() and any(OVERRIDE_ROOT.iterdir()):
            pytest.skip("OVERRIDE_ROOT 非空")
        from app.services import wp_template_finder as finder

        multi_file_codes = 0
        for code in _all_wp_codes():
            expected = finder.find_all_template_files(code)
            actual = [r.path for r in resolve_all_templates(code)]
            assert expected == actual, f"{code}: {expected} != {actual}"
            if len(expected) > 1:
                multi_file_codes += 1
        assert multi_file_codes > 0, "没有任何多文件底稿 —— 判据未覆盖该分支"


# ═══════════════════════════════════════════════════════════════════════════
# Property 3 / 4 —— 权威目录逐份冻结（Task 15）
# Requirements: 1.3, 1.4
# ═══════════════════════════════════════════════════════════════════════════
#
# ## 为什么用「编辑前后自比」而不是外部 digest 基线
#
# `_index.json` **不声明 sha256**（只有 `size_kb`），而既有的 digest 基线是按循环切片的
# （`test_task5X_*_cycle_migration.py` 的 `manifest_slice["authoritative_templates"]`），
# 每份只覆盖自己那个循环，没有全量 476 份的基线。
#
# 造一份全量基线会带来两个问题：① 与那些切片基线成为第二真源；② 任何 lane 合法更新模板
# 都要来改我这份基线，变成跨 spec 的回退高发文件。
#
# Property 3 的语义本来就是「**一次完整编辑保存后**逐份不变」—— 前后自比正好，且天然
# 不受并发会话合法改模板的影响（快照在同一次运行内取）。
#
# ## 🔴 Property 4 的安全陷阱：判据本身不能造成它要防的破坏
#
# Property 4 要求「把 `OVERRIDE_ROOT` 临时改为 `TEMPLATES_DIR` 时 Property 3 必须打红」。
# 字面照做是**危险**的：monkeypatch 掉 `OVERRIDE_ROOT` 后，越界门
# （`assert_target_within_override_root`）会认为权威目录内的路径是"根内"，于是
# `stage_override` 会**真的把字节写进 backend/wp_templates/**。判据跑一次就污染了它要
# 保护的基线，而且 476 份模板是所有项目所有底稿的生成基线。
#
# 故 Property 4 落在三重上，都不需要真写权威目录：
#   ① 互斥断言的三形态（`TestProperty5RootDisjoint`，在 write_gates 文件里）
#   ② 越界门对权威目录路径的拒绝（`test_absolute_path_outside_root_is_rejected`）
#   ③ 变异脚本在受控环境改源码跑（Task 23，归 E）
# 本文件只额外锁一条：**覆盖层的写入路径在真实常量下永远落不到权威目录**。

#: 索引声明存在、但磁盘上确实缺失的文件 —— **既有状态**，非本 spec 造成。
#:
#: 登记在这里而不是放宽判据：登记表参与期望值推导，于是「新增缺失」仍会被抓到，
#: 而这 2 份不会每次都把判据打红。两份都是 `.doc`（索引里 doc 恰好就是 2 份）。
_KNOWN_MISSING_FROM_DISK: frozenset[str] = frozenset({
    "A\\A17-7 审计项目团队成员独立性声明书（适用于中国及国际审计准则）.doc",
    "A\\A17-7A审计项目团队成员独立性声明书（适用于中国及国际审计准则）-专业技术委员会审核委员适用.doc",
})

#: 索引 `size_kb` 与磁盘的一致/漂移份数 —— 既有状态登记，见
#: `test_index_size_drift_is_registered_not_growing` 的说明。
_INDEX_SIZE_CONSISTENT = 451
_INDEX_SIZE_DRIFTED = 23


def _snapshot_authoritative() -> dict[str, tuple[int, str]]:
    """权威目录下**全部**文件的 (size, sha256) 快照。

    走目录 rglob 而不是索引，这样索引外的文件（若有）也在冻结面内 ——
    「权威目录不被写入」这件事跟某个文件是否在索引里无关。
    """
    import hashlib

    snapshot: dict[str, tuple[int, str]] = {}
    for path in sorted(_TEMPLATES_DIR.rglob("*")):
        if not path.is_file():
            continue
        data = path.read_bytes()
        rel = path.relative_to(_TEMPLATES_DIR).as_posix()
        snapshot[rel] = (len(data), hashlib.sha256(data).hexdigest())
    return snapshot


class TestProperty3AuthoritativeFrozen:
    """一次完整的覆盖层写入后，权威目录逐份不变。"""

    def test_index_declaration_matches_disk_except_known_missing(self):
        """索引声明与磁盘的一致性，并把既有缺口锁成**恰好那 2 份**。"""
        entries = _load_index_entries()
        assert len(entries) == _EXPECTED_INDEX_ENTRIES

        missing = {
            e["relative_path"]
            for e in entries
            if not (_TEMPLATES_DIR / e["relative_path"]).is_file()
        }
        assert missing == _KNOWN_MISSING_FROM_DISK, (
            "索引声明与磁盘的缺口变了。\n"
            f"  新增缺失：{sorted(missing - _KNOWN_MISSING_FROM_DISK)}\n"
            f"  已修复：{sorted(_KNOWN_MISSING_FROM_DISK - missing)}\n"
            "若是新增缺失，说明有人删了权威模板；若是已修复，把它从登记表里摘掉。"
        )

    def test_index_size_drift_is_registered_not_growing(self):
        """索引 `size_kb` 与磁盘的漂移**分布**锁死 —— 既有 23 份，新增会被抓到。

        🔴 为什么不是「零漂移」：实测索引声明与磁盘**普遍不符**，451 份一致 / 23 份漂移
        （4.8%）/ 2 份缺失。22 份是磁盘**更小**、1 份更大，最极端的
        `H\\H3 投资性房地产.xlsx` 索引声明 712.3KB 而磁盘只有 142.7KB（**-80%**）。
        按类别：A 4 / B 10 / G 4 / H 5。

        这是**既有状态，非本 spec 造成**（本 spec 一个字节都不写权威目录，由
        `test_full_override_write_leaves_authoritative_untouched` 逐份锁死）。两种可能：
        模板被人工换成新版而索引未重算，或某条历史路径真的重写过模板
        （xlsx 缩 80% 与 openpyxl 全量重写的已知毁坏形态吻合，但 A17-1 / B60 系列是
        **docx**、不经 openpyxl ⇒ 不能一概而论）。已报 A 裁，见分工书。

        ⇒ Property 3 的冻结判据用**前后自比**（见上一条），不依赖索引的 size_kb。
        这条只负责「不让漂移面继续扩大」。
        """
        entries = _load_index_entries()
        drifted: list[str] = []
        consistent = 0
        for e in entries:
            if e["relative_path"] in _KNOWN_MISSING_FROM_DISK:
                continue
            actual_kb = (_TEMPLATES_DIR / e["relative_path"]).stat().st_size / 1024
            if abs(actual_kb - e["size_kb"]) > 1.0:
                drifted.append(
                    f"{e['relative_path']}: 索引 {e['size_kb']}KB vs 磁盘 {actual_kb:.1f}KB"
                )
            else:
                consistent += 1

        assert consistent == _INDEX_SIZE_CONSISTENT, (
            f"size_kb 一致份数 {consistent} != 登记的 {_INDEX_SIZE_CONSISTENT}"
        )
        assert len(drifted) == _INDEX_SIZE_DRIFTED, (
            f"size_kb 漂移份数 {len(drifted)} != 登记的 {_INDEX_SIZE_DRIFTED}。\n"
            + "\n".join(drifted[:20])
            + "\n\n漂移**变多** ⇒ 有人改了权威模板（查是谁、是否合法）；"
            "\n漂移**变少** ⇒ 有人重算了索引（把登记数字同步下来）。"
        )

    def test_full_override_write_leaves_authoritative_untouched(
        self, tmp_path, monkeypatch
    ):
        """真跑一次 stage → activate → deactivate，权威目录 (size, sha256) 逐份不变。"""
        from app.models.template_library_models import TemplateLevel
        from app.services import wp_template_finder as finder
        from app.services import wp_template_override as mod

        before = _snapshot_authoritative()
        assert len(before) >= _EXPECTED_INDEX_ENTRIES - len(_KNOWN_MISSING_FROM_DISK), (
            f"快照只有 {len(before)} 份 —— 分母太小，判据接近恒真"
        )

        fake_root = tmp_path / "template_overrides"
        fake_root.mkdir()
        monkeypatch.setattr(mod, "OVERRIDE_ROOT", fake_root)

        wp_code = "A1"
        authoritative = finder.find_template_file_unresolved(wp_code)
        assert authoritative is not None

        staged = mod.stage_override(
            wp_code, authoritative, TemplateLevel.firm_default,
            b"edited-payload-that-must-never-reach-wp_templates",
            version_id="prop3-version",
        )
        mod.activate_staged_override(staged)
        assert mod.resolve_template(wp_code).origin == "override:firm_default"
        mod.deactivate_override(wp_code, authoritative, TemplateLevel.firm_default)

        after = _snapshot_authoritative()

        assert set(after) == set(before), (
            "权威目录的文件集合变了：\n"
            f"  新增：{sorted(set(after) - set(before))[:10]}\n"
            f"  消失：{sorted(set(before) - set(after))[:10]}"
        )
        changed = [
            f"{rel}: {before[rel]} → {after[rel]}"
            for rel in before
            if before[rel] != after[rel]
        ]
        assert not changed, "权威目录字节被改动：\n" + "\n".join(changed[:15])

    def test_override_root_is_disjoint_in_real_constants(self):
        """Property 4 的可安全执行部分：真实常量下覆盖层永远落不到权威目录。

        不 monkeypatch `OVERRIDE_ROOT`（那会让越界门认为权威目录是"根内"，
        判据自己就把基线写坏了）。这里只断言真实常量的互斥关系与越界门的行为。
        """
        from app.services import wp_template_override as mod

        # 真实常量互不包含
        mod.assert_override_root_disjoint_from_authoritative()

        # 越界门拒绝权威目录下的任何目标
        with pytest.raises(mod.OverrideRootEscapeError):
            mod.assert_target_within_override_root(
                mod.AUTHORITATIVE_ROOT / "A" / "A1 财务报告程序表.xlsx"
            )
        with pytest.raises(mod.OverrideRootEscapeError):
            mod.assert_target_within_override_root(mod.AUTHORITATIVE_ROOT)


# ═══════════════════════════════════════════════════════════════════════════
# Task 24 —— 范围边界（Requirement 7.1 ~ 7.6）
# ═══════════════════════════════════════════════════════════════════════════
#
# 这些是「本 spec **没有**做什么」的判据。它们比"做了什么"的判据更容易腐烂：
# 没人会因为多改了一处而想起来跑它们，所以每条都必须能独立打红。


class TestTask24ScopeBoundary:
    def test_authoritative_directory_has_no_uncommitted_changes(self):
        """Requirement 7.1：本 spec 不改 `backend/wp_templates/` 任何字节。

        Property 3 已从**行为**上证明（编辑前后逐份自比）。这条从 **git** 上再证一次：
        工作树里权威目录一个字节都没动。两条互补 —— 行为判据管运行时，git 判据管
        「有人手动改了模板还提交了」。
        """
        import subprocess

        proc = subprocess.run(
            ["git", "status", "--porcelain", "--", "backend/wp_templates/"],
            cwd=_REPO_ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120,
        )
        if proc.returncode != 0:
            pytest.skip(f"git 不可用：{proc.stderr[:200]}")
        dirty = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        assert not dirty, (
            "权威模板目录在工作树里被改动了：\n" + "\n".join(dirty[:20])
        )

    #: 前端禁止参与模板落盘的 xlsx 解析库（npm 包名）。
    _FORBIDDEN_FRONTEND_PKGS = (
        "univer", "@univerjs", "exceljs", "xlsx", "sheetjs",
        "xlsx-populate", "write-excel-file",
    )

    @staticmethod
    def _imported_modules(source: str) -> set[str]:
        """源码里 `import ... from 'X'` / `import 'X'` 的模块路径集合。"""
        import re

        pattern = re.compile(
            r"""import\s+(?:[\s\S]*?\s+from\s+)?['"]([^'"]+)['"]"""
        )
        return {m.group(1) for m in pattern.finditer(source)}

    def test_no_univer_in_the_override_write_path(self):
        """Requirement 7.3：不引入 Univer 或任何前端 xlsx 解析库参与模板落盘。

        后端侧由 Property 15 的 AST 可达性覆盖；这条管**前端**：模板覆盖层的 UI
        只上传字节、只让 OO 编辑，不得 import 任何 xlsx 解析库。

        🔴 判据必须落在 **import 语句的模块路径**上，不能扫全文子串。
        初版扫全文，当场被自己打红 —— 命中的是既有 CSS 类 `.gt-wpd-comp--univer`
        （Univer 是平台的一个 **componentType 取值**，那是底稿渲染的配色，与覆盖层无关）。
        这正是「字符串存在型判据不算判据」的翻版。
        """
        vue_path = (
            _REPO_ROOT / "audit-platform" / "frontend" / "src" / "components"
            / "template-library" / "WpTemplateDetail.vue"
        )
        if not vue_path.is_file():
            pytest.skip(f"前端组件不存在：{vue_path}")

        modules = self._imported_modules(vue_path.read_text(encoding="utf-8"))
        assert modules, "解析不出任何 import —— 判据会在空集上恒真"

        bad = sorted(
            m
            for m in modules
            if any(
                m == pkg or m.startswith(f"{pkg}/")
                for pkg in self._FORBIDDEN_FRONTEND_PKGS
            )
        )
        assert not bad, f"前端模板覆盖层 import 了 xlsx 解析库：{bad}"

    def test_the_import_scanner_catches_a_planted_dependency(self):
        """🔴 反向自检：喂一个合成的 Univer import，扫描器必须抓到；
        而 CSS 里的同名字样必须**不**被抓到。
        """
        planted = (
            "<script setup lang=\"ts\">\n"
            "import { ref } from 'vue'\n"
            "import { Univer } from '@univerjs/core'\n"
            "import * as XLSX from 'xlsx'\n"
            "</script>\n"
            "<style scoped>\n"
            ".gt-comp--univer { color: red; }\n"
            "</style>\n"
        )
        modules = self._imported_modules(planted)
        bad = sorted(
            m
            for m in modules
            if any(
                m == pkg or m.startswith(f"{pkg}/")
                for pkg in self._FORBIDDEN_FRONTEND_PKGS
            )
        )
        assert bad == ["@univerjs/core", "xlsx"], f"扫描器结果不符：{bad}"
        # CSS 里的 `univer` 字样不该进 modules
        assert not any("gt-comp" in m for m in modules)

    def test_migration_does_not_alter_existing_template_tables(self):
        """Requirement 7.5：不改 `wp_template` / `template_library` 已有列的语义。

        判据落在**迁移文件**：V154 里不得出现对这两张表的 ALTER / DROP。
        新增能力用新表承载。
        """
        import re

        migration = _REPO_ROOT / "backend" / "migrations" / (
            "V154__workpaper_template_override_version.sql"
        )
        if not migration.is_file():
            pytest.skip("V154 迁移文件不存在")
        sql = migration.read_text(encoding="utf-8")

        # 剥掉 `--` 注释：说明文字里会提到这两张表名（"不碰 wp_template"），
        # 不剥就会把说明当成违规。
        code = "\n".join(
            line.split("--", 1)[0] for line in sql.splitlines()
        )

        offenders: list[str] = []
        for table in ("wp_template", "template_library", "wp_index", "working_paper"):
            for verb in ("ALTER TABLE", "DROP TABLE", "TRUNCATE", "UPDATE", "DELETE FROM"):
                pattern = re.compile(
                    rf"\b{verb}\s+(?:IF\s+EXISTS\s+)?{re.escape(table)}\b", re.I
                )
                if pattern.search(code):
                    offenders.append(f"{verb} {table}")
        assert not offenders, (
            f"V154 动了既有表：{offenders} —— 新增能力必须用新表承载（Requirement 7.5）"
        )

    def test_migration_is_additive_only(self):
        """V154 只 CREATE，不 DROP 任何既有对象。"""
        import re

        migration = _REPO_ROOT / "backend" / "migrations" / (
            "V154__workpaper_template_override_version.sql"
        )
        if not migration.is_file():
            pytest.skip("V154 迁移文件不存在")
        code = "\n".join(
            line.split("--", 1)[0]
            for line in migration.read_text(encoding="utf-8").splitlines()
        )
        # 允许 CREATE OR REPLACE（函数/触发器的幂等写法）
        drops = re.findall(r"\bDROP\s+(?!.*IF\s+EXISTS\s+.*\bwptov_)\w+", code, re.I)
        assert not drops, f"V154 出现 DROP：{drops}"

    def test_rollback_script_exists_and_warns_about_files(self):
        """配对回滚脚本必须存在，且必须说明「DROP 表不会让覆盖失效」。

        这条不是形式检查：`resolve_template` 的判据是**文件系统**（`current{ext}` 是否
        存在），不查版本表 ⇒ 回滚 DB **不会**让解析回落权威目录，覆盖仍然生效、
        只是失去了版本元数据。回滚脚本不写清这一点，运维会以为 DROP 表就撤销了覆盖。
        """
        rollback = _REPO_ROOT / "backend" / "migrations" / (
            "R154__rollback_workpaper_template_override_version.sql"
        )
        assert rollback.is_file(), "V154 缺配对回滚脚本"
        text = rollback.read_text(encoding="utf-8")
        assert "current" in text and "OVERRIDE_ROOT" in text, (
            "回滚脚本没说明覆盖层物理文件的处置 —— 会留下「生效但无台账」的覆盖"
        )

    def test_override_root_is_gitignored(self):
        """覆盖层产物不得入 git（它们是运行时产物，与 `working_paper.file_path` 同类）。"""
        gitignore = (_REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        assert any(
            line.strip() in ("backend/storage/", "backend/storage", "storage/")
            for line in gitignore.splitlines()
        ), ".gitignore 未收 backend/storage/ —— 覆盖层文件会被提交进仓库"
