import json

d = json.load(open("app/security/wp_bound_entry_coverage.json", encoding="utf-8"))
na = [x for x in d["entries"] if x.get("gate") == "native_authz"]
for i, x in enumerate(sorted(na, key=lambda z: (z.get("route") or "", z.get("method") or ""))):
    print(f'{i+1:2d} | {str(x.get("method")):6s} | {x.get("route")} | kind={x.get("kind")}')
    print(f'      fam={x["family"]} action={x.get("action")} binding={x.get("binding")}')
    print(f'      ep={x["entrypoint"]}')
    if x.get("classification_reason"):
        print(f'      reason={x["classification_reason"]}')
