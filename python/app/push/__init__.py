"""推送通道抽象。

设计：
- 每个通道实现 `async def send(content: PushContent, config: dict) -> PushResult`
- dispatcher 按 `subscription.push_channel` 路由到对应通道
- 新增通道只需在 `CHANNELS` 注册一个 async 函数
"""
