from concurrent.futures import ThreadPoolExecutor, as_completed


class Orchestrator:

    def __init__(self):

        self.modules = {}

    # -------------------------
    # Registry
    # -------------------------

    def register(self, name, module):

        self.modules[name] = module

    def unregister(self, name):

        if name in self.modules:

            del self.modules[name]

    def exists(self, name):

        return name in self.modules

    def get(self, name):

        return self.modules.get(name)

    def all(self):

        return list(self.modules.keys())

    def clear(self):

        self.modules.clear()

    # -------------------------
    # Execution
    # -------------------------

    def execute(self, name, *args, **kwargs):

        module = self.get(name)

        if module is None:

            return None

        try:

            if hasattr(module, "run"):

                return module.run(*args, **kwargs)

            if hasattr(module, "execute"):

                return module.execute(*args, **kwargs)

            if callable(module):

                return module(*args, **kwargs)

        except Exception as e:

            return {

                "success": False,

                "module": name,

                "error": str(e)

            }

        return None

    # -------------------------
    # Execute All
    # -------------------------

    def execute_all(self, *args, **kwargs):

        results = {}

        for name in self.modules:

            results[name] = self.execute(

                name,

                *args,

                **kwargs

            )

        return results

    # -------------------------
    # Parallel Execution
    # -------------------------

    def execute_parallel(self, *args, **kwargs):

        results = {}

        with ThreadPoolExecutor() as executor:

            futures = {

                executor.submit(

                    self.execute,

                    name,

                    *args,

                    **kwargs

                ): name

                for name in self.modules

            }

            for future in as_completed(futures):

                name = futures[future]

                try:

                    results[name] = future.result()

                except Exception as e:

                    results[name] = {

                        "success": False,

                        "error": str(e)

                    }

        return results

    # -------------------------
    # Priority Order
    # -------------------------

    def priority_modules(self):

        modules = list(self.modules.items())

        modules.sort(

            key=lambda x: getattr(

                x[1],

                "priority",

                0

            ),

            reverse=True

        )

        return modules

    # -------------------------
    # Intelligent Dispatch
    # -------------------------

    def dispatch(self, command):

        for name, module in self.priority_modules():

            try:

                if hasattr(module, "can_handle"):

                    if module.can_handle(command):

                        if hasattr(module, "execute"):

                            return module.execute(command)

                        elif hasattr(module, "run"):

                            return module.run(command)

            except Exception:

                continue

        return None

    # -------------------------
    # Statistics
    # -------------------------

    def statistics(self):

        return {

            "registered_modules": len(self.modules),

            "modules": self.all()

        }


orchestrator = Orchestrator()