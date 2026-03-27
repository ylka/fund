import os
from dotenv import load_dotenv

import requests
from bs4 import BeautifulSoup
import pandas as pd
from email.mime.text import MIMEText
import smtplib

from tqdm import tqdm

# Load environment variables from .env file
load_dotenv()


def send_email(result):
    # 发送邮件通知
    sender_email = "460646359@qq.com"
    receiver_email = "460646359@qq.com"
    password = os.getenv('EMAIL_PASSWORD')  # 从环境变量读取密码

    if not password:
        print('password error')
    else:
        msg = MIMEText(result)
        msg['Subject'] = "S 计划最新数据"
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

            record = {
                'date': data['date'].strip(),
                'net_value': data['nav'].strip(),
                'accumulated_value': data['nav'].strip(),
                'growth_rate': data['percentage'].strip()
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


def save_to_csv(data, filename):
    df = pd.DataFrame(data)
    df.to_csv(filename, index=False)
    return df.to_csv(index=False)


email_contents = []

# df = pd.read_csv('s_plan.csv', header=None, dtype=str)
for file in ["my-code.csv", "s_plan.csv",  "oversea-code.csv"]:
    df = pd.read_csv(file, header=None, dtype=str)
    column_data = df[0].tolist()
    datas = []

    for fund_code, name, cost in tqdm(df.to_numpy()):
        fund_data = get_fund_from_danjuan(fund_code)
        # if not fund_data:
        # fund_data = get_fund_history(fund_code)

        if fund_data:
            data = {
                'date': fund_data.get('date', None),
                'fund_code': fund_code,
                'net_value': fund_data.get('net_value', None),
                'accumulated_value': fund_data.get('accumulated_value', None),
                'name': name,
                'cost': cost,
                'yield_rate': float(fund_data.get('net_value', None))/float(cost) - 1
            }
            datas.append(data)

    if datas == []:
        print(f'{file} no data')
        continue

    reports = []
    if file == "s_plan.csv":
        reports.append('# S 计划持仓最新净值\n')
    elif file == "oversea-code.csv":
        reports.append('# S 计划海外最新净值\n')
    else:
        reports.append('# 我的持仓最新净值\n')

    reports.append(f'代码,名称,成本,最新净值,收益率\n')

    result = sorted(datas, key=lambda x: x["yield_rate"])
    for val in result:
        net_value = val["net_value"]
        yield_rate = f"{val['yield_rate'] * 100:.2f}%"
        reports.append(
            f'{val["fund_code"]},{val["name"]},{val["cost"]},{net_value},{yield_rate}\n')

    email_contents.append("".join(reports))
    email_contents.append("\r\n")

result = "".join(email_contents)
print(result)

if result:
    send_email(result)
