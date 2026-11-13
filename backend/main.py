# -*- coding: utf-8 -*-
"""辩码场 · 后端服务（FastAPI）

职责：接前端提交的代码，并发跑四个评审 Skill，再做冲突汇总，用 SSE 逐条推回前端。

启动：
    cd backend
    pip install -r requirements.txt
    python -m uvicorn main:app --reload --port 8000
    浏览器打开 http://127.0.0.1:8000

说明：评审用的 system prompt 直接读取 ../skills/*/prompt.md（与码道平台上同一份文件），
后端不重写提示词，只做"输出格式适配 + 并发调度 + 冲突汇总"。
"""
import asyncio
import json
import os
import time
from pathlib import Path

# 读取同目录 .env（没有就忽略）
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

import prompts
from providers import build_provider, parse_level, strip_level

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = REPO_ROOT / "index.html"

app = FastAPI(title="辩码场 · 多 Skill 冲突消解服务", version="1.0.0")

# 允许直接双击 index.html（file:// 的 Origin 为 null）时跨域访问本服务
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.get("/api/health")
async def health():
    provider, note = build_provider()
    return {
        "status": "ok",
        "mode": provider.mode,
        "model": getattr(provider, "model", ""),
        "note": note,
        "skills": prompts.all_skill_meta(),
    }


@app.get("/")
async def index():
    if INDEX_HTML.exists():
        return FileResponse(INDEX_HTML, media_type="text/html")
    return JSONResponse({"error": "index.html 不存在"}, status_code=404)


@app.post("/api/review")
async def review(request: Request):
    body = await request.json()
    code = (body.get("code") or "").strip()
    if not code:
        return JSONResponse({"error": "code 不能为空"}, status_code=400)

    provider, note = build_provider()

    async def stream():
        started = time.perf_counter()
        yield sse("start", {
            "mode": provider.mode,
            "model": getattr(provider, "model", ""),
            "note": note,
            "skills": prompts.all_skill_meta(),
        })

        queue: asyncio.Queue = asyncio.Queue()

        async def run_skill(skill: dict):
            t0 = time.perf_counter()
            try:
                text = await provider.complete(prompts.system_prompt(skill), code)
                await queue.put(("skill", {
                    "key": skill["key"],
                    "name": skill["name"],
                    "short": skill["short"],
                    "level": parse_level(text),
                    "text": strip_level(text),
                    "ms": int((time.perf_counter() - t0) * 1000),
                }))
            except Exception as exc:  # 单个 Skill 失败不拖垮整条流水线
                await queue.put(("skill_error", {
                    "key": skill["key"],
                    "name": skill["name"],
                    "short": skill["short"],
                    "error": f"{type(exc).__name__}: {exc}",
                }))

        tasks = [asyncio.create_task(run_skill(s)) for s in prompts.REVIEW_SKILLS]

        results = {}
        for _ in range(len(prompts.REVIEW_SKILLS)):
            kind, payload = await queue.get()
            if kind == "skill":
                results[payload["key"]] = payload
            yield sse(kind, payload)

        await asyncio.gather(*tasks, return_exceptions=True)

        # 有失败就不做汇总，直接把失败抛给前端，避免"缺一路还硬下结论"
        if len(results) < len(prompts.REVIEW_SKILLS):
            yield sse("error", {
                "message": "存在评审失败，已跳过冲突汇总",
                "succeeded": list(results.keys()),
            })
            yield sse("done", {"total_ms": int((time.perf_counter() - started) * 1000),
                               "mode": provider.mode, "complete": False})
            return

        yield sse("conflict_start", {"name": prompts.CONFLICT_SKILL["name"]})
        ctx_parts = []
        for s in prompts.REVIEW_SKILLS:
            r = results[s["key"]]
            ctx_parts.append(f"【{r['name']}（LEVEL={r['level']}）】\n{r['text']}")
        ctx = "\n\n".join(ctx_parts)

        t0 = time.perf_counter()
        try:
            summary = await provider.complete(prompts.conflict_prompt(), ctx)
            yield sse("conflict", {
                "name": prompts.CONFLICT_SKILL["name"],
                "text": strip_level(summary),
                "ms": int((time.perf_counter() - t0) * 1000),
            })
        except Exception as exc:
            yield sse("conflict_error", {"error": f"{type(exc).__name__}: {exc}"})

        yield sse("done", {
            "total_ms": int((time.perf_counter() - started) * 1000),
            "mode": provider.mode,
            "complete": True,
        })

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=int(os.getenv("PORT", "8000")), reload=True)
