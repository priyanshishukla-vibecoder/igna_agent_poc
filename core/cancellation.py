import threading
from collections.abc import Callable


class FlowCancelled(Exception):
    """Raised when a running search flow has been cancelled."""


class CancelContext:
    """Tracks cancellation state and cleanup hooks for a single search flow."""

    def __init__(self, search_id: str):
        self.search_id = search_id
        self._event = threading.Event()
        self._callbacks: list[Callable[[], None]] = []
        self._lock = threading.Lock()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> bool:
        if self._event.is_set():
            return False

        self._event.set()
        with self._lock:
            callbacks = list(self._callbacks)

        for callback in callbacks:
            try:
                callback()
            except Exception:
                pass

        return True

    def register_callback(self, callback: Callable[[], None]) -> None:
        with self._lock:
            self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[], None]) -> None:
        with self._lock:
            self._callbacks = [registered for registered in self._callbacks if registered is not callback]

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled:
            raise FlowCancelled(f"Search flow {self.search_id} was cancelled")


_contexts: dict[str, CancelContext] = {}
_contexts_lock = threading.Lock()


def create_cancel_context(search_id: str) -> CancelContext:
    context = CancelContext(search_id)
    with _contexts_lock:
        _contexts[search_id] = context
    return context


def get_cancel_context(search_id: str) -> CancelContext | None:
    with _contexts_lock:
        return _contexts.get(search_id)


def pop_cancel_context(search_id: str) -> CancelContext | None:
    with _contexts_lock:
        return _contexts.pop(search_id, None)
