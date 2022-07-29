import datetime
from enum import Enum
from typing import Union


class DataRecordList:
    def __init__(self, data: list):
        super().__init__()
        self.data = data

    def __getitem__(self, item: Union[int, str]):
        if isinstance(item, int):
            try:
                return self.data[item]
            except IndexError:
                self.data.append(self.filler(len(self.data)))
                return self[item]
        elif isinstance(item, str):
            return {obj['name']: obj for obj in self.data}[item]

    def filler(self, index: int):
        raise NotImplementedError('DataField.filler(self, index: int) has to be overridden by subclass')


class ThermometerList(DataRecordList):
    def filler(self, index: int):
        return Thermometer(name=f'PROBE_{index}', friendly_name=f'PROBE {index}')


class RelayList(DataRecordList):
    def filler(self, index: int):
        return Relay(name=f'RELAY_{index}', friendly_name=f'RELAY {index}')


class PWMList(DataRecordList):
    def filler(self, index: int):
        return PWMOut(name=f'PWM_{index}', friendly_name=f'PWM {index}')


class AnalogInList(DataRecordList):
    def filler(self, index: int):
        return AnalogIn(name=f'ANALOG_{index}', friendly_name=f'ANALOG {index}')


class ThermometerState(Enum):
    DISCONNECTED = 0
    INITIALIZING = 1
    CONNECTED = 2

    def __eq__(self, other):
        return self.value == other


class DataRecord(dict):
    def __init__(self, config: dict = None, **kwargs):
        super().__init__()
        if config is None:
            config = {}
        elif isinstance(config, str):
            config = {'name': config}
        config.update(kwargs)
        self.config = config

        self['name'] = self.config['name']
        self['friendly_name'] = config.get('friendly_name', self['name'])

    @staticmethod
    def timestamp() -> str:
        """Returns a timestamp for the current datetime (YYYY-MM-DD HH:MM:SS)"""
        return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


class Thermometer(DataRecord):
    def __init__(self, config: dict = None, **kwargs):
        super().__init__(config, **kwargs)
        self['value'] = 0.0
        self['state'] = 0
        self['id'] = ''
        self['unit'] = '°C'

    def __setitem__(self, key, value):
        if key == 'state':
            state = ThermometerState(value)
            value = state.name
            if state == ThermometerState.DISCONNECTED:
                self['value'] = 0.0
                self['id'] = ''
        if key == 'value':
            value = float(value)
            self['timestamp'] = self.timestamp()
        super().__setitem__(key, value)


class Relay(DataRecord):
    def __init__(self, config: dict = None, **kwargs):
        super().__init__(config, **kwargs)
        self['states'] = self.config.get('states', {True: 'on', False: 'off'})
        self['state'] = 0

    def __setitem__(self, key, value):
        if key == 'state':
            value = bool(value)
            override = bool(value & 0b10)
            self['override'] = override
            self['friendly_state'] = self['states'][value]
            self['timestamp'] = self.timestamp()
        super().__setitem__(key, value)


class Analog(DataRecord):
    def __init__(self, config: dict = None, **kwargs):
        super().__init__(config, **kwargs)
        self['unit'] = '%'
        self['value'] = 0

    def __setitem__(self, key, value):
        if key == 'value':
            self['timestamp'] = self.timestamp()
        super().__setitem__(key, value)


class AnalogIn(Analog):
    def __init__(self, config: dict = None, **kwargs):
        super().__init__(config, **kwargs)
        self.calibration = None

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if key == 'value':
            self['voltage'] = self.reading2voltage(self['value'])

    def calibrate(self, calibration):
        self.calibration = calibration
        self['voltage'] = self.reading2voltage(self['value'])

    def reading2voltage(self, reading):
        if getattr(self, 'calibration', None) is None:
            return None
        return reading * self.calibration


class PWMOut(Analog):
    def __init__(self, config: dict = None, **kwargs):
        super().__init__(config, **kwargs)
        self['override'] = False
        self.min = self.config.get('min', 0)
        self.max = self.config.get('max', 100)
