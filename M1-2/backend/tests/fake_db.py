"""Firestore 흉내 (메모리). 테스트가 실제 DB/네트워크를 쓰지 않게 한다."""
import itertools

_ids = itertools.count(1)


class Doc:
    def __init__(self, id, data):
        self.id, self._d = id, data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._d)


class Ref:
    def __init__(self, store, id):
        self.store, self.id = store, id

    def set(self, data):
        self.store[self.id] = dict(data)

    def update(self, data):
        self.store[self.id].update(data)

    def get(self):
        return Doc(self.id, self.store.get(self.id))

    def delete(self):
        self.store.pop(self.id, None)


class Col:
    def __init__(self, store):
        self.store = store

    def document(self, id=None):
        return Ref(self.store, id or f"auto{next(_ids)}")

    def stream(self):
        return [Doc(k, v) for k, v in list(self.store.items())]


class FakeDB:
    def __init__(self):
        self.cols = {}

    def collection(self, name):
        return Col(self.cols.setdefault(name, {}))
