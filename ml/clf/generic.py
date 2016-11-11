import os
import numpy as np
import tensorflow as tf
import logging

from sklearn.preprocessing import LabelEncoder

logging.basicConfig()
log = logging.getLogger(__name__)
#np.random.seed(133)

class Measure(object):
    def __init__(self, predictions, labels):
        if len(predictions.shape) > 1:
            self.transform = lambda x: np.argmax(x, 1)
        else:
            self.transform = lambda x: x
        
        self.labels = labels
        self.predictions = predictions
        self.average = "macro"

    def accuracy(self):
        from sklearn.metrics import accuracy_score
        return accuracy_score(self.labels, self.transform(self.predictions))

    #false positives
    def precision(self):
        from sklearn.metrics import precision_score
        return precision_score(self.labels, self.transform(self.predictions), 
            average=self.average, pos_label=None)

    #false negatives
    def recall(self):
        from sklearn.metrics import recall_score
        return recall_score(self.labels, self.transform(self.predictions), 
            average=self.average, pos_label=None)

    #weighted avg presicion and recall
    def f1(self):
        from sklearn.metrics import f1_score
        return f1_score(self.labels, self.transform(self.predictions), 
            average=self.average, pos_label=None)

    def auc(self):
        from sklearn.metrics import roc_auc_score
        return roc_auc_score(self.labels, self.transform(self.predictions), 
            average=self.average)

    def confusion_matrix(self, base_labels=None):
        from sklearn.metrics import confusion_matrix
        cm = confusion_matrix(self.labels, self.transform(self.predictions), labels=base_labels)
        return cm.astype('float') / cm.sum(axis=1)[:, np.newaxis]

    def logloss(self):
        from sklearn.metrics import log_loss
        return log_loss(self.labels, self.predictions)


class ListMeasure(object):
    def __init__(self, headers=None, measures=None):
        if headers is None:
            headers = []
        if measures is None:
            measures = [[]]

        self.headers = headers
        self.measures = measures

    def add_measure(self, name, value, i=0):
        self.headers.append(name)
        self.measures[i].append(value)

    def get_measure(self, name):
        try:
            i = self.headers.index(name)
        except IndexError:
            i = 0

        for measure in self.measures:
            yield measure[i]

    def print_scores(self, order_column="f1"):
        from utils.order import order_table_print
        order_table_print(self.headers, self.measures, order_column)

    def print_matrix(self, labels):
        from tabulate import tabulate
        for name, measure in self.measures:
            print("******")
            print(name)
            print("******")
            print(tabulate(np.c_[labels.T, measure], list(labels)))

    def __add__(self, other):
        for hs, ho in zip(self.headers, other.headers):
            if hs != ho:
                raise Exception

        diff_len = abs(len(self.headers) - len(other.headers)) + 1
        if len(self.headers) < len(other.headers):
            headers = other.headers
            this_measures = [m +  ([None] * diff_len) for m in self.measures]
            other_measures = other.measures
        elif len(self.headers) > len(other.headers):
            headers = self.headers
            this_measures = self.measures
            other_measures = [m + ([None] * diff_len) for m in other.measures]
        else:
            headers = self.headers
            this_measures = self.measures
            other_measures = other.measures

        list_measure = ListMeasure(
            headers=headers, measures=this_measures+other_measures)
        return list_measure

    def calc_scores(self, name, predict, clf, measures=None):
        if measures is None:
            measures = ["accuracy", "presicion", "recall", "f1", "auc", "logloss"]
        elif isinstance(measures, str):
            measures = measures.split(",")
        else:
            measures = []
        uncertain = "logloss" in measures
        predictions = np.asarray(list(
            predict(clf.dataset.test_data, raw=uncertain, transform=False, chunk_size=258)))
        measure = Measure(predictions, 
            np.asarray([clf.convert_label(label, raw=False)
            for label in clf.dataset.test_labels]))
        self.add_measure("CLF", name)

        measure_class = []
        for measure_name in measures:
            measure_name = measure_name.strip()
            if hasattr(measure, measure_name):
                measure_class.append((measure_name, measure))

        for measure_name, measure in measure_class:
            self.add_measure(measure_name, getattr(measure, measure_name)())

