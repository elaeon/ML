import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

import ml
import argparse
from utils.config import get_settings
from utils.numeric_functions import le
from ml.processing import Preprocessing

settings = get_settings("ml")
settings.update(get_settings("numerai"))


def predict(classif, path, label_column):
    import pandas as pd
    import csv

    df = pd.read_csv(path)
    data = df.drop([label_column], axis=1).as_matrix()

    ids = df[label_column].as_matrix()
    predictions = []
    for value, label in zip(list(classif.predict(data, raw=True, chunk_size=258)), ids):
        predictions.append([str(label), str(value[1])])
    
    with open(settings["predictions_file_path"], "w") as csvfile:
        csvwriter = csv.writer(csvfile, delimiter=',', quoting=csv.QUOTE_MINIMAL)
        csvwriter.writerow(["t_id", "probability"])
        for row in predictions:
            csvwriter.writerow(row)


def merge_data_labels(file_path=None):
    df = ml.ds.DataSetBuilderFile.merge_data_labels(settings["numerai_test"], 
        settings["numerai_example"], "t_id")
    df.loc[df.probability >= .5, 'probability'] = 1
    df.loc[df.probability < .5, 'probability'] = 0
    df = df.drop(["t_id"], axis=1)
    df.rename(columns={'probability': 'target'}, inplace=True)
    if file_path is not None:
        df.to_csv(file_path, index=False)
    labels = df["target"].as_matrix()
    df = df.drop(["target"], axis=1)
    data = df.as_matrix()
    return data, labels


def build(dataset_name, transforms=None):
    dataset = ml.ds.DataSetBuilderFile(
        dataset_name, 
        dataset_path=settings["dataset_path"], 
        processing_class=Preprocessing,
        train_folder_path=settings["numerai_train"],
        transforms=transforms)
    dataset.build_dataset(label_column="target")
    return dataset


def build2(dataset_name, transforms=None):
    test_data, test_labels = merge_data_labels("/home/sc/test_data/t.csv")
    dataset = ml.ds.DataSetBuilderFile(
        dataset_name, 
        dataset_path=settings["dataset_path"], 
        processing_class=Preprocessing,
        train_folder_path=settings["numerai_train"],
        test_folder_path="/home/sc/test_data/t.csv",
        validator="adversarial",
        transforms=transforms)
    dataset.build_dataset(label_column="target")
    return dataset


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-name", help="nombre del dataset a utilizar", type=str)
    parser.add_argument("--build-dataset", help="crea el dataset", action="store_true")
    parser.add_argument("--train", help="inicia el entrenamiento", action="store_true")
    parser.add_argument("--epoch", type=int, default=1)
    parser.add_argument("--predict", help="inicia el entrenamiento", action="store_true")
    parser.add_argument("--model-version", type=str)
    parser.add_argument("--plot", action="store_true")
    args = parser.parse_args()


    if args.build_dataset:
        #dataset_t = {
        #    args.model_name+"-t1": 
        #    [("scale", None)],
        #    args.model_name+"-t2": 
        #    [("poly_features", {"degree": 2, "interaction_only": True, "include_bias": True}),
        #    ("scale", None)],
        #    args.model_name+"-t3":
        #    [("poly_features", {"degree": 2, "interaction_only": False, "include_bias": False}),
        #    ("scale", None)],
        #    args.model_name+"-t4":
        #    [("scale", None),
        #    ("tsne", {"perplexity": 50, "action": 'concatenate'})]
        #}
        transforms = [("scale", None)]
        dataset = build(args.model_name, transforms=transforms)

    if args.train:
        dataset = ml.ds.DataSetBuilderFile.load_dataset(
            args.model_name, dataset_path=settings["dataset_path"])
        #classif = ml.clf.generic.Boosting({"0": [
        #    ml.clf.extended.ExtraTrees,
        #    ml.clf.extended.MLP,
        #    ml.clf.extended.RandomForest,
        #    ml.clf.extended.SGDClassifier,
        #    ml.clf.extended.SVC,
        #    ml.clf.extended.LogisticRegression,
        #    ml.clf.extended.AdaBoost,
        #    ml.clf.extended.GradientBoost]},
        #    dataset=dataset,
        #    model_name=args.model_name,
        #    model_version=args.model_version,
        #    weights=[3, 1],
        #    election='best-c',
        #    num_max_clfs=5,
        #    check_point_path=settings["checkpoints_path"])
        #classif = ml.clf.generic.Stacking({"0": [
        #    ml.clf.extended.ExtraTrees,
        #    ml.clf.extended.MLP,
        #    ml.clf.extended.RandomForest,
        #    ml.clf.extended.SGDClassifier,
        #    ml.clf.extended.SVC,
        #    ml.clf.extended.LogisticRegression,
        #    ml.clf.extended.AdaBoost,
        #    ml.clf.extended.GradientBoost]},
        #    dataset=dataset,
        #    model_name=args.model_name,
        #    model_version=args.model_version,
        #    check_point_path=settings["checkpoints_path"])
        classif = ml.clf.generic.Bagging(ml.clf.extended.MLP, {"0": [
            ml.clf.extended.ExtraTrees,
            ml.clf.extended.MLP,
            ml.clf.extended.RandomForest,
            ml.clf.extended.SGDClassifier,
            ml.clf.extended.SVC,
            ml.clf.extended.LogisticRegression,
            ml.clf.extended.AdaBoost,
            ml.clf.extended.GradientBoost]},
            dataset=dataset,
            model_name=args.model_name,
            model_version=args.model_version,
            check_point_path=settings["checkpoints_path"])
        classif.train(batch_size=128, num_steps=args.epoch) # only_voting=True
        classif.all_clf_scores().print_scores(order_column="logloss")

    if args.predict:
        #classif = ml.clf.generic.Boosting({},
        #    model_name=args.model_name,
        #    model_version=args.model_version,
        #    check_point_path=settings["checkpoints_path"])
        #classif = ml.clf.generic.Stacking({},
        #    model_name=args.model_name,
        #    model_version=args.model_version,
        #    check_point_path=settings["checkpoints_path"])
        classif = ml.clf.generic.Bagging(None, {},
           model_name=args.model_name,
            model_version=args.model_version,
            check_point_path=settings["checkpoints_path"])
        classif.scores().print_scores(order_column="logloss")
        #predict(classif, settings["numerai_test"], "t_id")

    if args.plot:
        dataset = ml.ds.DataSetBuilderFile.load_dataset(
            args.model_name, dataset_path=settings["dataset_path"])
        print("DENSITY: ", dataset.density())
        dataset.plot()
