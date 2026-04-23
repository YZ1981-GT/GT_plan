"""调试：测试CSV文件解析"""
import sys, os, io, codecs
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

filepath = r"基础数据\和平药房2024\序时账-重庆和平药房连锁有限责任公司_2024年合并.csv"
print(f"文件: {filepath}")
print(f"大小: {os.path.getsize(filepath)/1024/1024:.1f} MB")

# 读取前 2KB 看看内容
with open(filepath, 'rb') as f:
    sample = f.read(2048)

print(f"\n前100字节 hex: {sample[:100].hex()}")

# 试探编码
for enc in ("utf-8-sig", "utf-8", "gbk", "gb2312", "gb18030", "latin-1"):
    try:
        text = sample.decode(enc)
        print(f"\n编码 {enc} 成功，前200字符:")
        print(text[:200])
        break
    except (UnicodeDecodeError, LookupError) as e:
        print(f"编码 {enc} 失败: {e}")

# 测试流式解码
print("\n=== 流式解码测试 ===")
with open(filepath, 'rb') as f:
    content = f.read(8192)  # 只读前8KB

encoding = None
for enc in ("utf-8-sig", "utf-8", "gbk", "gb2312", "gb18030"):
    try:
        content[:8192].decode(enc)
        encoding = enc
        break
    except (UnicodeDecodeError, LookupError):
        continue
print(f"检测到编码: {encoding}")

stream = codecs.getreader(encoding or "latin-1")(io.BytesIO(content))
for i in range(5):
    line = stream.readline()
    if not line:
        break
    print(f"  Line {i}: {line.strip()[:120]}")

# 测试 smart_match_column
from app.services.smart_import_engine import smart_match_column, _guess_data_type
import csv
# 用第一行非空行作为表头
stream2 = codecs.getreader(encoding or "latin-1")(io.BytesIO(content))
for _ in range(5):
    line = stream2.readline().strip()
    if not line:
        continue
    cells = line.split(',')
    non_empty = [c.strip() for c in cells if c.strip()]
    if len(non_empty) >= 3:
        headers = list(csv.reader([line]))[0]
        headers = [c.strip() for c in headers]
        print(f"\n表头 ({len(headers)}): {headers[:10]}")
        cm = {}
        for h in headers:
            m = smart_match_column(h)
            if m:
                cm[h] = m
        print(f"映射 ({len(cm)}): {cm}")
        dt = _guess_data_type(set(cm.values()))
        print(f"data_type: {dt}")
        break
