from brains_v2.performance import performance
from brains_v2.statistics import statistics
from brains_v2.brain_state import brain_state


class RuntimeController:

    def start(self, manager, command):

        brain_state.running = True
        brain_state.command()

        manager.total_commands += 1
        manager.last_command = command

        performance.command_started(command)

    def finish(self, manager, verification):

        performance.command_finished(
            success=verification["success"]
        )

        if verification["success"]:
            manager.success_count += 1
            brain_state.success()
        else:
            manager.failed_count += 1
            brain_state.failed()

        statistics.update(verification)

        try:
            performance.update()
            performance.finish()
        except Exception:
            pass


runtime_controller = RuntimeController()