#!/usr/bin/python

import json
import os
import pdb
import fastremap
import numpy as np
import tifffile
import torch
from matplotlib import pyplot as plt
import warnings
from typing import Union
from pathlib import Path
import rasterio.features
from rasterio.transform import Affine
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.cm import get_cmap
import colorcet as cc
import matplotlib as mpl
import os
import numpy as np
import matplotlib.pyplot as plt
import torch
import tifffile


def moving_average(x, w):
    """Moving average of an array x with window size w"""
    return np.convolve(x, np.ones(w), 'valid') / w


def plot_average(train, test, clip=99, window_size=10):
    fig = plt.figure(figsize=(10, 10))
    clip_val = np.percentile(test, [clip])
    test = np.clip(test, 0, clip_val[0])
    clip_val = np.percentile(train, [clip])
    train = np.clip(train, 0, clip_val[0])
    plt.plot(moving_average(test, window_size), label="test")
    plt.plot(moving_average(train, window_size), label="train")
    plt.legend()
    return fig


def _to_shape(a, shape):
    """Pad an array to a given shape."""
    a = _move_channel_axis(a)
    if len(np.shape(a)) == 2:
        a = a[None,]
    y_, x_ = shape
    y, x = a[0].shape
    y_pad = np.max([0, (y_ - y)])
    x_pad = np.max([0, (x_ - x)])
    return np.pad(a, ((0, 0), (y_pad // 2, y_pad // 2 + y_pad % 2),
                      (x_pad // 2, x_pad // 2 + x_pad % 2)),
                  mode='constant')


def labels_to_features(lab: np.ndarray, object_type='annotation', connectivity: int = 4,
                       transform: Affine = None, downsample: float = 1.0, include_labels=False,
                       classification=None, offset=None):
    """
    Create a GeoJSON FeatureCollection from a labeled image.
    """
    features = []

    # Ensure types are valid
    if lab.dtype == bool:
        mask = lab
        lab = lab.astype(np.uint8)
    else:
        mask = lab != 0

    # Create transform from downsample if needed
    if transform is None:
        transform = Affine.scale(downsample)

    # Trace geometries
    for i, obj in enumerate(rasterio.features.shapes(lab, mask=mask,
                                                     connectivity=connectivity, transform=transform)):

        # Create properties
        props = dict(object_type=object_type)
        if include_labels:
            props['measurements'] = [{'name': 'Label', 'value': i}]
        #  pdb.set_trace()

        # Just to show how a classification can be added
        if classification is not None:
            props['classification'] = str(classification)

        if offset is not None:
            coordinates = obj[0]['coordinates']
            coordinates = [
                [(int(x[0] + offset[0]), int(x[1] + offset[1])) for x in coordinates[0]]]
            obj[0]['coordinates'] = coordinates

        # Wrap in a dict to effectively create a GeoJSON Feature
        po = dict(type="Feature", geometry=obj[0], properties=props)

        features.append(po)

    return features


def interp(image: np.ndarray, shape=None, scale=None):
    """Interpolate an image to a new shape or scale."""
    from scipy import interpolate
    x = np.array(range(image.shape[1]))
    y = np.array(range(image.shape[0]))
    interpolate_fn = interpolate.interp2d(x, y, image)
    if shape:
        x_new = np.linspace(0, image.shape[1] - 1, shape[1])
        y_new = np.linspace(0, image.shape[0] - 1, shape[0])
    elif scale:
        x_new = np.linspace(0, image.shape[1] - 1, int(np.floor(image.shape[1] * scale) + 1))
        y_new = np.linspace(0, image.shape[0] - 1, int(np.floor(image.shape[0] * scale) + 1))
    znew = interpolate_fn(x_new, y_new)
    return znew



def apply_cmap(x, fg_mask = None, cmap = "coolwarm_r", bg_intensity = 255, normalize = True):
    """
    Apply a colormap to an image, with a background mask.
    x  and fg_mask should have the same shape, and be numpy arrays.

    """
    import matplotlib.cm as cm
    import matplotlib
    norm = matplotlib.colors.Normalize(vmin=1, vmax=10)

    if fg_mask is None:
        fg_mask = (x != 0).squeeze()
    x_clone = x.copy().astype(np.float32)
    x_clone = x_clone.squeeze()
    fg_clone = x_clone[fg_mask]
    cmap = matplotlib.colormaps.get_cmap(cmap)
    m = cm.ScalarMappable(cmap=cmap,norm = norm)

    rgba_image = m.to_rgba(fg_clone)
    canvas = np.zeros((x_clone.shape[0], x_clone.shape[1], 4)).astype(np.float32)
    canvas[fg_mask] = rgba_image
    canvas = (canvas[:, :, :3] * 255).astype(np.uint8)
    canvas[fg_mask == 0] = bg_intensity
    return canvas







def show_images(*img_list, clip_pct=None, titles=None, save_str=False, n_cols=3, axes=False, cmap="viridis",
                labels=None,
                dpi=None, timer_flag=None, colorbar=True, **args):
    """Designed to plot torch tensor and numpy arrays in windows robustly"""

    if labels is None:
        labels = []
    if titles is None:
        titles = []
    if dpi:
        mpl.rcParams['figure.dpi'] = dpi

    img_list = [img for img in img_list]
    if isinstance(img_list[0], list):
        img_list = img_list[0]

    rows = (len(img_list) - 1) // n_cols + 1
    columns = np.min([n_cols, len(img_list)])
    fig = plt.figure(figsize=(5 * (columns + 1), 5 * (rows + 1)))

    fig.tight_layout()
    grid = plt.GridSpec(rows, columns, figure=fig)
    grid.update(wspace=0.2, hspace=0, left=None, right=None, bottom=None, top=None)

    for i, img in enumerate(img_list):

        if torch.is_tensor(img):
            img = torch.squeeze(img).detach().cpu().numpy()
        img = np.squeeze(img)
        if len(img.shape) > 2:
            img = np.moveaxis(img, np.argmin(img.shape), -1)
            if img.shape[-1] > 4 or img.shape[-1] == 2:
                plt.close()
                show_images([img[..., i] for i in range(img.shape[-1])], clip_pct=clip_pct,
                            titles=["Channel:" + str(i) for i in range(img.shape[-1])], save_str=save_str,
                            n_cols=n_cols, axes=axes, cmap=cmap, colorbar=colorbar)
                continue
        ax1 = plt.subplot(grid[i])
        if not axes:
            plt.axis('off')
        if clip_pct is not None:
            print(np.percentile(img.ravel(), clip_pct), np.percentile(img.ravel(), 100 - clip_pct))
            im = ax1.imshow(img, vmin=np.percentile(img.ravel(), clip_pct),
                            vmax=np.percentile(img.ravel(), 100 - clip_pct))
        if i in labels:
            img = img.astype(int)
            img = fastremap.renumber(img)[0]
            n_instances = len(fastremap.unique(img))
            glasbey_cmap = cc.cm.glasbey_bw_minc_20_minl_30_r.colors
            glasbey_cmap[0] = [0, 0, 0]  # Set bg to black
            cmap_lab = LinearSegmentedColormap.from_list('my_list', glasbey_cmap, N=n_instances)
            im = ax1.imshow(img, cmap=cmap_lab, interpolation='nearest')
        else:
            im = ax1.imshow(img, cmap=cmap, **args)
        if colorbar:
            plt.colorbar(im, ax=ax1, fraction=0.046, pad=0.04)
        if i < len(titles):
            ax1.set_title(titles[i])
    if not save_str:
        # plt.tight_layout()

        if timer_flag is not None:
            plt.show(block=False)
            plt.pause(timer_flag)
            plt.close()

        plt.show()

    if save_str:
        plt.savefig(str(save_str) + ".png", bbox_inches='tight')
        plt.close()
        return None


def _scale_length(size: float, pixel_size: float, do_round=True) -> float:
    """
    Convert length in calibrated units to a length in pixels
    """
    size_pixels = size / pixel_size
    return np.round(size_pixels) if do_round else size_pixels


def _scale_area(size: float, pixel_size: float, do_round=True) -> float:
    """
    Convert area in calibrated units to an area in pixels
    """
    size_pixels = size / (pixel_size * pixel_size)
    return np.round(size_pixels) if do_round else size_pixels


def _move_channel_axis(img: Union[np.ndarray, torch.Tensor], to_back: bool = False):
    if isinstance(img, np.ndarray):
        if img.ndim != 3:
            if img.ndim == 2:
                img = img[None,]
            if img.ndim != 3:
                raise ValueError("Input array should be 3D or 2D")
        ch = np.argmin(img.shape)
        if to_back:
            return np.rollaxis(img, ch, 3)

        return np.rollaxis(img, ch, 0)
    elif isinstance(img, torch.Tensor):
        if img.dim() != 3:
            if img.dim() == 2:
                img = img[None,]
            if img.dim() != 3:
                raise ValueError("Input array should be 3D or 2D")
        ch = np.argmin(img.shape)
        if to_back:
            return img.movedim(ch, -1)
        return img.movedim(ch, 0)


def percentile_normalize(img: Union[np.ndarray, torch.Tensor], percentile=0.1, subsampling_factor: int = 1,
                         epsilon: float = 1e-3):
    if isinstance(img, np.ndarray):
        assert img.ndim == 2 or img.ndim == 3, "Image must be 2D or 3D, got image of shape" + str(img.shape)
        img = np.atleast_3d(img)
        channel_axis = np.argmin(img.shape)
        img = _move_channel_axis(img, to_back=True)

        for c in range(img.shape[-1]):
            im_temp = img[::subsampling_factor, ::subsampling_factor, c]
            (p_min, p_max) = np.percentile(im_temp, [percentile, 100 - percentile])
            img[:, :, c] = (img[:, :, c] - p_min) / max(epsilon, p_max - p_min)
       # img = img / np.maximum(0.01, np.max(img))
        return np.moveaxis(img, 2, channel_axis)

    elif isinstance(img, torch.Tensor):
        assert img.ndim == 2 or img.ndim == 3, "Image must be 2D or 3D, got image of shape" + str(img.shape)
        img = torch.atleast_3d(img)
        channel_axis = np.argmin(img.shape)
        img = _move_channel_axis(img, to_back=True)
        for c in range(img.shape[-1]):
            im_temp = img[::subsampling_factor, ::subsampling_factor, c]
            (p_min, p_max) = torch.quantile(im_temp, torch.tensor([percentile / 100, (100 - percentile) / 100],device = im_temp.device))
            img[:, :, c] = (img[:, :, c] - p_min) / max(epsilon, p_max - p_min)
       # img = img / np.maximum(0.01, torch.max(img))
        return img.movedim(2, channel_axis)


def generate_colors(num_colors: int):
    import colorsys
    # Calculate the equally spaced hue values
    hues = [i / float(num_colors) for i in range(num_colors)]

    # Generate RGB colors
    rgb_colors = [list(colorsys.hsv_to_rgb(hue, 1.0, 1.0)) for hue in hues]

    return rgb_colors


def tensor_or_np_copy(x):
    if isinstance(x, torch.Tensor):
        return x.clone()
    else:
        return x.copy()





def export_annotations_and_images(output_dir, original_image, lab, base_name=None):
    from pathlib import Path
    import os
    if os.path.isfile(output_dir):
        base_name = Path(output_dir).stem
        output_dir = Path(output_dir).parent
    else:
        if not os.path.exists(output_dir):
            os.mkdir(output_dir)
            if base_name is None:
                base_name = "image"

    image = np.atleast_3d(np.squeeze(np.array(original_image)))
    image = _move_channel_axis(image)

    if image.shape[0] == 3:

        features = labels_to_features(lab.astype(np.int32), object_type='annotation', include_labels=True,
                                      classification=None)
        geojson = json.dumps(features)
        with open(os.path.join(output_dir, str(base_name) + '_labels.geojson'), "w") as outfile:
            outfile.write(geojson)

        save_image_with_label_overlay(image, lab, output_dir=output_dir, label_boundary_mode='thick', alpha=0.8,
                                      base_name=base_name)

    else:
        warnings.warn("Did not attempt to save image of shape:")
        print(image.shape)


import matplotlib.colors as mcolors
def color_name_to_rgb(color_name):
    """
    Convert a color name to its corresponding RGB values.
    
    Args:
    color_name (str): The name of the color.
    
    Returns:
    tuple: A tuple containing the RGB values.
    """
    return mcolors.to_rgb(color_name)

#
def save_image_with_label_overlay(im: np.ndarray,
                                  lab: np.ndarray,
                                  output_dir: str = "./",
                                  base_name: str = 'image',
                                  clip_percentile: float = 1.0,
                                  scale_per_channel: bool = None,
                                  label_boundary_mode="inner",
                                  label_colors=None,
                                  alpha=1.0,
                                  thickness=3,
                                  return_image=False):
    """
    Save an image as RGB alongside a corresponding label overlay.
    This can be used to quickly visualize the results of a segmentation, generally using the
    default image viewer of the operating system.

    :param im: Image to save. If this is an 8-bit RGB image (channels-last) it will be used as-is,
               otherwise it will be converted to RGB
    :param lab: Label image to overlay
    :param output_dir: Directory to save to
    :param base_name: Base name for the image files to save
    :param clip_percentile: Percentile to clip the image at. Used during RGB conversion, if needed.
    :param scale_per_channel: Whether to scale each channel independently during RGB conversion.
    :param label_boundary_mode: A boundary mode compatible with scikit-image find_boundaries;
                                one of 'thick', 'inner', 'outer', 'subpixel'. If None, the lab is used directly.
    :param alpha: Alpha value for the underlying image when using the overlay.
                  Setting this less than 1 can help the overlay stand out more prominently.
    """

    import imageio
    from skimage.color import label2rgb
    from skimage.segmentation import find_boundaries
    from skimage import morphology

    if isinstance(im, torch.Tensor):
        im = torch.clamp(im,0,1).cpu().numpy() * 255 
        im = _move_channel_axis(im,to_back = True).astype(np.uint8)


    if isinstance(lab, torch.Tensor):
        lab = _move_channel_axis(torch.atleast_3d(lab.squeeze())).cpu().numpy()
        
        if lab.shape[0] == 1:
            lab = lab[0]
            image_overlay = save_image_with_label_overlay(im,lab=lab,return_image=True, label_boundary_mode="thick", label_colors=label_colors,thickness=5,alpha=1)
        elif lab.shape[0] == 2:
            nuclei_labels_for_display = lab[0]
            cell_labels_for_display = lab[1] 
            bg = (lab.sum(0) == 0)

            if label_boundary_mode is None:
                from palettable import wesanderson as wes
                from palettable.scientific import diverging as div
                colour_cells = list((np.array(div.Berlin_12.colors[1]) /255))
                colour_nuclei = list( np.array(div.Berlin_12.colors[11] ) /255)
                image_overlay = save_image_with_label_overlay(im,lab=cell_labels_for_display,return_image=True, label_boundary_mode=None, label_colors=colour_cells,thickness=1, alpha = 1)
                image_overlay = save_image_with_label_overlay(image_overlay,lab=nuclei_labels_for_display,return_image=True, label_boundary_mode=None, label_colors=colour_nuclei,thickness=1, alpha = 1)
                image_overlay = save_image_with_label_overlay(image_overlay,lab=nuclei_labels_for_display,return_image=True, label_boundary_mode="thick", label_colors="black",thickness=1, alpha = 1)
                image_overlay = save_image_with_label_overlay(image_overlay,lab=cell_labels_for_display,return_image=True, label_boundary_mode= "thick", label_colors="black",thickness=1, alpha = 1) 
                image_overlay[bg] = (255,255,255)
            else:
                image_overlay = save_image_with_label_overlay(im,lab=cell_labels_for_display,return_image=True, label_boundary_mode=label_boundary_mode, label_colors="cyan",thickness=1, alpha = 1)
                image_overlay = save_image_with_label_overlay(image_overlay,lab=nuclei_labels_for_display,return_image=True, label_boundary_mode=label_boundary_mode, label_colors="magenta",thickness=1, alpha = 1)
        return image_overlay



    # Check if we have an RGB, channels-last image already
    if im.dtype == np.uint8 and im.ndim == 3 and im.shape[2] == 3:
        im_rgb = im.copy()
    else:
        im_rgb = _to_rgb_channels_last(im, clip_percentile=clip_percentile, scale_per_channel=scale_per_channel)

    # Convert labels to boundaries, if required
    if label_boundary_mode is not None:
        bw_boundaries = find_boundaries(lab, mode=label_boundary_mode)
        lab = lab.copy()
        # Need to expand labels for outer boundaries, but have to avoid overwriting known labels
        if label_boundary_mode in ['thick', 'outer']:
            lab2 = morphology.dilation(lab, footprint=np.ones((thickness, thickness)))
            mask_dilated = bw_boundaries & (lab == 0)

            lab[mask_dilated] = lab2[mask_dilated]
        lab[~bw_boundaries] = 0
        mask_temp = bw_boundaries
    else:
        mask_temp = lab != 0

    # Create a labels displayed
    if label_colors is None:
        lab_overlay = label2rgb(lab).astype(np.float32)
    elif label_colors == "red":
        lab_overlay = np.zeros((lab.shape[0], lab.shape[1], 3))
        lab_overlay[lab > 0, 0] = 1
    elif label_colors == "green":
        lab_overlay = np.zeros((lab.shape[0], lab.shape[1], 3))
        lab_overlay[lab > 0, 1] = 1
    elif label_colors == "blue":
        lab_overlay = np.zeros((lab.shape[0], lab.shape[1], 3))
        lab_overlay[lab > 0, 2] = 1
    else:
        if type(label_colors) == str:
            label_colors = color_name_to_rgb(label_colors)
        lab_overlay = np.zeros((lab.shape[0], lab.shape[1], 3))
        lab_overlay[lab > 0] = label_colors
    # else:
    #     raise Exception("label_colors must be red, green, blue or None")

    im_overlay = im_rgb.copy()
    for c in range(im_overlay.shape[-1]):
        im_temp = im_overlay[..., c]
        lab_temp = lab_overlay[..., c]
        im_temp[mask_temp] = (lab_temp[mask_temp] * 255).astype(np.uint8)

    # Make main image translucent, if needed
    if alpha != 1.0:
        alpha_channel = (mask_temp * 255.0).astype(np.uint8)
        alpha_channel[~mask_temp] = alpha * 255
        im_overlay = np.dstack((im_overlay, alpha_channel))
    if return_image:
        return im_overlay

    if base_name is None:
        base_name = "image"

    print(f"Exporting image to {os.path.join(output_dir, f'{base_name}.png')}")
    imageio.imwrite(os.path.join(output_dir, f'{base_name}.png'), im_rgb)
    imageio.imwrite(os.path.join(output_dir, f'{base_name}_overlay.png'), im_overlay)

def display_cells_and_nuclei(lab):
    display = save_image_with_label_overlay(torch.zeros((lab.shape[-2],lab.shape[-1],3)), lab, return_image= True, label_boundary_mode=None,alpha = 1)
    return display
def display_colourized(mIF):
    from InstanSeg.utils.augmentations import Augmentations
    Augmenter=Augmentations()

    mIF = Augmenter.to_tensor(mIF, normalize=False)[0]
    if mIF.shape[0]!=3:
        colour_render,_ = Augmenter.colourize(mIF, random_seed = 0)
    else:
        colour_render = Augmenter.to_tensor(mIF, normalize=True)[0]
    colour_render = torch.clamp_(colour_render, 0, 1)
    colour_render = _move_channel_axis(colour_render,to_back = True).detach().numpy()*255
    return colour_render.astype(np.uint8)

def display_overlay(im, lab):
    assert lab.ndim == 4, "lab must be 4D"
    assert im.ndim == 3, "im must be 3D"
    output_dimension = lab.shape[1]

    im_for_display = display_colourized(im)

    if output_dimension ==1: #Nucleus or cell mask]
        labels_for_display = lab[0,0].cpu().numpy() #Shape is 1,H,W
        image_overlay = save_image_with_label_overlay(im_for_display,lab=labels_for_display,return_image=True, label_boundary_mode="thick", label_colors=None,thickness=10,alpha=0.5)
    elif output_dimension ==2: #Nucleus and cell mask
        nuclei_labels_for_display = lab[0,0].cpu().numpy()
        cell_labels_for_display = lab[0,1].cpu().numpy() #Shape is 1,H,W
        image_overlay = save_image_with_label_overlay(im_for_display,lab=nuclei_labels_for_display,return_image=True, label_boundary_mode="thick", label_colors="red",thickness=10)
        image_overlay = save_image_with_label_overlay(image_overlay,lab=cell_labels_for_display,return_image=True, label_boundary_mode="inner", label_colors="green",thickness=1)
    return image_overlay

def _to_rgb_channels_last(im: np.ndarray,
                          clip_percentile: float = 1.0,
                          scale_per_channel: bool = True,
                          input_channels_first: bool = True) -> np.ndarray:
    """
    Convert an image to RGB, ensuring the output has channels-last ordering.
    """

    if im.ndim < 2 or im.ndim > 3:
        raise ValueError(f"Number of dimensions should be 2 or 3! Image has shape {im.shape}")
    if im.ndim == 3:
        if input_channels_first:
            im = np.moveaxis(im, source=0, destination=-1)
        if im.shape[-1] != 3:
            im = im.mean(axis=-1)
    if im.ndim > 2 and scale_per_channel:
        im_scaled = np.dstack(
            [_to_scaled_uint8(im[..., ii], clip_percentile=clip_percentile) for ii in range(3)]
        )
    else:
        im_scaled = _to_scaled_uint8(im, clip_percentile=clip_percentile)
    if im.ndim == 2:
        im_scaled = np.repeat(im_scaled, repeats=3, axis=-1)
    return im_scaled


def _to_scaled_uint8(im: np.ndarray, clip_percentile=1.0) -> np.ndarray:
    """
    Convert an image to uint8, scaling according to the given percentile.
    """
    im_float = im.astype(np.float32, copy=True)
    min_val = np.percentile(im_float.ravel(), clip_percentile)
    max_val = np.percentile(im_float.ravel(), 100.0 - clip_percentile)
    im_float -= min_val
    im_float /= (max_val - min_val)
    im_float *= 255
    return np.clip(im_float, a_min=0, a_max=255).astype(np.uint8)


def _choose_device(device: str = None, verbose=True) -> str:
    """
    Choose a device to use with PyTorch, given the desired device name.
    If a requested device is not specified or not available, then a default is chosen.
    """
    if device is not None:
        if device == 'cuda' and not torch.cuda.is_available():
            device = None
            print('CUDA device requested but not available!')
        if device == 'mps' and not torch.backends.mps.is_available():
            device = None
            print('MPS device requested but not available!')

    if device is None:
        if torch.cuda.is_available():
            device = 'cuda'
        elif torch.backends.mps.is_available():
            device = 'mps'
        else:
            device = 'cpu'
        if verbose:
            print(f'Requesting default device: {device}')

    return device


def count_instances(labels: Union[np.ndarray, torch.Tensor]):
    import fastremap
    if isinstance(labels, torch.Tensor):
        num_labels = len(torch.unique(labels[labels > 0]))
    elif isinstance(labels, np.ndarray):
        num_labels = len(fastremap.unique(labels[labels > 0]))
    else:
        raise Exception("Labels must be numpy array or torch tensor")
    return num_labels


def _estimate_image_modality(img, mask):
    """
    This function estimates the modality of an image (i.e. brightfield, chromogenic or fluorescence) based on the
    mean intensity of the pixels inside and outside the mask.
    """

    if isinstance(img, np.ndarray):
        img = np.atleast_3d(_move_channel_axis(img))
        mask = np.squeeze(mask)

        assert mask.ndim == 2, print("Mask must be 2D, but got shape", mask.shape)
        if count_instances(mask) < 1:
            return "Fluorescence"  # The images don't contain any cells, but they look like fluorescence images.
        elif np.mean(img[:, mask > 0]) > np.mean(img[:, mask == 0]):
            return "Fluorescence"
        else:
            if img.shape[0] == 1:
                return "Brightfield"
            else:
                return "Brightfield"  # "Chromogenic"


    elif isinstance(img, torch.Tensor):
        img = torch.at_least_3d(_move_channel_axis(img))
        mask = torch.squeeze(mask)
        assert mask.ndim == 2, "Mask must be 2D"

        if count_instances(mask) < 1:
            return "Fluorescence"  # The images don't contain any cells, but they look like fluorescence images.
        elif torch.mean(img[:, mask > 0]) > torch.mean(img[:, mask == 0]):
            return "Fluorescence"
        else:
            if img.shape[0] == 1:
                return "Brightfield"
            else:
                return "Brightfield"  # "Chromogenic"


def timer(func):
    import functools
    from line_profiler import LineProfiler
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        lp = LineProfiler()
        lp_wrapper = lp(func)
        lp_wrapper(*args, **kwargs)
        lp.print_stats()
        value = func(*args, **kwargs)
        return value

    return wrapper


def read_pixel_size(image_path):
    from aicsimageio import AICSImage
    img = AICSImage(image_path)
    img_pixel_size = img.physical_pixel_sizes.X

    if img_pixel_size is None or img_pixel_size ==0:
        import slideio
        slide = slideio.open_slide(image_path, driver = "AUTO")
        scene  = slide.get_scene(0)
        img_pixel_size = scene.resolution[0] * 10**6

        if img_pixel_size is None or img_pixel_size ==0:
            raise ValueError("Could not read pixel size from image metadata")
    return img_pixel_size


def set_export_paths():
    from pathlib import Path
    if os.environ.get('INSTANSEG_BIOIMAGEIO_PATH'):
        path = Path(os.environ['INSTANSEG_BIOIMAGEIO_PATH'])
    else:
        path = Path(os.path.join(os.path.dirname(__file__),"../bioimageio_models/"))
        os.environ['INSTANSEG_BIOIMAGEIO_PATH'] = str(path)

    if not path.exists():
        path.mkdir(exist_ok=True,parents=True)

    if os.environ.get('INSTANSEG_TORCHSCRIPT_PATH'):
        path = Path(os.environ['INSTANSEG_TORCHSCRIPT_PATH'])
    else:
        path = Path(os.path.join(os.path.dirname(__file__),"../torchscripts/"))
        os.environ['INSTANSEG_TORCHSCRIPT_PATH'] = str(path)

    if not path.exists():
        path.mkdir(exist_ok=True,parents=True)

    if os.environ.get('INSTANSEG_MODEL_PATH'):
        path = Path(os.environ['INSTANSEG_MODEL_PATH'])
    else:
        path = Path(os.path.join(os.path.dirname(__file__),"../models/"))
        os.environ['INSTANSEG_MODEL_PATH'] = str(path)

    if not path.exists():
        path.mkdir(exist_ok=True,parents=True)

    if os.environ.get('EXAMPLE_IMAGE_PATH'):
        path = Path(os.environ['EXAMPLE_IMAGE_PATH'])
    else:
        path = Path(os.path.join(os.path.dirname(__file__),"../examples/"))
        os.environ['EXAMPLE_IMAGE_PATH'] = str(path)

        


def export_to_torchscript(model_str: str, show_example: bool = False, output_dir: str = "../torchscripts",
                          model_path: str = "../models", torchscript_name: str = None, mixed_predicision = False):
    device = 'cpu'
    from InstanSeg.utils.model_loader import load_model
    import math

    import os
    set_export_paths()
    output_dir = os.environ.get('INSTANSEG_TORCHSCRIPT_PATH')
    model_path = os.environ.get('INSTANSEG_MODEL_PATH')
    example_path = os.environ.get('EXAMPLE_IMAGE_PATH') 


    import pandas as pd

    #Check is best_params.csv exists in the model folder, if not, use default parameters
    if not os.path.exists(Path(model_path) / model_str / "best_params.csv"):
        print("No best_params.csv found in model folder, using default parameters")
        params = None
    else:
        #Load best_params.csv
        df = pd.read_csv(Path(model_path) / model_str / "best_params.csv",header = None)
        params = {key: value for key, value in df.to_dict('tight')['data']}

    model, model_dict = load_model(folder=model_str, path=model_path)
    model.eval()
    model.to(device)

    cells_and_nuclei = model_dict['cells_and_nuclei']
    pixel_size = model_dict['pixel_size']
    n_sigma = model_dict['n_sigma']


    input_data = tifffile.imread(os.path.join(example_path,"HE_example.tif"))
    #input_data = tifffile.imread("../examples/LuCa1.tif")
    from InstanSeg.utils.augmentations import Augmentations
    Augmenter = Augmentations()
    input_tensor, _ = Augmenter.to_tensor(input_data, normalize=False)
    input_tensor, _ = Augmenter.normalize(input_tensor)

    if not math.isnan(pixel_size):
        input_tensor, _ = Augmenter.torch_rescale(input_tensor, current_pixel_size=0.5, requested_pixel_size=pixel_size, crop =True, modality="Brightfield")
    input_tensor = input_tensor.to(device)


    if input_tensor.shape[0] != model_dict["dim_in"] and model_dict["dim_in"] != 0 and model_dict["dim_in"] is not None:
        input_tensor = torch.randn((model_dict["dim_in"], input_tensor.shape[1], input_tensor.shape[2])).to(device)
        dim_in = model_dict["dim_in"]
    else:
        dim_in = 3

    from InstanSeg.utils.loss.instanseg_loss import InstanSeg_Torchscript
    super_model = InstanSeg_Torchscript(model, cells_and_nuclei=cells_and_nuclei, 
                                        pixel_size = pixel_size, 
                                        n_sigma = n_sigma, 
                                        params = params, 
                                        feature_engineering_function = str(model_dict["feature_engineering"]), 
                                        backbone_dim_in= dim_in, 
                                        to_centre = bool(model_dict["to_centre"]),
                                        mixed_precision = mixed_predicision).to(device)
    

    out = super_model(input_tensor[None,])
    if show_example:
        show_images([input_tensor] + [i for i in out.squeeze(0)], labels=[i + 1 for i in range(len(out.squeeze(0)))])

    with torch.jit.optimized_execution(should_optimize=True):
        traced_cpu = torch.jit.script(super_model, input_tensor[None,])

    if torchscript_name is None:
        torchscript_name = model_str

    if not os.path.exists(output_dir):
        os.mkdir(output_dir)

    torch.jit.save(traced_cpu, os.path.join(output_dir, torchscript_name + ".pt"))
    print("Saved torchscript model to", os.path.join(output_dir, torchscript_name + ".pt"))



def drag_and_drop_file():
    """
    This opens a window where a user can drop a file and returns the path to the file
    """

    import tkinter as tk
    from tkinterdnd2 import TkinterDnD, DND_FILES

    def drop(event):
        file_path = event.data
        entry_var.set(file_path)

    def save_and_close():
        entry_var.get()
        root.destroy()  # Close the window

    root = TkinterDnD.Tk()
    entry_var = tk.StringVar()
    entry = tk.Entry(root, textvariable=entry_var, width=40)
    entry.pack(pady=20)

    entry.drop_target_register(DND_FILES)
    entry.dnd_bind('<<Drop>>', drop)

    save_button = tk.Button(root, text="Save and Close", command=save_and_close)
    save_button.pack(pady=10)
    root.mainloop()
    return entry_var.get()




def download_model(model_str: str, return_model = False):
    import os
    import requests
    import zipfile
    from io import BytesIO

    if not os.environ.get("INSTANSEG_BIOIMAGEIO_PATH"):
        os.environ["INSTANSEG_BIOIMAGEIO_PATH"] = os.path.join(os.path.dirname(__file__),"../bioimageio_models/")

    bioimageio_path = os.environ.get("INSTANSEG_BIOIMAGEIO_PATH")

    # Ensure the directory exists
    os.makedirs(bioimageio_path, exist_ok=True)
    
    # URL of the file to download
    url = r"https://github.com/instanseg/instanseg/releases/download/instanseg_models_v1/{}.zip".format(model_str)
    
    # Download the file
    response = requests.get(url)
    response.raise_for_status()  # Raise an error for bad responses
    
    # Unzip the file into the bioimageio path
    with zipfile.ZipFile(BytesIO(response.content)) as z:
        z.extractall(bioimageio_path)

    if return_model:
        import torch
        path_to_torchscript_model = bioimageio_path + f"{model_str}/instanseg.pt"
        return torch.jit.load(path_to_torchscript_model)


    print(f"Model {model_str} downloaded and extracted to {bioimageio_path}")
