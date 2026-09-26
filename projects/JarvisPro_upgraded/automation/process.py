"""
Process Manager
Jarvis Version 2
"""

import psutil


class ProcessManager:

    def list_processes(self):

        processes = []

        for process in psutil.process_iter(

            ["pid", "name"]

        ):

            try:

                processes.append(

                    {

                        "pid": process.info["pid"],

                        "name": process.info["name"]

                    }

                )

            except Exception:

                pass

        return processes

    def is_running(self, name):

        name = name.lower()

        for process in psutil.process_iter(

            ["name"]

        ):

            try:

                if process.info["name"]:

                    if name in process.info["name"].lower():

                        return True

            except Exception:

                pass

        return False

    def kill(self, name):

        name = name.lower()

        killed = 0

        for process in psutil.process_iter(

            ["name"]

        ):

            try:

                if process.info["name"]:

                    if name in process.info["name"].lower():

                        process.kill()

                        killed += 1

            except Exception:

                pass

        return {

            "success": True,

            "killed": killed

        }


processes = ProcessManager()