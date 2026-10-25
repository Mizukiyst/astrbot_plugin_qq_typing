"""Standalone QQ private-chat typing indicator for AstrBot."""

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from .typing_manager import TypingManager


def _seconds(config, name, default, minimum, maximum):
    value = config.get(name, default)
    if type(value) is not int or not minimum <= value <= maximum:
        logger.warning("QQ 正在输入：%s 配置无效，使用默认值 %s", name, default)
        return default
    return value


@register("astrbot_plugin_qq_typing", "Mizukiyst", "QQ 私聊正在输入提示", "1.0.1")
class QQTypingPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context, config)
        config = config or {}
        self.enabled = config.get("enabled", True) is True
        self.typing = TypingManager(
            refresh_seconds=_seconds(config, "refresh_seconds", 4, 1, 10),
            max_seconds=_seconds(config, "max_seconds", 300, 10, 600),
            logger=logger,
        )

    @filter.on_llm_request()
    async def on_request(self, event: AstrMessageEvent, req):
        if self.enabled:
            self.typing.start(event)

    @filter.on_agent_done()
    async def on_agent_finished(self, event: AstrMessageEvent, run_context, response):
        if getattr(response, "role", None) != "assistant":
            self.typing.finish(event)
        elif (not getattr(response, "completion_text", None)
              and not getattr(response, "result_chain", None)):
            self.typing.finish(event)

    @filter.on_decorating_result()
    async def on_result(self, event: AstrMessageEvent):
        result = event.get_result()
        kind = getattr(getattr(result, "result_content_type", None), "name", None)
        if result is None or kind in {"AGENT_RUNNER_ERROR", "STREAMING_FINISH"}:
            self.typing.finish(event)
        elif kind in {"LLM_RESULT", "STREAMING_RESULT"}:
            self.typing.mark_final_result(event)

    @filter.after_message_sent()
    async def on_sent(self, event: AstrMessageEvent):
        self.typing.finish_after_send(event)

    async def terminate(self):
        await self.typing.close()
