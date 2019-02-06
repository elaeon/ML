import hashlib
import numpy as np
import dask.array as da
import numbers
import time

from collections import OrderedDict
from .decorators import cache


class Hash:
    def __init__(self, hash_fn: str = 'sha1'):
        self.hash_fn = hash_fn
        self.hash = getattr(hashlib, hash_fn)()

    def update(self, it):
        if it.dtype == np.dtype('<M8[ns]'):
            for data in it:
                self.hash.update(data.astype('object'))
        else:
            for data in it:
                self.hash.update(data)

    def __str__(self):
        return "${hash_fn}${digest}".format(hash_fn=self.hash_fn, digest=self.hash.hexdigest())


class Shape(object):
    def __init__(self, shape: dict):
        self._shape = shape

    def __getitem__(self, item):
        if isinstance(item, numbers.Integral):
            return self.to_tuple()[item]
        elif isinstance(item, str):
            return self._shape[item]
        elif isinstance(item, slice):
            return self.to_tuple()[item.start:item.stop]
        else:
            raise IndexError

    def __iter__(self):
        return iter(self.to_tuple())

    def __len__(self):
        """ To add compatibility with shapes that are in tuple form, we define the Shape lenght
        as the lenght of its tuple"""
        return len(self.to_tuple())

    def __eq__(self, other):
        return self.to_tuple() == other

    def __str__(self):
        return str(self._shape)

    def groups(self):
        return self._shape.keys()

    def items(self):
        return self._shape.items()

    def values(self):
        return self._shape.values()

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
        shapes = list(self._shape.values())
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

    @property
    def max_length(self) -> int:
        if len(self._shape) > 0:
            values = [a[0] for a in self._shape.values() if len(a) > 0]
            if len(values) > 0:
                return max(values)
        return 0

    def change_length(self, length) -> 'Shape':
        shapes = OrderedDict()
        for group, shape in self.items():
            shapes[group] = tuple([length] + list(shape[1:]))
        return Shape(shapes)


class Array(da.Array):
    @property
    def shape(self) -> Shape:
        tuple_shape = super(Array, self).shape
        shape = Shape({"c0": tuple_shape})
        return shape

    @property
    def dtypes(self) -> list:
        return [("c0", self.dtype)]

    @staticmethod
    def from_da(array):
        return Array(array.dask, chunks=array.chunks, dtype=array.dtype, name=array.name)


class Login(object):
    __slots__ = ['username', 'passwd', 'resource', 'url']

    def __init__(self, username: str = None, resource: str = None, passwd: str = None, url=None):
        self.username = username
        self.passwd = passwd
        self.resource = resource
        self.url = url


def unique_dtypes(dtypes) -> np.ndarray:
    return np.unique([dtype.name for _, dtype in dtypes])


def labels2num(labels):
    from sklearn.preprocessing import LabelEncoder
    le = LabelEncoder()
    le.fit(labels)
    return le


def isnamedtupleinstance(x):
    f = getattr(x, '_fields', None)
    shape = getattr(x, 'shape', None)
    return f is not None and shape is None  # x.__bases__[0] == tuple


def time2str(date):
    return time.strftime("%a, %d %b %Y %H:%M", time.gmtime(date))
