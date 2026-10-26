"""Background job runner.

Heavy DSP (non-local means, Richardson-Lucy, video passes) must
not run on the Tk main loop or the window freezes.

Tk is not thread-safe, and calling `widget.after()` from a worker thread can
block on the interpreter lock, so workers never touch Tk at all: they push
callbacks into a plain queue which the GUI thread drains from a periodic poll.
"""
import queue
import threading
import traceback


class Cancelled(Exception):
    """Raised inside a worker when the job was cancelled."""


class Job:
    """One cancellable background task owned by a JobQueue."""

    def __init__(self, outbox, fn, on_done=None, on_progress=None, on_error=None):
        self.outbox = outbox
        self.fn = fn
        self.on_done = on_done
        self.on_progress = on_progress
        self.on_error = on_error
        self.cancelled = False
        self._thread = None

    # -- worker thread: queue only, never Tk --------------------------------
    def _emit(self, cb, *args):
        if cb is not None:
            self.outbox.put((cb, args))

    def _progress(self, frac, msg=""):
        if self.cancelled:
            raise Cancelled()
        self._emit(self.on_progress, frac, msg)

    def _run(self):
        try:
            result = self.fn(self._progress)
            if not self.cancelled:
                self._emit(self.on_done, result)
        except Cancelled:
            pass
        except Exception as ex:                     # surfaced in the status bar
            traceback.print_exc()
            if not self.cancelled:
                self._emit(self.on_error, ex)

    # -- GUI thread ---------------------------------------------------------
    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def cancel(self):
        self.cancelled = True

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()


class JobQueue:
    """Keeps one job per key in flight; a newer request supersedes the old one.

    Dragging a slider fires dozens of requests - only the latest matters.
    """

    POLL_MS = 30

    def __init__(self, widget):
        self.widget = widget
        self.outbox = queue.Queue()
        self._jobs = {}
        self._stopped = False
        self._poll()

    def _poll(self):
        if self._stopped:
            return
        try:
            while True:
                cb, args = self.outbox.get_nowait()
                try:
                    cb(*args)
                except Exception:
                    traceback.print_exc()
        except queue.Empty:
            pass
        try:
            self.widget.after(self.POLL_MS, self._poll)
        except Exception:                            # window destroyed
            self._stopped = True

    def submit(self, key, fn, on_done=None, on_progress=None, on_error=None):
        old = self._jobs.get(key)
        if old is not None and old.running:
            old.cancel()
        job = Job(self.outbox, fn, on_done, on_progress, on_error).start()
        self._jobs[key] = job
        return job

    def busy(self, key=None):
        if key:
            j = self._jobs.get(key)
            return bool(j and j.running)
        return any(j.running for j in self._jobs.values())

    def cancel_all(self):
        self._stopped = True
        for j in self._jobs.values():
            j.cancel()
