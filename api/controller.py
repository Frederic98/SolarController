import datetime
import select
import re

import pollable_queue
from traceback_thread import TracebackThread
import serial

from dtypes import Thermometer, Relay, PWMOut
from dtypes import ThermometerList, RelayList, AnalogInList, PWMList


def scale(val, src, dst):
    """
    Scale the given value from the scale of src to the scale of dst.
    """
    return ((val - src[0]) / (src[1]-src[0])) * (dst[1]-dst[0]) + dst[0]


def constrain(val, start, stop):
    return max(start, min(val, stop))


class SolarController:
    DATA_REGEX = re.compile(r'(?P<name>.+):(?P<index>\d+)=(?P<value>.+)')

    def __init__(self, config: dict):
        self.config = config

        # Create data containers for thermometers and relays
        self.data = {'temperature': [], 'relay': [], 'pwm': [], 'analog': [], 'health': {}}
        for key, config in self.config['temperature'].items():
            if isinstance(config, str):
                config = {'name': config}
                self.config['temperature'][key] = config
            self.data['temperature'].append(Thermometer(config))

        for key, config in self.config['relay'].items():
            if isinstance(config, str):
                config = {'name': config}
                self.config['relay'][key] = config
            self.data['relay'].append(Relay(config))

        for key, config in self.config['pwm'].items():
            if isinstance(config, str):
                config = {'name': config}
                self.config['pwm'][key] = config
            self.data['pwm'].append(PWMOut(config))

        self.data['health']['mcu'] = {'reset-source': [], 'reset-time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

        self.thermometer = ThermometerList(self.data['temperature'])
        self.relay = RelayList(self.data['relay'])
        self.pwm = PWMList(self.data['pwm'])
        self.analog = AnalogInList(self.data['analog'])

        # Serial data callbacks
        self.data_handlers = {
            'T': self.on_temperature,
            'TSTATE': self.on_thermometer_state,
            'TID': self.on_thermometer_id,
            'R': self.on_relay_state,
            'B': self.on_mcu_boot,
            'P': self.on_pwm,
            'A': self.on_analog,
            'AREF': self.on_analog_reference
        }
        # Serial comms worker
        self.write_queue = pollable_queue.PollableQueue()
        self.serial_thread = TracebackThread(target=self.serial_worker, daemon=True)
        self.serial_thread.start()

        # Request initial thermometer and relay information
        self.write_queue.put('T?')
        self.write_queue.put('R?')

    def on_temperature(self, index: int, value: str):
        self.thermometer[index]['value'] = float(value)

    def on_relay_state(self, index: int, value: str):
        self.relay[index]['state'] = int(value)

    def on_thermometer_state(self, index: int, value: str):
        self.thermometer[index]['state'] = int(value)

    def on_thermometer_id(self, index: int, value: str):
        self.thermometer[index]['id'] = value

    def on_pwm(self, index, value: str):
        pwm = self.pwm[index]
        value = scale(float(value), (pwm.min, pwm.max), (0, 100))
        pwm['value'] = value

    def on_analog(self, index: int, value: str):
        self.analog[index]['value'] = float(value)

    def on_analog_reference(self, index: int, value: str):
        voltage = index/1000    # Reference voltage is in index (mV)
        reading = float(value)  # ADC reading in %
        calibration = voltage / reading     # V/%
        for channel in self.data['analog']:
            channel.calibrate(calibration)

    def on_mcu_boot(self, index: int, value: str):
        reset_source = int(value)
        # MCUSR:     0b1000      0b0100       0b0010      0b0001
        sources = ('watchdog', 'brown-out', 'external', 'power-on')
        sources = [source for i,source in enumerate(sources[::-1]) if (reset_source >> i) & 1]
        self.data['health']['mcu']['reset-source'] = sources
        self.data['health']['mcu']['reset-time'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f'MCU reset: {", ".join(sources)}')

    def set_relay(self, name: str, value: bool):
        valid = False
        for idx, relay in enumerate(self.data['relay']):
            if name == relay['name']:
                self.write_queue.put(f'R:{idx}={1 if value else 0}')
                valid = True
        if not valid:
            raise ValueError(f"Unknown relay '{name}'")

    def set_pwm(self, name: str, value: float):
        value = constrain(value, 0, 100)
        valid = False
        for idx, pwm in enumerate(self.data['pwm']):
            if pwm['name'] == name:
                valid = True
                value = scale(value, (0,100), (pwm.min, pwm.max))
                self.write_queue.put(f'P:{idx}={value:.2f}')
        if not valid:
            raise ValueError(f"Unknown PWM channel '{name}'")

    def serial_worker(self):
        config = self.config['system']['serial']
        with serial.serial_for_url(config['port'], config['baudrate'], timeout=0) as conn:
            data = b''
            while True:
                readable, writable, exceptional = select.select([conn, self.write_queue], [], [])
                for obj in readable:
                    if obj is conn:
                        data += conn.read(50)
                        while b'\n' in data:
                            line, data = data.split(b'\n', 1)
                            self.on_serial_data(line.strip())
                    elif obj is self.write_queue:
                        line = self.write_queue.get() + '\n'
                        conn.write(line.encode('ascii'))

    def on_serial_data(self, data: bytes):
        match = self.DATA_REGEX.fullmatch(data.decode('ascii'))
        if match:
            if match.group('name') in self.data_handlers:
                self.data_handlers[match.group('name')](int(match.group('index')), match.group('value'))


if __name__ == '__main__':
    import yaml
    with open('config.yaml') as f:
        config = yaml.safe_load(f)
    controller = SolarController(config)
