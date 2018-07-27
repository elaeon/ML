from ml.reg.wrappers import XGB, SKLP
from ml.models import MLModel

from sklearn.calibration import CalibratedClassifierCV
import xgboost as xgb
import os
import numpy as np


class Xgboost(XGB):
    def convert_label(self, labels, output=None):
        if output is None:
            for chunk in labels:
                yield chunk
        elif output == 'n_dim':
            for chunk in labels:
                if len(chunk.shape) == 1:
                    label = chunk.reshape(-1, 1)
                    yield np.concatenate((np.abs(label - 1), label), axis=1)
                else:
                    yield chunk
        else:
            for chunk in labels:
                for label in self.position_index(chunk):
                    yield label

    def prepare_model(self, obj_fn=None, num_steps=None, **params):
        with self.train_ds, self.validation_ds:
            d_train = xgb.DMatrix(self.train_ds.data[:], self.train_ds.labels[:]) 
            d_valid = xgb.DMatrix(self.validation_ds.data[:], self.validation_ds.labels[:]) 
        watchlist = [(d_train, 'train'), (d_valid, 'valid')]
        nrounds = num_steps
        bst = xgb.train(params, d_train, nrounds, watchlist, early_stopping_rounds=nrounds/2, 
                          feval=obj_fn, maximize=True, verbose_eval=100)#, tree_method="hist")
        return self.ml_model(xgb, bst=bst)

    def feature_importance(self):
        #import pandas as pd
        #gain = self.bst.feature_importance('gain')
        #df = pd.DataFrame({'feature':self.bst.feature_name(), 
        #    'split':self.bst.feature_importance('split'), 
        #    'gain':100 * gain /gain.sum()}).sort_values('gain', ascending=False)
        #return df
        pass


class XgboostSKL(SKLP):
    def prepare_model(self, obj_fn=None, num_steps=None, **params):
        model = CalibratedClassifierCV(xgb.XGBClassifier(seed=3, n_estimators=25), method="sigmoid")
        with self.train_ds, self.validation_ds:
            model_clf = model.fit(self.train_ds.data, self.train_ds.labels)
            reg_model = CalibratedClassifierCV(model_clf, method="sigmoid", cv="prefit")
            reg_model.fit(self.validation_ds.data, self.validation_ds.labels)
        return self.ml_model(reg_model)

    def prepare_model_k(self, obj_fn=None, **params):
        model = CalibratedClassifierCV(xgb.XGBClassifier(seed=3, n_estimators=25), method="sigmoid")
        return self.ml_model(model)