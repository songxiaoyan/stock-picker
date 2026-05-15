#!/usr/bin/env python3
"""
测试腾讯接口字段索引
"""
import requests

codes = "sh600776,sz002676,sz300397"
url = f'http://qt.gtimg.cn/q={codes}'

resp = requests.get(url, timeout=5)
resp.encoding = 'gbk'

lines = resp.text.split(';')
for line in lines:
    if '=' in line:
        match = re.search(r'="([^"]*)"', line)
        if match:
            d = match.group(1).split('~')
            print(f"代码: {d[2]}, 名称: {d[1]}")
            # 打印关键索引内容
            print(f"索引39 (成交额): {d[39]}")
            print(f"索引44 (流通市值): {d[44]}")
            print(f"索引49 (行业?): {d[49]}")
            print(f"索引50 (概念?): {d[50]}")
            print(f"索引51 (名称): {d[51]}")
            print(f"索引52 (今日开盘): {d[52]}")
            print("-" * 50)
