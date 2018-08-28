"""
Module for create datasets from distinct sources of data.
"""
from skimage import io

import os
import numpy as np
import pandas as pd
import dill as pickle
import random
import h5py
import logging
import datetime
import uuid

from ml.processing import Transforms
from ml.utils.config import get_settings
from ml.data.it import Iterator 
from ml.random import downsample
from ml import fmtypes as Fmtypes
from ml.random import sampling_size
from ml.data.abc import AbsDataset
from ml.utils.decorators import clean_cache, cache

settings = get_settings("ml")

log = logging.getLogger(__name__)
logFormatter = logging.Formatter("[%(name)s] - [%(levelname)s] %(message)s")
handler = logging.StreamHandler()
handler.setFormatter(logFormatter)
log.addHandler(handler)
log.setLevel(int(settings["loglevel"]))


def save_metadata(file_path, data):
    with open(file_path, 'wb') as f:
        pickle.dump(data, f, pickle.HIGHEST_PROTOCOL)


def load_metadata(path):
    try:
        with open(path, 'rb') as f:
            data = pickle.load(f)
        return data
    except IOError as e:
        log.info(e)
        return {}
    except Exception as e:
        log.error("{} {}".format(e, path))


def calc_nshape(data, value):
    if value is None or not (0 < value <= 1) or data is None:
        value = 1
    return int(round(data.shape[0] * value, 0))
    

class Memory:
    def __init__(self):
        self.spaces = {}
        self.attrs = {}

    def __contains__(self, item):
        return item in self.spaces

    def __getitem__(self, key):
        levels = [e for e in key.split("/") if e != ""]
        v =  self._get_level(self.spaces, levels)
        return v

    def __setitem__(self, key, value):
        levels = [e for e in key.split("/") if e != ""]
        v = self._get_level(self.spaces, levels[:-1])
        if v is None:
            self.spaces[levels[-1]] = value
        else:
            v[levels[-1]] = value

    def require_group(self, name):
        if name not in self:
            self[name] = Memory()

    def require_dataset(self, name, shape, dtype='float', **kwargs):
        if name not in self:
            self[name] = np.empty(shape, dtype=dtype)

    def get(self, name, value):
        try:
            return self[name]
        except KeyError:
            return value

    def _get_level(self, spaces, levels):
        if len(levels) == 1:
            return spaces[levels[0]]
        elif len(levels) == 0:
            return None
        else:
            return self._get_level(spaces[levels[0]], levels[1:])

    def close(self):
        pass