class DataDrive(object):
    def __init__(self, check_point_path=None, model_version=None, model_name=None):
        self.check_point_path = check_point_path
        self.model_version = model_version
        self.model_name = model_name

    def _metadata(self):
        pass

    def save_meta(self):
        from ml.ds import save_metadata
        if self.check_point_path is not None:
            path = self.make_model_file()
            save_metadata(path+".xmeta", self._metadata())

    def load_meta(self):
        from ml.ds import load_metadata
        if self.check_point_path is not None:
            path = self.make_model_file(check=False)
            return load_metadata(path+".xmeta")

    def get_model_name_v(self):
        if self.model_version is None:
            id_ = "123"
        else:
            id_ = self.model_version
        return "{}.{}".format(self.model_name, id_)

    def make_model_file(self, check=True):
        model_name_v = self.get_model_name_v()
        check_point = os.path.join(self.check_point_path, self.__class__.__name__)
        if check is True:
            if not os.path.exists(check_point):
                os.makedirs(check_point)

            destination = os.path.join(check_point, model_name_v)
            if not os.path.exists(destination):
                os.makedirs(destination)
        
        return os.path.join(check_point, model_name_v, model_name_v)

    def print_meta(self):
        print(self.load_meta())


class Grid(DataDrive):
    def __init__(self, classifs, model_name=None, dataset=None, 
            check_point_path=None, model_version=None):
        self.model = None
        #self.model_name = model_name
        #self.check_point_path = check_point_path
        #self.model_version = model_version
        self.dataset = dataset
        self.classifs = classifs
        self.params = {}
        super(Grid, self).__init__(
            check_point_path=check_point_path,
            model_version=model_version,
            model_name=model_name)
        
    def load_models(self):
        for classif in self.classifs:
            yield self.load_model(classif, info=False)
    
    def load_model(self, model, info=True, dataset=None):
        dataset = self.dataset if dataset is None else dataset
        return model(dataset=dataset, 
                model_name=self.model_name, 
                model_version=self.model_version, 
                check_point_path=self.check_point_path,
                info=info,
                **self.get_params(model.cls_name()))

    def train(self, batch_size=128, num_steps=1):
        for classif in self.load_models():
            classif.train(batch_size=batch_size, num_steps=num_steps)
    
    def all_clf_scores(self, measures=None):
        from operator import add
        return reduce(add, (classif.scores(measures=measures) for classif in self.load_models()))

    def scores(self, measures=None):
        return self.all_clf_scores(measures=measures)

    def print_confusion_matrix(self):
        from operator import add
        list_measure = reduce(add, (classif.confusion_matrix() for classif in self.load_models()))
        classifs_reader = self.load_models()
        classif = classifs_reader.next()
        list_measure.print_matrix(classif.base_labels)

    def add_params(self, model_cls, **params):
        self.params.setdefault(model_cls, params)
        self.params[model_cls].update(params)

    def get_params(self, model_cls):
        return self.params.get(model_cls, {})

    def ordered_best_predictors(self, measure="logloss", operator=None):
        from functools import cmp_to_key
        list_measure = self.all_clf_scores(measures=measure)
        column_measures = list_measure.get_measure(measure)

        class DTuple:
            def __init__(self, counter, elem):
                self.elem = elem
                self.counter = counter
            
            def __sub__(self, other):
                if self.elem is None or other is None:
                    return 0
                return self.elem - other.elem

            def __str__(self):
                return "({}, {})".format(self.counter, self.elem)

            def __repr__(self):
                return self.__str__()

        def enum(seq, position=0):
            counter = 0
            for elem in seq:
                yield DTuple(counter, elem)
                counter += 1

        return sorted(enum(column_measures), key=cmp_to_key(operator))

    def best_predictor_threshold(self, threshold=2, limit=3, measure="logloss", operator=None):
        best = self.ordered_best_predictors(measure=measure, operator=operator)
        base = best[0].elem
        return filter(lambda x: x[1] < threshold, 
            ((elem.counter, elem.elem/base) for elem in best if elem.elem is not None))[:limit]

    def best_predictor(self, measure="logloss", operator=None):
        best = self.ordered_best_predictors(measure=measure, operator=operator)[0].counter
        #self.load_model(self.classifs[best], info=False)
        return best

    def predict(self, data, raw=False, transform=True, chunk_size=1):
        for classif in self.load_models():
            yield classif.predict(data, raw=raw, transform=transform, chunk_size=chunk_size)


