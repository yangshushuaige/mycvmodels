# coding=utf-8

import pdb
import time
import torch
import sys
from tqdm import tqdm
from models import SalModel
from datasets import Folder
from evaluate_sal import fm_and_mae
import json
import os


from options.train_options import TrainOptions
opt = TrainOptions().parse()  # set CUDA_VISIBLE_DEVICES before import torch

home = os.path.expanduser("~")

train_img_dir = '%s/data/datasets/saliency_Dataset/DUT-train/images'%home
train_gt_dir = '%s/data/datasets/saliency_Dataset/DUT-train/masks'%home

val_img_dir = '%s/data/datasets/saliency_Dataset/ECSSD/images'%home
val_gt_dir = '%s/data/datasets/saliency_Dataset/ECSSD/masks'%home


train_loader = torch.utils.data.DataLoader(
    Folder(train_img_dir, train_gt_dir,
           crop=0.9, flip=True, rotate=None, size=opt.imageSize,
           mean=opt.mean, std=opt.std, training=True),
    batch_size=opt.batchSize, shuffle=True, num_workers=4, pin_memory=True)

val_loader = torch.utils.data.DataLoader(
    Folder(val_img_dir, val_gt_dir,
           crop=None, flip=False, rotate=None, size=opt.imageSize,
           mean=opt.mean, std=opt.std, training=False),
    batch_size=opt.batchSize, shuffle=True, num_workers=4, pin_memory=True)


def test(model):
    print("============================= TEST ============================")
    model.switch_to_eval()
    for i, (img, name, WW, HH) in tqdm(enumerate(val_loader), desc='testing'):
        model.test(img, name, WW, HH)
    model.switch_to_train()
    maxfm, mae, _, _ = fm_and_mae(opt.results_dir, val_gt_dir)
    model.performance = {'maxfm': maxfm, 'mae': mae}
    return maxfm, mae


model = SalModel(opt)


def train(model):
    print("============================= TRAIN ============================")
    model.switch_to_train()

    train_iter = iter(train_loader)
    it = 0
    log = {'best': 0, 'best_it': 0}

    for i in tqdm(range(opt.train_iters), desc='train'):
        # landscape
        if it >= len(train_loader):
            train_iter = iter(train_loader)
            it = 0
        img, gt = train_iter.next()
        it += 1

        model.set_input(img, gt)
        model.optimize_parameters()

        if i % opt.display_freq == 0:
            model.show_tensorboard(i)

        if i != 0 and i % opt.save_latest_freq == 0:
            model.save(i)
            maxfm, mae = test(model)
            model.show_tensorboard_eval(i)
            log[i] = {'maxfm': maxfm, 'mae': mae}
            if maxfm > log['best']:
                log['best'] = maxfm
                log['best_it'] = i
                model.save('best')
            print(u'最大fm: %.4f, 这次fm: %.4f'%(log['best'], maxfm))
            with open(model.save_dir+'/'+'train-log.json', 'w') as outfile:
                json.dump(log, outfile)


train(model)

print("We are done")