class HDF5Dataset(AbsDataset):

    def __enter__(self):
        if self.driver == "core":
            if self.f is None:
                self.f = Memory()
        else:
            if not self.f:
                self.f = h5py.File(self.url(), mode=self.mode)
        return self

    def __exit__(self, type, value, traceback):
        self.f.close()

    def __iter__(self):
        return iter(self.data)

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value

    def __next__(self):
        return next(self.__iter__())

    def auto_dtype(self, ttype):
        if ttype == np.dtype("O") or ttype.kind == "U":
            return h5py.special_dtype(vlen=str)
        else:
            return ttype

    def _set_space_shape(self, name, shape, dtype):
        with self:
            self.f.require_group("data")
            dtype = self.auto_dtype(dtype)
            self.f['data'].require_dataset(name, shape, dtype=dtype, chunks=True, 
                exact=True, **self.zip_params)

    def _get_data(self, name):
        key = '/data/' + name
        return self.f[key]

    def _set_space_fmtypes(self, num_features):
        with self:
            self.f.require_group("fmtypes")
            self.f['fmtypes'].require_dataset("names", (num_features,), dtype=h5py.special_dtype(vlen=str), 
                exact=True, chunks=True, **self.zip_params)
            self.f['fmtypes'].require_dataset("types", (num_features,), dtype=np.dtype("|S8"), 
                exact=True, chunks=True, **self.zip_params)
            self.columns = list(map(lambda x: "c"+str(x), range(num_features)))

    def _set_attr(self, name, value):
        with self:
            self.f.attrs[name] = value
            
    def _get_attr(self, name):
        try:
            with self:
                return self.f.attrs[name]
        except KeyError:
            log.debug("Not found attribute {} in file {}".format(name, self.url()))
            return None
        except IOError as e:
            log.debug("Error opening {} in file {}".format(name, self.url()))
            return None

    def chunks_writer(self, name, data, init=0):
        from tqdm import tqdm
        log.info("Writing with chunks size {}".format(data.chunks_size))
        end = init
        with self:
            for smx in tqdm(data, total=data.num_splits()):
                if hasattr(smx, 'shape') and len(smx.shape) >= 1 and data.has_chunks:
                    end += smx.shape[0]
                else:
                    end += 1

                if isinstance(smx, pd.DataFrame):
                    array = smx.values
                elif not hasattr(smx, '__iter__'):
                    array = (smx,)
                else:
                    array = smx

                try:
                    self.f[name][init:end] = array
                    init = end
                except TypeError as e:
                    if type(array) == np.ndarray:
                        array_type = array.dtype
                        if array.dtype != self.f[name].dtype:                        
                            must_type = self.f[name].dtype
                        else:
                            raise TypeError(e)
                    else:
                        array_type = type(array[0])
                        must_type = self.f[name].dtype
                    raise TypeError("All elements in array must be of type '{}' but found '{}'".format(
                        must_type, array_type))
            return end

    def chunks_writer_split(self, data_key, labels_key, data, labels_column, init=0):
        from tqdm import tqdm
        log.info("Writing with chunks size {}".format(data.chunks_size))
        end = init
        with self:
            for smx in tqdm(data, total=data.num_splits()):
                if hasattr(smx, 'shape') and len(smx.shape) >= 1 and data.has_chunks:
                    end += smx.shape[0]
                else:
                    end += 1

                if isinstance(smx, pd.DataFrame):
                    array_data = smx.drop([labels_column], axis=1).values
                    array_labels = smx[labels_column].values
                else:
                    labels_column = int(labels_column)
                    array_data = np.delete(smx, labels_column, axis=1)
                    array_labels = smx[:, labels_column]

                self.f[data_key][init:end] = array_data
                self.f[labels_key][init:end] = array_labels
                init = end

        if hasattr(data.dtype, "__iter__"):
            ndtype = []
            for col_name, type_e in data.dtype:
                if col_name == labels_column:
                    pass
                else:
                    ndtype.append((col_name, type_e))
            data.dtype = ndtype

        return end

    def destroy(self):
        """
        delete the correspondly hdf5 file
        """
        from ml.utils.files import rm
        rm(self.url())
        log.debug("DESTROY {}".format(self.url()))

    def url(self):
        """
        return the path where is saved the dataset
        """
        return os.path.join(self.dataset_path, self.name)

    def exists(self):
        return os.path.exists(self.url())

    def reader(self, chunksize:int=0, df=True) -> Iterator:
        if df is True:
            dtypes = self.dtype
            dtype = [(col, dtypes) for col in self.columns]
        else:
            dtype = self.dtype
        if chunksize == 0:
            it = Iterator(self, dtype=dtype)
            return it
        else:
            it = Iterator(self, dtype=dtype).to_chunks(chunksize)
            return it

    @property
    def shape(self):
        "return the shape of the dataset"
        return self.data.shape

    @property
    def columns(self):
        return self.f.get("fmtypes/names", None)

    @columns.setter
    def columns(self, value):
        with self:
            data = self.f.get("fmtypes/names", None)
            data[:] = value

    def num_features(self):
        """
        return the number of features of the dataset
        """
        if len(self.shape) > 1:
            return self.shape[-1]
        else:
            return 1


