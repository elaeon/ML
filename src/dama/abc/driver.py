from abc import ABC, abstractmethod
from numcodecs.abc import Codec
import numpy as np
import os
from dama.utils.config import get_settings
from dama.utils.logger import log_config
from dama.utils.core import Login, Chunks, Shape
from dama.utils.files import build_path
from dama.abc.conn import AbsConn
from dama.fmtypes import Slice
from numbers import Number
from tqdm import tqdm


settings = get_settings("paths")
log = log_config(__name__)
__all__ = ['AbsDriver']


class AbsDriver(ABC):
    persistent = None
    ext = None
    insert_by_rows = None
    data_tag = None

    def __init__(self, compressor: Codec = None, login: Login = None, mode: str = 'a', path: str = None, conn=None):
        self.compressor = compressor
        self.conn = conn
        if compressor is not None:
            self.compressor_params = {"compression": self.compressor.codec_id,
                                      "compression_opts": self.compressor.level}
        else:
            self.compressor_params = {}

        self.mode = mode
        self.attrs = None
        self.path = path
        self.url = None
        self.login = login
        log.debug("Driver: {}, mode: {}, compressor: {}".format(self.cls_name(),
                                                                self.mode, self.compressor))

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @abstractmethod
    def __getitem__(self, item):
        return NotImplemented

    @abstractmethod
    def __setitem__(self, key, value):
        return NotImplemented

    def build_url(self, filename, group_level=None, with_class_name=True):
        filename = "{}.{}".format(filename, self.ext)

        if with_class_name is True:
            if group_level is None:
                dir_levels = [self.path, self.cls_name(), filename]
            else:
                dir_levels = [self.path, self.cls_name(), group_level, filename]
        else:
            dir_levels = [self.path, filename]
        self.url = os.path.join(*dir_levels)
        build_path(dir_levels[:-1])

    @abstractmethod
    def manager(self, chunks: Chunks) -> AbsConn:
        return NotImplemented

    @abstractmethod
    def absconn(self) -> AbsConn:
        return NotImplemented

    @classmethod
    def module_cls_name(cls):
        return "{}.{}".format(cls.__module__, cls.__name__)

    @classmethod
    def cls_name(cls):
        return cls.__name__

    @abstractmethod
    def open(self):
        return NotImplemented

    @abstractmethod
    def close(self):
        return NotImplemented

    @property
    @abstractmethod
    def dtypes(self):
        return NotImplemented

    @property
    def groups(self):
        if self.dtypes is not None:
            return self.dtypes.names

    @abstractmethod
    def set_schema(self, dtypes: np.dtype, idx: list = None, unique_key: list = None):
        return NotImplemented

    @abstractmethod
    def set_data_shape(self, shape):
        return NotImplemented

    @abstractmethod
    def destroy(self):
        return NotImplemented

    @abstractmethod
    def exists(self):
        return NotImplemented

    @abstractmethod
    def spaces(self):
        return NotImplemented

    def store(self, manager: AbsConn):
        if self.insert_by_rows is True:
            from dama.data.it import Iterator
            data = Iterator(manager).batchs(chunks=manager.chunksize)
            self.batchs_writer(data)
        else:
            manager.store(self)

    def batchs_writer(self, data):
        batch_size = getattr(data, 'batch_size', 0)
        log.info("Writing with chunks {}".format(batch_size))
        if batch_size > 0:
            for smx in tqdm(data, total=data.num_splits()):
                self.setitem(smx.slice, smx)
        else:
            for i, smx in tqdm(enumerate(data), total=data.num_splits()):
                for j, group in enumerate(self.groups):
                    self[group][i] = smx[j]

    def setitem(self, item, value):
        if self.insert_by_rows is True:
            self[item] = value
        else:
            if isinstance(value, AbsConn):
                for group in value.groups:
                    self[group][item] = value[group].to_ndarray()
            elif type(value) == Slice:
                for group in value.batch.groups:
                    self[group][item] = value.batch[group].to_ndarray()
            elif isinstance(value, Number):
                self[item] = value
            elif isinstance(value, np.ndarray):
                self[item] = value
            else:
                if isinstance(item, str):
                    self[item] = value

    @property
    @abstractmethod
    def shape(self) -> Shape:
        return NotImplemented
