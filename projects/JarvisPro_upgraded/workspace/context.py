from workspace.state import workspace


def show_context():

    return f"""
========== WORKSPACE ==========

Project : {workspace["project"]}

Task : {workspace["current_task"]}

Last File : {workspace["last_file"]}

===============================
"""