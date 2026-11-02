import sqlite3
username = input("请输入用户名：")
conn = sqlite3.connect("test.db")
cursor = conn.cursor()
sql = f"select * from user where name='{username}'"
cursor.execute(sql)
