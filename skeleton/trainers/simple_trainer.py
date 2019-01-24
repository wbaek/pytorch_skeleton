# -*- coding: utf-8 -*-
from __future__ import absolute_import
import logging

from tqdm import tqdm
import numpy as np
import torch


LOGGER = logging.getLogger(__name__)


class SimpleTrainer:
    def __init__(self, module, optimizer, metric_fns=None):
        self.module = module
        self.optimizer = optimizer

        self.metric_fns = metric_fns if metric_fns is not None else {}

        self.global_step = 0
        self.global_epoch = 0

    def warmup(self, inputs, targets):
        self.module.train()
        logits, loss = self.module(inputs, targets)
        loss.backward()
        self.module.zero_grad()
        torch.cuda.synchronize()

    def forward(self, inputs, targets):
        logits, loss = self.module(inputs, targets)

        metrics = {name: m(logits, targets) for name, m in self.metric_fns.items()} if self.metric_fns is not None else {}
        metrics['loss'] = loss
        return logits, metrics

    def step(self, inputs, targets):
        self.module.zero_grad()

        logits, metrics = self.forward(inputs, targets)
        metrics['loss'].backward()

        self.optimizer.step()
        self.global_step += 1
        return logits, metrics

    def epoch(self, loader, is_training=True, desc='', verbose=False):
        steps = len(loader)
        desc = desc if desc else '[%s] [epoch:%04d]' % ('train' if is_training else 'valid', self.global_epoch)

        generator = enumerate(loader)
        if verbose:
            generator = tqdm(generator, total=steps, desc=desc)

        metric_hist = []
        with torch.set_grad_enabled(is_training):
            _ = self.module.train() if is_training else self.module.eval()
            f = self.step if is_training else self.forward

            for batch_idx, (inputs, targets) in generator:
                logits, metrics = f(inputs, targets)

                metrics = {key: float(value) for key, value in metrics.items()}
                metric_hist.append(metrics)
                if verbose:
                    generator.set_postfix(metrics)

            self.global_epoch += 1 if is_training else 0

        metric_avg = {metric: np.average([m[metric] for m in metric_hist]) for metric in metric_hist[0].keys()}
        metric_str = ['%s: %.4f' % (key, value) for key, value in metric_avg.items()]
        LOGGER.info('%s average %s', desc, ', '.join(metric_str))
        return metric_avg['loss']