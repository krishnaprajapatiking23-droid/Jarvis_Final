class RuntimeCacheController:

    def clear(self, manager):

        manager.last_reply = None
        manager.last_result = None


runtime_cache_controller = RuntimeCacheController()