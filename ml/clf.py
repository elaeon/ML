import os
import numpy as np
import tensorflow as tf

from sklearn.preprocessing import LabelEncoder

CHECK_POINT_PATH = "/home/sc/data/face_recog/"
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

    def logloss(self):
        from sklearn.metrics import log_loss
        return log_loss(self.labels, self.transform(self.predictions))


class UDMeasure(object):
    def __init__(self, predictions, labels):
        self.labels = labels
        self.predictions = predictions

    def logloss(self):
        from sklearn.metrics import log_loss
        return log_loss(self.labels, self.predictions)


class ListMeasure(object):
    def __init__(self):
        self.headers = []
        self.measures = []

    def add_measure(self, name, value):
        self.headers.append(name)
        self.measures.append(value)

    def dataset_test(self, classifs, dataset, order_column):
        from utils.order import order_table_print
        table = []
        print("DATASET", dataset.name)
        for classif_name in classifs:
            classif = classifs[classif_name]["name"]
            params = classifs[classif_name]["params"]
            clf = classif(dataset, **params)
            name_clf, measure = clf.detector_test_dataset(raw=self.logloss)
            if self.logloss:
                table.append((name_clf, measure.precision(), measure.recall(), 
                    measure.f1(), measure.logloss()))
            else:
                table.append((name_clf, measure.precision(), measure.recall(), measure.f1()))
        order_table_print(self.headers, table, order_column)

    def print_scores(self, order_column="f1"):
        from utils.order import order_table_print
        order_table_print(self.headers, [self.measures], order_column)


class BaseClassif(object):
    def __init__(self, dataset='test', check_point_path=CHECK_POINT_PATH, 
            pprint=True, model_version=None):
        self.model = None
        self.pprint = pprint
        self.le = LabelEncoder()
        self.load_dataset(dataset)
        self.check_point_path = check_point_path
        self.check_point = check_point_path + self.__class__.__name__ + "/"
        self.model_version = model_version
        self.has_uncertain = False

    def scores(self, order_column="f1"):
        list_measure = ListMeasure()
        predictions = self.predict(self.dataset.test_data, raw=False, transform=False)
        measure = Measure(np.asarray(list(predictions)), 
            np.asarray([self.convert_label(label, raw=False)
            for label in self.dataset.test_labels]))
        list_measure.add_measure("CLF", self.__class__.__name__)
        list_measure.add_measure("accuracy", measure.accuracy())
        list_measure.add_measure("precision", measure.precision())
        list_measure.add_measure("recall", measure.recall()) 
        list_measure.add_measure("f1", measure.f1())
        if self.has_uncertain:
            predictions = self.predict(self.dataset.test_data, raw=True, transform=False)
            udmeasure = UDMeasure(np.asarray(list(predictions)), self.dataset.test_labels)
            list_measure.add_measure("logloss", udmeasure.logloss())
        list_measure.print_scores(order_column=order_column)

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

    def transform_shape(self, data):
        return data.reshape(data.shape[0], -1).astype(np.float32)

    def labels_encode(self, labels):
        self.le.fit(labels)
        self.num_labels = self.le.classes_.shape[0]

    def position_index(self, label):
        if isinstance(label, np.ndarray):
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

        if self.pprint:
            print('RF-Training set', self.dataset.train_data.shape, self.dataset.train_labels.shape)
            if self.dataset.valid_data.shape[0] > 0:
                print('RF-Validation set', self.dataset.valid_data.shape,
                    self.dataset.valid_labels.shape)
            print('RF-Test set', self.dataset.test_data.shape, self.dataset.test_labels.shape)

    def load_dataset(self, dataset):
        self.dataset = dataset.copy()
        self.reformat_all()

    def predict(self, data, raw=False, transform=True):
        if self.model is None:
            self.load_model()

        if isinstance(data, list):
            data = np.asarray(data)

        if transform is True:
            ndata = [self.dataset.processing(datum, 'global') for datum in data]
            data = self.transform_shape(np.asarray(ndata))
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

    def retrain(self, dataset, batch_size=10, num_steps=1000):
        self.dataset = dataset
        self.reformat_all()
        self.train(batch_size=batch_size, num_steps=num_steps)

    def train2steps(self, dataset, valid_size=.1, batch_size=10, num_steps=1000, test_data_labels=None):
        self.train(batch_size=batch_size, num_steps=num_steps)
        dataset_v = self.rebuild_validation_from_errors(dataset, 
            valid_size=valid_size, test_data_labels=test_data_labels)
        self.retrain(dataset_v, batch_size=batch_size, num_steps=num_steps)

    def get_model_name(self):
        if self.model_version is None:
            import datetime
            id_ = datetime.datetime.today().strftime("%Y-%m-%d-%H:%M:%S")
        else:
            id_ = self.model_version
        return "{}.{}".format(self.dataset.name, id_)

    def make_model_file(self):
        model_name = self.get_model_name()
        if not os.path.exists(self.check_point):
            os.makedirs(self.check_point)

        if not os.path.exists(self.check_point + model_name + "/"):
            os.makedirs(self.check_point + model_name + "/")
            
        return "{}{}/{}".format(self.check_point, model_name, model_name)

