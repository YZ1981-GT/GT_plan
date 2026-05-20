"""一次性脚本：实测 K1-2/K3-2 aux_type/aux_code，验证 0x.1 实测结论。用完即删。"""
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    dbname="audit_platform",
    user="postgres",
    password="postgres",
)
cur = conn.cursor()

for ac_pat, name in [("1221%", "其他应收款"), ("2241%", "其他应付款")]:
    print(f"--- {name} account_code LIKE {ac_pat} ---")
    cur.execute(
        "SELECT DISTINCT aux_type, aux_code FROM tb_aux_balance "
        "WHERE account_code LIKE %s ORDER BY aux_type, aux_code LIMIT 30",
        (ac_pat,),
    )
    rows = cur.fetchall()
    print(f"count: {len(rows)}")
    for r in rows:
        print("  ", r)

cur.close()
conn.close()
