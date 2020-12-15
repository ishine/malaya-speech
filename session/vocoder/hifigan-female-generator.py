import os

os.environ['CUDA_VISIBLE_DEVICES'] = '1'

import tensorflow as tf
import numpy as np
from glob import glob
from itertools import cycle

mels = glob('../speech-bahasa/output-female-v2/mels/*.npy')
file_cycle = cycle(mels)
f = next(file_cycle)

import random


def generate(batch_max_steps = 8192, hop_size = 256):
    while True:
        f = next(file_cycle)
        mel = np.load(f)
        audio = np.load(f.replace('mels', 'audios'))

        batch_max_frames = batch_max_steps // hop_size
        if len(audio) < len(mel) * hop_size:
            audio = np.pad(audio, [[0, len(mel) * hop_size - len(audio)]])

        if len(mel) > batch_max_frames:
            interval_start = 0
            interval_end = len(mel) - batch_max_frames
            start_frame = random.randint(interval_start, interval_end)
            start_step = start_frame * hop_size
            audio = audio[start_step : start_step + batch_max_steps]
            mel = mel[start_frame : start_frame + batch_max_frames, :]
        else:
            audio = np.pad(audio, [[0, batch_max_steps - len(audio)]])
            mel = np.pad(mel, [[0, batch_max_frames - len(mel)], [0, 0]])

        yield {'mel': mel, 'audio': audio}


dataset = tf.data.Dataset.from_generator(
    generate,
    {'mel': tf.float32, 'audio': tf.float32},
    output_shapes = {
        'mel': tf.TensorShape([None, 80]),
        'audio': tf.TensorShape([None]),
    },
)
dataset = dataset.shuffle(32)
dataset = dataset.padded_batch(
    32,
    padded_shapes = {
        'audio': tf.TensorShape([None]),
        'mel': tf.TensorShape([None, 80]),
    },
    padding_values = {
        'audio': tf.constant(0, dtype = tf.float32),
        'mel': tf.constant(0, dtype = tf.float32),
    },
)

features = dataset.make_one_shot_iterator().get_next()
features

import malaya_speech
import malaya_speech.train
from malaya_speech.train.model import melgan, hifigan
from malaya_speech.train.model import stft
import malaya_speech.config
from malaya_speech.train.loss import calculate_2d_loss, calculate_3d_loss

hifigan_config = malaya_speech.config.hifigan_config
generator = hifigan.Generator(
    hifigan.GeneratorConfig(**hifigan_config['hifigan_generator_params']),
    name = 'hifigan_generator',
)

stft_loss = stft.loss.MultiResolutionSTFT(**hifigan_config['stft_loss_params'])

y_hat = generator(features['mel'], training = True)
audios = features['audio']

sc_loss, mag_loss = calculate_2d_loss(audios, tf.squeeze(y_hat, -1), stft_loss)

sc_loss = tf.where(sc_loss >= 15.0, tf.zeros(shape = sc_loss.shape), sc_loss)
mag_loss = tf.where(
    mag_loss >= 15.0, tf.zeros(shape = mag_loss.shape), mag_loss
)

generator_loss = 0.5 * (sc_loss + mag_loss)
generator_loss = tf.reduce_mean(generator_loss)

global_step = tf.train.get_or_create_global_step()

print(global_step)

g_boundaries = [100_000, 200_000, 300_000, 400_000, 500_000, 600_000, 700_000]
g_values = [
    0.0005,
    0.0005,
    0.00025,
    0.000_125,
    0.000_062_5,
    0.000_031_25,
    0.000_015_625,
    0.000_001,
]

piece_wise = tf.keras.optimizers.schedules.PiecewiseConstantDecay(
    g_boundaries, g_values
)
lr = piece_wise(global_step)
g_optimizer = tf.train.AdamOptimizer(lr).minimize(
    generator_loss, global_step = global_step
)

sess = tf.InteractiveSession()
sess.run(tf.global_variables_initializer())
saver = tf.train.Saver()

checkpoint = 10000
epoch = 100_000
path = 'hifigan-female'

ckpt_path = tf.train.latest_checkpoint(path)
if ckpt_path:
    saver.restore(sess, ckpt_path)
    print(f'restoring checkpoint from {ckpt_path}')

for i in range(0, epoch):
    g_loss, _, step = sess.run([generator_loss, g_optimizer, global_step])

    if step % checkpoint == 0:
        saver.save(sess, f'{path}/model.ckpt', global_step = step)

    print(step, g_loss)

saver.save(sess, f'{path}/model.ckpt', global_step = step)
