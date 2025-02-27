# --------------------------------------------------------
# SiamMask
# Licensed under The MIT License
# Written by Qiang Wang (wangqiang2015 at ia.ac.cn)
# --------------------------------------------------------
from os.path import join, isdir
from os import listdir, mkdir, makedirs
import cv2
import numpy as np
import glob
import xml.etree.ElementTree as ET
from concurrent import futures
import sys
import time

VID_base_path = './ILSVRC2015'
ann_base_path = join(VID_base_path, 'Annotations/VID/train/')
sub_sets= sorted({'ILSVRC2015_VID_train_0000', 'ILSVRC2015_VID_train_0001', 'ILSVRC2015_VID_train_0002', 'ILSVRC2015_VID_train_0003', 'val'})
# Print iterations progress (thanks StackOverflow)
def printProgress(iteration, total, prefix='', suffix='', decimals=1, barLength=100):
    """
    Call in a loop to create terminal progress bar
    @params:
        iteration   - Required  : current iteration (Int)
        total       - Required  : total iterations (Int)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
        decimals    - Optional  : positive number of decimals in percent complete (Int)
        barLength   - Optional  : character length of bar (Int)
    """
    formatStr       = "{0:." + str(decimals) + "f}"
    percents        = formatStr.format(100 * (iteration / float(total)))
    filledLength    = int(round(barLength * iteration / float(total)))
    bar             = '' * filledLength + '-' * (barLength - filledLength)
    sys.stdout.write('\r%s |%s| %s%s %s' % (prefix, bar, percents, '%', suffix)),
    if iteration == total:
        sys.stdout.write('\x1b[2K\r')
    sys.stdout.flush()


def crop_hwc(image, bbox, out_sz, padding=(0, 0, 0)):
    a = (out_sz-1) / (bbox[2]-bbox[0])
    b = (out_sz-1) / (bbox[3]-bbox[1])
    c = -a * bbox[0]
    d = -b * bbox[1]
    mapping = np.array([[a, 0, c],
                        [0, b, d]]).astype(np.float)
    crop = cv2.warpAffine(image, mapping, (out_sz, out_sz), borderMode=cv2.BORDER_CONSTANT, borderValue=padding)
    return crop


def pos_s_2_bbox(pos, s):
    return [pos[0]-s/2, pos[1]-s/2, pos[0]+s/2, pos[1]+s/2]


def crop_like_SiamFC(image, bbox, context_amount=0.5, exemplar_size=127, instanc_size=255, padding=(0, 0, 0)):
    target_pos = [(bbox[2]+bbox[0])/2., (bbox[3]+bbox[1])/2.]
    target_size = [bbox[2]-bbox[0], bbox[3]-bbox[1]]
    wc_z = target_size[1] + context_amount * sum(target_size)
    hc_z = target_size[0] + context_amount * sum(target_size)
    s_z = np.sqrt(wc_z * hc_z)
    scale_z = exemplar_size / s_z
    d_search = (instanc_size - exemplar_size) / 2
    pad = d_search / scale_z
    s_x = s_z + 2 * pad

    z = crop_hwc(image, pos_s_2_bbox(target_pos, s_z), exemplar_size, padding)
    x = crop_hwc(image, pos_s_2_bbox(target_pos, s_x), instanc_size, padding)
    return z, x


def crop_like_SiamFCx(image, bbox, context_amount=0.5, exemplar_size=127, instanc_size=255, padding=(0, 0, 0)):
    target_pos = [(bbox[2]+bbox[0])/2., (bbox[3]+bbox[1])/2.]
    target_size = [bbox[2]-bbox[0], bbox[3]-bbox[1]]
    wc_z = target_size[1] + context_amount * sum(target_size)
    hc_z = target_size[0] + context_amount * sum(target_size)
    s_z = np.sqrt(wc_z * hc_z)
    scale_z = exemplar_size / s_z
    d_search = (instanc_size - exemplar_size) / 2
    pad = d_search / scale_z
    s_x = s_z + 2 * pad

    x = crop_hwc(image, pos_s_2_bbox(target_pos, s_x), instanc_size, padding)
    return x


def crop_video(sub_set, video, crop_path, instanc_size):
    # 构建当前视频裁剪图像的保存路径
    video_crop_base_path = join(crop_path, sub_set, video)
    # 若路径不存在则创建
    if not isdir(video_crop_base_path):
        makedirs(video_crop_base_path)

    # 构建当前子集的基础路径
    sub_set_base_path = join(ann_base_path, sub_set)
    # 获取当前视频下所有的 XML 文件列表并排序
    xmls = sorted(glob.glob(join(sub_set_base_path, video, '*.xml')))
    for xml in xmls:
        # 解析 XML 文件
        xmltree = ET.parse(xml)
        # 获取所有的目标对象
        objects = xmltree.findall('object')
        # 用于存储目标对象信息的列表
        objs = []
        # 获取文件名
        filename = xmltree.findall('filename')[0].text

        # 读取对应的 JPEG 图像
        im = cv2.imread(xml.replace('xml', 'JPEG').replace('Annotations', 'Data'))
        # 计算图像各通道的平均像素值
        avg_chans = np.mean(im, axis=(0, 1))
        for object_iter in objects:
            # 获取目标对象的跟踪 ID
            trackid = int(object_iter.find('trackid').text)
            # 获取目标对象的边界框信息
            bndbox = object_iter.find('bndbox')
            # 提取边界框坐标
            bbox = [int(bndbox.find('xmin').text), int(bndbox.find('ymin').text),
                    int(bndbox.find('xmax').text), int(bndbox.find('ymax').text)]

            # 调用裁剪函数进行裁剪操作
            x = crop_like_SiamFCx(im, bbox, instanc_size=instanc_size, padding=avg_chans)
            # 将裁剪后的图像转换为 CV_8U 格式，避免 cv::imwrite 警告
            x_8u = cv2.convertScaleAbs(x)
            # 保存转换格式后的裁剪图像
            cv2.imwrite(join(video_crop_base_path, '{:06d}.{:02d}.x.jpg'.format(int(filename), trackid)), x_8u)

def main(instanc_size=511, num_threads=24):
    crop_path = './crop{:d}'.format(instanc_size)
    if not isdir(crop_path): mkdir(crop_path)

    for sub_set in sub_sets:
        sub_set_base_path = join(ann_base_path, sub_set)
        videos = sorted(listdir(sub_set_base_path))
        n_videos = len(videos)
        with futures.ProcessPoolExecutor(max_workers=num_threads) as executor:
            fs = [executor.submit(crop_video, sub_set, video, crop_path, instanc_size) for video in videos]
            for i, f in enumerate(futures.as_completed(fs)):
                # Write progress to error so that it can be seen
                printProgress(i, n_videos, prefix=sub_set, suffix='Done ', barLength=40)


if __name__ == '__main__':
    since = time.time()
    main(int(sys.argv[1]), int(sys.argv[2]))
    time_elapsed = time.time() - since
    print('Total complete in {:.0f}m {:.0f}s'.format(
        time_elapsed // 60, time_elapsed % 60))
