"""
토론 실행 런타임 - 프로세스 단일 인스턴스
"""
from api.runtime.broker import EventBroker
from api.runtime.registry import DiscussionRegistry
from config.config_loader import config_loader

broker = EventBroker()
registry = DiscussionRegistry(broker, max_running=config_loader.config.limits.max_global_running)

__all__ = ["broker", "registry"]
