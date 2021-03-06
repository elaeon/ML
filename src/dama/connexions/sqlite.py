from dama.abc.conn import AbsConn
from dama.utils.core import Shape, Chunks
import numpy as np
from collections import OrderedDict
from dama.utils.decorators import cache
from dama.data.it import Iterator, BatchIterator
from dama.utils.miscellaneous import filter_dtypes, merge_dtype_list


class Table(AbsConn):

    def __init__(self, conn, dtypes, name=None, query_parts=None):
        super(Table, self).__init__(conn, dtypes=dtypes)
        self.name = name
        if query_parts is None:
            self.query_parts = {"columns": None, "slice": None}
        else:
            self.query_parts = query_parts

    def __getitem__(self, item):
        query_parts = self.query_parts.copy()
        if isinstance(item, str):
            query_parts["columns"] = [item]
            dtypes = filter_dtypes(item, self.dtypes)
            return Table(self.conn, dtypes, name=self.name, query_parts=query_parts)
        elif isinstance(item, list) or isinstance(item, tuple):
            it = Iterator(item)
            if it.type_elem == int:
                query_parts["slice"] = [slice(index, index + 1) for index in item]
                dtypes = self.dtypes
            elif it.type_elem == slice:
                query_parts["slice"] = item
                dtypes = self.dtypes
            elif it.type_elem == str:
                query_parts["columns"] = item
                dtypes = merge_dtype_list([filter_dtypes(elem, self.dtypes) for elem in item])
            else:
                dtypes = self.dtypes
            dtype = self.attrs.get("dtype", None)
            return Table(self.conn, dtypes, name=self.name, query_parts=query_parts).to_ndarray(dtype=dtype)
        elif isinstance(item, int):
            query_parts["slice"] = slice(item, item + 1)
            dtype = self.attrs.get("dtype", None)
            return Table(self.conn, self.dtypes, name=self.name, query_parts=query_parts).to_ndarray(dtype=dtype)
        elif isinstance(item, slice):
            query_parts["slice"] = item
            dtype = self.attrs.get("dtype", None)
            return Table(self.conn, self.dtypes, name=self.name, query_parts=query_parts).to_ndarray(dtype=dtype)

    def __setitem__(self, item, value):
        if hasattr(value, 'batch'):
            value = value.batch

        if isinstance(item, tuple):
            if len(item) == 1:
                stop = item[0].stop
                start = item[0].start
            else:
                raise NotImplementedError
            batch_size = abs(stop - start)
        elif isinstance(item, slice):
            stop = item.stop
            start = item.start
            batch_size = abs(stop - start)
        elif isinstance(item, int):
            stop = item + 1
            if hasattr(value, '__len__'):
                batch_size = len(value)
            else:
                batch_size = 1
        else:
            raise NotImplementedError

        last_id = self.last_id()
        if last_id < stop or item == -1:
            self.insert(value, chunks=(batch_size,))
        else:
            self.update(value, item)

    def insert(self, data, chunks=None):
        if not isinstance(data, BatchIterator):
            data = Iterator(data, dtypes=self.dtypes).batchs(chunks=chunks)

        columns = "(" + ", ".join(self.groups) + ")"
        values = "(" + "?,".join(("" for _ in self.groups)) + "?)"
        insert_str = "INSERT INTO {name} {columns} VALUES {values}".format(
            name=self.name, columns=columns, values=values)
        cur = self.conn.cursor()
        num_groups = len(data.groups)
        for row in data:
            shape = row.batch.shape.to_tuple()
            if len(shape) == 1 and num_groups > 1:
                value = row.batch.to_df().values
            elif len(shape) == 1 and num_groups == 1:
                value = row.batch.to_df().values
            else:
                value = row.batch.to_ndarray(object)
            cur.executemany(insert_str, value)
        self.conn.commit()
        cur.close()

    def update(self, values, item):
        if isinstance(item, int):
            columns = ["{col}=?".format(col=group) for group in self.groups]
            query = "UPDATE {name} SET {columns_val} WHERE ID = ?".format(name=self.name,
                                                                          columns_val=",".join(columns))
            cur = self.conn.cursor()
            values_list = list(values) + [item + 1]
            cur.execute(query, values_list)
            self.conn.commit()
            cur.close()
        else:
            raise NotImplementedError

    def to_ndarray(self, dtype: np.dtype = None) -> np.ndarray:
        if self.dtype is None:
            return np.asarray([])

        query, _ = self.build_query()
        cur = self.conn.cursor()
        cur.execute(query)
        array = np.empty(self.shape, dtype=self.dtype)
        if len(self.groups) == 1:
            for i, row in enumerate(cur):
                array[i] = row[0]
        else:
            array[:] = cur.fetchall()
        self.conn.commit()
        cur.close()
        if dtype is not None and self.dtype != dtype:
            return array.astype(dtype)
        else:
            return array

    def to_df(self):
        pass

    @property
    @cache
    def shape(self) -> Shape:
        cur = self.conn.cursor()
        slice_item, limit_txt = self.build_limit_info()
        if limit_txt == "":
            query = "SELECT COUNT(*) FROM {table_name}".format(table_name=self.name)
            cur.execute(query)
            length = cur.fetchone()[0]
        else:
            query = "SELECT Count(*) FROM (SELECT id FROM {table_name} LIMIT {limit} OFFSET {start})".format(
                table_name=self.name, start=slice_item.start, limit=(abs(slice_item.stop - slice_item.start)))
            cur.execute(query)
            length = cur.fetchone()[0]
        shape = OrderedDict([(group, (length,)) for group in self.groups])
        cur.close()
        return Shape(shape)

    def last_id(self) -> int:
        cur = self.conn.cursor()
        cur.execute("SELECT max(id) FROM {}".format(self.name))
        id_ = cur.fetchone()[0]
        cur.close()
        return id_ if id_ is not None else 0

    def first_id(self):
        cur = self.conn.cursor()
        cur.execute("SELECT min(id) FROM {}".format(self.name))
        id_ = cur.fetchone()[0]
        cur.close()
        return id_

    def format_columns(self):
        columns = self.query_parts["columns"]
        if columns is None:
            columns = self.groups
        return ",".join(columns)

    def build_limit_info(self) -> tuple:
        if isinstance(self.query_parts["slice"], list):
            index_start = [index.start for index in self.query_parts["slice"]]
            index_stop = [index.stop for index in self.query_parts["slice"]]
            min_elem = min(index_start)
            max_elem = max(index_stop)
            return slice(min_elem, max_elem), "LIMIT {}".format(max_elem)
        elif isinstance(self.query_parts["slice"], tuple):
            item = self.query_parts["slice"][0]
        else:
            item = self.query_parts["slice"]
        if item is None:
            start = 0
            stop = None
            limit_txt = ""
        else:
            if item.start is None:
                start = 0
            else:
                start = item.start

            if item.stop is None:
                limit_txt = ""
                stop = None
            else:
                limit_txt = "LIMIT {}".format(item.stop)
                stop = item.stop

        return slice(start, stop), limit_txt

    def build_query(self) -> tuple:
        if isinstance(self.query_parts["slice"], list):
            id_list = [index.start + 1 for index in self.query_parts["slice"]]
            query = "SELECT {columns} FROM {table_name} WHERE ID IN ({id_list}) ORDER BY {order_by}".format(
                columns=self.format_columns(), table_name=self.name, order_by="id",
                id_list=",".join(map(str, id_list)))
            one_row = True
        else:
            slice_item, limit_txt = self.build_limit_info()
            if limit_txt == "":
                query = "SELECT {columns} FROM {table_name} ORDER BY {order_by}".format(
                    columns=self.format_columns(), table_name=self.name, order_by="id")
            else:
                query = "SELECT {columns} FROM {table_name} ORDER BY {order_by} LIMIT {limit} OFFSET {start}".format(
                    columns=self.format_columns(), table_name=self.name, order_by="id", start=slice_item.start,
                    limit=(abs(slice_item.stop - slice_item.start)))
            one_row = False
        return query, one_row

    def store(self, driver: 'AbsDriver'):
        pass

    def chunksize(self) -> Chunks:
        pass
