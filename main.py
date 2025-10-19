import requests
from bs4 import BeautifulSoup
import pandas as pd
from tqdm import tqdm


def get_fund_history(fund_code, pages=1):
    all_data = {}

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

                all_data = record

    return all_data


def save_to_csv(data, filename):
    df = pd.DataFrame(data)
    df.to_csv(filename, index=False)


df = pd.read_csv('s_plan.csv', header=None, dtype=str)
column_data = df[0].tolist()
datas = []

for fund_code, name, cost in tqdm(df.to_numpy()):
    fund_data = get_fund_history(fund_code)
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

save_to_csv(datas, 'update_s_plan.csv')

with open('README.md', 'w', encoding='utf-8') as f:
    f.write(f'# S 计划持仓最新净值\n')
    f.write(f'| 代码 | 名称 | 成本 | 最新净值（{datas[0]["date"]}) | 收益率 |\n')
    f.write(f'| --- | --- | --- | --- | --- |\n')

    result = sorted(datas, key=lambda x: x["yield_rate"])
    for val in result:
        net_value = val["net_value"]
        yield_rate = f"{val['yield_rate'] * 100:.2f}%"
        f.write(
            f'| {val["fund_code"]} | {val["name"]} | {val["cost"]} | {net_value} | {yield_rate} |\n')

print("Data saved to update_s_plan.csv and README.md")
