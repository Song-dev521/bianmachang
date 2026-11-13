"""用例 2：含明确安全漏洞代码（SQL 注入）。

验证目标：安全评审 Skill 应报出高危（SQL 注入 / CWE-89），
其余维度各自给出本维度结论，冲突汇总 Skill 汇总共识与分歧。
（依据码道 IDE 中 testcases/case_simple_bug.py 复原）
"""

import sqlite3


def query_user(username):
    conn = sqlite3.connect("test.db")
    cursor = conn.cursor()
    sql = "select * from user where name = '" + username + "'"
    cursor.execute(sql)
    return cursor.fetchall()


name = input("请输入用户名: ")
print(query_user(name))
