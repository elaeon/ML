from ml.abc.group import AbsGroup, AbsBaseGroup
from ml.abc.data import AbsData
from ml.utils.basic import Shape
import numpy as np
from collections import OrderedDict
import dask.array as da
import numbers


class DaGroupDict(OrderedDict):
    def __init__(self, *args, map_rename=None, **kwargs):
        super(DaGroupDict, self).__init__(*args, **kwargs)
        if map_rename is None:
            self.map_rename = {}
        else:
            self.map_rename = map_rename

    def rename(self, key, new_key) -> 'DaGroupDict':
        map_rename = self.map_rename.copy()
        map_rename[new_key] = key
        return DaGroupDict(((new_key if k == key else k, v) for k, v in self.items()), map_rename=map_rename)

    def get_oldname(self, name) -> str:
        return self.map_rename.get(name, name)


class DaGroup(AbsGroup):
    def __init__(self, conn, chunks=None, from_groups=None, writer_conn=None):
        if isinstance(conn, DaGroupDict):
            reader_conn = conn
        elif isinstance(conn, dict):
            reader_conn = self.convert(conn, chunks=chunks)
        elif isinstance(conn, AbsBaseGroup) or AbsGroup:
            groups = OrderedDict()
            #if from_groups is not None:
            #    for group in conn.groups:
            #        if group in from_groups:
            #            groups[group] = conn.conn[group]
            #else:
            for group in conn.groups:
                groups[group] = conn.get_group(group)
            reader_conn = self.convert(groups, chunks=chunks)
            if writer_conn is None:
                writer_conn = conn
        else:
            raise NotImplementedError("Type {} does not supported".format(type(conn)))
        super(DaGroup, self).__init__(reader_conn, writer_conn=writer_conn)

    def convert(self, groups_dict, chunks) -> dict:
        groups = DaGroupDict()
        for group, data in groups_dict.items():
            chunks = data.shape  # fixme
            groups[group] = da.from_array(data, chunks=chunks)
        return groups

    def sample(self, index):
        return self.set_values(self.groups, index)

    @property
    def dtypes(self) -> np.dtype:
        return np.dtype([(group, self.conn[group].dtype) for group in self.conn.keys()])

    def set_values(self, groups, item) -> 'DaGroup':
        dict_conn = DaGroupDict(map_rename=self.conn.map_rename)
        for group in groups:
            dict_conn[group] = self.conn[group][item]
        return DaGroup(dict_conn, writer_conn=self.writer_conn)

    def __getitem__(self, item) -> 'DaGroup':
        if isinstance(item, slice):
            return self.set_values(self.groups, item)
        elif isinstance(item, str):
            dict_conn = DaGroupDict(map_rename=self.conn.map_rename)
            dict_conn[item] =  self.conn[item]
            return DaGroup(dict_conn, writer_conn=self.writer_conn)
        elif isinstance(item, int):
            return self.set_values(self.groups, item)
        elif isinstance(item, list):
            dict_conn = DaGroupDict(map_rename=self.conn.map_rename)
            for group in item:
                dict_conn[group] = self.conn[group]
            return DaGroup(dict_conn, writer_conn=self.writer_conn)
        elif isinstance(item, np.ndarray) and item.dtype == np.dtype(int):
            return self.sample(item)

    def __setitem__(self, item, value):
        if self.writer_conn:#.inblock is True:
            batch_size = 2
            init = 0
            end = batch_size
            init_g = init
            end_g = end
            shape = tuple([batch_size] + list(self.shape.to_tuple())[1:])
            while True:
                total_cols = 0
                data = np.empty(shape, dtype=float)
                for group in self.groups:
                    try:
                        num_cols = self.shape[group][1]
                        slice_grp = (slice(init_g, end_g), slice(total_cols, total_cols + num_cols))
                    except IndexError:
                        num_cols = 1
                        slice_grp = (slice(init_g, end_g), total_cols)

                    if len(shape) == 1:
                        data[slice_grp[0]] = self.conn[group][init:end].compute()
                    else:
                        data[slice_grp] = self.conn[group][init:end].compute()
                    total_cols += num_cols
                init_g = 0
                end_g = batch_size
                #dataset.data[init:end] = data
                print(data, self.writer_conn, item)
                self.writer_conn[init:end] = data
                if end < self.shape.to_tuple()[0]:
                    init = end
                    end += batch_size
                else:
                    break
        else:
            if hasattr(value, "groups"):
                for group in value.groups:
                    group = self.conn.get_oldname(group)
                    self.writer_conn.conn[group][item] = value[group].to_ndarray()
            elif hasattr(value, 'batch'):
                for group in value.batch.dtype.names:
                    group = self.conn.get_oldname(group)
                    self.writer_conn.conn[group][item] = value.batch[group]
            elif isinstance(value, numbers.Number):
                group = self.conn.get_oldname(self.groups[0])
                self.writer_conn.conn[group][item] = value
            elif isinstance(value, np.ndarray):
                group = self.conn.get_oldname(self.groups[0])
                self.writer_conn.conn[group][item] = value
            else:
                if isinstance(item, str):
                    self.writer_conn.conn[item] = value

    def __add__(self, other: 'DaGroup') -> 'DaGroup':
        if other == 0:
            return self
        groups = DaGroupDict()
        groups.update(self.conn)
        groups.update(other.conn)
        return DaGroup(groups)

    def __radd__(self, other):
        return self.__add__(other)

    @property
    def shape(self) -> 'Shape':
        shape = {group: data.shape for group, data in self.conn.items()}
        return Shape(shape)

    def to_ndarray(self, dtype: np.dtype = None, chunksize=(258,)):
        if len(self.groups) == 1:
            return self.conn[self.groups[0]].compute()
        else:
            shape = self.shape.to_tuple()
            data = np.empty(shape, dtype=self.dtype)
            total_cols = 0
            for i, group in enumerate(self.groups):
                try:
                    num_cols = self.shape[group][1]
                    slice_grp = (slice(None, None), slice(total_cols, total_cols + num_cols))
                except IndexError:
                    num_cols = 1
                    slice_grp = (slice(None, None), total_cols)
                total_cols += num_cols
                data[slice_grp] = self.conn[group].compute()
            return data

    def to_df(self):
        from ml.data.it import Iterator
        import pandas as pd
        shape = self.shape
        if len(shape) > 1 and len(self.groups) < shape[1]:
            dtypes = np.dtype([("c{}".format(i), self.dtype) for i in range(shape[1])])
            columns = self.groups
        else:
            dtypes = self.dtypes
            columns = self.groups

        data = Iterator(self).batchs(batch_size=258)
        stc_arr = np.empty(shape.to_tuple()[0], dtype=dtypes)
        if len(self.groups) == 1:
            for slice_obj in data:
                stc_arr[slice_obj.slice] = slice_obj.batch.to_ndarray()
        else:
            for i, group in enumerate(self.groups):
                for slice_obj in data:
                    stc_arr[group][slice_obj.slice] = slice_obj.batch.to_ndarray()[:, i]
        return pd.DataFrame(stc_arr, index=np.arange(0, stc_arr.shape[0]), columns=columns)

    def rename_group(self, old_name, new_name):
        self.conn = self.conn.rename(old_name, new_name)

    def store(self, dataset: AbsData):
        self.writer_conn = dataset.data.writer_conn
        for group in self.groups:
            self.conn[group].store(dataset.data[group])


