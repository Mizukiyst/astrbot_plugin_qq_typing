# QQ 私聊正在输入提示

独立 AstrBot 插件。收到 QQ 私聊的模型请求后，通过 `aiocqhttp` 的反向 WebSocket 调用 OneBot 扩展接口 `set_input_status`，每隔 4 秒刷新一次；模型回复发出后停止刷新。不发送文字消息，也不修改 QQ 在线状态。

## 安装

将整个 `astrbot_plugin_qq_typing` 目录复制到 AstrBot 的 `data/plugins/`，重启 AstrBot，在插件管理页启用。本插件要求 AstrBot 4.27.2 或更新版本、`aiocqhttp` 平台和支持 `set_input_status` 的 QQ 客户端（例如 NapCat），并使用已连接的反向 WebSocket。安装后可在配置页调整开关、刷新间隔和单条回复最长提示时间。

如果同时启用了原「我会永远陪着你」插件，请关闭其「正在输入」选项，避免对同一私聊重复调用接口。

## 行为边界

- 只处理 QQ 私聊的 AstrBot 模型回复；群聊、命令自身的回复以及其他平台不触发。
- 同一 QQ 私聊的并发请求共用一个刷新任务。工具调用期间的中途发送不会结束提示；最终回复发出后结束。
- 出错、连接断开、插件关闭或超过最长时间时停止刷新。QQ 客户端会自行让最后一次输入提示过期；插件不发送未经验证的关闭指令。
- 使用了 AstrBot `aiocqhttp` 客户端的内部反向 WebSocket 接口。若后续 AstrBot 或 QQ 客户端修改该接口，需要调整 `typing_manager.py`。

## 代码来源与致谢

本插件参考了 [menglimi 的 astrbot_plugin_private_companion](https://github.com/menglimi/astrbot_plugin_private_companion)（核对版本：`3ff6b7f`）中的 QQ「正在输入」机制：[`OneBotPresencePort.typing`](https://github.com/menglimi/astrbot_plugin_private_companion/blob/3ff6b7f/companion_v2/adapters/astrbot/presence.py#L46) 使用 `set_input_status`，[`PresenceCoordinator`](https://github.com/menglimi/astrbot_plugin_private_companion/blob/3ff6b7f/companion_v2/delivery/presence.py#L160) 按回复生命周期刷新提示。感谢原作者 menglimi。

本插件为独立重写，使用 AstrBot 事件钩子管理生命周期，不依赖原项目的数据库、角色状态或配置；并非原项目的官方拆分版本。
