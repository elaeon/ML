import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

import ml
import argparse
from utils.config import get_settings
from ml.processing import Preprocessing
from operator import le, ge

settings = get_settings("ml")
settings.update(get_settings("numerai"))


def predict(classif, path, label_column):
    import pandas as pd
    import csv

    df = pd.read_csv(path)
    data = df.drop([label_column], axis=1).as_matrix()

    ids = df[label_column].as_matrix()
    predictions = []
    for value, label in zip(list(classif.predict(data, raw=True)), ids):
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
    parser.add_argument("--epoch", type=int)
    parser.add_argument("--predic", help="inicia el entrenamiento", action="store_true")
    parser.add_argument("--model-version", type=str)
    parser.add_argument("--transform", action="store_true")
    args = parser.parse_args()


    if args.build_dataset:
        transforms = None if args.transform else [("tsne", None), ("poly_features", None), ("scale", None)]
        dataset = build(args.model_name, transforms=transforms)
        #dataset = build2(args.model_name, transforms=transforms)

    if args.train:
        dataset = ml.ds.DataSetBuilderFile.load_dataset(
            args.model_name, dataset_path=settings["dataset_path"])
        classif = ml.clf.generic.Grid([
            ml.clf.extended.ExtraTrees,
            ml.clf.extended.MLP,
            ml.clf.extended.RandomForest,
            ml.clf.extended.SGDClassifier,
            ml.clf.extended.SVC,
            ml.clf.extended.LogisticRegression,
            ml.clf.extended.AdaBoost,
            ml.clf.extended.GradientBoost,
            #ml.clf.extended.LSTM,
            ml.clf.extended.Voting],
            dataset=dataset,
            model_version=args.model_version,
            check_point_path=settings["checkpoints_path"])
        #classif.add_params('LSTM', timesteps=7)
        classif.train(batch_size=128, num_steps=args.epoch)
        classif.scores().print_scores(order_column="f1")

    if args.predic:
        classif = ml.clf.generic.Grid([
            ml.clf.extended.ExtraTrees,
            ml.clf.extended.MLP,
            ml.clf.extended.RandomForest,
            ml.clf.extended.SGDClassifier,
            ml.clf.extended.SVC,
            ml.clf.extended.LogisticRegression,
            ml.clf.extended.AdaBoost,
            ml.clf.extended.GradientBoost,
            #ml.clf.extended.LSTM,
            ml.clf.extended.Voting],
            model_name=args.model_name,
            model_version=args.model_version,
            check_point_path=settings["checkpoints_path"])
        classif.confusion_matrix()
        classif.scores().print_scores(order_column="f1")
        classif_best = classif.best_predictor(measure_name="logloss", operator=le)
        print("BEST: {}".format(classif_best.cls_name_simple()))
        predict(classif_best, settings["numerai_test"], "t_id")
