#!/usr/bin/env python3
"""
同步行业数据到本地
"""
import baostock as bs
import json
import os

def sync_industry():
    lg = bs.login()
    if lg.error_code != '0':
        print("Login failed")
        return

    rs = bs.query_stock_industry()
    if rs.error_code != '0':
        print("Query failed")
        return

    df = rs.get_data()
    
    # 构建映射: 代码 -> 行业
    ind_map = {}
    for _, row in df.iterrows():
        code = row['code']
        industry = row['industry']
        if code not in ind_map:
            ind_map[code] = industry
            
    # 保存
    path = os.path.join(os.path.dirname(__file__), 'industry_map.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(ind_map, f, ensure_ascii=False)
        
    print(f"同步完成！共 {len(ind_map)} 只股票。")
    bs.logout()

if __name__ == '__main__':
    sync_industry()
