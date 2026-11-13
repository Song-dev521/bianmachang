# 辩码场 · 后端服务

把码道上验证过的 5 个 Skill（`../skills/*/prompt.md`，与平台同源）搬进可服务化后端：
前端提交代码 → 四路评审并发执行 → 冲突汇总 → SSE 逐条推回页面。

## 启动（两条命令）

```bash
pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

然后浏览器打开 <http://127.0.0.1:8000>（后端会直接托管 `../index.html`）。
双击 `run.bat` 等价于以上过程。

## 运行模式

| MODE | 行为 |
|---|---|
| `maas` | 强制真实调用华为云 MaaS（需 `MAAS_API_KEY`） |
| `replay` | 强制回放 `replay.json`（内容节选自 `codearts_proof/run_log` 真实运行记录） |
| `auto`（默认） | 有 Key 走真实，没 Key 自动回放 |

页面右上角会显示当前模式；后端未启动时前端自动进入"离线演示"（内置样例结论），**不会假装是真实结果**。

## 硬约束

- **模型白名单**：`providers.py` 中 `ALLOWED_MODELS` 只允许 `deepseek-v4.1-flash-1017`，
  配置成其他模型会直接拒绝启动（防止误消耗其他模型额度）。
- `backend/.env` 含密钥，已被仓库根 `.gitignore` 忽略，**禁止提交、禁止打进交付包**。

## 接口

- `GET /api/health` —— 模式 / 模型 / Skill 清单
- `POST /api/review` —— body `{"code": "..."}`，SSE 事件流：
  `start → skill×4（逐条）→ conflict_start → conflict → done`

## 设计边界（诚实口径）

后端调用的是**华为云 MaaS 大模型 + 码道同源 Prompt**，不是码道流水线本身。
所有材料表述必须写成：*"在码道平台完成 Skill 研发与验证，并将其服务化移植，
使教学场景脱离 IDE 也可运行；Prompt 与码道仓库完全一致（见 skills/）。"*
禁止写成"前端调用了码道流水线 / 码道 API"。
