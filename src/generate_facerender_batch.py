import os, sys
import numpy as np
from PIL import Image
from skimage import img_as_float32, transform
import torch
import scipy.io as scio
from glob import glob
import cv2


def get_facerender_data(coeff_path, pic_path, first_coeff_path, audio_path, batch_size, device):
    semantic_radius = 13
    video_name = os.path.splitext(os.path.split(coeff_path)[-1])[0]
    txt_path = os.path.splitext(coeff_path)[0]

    data = {}
    images_list = sorted(glob(os.path.join(pic_path, '*.png')))
    source_image_ts_list = []
    image_index=0
    for single in images_list:
        img1 = Image.open(single)
        source_image = np.array(img1)
        source_image = img_as_float32(source_image)
        source_image = transform.resize(source_image, (256, 256, 3))
        source_image = source_image.transpose((2, 0, 1))
        ##测试下输出的啥
        source_image_ts = torch.FloatTensor(source_image).unsqueeze(0)
        temp_source_image=source_image_ts
        source_image_ts = source_image_ts.repeat(batch_size, 1, 1, 1)
        source_image_ts = source_image_ts.to(device)
        '''
        if image_index <= 5:
            # 将张量转换为NumPy数组
            array = temp_source_image.numpy()
            testSaveImageDir = os.path.join(os.getcwd() , 'testSaveImage')
            os.makedirs(testSaveImageDir, exist_ok=True)
            output_path = 'output_image.jpg'  # 替换为您希望保存的图像路径和文件名
            testSaveImagePath = os.path.join(testSaveImageDir, output_path)
            cv2.imwrite(testSaveImagePath, array)
        image_index+=1
        '''
        source_image_ts_list.append(source_image_ts)
    data['source_image'] = source_image_ts_list

    source_semantics_dict = scio.loadmat(first_coeff_path)

    source_semantics = source_semantics_dict['coeff_3dmm'][:1, :73]  # 1 70

    source_semantics_new = transform_semantic_1(source_semantics, semantic_radius)
    source_semantics_ts = torch.FloatTensor(source_semantics_new).unsqueeze(0)
    source_semantics_ts = source_semantics_ts.repeat(batch_size, 1, 1)
    data['source_semantics'] = source_semantics_ts

    # target 
    generated_dict = scio.loadmat(coeff_path)
    generated_3dmm = generated_dict['coeff_3dmm']
    generated_3dmm[:, :64] = generated_3dmm[:, :64] * 1.0

    generated_3dmm = np.concatenate(
        [generated_3dmm, np.repeat(source_semantics[:, 70:], generated_3dmm.shape[0], axis=0)], axis=1)

    generated_3dmm[:, 64:] = np.repeat(source_semantics[:, 64:], generated_3dmm.shape[0], axis=0)

    with open(txt_path + '.txt', 'w') as f:
        for coeff in generated_3dmm:
            for i in coeff:
                f.write(str(i)[:7] + '  ' + '\t')
            f.write('\n')

    target_semantics_list = []
    frame_num = generated_3dmm.shape[0]
    data['frame_num'] = frame_num
    for frame_idx in range(frame_num):
        target_semantics = transform_semantic_target(generated_3dmm, frame_idx, semantic_radius)
        target_semantics_list.append(target_semantics)

    remainder = frame_num % batch_size
    if remainder != 0:
        for _ in range(batch_size - remainder):
            target_semantics_list.append(target_semantics)

    target_semantics_np = np.array(target_semantics_list)  # frame_num 70 semantic_radius*2+1
    target_semantics_np = target_semantics_np.reshape(batch_size, -1, target_semantics_np.shape[-2],
                                                      target_semantics_np.shape[-1])
    data['target_semantics_list'] = torch.FloatTensor(target_semantics_np)
    data['video_name'] = video_name
    data['audio_path'] = audio_path
    return data


def transform_semantic_1(semantic, semantic_radius):
    semantic_list = [semantic for i in range(0, semantic_radius * 2 + 1)]
    coeff_3dmm = np.concatenate(semantic_list, 0)
    return coeff_3dmm.transpose(1, 0)


def transform_semantic_target(coeff_3dmm, frame_index, semantic_radius):
    num_frames = coeff_3dmm.shape[0]
    seq = list(range(frame_index - semantic_radius, frame_index + semantic_radius + 1))
    index = [min(max(item, 0), num_frames - 1) for item in seq]
    coeff_3dmm_g = coeff_3dmm[index, :]
    return coeff_3dmm_g.transpose(1, 0)


def gen_camera_pose(camera_degree_list, frame_num, batch_size):
    new_degree_list = []
    if len(camera_degree_list) == 1:
        for _ in range(frame_num):
            new_degree_list.append(camera_degree_list[0])
        remainder = frame_num % batch_size
        if remainder != 0:
            for _ in range(batch_size - remainder):
                new_degree_list.append(new_degree_list[-1])
        new_degree_np = np.array(new_degree_list).reshape(batch_size, -1)
        return new_degree_np

    degree_sum = 0.
    for i, degree in enumerate(camera_degree_list[1:]):
        degree_sum += abs(degree - camera_degree_list[i])

    degree_per_frame = degree_sum / (frame_num - 1)
    for i, degree in enumerate(camera_degree_list[1:]):
        degree_last = camera_degree_list[i]
        degree_step = degree_per_frame * abs(degree - degree_last) / (degree - degree_last)
        new_degree_list = new_degree_list + list(np.arange(degree_last, degree, degree_step))
    if len(new_degree_list) > frame_num:
        new_degree_list = new_degree_list[:frame_num]
    elif len(new_degree_list) < frame_num:
        for _ in range(frame_num - len(new_degree_list)):
            new_degree_list.append(new_degree_list[-1])
    print(len(new_degree_list))
    print(frame_num)

    remainder = frame_num % batch_size
    if remainder != 0:
        for _ in range(batch_size - remainder):
            new_degree_list.append(new_degree_list[-1])
    new_degree_np = np.array(new_degree_list).reshape(batch_size, -1)
    return new_degree_np
