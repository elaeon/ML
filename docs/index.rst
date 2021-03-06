
.. image:: https://travis-ci.org/elaeon/dama_ml.svg?branch=master
    :target: https://travis-ci.org/elaeon/dama_ml

.. image:: https://api.codacy.com/project/badge/Grade/0ab998e72f4f4e31b3dc7b3c9921374a
    :target: https://www.codacy.com/app/elaeon/dama_ml?utm_source=github.com&amp;utm_medium=referral&amp;utm_content=elaeon/dama_ml&amp;utm_campaign=Badge_Grade


Overview
=====================================

Dama ML is a framework for data management and is used to do data science and machine learning's pipelines, also dama-ml try to unify diverse data sources like csv, sql db, hdf5, zarr, etc, and also unify machine learning frameworks (sklearn, Keras, LigthGBM, etc) with a simplify interface.

For more detail read the docs_.

.. _docs: https://elaeon.github.io/dama_ml/


Warning
---------------
    Although, the API is stable this work is in alpha steps and there are methods that have limited functionality or aren't implemented.


Installation
=====================

.. code-block:: bash

    git clone https://github.com/elaeon/dama_ml.git
    pip install dama_ml/

or

.. code-block:: bash

    pip install DaMa-ML


You can install the python dependences with pip, but we strongly recommend install the dependences with conda and conda forge.

.. code-block:: bash

    conda config --add channels conda-forge
    conda create -n new_environment --file dama_ml/requirements.txt
    conda activate new_environment
    pip install DaMa-ML


Quick start
==================

Configure the data paths where all data will be saved. This can be done with help of dama_ml cli tools.

.. code-block:: python

    $ dama-cli config --edit

This will display a nano editor where you can edit data_path, models_path, code_path, class_path and metadata_path.

* data_path is where all datasets are saved.
* models_path is where all files from your models are saved.
* code_path is the repository of code. (In development)
* metadata_path is where the metadata database is saved.

Building a dataset

.. code-block:: python

    from dama.data.ds import Data
    from dama.drivers.core import Zarr, HDF5
    import numpy as np

    array_0 = np.random.rand(100, 1)
    array_1 = np.random.rand(100,)
    array_2 = np.random.rand(100, 3)
    array_3 = np.random.rand(100, 6)
    array_4 = (np.random.rand(100)*100).astype(int)
    array_5 = np.random.rand(100).astype(str)
    with Data(name=name, driver=Zarr(mode="w")) as data:
        data.from_data({"x": array_0, "y": array_1, "z": array_2, "a": array_3, "b": array_4, "c": array_5})


We can use a regression model, in this case we use RandomForestRegressor

.. code-block:: python

    from dama.reg.extended.w_sklearn import RandomForestRegressor
    from dama.utils.model_selection import CV

    data.driver.mode = "r"  # we changed mode "w" to "r" to not overwrite the data previously saved
    with data, Data(name="test_from_hash", driver=HDF5(mode="w")) as ds:
        cv = CV(group_data="x", group_target="y", train_size=.7, valid_size=.1)  # cross validation class
        stc = cv.apply(data)
        ds.from_data(stc, from_ds_hash=data.hash)
        reg = RandomForestRegressor()
        model_params = dict(n_estimators=25, min_samples_split=2)
        reg.train(ds, num_steps=1, data_train_group="train_x", target_train_group='train_y',
                  data_test_group="test_x", target_test_group='test_y', model_params=model_params,
                  data_validation_group="validation_x", target_validation_group="validation_y")
        reg.save(name="test_model", model_version="1")

Using RandomForestRegressor to do predictions is like this:

.. code-block:: python

    with RandomForestRegressor.load(model_name="test_model", model_version="1") as reg:
        for pred in reg.predict(data):
            prediction = pred.batch.to_ndarray()


CLI
==============
dama-ml has a CLI where you can view your datasets and models.
For example

.. code-block:: bash

    dama-cli datasets

Return a table of datasets previously saved.

.. code-block:: bash

    Using metadata ..../metadata/metadata.sqlite3
    Total 2 / 2

    hash                    name            driver    group name    size       num groups  datetime UTC
    ---------------------  --------------  --------  ------------  --------  ------------  -------------------
    sha1.3124d5f16eb0e...  test_from_hash  HDF5      s/n           9.12 KB              6  2019-02-27 19:39:00
    sha1.e832f56e33491...  reg0            Zarr      s/n           23.68 KB             6  2019-02-27 19:39:00


.. code-block:: bash

    dama-cli models

.. code-block:: bash

    Total 3 / 3
    from_ds                       name      group_name    model                                                version     score name        score
    -------------------------  ----------  ------------  -------------------------------------------------  ---------  ---------------  ----------
    sha1.d8ff5a342d2d7229...  test_model  s/n           dama.reg.extended.w_sklearn.RandomForestRegressor          1  mse               0.162365
    sha1.d8ff5a342d2d7229...  test_model  s/n           dama.reg.extended.w_sklearn.RandomForestRegressor          1  msle              0.0741331
    sha1.d8ff5a342d2d7229...  test_model  s/n           dama.reg.extended.w_sklearn.RandomForestRegressor          1  gini_normalized  -0.307407


You can use "--help" for view more options.



Index
================

.. toctree::
   :maxdepth: 2
   :name: mastertoc

   datasets
   iterators


Support
=======
If you find bugs then `let me know`_ .

.. _let me know: https://github.com/elaeon/dama_ml/issues


Indices and tables
==================
 
* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
