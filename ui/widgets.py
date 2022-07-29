import os
import time
import math
import threading
from io import BytesIO
from typing import Optional, Union

import numpy as np
import netifaces
from PIL import Image, ImageDraw, ImageFont, ImageChops, ImageOps
import cairosvg


def update_on_change(func):
    def wrapper(self, value):
        try:
            old = getattr(self, func.__name__)
        except AttributeError:
            old = None
        ret = func(self, value)
        new = getattr(self, func.__name__)
        if old != new:
            self.update()
        return ret
    return wrapper


class Widget:
    def __init__(self, parent: Optional['Widget'] = None, size=None, pos=(0,0), *, width=None, height=None, mode=None, background=None, **kwargs):
        super().__init__()

        if width is None:
            if size is not None and size[0] is not None:
                width = size[0]
            elif isinstance(parent, LayoutWidget):
                width = parent.child_width
            elif parent is not None:
                width = parent.width
            else:
                raise ValueError(f'No width, size or parent specified')
        if height is None:
            if size is not None and size[1] is not None:
                height = size[1]
            elif isinstance(parent, LayoutWidget):
                height = parent.child_height
            elif parent is not None:
                height = parent.height
            else:
                raise ValueError(f'No height, size or parent specified')
        if mode is None:
            if parent is not None:
                mode = parent.image.mode
            else:
                mode = 'RGB'
        if background is None:
            if parent is not None:
                background = parent.background_color
            else:
                background = '#000000'

        self.background_color = background
        self.image = Image.new(mode, (width, height), color=self.background_color)
        if parent is not None:
            parent.register_widget(self)

        self.position = pos
        self.children: list[Widget] = []

        self._update = threading.Event()

    def draw(self) -> Image.Image:
        for child in self.children:
            self.image.paste(child.draw(), child.position)
        return self.image

    @classmethod
    def load_icon(cls, path: Union[str, Image.Image], size: Union[int, tuple[int, int]], color=None, invert=True):
        if isinstance(size, (int,float)):
            w = h = int(size)
        else:
            w = int(size[0])
            h = int(size[1])
        if not path.endswith('.svg'):
            # If only a image name is given without file extension, assume it's a FontAwesome icon
            path = os.path.join(os.path.dirname(__file__), 'res/fontawesome/svgs/solid', path) + '.svg'
        out = BytesIO()
        cairosvg.svg2png(url=path, write_to=out, background_color='#ffffff', parent_width=w, parent_height=h)
        image = Image.open(out)
        if invert:                                  # If needed, invert the image colors - to convert svg with black strokes to image
            image = ImageChops.invert(image)        # with black background and white icon
        if isinstance(size, (int,float)):           # If only one size was specified, crop image to content bounding box
            image = image.crop(image.getbbox())
        if color is not None:
            image = cls.color_image(image, color)
        image.filename = path
        return image

    @classmethod
    def load_font(cls, font, size):
        path = os.path.join(os.path.dirname(__file__), 'res/fonts', font)
        return ImageFont.truetype(path, size)

    @classmethod
    def color_image(cls, image, color):
        color_image = Image.new('RGB', image.size, color=color)
        image = ImageChops.multiply(color_image, image)
        # image = ImageOps.colorize(image, '#000000', color)
        return image

    def register_widget(self, widget: 'Widget'):
        self.children.append(widget)

    @property
    def width(self):
        return self.image.width

    @property
    def height(self):
        return self.image.height

    def update(self):
        self._update.set()

    def clear_canvas(self):
        painter = ImageDraw.Draw(self.image)
        painter.rectangle(((0, 0), self.image.size), fill=self.background_color)


class LayoutWidget(Widget):
    @property
    def child_width(self):
        return self.width

    @property
    def child_height(self):
        return self.height


