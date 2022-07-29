import os
import time
import threading

import yaml
import requests
import luma.lcd.device
import luma.core

from widgets import Widget, IPAddressWidget, TemperatureWidget, CyclerWidget, GridLayoutWidget, PowerWidget


class SolarUI(Widget):
    def __init__(self):
        with open(os.path.join(os.path.dirname(__file__), 'config.yaml'), 'rt') as f:
            self.config = yaml.safe_load(f)
        screen_config = self.config['display']

        super().__init__(width=screen_config['width'], height=screen_config['height'])

        spi = luma.core.interface.serial.spi(port=screen_config['spi_port'], device=screen_config['spi_device'],
                                             gpio_DC=screen_config['DC'], gpio_RST=screen_config['RST'])
        driver = getattr(luma.lcd.device, screen_config['driver'])
        self.display = driver(spi, width=self.width, height=self.height, gpio_LIGHT=screen_config['BL'], active_low=screen_config['BL_invert'],
                              rotate=screen_config.get('rotation', 0) // 90)
        self.display.backlight(True)

        self.ip_cycler = CyclerWidget(self, height=20, cycle_time=5)
        for interface in self.config['widgets']['network']['interfaces']:
            IPAddressWidget(self.ip_cycler, interface['interface'], interface['icon'], 'Roboto-Regular.ttf')

        temperature_layout = GridLayoutWidget(self, 4, 2, height=4*40, pos=(0,20))
        self.temperatures = []
        for i in range(8):
            widget = TemperatureWidget(temperature_layout, 'Roboto-Regular.ttf', icon_disconnect='circle-exclamation')
            widget.name = f'Temperature {i}'
            widget.value = 11*i
            self.temperatures.append(widget)

        relay_layout_pos = temperature_layout.height + 20
        relay_layout = GridLayoutWidget(self, 3, 2, height=60, pos=(0, relay_layout_pos), padding=(0,0,0,2))
        self.relays = []
        for i, relay in enumerate(self.config['widgets']['relay']):
            name = relay.get('label', relay['name'])
            widget = PowerWidget(relay_layout, 'Roboto-Regular.ttf', name=name, value=bool(i%2), icon=relay['states'])
            self.relays.append(widget)

        self.quit = threading.Event()
        threading.Thread(target=self.run_ui, daemon=False).start()

    def update(self):
        self.display.display(self.draw())
        # old = self.image.copy()
        # new = self.draw()
        # bbox = ImageChops.difference(old, new).getbbox()
        # if bbox is None:
        #     return
        # x0, y0, x1, y1 = bbox
        # with self.display_lock:
        #     # If more than 90% of the screen needs a refresh, write whole screen content, otherwise do a partial refresh
        #     if True or (((x1-x0+1) * (y1-y0+1)) / (self.width * self.height)) > 0.9:
        #         # print('whole update')
        #         self.display.display(new)
        #     else:
        #         # print(f'partial update: {((x1-x0+1) * (y1-y0+1)) / (self.width * self.height):.2%} ({x0} {x1} {y0} {y1})')
        #         self.display.set_window(x0, y0, x1, y1)
        #         image = self.display.preprocess(new.crop((x0, y0, x1, y1)))
        #         self.display.data(list(image.convert("RGB").tobytes()))
        #         # self.display.display(self.image)
        # # self.image.save('screen.png')

    def run_ui(self, interval=1):
        while not self.quit.is_set():
            self.update()
            if self.quit.wait(interval):        # wait for [interval] seconds, or break loop when quitting
                break

        self.clear_canvas()
        self.display.display(self.image)

    def run(self, interval=2):
        while not self.quit.is_set():
            try:
                resp = requests.get(self.config['server']['host'])
                resp.raise_for_status()
                data = resp.json()
                for idx, probe in enumerate(data['temperature']):
                    if self.temperatures[idx].name != probe['friendly_name']:
                        self.temperatures[idx].name = probe['friendly_name']
                    self.temperatures[idx].value = probe['value']
                    self.temperatures[idx].connected = probe['state'].upper() == 'CONNECTED'
                for idx, relay in enumerate(data['relay']):
                    if self.relays[idx].name != relay['friendly_name']:
                        self.relays[idx].name = relay['friendly_name']
                    self.relays[idx].value = relay['state']
            except requests.RequestException:
                print('Failed fetching API')
            if self.quit.wait(interval):
                break


if __name__ == '__main__':
    import signal
    ui = SolarUI()
    signal.signal(signal.SIGTERM, lambda sig, frame: ui.quit.set())
    ui.run()
