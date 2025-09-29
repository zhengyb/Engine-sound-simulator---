import time
import threading

try:
    from pynput import keyboard
    _HAS_PYNPUT = True
except Exception:
    # In headless or restricted environments (no X server), pynput may fail.
    # Fall back to a non-interactive mode.
    _HAS_PYNPUT = False

class _BlockingInputThread(threading.Thread):
    '''
    The `inputs` library's IO is blocking, which means a new thread is needed to wait for
    events to avoid blocking the program when no inputs are received.
    '''
    def __init__(self, lock):
        super(_BlockingInputThread, self).__init__(daemon=True)
        self.lock = lock
        self.space_held = False
    def on_press(self, key):
        self.space_held = True
    def on_release(self, key):
        self.space_held = False
    def run(self):
        if not _HAS_PYNPUT:
            return
        listener = keyboard.Listener(
            on_press=self.on_press,
            on_release=self.on_release)
        listener.start()

def capture_input(engine):
    if _HAS_PYNPUT:
        print('Press Ctrl+C to exit, any key to rev\n')

        lock = threading.Lock()
        blockingInputThread = _BlockingInputThread(lock)
        blockingInputThread.start()

        while True:
            with lock:
                engine.throttle(1.0 if blockingInputThread.space_held else 0.0)

            time.sleep(0.02)
    else:
        print('Keyboard input unavailable (no X/GUI). Running headless demo.')
        print('Press Ctrl+C to exit. Auto-sweeping throttle...')

        # Simple automatic throttle sweep between idle and wide-open throttle
        t = 0.0
        direction = 1.0
        while True:
            t += direction * 0.02
            if t >= 1.0:
                t = 1.0
                direction = -1.0
            elif t <= 0.0:
                t = 0.0
                direction = 1.0
            engine.throttle(t)
            time.sleep(0.02)
