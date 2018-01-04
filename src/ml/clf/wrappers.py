import numpy as np
import tensorflow as tf
import logging

from sklearn.preprocessing import LabelEncoder
from ml.utils.config import get_settings
from ml.models import MLModel, DataDrive, BaseModel
from ml.ds import DataLabel, Data
from ml.clf import measures as metrics
from ml.layers import IterLayer

settings = get_settings("ml")
log = logging.getLogger(__name__)
logFormatter = logging.Formatter("[%(name)s] - [%(levelname)s] %(message)s")
handler = logging.StreamHandler()
handler.setFormatter(logFormatter)
log.addHandler(handler)
log.setLevel(int(settings["loglevel"]))


class ClassifModel(BaseModel):
    def __init__(self, model_name=None, dataset=None, check_point_path=None, 
                model_version=None, autoload=True, group_name=None, metrics=None,
                dtype='float64', ltype='int'):

        self.le = LabelEncoder()
        self.base_labels = None
        super(ClassifModel, self).__init__(
            dataset=dataset,
            autoload=autoload,
            metrics=metrics,
            dtype=dtype,
            ltype=ltype,
            check_point_path=check_point_path,
            model_version=model_version,
            model_name=model_name,
            group_name=group_name)

    def scores(self, measures=None):
        from tqdm import tqdm
        if measures is None or isinstance(measures, str):
            measures = metrics.Measure.make_metrics(measures, name=self.model_name)
        with self.test_ds:
            test_data = self.test_ds.data[:]
            test_labels = self.test_ds.labels[:]

        predictions = np.asarray(list(tqdm(
            self.predict(test_data, raw=measures.has_uncertain(), transform=False, chunk_size=0), 
            total=test_labels.shape[0])))
        measures.set_data(predictions, test_labels, self.numerical_labels2classes)
        log.info("Getting scores")
        return measures.to_list()

    def confusion_matrix(self):
        from tqdm import tqdm
        with self.test_ds:
            test_data = self.test_ds.data[:]
            test_labels = self.test_ds.labels[:]
        predictions = self.predict(test_data, raw=False, 
            transform=False, chunk_size=0)
        measure = metrics.Measure(np.asarray(list(tqdm(predictions, 
                        total=test_labels.shape[0]))),
                        test_labels, 
                        labels2classes=self.numerical_labels2classes,
                        name=self.__class__.__name__)
        measure.add(metrics.confusion_matrix, greater_is_better=None, uncertain=False)
        return measure.to_list()

    def only_is(self, op):
        with self.test_ds:
            test_data = self.test_ds.data[:]
            test_labels = self.test_ds.labels[:]
        predictions = np.asarray(list(self.predict(test_data, raw=False, transform=False)))
        data = zip(*filter(
                        lambda x: op(x[1], x[2]), 
                        zip(test_data, 
                            self.numerical_labels2classes(predictions), 
                            self.numerical_labels2classes(test_labels))))
        if len(data) > 0:
            return np.array(data[0]), data[1], data[2]

    def erroneous_clf(self):
        import operator
        return self.only_is(operator.ne)

    def correct_clf(self):
        import operator
        return self.only_is(operator.eq)

    def reformat_labels(self, labels):
        #dataset = self.transform_shape(dataset)
        return labels

    def transform_shape(self, data, size=None):
        if isinstance(data, IterLayer):
            return np.asarray(list(data))
        elif len(data.shape) > 2:
            if size is None:
                size = data.shape[0]
            return data[:].reshape(size, -1)
        else:
            return data

    def is_binary():
        return self.num_labels == 2

    def labels_encode(self, labels):
        self.le.fit(labels)
        self.num_labels = self.le.classes_.shape[0]
        self.base_labels = self.le.classes_

    def load_original_ds(self):
        return Data.original_ds(self.original_dataset_name, self.original_dataset_path)

    def load_dataset(self, dataset):
        if dataset is None:
            self.test_ds = self.get_dataset()
            with self.load_original_ds() as ds:
                if isinstance(ds, DataLabel):
                    self.labels_encode(ds.labels)
        else:
            self.set_dataset(dataset)

        with self.test_ds:
            self.num_features = self.test_ds.num_features()

    def position_index(self, label):
        if isinstance(label, np.ndarray) or isinstance(label, list):
            return np.argmax(label, axis=1)
        return label

    def convert_label(self, label, raw=False):
        if raw is True:
            return label
        elif raw is None:
            return self.position_index(label)
        else:
            return self.le.inverse_transform(self.position_index(label))

    def numerical_labels2classes(self, labels):
        if len(labels.shape) > 1 and labels.shape[1] > 1:
            return self.le.inverse_transform(np.argmax(labels, axis=1))
        else:
            return self.le.inverse_transform(labels.astype('int'))

    def reformat_all(self, dataset):
        log.info("Reformating {}...".format(self.cls_name()))
        dl_train = DataLabel(
            dataset_path=settings["dataset_model_path"],
            apply_transforms=not dataset._applied_transforms,
            compression_level=9,
            transforms=dataset.transforms,
            rewrite=True)
        dl_test = DataLabel(
            dataset_path=settings["dataset_model_path"],
            apply_transforms=not dataset._applied_transforms,
            compression_level=9,
            transforms=dataset.transforms,
            rewrite=True)
        dl_validation = DataLabel(
            dataset_path=settings["dataset_model_path"],
            apply_transforms=not dataset._applied_transforms,
            compression_level=9,
            transforms=dataset.transforms,
            rewrite=True)

        self.labels_encode(dataset.labels)
        log.info("Labels encode finished")
        train_data, validation_data, test_data, train_labels, validation_labels, test_labels = dataset.cv()
        train_labels = self.reformat_labels(self.le.transform(train_labels))
        validation_labels = self.reformat_labels(self.le.transform(validation_labels))
        test_labels = self.reformat_labels(self.le.transform(test_labels))
        with dl_train:
            dl_train.build_dataset(train_data, train_labels)
            dl_train.apply_transforms = True
            dl_train._applied_transforms = dataset._applied_transforms
        with dl_test:
            dl_test.build_dataset(test_data, test_labels)
            dl_test.apply_transforms = True
            dl_test._applied_transforms = dataset._applied_transforms
        with dl_validation:
            dl_validation.build_dataset(validation_data, validation_labels)
            dl_validation.apply_transforms = True
            dl_validation._applied_transforms = dataset._applied_transforms

        return dl_train, dl_test, dl_validation

    def _predict(self, data, raw=False):
        prediction = self.model.predict(data)
        if not isinstance(prediction, np.ndarray):
            prediction = np.asarray(prediction, dtype=np.float)
        return self.convert_label(prediction, raw=raw)