class Data(HDF5Dataset):
    """
    Base class for dataset build. Get data from memory.
    create the initial values for the dataset.

    :type name: string
    :param name: dataset's name

    :type dataset_path: string
    :param dataset_path: path where the datased is saved. This param is automaticly set by the settings.cfg file.

    :type transforms: transform instance
    :param transforms: list of transforms

    :type apply_transforms: bool
    :param apply_transforms: apply transformations to the data

    :type dtype: string
    :param dtype: the type of the data to save

    :type description: string
    :param description: an bref description of the dataset

    :type author: string
    :param author: Dataset Author's name

    :type compression_level: int
    :param compression_level: number in 0-9 range. If 0 is passed no compression is executed

    :type rewrite: bool
    :param rewrite: if true, you can clean the saved data and add a new dataset.
    """
    def __init__(self, name=None, dataset_path=None, description='', author='', 
                compression_level=0, clean=False, mode='a', driver='default'):

        if name is None:
            raise Exception("I can't build a dataset without a name, plese add a name to this dataset.")

        self.name = uuid.uuid4().hex if name is None else name
        self.header_map = ["author", "description", "timestamp", "transforms_str"]
        self.f = None
        self.driver = driver
        self.mode = mode

        if dataset_path is None:
            self.dataset_path = settings["dataset_path"]
        else:
            self.dataset_path = dataset_path

        ds_exist = self.exists()
        if ds_exist and clean:
            self.destroy()
            ds_exist = False

        if not ds_exist and (self.mode == 'w' or self.mode == 'a'):
            self.create_route()
            self.author = author
            self.transforms = Transforms()
            self.description = description
            self.compression_level = compression_level
            self.timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M UTC")
            self.dataset_class = self.module_cls_name()
            self.hash_header = self.calc_hash_H()

        self.zip_params = {"compression": "gzip", "compression_opts": self.compression_level}

    @property
    def author(self):
        return self._get_attr('author')

    @author.setter
    def author(self, value):
        self._set_attr('author', value)

    @property
    def dtype(self):
        return self.data.dtype

    @property
    @cache
    def transforms(self):
        return Transforms.from_json(self._get_attr('transforms'), add_to=self._set_attr)

    @transforms.setter
    @clean_cache
    def transforms(self, value):
        if isinstance(value, Transforms):
            self._set_attr('transforms', value.to_json())

    @property
    def transforms_str(self):
        return self._get_attr('transforms')

    @property
    def description(self):
        return self._get_attr('description')

    @description.setter
    def description(self, value):
        self._set_attr('description', value)

    @property
    def timestamp(self):
        return self._get_attr('timestamp')

    @timestamp.setter
    def timestamp(self, value):
        self._set_attr('timestamp', value)

    @property
    def compression_level(self):
        return self._get_attr('compression_level')

    @compression_level.setter
    def compression_level(self, value):
        self._set_attr('compression_level', value)

    @property
    def dataset_class(self):
        return self._get_attr('dataset_class')

    @dataset_class.setter
    def dataset_class(self, value):
        self._set_attr('dataset_class', value)

    @property
    def hash_header(self):
        return self._get_attr('hash_H')

    @hash_header.setter
    def hash_header(self, value):
        self._set_attr('hash_H', value)

    @property
    def md5(self):
        return self._get_attr('md5')

    @md5.setter
    def md5(self, value):
        self._set_attr('md5', value)

    @classmethod
    def module_cls_name(cls):
        return "{}.{}".format(cls.__module__, cls.__name__)

    @property
    def data(self):
        """
        eturn the data in the dataset
        """
        return self._get_data('data')

    def info(self, classes=False):
        """
        :type classes: bool
        :param classes: if true, print the detail of the labels

        This function print the details of the dataset.
        """
        from ml.utils.order import order_table
        print('       ')
        print('Dataset NAME: {}'.format(self.name))
        print('Author: {}'.format(self.author))
        print('Transforms: {}'.format(self.transforms.to_json()))
        print('Header Hash: {}'.format(self.hash_header))
        print('Body Hash: {}'.format(self.md5))
        print('Description: {}'.format(self.description))
        print('       ')
        headers = ["Dataset", "Shape", "dType"]
        table = []
        with self:
            table.append(["dataset", self.shape, self.dtype])
        print(order_table(headers, table, "shape"))

    def calc_md5(self):
        """
        calculate the md5 from the data.
        """
        import hashlib
        h = hashlib.md5(self.data[:])
        return h.hexdigest()

    def calc_hash_H(self):
        """
        hash digest for the header.
        """
        import hashlib
        header = [getattr(self, attr) for attr in self.header_map]
        h = hashlib.md5("".join(header).encode("utf-8"))
        return h.hexdigest()

    def from_data(self, data, length=None, chunks_size=258, transform=True):
        """
        build a datalabel dataset from data and labels
        """
        if length is None and data.shape[0] is not None:
            length = data.shape[0]
        data = self.processing(data, apply_transforms=transform,
                            chunks_size=chunks_size)
        data = data.it_length(length)
        self._set_space_shape('data', data.shape, dtype=data.global_dtype)
        end = self.chunks_writer("/data/data", data)
        #self.md5 = self.calc_md5()
        columns = data.columns
        self._set_space_fmtypes(len(columns))
        if columns is not None:
            self.columns = columns

    def empty(self, name, dataset_path=None):
        """
        build an empty Data with the default parameters
        """
        data = Data(name=name, 
            dataset_path=dataset_path,
            description=self.description,
            author=self.author,
            compression_level=self.compression_level,
            clean=True)
        return data

    def convert(self, name, chunks_size=258, percentaje=1, dataset_path=None, 
        transforms=None):
        """
        :type dtype: string
        :param dtype: cast the data to the defined type

        dataset_path is not necesary to especify, this info is obtained from settings.cfg
        """
        data = self.empty(name, dataset_path=dataset_path)
        with self:
            data.from_data(self, calc_nshape(self, percentaje), 
            chunks_size=chunks_size)
        if transforms is not None:
            data.transforms = self.transforms + transforms
        else:
            data.transforms = self.transforms
        return data

    def processing(self, data, apply_transforms=True, chunks_size=258):
        """
        :type data: array
        :param data: data to transform

        :type initial: bool
        :param initial: if multirow transforms are added, then this parameter
        indicates the initial data fit

        execute the transformations to the data.

        """
        if apply_transforms and not self.transforms.is_empty():
            return self.transforms.apply(data, chunks_size=chunks_size)
        else:
            if not isinstance(data, Iterator):
                return Iterator(data).to_chunks(chunks_size)
            return data

    def to_df(self):
        """
        convert the dataset to a dataframe
        """
        dataset = self[:]
        if len(dataset.shape) > 2:
            dataset = dataset.reshape(dataset.shape[0], -1)
        columns_name = map(lambda x: "c"+str(x), range(dataset.shape[-1]))
        return pd.DataFrame(data=dataset, columns=columns_name)

    @staticmethod
    def concat(datasets, chunksize:int=0, name:str=None):
        ds0 = datasets.pop(0)
        i = 0
        to_destroy = []
        while len(datasets) > 0:
            ds1 = datasets.pop(0)
            if len(datasets) == 0:
                name_ds = name
            else:
                name_ds = "test_"+str(i)
            data = Data(name=name_ds, dataset_path="/tmp", clean=True)
            with ds0, ds1, data:
                it = ds0.reader(chunksize=chunksize).concat(ds1.reader(chunksize=chunksize))
                data.from_data(it)
            i += 1
            ds0 = data
            to_destroy.append(data)
        for ds in to_destroy[:-1]:
            ds.destroy()
        return ds0

    def create_route(self):
        """
        create directories if the dataset_path does not exist
        """
        if os.path.exists(self.dataset_path) is False:
            os.makedirs(self.dataset_path)

    @staticmethod
    def url_to_name(url):
        dataset_url = url.split("/")
        name = dataset_url[-1]
        path = "/".join(dataset_url[:-1])
        return name, path

    @staticmethod
    def original_ds(name, dataset_path=None):
        from pydoc import locate
        meta_dataset = Data(name=name, dataset_path=dataset_path, clean=False)
        DS = locate(str(meta_dataset.dataset_class))
        if DS is None:
            return
        return DS(name=name, dataset_path=dataset_path, clean=False)


