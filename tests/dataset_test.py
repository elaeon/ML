import unittest
import ml
import numpy as np
import csv


class TestDataset(unittest.TestCase):
    def setUp(self):
        NUM_FEATURES = 10
        self.X = np.append(np.zeros((5, NUM_FEATURES)), np.ones((5, NUM_FEATURES)), axis=0)
        self.Y = (np.sum(self.X, axis=1) / 10).astype(int)
        self.dataset = ml.ds.DataSetBuilder(
            "test",
            dataset_path="/tmp/", 
            transforms=[('scale', None)],
            train_size=.5,
            valid_size=.2,
            validator="cross",
            print_info=False)
        self.dataset.build_dataset(self.X, self.Y)

    def test_build_dataset_dim_7_1_2(self):
        dataset = ml.ds.DataSetBuilder(
            "test",
            dataset_path="/tmp/", 
            transforms=[('scale', None)],
            validator="cross",
            print_info=False)
        dataset.build_dataset(self.X, self.Y)
        self.assertEqual(dataset.train_labels.shape, (7,))
        self.assertEqual(dataset.valid_labels.shape, (1,))
        self.assertEqual(dataset.test_labels.shape, (2,))

    def test_build_dataset_dim_5_2_3(self):
        self.assertEqual(self.dataset.train_labels.shape, (5,))
        self.assertEqual(self.dataset.valid_labels.shape, (2,))
        self.assertEqual(self.dataset.test_labels.shape, (3,))

    def test_only_labels(self):
        dataset0, label0 = self.dataset.only_labels([0])
        self.assertTrue((dataset0 == (np.ones((5, 10))*-1)).all())
        self.assertItemsEqual(label0, np.zeros(5))
        dataset1, label1 = self.dataset.only_labels([1])
        self.assertTrue((dataset1 == np.ones((5, 10))).all())
        self.assertItemsEqual(label1, np.ones(5))

    def test_labels_info(self):
        labels_counter = self.dataset.labels_info()
        self.assertEqual(labels_counter[0], 5)
        self.assertEqual(labels_counter[1], 5)

    def test_density(self):
        self.assertEqual(self.dataset.density(), 1)
        self.assertEqual(self.dataset.density(axis=1), 1)


class TestDatasetFile(unittest.TestCase):
    def setUp(self):
        NUM_FEATURES = 10
        self.X = np.append(np.zeros((5, NUM_FEATURES)), np.ones((5, NUM_FEATURES)), axis=0)
        self.Y = (np.sum(self.X, axis=1) / 10).astype(int)
        dataset = np.c_[self.X, self.Y]
        with open('test.csv', 'wb') as csvfile:
            csv_writer = csv.writer(csvfile, delimiter=',', quoting=csv.QUOTE_MINIMAL)
            csv_writer.writerow(map(str, range(10)) + ['target']) 
            for row in dataset:
                csv_writer.writerow(row)

    def test_load(self):
        dataset = ml.ds.DataSetBuilderFile(
            "test",
            dataset_path="/tmp/", 
            transforms=[('scale', None)],
            validator="cross")
        data, labels = dataset.from_csv('test.csv', 'target')
        self.assertItemsEqual(self.Y, labels.astype(int))


if __name__ == '__main__':
    unittest.main()