class SKL(ClassifModel):
    def convert_label(self, label, raw=False):
        if raw is True:
            return (np.arange(self.num_labels) == label).astype(np.float32)
        elif raw is None:
            return self.position_index(label)
        else:
            return self.le.inverse_transform(self.position_index(label))

    def ml_model(self, model):        
        from sklearn.externals import joblib
        return MLModel(fit_fn=model.fit, 
                            predictors=[model.predict],
                            load_fn=self.load_fn,
                            save_fn=lambda path: joblib.dump(model, '{}'.format(path)))

    def load_fn(self, path):
        model = joblib.load('{}'.format(path))
        self.model = self.ml_model(model)


class SKLP(ClassifModel):
    def __init__(self, *args, **kwargs):
        super(SKLP, self).__init__(*args, **kwargs)

    def ml_model(self, model):        
        from sklearn.externals import joblib
        return MLModel(fit_fn=model.fit, 
                            predictors=[model.predict_proba],
                            load_fn=self.load_fn,
                            save_fn=lambda path: joblib.dump(model, '{}'.format(path)))

    def load_fn(self, path):
        from sklearn.externals import joblib
        model = joblib.load('{}'.format(path))
        self.model = self.ml_model(model)


class XGB(ClassifModel):
    def ml_model(self, model, model_2=None):
        return MLModel(fit_fn=model.train, 
                            predictors=[model_2.predict],
                            load_fn=self.load_fn,
                            save_fn=model_2.save_model,
                            transform_data=self.array2dmatrix)

    def load_fn(self, path):
        import xgboost as xgb
        booster = xgb.Booster()
        booster.load_model(path)
        self.model = self.ml_model(xgb, model_2=booster)

    def array2dmatrix(self, data):
        import xgboost as xgb
        return xgb.DMatrix(data)


