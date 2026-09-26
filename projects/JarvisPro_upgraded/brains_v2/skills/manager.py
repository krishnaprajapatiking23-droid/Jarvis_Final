from brains_v2.skills.registry import all_skills


def process(command):

    for skill in all_skills():

        if skill.can_handle(command):

            return skill.execute(command)

    return None