class Voting(Grid):
    def __init__(self, classifs, weights=None, election='best', num_max_clfs=1, **kwargs):
        super(Voting, self).__init__(classifs, **kwargs)
        if len(classifs) > 0:
            self.weights = self.set_weights(0, classifs, weights)
            self.election = election
            self.num_max_clfs = num_max_clfs
        else:
            meta = self.load_meta()
            from pydoc import locate
            self.classifs = [locate(model) for model in meta.get('models', [])]
            self.weights = {index: w for index, w in enumerate(meta['weights'])}
            self.election = meta["election"]

    def avg_prediction(self, predictions, weights, uncertain=True):
        from itertools import izip
        if uncertain is False:
            from utils.numeric_functions import discrete_weight
            return discrete_weight(predictions, weights)
        else:
            from utils.numeric_functions import arithmetic_mean
            predictions_iter = ((prediction * w for prediction in row_prediction)
                for w, row_prediction in izip(weights, predictions))
            return arithmetic_mean(predictions_iter, float(sum(weights)))

    def train(self, batch_size=128, num_steps=1, only_voting=False):
        if only_voting is False:
            for classif in self.load_models():
                print("Training [{}]".format(classif.__class__.__name__))
                classif.train(batch_size=batch_size, num_steps=num_steps)

        if self.election == "best":
            from utils.numeric_functions import le
            best = self.best_predictor(operator=le)
            self.weights = self.set_weights(best, self.classifs, self.weights.values())
            models = self.classifs
            models_index = range(len(self.classifs))
        elif self.election == "best-c":
            bests = self.correlation_between_models(sort=True)
            self.weights = self.set_weights(bests[0], self.classifs, self.weights.values())
            models = [self.classifs[index] for index in bests]
            models_index = bests

        weights = [self.weights[index] for index in models_index]
        self.save_model(models, weights)

    def _metadata(self):
        return {"dataset_path": self.dataset.dataset_path,
                "dataset_name": self.dataset.name,
                "models": self.clf_models_namespace,
                "weights": self.clf_weights,
                "election": self.election}

    def save_model(self, models, weights):
        self.clf_models_namespace = [model.module_cls_name() for model in models]
        self.clf_weights = weights
        if self.check_point_path is not None:
            path = self.make_model_file()
            self.save_meta()

    def scores(self, measures=None, all_clf=True):
        clf = self.load_models().next()
        list_measure = ListMeasure()
        list_measure.calc_scores(self.__class__.__name__, self.predict, clf, measures=measures)
        if all_clf is True:
            return list_measure + self.all_clf_scores(measures=measures)
        else:
            return list_measure

    def set_weights(self, best, classifs, values):
        if values is None:
            values = [1]
        max_value = max(values)
        min_value = min(values)
        weights = {} 
        for c_index, clf in enumerate(classifs):
            if c_index == best:
                weights[c_index] = max_value
            else:
                weights[c_index] = min_value
        return weights

    def predict(self, data, raw=False, transform=True, chunk_size=1):
        models = (self.load_model(classif, info=False) for classif in self.classifs)
        weights = [w for i, w in sorted(self.weights.items(), key=lambda x:x[0])]
        predictions = (
            classif.predict(data, raw=raw, transform=transform, chunk_size=chunk_size)
            for classif in models)
        return self.avg_prediction(predictions, weights, uncertain=raw)

    def correlation_between_models(self, sort=False):
        from utils.numeric_functions import le, pearsoncc
        from utils.network import all_simple_paths_graph
        from itertools import combinations
        from utils.order import order_from_ordered
        import networkx as nx

        best_predictors = []
        def predictions_fn():
            predictions = {}
            for index, _ in self.best_predictor_threshold(operator=le, limit=self.num_max_clfs):
                classif = self.load_model(self.classifs[index], info=False)
                predictions[index] = np.asarray(list(classif.predict(
                    classif.dataset.test_data, raw=False, transform=False, chunk_size=258)))
                best_predictors.append(index)
            return predictions

        def correlations_fn(predictions):
            for clf_index1, clf_index2 in combinations(predictions.keys(), 2):
                correlation = pearsoncc(predictions[clf_index1], predictions[clf_index2])
                yield (clf_index1, clf_index2, correlation)

        FG = nx.Graph()
        FG.add_weighted_edges_from(correlations_fn(predictions_fn()))
        classif_weight = []
        for initial_node in FG.nodes():
            for path in all_simple_paths_graph(FG, initial_node, self.num_max_clfs-2):
                total_weight = sum(FG[v1][v2]["weight"] for v1, v2 in combinations(path, 2))
                #total_weight = sum(FG[v1][v2]["weight"] for v1, v2 in zip(path, path[1:]))
                classif_weight.append((total_weight/len(path), path))

        relation_clf = max(classif_weight, key=lambda x:x[0])[1]
        if sort:
            return order_from_ordered(best_predictors, relation_clf)
        else:
            return relation_clf


