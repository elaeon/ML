import hashlib
import numpy as np
import sqlite3

from collections import OrderedDict
from dama.utils.decorators import cache
from dama.utils.logger import log_config
from dama.utils.numeric_functions import calc_chunks
from dask.base import normalize_token


log = log_config(__name__)
__all__ = ['Hash', 'Shape', 'Chunks', 'Login', 'Metadata']


class Hash:
    def __init__(self, hash_fn: str = 'sha1'):
        self.hash_fn = hash_fn
        self.hash = getattr(hashlib, hash_fn)()

    def update(self, it):
        # if it.dtype == np.dtype('<M8[ns]'):
        #     for data in it:
        #         self.hash.update(data.astype('object'))
        self.hash.update(str(tuple((t[:2] for t in map(normalize_token, it)))).encode())

    def __str__(self):
        return "{hash_fn}.{digest}".format(hash_fn=self.hash_fn, digest=self.hash.hexdigest())


class Shape(dict):

    def __getitem__(self, item):
        if isinstance(item, int):
            return self.to_tuple()[item]
        elif isinstance(item, str):
            return super(Shape, self).__getitem__(item)
        elif isinstance(item, slice):
            return self.to_tuple()[item.start:item.stop]
        else:
            raise IndexError

    def __iter__(self):
        return iter(self.to_tuple())

    def __len__(self):
        """ NOT CHANGE THIS!!, to add compatibility with shapes librarys that use shapes in tuple form,
        we define the Shape length as the tuple length"""
        return len(self.to_tuple())

    def __eq__(self, other):
        return self.to_tuple() == other

    def groups(self):
        return self.keys()

    @staticmethod
    def get_dim_shape(dim, shapes) -> list:
        values = []
        for shape in shapes:
            try:
                values.append(shape[dim])
            except IndexError:
                pass
        return values

    @cache
    def to_tuple(self) -> tuple:
        # if we have different lengths return dict of shapes
        shapes = list(self.values())
        if len(shapes) == 0:
            return tuple([0])
        elif len(shapes) == 1:
            return shapes[0]
        else:
            nshape = [self.max_length]
            max_shape = max(self.values())
            sum_groups = 0
            for shape in self.values():
                dim = shape[1:2]
                if len(dim) == 0:
                    sum_groups += 1
                else:
                    if len(shape) == len(max_shape):
                        sum_groups += dim[0]
                    else:
                        sum_groups += 1
            nshape.append(sum_groups)
            remaining = list(max_shape[2:])
            if nshape[0] == 0 and len(max_shape) == 0:
                nshape[0] = 1
            return tuple(nshape + remaining)

    def to_chunks(self, chunks) -> 'Chunks':
        if isinstance(chunks, int):
            shape = self.change_length(chunks)
            return Chunks(shape)
        else:
            return Chunks.build_from(chunks, tuple(self.groups()))

    @property
    def max_length(self) -> int:
        if super(Shape, self).__len__() > 0:
            values = [a[0] for a in self.values() if len(a) > 0]
            if len(values) > 0:
                return max(values)
        return 0

    def change_length(self, length) -> 'Shape':
        shapes = OrderedDict()
        for group, shape in self.items():
            shapes[group] = tuple([length if length < shape[0] else shape[0]] + list(shape[1:]))
        return Shape(shapes)

    @staticmethod
    def get_shape_dtypes_from_dict(data_dict) -> tuple:
        shape = dict()
        dtypes = OrderedDict()
        for group, data in data_dict.items():
            shape[group] = data.shape
            dtypes[group] = data.dtype
        return Shape(shape), np.dtype(list(dtypes.items()))


class Chunks(dict):
    static_value = 0

    def from_groups(self, chunks: tuple, groups: tuple) -> 'Chunks':
        for group in groups:
            self[group] = chunks
        return self

    @staticmethod
    def build_from(chunks, groups: tuple) -> 'Chunks':
        if not isinstance(chunks, Chunks):
            _chunks = Chunks()
            if not hasattr(chunks, '__iter__'):
                chunks = tuple([chunks])
            return _chunks.from_groups(chunks, groups)
        else:
            return chunks

    @staticmethod
    def build_from_shape(shape: Shape, dtypes: np.dtype, memory_allowed=.9) -> 'Chunks':
        chunks_dict = calc_chunks(shape, dtypes, memory_allowed=memory_allowed)
        return Chunks(chunks_dict)

    @property
    def length(self) -> int:
        return max(r0[0] for r0 in self.values())


class Login(object):
    __slots__ = ['username', 'passwd', 'resource', 'url', 'table', 'host', 'port']

    def __init__(self, username: str = None, resource: str = None, passwd: str = None, url=None,
                 table: str = None, host: str = None, port: int = None):
        self.username = username
        self.passwd = passwd
        self.resource = resource
        self.url = url
        self.table = table
        self.host = host
        self.port = port


class Metadata(dict):

    def __init__(self, driver, *args, **kwargs):
        super(Metadata, self).__init__(*args, **kwargs)
        self.driver = driver
        self.name = self.driver.login.table
        self.driver.build_url("metadata", with_class_name=False)

    def __enter__(self):
        self.driver.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.driver.close()

    def set_schema(self, dtypes: np.dtype, unique_key: list = None):
        self.driver.set_schema(dtypes, unique_key=unique_key)

    def insert_data(self):
        try:
            data = [self[group] for group in self.driver.groups]
            self.driver.insert(data)
        except sqlite3.IntegrityError as e:
            log.error(str(e) + " in " + self.driver.url)

    def insert_update_data(self, keys: list = None):
        try:
            data = [[self[group] for group in self.driver.groups]]
            self.driver[-1] = data
        except sqlite3.IntegrityError as e:
            log.warning(e)
            for key in keys:
                if self.insert_update_keys(key):
                    break
            else:
                raise Exception("This dataset already exists with another hash")

    def insert_update_keys(self, keys: list):
        if not isinstance(keys, list):
            base_keys = [keys]
        else:
            base_keys = list(keys)

        columns = ["{col}=?".format(col=group) for group in base_keys]
        query = "SELECT id FROM {name} WHERE {columns_val}".format(name=self.name,
                                                                   columns_val=" AND ".join(columns))
        values = tuple([self[key] for key in base_keys])
        query_result = self.query(query, values)
        result = len(query_result) > 0
        if result:
            index = query_result[0][0] - 1
            data = [self[group] for group in self.driver.groups]
            self.driver[index] = data
        return result

    def query(self, query: str, values: tuple) -> tuple:
        try:
            cur = self.driver.conn.cursor()
            data = cur.execute(query, values).fetchall()
            cur.close()
        except sqlite3.OperationalError as e:
            log.error(str(e) + " in " + self.driver.url)
        else:
            self.driver.conn.commit()
            return data

    def data(self):
        chunks = Chunks.build_from(10, self.driver.groups)
        return self.driver.manager(chunks)

    def remove_data(self, hash_hex: str):
        self.query("DELETE FROM {} WHERE hash = ?".format(self.name), (hash_hex, ))

    def invalid(self, hash_hex: str):
        self.query("UPDATE {} SET is_valid=? WHERE hash = ?".format(self.name), (False, hash_hex,))

    def exists(self, hash_hex: str) -> bool:
        result = self.query("SELECT id FROM {} WHERE hash = ?".format(self.name), (hash_hex, ))
        return len(result) > 0

    def is_valid(self, hash_hex: str) -> bool:
        result = self.query("SELECT is_valid FROM {} WHERE hash = ?".format(self.name), (hash_hex,))
        return result[0][0]
