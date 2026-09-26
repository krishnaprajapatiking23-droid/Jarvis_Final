from plugins.plugin_loader import load_plugins


def process_plugin(command):

    for plugin in load_plugins():

        if plugin.can_handle(command):

            return plugin.execute(command)

    return None