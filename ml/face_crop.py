"""Shared crop geometry for training and serving; detection remains in the API."""


def crop_face(image, box):
    x, y, width, height = map(int, box)
    margin = int(max(width, height) * 0.15)
    return image.crop((max(0, x - margin), max(0, y - margin),
                       min(image.width, x + width + margin), min(image.height, y + height + margin)))