class GridLayoutWidget(LayoutWidget):
    def __init__(self, parent, rows, cols, padding=(0,0,0,0), **kwargs):
        super().__init__(parent, **kwargs)
        self.row_count = rows
        self.col_count = cols
        self.padding = padding

    def register_widget(self, widget: Widget):
        if len(self.children) == self.row_count * self.col_count:
            raise RuntimeError('Grid layout is full')
        super().register_widget(widget)

    @property
    def cell_width(self):
        return self.width // self.col_count

    @property
    def cell_height(self):
        return self.height // self.row_count

    @property
    def child_width(self):
        return self.cell_width - (self.padding[1] + self.padding[3])

    @property
    def child_height(self):
        return self.cell_height - (self.padding[0] + self.padding[2])

    def draw(self) -> Image.Image:
        for idx, child in enumerate(self.children):
            row = idx // self.col_count
            col = idx % self.col_count
            self.image.paste(child.draw(), (col*self.cell_width + self.padding[3], row*self.cell_height + self.padding[0]))
        return self.image


class CyclerWidget(Widget):
    def __init__(self, parent, cycle_time=0, **kwargs):
        super().__init__(parent, **kwargs)
        self.children: list[Widget] = []
        self._index = 0
        self._cycle_time = cycle_time
        self._last_change = time.time()

    def draw(self) -> Image.Image:
        if self._cycle_time > 0 and time.time() - self._last_change > self._cycle_time:
            self.next()
        child = self.children[self.index]
        sub_image = child.draw()
        self.image.paste(sub_image, (0,0))
        return self.image

    @property
    def index(self):
        return self._index

    @index.setter
    def index(self, idx):
        self._index = idx % len(self.children)
        self._last_change = time.time()

    def next(self):
        self.index += 1

    def previous(self):
        self.index -= 1


class ScrollingTextWidget(Widget):
    def __init__(self, parent, font, text='', stepsize=1, **kwargs):
        super().__init__(parent, **kwargs)
        self.text_img: Optional[Image.Image] = None
        # font = os.path.join(os.path.dirname(__file__), 'Roboto-Regular.ttf')
        self.font = ImageFont.truetype(font, self.image.size[1] - 2)
        self.set_text(text)
        self.idx = 0
        self.stepsize = stepsize

    def set_text(self, text):
        width = math.ceil(self.font.getlength(text))
        self.text_img = Image.new(self.image.mode, (width+15, self.image.height), color='#000000')
        painter = ImageDraw.Draw(self.text_img)
        painter.text((0,1), text, font=self.font)

    def draw(self):
        self.image.paste(ImageChops.offset(self.text_img, -self.idx, 0), (0, 0))
        self.idx += self.stepsize
        self.idx %= self.text_img.width
        return self.image


