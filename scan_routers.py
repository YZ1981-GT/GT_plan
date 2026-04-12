import os
router_dir = r'D:\GT_plan\backend\app\routers'
files = [f for f in os.listdir(router_dir) if f.endswith('.py')]
broken = []
for fn in files:
    fp = os.path.join(router_dir, fn)
    b = open(fp, 'rb').read()
    for i, line in enumerate(b.split(b'\n')):
        s = line.decode('utf-8', errors='replace').strip()
        if 'HTTPException' in s or 'detail=' in s:
            # Check if line is properly closed
            # A properly closed line should end with ) or ")
            # Broken: line ends with Chinese char but no )
            stripped = s.rstrip()
            if stripped and not stripped.endswith(')")') and not stripped.endswith('"') and not stripped.endswith(')'):
                broken.append((fn, i+1, repr(s[:120])))
                print(f'{fn}:{i+1}: {repr(s[:120])}')
print(f'\nTotal broken: {len(broken)}')
