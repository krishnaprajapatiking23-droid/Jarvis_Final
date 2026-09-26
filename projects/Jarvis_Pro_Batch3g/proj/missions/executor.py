from business.manager import business_manager
from coding.manager import coding_manager


def execute_task(task, goal):

    task = task.lower()

    if "product" in task:
        return business_manager("research " + goal)

    if "competitor" in task:
        return business_manager("competitor " + goal)

    if "audience" in task:
        return business_manager("audience " + goal)

    if "pricing" in task:
        return business_manager("price " + goal)

    if "profit" in task:
        return business_manager("profit " + goal)

    if "description" in task:
        return business_manager("description " + goal)

    if "meta" in task:
        return business_manager("meta ads " + goal)

    if "strategy" in task:
        return business_manager("strategy " + goal)

    if "code" in task or "debug" in task:
        return coding_manager(goal)

    return "Task completed."