class DataLabel(Data):
    """
    Base class for dataset build. Get data from memory.
    create the initial values for the dataset.

    :type name: string
    :param name: dataset's name

    :type dataset_path: string
    :param dataset_path: path where the datased is saved. This param is automaticly set by the settings.cfg file.

    :type transforms: transform instance
    :param transforms: list of transforms

    :type apply_transforms: bool
    :param apply_transforms: apply transformations to the data

    :type dtype: string
    :param dtype: the type of the data to save

    :type ltype: string
    :param ltype: the type of the labels to save

    :type description: string
    :param description: an bref description of the dataset

    :type author: string
    :param author: Dataset Author's name

    :type compression_level: int
    :param compression_level: number in 0-9 range. If 0 is passed no compression is executed

    :type rewrite: bool
    :param rewrite: if true, you can clean the saved data and add a new dataset.
    """
    @property
    def ltype(self):
        return self.labels.dtype

    @property
    def labels(self):
        """
        return the labels in the dataset
        """
        return self._get_data('labels')

    def labels_info(self):
        """
        return a counter of labels
        """
        return dict(zip(*np.unique(self.labels, return_counts=True)))

    def only_labels(self, labels):
        """
        :type labels: list
        :param labels: list of labels

        return a tuple of arrays with data and only the selected labels.
        """
        try:
            dataset, n_labels = self.only_labels_from_data(self, labels)
        except ValueError:
            label = labels[0] if len(labels) > 0 else None
            log.warning("label {} is not found in the labels set".format(label))
            return np.asarray([]), np.asarray([])
        return np.asarray(dataset), np.asarray(n_labels)

    def is_binary(self):
        return len(self.labels_info().keys()) == 2

    @classmethod
    def only_labels_from_data(self, ds, labels):
        """
        :type ds: dataset
        :param ds: dataset to select the data

        :type labels: list
        :type labels: list of labels to filter data

        return a tuple (data, labels) with the data filtered.
        """
        s_labels = set(labels)
        return zip(*filter(lambda x: x[1] in s_labels, zip(ds.data, ds.labels)))

    def info(self, classes=False):
        """
        :type classes: bool
        :param classes: if true, print the detail of the labels

        This function print the details of the dataset.
        """
        from ml.utils.order import order_table
        print('       ')
        print('DATASET NAME: {}'.format(self.name))
        print('Author: {}'.format(self.author))
        print('Transforms: {}'.format(self.transforms.to_json()))
        print('Header Hash: {}'.format(self.hash_header))
        print('Body Hash: {}'.format(self.md5))
        print('Description: {}'.format(self.description))
        print('       ')
        headers = ["Dataset", "Shape", "dType", "Labels", "ltype"]
        table = []
        with self:
            table.append(["dataset", self.shape, self.dtype, self.labels.size, self.ltype])
        print(order_table(headers, table, "shape"))
        if classes == True:
            headers = ["class", "# items", "%"]
            items = [(cls, total, (total/float(self.shape[0]))*100) 
                    for cls, total in self.labels_info().items()]
            items_p = [0, 0]
            print(order_table(headers, items, "# items"))

    def from_data(self, data, labels, length=None, chunks_size=258, transform=True):
        if length is None and data.shape[0] is not None:
            length = data.shape[0]
        data = self.processing(data, apply_transforms=transform, 
            chunks_size=chunks_size)
        if isinstance(labels, str):
            data = data.it_length(length)
            data_shape = list(data.shape[:-1]) + [data.shape[-1] - 1]
            self._set_space_shape('data', data_shape, data.global_dtype)
            if isinstance(data.dtype, list):
                dtype_dict = dict(data.dtype)
                self._set_space_shape('labels', (data.shape[0],), dtype_dict[labels])
            else:
                self._set_space_shape('labels', (data.shape[0],), data.global_dtype)
            self.chunks_writer_split("/data/data", "/data/labels", data, labels)
        else:
            if not isinstance(labels, Iterator):
                labels = Iterator(labels, dtype=labels.dtype).to_chunks(chunks_size)
            data = data.it_length(length)
            labels = labels.it_length(length)
            self._set_space_shape('data', data.shape, data.global_dtype)
            self._set_space_shape('labels', labels.shape, labels.dtype)
            self.chunks_writer("/data/data", data)
            self.chunks_writer("/data/labels", labels)

        #self.md5 = self.calc_md5()
        columns = data.columns
        self._set_space_fmtypes(len(columns))
        if columns is not None:
            self.columns = columns

    def empty(self, name, dataset_path=None):
        """
        build an empty DataLabel with the default parameters
        """
        dl = DataLabel(name=name, 
            dataset_path=dataset_path,
            description=self.description,
            author=self.author,
            compression_level=self.compression_level,
            clean=True)
        return dl

    def convert(self, name, percentaje=1, dataset_path=None, transforms=None, 
        chunks_size=258):
        """
        :type dtype: string
        :param dtype: cast the data to the defined type

        dataset_path is not necesary to especify, this info is obtained from settings.cfg
        """
        dl = self.empty(name, dataset_path=dataset_path)
        with self:
            dl.from_data(self[:], self.labels[:], calc_nshape(self, percentaje), 
                chunks_size=chunks_size, transform=transforms is not None)
        if transforms is not None:
            dl.transforms = self.transforms + transforms
        else:
            dl.transforms = self.transforms
        return dl      

    def to_df(self, include_target=True):
        """
        convert the dataset to a dataframe
        """
        if len(self.shape) > 2:
            raise Exception("I could don't convert a multiarray to tabular")

        if include_target == True:
            columns_name = list(self.columns) + ["target"]
            return pd.DataFrame(data=np.column_stack((self[:], self.labels[:])), columns=columns_name)
        else:
            columns_name = list(self.columns)
            return pd.DataFrame(data=self[:], columns=columns_name)

    def to_data(self):
        name = self.name + "_data_" + uuid.uuid4().hex
        data = super(DataLabel, self).empty(name)
        with self:
            data.from_data(self)
        return data

    def plot(self, view=None, type_g=None, columns=None):        
        import seaborn as sns
        import matplotlib.pyplot as plt
        import matplotlib.cm as cm

        if type_g == 'box':
            sns.set(style="whitegrid", palette="pastel", color_codes=True)
            col = int(view)
            sns.boxplot(x=self.labels, y=self.data[:,col], palette="PRGn")
            #sns.despine(offset=10, trim=True)
        elif type_g == "violin":
            sns.set(style="whitegrid", palette="pastel", color_codes=True)
            col = int(view)
            sns.violinplot(x=self.labels, y=self.data[:,col], palette="PRGn", inner="box")
            #sns.despine(offset=10, trim=True)
        elif type_g == "hist" and self.num_features() <= 64:
            #size = int(round(self.num_features() ** .5))
            #f, axarr = plt.subplots(size, size, sharey=True, sharex=True)
            #base = 0
            #for i in range(size):
            #    for j in range(size):
            #        axarr[i, j].set_title('Feature {}'.format(base+1))
            col = int(view)
            sns.distplot(self.data[:, col], bins=50, 
                kde=False, rug=False, color="b")#, ax=axarr[i, j])
        elif type_g == "hist_label" and self.is_binary() and self.num_features() <= 64:
            labels_info = self.labels_info()
            label_0 = labels_info.keys()[0]
            label_1 = labels_info.keys()[1]
            ds0, _ = self.only_labels_from_data(self, [label_0])
            ds1, _ = self.only_labels_from_data(self, [label_1])
            ds0 = np.asarray(ds0)
            ds1 = np.asarray(ds1)
            size = int(round(self.num_features() ** .5))
            f, axarr = plt.subplots(size, size, sharey=True, sharex=True)
            base = 0
            for i in range(size):
                for j in range(size):
                    axarr[i, j].set_title('Feature {}'.format(base+1))
                    sns.distplot(ds0[:, base:base+1], bins=50, 
                        kde=False, rug=False, color="b", ax=axarr[i, j])
                    sns.distplot(ds1[:, base:base+1], bins=50, 
                        kde=False, rug=False, color="r", ax=axarr[i, j])
                    base += 1
        elif type_g == "corr":
            df = self.to_df()
            df = df.iloc[:, :self.num_features()].astype(np.float64) 
            corr = df.corr()
            mask = np.zeros_like(corr, dtype=np.bool)
            mask[np.triu_indices_from(mask)] = True
            cmap = sns.diverging_palette(10, 240, n=6, as_cmap=True)
            sns.heatmap(corr, mask=mask, cmap=cmap, vmax=.3,
                square=True, xticklabels=5, yticklabels=5,
                linewidths=.5, cbar_kws={"shrink": .5})
        else:
            if self.shape[1] > 2:
                from ml.ae.extended.w_keras import PTsne
                dl = DataLabel(name=self.name+"_2d_", 
                        dataset_path=self.dataset_path,
                        compression_level=9)
                if not dl.exists():
                    ds = self.to_data()
                    classif = PTsne(model_name="tsne", model_version="1", 
                        check_point_path="/tmp/", dataset=ds, latent_dim=2)
                    classif.train(batch_size=50, num_steps=120)
                    data = np.asarray(list(classif.predict(self.data)))
                    dl.from_data(data, self.labels[:])
                    ds.destroy()
            else:
                dl = self

            if dl.shape[1] == 2:
                if type_g == "lm":
                    df = dl.to_df(labels2numbers=True)
                    sns.lmplot(x="c0", y="c1", data=df, hue="target")
                elif type_g == "scatter":
                    df = dl.to_df()
                    legends = []
                    labels = self.labels_info()
                    colors = cm.rainbow(np.linspace(0, 1, len(labels)))
                    for color, label in zip(colors, labels):
                        df_tmp = df[df["target"] == label]
                        legends.append((plt.scatter(df_tmp["c0"].astype("float64"), 
                            df_tmp["c1"].astype("float64"), color=color), label))
                    p, l = zip(*legends)
                    plt.legend(p, l, loc='lower left', ncol=3, fontsize=8, 
                        scatterpoints=1, bbox_to_anchor=(0,0))
                elif type_g == "pairplot":
                    df = dl.to_df(labels2numbers=True)
                    sns.pairplot(df.astype("float64"), hue='target', 
                        vars=df.columns[:-1], diag_kind="kde", palette="husl")
        plt.show()

    def labels2num(self):
        from sklearn.preprocessing import LabelEncoder
        le = LabelEncoder()
        le.fit(self.labels)
        return le

    def to_libsvm(self, name=None, save_to=None):
        """
        tranforms the dataset into libsvm format
        """
        from ml.utils.seq import libsvm_row
        le = self.labels2num()
        name = self.name+".txt" if name is None else name
        file_path = os.path.join(save_to, name)
        with open(file_path, 'w') as f:
            for row in libsvm_row(self.labels, self.data, le):
                f.write(" ".join(row))
                f.write("\n")

    def stadistics(self):
        from tabulate import tabulate
        from collections import defaultdict
        from ml.utils.numeric_functions import unique_size, data_type
        from ml.utils.numeric_functions import missing, zeros
        from ml.fmtypes import fmtypes_map

        headers = ["feature", "label", "missing", "mean", "std dev", "zeros", 
            "min", "25%", "50%", "75%", "max", "type", "unique"]
        table = []
        li = self.labels_info()
        feature_column = defaultdict(dict)
        for label in li:
            mask = (self.labels[:] == label)
            data = self.data[:][mask]
            for i, column in enumerate(data.T):
                percentile = np.nanpercentile(column, [0, 25, 50, 75, 100])
                values = [
                    "{0:.{1}f}%".format(missing(column), 2),
                    np.nanmean(column),  
                    np.nanstd(column),
                    "{0:.{1}f}%".format(zeros(column), 2),
                    ]
                values.extend(percentile)
                feature_column[i][label] = values

        data = self.data
        fmtypes = self.fmtypes
        for feature, rows in feature_column.items():
            column = data[:, feature]            
            usize = unique_size(column)
            if fmtypes is None or len(fmtypes) != self.num_features():
                data_t = data_type(usize, column.size).name
            else:
                data_t = fmtypes_map[fmtypes[feature]]

            for label, row in rows.items():
                table.append([feature, label] + row + [data_t, str(usize)])
                feature = "-"
                data_t = "-"
                usize = "-"

        return tabulate(table, headers)
    
    def cv(self, train_size=.7, valid_size=.1, unbalanced=None):
        from sklearn.model_selection import train_test_split

        train_size = round(train_size+valid_size, 2)
        X_train, X_test, y_train, y_test = train_test_split(
            self.data[:], self.labels[:], train_size=train_size, random_state=0)
        size = self.data.shape[0]
        valid_size_index = int(round(size * valid_size, 0))
        X_validation = X_train[:valid_size_index]
        y_validation = y_train[:valid_size_index]
        X_train = X_train[valid_size_index:]
        y_train = y_train[valid_size_index:]

        if unbalanced is not None:
            X_unb = [X_train, X_validation]
            y_unb = [y_train, y_validation]
            log.debug("Unbalancing data")
            for X_, y_ in [(X_test, y_test)]:
                X = np.c_[X_, y_]
                y_index = X_.shape[-1]
                unbalanced = sampling_size(unbalanced, y_)
                it = downsample(X, unbalanced, y_index, y_.shape[0])
                v = it.to_memory()
                if v.shape[0] == 0:
                    X_unb.append(v)
                    y_unb.append(v)
                    continue
                X_unb.append(v[:, :y_index])
                y_unb.append(v[:, y_index])
            return X_unb + y_unb
        else:
            return X_train, X_validation, X_test, y_train, y_validation, y_test        

    def cv_ds(self, train_size=.7, valid_size=.1, dataset_path=None, apply_transforms=True):
        data = self.cv(train_size=train_size, valid_size=valid_size)
        train_ds = DataLabel(name="train", dataset_path=dataset_path)
        train_ds.transforms = self.transforms
        with train_ds:
            train_ds.from_data(data[0], data[3], data[0].shape[0])
        validation_ds = DataLabel(name="validation", dataset_path=dataset_path)
        validation_ds.transforms = self.transforms
        with validation_ds:
            validation_ds.from_data(data[1], data[4], data[1].shape[0])
        test_ds = DataLabel(name="test", dataset_path=dataset_path)
        test_ds.transforms = self.transforms
        with test_ds:
            test_ds.from_data(data[2], data[5], data[2].shape[0])
        
        return train_ds, validation_ds, test_ds


