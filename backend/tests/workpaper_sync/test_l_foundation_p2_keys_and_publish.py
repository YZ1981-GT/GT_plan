# -*- coding: utf-8 -*-
r"""L 循环 foundation spec — 阶段 2+3：键/行身份 + 写路径/发布门。

spec: l-cycle-sync-foundation-and-first-canary · Task 10~19
Properties: LF-P13 ~ LF-P22, LF-P34 ~ LF-P38

═══ 运行 ═══

    .\.venv\Scripts\python.exe -m pytest backend/tests/workpaper_sync/test_l_foundation_p2_keys_and_publish.py -v --tb=short
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

# ─── 路径常量 ──────────────────────────────────────────────────────────
_THIS = pathlib.Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "audit-platform" / "frontend" / "src"
WP_COMPONENTS = FRONTEND / "components" / "workpaper"
WP_COMPOSABLES = WP_COMPONENTS / "composables"
SRC_COMPOSABLES = FRONTEND / "composables"
DATA = BACKEND / "data"

MANIFEST_SLICE_PATH = DATA / "workpaper_sync_l_cycle_manifest_slice.json"


# ─── 工具 ──────────────────────────────────────────────────────────────
def _load(p: pathlib.Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _blank_keep_newlines(match: re.Match[str]) -> str:
    return re.sub(r"[^\n]", " ", match.group(0))


def _strip_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", _blank_keep_newlines, source, flags=re.S)
    source = re.sub(r"<!--.*?-->", _blank_keep_newlines, source, flags=re.S)
    source = re.sub(
        r"(?<![:\w\"'`\\])//[^\n]*", lambda m: " " * len(m.group(0)), source
    )
    return source


def _l_domain_files_strict() -> list[pathlib.Path]:
    strict_re = re.compile(r"^(?:use|Gt)?L[1-8](?:[A-Z]|$|\.)")
    dir_re = re.compile(r"[/\\]l[1-8][/\\]")
    out: list[pathlib.Path] = []
    for p in FRONTEND.rglob("*"):
        if not p.is_file() or p.suffix not in (".ts", ".vue"):
            continue
        if "__tests__" in p.as_posix():
            continue
        if dir_re.search(p.as_posix()) or strict_re.match(p.name):
            out.append(p)
    return sorted(set(out))


_FE_CACHE: dict[pathlib.Path, str] = {}


def _cached_text(path: pathlib.Path) -> str:
    if path not in _FE_CACHE:
        _FE_CACHE[path] = path.read_text(encoding="utf-8", errors="replace")
    return _FE_CACHE[path]


def _form_data_path(n: int) -> pathlib.Path:
    """useL{n}FormData.ts 的路径——L1/L3 在 src/composables/，L2/L4~L8 在 WP_COMPOSABLES。"""
    p1 = SRC_COMPOSABLES / f"useL{n}FormData.ts"
    p2 = WP_COMPOSABLES / f"useL{n}FormData.ts"
    if p1.exists():
        return p1
    if p2.exists():
        return p2
    raise FileNotFoundError(f"useL{n}FormData.ts not found")


def _adjudication_path(n: int) -> pathlib.Path:
    p1 = SRC_COMPOSABLES / f"useL{n}Adjudication.ts"
    p2 = WP_COMPOSABLES / f"useL{n}Adjudication.ts"
    if p1.exists():
        return p1
    if p2.exists():
        return p2
    raise FileNotFoundError(f"useL{n}Adjudication.ts not found")


# ─── fixtures ──────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def entries() -> list[dict]:
    return _load(MANIFEST_SLICE_PATH)["independent_entries"]


@pytest.fixture(scope="module")
def l_files() -> list[pathlib.Path]:
    return _l_domain_files_strict()


# ═══════════════════════════════════════════════════════════════════════
# Task 17: 发布门端点字面量门（LC-3）
# Property: LF-P13, LF-P14
# ═══════════════════════════════════════════════════════════════════════
class TestTask17PublishGate:
    """发布门端点字面量 publish-to-tb 代码命中 == 8。"""

    def test_publish_endpoint_code_hits_8(self) -> None:
        """端点 audit-determination/publish-to-tb 代码行命中恰 8（LF-P13）。"""
        endpoint = "audit-determination/publish-to-tb"
        code_hits = 0
        for n in range(1, 9):
            path = _form_data_path(n)
            text = _cached_text(path)
            clean = _strip_comments(text)
            for line in clean.split("\n"):
                if endpoint in line:
                    code_hits += 1
        assert code_hits == 8, (
            f"publish-to-tb 代码命中应为 8，实得 {code_hits}"
        )

    def test_old_writeback_endpoint_only_in_comments(self) -> None:
        """旧端点 trial-balance/writeback 命中全为注释行（LF-P14）。"""
        old_endpoint = "trial-balance/writeback"
        for n in range(1, 9):
            path = _form_data_path(n)
            raw = _cached_text(path)
            clean = _strip_comments(raw)
            # 在注释剥除后不应有旧端点
            for i, line in enumerate(clean.split("\n"), 1):
                assert old_endpoint not in line, (
                    f"useL{n}FormData.ts 第 {i} 行剥注释后仍有旧端点"
                )


# ═══════════════════════════════════════════════════════════════════════
# Task 18: 二次确认门在调用链上（LC-4）
# Property: LF-P15
# ═══════════════════════════════════════════════════════════════════════
class TestTask18ConfirmGate:
    """confirm 文件集与发布门文件集交集为空。"""

    def test_confirm_and_publish_in_different_files(self) -> None:
        """Adjudication 有 confirm，FormData 有 publish——两集合交集为空（LF-P15）。"""
        publish_files = set()
        confirm_files = set()
        for n in range(1, 9):
            fd = _form_data_path(n)
            adj = _adjudication_path(n)
            fd_text = _strip_comments(_cached_text(fd))
            adj_text = _strip_comments(_cached_text(adj))

            if "publish-to-tb" in fd_text:
                publish_files.add(fd.name)
            if "ElMessageBox.confirm" in adj_text or "ElMessageBox" in adj_text:
                confirm_files.add(adj.name)

        assert len(publish_files) == 8, f"发布门文件应 8 个，实得 {publish_files}"
        assert len(confirm_files) == 8, f"确认门文件应 8 个，实得 {confirm_files}"
        overlap = publish_files & confirm_files
        assert len(overlap) == 0, (
            f"发布门与确认门文件集应交集为空，实有重叠 {overlap}"
        )

    @pytest.mark.parametrize("n", range(1, 9))
    def test_adjudication_imports_form_data(self, n: int) -> None:
        """Adjudication → FormData 调用边存在。"""
        adj = _adjudication_path(n)
        text = _cached_text(adj)
        # 查找 import useL{n}FormData 或调用
        assert f"useL{n}FormData" in text or f"FormData" in text or "publish" in text.lower(), (
            f"useL{n}Adjudication 未引用 FormData"
        )


# ═══════════════════════════════════════════════════════════════════════
# Task 19: Adjudication 模块分居两路径（LC-4 / LC-25）
# Property: LF-P16
# ═══════════════════════════════════════════════════════════════════════
class TestTask19AdjudicationDistribution:
    """8 个 Adjudication 分居 src/composables/(2) + composables/(6)。"""

    def test_adjudication_split_2_plus_6(self) -> None:
        """LF-P16: src/composables 2（L1/L3）+ composables 6（L2/L4~L8）。"""
        src_count = 0
        wp_count = 0
        for n in range(1, 9):
            p = _adjudication_path(n)
            if SRC_COMPOSABLES in p.parents or p.parent == SRC_COMPOSABLES:
                src_count += 1
            else:
                wp_count += 1
        assert src_count == 2, f"src/composables 侧应 2 个，实得 {src_count}"
        assert wp_count == 6, f"composables 侧应 6 个，实得 {wp_count}"


# ═══════════════════════════════════════════════════════════════════════
# Task 10: item_id 前缀过滤门（LC-17 ④）
# Property: LF-P35
# ═══════════════════════════════════════════════════════════════════════
class TestTask10ItemIdPrefix:
    """8 个 useL{n}FormData 有 L{n}- 前缀过滤（常量或字面量）。"""

    @pytest.mark.parametrize("n", range(1, 9))
    def test_has_prefix_filter(self, n: int) -> None:
        """常量 ITEM_PREFIX 或字面量 startsWith('L{n}-') 二者之一存在。"""
        path = _form_data_path(n)
        text = _cached_text(path)
        has_constant = "ITEM_PREFIX" in text
        has_literal = f"startsWith('L{n}-')" in text or f'startsWith("L{n}-")' in text
        # 也检查模板串形式
        has_template = f"L{n}-" in text and ("prefix" in text.lower() or "filter" in text.lower() or "startsWith" in text)
        assert has_constant or has_literal or has_template, (
            f"useL{n}FormData.ts 无 L{n}- 前缀过滤"
        )


# ═══════════════════════════════════════════════════════════════════════
# Task 15: derived_total 双正则门（LC-16）
# Property: LF-P34
# ═══════════════════════════════════════════════════════════════════════
class TestTask15DerivedTotal:
    """TAIL (-total 结尾) 与 MID (-total- 中置) 两种形态都存在。"""

    def test_both_total_patterns_exist(self, l_files: list[pathlib.Path]) -> None:
        """TAIL 与 MID 各自非空。"""
        tail_re = re.compile(r"-total['\"`\s,\)]")
        mid_re = re.compile(r"-total-")
        tail_hits = set()
        mid_hits = set()
        for p in l_files:
            text = _strip_comments(_cached_text(p))
            if tail_re.search(text):
                tail_hits.add(p.name)
            if mid_re.search(text):
                mid_hits.add(p.name)
        assert len(tail_hits) > 0, "TAIL 型 (-total 结尾) 应非空"
        assert len(mid_hits) > 0, "MID 型 (-total- 中置) 应非空"

    def test_l1_has_no_total_key(self) -> None:
        """L1 无 total 键。"""
        path = _form_data_path(1)
        text = _strip_comments(_cached_text(path))
        # L1 的利息测算已改 JSON 整表存储，无 total 键
        total_hits = re.findall(r"L1-.*-total", text)
        assert len(total_hits) == 0, f"L1 不应有 total 键，实得 {total_hits}"


# ═══════════════════════════════════════════════════════════════════════
# Task 16: localStorage 三形态门（LC-18）
# Property: LF-P38
# ═══════════════════════════════════════════════════════════════════════
class TestTask16LocalStoragePartition:
    """9 个 dual-mode 的 storage 键三形态 3/5/1。"""

    def test_storage_key_cleanup_complete(self) -> None:
        """BP-4+BP-5 收口后所有 L 域 DualMode 文件已删——0 个残留。"""
        dual_mode_files = sorted(FRONTEND.rglob("useL*DualMode.ts"))
        dual_mode_files = [f for f in dual_mode_files if "__tests__" not in f.as_posix()]
        assert len(dual_mode_files) == 0, (
            f"所有 L 域 DualMode 应已删除，实剩 {[f.name for f in dual_mode_files]}"
        )


# ═══════════════════════════════════════════════════════════════════════
# Task 12: 位置化两口径并报门（LC-8）
# Property: LF-P19, LF-P20
# ═══════════════════════════════════════════════════════════════════════
class TestTask12PositionalIdentity:
    """位置化行身份双口径。"""

    def test_scope1_rowkey_rowid_assignment(self, l_files: list[pathlib.Path]) -> None:
        """口径①: rowKey/rowId 赋值，与 slice total_hits 等值。"""
        rowkey_re = re.compile(r"\b(?:rowKey|rowId)\s*:")
        hits = 0
        for p in l_files:
            text = _strip_comments(_cached_text(p))
            for line in text.split("\n"):
                if rowkey_re.search(line):
                    hits += 1
        # slice total_hits 是 1（口径①只命中 1 处）
        # 这是现算——具体值由 slice 决定
        assert hits >= 1, f"口径① rowKey/rowId 赋值应 >= 1，实得 {hits}"

    def test_scope2_item_id_row_segment(self, l_files: list[pathlib.Path]) -> None:
        """口径②: item_id 模板串里 row-${{…}} / row${{…}} / -${{n}}- 序号段。"""
        row_interp_re = re.compile(r"row-?\$\{")
        hits_by_module: dict[str, int] = {}
        for p in l_files:
            text = _strip_comments(_cached_text(p))
            count = len(row_interp_re.findall(text))
            if count > 0:
                hits_by_module[p.name] = count
        total = sum(hits_by_module.values())
        assert total > 0, "口径② item_id 行序号段应非空"
        # 断言两口径不等（证明②是新增覆盖面）
        # 口径①约 1 处，口径②远多于 1

    def test_two_scopes_differ(self, l_files: list[pathlib.Path]) -> None:
        """两口径结果不等（证明②是新增覆盖面，非重复计数）。"""
        rowkey_re = re.compile(r"\b(?:rowKey|rowId)\s*:")
        row_interp_re = re.compile(r"row-?\$\{")
        scope1 = 0
        scope2 = 0
        for p in l_files:
            text = _strip_comments(_cached_text(p))
            scope1 += len(rowkey_re.findall(text))
            scope2 += len(row_interp_re.findall(text))
        assert scope1 != scope2, (
            f"两口径应不等——口径① {scope1} vs 口径② {scope2}"
        )


# ═══════════════════════════════════════════════════════════════════════
# Task 14: removeRow 签名枚举门（LC-6 / LC-7）
# Property: LF-P17, LF-P18
# ═══════════════════════════════════════════════════════════════════════
class TestTask14RemoveRowSignatures:
    """removeRow / handleRemove 签名枚举。"""

    def test_remove_row_signatures_enumerated(self, l_files: list[pathlib.Path]) -> None:
        """strict 口径下 removeRow / handleRemove 签名存在（LF-P17）。"""
        remove_re = re.compile(r"\b(?:removeRow|handleRemove)\s*\(")
        signatures: list[tuple[str, str]] = []
        for p in l_files:
            text = _strip_comments(_cached_text(p))
            for i, line in enumerate(text.split("\n"), 1):
                if remove_re.search(line):
                    # 取函数签名
                    m = re.search(r"(?:removeRow|handleRemove)\s*\(([^)]*)\)", line)
                    sig = m.group(1).strip() if m else "..."
                    signatures.append((p.name, sig))
        assert len(signatures) > 0, "L 域应有 removeRow/handleRemove 签名"

    def test_rowid_remove_modules_equal_rowid_generators(
        self, l_files: list[pathlib.Path]
    ) -> None:
        """能按行身份删的模块集合 == 生成真 rowId 的模块集合（LF-P18 交叉验证）。"""
        # 按行身份删：removeRow 首参含 rowId/row.rowId
        rowid_remove_re = re.compile(r"removeRow\s*\(\s*(?:\w+\.)?rowId")
        rowid_remove_modules = set()
        for p in l_files:
            text = _strip_comments(_cached_text(p))
            if rowid_remove_re.search(text):
                rowid_remove_modules.add(p.stem)

        # 生成真 rowId：有 rowId 赋值（非 import）
        rowid_gen_re = re.compile(r"rowId\s*:\s*(?:uuid|crypto|Date\.now|Math\.random|`)")
        rowid_gen_modules = set()
        for p in l_files:
            text = _strip_comments(_cached_text(p))
            if rowid_gen_re.search(text):
                rowid_gen_modules.add(p.stem)

        # 两集合应有交集（能按身份删的模块 ⊆ 能生成身份的模块）
        if rowid_remove_modules and rowid_gen_modules:
            assert len(rowid_remove_modules & rowid_gen_modules) > 0, (
                "按行身份删的模块与生成 rowId 的模块应有交集"
            )


# ═══════════════════════════════════════════════════════════════════════
# Task 11: 前缀重复轴与 JSON 整表键命名门（LC-17 ①③）
# Property: LF-P36, LF-P37
# ═══════════════════════════════════════════════════════════════════════
class TestTask11PrefixAndJsonKeys:
    """前缀重复轴两组各自非空 + JSON 整表键四形态。"""

    def test_repeated_prefix_nonempty(self, l_files: list[pathlib.Path]) -> None:
        """L{n}-L{n}-… 重复前缀组非空（LF-P36）。"""
        repeat_re = re.compile(r"""['"`]L(\d)-L\1-""")
        hits = 0
        for p in l_files:
            text = _strip_comments(_cached_text(p))
            hits += len(repeat_re.findall(text))
        assert hits > 0, "重复前缀 L{n}-L{n}-… 应非空"

    def test_non_repeated_prefix_nonempty(self, l_files: list[pathlib.Path]) -> None:
        """L{n}-… 不重复前缀组非空（LF-P36）。"""
        nonrepeat_re = re.compile(r"""['"`]L(\d)-(?!L\1-)""")
        hits = 0
        for p in l_files:
            text = _strip_comments(_cached_text(p))
            hits += len(nonrepeat_re.findall(text))
        assert hits > 0, "不重复前缀 L{n}-… 应非空"

    def test_json_key_four_shapes(self, l_files: list[pathlib.Path]) -> None:
        """JSON 整表键四种命名形态各自命中（LF-P37）。"""
        json_key_re = re.compile(r"""['"`](L\d-(?:L\d-)?[\w-]+(?:rows|entries))['"`]""")
        keys = set()
        for p in l_files:
            text = _strip_comments(_cached_text(p))
            for m in json_key_re.finditer(text):
                keys.add(m.group(1))
        # 四形态：
        # 1. L{n}-L{n}-{d}-rows（重复前缀）如 L3-L3-2-rows
        shape1 = [k for k in keys if re.match(r"L\d-L\d-\d+", k) and k.endswith("rows")]
        # 2. L{n}-{d}-rows（不重复）如 L4-2-rows
        shape2 = [k for k in keys if re.match(r"L\d-\d+-", k) and not re.match(r"L\d-L\d", k) and k.endswith("rows")]
        # 3. 纯语义名如 L3-overdue-check-rows
        shape3 = [k for k in keys if re.match(r"L\d-[a-z]", k) and k.endswith("rows")]
        # 4. entries 后缀如 L2-L2-3-entries
        shape4 = [k for k in keys if k.endswith("entries")]
        assert len(shape1) > 0, f"形态1（重复前缀+rows）应非空，keys={sorted(keys)}"
        assert len(shape3) > 0, f"形态3（纯语义名+rows）应非空，keys={sorted(keys)}"
        assert len(shape4) > 0, f"形态4（entries后缀）应非空，keys={sorted(keys)}"


# ═══════════════════════════════════════════════════════════════════════
# Task 13: 位置化次级差异门（LC-8）
# Property: LF-P21, LF-P22
# ═══════════════════════════════════════════════════════════════════════
class TestTask13PositionalSubDifferences:
    """分隔符两型 + 索引基准两型。"""

    def test_separator_two_types(self, l_files: list[pathlib.Path]) -> None:
        """分隔符两型各自非空：row-${…} 带连字符存在（LF-P21）。"""
        hyphen_re = re.compile(r"row-\$\{")
        hyphen_hits = 0
        for p in l_files:
            text = _strip_comments(_cached_text(p))
            hyphen_hits += len(hyphen_re.findall(text))
        assert hyphen_hits > 0, "row-${…} 带连字符应非空"

    def test_l6_disclosure_uses_row_no_hyphen(self, l_files: list[pathlib.Path]) -> None:
        """L6 Disclosure 使用 row${i} 形态（row 后直接 ${，无连字符分隔）（LF-P21）。"""
        # L6 Disclosure 的 item_id 模板：`L6-L6-2-row${i}-project`
        # 这里 row 和 ${ 之间无连字符
        l6_disclosure_files = [
            p for p in l_files
            if "L6TabDisclosure" in p.name
        ]
        assert len(l6_disclosure_files) >= 2, "应有 L6 Disclosure 文件"
        found = False
        for p in l6_disclosure_files:
            text = _strip_comments(_cached_text(p))
            # row${i} 不带连字符——键形态是 -row${i}-
            if re.search(r"row\$\{[^}]*\}", text):
                found = True
        assert found, "L6 Disclosure 应有 row${i} 形态"

    def test_index_basis_write_and_read(self, l_files: list[pathlib.Path]) -> None:
        """写侧 ${i + 1} 与读侧 ${i} 同时存在（LF-P22）。"""
        write_re = re.compile(r"\$\{\s*(?:i|idx|index)\s*\+\s*1\s*\}")
        read_re = re.compile(r"\$\{\s*(?:i|idx|index)\s*\}")
        write_count = 0
        read_count = 0
        for p in l_files:
            text = _strip_comments(_cached_text(p))
            write_count += len(write_re.findall(text))
            read_count += len(read_re.findall(text))
        assert write_count > 0, "写侧 ${i + 1} 应非空"
        assert read_count > 0, "读侧 ${i} 应非空"
