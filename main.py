import json
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.provider import ProviderRequest
from astrbot.api import logger

@register("owner_mode", "人格切换插件", "根据 QQ 号动态切换人格配置文件", "1.0.0")
class OwnerModePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.context = context
        self.bindings = {}  # {qq: persona_id}
        self.persona_cache = {}  # {persona_name: persona_id}
        self.load_bindings()

    def load_bindings(self):
        """从持久化存储加载绑定关系"""
        try:
            data = self.context.get_kv_data("owner_mode_bindings")
            if data:
                self.bindings = json.loads(data)
        except Exception as e:
            logger.error(f"加载绑定数据失败: {e}")

    def save_bindings(self):
        """保存绑定关系到持久化存储"""
        try:
            self.context.put_kv_data("owner_mode_bindings", json.dumps(self.bindings))
        except Exception as e:
            logger.error(f"保存绑定数据失败: {e}")

    def get_persona_id_by_name(self, name: str) -> str | None:
        """通过配置文件名获取 persona_id"""
        if name in self.persona_cache:
            return self.persona_cache[name]

        # 通过 context 获取人格管理器
        persona_mgr = self.context.persona_manager
        if persona_mgr is None:
            logger.error("无法获取人格管理器")
            return None

        personas = persona_mgr.get_all_personas()
        for p in personas:
            # 匹配名称或显示名称
            if p.name == name or getattr(p, 'display_name', '') == name:
                self.persona_cache[name] = p.persona_id
                return p.persona_id
        return None

    @filter.on_llm_request()
    async def on_llm_request(self, event: AstrMessageEvent, req: ProviderRequest):
        """根据发送者 QQ 切换配置文件"""
        sender_id = str(event.get_sender_id())
        if sender_id in self.bindings:
            target_persona_id = self.bindings[sender_id]
            # 尝试设置 persona_id（不同版本可能在不同位置）
            if hasattr(req, 'persona_id'):
                req.persona_id = target_persona_id
            elif hasattr(req, 'provider_config') and hasattr(req.provider_config, 'persona_id'):
                req.provider_config.persona_id = target_persona_id
            else:
                logger.warning("无法设置 persona_id，当前版本可能不支持")

    @filter.command("bindprofile")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def bind_profile(self, event: AstrMessageEvent, qq: str = None, persona_name: str = None):
        """绑定 QQ 号到指定配置文件，用法：/bindprofile <QQ号> <配置文件名>"""
        if not qq or not persona_name:
            yield event.plain_result("用法：/bindprofile <QQ号> <配置文件名>")
            return

        persona_id = self.get_persona_id_by_name(persona_name)
        if not persona_id:
            yield event.plain_result(f"未找到名为 '{persona_name}' 的配置文件，请检查名称是否正确")
            return

        self.bindings[qq] = persona_id
        self.save_bindings()
        yield event.plain_result(f"已将 QQ {qq} 绑定到配置文件 '{persona_name}'")

    @filter.command("unbind")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def unbind(self, event: AstrMessageEvent, qq: str = None):
        """解除绑定，用法：/unbind <QQ号>"""
        if not qq:
            yield event.plain_result("用法：/unbind <QQ号>")
            return

        if qq in self.bindings:
            del self.bindings[qq]
            self.save_bindings()
            yield event.plain_result(f"已解除 QQ {qq} 的绑定")
        else:
            yield event.plain_result(f"QQ {qq} 没有绑定任何配置文件")

    @filter.command("listbind")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def list_bind(self, event: AstrMessageEvent):
        """列出所有绑定关系"""
        if not self.bindings:
            yield event.plain_result("当前没有任何绑定关系")
            return

        # 获取所有人格以便显示名称
        persona_mgr = self.context.persona_manager
        if persona_mgr is None:
            yield event.plain_result("无法获取人格管理器")
            return

        personas = {p.persona_id: p.name for p in persona_mgr.get_all_personas()}
        lines = []
        for qq, pid in self.bindings.items():
            name = personas.get(pid, "未知配置文件")
            lines.append(f"QQ {qq} -> {name} (ID: {pid})")
        yield event.plain_result("\n".join(lines))

    async def terminate(self):
        """插件卸载时可选清理"""
        pass