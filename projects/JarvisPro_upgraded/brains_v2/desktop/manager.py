from brains_v2.desktop.mouse import move
from brains_v2.desktop.mouse import click

from brains_v2.desktop.keyboard import write
from brains_v2.desktop.keyboard import press


class Desktop:

    def move_mouse(self, x, y):

        move(x, y)

    def click(self):

        click()

    def type(self, text):

        write(text)

    def press(self, key):

        press(key)


desktop = Desktop()