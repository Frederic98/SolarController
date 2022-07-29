from threading import Thread
import traceback


class TracebackThread(Thread):
    def __init__(self, *args, **kwargs):
        Thread.__init__(self, *args, **kwargs)
        self.traceback = ''
        self.exception = None

    def run(self):
        try:
            Thread.run(self)
        except Exception as e:
            self.traceback = traceback.format_exc()
            self.exception = e
            raise
