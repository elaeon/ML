import datetime
import json
import numpy as np
import pandas as pd
import dask.array as da
import dask.bag as db
import dask
from tabulate import tabulate
from dama.abc.data import AbsData
from dama.abc.conn import AbsConn
from dama.data.it import Iterator, BaseIterator, BatchIterator
from dama.utils.core import Hash, Login, Metadata, Chunks, Shape
from dama.abc.driver import AbsDriver
from dama.drivers.core import Memory
from dama.drivers.sqlite import Sqlite
from dama.utils.logger import log_config
from dama.utils.config import get_settings
from dama.utils.decorators import cache, clean_cache
from dama.utils.files import get_dir_file_size
from dama.utils.order import order_table
from dama.connexions.core import GroupManager
from pydoc import locate


settings = get_settings("paths")
log = log_config(__name__)


class Data(AbsData):
    def __init__(self, name: str = None, driver: AbsDriver = None, group_name: str = None,
                 chunks=None, auto_chunks=False, metadata_path: str = None):

        if driver is None:
            self.driver = Memory()
        else:
            self.driver = driver

        if name is None and not isinstance(self.driver, Memory):
            raise Exception("I can't build a dataset without a name, plese add a name to this dataset.")

        if self.driver.persistent is True:
            if metadata_path is not None:
                self.metadata_path = metadata_path
            else:
                self.metadata_path = settings["metadata_path"]
            self.metadata_driver = Sqlite(login=Login(table="data"), path=self.metadata_path)
        else:
            self.metadata_path = None
            self.metadata_driver = None

        self.name = name
        self.header_map = ["author", "description"]
        self.group_name = group_name
        self.dtypes = None
        self.hash = None
        self.author = None
        self.description = None
        self.timestamp = None
        self.compressor_params = None
        self.chunksize = chunks
        self.from_ds_hash = None
        self.auto_chunks = auto_chunks
        if self.driver.path is None:
            self.driver.path = settings["data_path"]
        self.driver.build_url(self.name, group_level=self.group_name)

    @property
    def author(self):
        return self._get_attr('author')

    @author.setter
    def author(self, value):
        if value is not None:
            self._set_attr('author', value)

    @property
    def dtype(self):
        return self.data.dtype

    @property
    def description(self):
        return self._get_attr('description')

    @description.setter
    def description(self, value):
        if value is not None:
            self._set_attr('description', value)

    @property
    def timestamp(self):
        return self._get_attr('timestamp')

    @timestamp.setter
    def timestamp(self, value):
        if value is not None:
            self._set_attr('timestamp', value)

    @property
    def hash(self):
        return self._get_attr('hash')

    @hash.setter
    def hash(self, value):
        if value is not None:
            self._set_attr('hash', value)

    @property
    def compressor_params(self):
        return json.loads(self._get_attr('compressor_params'))

    @compressor_params.setter
    def compressor_params(self, value):
        if value is not None:
            self._set_attr('compressor_params', json.dumps(value))

    @classmethod
    def module_cls_name(cls):
        return "{}.{}".format(cls.__module__, cls.__name__)

    @property
    @cache
    def data(self) -> AbsConn:
        return self.driver.manager(chunks=self.chunksize)

    @data.setter
    @clean_cache
    def data(self, v):
        pass

    def clean_data_cache(self):
        self.data = None

    @property
    def from_ds_hash(self):
        return self._get_attr('from_ds_hash')

    @from_ds_hash.setter
    def from_ds_hash(self, value):
        if value is not None:
            self._set_attr('from_ds_hash', value)

    def open(self):
        self.driver.open()

        if self.driver.mode in ["w", "a", "r+"]:
            if len(self.driver.compressor_params) > 0:
                self.compressor_params = self.driver.compressor_params

        if self.auto_chunks is True and self.driver.mode in ["a", "r"]:
            try:
                self.chunksize = Chunks.build_from_shape(self.driver.shape, self.driver.dtypes)
            except KeyError as e:
                log.error(e)
        else:
            if isinstance(self.chunksize, tuple) and self.driver.mode in ["a", "r"]:
                groups = self.driver.groups
                if groups is not None:
                    self.chunksize = Chunks.build_from(self.chunksize, groups)
            elif self.driver.mode == "w" or self.chunksize is None:
                pass
            elif isinstance(self.chunksize, Chunks) and self.driver.mode in ["a", "r"]:
                pass
            else:
                raise Exception("chunks value {} not allowed".format(self.chunksize))

    def close(self):
        self.driver.close()
        self.data = None

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        raise NotImplementedError

    def __iter__(self):
        return self

    def __next__(self):
        return next(self.data)

    def _set_attr(self, name, value):
        if value is not None:
            log.debug("SET attribute {name} {value}".format(name=name, value=value))
            self.driver.attrs[name] = value

    def _get_attr(self, name):
        try:
            return self.driver.attrs[name]
        except KeyError:
            log.debug("Not found attribute {} in file {}".format(name, self.url))
            return None
        except IOError as e:
            log.debug(e)
            log.debug("Error opening {} in file {}".format(name, self.url))
            return None

    def destroy(self):
        hash_hex = self.hash
        self.driver.destroy()
        if self.driver.persistent is True:
            with Metadata(self.metadata_driver) as metadata:
                metadata.invalid(hash_hex)

    @property
    def url(self) -> str:
        return self.driver.url

    @property
    def metadata_url(self) -> str:
        return self.metadata_driver.url

    def __len__(self):
        return len(self.groups)

    def __repr__(self):
        return repr(self.data)

    @property
    def size(self):
        return self.shape[0]

    @property
    def shape(self) -> Shape:
        return self.data.shape

    @property
    def groups(self) -> tuple:
        if self.data is not None:
            return self.data.groups

    @property
    def dtypes(self) -> np.dtype:
        return self.data.dtypes

    @dtypes.setter
    def dtypes(self, value):
        if value is not None:
            self.driver.set_schema(value)

    def info(self):
        print('       ')
        print('Name: {}'.format(self.name))
        print('Author: {}'.format(self.author))
        print('Description: {}'.format(self.description))
        print('URL path: {}'.format(self.driver.url))
        print('Hash: {}'.format(self.hash))
        print('       ')
        headers = ["group", "shape", "dtype"]
        table = []
        shape = self.shape
        for group, (dtype, _) in self.dtypes.fields.items():
            table.append([group, shape[group], dtype])
        print(order_table(headers, table, "Group"))

    def metadata(self) -> dict:
        meta_dict = dict()
        meta_dict["hash"] = self.hash
        meta_dict["path"] = self.driver.path
        meta_dict["metadata_path"] = self.metadata_path
        meta_dict["group_name"] = self.group_name
        meta_dict["driver_module"] = self.driver.module_cls_name()
        meta_dict["driver_name"] = self.driver.cls_name()
        meta_dict["name"] = self.name
        meta_dict["size"] = get_dir_file_size(self.url)
        meta_dict["timestamp"] = self.timestamp
        meta_dict["author"] = self.author
        meta_dict["num_groups"] = len(self.groups)
        meta_dict["description"] = self.description if self.description is None else ""
        meta_dict["from_ds_hash"] = self.from_ds_hash
        return meta_dict

    def metadata_to_json(self, f):
        metadata = self.metadata()
        json.dump(metadata, f)

    def write_metadata(self):
        if self.driver.persistent is True:
            with Metadata(self.metadata_driver, self.metadata()) as metadata:
                dtypes = np.dtype([("hash", object), ("name", object), ("author", object),
                                   ("description", object), ("size", int), ("driver_module", object),
                                   ("path", object), ("driver_name", object), ("group_name", object),
                                   ("timestamp", np.dtype("datetime64[ns]")), ("num_groups", int),
                                   ("is_valid", bool), ("from_ds_hash", object)])
                timestamp = metadata["timestamp"]
                metadata["timestamp"] = datetime.datetime.strptime(timestamp, '%Y-%m-%dT%H:%M UTC')
                metadata["group_name"] = "s/n" if self.group_name is None else self.group_name
                metadata["is_valid"] = True
                metadata.set_schema(dtypes, unique_key=["hash", ["path", "name", "driver_name", "group_name"]])
                metadata.insert_update_data(keys=["hash", ["path", "name", "driver_name", "group_name"]])

    def calc_hash(self, with_hash: str) -> str:
        hash_obj = Hash(hash_fn=with_hash)
        header = [getattr(self, attr) for attr in self.header_map]
        header = [attr for attr in header if attr is not None]
        hash_obj.hash.update("".join(header).encode("utf-8"))
        for group in self.groups:
            it = Iterator(self.data[group]).batchs(chunks=self.chunksize)
            hash_obj.update(it.only_data())
        return str(hash_obj)

    def from_data(self, data, with_hash: str = "sha1", from_ds_hash: str = None, start_i: int = 0):
        if isinstance(data, da.Array):
            data = GroupManager.from_da(data)
            if self.chunksize is None:
                self.chunksize = data.chunksize
            elif isinstance(self.chunksize, tuple):
                self.chunksize = Chunks.build_from(self.chunksize, data.groups)
        elif isinstance(data, Iterator):
            if self.chunksize is None:
                self.chunksize = Chunks.build_from_shape(data.shape, data.dtypes)
            elif isinstance(self.chunksize, tuple):
                self.chunksize = Chunks.build_from(self.chunksize, data.groups)
            data = data.batchs(chunks=self.chunksize, start_i=start_i)
            self.chunksize = data.chunksize
        elif isinstance(data, BatchIterator):
            if self.chunksize is None:
                self.chunksize = data.chunksize
            elif isinstance(self.chunksize, tuple):
                self.chunksize = Chunks.build_from(self.chunksize, data.groups)
        elif isinstance(data, dict) and not isinstance(data, AbsConn):
            if self.chunksize is None:
                shape, dtypes = Shape.get_shape_dtypes_from_dict(data)
                self.chunksize = Chunks.build_from_shape(shape, dtypes)
            elif isinstance(self.chunksize, tuple):
                self.chunksize = Chunks.build_from(self.chunksize, tuple(data.keys()))
            data = GroupManager.convert(data, chunks=self.chunksize)
        elif isinstance(data, AbsConn):
            if self.chunksize is None:
                self.chunksize = data.chunksize
            elif isinstance(self.chunksize, tuple):
                self.chunksize = Chunks.build_from(self.chunksize, data.groups)
        elif not isinstance(data, BaseIterator):
            data = Iterator(data)
            if self.chunksize is None:
                self.chunksize = Chunks.build_from_shape(data.shape, data.dtypes)
            elif isinstance(self.chunksize, tuple):
                self.chunksize = Chunks.build_from(self.chunksize, data.groups)
            data = data.batchs(chunks=self.chunksize, start_i=start_i)
            self.chunksize = data.chunksize
        self.dtypes = data.dtypes
        self.driver.set_data_shape(data.shape)
        if isinstance(data, BatchIterator) or isinstance(data, Iterator):
            self.driver.batchs_writer(data)
        elif isinstance(data, AbsConn):
            self.driver.store(data)
        else:
            raise NotImplementedError

        if with_hash is not None:
            c_hash = self.calc_hash(with_hash=with_hash)
        else:
            c_hash = None

        self.from_ds_hash = from_ds_hash
        self.hash = c_hash
        self.timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M UTC")
        self.write_metadata()

    def from_loader(self, data_list: list, loader_fn, npartitions: int = 1, with_hash: str = "sha1"):
        def concat_partitions(part1: list, part2: list):
            if not isinstance(part1, list):
                part1 = [part1]
            if not isinstance(part2, list):
                part2 = [part2]
            return GroupManager.concat(part1 + part2, axis=0)

        url_bag_partition = db.from_sequence(data_list, npartitions=npartitions)
        fold_loader = url_bag_partition.map(loader_fn).fold(binop=self.add_to_list, combine=concat_partitions,
                                                            initial=[])
        da_group = fold_loader.compute()
        self.from_data(da_group, with_hash=with_hash)

    @staticmethod
    def add_to_list(base_list, data) -> list:
        it = Iterator(data)
        groups = it.groups
        if len(groups) == 1:
            group_items = [(groups[0], data)]
        else:
            group_items = [(group, data[group]) for group in groups]
        dagroup_dict = GroupManager.convert(group_items, Chunks.build_from_shape(it.shape, it.dtypes))
        return base_list + [dagroup_dict]

    def to_df(self) -> pd.DataFrame:
        return self.data.to_df()

    def to_ndarray(self, dtype=None) -> np.ndarray:
        return self.data.to_ndarray(dtype=dtype)

    def concat(self, datasets: tuple, axis=0):
        da_groups = []
        managers = set([])
        for ds in datasets:
            da_groups.append(ds.data)
            managers.add(type(ds.data))
        if len(managers) == 1:
            manager = managers.pop()
            da_group = manager.concat(da_groups, axis=axis)
            self.from_data(da_group)
        else:
            raise NotImplementedError

    def stadistics(self):
        headers = ["group", "mean", "std dev", "min", "25%", "50%", "75%", "max", "nonzero", "nonan", "unique", "dtype"]
        self.chunksize = Chunks.build_from_shape(self.shape, self.dtypes)
        table = []
        for group, (dtype, _) in self.dtypes.fields.items():
            values = dict()
            values["dtype"] = dtype
            values["group"] = group
            darray = self.data[group].da
            if dtype == np.dtype(float) or dtype == np.dtype(int):
                da_mean = da.around(darray.mean(), decimals=3)
                da_std = da.around(darray.std(), decimals=3)
                da_min = da.around(darray.min(), decimals=3)
                da_max = da.around(darray.max(), decimals=3)
                result = dask.compute([da_mean, da_std, da_min, da_max])[0]
                values["mean"] = result[0] if not np.isnan(result[0]) else da.around(da.nanmean(darray), decimals=3).compute()
                values["std dev"] = result[1] if not np.isnan(result[0]) else da.around(da.nanstd(darray), decimals=3).compute()
                values["min"] = result[2] if not np.isnan(result[0]) else da.around(da.nanmin(darray), decimals=3).compute()
                values["max"] = result[3] if not np.isnan(result[0]) else da.around(da.nanmax(darray), decimals=3).compute()
                if len(self.shape[group]) == 1:
                    da_percentile = da.around(da.percentile(darray, [25, 50, 75]), decimals=3)
                    result = da_percentile.compute()
                    values["25%"] = result[0]
                    values["50%"] = result[1]
                    values["75%"] = result[2]
                else:
                    values["25%"] = "-"
                    values["50%"] = "-"
                    values["75%"] = "-"
                values["nonzero"] = da.count_nonzero(darray).compute()
                values["nonan"] = da.count_nonzero(da.notnull(darray)).compute()
                values["unique"] = "-"
            else:
                values["mean"] = "-"
                values["std dev"] = "-"
                values["min"] = "-"
                values["max"] = "-"
                values["25%"] = "-"
                values["50%"] = "-"
                values["75%"] = "-"
                values["nonzero"] = "-"
                values["nonan"] = da.count_nonzero(da.notnull(darray)).compute()
                vunique = darray.to_dask_dataframe().fillna('').nunique().compute()
                values["unique"] = vunique

            row = []
            for column in headers:
                row.append(values[column])
            table.append(row)

        print("# rows {}".format(self.shape[0]))
        return tabulate(table, headers)

    @staticmethod
    def load(hash_hex: str, metadata_driver: AbsDriver, metadata_path: str = None, auto_chunks: bool = True) -> 'Data':
        with Metadata(metadata_driver) as metadata:
            query = "SELECT name, driver_module, path, group_name, hash FROM {} WHERE hash = ?".format(
                metadata_driver.login.table)
            data = metadata.query(query, (hash_hex,))
            if len(data) == 0:
                log.warning(
                    "Resource {} does not exists in table '{}' in url {}".format(hash_hex,
                                                                                 metadata_driver.login.table,
                                                                                 metadata_driver.url))
            else:
                row = data[0]
                data_driver = locate(row[1])
                path = row[2]
                group_name = None if row[3] == "s/n" else row[3]
                name = row[0]
                return Data(name=name, group_name=group_name, driver=data_driver(path=path, mode="r"),
                            metadata_path=metadata_path, auto_chunks=auto_chunks)
