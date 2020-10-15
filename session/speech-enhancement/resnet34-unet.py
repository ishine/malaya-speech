import os
import warnings

os.environ['CUDA_VISIBLE_DEVICES'] = '2,3'
warnings.filterwarnings('ignore')

from glob import glob
from itertools import cycle
import random
import pickle
import numpy as np
import tensorflow as tf
import segmentation_models as sm
import malaya_speech.utils.featurization as featurization
import malaya_speech.augmentation.waveform as augmentation
import malaya_speech.train as train
import malaya_speech
from tqdm import tqdm
import soundfile as sf
from multiprocessing import Pool
import itertools


def chunks(l, n):
    for i in range(0, len(l), n):
        yield (l[i : i + n], i // n)


def multiprocessing(strings, function, cores = 6, returned = True):
    df_split = chunks(strings, len(strings) // cores)
    pool = Pool(cores)
    print('initiate pool map')
    pooled = pool.map(function, df_split)
    print('gather from pool')
    pool.close()
    pool.join()
    print('closed pool')

    if returned:
        return list(itertools.chain(*pooled))


def get_data(
    pattern = '../youtube/clean-wav/*.wav',
    ambient_file = '../youtube/ambients.pkl',
):

    files = glob(pattern)
    files = list(set(files))
    random.shuffle(files)
    print('total files', len(files))
    file_cycle = cycle(files)

    with open(ambient_file, 'rb') as fopen:
        ambient = pickle.load(fopen)

    return file_cycle, ambient


file_cycle, ambient = get_data()


def combine_speakers(files, n = 5):
    w_samples = random.sample(files, n)
    y = [w_samples[0]]
    left = w_samples[0].copy()
    for i in range(1, n):

        right = w_samples[i].copy()

        overlap = random.uniform(0.01, 1.5)
        left_len = int(overlap * len(left))

        padded_right = np.pad(right, (left_len, 0))

        if len(left) > len(padded_right):
            padded_right = np.pad(
                padded_right, (0, len(left) - len(padded_right))
            )
        else:
            left = np.pad(left, (0, len(padded_right) - len(left)))

        y.append(padded_right)
        left = left + padded_right
    return left, y


def sampling(combined, frame_duration_ms = 700, sample_rate = 22050):
    n = int(sample_rate * (frame_duration_ms / 1000.0))
    offset = 0
    results = []
    while offset + n <= len(combined):
        results.append(combined[offset : offset + n])
        offset += n
    if offset < len(combined):
        results.append(combined[offset:])

    return results


def calc(signal):

    choice = random.randint(0, 5)
    if choice == 0:

        x = augmentation.sox_augment_high(
            signal,
            min_bass_gain = random.randint(25, 50),
            reverberance = random.randint(0, 80),
            hf_damping = 10,
            room_scale = random.randint(0, 50),
            negate = 1,
        )
    if choice == 1:
        x = augmentation.sox_augment_high(
            signal,
            min_bass_gain = random.randint(25, 70),
            reverberance = random.randint(0, 80),
            hf_damping = 10,
            room_scale = random.randint(0, 50),
            negate = 0,
        )
    if choice == 2:
        x = augmentation.sox_augment_low(
            signal,
            min_bass_gain = random.randint(5, 30),
            reverberance = random.randint(0, 80),
            hf_damping = 10,
            room_scale = random.randint(0, 50),
            negate = random.randint(0, 1),
        )
    if choice == 3:
        x = augmentation.sox_augment_combine(
            signal,
            min_bass_gain_high = random.randint(25, 70),
            min_bass_gain_low = random.randint(5, 30),
            reverberance = random.randint(0, 80),
            hf_damping = 10,
            room_scale = random.randint(0, 90),
        )
    if choice == 4:
        x = augmentation.sox_reverb(
            signal,
            reverberance = random.randint(10, 80),
            hf_damping = 10,
            room_scale = random.randint(10, 90),
        )
    if choice == 5:
        x = signal

    if random.randint(0, 1):
        x = augmentation.add_uniform_noise(
            x, power = random.uniform(0.005, 0.015)
        )

    return x


def calc_mel(signal):
    x, signal = signal
    y = featurization.scale_mel(signal)
    x = featurization.scale_mel(x)
    z = y.T - x.T
    return x.T, z


def loop(files):
    files = files[0]
    results = []
    for f in files:
        results.append(calc(f))
    return results


def loop_mel(files):
    files = files[0]
    results = []
    for f in files:
        results.append(calc_mel(f))
    return results


def read_file(file):
    y, sr = sf.read(file)
    print(file, len(y) / sr / 60)

    y = augmentation.random_sampling(y, sr, random.randint(30000, 180000))
    return y


def generate(batch_size = 40, core = 20, repeat = 2):

    while True:
        batch_files = [next(file_cycle) for _ in range(batch_size)]
        print(batch_files)
        print('before wavs')
        wavs = [read_file(f) for f in tqdm(batch_files)]
        print('after wavs')

        samples = []
        print('before iterating wavs')
        for wav in tqdm(wavs):
            if random.random() < 0.7:
                signal = wav.copy()

                if random.randint(0, 1):
                    signal_ = random.choice(wavs)
                    signal = augmentation.add_noise(
                        signal, signal_, factor = random.uniform(0.6, 1.0)
                    )

            else:
                r = random.randint(2, 4)
                signal = combine_speakers(wavs, min(len(wavs), r))[0]

            samples.append(signal)

        R = []
        print('before iterating samples')
        for s in tqdm(samples):
            if random.random() > 0.8:
                signal_ = random.choice(ambient)
                s = augmentation.add_noise(
                    s, signal_, factor = random.uniform(0.1, 0.3)
                )
            R.append(s)

        print('len samples', len(samples))
        results = multiprocessing(R, loop, cores = min(len(samples), core))
        print('after len samples', len(samples))

        X, Y = [], []
        for o in range(len(samples)):
            X.extend(sampling(results[o], 1000))
            Y.extend(sampling(samples[o], 1000))

        combined = list(zip(X, Y))
        print('len combined', len(combined))
        results = multiprocessing(
            combined, loop_mel, cores = min(len(combined), core)
        )
        print('after len combined', len(combined))

        for _ in range(repeat):
            for r in results:
                yield {'inputs': r[0], 'targets': r[1]}

        del wavs, samples, R, results, combined


DIMENSION = 256


def parse(example):
    x = tf.compat.v1.numpy_function(
        featurization.scale_mel, [example['inputs']], tf.float32
    )
    x = tf.transpose(tf.reshape(x, (DIMENSION, -1)))

    y = tf.compat.v1.numpy_function(
        featurization.scale_mel, [example['targets']], tf.float32
    )
    y = tf.transpose(tf.reshape(y, (DIMENSION, -1)))

    z = y - x
    example['inputs'] = x
    example['targets'] = z
    return example


def get_dataset(batch_size = 32, shuffle_size = 128, prefetch_size = 128):
    def get():
        dataset = tf.data.Dataset.from_generator(
            generate,
            {'inputs': tf.float32, 'targets': tf.float32},
            output_shapes = {
                'inputs': tf.TensorShape([None, 256]),
                'targets': tf.TensorShape([None, 256]),
            },
        )

        dataset = dataset.shuffle(shuffle_size)

        dataset = dataset.padded_batch(
            batch_size,
            padded_shapes = {
                'inputs': tf.TensorShape([256, 256]),
                'targets': tf.TensorShape([256, 256]),
            },
            padding_values = {
                'inputs': tf.constant(0, dtype = tf.float32),
                'targets': tf.constant(0, dtype = tf.float32),
            },
        )
        # dataset = dataset.prefetch(prefetch_size)
        return dataset

    return get


init_lr = 1e-5
epochs = 500000


def model_fn(features, labels, mode, params):
    model = sm.Unet(
        'resnet34',
        classes = 1,
        activation = 'tanh',
        input_shape = (256, 256, 1),
        encoder_weights = None,
    )
    Y = tf.expand_dims(features['inputs'], -1)
    logits = model(Y)
    huber = tf.compat.v1.losses.huber_loss(
        features['targets'], logits[:, :, :, 0]
    )
    z = tf.expand_dims(features['targets'], -1)
    ssim = 1 - tf.image.ssim(
        logits,
        z,
        max_val = 1.5,
        filter_size = 11,
        filter_sigma = 1.5,
        k1 = 0.01,
        k2 = 0.03,
    )
    ssim = tf.reduce_mean(ssim)
    huber = tf.reduce_mean(huber)
    loss = huber + ssim
    tf.identity(loss, 'train_loss')
    tf.identity(huber, 'train_huber')
    tf.identity(ssim, 'train_ssim')

    tf.summary.scalar('train_huber', huber)
    tf.summary.scalar('train_ssim', ssim)
    tf.summary.scalar('train_loss', loss)

    if mode == tf.estimator.ModeKeys.TRAIN:
        global_step = tf.train.get_or_create_global_step()
        learning_rate = tf.constant(
            value = init_lr, shape = [], dtype = tf.float32
        )
        learning_rate = tf.train.polynomial_decay(
            learning_rate,
            global_step,
            epochs,
            end_learning_rate = 1e-7,
            power = 1.0,
            cycle = False,
        )
        optimizer = tf.train.AdamOptimizer(learning_rate = learning_rate)

        train_op = optimizer.minimize(loss, global_step = global_step)
        estimator_spec = tf.estimator.EstimatorSpec(
            mode = mode, loss = loss, train_op = train_op
        )

    elif mode == tf.estimator.ModeKeys.EVAL:

        estimator_spec = tf.estimator.EstimatorSpec(
            mode = tf.estimator.ModeKeys.EVAL, loss = loss
        )

    return estimator_spec


train_hooks = [
    tf.train.LoggingTensorHook(
        ['train_loss', 'train_huber', 'train_ssim'], every_n_iter = 1
    )
]
train_dataset = get_dataset(batch_size = 32)

save_directory = 'output-resnet34-unet'

train.run_training(
    train_fn = train_dataset,
    model_fn = model_fn,
    model_dir = save_directory,
    num_gpus = 2,
    log_step = 1,
    save_checkpoint_step = 5000,
    max_steps = epochs,
    train_hooks = train_hooks,
    eval_step = 0,
)
