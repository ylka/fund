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
    sender_email = "460646359@qq.com"
    receiver_email = "460646359@qq.com"
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

# Deprecation


def get_fund_history(fund_code, pages=1):
    url = f'http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={fund_code}&page={pages}&per=1'
    response = requests.get(url)
    html_content = response.content
    soup = BeautifulSoup(html_content, 'html.parser')
    table = soup.find('table', {'class': 'w782 comm lsjz'})
    if table:
        rows = table.find_all('tr')[1:]  # Skip the header row
        for row in rows:
            columns = row.find_all('td')
            if len(columns) > 1:
                record = {
                    'date': columns[0].text.strip(),
                    'net_value': columns[1].text.strip(),
                    'accumulated_value': columns[2].text.strip(),
                    'growth_rate': columns[3].text.strip()
                }

                return record

    print('data err')
    return None

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

        result = sorted(datas, key=lambda x: x["yield_rate"])

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