class Stacking(Grid):
    def train(self, batch_size=128, num_steps=1):
        from sklearn.model_selection import StratifiedKFold
        clf_b = self.load_models().next()
        num_classes = len(clf_b.dataset.labels_info().keys())
        skf = StratifiedKFold(n_splits=num_classes)
        data, labels = clf_b.dataset.desfragment()
        size = data.shape[0]
        self.dataset_blend_train = np.zeros((size, len(self.classifs), num_classes))
        for j, clf in enumerate(self.load_models()):
            print(j, clf.cls_name())
            #clf.model_name = clf.dataset.name + "-s"
            for i, (train, test) in enumerate(skf.split(data, labels)):
                print("Fold", i)
                clf.dataset.train_data = data[train]
                clf.dataset.train_labels = labels[train]
                clf.dataset.test_data = data[test]
                clf.dataset.test_labels = labels[test]
                clf.train(batch_size=batch_size, num_steps=num_steps)
                y_submission = list(
                    clf.predict(clf.dataset.test_data, raw=True, transform=False, chunk_size=0))
                self.dataset_blend_train[test, j] = y_submission
            self.i = i + 1

    def predict(self, data, raw=False, transform=True, chunk_size=1):
        from sklearn.linear_model import LogisticRegression
        clf_b = self.load_models().next()
        _, labels = clf_b.dataset.desfragment()
        size = data.shape[0]
        num_classes = len(clf_b.dataset.labels_info().keys())
        dataset_blend_test = np.zeros((size, len(self.classifs), num_classes))
        for j, clf in enumerate(self.load_models()):
            dataset_blend_test_j = np.zeros((size, self.i, num_classes))
            count = 0            
            while count < self.i:
                dataset_blend_test_j[:, count] = np.asarray(list(
                    clf.predict(data, raw=True, transform=transform, chunk_size=0)))
                count += 1
            dataset_blend_test[:, j] = dataset_blend_test_j.mean(1)

        clf = LogisticRegression()
        clf.fit(self.dataset_blend_train.reshape(self.dataset_blend_train.shape[0], -1), labels)
        return clf.predict_proba(dataset_blend_test.reshape(dataset_blend_test.shape[0], -1))

    def scores(self, measures=None, all_clf=True):
        clf = self.load_models().next()
        list_measure = ListMeasure()
        list_measure.calc_scores(self.__class__.__name__, self.predict, clf, measures=measures)
        if all_clf is True:
            return list_measure + self.all_clf_scores(measures=measures)
        else:
            return list_measure


