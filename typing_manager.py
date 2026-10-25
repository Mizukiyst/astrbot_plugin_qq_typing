"""QQ private-chat typing indicator over aiocqhttp reverse WebSocket."""

import asyncio
from dataclasses import dataclass, field


def _qq_number(value):
    text = str(value)
    return text if text.isascii() and text.isdigit() and int(text) > 0 else None


def private_route(event):
    message = getattr(event, "message_obj", None)
    session = getattr(event, "session", None)
    platform = getattr(event, "platform_meta", None)
    if (getattr(platform, "name", None) != "aiocqhttp"
            or getattr(getattr(message, "type", None), "value", None) != "FriendMessage"
            or getattr(getattr(session, "message_type", None), "value", None) != "FriendMessage"
            or getattr(message, "group_id", None)):
        return None
    bot_id = _qq_number(getattr(message, "self_id", None))
    user_id = _qq_number(getattr(getattr(message, "sender", None), "user_id", None))
    platform_id = getattr(platform, "id", None)
    if (not bot_id or not user_id or bot_id == user_id or not platform_id
            or getattr(session, "platform_id", None) != platform_id
            or getattr(session, "platform_name", None) != platform_id
            or str(getattr(session, "session_id", None)) != user_id):
        return None
    client = getattr(event, "bot", None)
    return (platform_id, bot_id, user_id), client


@dataclass
class Lease:
    client: object
    bot_id: str
    user_id: str
    deadlines: dict[int, float] = field(default_factory=dict)
    wake: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None


class TypingManager:
    def __init__(self, *, refresh_seconds, max_seconds, logger):
        self.refresh_seconds = refresh_seconds
        self.max_seconds = max_seconds
        self.logger = logger
        self.leases = {}
        self.events = {}
        self.final_results = set()
        self.closed = False

    def start(self, event):
        if self.closed:
            return False
        route = private_route(event)
        if route is None:
            return False
        key, client = route
        token = id(event)
        if token in self.events:
            return True
        lease = self.leases.get(key)
        if lease is None:
            lease = Lease(client, key[1], key[2])
            self.leases[key] = lease
        elif lease.client is not client:
            return False
        lease.deadlines[token] = asyncio.get_running_loop().time() + self.max_seconds
        self.events[token] = key
        owner_task = asyncio.current_task()
        if owner_task is not None:
            owner_task.add_done_callback(lambda _: self.finish(event))
        lease.wake.set()
        if lease.task is None:
            lease.task = asyncio.create_task(self._run(key, lease), name="qq-typing:" + key[2])
        return True

    def mark_final_result(self, event):
        if id(event) in self.events:
            self.final_results.add(id(event))

    def finish_after_send(self, event):
        if id(event) in self.final_results:
            self.finish(event)

    def finish(self, event):
        token = id(event)
        self.final_results.discard(token)
        key = self.events.pop(token, None)
        if key is None:
            return
        lease = self.leases.get(key)
        if lease is not None:
            lease.deadlines.pop(token, None)
            lease.wake.set()

    @staticmethod
    def _api(lease):
        client = lease.client
        clients = getattr(client, "_wsr_api_clients", None)
        api = getattr(getattr(client, "_api", None), "_wsr_api", None)
        if (clients is None or not callable(getattr(clients, "get", None))
                or not clients.get(lease.bot_id) or api is None
                or getattr(api, "_api_clients", None) is not clients
                or not callable(getattr(api, "call_action", None))):
            return None
        return api

    async def _run(self, key, lease):
        try:
            while not self.closed:
                now = asyncio.get_running_loop().time()
                for token, deadline in tuple(lease.deadlines.items()):
                    if deadline <= now:
                        lease.deadlines.pop(token, None)
                        self.events.pop(token, None)
                        self.final_results.discard(token)
                if not lease.deadlines:
                    break
                lease.wake.clear()
                api = self._api(lease)
                if api is None:
                    self.logger.warning("QQ 正在输入：反向 WebSocket 连接不可用，停止刷新")
                    break
                try:
                    result = await asyncio.wait_for(
                        api.call_action("set_input_status", self_id=lease.bot_id,
                                        user_id=int(lease.user_id), event_type=1), timeout=3)
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    self.logger.warning("QQ 正在输入：平台调用失败（%s），停止刷新", type(error).__name__)
                    break
                if not (result is None or isinstance(result, dict)
                        and result.get("retcode", 0) == 0
                        and result.get("status", "ok") in ("ok", "async")):
                    self.logger.warning("QQ 正在输入：平台拒绝请求，停止刷新")
                    break
                if not lease.deadlines:
                    break
                timeout = min(self.refresh_seconds,
                              max(0, min(lease.deadlines.values()) - asyncio.get_running_loop().time()))
                try:
                    await asyncio.wait_for(lease.wake.wait(), timeout=timeout)
                except asyncio.TimeoutError:
                    pass
        finally:
            for token in lease.deadlines:
                self.events.pop(token, None)
                self.final_results.discard(token)
            if self.leases.get(key) is lease:
                del self.leases[key]

    async def close(self):
        self.closed = True
        tasks = [lease.task for lease in self.leases.values() if lease.task is not None]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.leases.clear()
        self.events.clear()
        self.final_results.clear()
