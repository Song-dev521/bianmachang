"""用例 3：工程权衡冲突代码（演示核心样例）。

设计意图：查询本身使用参数化绑定，安全上没有明显问题；
但每次调用都新建并关闭数据库连接，且在循环中高频调用，
制造"安全 vs 性能"的真实评审冲突，用于验证冲突汇总 Skill
识别多方分歧、输出多套可选方案的核心能力。
（依据码道 IDE 中 testcases/case_conflict.py 复原）
"""

import sqlite3


def fetch_user(username):
    conn = sqlite3.connect("test.db")
    cursor = conn.cursor()
    cursor.execute("select * from user where name = ?", (username,))
    data = cursor.fetchall()
    conn.close()
    return data


def main():
    for i in range(100):
        # 循环里反复开关数据库连接，安全上没问题，性能上有隐患
        print(fetch_user("user" + str(i)))


if __name__ == "__main__":
    main()
