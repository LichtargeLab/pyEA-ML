#!/usr/bin/env python3
"""
Created on 2019-04-17

@author: dillonshapiro
"""
import signal
import sys
from collections import defaultdict
from functools import partial
from multiprocessing import Pool

import numpy as np
from sklearn.model_selection import StratifiedKFold
import weka.core.jvm as jvm
from weka.classifiers import Classifier, Evaluation
from weka.core.dataset import Attribute
from weka.core.converters import ndarray_to_instances, save_any_file


def _init_worker():
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def _weka_worker(chunk, clf_dict, folds, hyps):
    """Worker process for Weka experiments"""
    matrix, gene_list = chunk
    jvm.start(bundled=False)
    result_d = {}
    for gene in gene_list:
        sub_matrix = matrix.get_genes([gene], hyps=hyps)
        col_names = sub_matrix.feature_labels
        result_d[gene] = defaultdict(list)
        for i, (train, test) in enumerate(folds):
            train_X = sub_matrix.X[train, :]
            train_y = sub_matrix.y[train]
            test_X = sub_matrix.X[test, :]
            test_y = sub_matrix.y[test]

            train_arff = convert_array(train_X, train_y, gene, col_names)
            test_arff = convert_array(test_X, test_y, gene, col_names)
            train_arff.class_is_last()
            test_arff.class_is_last()

            for clf_str, opts in clf_dict.items():
                clf = Classifier(classname=clf_str, options=opts)
                clf.build_classifier(train_arff)
                evl = Evaluation(train_arff)
                _ = evl.test_model(clf, test_arff)
                mcc = evl.matthews_correlation_coefficient(1)
                if np.isnan(mcc):
                    mcc = 0
                result_d[gene][clf_str].append(mcc)
    jvm.stop()
    return result_d


def convert_array(X, y, gene, col_names):
    arff = ndarray_to_instances(X, gene,
                                att_list=col_names)
    labels = [str(y) for y in y]
    cls_attr = Attribute.create_nominal('class', ['0', '1'])
    cls_attr_pos = len(col_names)
    arff.insert_attribute(cls_attr, cls_attr_pos)
    for i, label in enumerate(labels):
        # check for weird DenseInstance calling issue
        try:
            inst = arff.get_instance(i)
            inst.set_string_value(cls_attr_pos, label)
        except TypeError as e:
            save_any_file(arff, 'error_matrix.arff')
            raise e
    return arff


def run_weka(design_matrix, test_genes, n_workers, clf_dict,
             hyps=None, seed=111):
    """
    The overall Weka experiment. The steps include loading the K .arff files
    for each gene, building a new classifier based on the training set, then
    evaluating the model on the test set and outputting the MCC to a
    dictionary.
    """
    gene_result_d = {}
    jvm.add_bundled_jars()
    # split genes into chunks by number of workers
    gene_splits = np.array_split(np.array(test_genes), n_workers)
    # split DesignMatrix by each chunk of genes
    data_splits = [design_matrix.get_genes(split, hyps=hyps)
                   for split in gene_splits]
    chunks = list(zip(data_splits, gene_splits))
    kf = StratifiedKFold(n_splits=10, shuffle=True, random_state=seed)
    splits = list(kf.split(design_matrix.X, design_matrix.y))
    pool = Pool(n_workers, _init_worker, maxtasksperchild=1)
    worker = partial(_weka_worker, clf_dict=clf_dict, folds=splits, hyps=hyps)
    try:
        results = pool.map(worker, chunks)
        pool.close()
        pool.join()
        for result in results:
            gene_result_d.update(result)
    except KeyboardInterrupt:
        print('Caught KeyboardInterrupt, terminating workers')
        pool.terminate()
        pool.join()
        sys.exit(1)
    return gene_result_d