class Bagging(Grid):
    def __init__(self, classif, classifs_rbm, **kwargs):
        self.classif = classif
        super(Bagging, self).__init__(classifs_rbm, **kwargs)
        self.name_sufix = "-bagging"

    def train(self, batch_size=128, num_steps=1):
        import ml
        for classif in self.load_models():
            classif.train(batch_size=batch_size, num_steps=num_steps)

        model_base = self.load_model(self.classif, info=False)
        params = model_base.dataset.to_raw()
        params["train_dataset"] = self.prepare_data(params["train_dataset"], transform=False)
        params["test_dataset"] = self.prepare_data(params["test_dataset"], transform=False)
        params["valid_dataset"] =  self.prepare_data(params["valid_dataset"], transform=False)
        if params["train_labels"].shape[1] > 1:
            transform_fn = lambda x: np.argmax(x, axis=1)
            
        params["train_labels"] = transform_fn(params["train_labels"])
        params["test_labels"] = transform_fn(params["test_labels"])
        params["valid_labels"] = transform_fn(params["valid_labels"])
        params["md5"] = None
        dataset = ml.ds.DataSetBuilder.from_raw_to_ds(
            model_base.dataset.name+self.name_sufix,
            model_base.dataset.dataset_path, 
            **params)
        model_base.set_dataset(dataset)
        model_base.model_name = model_base.model_name+self.name_sufix
        model_base.train(batch_size=batch_size, num_steps=num_steps)

    def prepare_data(self, data, transform=True, chunk_size=1):
        from utils.numeric_functions import geometric_mean
        predictions = (
            classif.predict(data, raw=True, transform=transform, chunk_size=chunk_size)
            for classif in self.load_models())
        predictions = np.asarray(list(geometric_mean(predictions, len(self.classifs))))
        return self.dataset.processing(np.append(data, predictions, axis=1), 'global')

    def predict(self, data, raw=False, transform=True, chunk_size=1):
        import ml
        dataset = ml.ds.DataSetBuilder.load_dataset(
            self.dataset.name+self.name_sufix, 
            dataset_path=self.dataset.dataset_path)
        model_base = self.load_model(self.classif, info=False, dataset=dataset)
        data_model_base = self.prepare_data(data, transform=transform, chunk_size=chunk_size)
        return model_base.predict(data_model_base, raw=raw, transform=False, chunk_size=chunk_size)
    
    def scores(self, measures=None, all_clf=True):
        clf = self.load_model(self.classif, info=False)
        list_measure = ListMeasure()
        list_measure.calc_scores(self.__class__.__name__, self.predict, clf, measures=measures)
        if all_clf is True:
            return list_measure + self.all_clf_scores(measures=measures)
        else:
            return list_measure


