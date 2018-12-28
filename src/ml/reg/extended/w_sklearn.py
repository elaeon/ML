from ml.reg.wrappers import SKLP
from sklearn.ensemble import RandomForestRegressor as SkRandomForestReg
from sklearn.ensemble import GradientBoostingRegressor as SkGradientBoostingReg


class RandomForestRegressor(SKLP):
    def prepare_model(self, obj_fn=None, num_steps=0, model_params=None):
        model = SkRandomForestReg(**model_params)
        with self.ds:
            reg_model = model.fit(self.ds[self.data_groups["data_train_group"]].to_ndarray(),
                                  self.ds[self.data_groups["target_train_group"]].to_ndarray())
        return self.ml_model(reg_model)

    def feature_importance(self):
        import pandas as pd
        with self.ds:
            df = pd.DataFrame({'importance': self.model.model.feature_importances_, 
                'feature': self.ds.groups}).sort_values(
                by=['importance'], ascending=False)
        return df
    

class GradientBoostingRegressor(SKLP):
    def prepare_model(self, obj_fn=None, num_steps=0, model_params=None):
        model = SkGradientBoostingReg(**model_params)
        with self.ds:
            reg_model = model.fit(self.ds[self.data_groups["data_train_group"]].to_ndarray(),
                                  self.ds[self.data_groups["target_train_group"]].to_ndarray())
        return self.ml_model(reg_model)
