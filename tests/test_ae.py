import unittest
import numpy as np
from ml.data.ds import Data
from ml.data.drivers import HDF5
from ml.utils.numeric_functions import CV
from ml.ae.extended.w_keras import PTsne
from ml.models import Metadata
from ml.utils.tf_functions import TSNe
from ml.data.it import Iterator


def to_data(cv, driver=None):
    x_train, x_validation, x_test = cv
    x_train.rename_group("x", "train_x")
    x_test.rename_group("x", "test_x")
    x_validation.rename_group("x", "validation_x")
    stc = x_train + x_test + x_validation
    cv_ds = Data(name="cv", driver=driver, clean=True)
    cv_ds.from_data(stc)
    return cv_ds


class TestUnsupervicedModel(unittest.TestCase):
    def train(self, ae, model_params=None):
        np.random.seed(0)
        x = np.random.rand(100)
        x = np.sin(6 * x).reshape(-1, 1)
        dataset = Data(name="tsne", dataset_path="/tmp", driver=HDF5(), clean=True)
        tsne = TSNe(batch_size=10, perplexity=ae.perplexity, dim=2)
        x_p = Iterator(tsne.calculate_P(x), length=len(x), dtypes=[("x", np.dtype(float)), ("y", np.dtype(float))])
        dataset.from_data(x_p, batch_size=0)

        cv = CV(group_data="x", train_size=.7, valid_size=.1)
        with dataset:
            stc = cv.apply(dataset)
            ds = to_data(stc, driver=HDF5())
            ae.train(ds, num_steps=2, data_train_group="train_x", batch_size=10, data_test_group="test_x",
                     model_params=model_params, data_validation_group="validation_x")
            ae.save("test", path="/tmp/", model_version="1")
        dataset.destroy()
        return ae

    def test_parametric_tsne(self):
        ae = self.train(PTsne(), model_params=None)
        #self.assertEqual(len(clf.scores2table().measures[0]), 7)
        metadata = Metadata.get_metadata(ae.path_metadata, ae.path_metadata_version)
        print(metadata)
        #self.assertEqual(len(metadata["train"]["model_json"]) > 0, True)
        #clf.destroy()
        #classif = PTsne(model_name="tsne",
        #    check_point_path="/tmp/", latent_dim=2)
        #classif.set_dataset(dataset)
        #classif.train(batch_size=8, num_steps=2)
        #classif.save(model_version="1")

        #classif = PTsne(model_name="tsne", check_point_path="/tmp/")
        #classif.load(model_version="1")
        #self.assertEqual(classif.predict(X[:1]).shape, (None, 2))
        ae.destroy()


class TestAE(unittest.TestCase):
    def setUp(self):
        pass
        
    def tearDown(self):
        pass

    def test_vae(self):
        from ml.ae.extended.w_keras import VAE

        X = np.random.rand(1000, 10)
        X = (X * 10) % 2
        X = X.astype(int)
        dataset = Data(name="test", dataset_path="/tmp/", clean=True)
        with dataset:
            dataset.from_data(X)

        vae = VAE( 
            model_name="test", 
            check_point_path="/tmp/",
            intermediate_dim=5)
        vae.set_dataset(dataset)
        vae.train(batch_size=1, num_steps=10)
        vae.save(model_version="1")

        vae = VAE( 
            model_name="test",
            check_point_path="/tmp/")
        vae.load(model_version="1")
        encoder = vae.encode(X[0:1], chunks_size=10)
        decoder = vae.predict(X[0:1], chunks_size=10)
        self.assertEqual(encoder.shape, (None, 2))
        self.assertEqual(decoder.shape, (None, 10))
        dataset.destroy()
        vae.destroy()

    def test_dae(self):
        from ml.ae.extended.w_keras import SAE
        X = np.random.rand(1000, 10)
        X = (X * 10) % 2
        X = X.astype(int)
        dataset = Data(name="test", dataset_path="/tmp/", clean=True)
        with dataset:
            dataset.from_data(X)

        dae = SAE( 
            model_name="test", 
            check_point_path="/tmp/",
            latent_dim=5)
        dae.set_dataset(dataset)
        dae.train(batch_size=1, num_steps=10, num_epochs=3)
        dae.save(model_version="1")

        dae = SAE( 
            model_name="test", 
            check_point_path="/tmp/")
        dae.load(model_version="1")
        encoder = dae.encode(X[0:1], chunks_size=10)
        self.assertEqual(encoder.shape, (None, 5))
        decoder = dae.predict(X[0:1], chunks_size=10)
        self.assertEqual(decoder.shape, (None, 10))
        dataset.destroy()
        dae.destroy()


if __name__ == '__main__':
    unittest.main()
