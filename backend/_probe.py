import re, glob

# 1. request model fields
for cls in ["BatchExportEnhancedRequest", "ImportResolveRequest", "TemplateCopyRequest", "DownloadPackRequest"]:
    for f in glob.glob("app/**/*.py", recursive=True):
        src = open(f, encoding="utf-8").read()
        m = re.search(r"class " + cls + r"\b.*?(?=\nclass |\Z)", src, re.S)
        if m:
            block = m.group(0)[:600]
            print("=" * 60, cls, "in", f)
            for line in block.splitlines():
                if ":" in line and "=" not in line.split(":")[0] and not line.strip().startswith('"'):
                    print("   ", line.strip())
                elif "wp_id" in line or "target" in line:
                    print("   ", line.strip())
            break

# 2. import_enhanced service write path
print("#" * 60, "import_enhanced body")
src = open("app/routers/wp_export_import_router.py", encoding="utf-8").read()
i = src.find("async def import_enhanced")
print(src[i:i+1500])
