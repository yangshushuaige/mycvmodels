import torch
import torch.nn as nn
from torch.autograd.variable import Variable

# from .densenet import *
# from .resnet import *
# from .vgg import *

from densenet import *
from resnet import *
from vgg import *

import numpy as np
import sys
thismodule = sys.modules[__name__]
import pdb

dim_dict = {
    'densenet169': [64, 128, 256, 640, 1664],
}


def get_upsampling_weight(in_channels, out_channels, kernel_size):
    """Make a 2D bilinear kernel suitable for upsampling"""
    factor = (kernel_size + 1) // 2
    if kernel_size % 2 == 1:
        center = factor - 1
    else:
        center = factor - 0.5
    og = np.ogrid[:kernel_size, :kernel_size]
    filt = (1 - abs(og[0] - center) / factor) * \
           (1 - abs(og[1] - center) / factor)
    weight = np.zeros((in_channels, out_channels, kernel_size, kernel_size),
                      dtype=np.float64)
    weight[range(in_channels), range(out_channels), :, :] = filt
    return torch.from_numpy(weight).float()

def proc_densenet(model):
    def hook(module, input, output):
        model.feats[output.device.index] += [output]
    model.features.transition3[-2].register_forward_hook(hook)
    model.features.transition2[-2].register_forward_hook(hook)
    model.features.transition1[-2].register_forward_hook(hook)
    model.features.block0[-2].register_forward_hook(hook)
    return model


procs = {'densenet169': proc_densenet}


class UNet(nn.Module):
    def __init__(self, pretrained=True, c_output=21, base='densenet169'):
        super(UNet, self).__init__()
        dims = dim_dict[base][::-1]
        self.upscales = nn.ModuleList([nn.ConvTranspose2d(ic, oc, 2, 2)
                                       for ic, oc in zip(dims[:-1], dims[1:])])
        self.reduce_convs = nn.ModuleList([nn.Conv2d(2*oc, oc, 3, 1, 1)
                                           for oc in dims[1:]])
        self.output_convs = nn.Sequential(nn.Conv2d(dims[-1], c_output, 1, 1),
                                          nn.ConvTranspose2d(c_output, c_output, 4, 2, 1))
        for m in self.modules():
            if isinstance(m, nn.Conv2d) or isinstance(m, nn.Linear) or isinstance(m, nn.Linear):
                m.weight.data.normal_(0.0, 0.01)
                m.bias.data.fill_(0)

        for m in self.output_convs.modules():
            if isinstance(m, nn.ConvTranspose2d):
                assert m.kernel_size[0] == m.kernel_size[1]
                initial_weight = get_upsampling_weight(
                    m.in_channels, m.out_channels, m.kernel_size[0])
                m.weight.data.copy_(initial_weight)

        self.feature = getattr(thismodule, base)(pretrained=pretrained)
        self.feature.feats = {}
        self.feature = procs[base](self.feature)
        for m in self.feature.modules():
            if isinstance(m, nn.BatchNorm2d):
                m.requires_grad=False

    def forward(self, x, boxes=None, ids=None):
        self.feature.feats[x.device.index] = []
        x = self.feature(x)
        feats = self.feature.feats[x.device.index]
        feats = feats[::-1]

        for i, feat in enumerate(feats):
            x = self.upscales[i](x)
            x = torch.cat((feats[i], x), 1)
            x = self.reduce_convs[i](x)
        pred = self.output_convs(x)
        return pred


if __name__ == "__main__":
    fcn = WSFCN2(base='densenet169').cuda()
    x = torch.Tensor(2, 3, 256, 256).cuda()
    sb = fcn(Variable(x))
