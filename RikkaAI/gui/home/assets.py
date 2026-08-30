"""Centralized paths for home-screen assets."""

import os

from PyQt5.QtGui import QIcon

import config


OUTLINE_ICON_DIR = os.path.join(config.ROOT_DIR, "ui_assets", "03_Icons", "Outline")
FIGMA_ICON_DIR = os.path.join(config.ASSETS_DIR, "figma", "icons")
HOME_IMAGE_DIR = os.path.join(config.IMAGES_DIR, "home")


def icon(name, *, figma=False):
    base = FIGMA_ICON_DIR if figma else OUTLINE_ICON_DIR
    return QIcon(os.path.join(base, f"{name}.svg"))


def image_path(name):
    return os.path.join(HOME_IMAGE_DIR, name)
