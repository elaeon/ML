import sys
sys.path.append("/home/alejandro/Programas/ML")

import argparse
import ml

from utils.config import get_settings

settings = get_settings("ml")
settings.update(get_settings("numbers"))

if __name__ == '__main__':
    IMAGE_SIZE = int(settings["image_size"])
    transforms = [
            ("rgb2gray", None),
            ("cut", None), 
            ("resize", (settings["image_size"], 'asym')), 
            ("threshold", 91), 
            ("merge_offset", (IMAGE_SIZE, 1))]

    parser = argparse.ArgumentParser()
    parser.add_argument("--build", help="crea el dataset", action="store_true")
    parser.add_argument("--dataset", help="nombre del dataset a utilizar", type=str)
    parser.add_argument("--test", 
        help="evalua el predictor en base a los datos de prueba", 
        action="store_true")
    parser.add_argument("--train", help="inicia el entrenamiento", action="store_true")
    parser.add_argument("--epoch", type=int)
    args = parser.parse_args()

    if args.build:
        ds_builder = ml.ds.DataSetBuilderImage(
            settings["dataset_name"], 
            image_size=int(settings["image_size"]), 
            dataset_path=settings["dataset_path"], 
            train_folder_path=settings["train_folder_path"],
            transforms=transforms,
            transforms_apply=False)
        ds_builder.build_dataset()
    elif args.train:
        dataset = ml.ds.DataSetBuilder.load_dataset(
            settings["dataset_name"], 
            dataset_path=settings["dataset_path"])
        classif = ml.clf_e.SVC(dataset, check_point_path=settings["checkpoints_path"], pprint=False)
        classif.batch_size = 100
        classif.train(num_steps=args.epoch)
    elif args.test:
        pass