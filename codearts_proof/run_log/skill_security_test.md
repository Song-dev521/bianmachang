import sqlite3
def get_user(username):
conn = sqlite3.connect('test.db')
cursor = conn.cursor()
query = "SELECT * FROM users WHERE name = '" + username + "'"
cursor.execute(query)
return cursor.fetchall()



S1｜SQL 注入（Critical，CWE-89）
位置：query = "SELECT * FROM users WHERE name = '" + username + "'"

username 被原样拼入 SQL，任何调用方可控的输入都能改写语句结构。

这是最严重的问题，且无任何缓解措施：没有输入转义、没有白名单、没有参数化。

修复：参数化查询，让 SQL 结构与数据彻底分离。

python：
cursor.execute("SELECT id, name, email FROM users WHERE name = ?", (username,))

S2｜SELECT * 造成敏感字段过度暴露（High，CWE-213）
按列名返回全部字段，密码哈希、手机号、内部状态标记等会无差别交到调用方手里。与 S1 叠加时危害放大：注入一次即可拖走整表所有列。

修复：显式列出业务所需的列。

S3｜资源未释放，存在句柄耗尽风险（Medium，CWE-404）
conn 与 cursor 均无 close()。异常路径下连接必然泄漏；高频调用下会耗尽文件句柄，构成拒绝服务面。

修复：使用上下文管理器。
with sqlite3.connect("test.db") as conn:
    with conn.cursor() as cursor:
 更严谨可用 contextlib.closing，因 sqlite3.Connection.__exit__ 只提交/回滚事务，并不关闭连接。

S4｜无输入校验，无长度与类型约束（Medium，CWE-20）
username 为 None、超长串、含控制字符时行为未定义。即使改用参数化，缺失校验仍会带来异常注入与资源浪费。       ...

修复：


python
 
if not isinstance(username, str) or not username or len(username) > 64:
    raise ValueError("invalid username")
S5｜缺少授权/身份边界（High，CWE-862）
get_user(username) 接受任意用户名参数，函数内部不校验调用者是否有权查询该用户。若上层直接透传用户输入（例如 URL 中的 ?name=），即构成水平越权（IDOR），任何登录用户可枚举并读取他人资料。

修复：查询条件应绑定当前会话主体，并对返回结果做归属校验；敏感字段脱敏后再返回。

S6｜无结果数量上限（Medium，CWE-770）
无 LIMIT，注入或宽匹配场景下 fetchall() 全量载入，可被用于内存耗尽。

修复：加 LIMIT，或分页。

S7｜硬编码数据库路径与默认权限（Low–Medium）
'test.db' 写死且使用默认连接参数。SQLite 会在进程当前目录创建文件，权限依 umask 而定；若路径落在可写目录，存在被替换/篡改的风险。同时文件名暗示这是测试库，可能被误部署到生产。

修复：路径从配置读取，确保目录权限仅限服务账号。

S8｜异常处理缺失，错误信息可能泄露结构（Medium，CWE-209）
cursor.execute 抛出的异常原样冒泡，SQLite 的报错文本会带出表名、列名与出错 SQL 片段，为注入探测提供反馈信号。

修复：在边界处捕获并转为通用错误，详细信息仅写日志，不返回给调用方。

S9｜返回裸元组，调用方易误用（Low，CWE-1104）
fetchall() 返回 list[tuple]，字段依赖位置索引。一旦 schema 调整，调用方读取的值会静默错位，可能把非敏感字段当敏感字段处理或反之。

修复：返回具名结构或启用 row_factory = sqlite3.Row。

修复后参考实现

python
 
import sqlite3
from contextlib import closing


def get_user(username: str):
    if not isinstance(username, str) or not username or len(username) > 64:
        raise ValueError("invalid username")

    try:
        with closing(sqlite3.connect("test.db")) as conn:
            with closing(conn.cursor()) as cursor:
                cursor.execute(
                    "SELECT id, name, email FROM users WHERE name = ? LIMIT 1",
                    (username,),
                )
                return cursor.fetchall()
    except sqlite3.Error:
        # 仅记录日志，不向上层暴露 SQL 细节
        raise RuntimeError("query failed")
优先级
级别	问题
立即修复	S1 SQL 注入
上线前必须修复	S2 敏感字段暴露、S5 越权
同批次修复	S3 资源泄漏、S4 输入校验、S8 异常泄露
建议修复	S6 结果上限、S7 路径配置、S9 返回类型
结论：S1 是致命缺陷，不可通过“调用方保证输入安全”来规避——这个函数本身就是边界，必须自行落实参数化。