class TemperatureWidget(Widget):
    def __init__(self, parent, font, name='', value=0, connected=False, icon='temperature-half', **kwargs):
        super().__init__(parent, **kwargs)

        self.font = self.load_font(font, (self.image.size[1] // 2) - 2)
        self.name = name
        self.value = value
        self.connected = connected
        self.icon = self.load_icon(icon, self.image.height-4)
        if 'icon_disconnect' in kwargs:
            self.icon_disconnect = self.load_icon(kwargs['icon_disconnect'], size=self.icon.size)
        else:
            self.icon_disconnect = self.icon

    @property
    def name(self):
        return self._name

    @name.setter
    @update_on_change
    def name(self, name):
        self._name = name

    @property
    def value(self):
        return self._value

    @value.setter
    @update_on_change
    def value(self, value):
        self._value = value

    @property
    def connected(self):
        return self._connected

    @connected.setter
    @update_on_change
    def connected(self, connected):
        self._connected = bool(connected)

    def draw(self):
        if self._update.is_set():
            self._update.clear()
            painter = ImageDraw.Draw(self.image)
            painter.rectangle(((0,0), self.image.size), fill=self.background_color)

            if self.connected:
                icon = self.color_image(self.icon, self.temperature2color(self.value))
            else:
                icon = self.color_image(self.icon_disconnect, '#ff0000')
            self.image.paste(icon, (0, (self.height - self.icon.height) // 2))

            text_xpos = self.icon.width + 5
            painter.text((text_xpos, 1), self.name, font=self.font)
            text = f'{self.value:.1f}°C' if self.connected else ''
            painter.text((text_xpos, (self.image.height // 2) + 1), text, font=self.font)
        return self.image

    @staticmethod
    def temperature2color(temperature):
        hue = np.interp(temperature, (0,100), (290,0))
        return f'hsv({hue:.1f}, 100%, 100%)'


class PowerWidget(Widget):
    def __init__(self, parent, font, name='', value=False, icon: Union[dict, str] = 'power-off', **kwargs):
        super().__init__(parent, **kwargs)
        self.font = self.load_font(font, self.height - 2)
        # self.icon = self.load_icon(icon, self.height - 2)
        if isinstance(icon, str):
            icon = {True: {'icon': icon, 'color': 'green'}, False: {'icon': icon, 'color': 'red'}}
        self.icons = {state: RotatingIcon(self, size=(self.height-2, self.height-2), **args) for state, args in icon.items()}
        self.name = name
        self.value = value

    @property
    def name(self):
        return self._name

    @name.setter
    @update_on_change
    def name(self, name):
        self._name = name

    def draw(self) -> Image.Image:
        icon: RotatingIcon = self.icons[self.value]
        self.image.paste(icon.draw(), (0,1))                                        # Paste icon
        if self._update.is_set():
            self._update.clear()
            painter = ImageDraw.Draw(self.image)
            painter.rectangle(((icon.width, 0), (self.width, self.height)), fill='#000000')      # Clear image
            painter.text((icon.width + 5, 1), self.name, font=self.font)                # Draw text
        return self.image


class IPAddressWidget(Widget):
    def __init__(self, parent, interface, icon, font, **kwargs):
        super().__init__(parent, **kwargs)
        self.interface = interface
        self.icon_name = icon
        self.font_name = font
        self.icon = self.load_icon(icon, self.image.height)
        self.font = self.load_font(font, self.image.height - 2)

    def draw(self):
        painter = ImageDraw.Draw(self.image)
        painter.rectangle(((0,0), self.image.size), fill=self.background_color)

        self.image.paste(self.icon, (0, 0))

        addresses = netifaces.ifaddresses(self.interface)
        if netifaces.AF_INET in addresses:
            address = addresses[netifaces.AF_INET][0]['addr']
        else:
            address = 'NOT CONNECTED'
            painter.line(((0,self.icon.height), (self.icon.width, 0)), fill='#ff0000', width=2)
        painter.text((self.icon.width + 5, 1), f'{self.interface}: {address}', font=self.font)
        return self.image


class Icon(Widget):
    def __init__(self, parent, icon, color=None, invert=True, **kwargs):
        super().__init__(parent, **kwargs)
        self.base_icon = self.load_icon(icon, (self.width, self.height), invert=invert)
        self.color = color
        self.icon = self._preprocess_icon()

    def draw(self) -> Image.Image:
        self.image.paste(self.icon, (0,0))
        return self.image

    @property
    def color(self):
        return self._color

    @color.setter
    def color(self, color):
        self._color = color
        self._preprocess_icon()

    def _preprocess_icon(self) -> Image.Image:
        image = self.base_icon.copy()
        if self.color is not None:
            image = self.color_image(image, self.color)
        return image


class RotatingIcon(Icon):
    def __init__(self, parent, icon, speed=5, rotating=False, **kwargs):
        super().__init__(parent, icon, **kwargs)
        self.speed = speed
        self.idx = 0
        self.rotating = rotating
        self.last_update = 0

    def draw(self) -> Image.Image:
        if time.time() - self.last_update > self.speed/4:
            self.last_update = time.time()
            icon = self.icon
            if self.rotating:
                icon = self.icon.rotate(90*self.idx, fillcolor='#000000')
                self.idx += 1
            self.image.paste(icon, (0,0))
        return self.image