class SKL(BaseClassif):
    def train(self, batch_size=0, num_steps=0):
        self.prepare_model()
        self.save_model()

    def save_model(self):
        from sklearn.externals import joblib
        path = self.make_model_file()
        joblib.dump(self.model, '{}.pkl'.format(path))

    def load_model(self):
        from sklearn.externals import joblib
        path = self.make_model_file()
        self.model = joblib.load('{}.pkl'.format(path))

    def _predict(self, data, raw=False):
        for prediction in self.model.predict(data):
            yield self.convert_label(prediction)


class SKLP(SKL):
    def __init__(self, *args, **kwargs):
        super(SKLP, self).__init__(*args, **kwargs) 
        self.has_uncertain = True

    def _predict(self, data, raw=False):
        for prediction in self.model.predict_proba(data):
            yield self.convert_label(prediction, raw=raw)


class TF(BaseClassif):
    #def position_index(self, label):
    #    return np.argmax(label)

    def reformat(self, data, labels):
        data = self.transform_shape(data)
        # Map 0 to [1.0, 0.0, 0.0 ...], 1 to [0.0, 1.0, 0.0 ...]
        labels_m = (np.arange(self.num_labels) == labels[:,None]).astype(np.float32)
        return data, labels_m

    def train(self, batch_size=10, num_steps=3001):
        self.prepare_model(batch_size)
        with tf.Session(graph=self.graph) as session:
            saver = tf.train.Saver()
            tf.initialize_all_variables().run()
            print "Initialized"
            for step in xrange(num_steps):
                # Pick an offset within the training data, which has been randomized.
                # Note: we could use better randomization across epochs.
                offset = (step * batch_size) % (self.dataset.train_labels.shape[0] - batch_size)
                # Generate a minibatch.
                batch_data = self.dataset.train_data[offset:(offset + batch_size), :]
                batch_labels = self.train_labels[offset:(offset + batch_size), :]
                # Prepare a dictionary telling the session where to feed the minibatch.
                # The key of the dictionary is the placeholder node of the graph to be fed,
                # and the value is the numpy array to feed to it.
                feed_dict = {self.tf_train_data : batch_data, self.tf_train_labels : batch_labels}
                _, l, predictions = session.run(
                [self.optimizer, self.loss, self.train_prediction], feed_dict=feed_dict)
                if (step % 500 == 0):
                    print "Minibatch loss at step", step, ":", l
                    print "Minibatch accuracy: %.1f%%" % (self.accuracy(predictions, batch_labels)*100)
                    print "Validation accuracy: %.1f%%" % (self.accuracy(
                      self.valid_prediction.eval(), self.dataset.valid_labels)*100)
            #score_v = self.accuracy(self.test_prediction.eval(), self.dataset.test_labels)
            self.save_model(saver, session, step)
            #return score_v

    def save_model(self, saver, session, step):
        path = self.make_model_file()
        saver.save(session, '{}.ckpt'.format(path), global_step=step)


class TFL(BaseClassif):
    #def position_index(self, label):
    #    return np.argmax(label)

    def reformat(self, data, labels):
        data = self.transform_shape(data)
        # Map 0 to [1.0, 0.0, 0.0 ...], 1 to [0.0, 1.0, 0.0 ...]
        labels_m = (np.arange(self.num_labels) == labels[:,None]).astype(np.float32)
        return data, labels_m

    def save_model(self):
        path = self.make_model_file()
        self.model.save('{}.ckpt'.format(path))

    def load_model(self):
        import tflearn
        self.prepare_model()
        self.model = tflearn.DNN(self.net, tensorboard_verbose=3)
        path = self.make_model_file()
        self.model.load('{}.ckpt'.format(path))

    def predict(self, data, raw=False, transform=True):
        with tf.Graph().as_default():
            if self.model is None:
                self.load_model()

            if isinstance(data, list):
                data = np.asarray(data)

            if transform is True:
                if len(data.shape) > 2:
                    data = data.reshape(data.shape[0], -1).astype(np.float32)
                data = self.transform_shape(self.dataset.processing(data, 'global'))

            return self._predict(data, raw=raw)

    def _predict(self, data, raw=False):
        for prediction in self.model.predict(data):
            yield self.convert_label(prediction, raw=raw)

