"""用例 1：干净、无缺陷代码。

验证目标：4 个评审 Skill 均应给出低风险/整洁类结论，
冲突汇总 Skill 应识别出"多方共识、无实质冲突"的场景。
（依据码道 IDE 中 testcases/case_normal.py 复原）
"""


def greet(name):
    return "hello, " + name


def add(a, b):
    return a + b


if __name__ == "__main__":
    print(greet("world"))
    print(add(1, 2))
