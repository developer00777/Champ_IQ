"""Flow nodes: Loop, Wait."""
from __future__ import annotations

import asyncio
from typing import Any

from ..core.interfaces import NodeContext, NodeExecutor, NodeResult


class LoopExecutor(NodeExecutor):
    """Iterates over an array one item at a time.

    Config fields:
        items           expression resolving to a list  (required)
        concurrency     parallel items at once          (default: 1)
        each            per-item expression template    (optional)
        wait_for_event  event name to wait for before
                        moving to the next item         (optional)
                        e.g. "transcript.ready" — the loop
                        subscribes to the bus and blocks
                        until that event fires (or timeout).
        wait_timeout    seconds to wait for the event   (default: 300)
    """

    kind = "loop"

    async def execute(self, ctx: NodeContext) -> NodeResult:
        items = ctx.render(ctx.config.get("items", []))
        if not isinstance(items, list):
            raise TypeError("loop.items must render to a list")

        concurrency = int(ctx.config.get("concurrency", 1))
        template = ctx.config.get("each", {}) or {}
        wait_event: str | None = ctx.config.get("wait_for_event") or None
        wait_timeout: int = int(ctx.config.get("wait_timeout", 300))

        def _make_sub_ctx(item: Any, index: int) -> dict[str, Any]:
            sub = dict(ctx.expression_context())
            sub["item"] = item
            sub["index"] = index
            sub["prev"] = {"item": item, "index": index, **(ctx.input or {})}
            return sub

        async def _render_one(item: Any, index: int) -> dict[str, Any]:
            sub_ctx = _make_sub_ctx(item, index)
            rendered = ctx.expressions.evaluate(template, sub_ctx)
            return rendered if isinstance(rendered, dict) else {"value": rendered}

        async def _wait_for_completion(index: int) -> None:
            """Subscribe to wait_event and block until it fires or times out."""
            if wait_event is None:
                return
            try:
                async with asyncio.timeout(wait_timeout):
                    async for _ in ctx.events.subscribe(wait_event):
                        # Any firing of this event means the call completed —
                        # break and move to the next item.
                        break
            except asyncio.TimeoutError:
                # Timeout — log and continue to avoid stalling the whole loop.
                await ctx.emit("loop.item_timeout", {
                    "index": index,
                    "event": wait_event,
                    "timeout": wait_timeout,
                })

        results: list[dict[str, Any]] = []

        if concurrency == 1 or wait_event:
            # Sequential: process one item fully (including waiting for the
            # completion event) before moving to the next.
            for index, item in enumerate(items):
                rendered = await _render_one(item, index)
                results.append(rendered)
                await ctx.emit("loop.item_started", {"index": index, "item": item})
                await _wait_for_completion(index)
                await ctx.emit("loop.item_done", {"index": index})
        else:
            # Parallel with concurrency cap — no event waiting.
            sem = asyncio.Semaphore(max(concurrency, 1))

            async def _guarded(item: Any, index: int) -> dict[str, Any]:
                async with sem:
                    return await _render_one(item, index)

            results = await asyncio.gather(
                *[_guarded(item, i) for i, item in enumerate(items)]
            )

        return NodeResult(output={"items": results, "count": len(results)})


class WaitExecutor(NodeExecutor):
    kind = "wait"

    async def execute(self, ctx: NodeContext) -> NodeResult:
        seconds = int(ctx.render(ctx.config.get("seconds", 0)) or 0)
        if seconds > 0:
            await asyncio.sleep(min(seconds, 3600))
        return NodeResult(output={"waited": seconds})
