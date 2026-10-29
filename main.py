import os
import warnings

warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

from dotenv import load_dotenv

import requests
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
import smtplib

from tqdm import tqdm
from supabase import create_client

# Load environment variables from .env file
load_dotenv()

# 初始化 Supabase 客户端
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))


def send_email(result):
    # 发送邮件通知
    sender_email = os.getenv('SENDER_EMAIL')  # 从环境变量读取发件人邮箱
    receiver_email = os.getenv('RECEIVER_EMAIL')  # 从环境变量读取收件人邮箱
    password = os.getenv('EMAIL_PASSWORD')  # 从环境变量读取密码

    if not password:
        print('password error')
    else:
        msg = MIMEText(result, 'html', 'utf-8')
        msg['Subject'] = "基金持仓最新数据"
        msg['From'] = sender_email
        msg['To'] = receiver_email

        # 连接到 SMTP 服务器并发送邮件
        server = smtplib.SMTP_SSL('smtp.qq.com', 465)
        server.login(sender_email, password)
        server.sendmail(sender_email, receiver_email, msg.as_string())
        server.quit()
        print("邮件已发送")

# 雪球
def get_fund_from_danjuan(fund_code):
    url = f'https://danjuanfunds.com/djapi/fund/growth/{fund_code}?day=ty'

    # 模拟浏览器请求头
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://danjuanfunds.com/',
        'Connection': 'keep-alive',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # 检查请求是否成功

        json_content = response.content
        # json parse
        import json
        data = json.loads(json_content)
        fund_nav_growth = data.get('data', {}).get('fund_nav_growth', [])
        if fund_nav_growth:
            data = fund_nav_growth[-1]
            last_data = fund_nav_growth[-2]

            record = {
                'date': data['date'].strip(),
                'net_value': data['nav'].strip(),
                'accumulated_value': data['nav'].strip(),
                'growth_rate': data['percentage'].strip(),
                'last_value': last_data['nav'].strip(),
                'percentage': data['percentage'].strip()
            }

            return record

        return None
    except requests.RequestException as e:
        print(f"Request failed for fund {fund_code}: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"JSON parse failed for fund {fund_code}: {e}")
        return None

# https://m.dayfund.cn/ajs/ajaxdata.shtml?showtype=getfundvalue&fundcode=020433


def get_fund_value(fund_code):
    url = f'https://m.dayfund.cn/ajs/ajaxdata.shtml?showtype=getfundvalue&fundcode={fund_code}'

    # 模拟浏览器请求头
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://m.dayfund.cn/',
        'Connection': 'keep-alive',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # 检查请求是否成功

        # 2026-01-14|1.2400|1.2400|0.0764|6.57%|-0.11%|-0.0013|1.2387|1.1636|2026-01-15|09:39:59
        vals = response.content.decode('utf-8').split('|')
        if len(vals) > 1:
            record = {
                'date': vals[0].strip(),
                'net_value': vals[1].strip(),
                'accumulated_value': vals[2].strip(),
                'growth_rate': vals[4].strip()
            }
            return record
        else:
            print(f"data err: {response.content}")
    except requests.RequestException as e:
        print(f"Request failed for fund {fund_code}: {e}")

    return None


def update_supabase_prices(datas):
    """更新 Supabase funds 表中的 current_price、yield_rate、profit，按 code 匹配"""
    # 先查出表中所有记录，用于计算收益
    all_records = supabase.table("funds").select("id, code, cost_price, share").execute().data

    # 建立 code -> net_value 映射
    code_to_price = {}
    for item in datas:
        code = item.get("code")
        if code not in code_to_price:
            code_to_price[code] = float(item["net_value"])

    updated_count = 0
    for rec in all_records:
        code = rec["code"]
        if code not in code_to_price:
            continue

        net_value = code_to_price[code]
        cost_price = float(rec["cost_price"]) if rec.get("cost_price") else None
        share = float(rec["share"]) if rec.get("share") else None

        update_data = {"current_price": net_value}

        if cost_price and cost_price > 0:
            yield_rate = net_value / cost_price - 1
            update_data["yield_rate"] = round(yield_rate, 6)

            if share:
                total_cost = cost_price * share
                total_value = net_value * share
                profit = total_value - total_cost
                update_data["total_cost"] = round(total_cost, 2)
                update_data["total_value"] = round(total_value, 2)
                update_data["profit"] = round(profit, 2)

        supabase.table("funds").update(update_data).eq("id", rec["id"]).execute()
        updated_count += 1

    print(f"Supabase 已更新 {updated_count} 条记录")


def save_history_snapshot():
    """保存当日持仓快照到 funds_history 表"""
    from datetime import date

    records = supabase.table("funds").select("total_value, total_cost, profit").execute().data

    total_value = sum(float(r["total_value"]) for r in records if r.get("total_value"))
    total_cost = sum(float(r["total_cost"]) for r in records if r.get("total_cost"))
    total_profit = sum(float(r["profit"]) for r in records if r.get("profit"))
    yield_rate = total_profit / total_cost if total_cost > 0 else 0

    snapshot = {
        "date": date.today().isoformat(),
        "total_value": round(total_value, 2),
        "total_cost": round(total_cost, 2),
        "total_profit": round(total_profit, 2),
        "yield_rate": round(yield_rate, 6),
    }

    # upsert 按 date 去重，同一天多次运行只保留最新
    supabase.table("funds_history").upsert(snapshot, on_conflict="date").execute()
    print(f"历史快照已保存: 总市值 {total_value:.2f}, 收益 {total_profit:.2f}, 收益率 {yield_rate*100:.2f}%")


def update_peak_and_get_drawdown(tracked_codes, code_to_fund_data):
    """更新最高净值，计算并返回每个基金的回撤

    为处理分红导致的净值"假跌"：
    用前一天净值和当天涨跌幅推算理论净值，与接口返回的实际净值对比，
    若差异较大则视为分红，将该差异同步到 peak_price 上，保证回撤口径一致。
    """
    results = []

    for code in tracked_codes:
        fund_data = code_to_fund_data.get(code)
        if not fund_data:
            continue

        current_price = float(fund_data.get('net_value', 0))
        percentage = fund_data.get('percentage', '0')
        nav_date = fund_data.get('date')  # 净值对应的交易日
        try:
            pct = float(percentage) / 100
        except (TypeError, ValueError):
            pct = 0

        # 查询当前记录
        existing = supabase.table("funds_peak").select("*").eq("code", code).execute().data

        adjust_diff = 0

        if not existing:
            # 首次运行，写入初始最高净值、前一天净值及其日期
            supabase.table("funds_peak").insert({
                "code": code,
                "peak_price": current_price,
                "prev_price": current_price,
                "prev_date": nav_date,
            }).execute()
            peak_price = current_price
            name = code
        else:
            peak_price = float(existing[0]["peak_price"])
            name = existing[0].get("name") or code
            prev_price = existing[0].get("prev_price")
            prev_date = existing[0].get("prev_date")

            # 净值日期和已存的 prev_date 相同，说明是同一交易日重复运行
            is_same_day = (prev_date is not None and str(prev_date) == str(nav_date))

            # 分红检测：用前一天净值和涨跌幅推算理论净值
            # 理论净值与实际净值有差异即视为除权/分红，把差异同步到 peak 上
            # 同一交易日重复运行时跳过，避免用今天的净值当前一天净值导致误判
            if prev_price and not is_same_day:
                prev_price = float(prev_price)
                theoretical = prev_price * (1 + pct)
                diff = current_price - theoretical
                # 差异超过 0.0005 才视为除权/分红，过滤涨跌幅精度误差
                if abs(diff) > 0.0005:
                    adjust_diff = diff
                    peak_price = peak_price + diff
                    print(f"[{code}] 检测到分红/除权，理论净值 {theoretical:.4f} vs 实际 {current_price:.4f}，"
                          f"peak 调整 {diff:+.4f} -> {peak_price:.4f}")

            # 净值创新高则更新 peak
            if current_price > peak_price:
                peak_price = current_price

            # 只有新交易日才滚动 prev_price 和 prev_date
            update_data = {
                "peak_price": round(peak_price, 4),
                "updated_at": "now()",
            }
            if not is_same_day:
                update_data["prev_price"] = current_price
                update_data["prev_date"] = nav_date

            supabase.table("funds_peak").update(update_data).eq("code", code).execute()

        drawdown = (current_price - peak_price) / peak_price * 100 if peak_price > 0 else 0
        results.append({
            "code": code,
            "name": name,
            "current_price": current_price,
            "peak_price": round(peak_price, 4),
            "drawdown": drawdown,
            "percentage": percentage,
            "adjust_diff": adjust_diff,
        })

    return results


# 回撤追踪的基金（从 funds_peak 表读取）
TRACKED_CODES = [r["code"] for r in supabase.table("funds_peak").select("code").execute().data]

email_contents = []

# 从 Supabase 读取持仓数据
db_funds = supabase.table("funds").select("*").execute().data

if not db_funds:
    print("数据库中没有持仓数据")
else:
    datas = []
    # 同一个 code 只需获取一次价格
    code_to_price = {}

    for rec in tqdm(db_funds):
        fund_code = rec["code"]
        name = rec["name"]
        cost = float(rec["cost_price"]) if rec.get("cost_price") else 0
        share = float(rec["share"]) if rec.get("share") else 0

        # 同 code 复用已获取的价格数据
        if fund_code not in code_to_price:
            fund_data = get_fund_from_danjuan(fund_code)
            code_to_price[fund_code] = fund_data
        else:
            fund_data = code_to_price[fund_code]

        if fund_data:
            net_value = float(fund_data.get('net_value', 0))
            last_value = float(fund_data.get('last_value', 0))
            daily_profit = (net_value - last_value) * share
            data = {
                'date': fund_data.get('date', None),
                'net_value': fund_data.get('net_value', None),
                'name': name,
                'code': fund_code,
                'cost': str(cost),
                'share': str(share),
                'daily_profit': daily_profit,
                'yield_rate': net_value / cost - 1 if cost > 0 else 0,
                'percentage': fund_data.get('percentage', '0')
            }
            datas.append(data)

    if not datas:
        print("没有获取到任何基金数据")
    else:
        # 更新 Supabase 表中的 current_price
        update_supabase_prices(datas)

        # 保存当日历史快照
        save_history_snapshot()

        # 补充获取回撤追踪基金的价格（可能不在持仓里）
        for code in TRACKED_CODES:
            if code not in code_to_price:
                fund_data = get_fund_from_danjuan(code)
                code_to_price[code] = fund_data

        # 给 code_to_price 里的数据补充 name（从持仓或直接用 code）
        for code, fd in code_to_price.items():
            if fd and 'name' not in fd:
                # 尝试从 db_funds 找 name
                match = next((r["name"] for r in db_funds if r["code"] == code), code)
                fd['name'] = match

        result = sorted(datas, key=lambda x: x["yield_rate"], reverse=True)

        rows_html = ""
        for i, val in enumerate(result):
            net_value = val["net_value"]
            yield_rate_val = val["yield_rate"] * 100
            yield_rate_str = f"{yield_rate_val:.2f}%"
            daily_profit = val["daily_profit"]
            daily_profit_str = f"{daily_profit:.2f}"
            percentage_val = float(val.get("percentage", 0))
            percentage_str = f"{percentage_val:.2f}%"
            color = "#e74c3c" if yield_rate_val >= 0 else "#27ae60"
            profit_color = "#e74c3c" if daily_profit >= 0 else "#27ae60"
            pct_color = "#e74c3c" if percentage_val >= 0 else "#27ae60"
            rows_html += f"""
        <tr style="background-color:#{'ecf0f1' if i % 2 == 0 else 'ffffff'};">
          <td style="padding:2px 2px;border:1px solid white;">{val["name"]}</td>
          <td style="padding:2px 2px;text-align:right;border:1px solid white;color:{pct_color};font-weight:bold;">{percentage_str}</td>
          <td style="padding:2px 2px;text-align:right;border:1px solid white;color:{profit_color};font-weight:bold;">{daily_profit_str}</td>
          <td style="padding:2px 2px;text-align:right;border:1px solid white;color:{color};font-weight:bold;">{yield_rate_str}</td>
        </tr>"""

        report_html = f"""
    <div style="margin-bottom:24px;">
      <h2 style="color:#2c3e50;border-bottom:2px solid #3498db;padding-bottom:8px;">我的持仓最新净值</h2>
      <table style="border-collapse:collapse;width:100%;font-family:Arial,sans-serif;font-size:14px;">
        <thead>
          <tr style="background-color:#3498db;color:white;">
            <th style="padding:2px 2px;text-align:left;border:1px solid white;">名称</th>
            <th style="padding:2px 2px;text-align:right;border:1px solid white;">日涨幅</th>
            <th style="padding:2px 2px;text-align:right;border:1px solid white;">收益</th>
            <th style="padding:2px 2px;text-align:right;border:1px solid white;">收益率</th>
          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
    </div>"""

        email_contents.append(report_html)

        # 计算回撤并生成邮件内容
        drawdown_results = update_peak_and_get_drawdown(TRACKED_CODES, code_to_price)

        if drawdown_results:
            drawdown_rows_html = ""
            for i, item in enumerate(drawdown_results):
                drawdown_val = item["drawdown"]
                drawdown_str = f"{drawdown_val:.2f}%"
                color = "#27ae60" if drawdown_val < 0 else "#333"
                pct_val = float(item.get("percentage", 0))
                pct_str = f"{pct_val:.2f}%"
                pct_color = "#e74c3c" if pct_val >= 0 else "#27ae60"
                adjust = item.get("adjust_diff", 0)
                if adjust:
                    adjust_str = f"{adjust:+.4f}"
                    adjust_color = "#e67e22"
                else:
                    adjust_str = "-"
                    adjust_color = "#999"
                drawdown_rows_html += f"""
        <tr style="background-color:#{'ecf0f1' if i % 2 == 0 else 'ffffff'};">
          <td style="padding:4px 8px;border:1px solid white;">{item["name"]}</td>
          <td style="padding:4px 8px;text-align:right;border:1px solid white;color:{pct_color};font-weight:bold;">{pct_str}</td>
          <td style="padding:4px 8px;text-align:right;border:1px solid white;">{item["current_price"]}</td>
          <td style="padding:4px 8px;text-align:right;border:1px solid white;">{item["peak_price"]}</td>
          <td style="padding:4px 8px;text-align:right;border:1px solid white;color:{adjust_color};font-weight:bold;">{adjust_str}</td>
          <td style="padding:4px 8px;text-align:right;border:1px solid white;color:{color};font-weight:bold;">{drawdown_str}</td>
        </tr>"""

            drawdown_html = f"""
    <div style="margin-bottom:24px;">
      <h2 style="color:#2c3e50;border-bottom:2px solid #3498db;padding-bottom:8px;">净值回撤追踪</h2>
      <table style="border-collapse:collapse;width:100%;font-family:Arial,sans-serif;font-size:14px;">
        <thead>
          <tr style="background-color:#3498db;color:white;">
            <th style="padding:4px 8px;text-align:left;border:1px solid white;">名称</th>
            <th style="padding:4px 8px;text-align:right;border:1px solid white;">昨日涨跌</th>
            <th style="padding:4px 8px;text-align:right;border:1px solid white;">当前净值</th>
            <th style="padding:4px 8px;text-align:right;border:1px solid white;">历史最高</th>
            <th style="padding:4px 8px;text-align:right;border:1px solid white;">除权</th>
            <th style="padding:4px 8px;text-align:right;border:1px solid white;">回撤</th>
          </tr>
        </thead>
        <tbody>
          {drawdown_rows_html}
        </tbody>
      </table>
    </div>"""

            email_contents.append(drawdown_html)

        # 按类型汇总占比
        from collections import defaultdict
        type_values = defaultdict(float)
        total_all = 0
        for val in datas:
            net_value = float(val["net_value"])
            share = float(val["share"])
            value = net_value * share
            # 从 db_funds 中找到对应的 type
            fund_type = None
            for rec in db_funds:
                if rec["code"] == val["code"] and rec["name"] == val["name"]:
                    fund_type = rec.get("type", "未分类")
                    break
            if not fund_type:
                fund_type = "未分类"
            type_values[fund_type] += value
            total_all += value

        # 按占比从大到小排序
        type_sorted = sorted(type_values.items(), key=lambda x: x[1], reverse=True)

        type_rows_html = ""
        for i, (fund_type, value) in enumerate(type_sorted):
            ratio = value / total_all * 100 if total_all > 0 else 0
            type_rows_html += f"""
        <tr style="background-color:#{'ecf0f1' if i % 2 == 0 else 'ffffff'};">
          <td style="padding:4px 8px;border:1px solid white;">{fund_type}</td>
          <td style="padding:4px 8px;text-align:right;border:1px solid white;">{value:.0f}</td>
          <td style="padding:4px 8px;text-align:right;border:1px solid white;font-weight:bold;">{ratio:.1f}%</td>
        </tr>"""

        type_html = f"""
    <div style="margin-bottom:24px;">
      <h2 style="color:#2c3e50;border-bottom:2px solid #3498db;padding-bottom:8px;">持仓类型占比</h2>
      <table style="border-collapse:collapse;width:100%;font-family:Arial,sans-serif;font-size:14px;">
        <thead>
          <tr style="background-color:#3498db;color:white;">
            <th style="padding:4px 8px;text-align:left;border:1px solid white;">类型</th>
            <th style="padding:4px 8px;text-align:right;border:1px solid white;">市值</th>
            <th style="padding:4px 8px;text-align:right;border:1px solid white;">占比</th>
          </tr>
        </thead>
        <tbody>
          {type_rows_html}
        </tbody>
      </table>
    </div>"""

        email_contents.append(type_html)

result = f"""
<html>
<body style="font-family:Arial,sans-serif;background:#f5f6fa;padding:24px;">
  <div style="max-width:700px;margin:0 auto;background:white;border-radius:8px;padding:24px;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
    {"".join(email_contents)}
    <p style="color:#999;font-size:12px;margin-top:24px;">数据来源：蛋卷基金 &nbsp;|&nbsp; 自动生成，请勿回复</p>
  </div>
</body>
</html>
"""
print(result)

if result:
    send_email(result)
