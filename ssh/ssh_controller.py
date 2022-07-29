import signal
import threading
import subprocess

import pigpio


class SSHController:
    def __init__(self, button, led=None, timeout=15*60):
        self.button = button
        self.led = led
        self.timeout = timeout
        self.timer: threading.Timer = None

        self.pi = pigpio.pi()
        self.pi.set_mode(self.button, pigpio.INPUT)
        if self.led is not None:
            self.pi.set_mode(self.led, pigpio.OUTPUT)
        self.pi.set_pull_up_down(self.button, pigpio.PUD_UP)
        self.pi.set_glitch_filter(self.button, 5000)    # 5000 us -> 5ms debounce
        self.pi.callback(self.button, pigpio.FALLING_EDGE, lambda io, level, tick: self.enable_ssh())

    def enable_ssh(self):
        if self.timer is not None:
            self.timer.cancel()
        subprocess.run(['systemctl', 'start', 'sshd'])
        if self.led is not None:
            self.pi.write(self.led, True)
        self.timer = threading.Timer(self.timeout, self.disable_ssh)
        self.timer.start()

    def disable_ssh(self):
        subprocess.run(['systemctl', 'stop', 'sshd'])
        if self.led is not None:
            self.pi.write(self.led, False)
        self.timer = None


controller = SSHController(button=13, led=15)
signal.pause()
