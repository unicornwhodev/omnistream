"""Bounded, thread-safe observability. Never performs scene IO from log callbacks."""
import collections
import re
import threading
import time

_SECRET = re.compile(r'(?i)((?:token|password|secret|authorization|credential)\s*[=:]\s*)(?:"[^"]*"|\S+)')
_BEARER = re.compile(r'(?i)bearer\s+\S+')


def sanitize(value):
    # Redact bearer values first; otherwise the generic key matcher would only
    # consume the word Bearer, accidentally leaving its credential visible.
    value = _BEARER.sub('Bearer [REDACTED]', str(value))
    return _SECRET.sub(lambda match: match.group(1) + '[REDACTED]', value)[:1200]


class TelemetryBuffer:
    def __init__(self, capacity=400):
        self._items = collections.deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._sequence = 0
        self.dropped = 0

    def emit(self, kind, data):
        with self._lock:
            self._sequence += 1
            if len(self._items) == self._items.maxlen:
                self.dropped += 1
            item = {'sequence': self._sequence, 'atUnixMs': round(time.time()*1000),
                    'kind': kind, 'data': data}
            self._items.append(item)
            return item

    def drain(self, limit=32):
        with self._lock:
            result = []
            while self._items and len(result) < limit:
                result.append(self._items.popleft())
            return result

    def log(self, source, level, message):
        self.emit('log', {'source': sanitize(source), 'level': str(level), 'message': sanitize(message)})