class BaseClassif(DataDrive):
    def __init__(self, model_name=None, dataset=None, 
            check_point_path=None, model_version=None,
            dataset_train_limit=None,
            info=True):
        self.model = None
        #self.model_name = model_name
        self.le = LabelEncoder()
        #self.check_point_path = check_point_path
        #self.model_version = model_version
        self.dataset_train_limit = dataset_train_limit
        self.print_info = info
        self.base_labels = None
        self._original_dataset_md5 = None
        super(BaseClassif, self).__init__(
            check_point_path=check_point_path,
            model_version=model_version,
            model_name=model_name)
        self.load_dataset(dataset)

    @classmethod
    def cls_name(cls):
        return cls.__name__

    @classmethod
    def module_cls_name(cls):
        return "{}.{}".format(cls.__module__, cls.__name__)

    #classmethod
    #sef cls_name_simple(cls):
    #   try:
    #        return cls.__name__.split(".").pop()
    #    except IndexError:
    #        return cls.__name__

    def scores(self, measures=None):
        list_measure = ListMeasure()
        list_measure.calc_scores(self.__class__.__name__, self.predict, self, measures=measures)
        return list_measure

    def confusion_matrix(self):
        list_measure = ListMeasure()
        predictions = self.predict(self.dataset.test_data, raw=False, transform=False)
        measure = Measure(np.asarray(list(predictions)), 
            np.asarray([self.convert_label(label, raw=False)
            for label in self.dataset.test_labels]))
        list_measure.add_measure("CLF", self.__class__.__name__)
        list_measure.add_measure("CM", measure.confusion_matrix(base_labels=self.base_labels))
        return list_measure

    def only_is(self, op):
        predictions = list(self.predict(self.dataset.test_data, raw=False, transform=False))
        labels = [self.convert_label(label) for label in self.dataset.test_labels]
        data = zip(*filter(lambda x: op(x[1], x[2]), 
            zip(self.dataset.test_data, predictions, labels)))
        return np.array(data[0]), data[1], data[2]

    def erroneous_clf(self):
        import operator
        return self.only_is(operator.ne)

    def correct_clf(self):
        import operator
        return self.only_is(operator.eq)

    def reformat(self, dataset, labels):
        dataset = self.transform_shape(dataset)
        return dataset, labels

    def transform_shape(self, data, size=None):
        if size is None:
            size = data.shape[0]
        return data.reshape(size, -1).astype(np.float32)

    def is_binary():
        return self.num_labels == 2

    def labels_encode(self, labels):
        self.le.fit(labels)
        self.num_labels = self.le.classes_.shape[0]
        self.base_labels = self.le.classes_

    def position_index(self, label):
        if isinstance(label, np.ndarray) or isinstance(label, list):
            return np.argmax(label)
        return label

    def convert_label(self, label, raw=False):
        if raw is True:
            return label
        else:
            return self.le.inverse_transform(self.position_index(label))

    def reformat_all(self):
        all_ds = np.concatenate((self.dataset.train_labels, 
            self.dataset.valid_labels, self.dataset.test_labels), axis=0)
        self.labels_encode(all_ds)
        self.dataset.train_data, self.dataset.train_labels = self.reformat(
            self.dataset.train_data, self.le.transform(self.dataset.train_labels))
        self.dataset.test_data, self.dataset.test_labels = self.reformat(
            self.dataset.test_data, self.le.transform(self.dataset.test_labels))
        self.num_features = self.dataset.test_data.shape[-1]

        if len(self.dataset.valid_labels) > 0:
            self.dataset.valid_data, self.dataset.valid_labels = self.reformat(
                self.dataset.valid_data, self.le.transform(self.dataset.valid_labels))

        if self.dataset_train_limit is not None:
            if self.dataset.train_data.shape[0] > self.dataset_train_limit:
                self.dataset.train_data = self.dataset.train_data[:self.dataset_train_limit]
                self.dataset.train_labels = self.dataset.train_labels[:self.dataset_train_limit]

            if self.dataset.valid_data.shape[0] > self.dataset_train_limit:
                self.dataset.valid_data = self.dataset.valid_data[:self.dataset_train_limit]
                self.dataset.valid_labels = self.dataset.valid_labels[:self.dataset_train_limit]

    def load_dataset(self, dataset):
        if dataset is None:
            self.dataset = self.get_dataset()
        else:
            self.dataset = dataset.copy()
            self.model_name = self.dataset.name
        self._original_dataset_md5 = self.dataset.md5()
        self.reformat_all()

    def set_dataset(self, dataset):
        self.dataset = dataset
        self.reformat_all()

    def chunk_iter(self, data, chunk_size=1, transform_fn=None, uncertain=False):
        from ml.ds import grouper_chunk
        for chunk in grouper_chunk(chunk_size, data):
            data = np.asarray(list(chunk))
            size = data.shape[0]
            if data.shape[0] == 1 and len(data.shape) > 1:
                data = data[0]
            #else:
            #    size = 1
            for prediction in self._predict(transform_fn(data, size), raw=uncertain):
                yield prediction

    def predict(self, data, raw=False, transform=True, chunk_size=1):
        from ml.ds import grouper_chunk
        if self.model is None:
            self.load_model()

        if transform is True and chunk_size > 0:
            fn = lambda x, s: self.transform_shape(self.dataset.processing(x, 'global'), size=s)
            return self.chunk_iter(data, chunk_size, transform_fn=fn, uncertain=raw)
        elif transform is True and chunk_size == 0:
            data = self.transform_shape(self.dataset.processing(data, 'global'))
            return self._predict(data, raw=raw)
        elif transform is False and chunk_size > 0:
            fn = lambda x, s: self.transform_shape(x, size=s)
            return self.chunk_iter(data, chunk_size, transform_fn=fn, uncertain=raw)
        else:
            return self._predict(data, raw=raw)

    def _pred_erros(self, predictions, test_data, test_labels, valid_size=.1):
        validation_labels_d = {}
        pred_index = []
        for index, (pred, label) in enumerate(zip(predictions, test_labels)):
            if pred[1] >= .5 and (label < .5 or label == 0):
                pred_index.append((index, label - pred[1]))
                validation_labels_d[index] = 1
            elif pred[1] < .5 and (label >= .5 or label == 1):
                pred_index.append((index, pred[1] - label))
                validation_labels_d[index] = 0

        pred_index = sorted(filter(lambda x: x[1] < 0, pred_index), 
            key=lambda x: x[1], reverse=False)
        pred_index = pred_index[:int(len(pred_index) * valid_size)]
        validation_data = np.ndarray(
            shape=(len(pred_index), test_data.shape[1]), dtype=np.float32)
        validation_labels = np.ndarray(shape=len(pred_index), dtype=np.float32)
        for i, (j, _) in enumerate(pred_index):
            validation_data[i] = test_data[j]
            validation_labels[i] = validation_labels_d[j]
        return validation_data, validation_labels, pred_index

    def rebuild_validation_from_errors(self, dataset, valid_size=.1, test_data_labels=None):
        valid_size = dataset.valid_size if valid_size is None else valid_size
        if dataset.is_binary():
            if dataset.test_folder_path is not None or test_data_labels is None:
                test_data, test_labels = dataset.test_data, dataset.test_labels
                predictions = self.predict(self.dataset.test_data, raw=True, transform=False)
            else:
                test_data, test_labels = test_data_labels
                predictions = self.predict(test_data, raw=True, transform=True)
                test_data = dataset.processing(test_data, 'global')

            ndataset = dataset.copy()
            ndataset.train_data = np.concatenate(
                (dataset.train_data, dataset.valid_data), axis=0)
            ndataset.train_labels = np.concatenate(
                (dataset.train_labels, dataset.valid_labels), axis=0)
            ndataset.valid_data, ndataset.valid_labels, pred_index = self._pred_erros(
                predictions, test_data, test_labels, valid_size=valid_size)
            indexes = sorted(np.array([index for index, _ in pred_index]))            
            ndataset.test_data = np.delete(test_data, indexes, axis=0)
            ndataset.test_labels = np.delete(test_labels, indexes)
            ndataset.info()
            return ndataset
        else:
            raise Exception

    def train2steps(self, dataset, valid_size=.1, batch_size=10, num_steps=1000, test_data_labels=None):
        self.train(batch_size=batch_size, num_steps=num_steps)
        dataset_v = self.rebuild_validation_from_errors(dataset, 
            valid_size=valid_size, test_data_labels=test_data_labels)
        self.set_dataset(dataset)
        self.train(batch_size=batch_size, num_steps=num_steps)

    #def get_model_name_v(self):
    #    if self.model_version is None:
    #        import datetime
    #        id_ = datetime.datetime.today().strftime("%Y-%m-%d-%H:%M:%S")
    #    else:
    #        id_ = self.model_version
    #    return "{}.{}".format(self.model_name, id_)

    #def make_model_file(self, check=True):
    #    model_name_v = self.get_model_name_v()
    #    check_point = os.path.join(self.check_point_path, self.__class__.__name__)
    #    if check is True:
    #        if not os.path.exists(check_point):
    #            os.makedirs(check_point)

    #        destination = os.path.join(check_point, model_name_v)
    #        if not os.path.exists(destination):
    #            os.makedirs(destination)
        
    #    return os.path.join(check_point, model_name_v, model_name_v)

    def _metadata(self):
        return {"dataset_path": self.dataset.dataset_path,
                "dataset_name": self.dataset.name,
                "md5": self._original_dataset_md5, #not reformated dataset
                "transforms": self.dataset.transforms.get_all_transforms(),
                "preprocessing_class": self.dataset.processing_class.module_cls_name()}

    #def save_meta(self):
    #    from ml.ds import save_metadata
    #    if self.check_point_path is not None:
    #        path = self.make_model_file()
    #        save_metadata(path+".xmeta", self._metadata())

    #def load_meta(self):
    #    from ml.ds import load_metadata
    #    if self.check_point_path is not None:
    #        path = self.make_model_file(check=False)
    #        return load_metadata(path+".xmeta")
        
    def get_dataset(self):
        from ml.ds import DataSetBuilder
        meta = self.load_meta()
        dataset = DataSetBuilder.load_dataset(
            meta["dataset_name"],
            dataset_path=meta["dataset_path"],
            info=self.print_info)
        if meta.get('md5', None) != dataset.md5():
            log.warning("The dataset md5 is not equal to the model '{}'".format(
                self.__class__.__name__))
        elif meta.get('transforms', None) != dataset.transforms.get_all_transforms():
            log.warning(
                "The filters in the dataset are distinct to training model '{}'".format(self.__class__.__name__))
        return dataset


