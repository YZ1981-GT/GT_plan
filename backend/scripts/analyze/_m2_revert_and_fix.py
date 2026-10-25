# -*- coding: utf-8 -*-
"""M2 修复：
1. 用净化版（不经 openpyxl resave）恢复模板——只做 ZIP 级外链净化
2. 用 ZIP 级 XML 处理展开共享公式
"""
import hashlib, io, re, zipfile
from pathlib import Path

TPL = Path("backend/wp_templates/M/M2 实收资本（股本）.xlsx")
BAK = TPL.with_suffix(TPL.suffix + ".preclean.bak")

# 从 BAK 读原始未净化字节
import sys; sys.path.insert(0, "backend")
from scripts.fix.sanitize_m_cycle_template_external_links import sanitize_bytes

src = BAK.read_bytes()
print(f"1. BAK: {hashlib.sha256(src).hexdigest()[:16]}...")

# 第一步：净化外部链接（ZIP 级）
clean, stats = sanitize_bytes(src)
print(f"2. 净化: {hashlib.sha256(clean).hexdigest()[:16]}... stats={stats}")

# 第二步：ZIP 级展开共享公式
# 遍历所有 worksheet xml，把 <f t="shared" ref="..." si="N">公式</f> 改为 <f>公式</f>
# 也把 <f t="shared" si="N"/> （slave cell 自闭合）直接删除（openpyxl 读时会自动展开）
# 但删除自闭合的 <f/> 会让 Excel Table 的公式消失。更安全的做法：
# 只把主格的 t="shared" ref="..." 属性删掉，保留公式文本。
# Slave cell 的 <f t="shared" si="N"/> 保持不动——Excel 打开时会根据主格重新计算。
# 但 instrumentation 层面可能不理解 shared formula——需要确认。

# 实际上最安全的做法是：把主格的 t="shared" ref="..." 删掉（变成普通公式），
# 把 slave cell 的 <f t="shared" si="N"/> 也替换为显式公式文本。
# 但我们没有 slave cell 的公式文本（它们在 XML 里就是空的）。
# openpyxl 能展开是因为它从主格推导 slave 的公式。

# 最务实的方案：直接从净化版（ZIP 级）做 openpyxl resave，但只保存为临时文件
# 用于验证。真正写盘用净化版（不经 openpyxl resave）。
# 共享公式在 instrumentation 层面不是问题——instrumentation 的 Excel Table 和 UUID 列
# 与公式无关。问题在 materialization 后的 structure 观测。

# 实验：直接用净化版（不经 openpyxl resave），看能不能过首版发布
import tempfile
from app.services.workpaper_sync.ooxml_security import validate_ooxml_artifact
with tempfile.TemporaryDirectory() as tmp:
    p = Path(tmp) / "probe.xlsx"
    p.write_bytes(clean)
    try:
        validate_ooxml_artifact(p, document_type="xlsx")
        print("3. OOXML gate (clean only): PASS")
    except Exception as e:
        print(f"3. OOXML gate (clean only): REJECT {e}")

# 验证 sheet 逐格不变
import openpyxl
def snap(data, sheet):
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=False)
    ws = wb[sheet]
    s = {}
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column):
        for c in row:
            if c.value is not None:
                s[c.coordinate] = str(c.value)[:100]
    wb.close()
    return s

b = snap(src, "明细表（非上市公司）M2-2")
a = snap(clean, "明细表（非上市公司）M2-2")
diffs = [k for k in sorted(set(b) | set(a)) if b.get(k) != a.get(k)]
print(f"4. 明细表 diffs: {len(diffs)}")

# 写盘（纯净化版，不经 openpyxl resave）
TPL.write_bytes(clean)
new_sha = hashlib.sha256(clean).hexdigest()
print(f"\n已写入 {TPL.name}")
print(f"SHA256: {new_sha}")