class StructuredGroup(AbsGroup):
    def __init__(self, conn, name=None):
        super(StructuredGroup, self).__init__(conn, name=name)

    def __getitem__(self, item):
        if isinstance(item, str):
            key = self.alias_map.get(item, item)
            group = StructuredGroup(self.conn[key])
            group.slice = self.slice
            return group
        else:
            group = StructuredGroup(self.conn)
            if isinstance(item, slice):
                group.slice = item
            elif isinstance(item, int):
                group.slice = slice(item, item + 1)
            else:
                group.slice = self.slice
            return group.to_ndarray()

    def __setitem__(self, item, value):
        if hasattr(value, "groups"):
            for group in value.groups:
                self.conn[group][item] = value[group]

    @property
    def dtypes(self) -> np.dtype:
        if isinstance(self.conn, np.ndarray):
            if self.conn.dtype.fields is None:
                return self.conn.dtype
            else:
                return np.dtype([(self.inv_map.get(group, group), dtype) for group, (dtype, _) in self.conn.dtype.fields.items()])
        elif isinstance(self.conn, np.void):
            return np.dtype(
                [(self.inv_map.get(group, group), dtype) for group, (dtype, _) in self.conn.dtype.fields.items()])

    @property
    def shape(self) -> Shape:
        if isinstance(self.conn, np.ndarray):
            if self.groups is None:
                shape = dict([("c0", self.conn.shape)])
            else:
                shape = dict([(group, self.conn[group].shape) for group in self.groups])
        else:
            shape = dict([(group, self.conn.shape) for group in self.groups])
        return Shape(shape)

    def to_ndarray(self, dtype: np.dtype = None, chunksize=(258,)) -> np.ndarray:
        return self.conn[self.slice]
