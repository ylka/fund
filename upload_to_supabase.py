import os
import csv
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 建表 SQL（首次运行需要在 Supabase SQL Editor 中执行）
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS funds (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL,
    name TEXT,
    ratio NUMERIC,
    lots NUMERIC,
    share NUMERIC,
    cost_price NUMERIC,
    current_price NUMERIC,
    yield_rate NUMERIC,
    total_cost NUMERIC,
    total_value NUMERIC,
    profit NUMERIC,
    type TEXT,
    UNIQUE(code, type)
);
"""


def upload_csv(file_path: str, fund_type: str):
    """读取 CSV 并上传到 Supabase funds 表"""
    rows = []
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or not row[0].strip():
                continue

            if len(row) >= 4:
                # my-code.csv: 代码, 名称, 成本, 份额
                code, name, cost, share = row[0], row[1], row[2], row[3]
            elif len(row) >= 3:
                # oversea-code.csv / s_plan.csv: 代码, 名称, 成本
                code, name, cost = row[0], row[1], row[2]
                share = None
            else:
                continue

            record = {
                "code": code.strip(),
                "name": name.strip(),
                "ratio": None,
                "lots": None,
                "share": float(share) if share else None,
                "cost_price": float(cost.strip()) if cost.strip() else None,
                "current_price": None,
                "yield_rate": None,
                "total_cost": None,
                "total_value": None,
                "profit": None,
                "type": fund_type,
            }
            rows.append(record)

    if rows:
        # upsert: 按 code + type 去重，重复则更新
        result = supabase.table("funds").upsert(
            rows, on_conflict="code,type"
        ).execute()
        print(f"[{fund_type}] 上传 {len(rows)} 条记录成功")
    else:
        print(f"[{fund_type}] 没有数据")


if __name__ == "__main__":
    # 上传三个 CSV 文件
    csv_files = [
        ("my-code.csv", "my"),
        ("oversea-code.csv", "oversea"),
        ("s_plan.csv", "s_plan"),
    ]

    for file_name, fund_type in csv_files:
        if os.path.exists(file_name):
            upload_csv(file_name, fund_type)
        else:
            print(f"文件不存在: {file_name}")