class DataLabelFold(object):
    """
    Class for create datasets folds from datasets.
    
    :type n_splits: int
    :param n_plists: numbers of splits for apply to the dataset
    """
    def __init__(self, n_splits=2, dataset_path=None):
        self.name = uuid.uuid4().hex
        self.splits = []
        self.n_splits = n_splits
        self.dataset_path = settings["dataset_folds_path"] if dataset_path is None else dataset_path
    
    def create_folds(self, dl):
        """
        :type dl: DataLabel
        :param dl: datalabel to split

        return an iterator of splited datalabel in n_splits DataSetBuilder datasets
        """
        from sklearn.model_selection import StratifiedKFold
        skf = StratifiedKFold(n_splits=self.n_splits)        
        with dl:
            for i, (train, test) in enumerate(skf.split(dl.data, dl.labels)):
                dsb = DataLabel(name=self.name+"_"+str(i), 
                    dataset_path=self.dataset_path,
                    description="",
                    author="",
                    compression_level=3,
                    clean=True)
                data = dl.data[:]
                labels = dl.labels[:]
                with dsb:
                    dsb.from_data(data[train], labels[train])
                    yield dsb

    def from_data(self, dataset=None):
        """
        :type dataset: DataLabel
        :param dataset: dataset to fold

        construct the dataset fold from an DataSet class
        """
        for dsb in self.create_folds(dataset):
            self.splits.append(dsb.name)

    def get_splits(self):
        """
        return an iterator of datasets with the splits of original data
        """
        for split in self.splits:
            yield DataLabel(name=split, dataset_path=self.dataset_path)

    def destroy(self):
        for split in self.get_splits():
            split.destroy()
