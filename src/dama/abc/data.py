from abc import ABC, abstractmethod


class AbsData(ABC):
    # _graphviz_shape = 'ellipse'
    # _graphviz_style = 'rounded,filled'
    # _graphviz_fillcolor = 'white'
    # _graphviz_orientation = 0
    driver = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, value, traceback):
        self.close()

    @abstractmethod
    def __iter__(self):
        raise NotImplementedError

    @abstractmethod
    def __getitem__(self, key):
        return NotImplemented

    @abstractmethod
    def open(self):
        return NotImplemented

    @abstractmethod
    def close(self):
        return NotImplemented

    @property
    def data(self):
        return NotImplemented

    @abstractmethod
    def __next__(self):
        return NotImplemented

    @abstractmethod
    def destroy(self):
        return NotImplemented

    @abstractmethod
    def url(self):
        return NotImplemented

    @property
    @abstractmethod
    def shape(self):
        return NotImplemented

    @property
    @abstractmethod
    def groups(self):
        return NotImplemented

    @property
    @abstractmethod
    def dtypes(self):
        return NotImplemented