class LGB(ClassifModel):
    def ml_model(self, model, model_2=None):
        return MLModel(fit_fn=model.train, 
                            predictors=[model_2.predict],
                            load_fn=self.load_fn,
                            save_fn=model_2.save_model)

    def load_fn(self, path):
        import lightgbm as lgb
        bst = lgb.Booster(model_file=path)
        self.model = self.ml_model(lgb, model_2=bst)

    def array2dmatrix(self, data):
        import lightgbm as lgb
        return lgb.Dataset(data)


class TFL(ClassifModel):

    def reformat_labels(self, labels):
        #data = self.transform_shape(data)
        # Map 0 to [1.0, 0.0, 0.0 ...], 1 to [0.0, 1.0, 0.0 ...]
        return (np.arange(self.num_labels) == labels[:,None]).astype(np.float)

    def load_fn(self, path):
        model = self.prepare_model()
        self.model = MLModel(fit_fn=model.fit, 
                            predictors=[model.predict],
                            load_fn=self.load_fn,
                            save_fn=model.save)

    def predict(self, data, raw=False, transform=True, chunk_size=1):
        with tf.Graph().as_default():
            return super(TFL, self).predict(data, raw=raw, transform=transform, chunk_size=chunk_size)

    def train(self, batch_size=10, num_steps=1000, n_splits=None):
        with tf.Graph().as_default():
            self.model = self.prepare_model()
            self.model.fit(self.dataset.train_data, 
                self.dataset.train_labels, 
                n_epoch=num_steps, 
                validation_set=(self.dataset.validation_data, self.dataset.validation_labels),
                show_metric=True, 
                batch_size=batch_size,
                run_id="tfl_model")
            self.save_model()


class Keras(ClassifModel):
    def __init__(self, **kwargs):
        super(Keras, self).__init__(**kwargs)
        self.ext = "ckpt"

    def load_fn(self, path):
        from keras.models import load_model
        model = load_model(path)
        self.model = self.ml_model(model)

    def ml_model(self, model):
        return MLModel(fit_fn=model.fit, 
                        predictors=[model.predict],
                        load_fn=self.load_fn,
                        save_fn=model.save)

    def reformat_labels(self, labels):
        return (np.arange(self.num_labels) == labels[:,None]).astype(np.float)

    def train_kfolds(self, batch_size=10, num_steps=100, n_splits=None):
        from sklearn.model_selection import StratifiedKFold
        self.model = self.prepare_model_k()
        cv = StratifiedKFold(n_splits=n_splits)
        
        with self.train_ds:
            labels = self.position_index(self.train_ds.labels[:])
            for k, (train, test) in enumerate(cv.split(self.train_ds.data, labels), 1):
                train = list(train)
                test = list(test)
                self.model.fit(self.train_ds.data[train], 
                    self.train_ds.labels[train],
                    epochs=num_steps,
                    batch_size=batch_size,
                    shuffle="batch",
                    validation_data=(self.train_ds.data[test], self.train_ds.labels[test]))
                print("fold ", k)

    def train(self, batch_size=0, num_steps=0, n_splits=None):
        if n_splits is not None:
            self.train_kfolds(batch_size=batch_size, num_steps=num_steps, n_splits=n_splits)
        else:
            self.model = self.prepare_model()
            with self.train_ds, self.validation_ds:
                self.model.fit(self.train_ds.data, 
                    self.train_ds.labels,
                    epochs=num_steps,
                    batch_size=batch_size,
                    shuffle="batch",
                    validation_data=(self.validation_ds.data, self.validation_ds.labels))
        self.save_model()

