import hashlib
import numpy as np
import pandas as pd
import xarray as xr

from collections import OrderedDict
from .decorators import cache
from .numeric_functions import max_dtype


class Hash:
    def __init__(self, hash_fn: str='sha1'):
        self.hash_fn = hash_fn
        self.hash = getattr(hashlib, hash_fn)()

    def update(self, it):
        for chunk in it:
            self.hash.update(chunk)

    def __str__(self):
        return "${hash_fn}${digest}".format(hash_fn=self.hash_fn, digest=self.hash.hexdigest())


class StructArray:
    def __init__(self, labels_data):
        self.labels_data = labels_data
        self.dtypes = self.columns2dtype()
        self.dtype = max_dtype(self.dtypes)
        self.o_columns = OrderedDict(self.labels_data)
        self.labels = list(self.o_columns.keys())
        self.counter = 0

    def __getitem__(self, key):
        if isinstance(key, slice):
            return self.convert(self.labels_data, key.start, key.stop)
        elif isinstance(key, str):
            columns = [(key, self.o_columns[key])]
            return self.convert_from_columns(columns, 0, self.length())
        elif isinstance(key, list):
            try:
                columns = [(col_name, self.o_columns[col_name]) for col_name in key]
            except KeyError:
                columns = [(self.labels_data[i][0], self.labels_data[i][1]) for i in key]
            return self.convert_from_columns(columns, 0, self.length())
        else:
            return self.convert_from_index(key)

    def __iter__(self):
        return self

    def __next__(self):
        try:
            elem = self[self.counter]
        except IndexError:
            raise StopIteration
        else:
            self.counter += 1
            return elem

    def is_multidim(self) -> bool:
        return len(self.labels_data[0][1].shape) >= 2

    @cache
    def length(self) -> int:
        return max([a.shape[0] for _, a in self.labels_data])

    @property
    def struct_shape(self) -> tuple:
        if len(self.labels_data) > 1:
            return tuple([self.length()])  # + [1])
        else:
            return tuple([self.length()] + list(self.labels_data[0][1].shape[1:]))

    @property
    def shape(self):
        if len(self.labels_data) > 1:
            return tuple([self.length()] + [len(self.labels_data)])
        else:
            return tuple([self.length()] + list(self.labels_data[0][1].shape[1:]))

    def columns2dtype(self) -> list:
        return [(col_name, array.dtype) for col_name, array in self.labels_data]

    def convert(self, labels_data, start_i, end_i):
        if start_i is None:
            start_i = 0

        if end_i is None:
            end_i = self.length()

        sub_labels_data = [(label, array[start_i:end_i]) for label, array in labels_data]
        return StructArray(sub_labels_data)

    def convert_from_index(self, index: int):
        sub_labels_data = []
        dtypes = dict(self.dtypes)
        for label, array in self.labels_data:
            shape = [1] + list(array.shape[1:])
            tmp_array = np.empty(shape, dtype=dtypes[label])
            tmp_array[0] = array[index]
            sub_labels_data.append((label, tmp_array))
        return StructArray(sub_labels_data)

    @staticmethod
    def convert_from_columns(labels_data: list, start_i: int, end_i: int):
        sub_labels_data = [(label, array[start_i:end_i]) for label, array in labels_data]
        return StructArray(sub_labels_data)

    @staticmethod
    def _array_builder(shape, dtypes, columns: list, start_i: int, end_i: int):
        stc_arr = np.empty(shape, dtype=dtypes)
        for col_name, array in columns:
            stc_arr[col_name] = array[start_i:end_i]
        return stc_arr

    def to_df(self, init_i: int=0, end_i=None) -> pd.DataFrame:
        data = StructArray._array_builder(self.struct_shape, self.dtypes, self.labels_data, 0, self.length())
        if end_i is None:
            end_i = self.length()
        size = abs(end_i - init_i)
        if size > data.shape[0]:
            end_i = init_i + data.shape[0]
        if len(self.dtypes) == 1 and len(data.shape) == 2:
            if self.labels is None:
                self.labels = ["c"+str(i) for i in range(data.shape[1])]
            label, _ = self.dtypes[0]
            return pd.DataFrame(data[label], index=np.arange(init_i, end_i), columns=self.labels)
        else:
            if self.labels is None:
                self.labels = [col_name for col_name, _ in self.dtypes]
            return pd.DataFrame(data, index=np.arange(init_i, end_i), columns=self.labels)

    def to_ndarray(self, dtype: list=None) -> np.ndarray:
        if dtype is None:
            dtype = self.dtype
        ndarray = np.empty(self.shape, dtype=dtype)
        if len(self.labels_data) == 1:
            _, array = self.labels_data[0]
            ndarray[:] = array[0:self.length()]
        else:
            if not self.is_multidim():
                for i, (label, array) in enumerate(self.labels_data):
                    ndarray[:, i] = array[0:self.length()]
            else:
                for i, (label, array) in enumerate(self.labels_data):
                    ndarray[:, i] = array[0:self.length()].reshape(-1)
                return ndarray
        return ndarray

    def to_xrds(self) -> xr.Dataset:
        xr_data = {}
        for label, data in self.labels_data:
            if len(data.shape) >= 2:
                dims = ["x{}".format(i) for i in range(data.shape[1])]
                data_dims = (dims, data)
                xr_data[label] = data_dims
            else:
                xr_data[label] = ("x0", data)
        return xr.Dataset(xr_data)


def unique_dtypes(dtypes) -> np.ndarray:
    return np.unique([dtype.name for _, dtype in dtypes])


def labels2num(self):
    from sklearn.preprocessing import LabelEncoder
    le = LabelEncoder()
    le.fit(self.labels)
    return le