class SKL(BaseClassif):
    def convert_label(self, label, raw=False):
        if raw is True:
            return (np.arange(self.num_labels) == label).astype(np.float32)
        else:
            return self.le.inverse_transform(self.position_index(label))

    def train(self, batch_size=0, num_steps=0):
        self.prepare_model()
        self.save_model()

    def save_model(self):
        from sklearn.externals import joblib
        if self.check_point_path is not None:
            path = self.make_model_file()
            joblib.dump(self.model, '{}.pkl'.format(path))
            self.save_meta()

    def load_model(self):
        from sklearn.externals import joblib
        if self.check_point_path is not None:
            path = self.make_model_file(check=False)
            self.model = joblib.load('{}.pkl'.format(path))

    def _predict(self, data, raw=False):
        for prediction in self.model.predict(data):
            yield self.convert_label(prediction, raw=raw)


class SKLP(SKL):
    def __init__(self, *args, **kwargs):
        super(SKLP, self).__init__(*args, **kwargs)

    def convert_label(self, label, raw=False):
        if raw is True:
            return label
        else:
            return self.le.inverse_transform(self.position_index(label))

    def _predict(self, data, raw=False):
        for prediction in self.model.predict_proba(data):
            yield self.convert_label(prediction, raw=raw)


class TFL(BaseClassif):
    def __init__(self, **kwargs):
        super(TFL, self).__init__(**kwargs)

    def reformat(self, data, labels):
        data = self.transform_shape(data)
        # Map 0 to [1.0, 0.0, 0.0 ...], 1 to [0.0, 1.0, 0.0 ...]
        labels_m = (np.arange(self.num_labels) == labels[:,None]).astype(np.float32)
        return data, labels_m

    def save_model(self):
        if self.check_point_path is not None:
            path = self.make_model_file()
            self.model.save('{}.ckpt'.format(path))
            self.save_meta()

    def load_model(self):
        import tflearn
        self.prepare_model()
        if self.check_point_path is not None:
            path = self.make_model_file()
            self.model.load('{}.ckpt'.format(path))

    def predict(self, data, raw=False, transform=True, chunk_size=1):
        with tf.Graph().as_default():
            return super(TFL, self).predict(data, raw=raw, transform=transform, chunk_size=chunk_size)

    def _predict(self, data, raw=False):
        for prediction in self.model.predict(data):
            yield self.convert_label(np.asarray(prediction), raw=raw)

