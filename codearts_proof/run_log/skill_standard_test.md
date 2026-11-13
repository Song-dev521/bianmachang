import sqlite3

def get_user(username):
    conn = sqlite3.connect('test.db')
    cursor = conn.cursor()
    query = "SELECT * FROM users WHERE... '"
    cursor.execute(query)
    resp = cursor.fetchall()
    conn.close()
    return resp


【规范评审结论】规范等级：较多问题

【规范问题清单】

位置：query = "SELECT * FROM users WHERE... '"

问题：SQL 语句文本残缺（止于 WHERE... '，引号未闭合、条件未写完），并非可执行代码；且未以注释或 TODO 标明这是示意片段。

影响：代码无法执行，读者无法判断原意；残缺文本混在可运行代码中，会误导后续维护者以为是真实逻辑。

修改建议：补全为完整 SQL 语句；若确为示意，改为注释块或独立的示例文件，并标注用途。

位置：def get_user(username):

问题：公共函数缺少 docstring；参数与返回值均无类型注解。

影响：调用方只能靠阅读实现推断语义，签名不自解释；静态检查与 IDE 提示失效。

修改建议：补充 docstring（用途、参数、返回值、可能的异常），并加注解 def get_user(username: str) -> list[tuple]:。

位置：函数名 get_user 与返回值 resp = cursor.fetchall()

问题：函数名表达“获取单个用户”，实际返回列表；变量 resp 为复数含义的数据却用单数命名。

影响：命名与数据形态不一致，读者与调用方对返回值基数的预期容易出错。

修改建议：统一为复数语义，如 find_users_by_name / rows / users，使名称与实际形态一致。

位置：resp、conn、cursor、query

问题：过度使用缩写；query 实为 SQL 文本，命名为 query 易与查询对象混淆。

影响：可读性下降，缩写在不同上下文中含义不稳定。

修改建议：conn → connection，cursor → cursor（可保留），query → sql，resp → rows。

位置：sqlite3.connect('test.db')、users、name

问题：库路径、表名、列名均以魔法字符串内联在函数体，未提取为常量或配置。

影响：同一常量多处重复时易改漏；test.db 的命名会让人误判运行环境。

修改建议：提取为模块级常量（如 DB_PATH）或外部配置；表名列名如多处使用应集中定义。

位置：'test.db' 与其他字符串字面量

问题：引号风格混用——路径用单引号，SQL 用双引号。

影响：同一文件内风格不统一，降低一致性观感。

修改建议：全文统一一种引号风格（PEP 8 未强制，但要求项目内一致）。

位置：cursor = conn.cursor() 与后续唯一一次 cursor.execute(query)

问题：游标对象仅使用一次，属可简化的冗余中间对象。

影响：增加一行无实际收益的样板代码，延长阅读路径。

修改建议：若无复用需求，直接 conn.execute(sql)；若保留，应说明为何需要独立游标。

位置：import sqlite3 与 def get_user 之间

问题：模块级定义前的空行不足（PEP 8 要求顶层定义前有两个空行）；模块缺少模块级 docstring。

影响：不符合 PEP 8 排版约定，工具检查会报 E302。

修改建议：补齐两个空行；在文件首行添加模块用途说明。

位置：cursor.execute(query) / cursor.fetchall() / conn.close()

问题：全程无异常处理，也无任何错误提示文本；失败时直接抛出底层异常。

影响：错误信息缺乏上下文（是谁在查哪个用户、查的哪张表），排障时信息不足。

修改建议：如需捕获，应包装为带上下文的提示（包含操作意图，不含敏感值）；至少保证资源释放路径完整。

位置：conn.close() 之前的整个函数体

问题：连接释放未使用 with 或 try/finally，属显式资源管理的裸写法。

影响：违背项目内常见的资源管理约定，异常时释放语句被跳过，代码意图不够自证。

修改建议：改用 with sqlite3.connect(...) as conn: 或 contextlib.closing，让格式本身表达资源边界。

位置：username 参数

问题：无输入约束说明（是否允许空串、None、超长值）。

影响：函数契约未在文档与签名层表达，边界行为不可预期。

修改建议：在 docstring 中声明参数约束，必要时加注解与显式校验。