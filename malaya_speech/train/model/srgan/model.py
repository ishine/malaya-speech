from tensorflow.python.keras.layers import (
    Add,
    BatchNormalization,
    Conv1D,
    Dense,
    Flatten,
    Input,
    LeakyReLU,
    PReLU,
    Lambda,
)
from tensorflow.python.keras.models import Model
from .layer import pixel_shuffle
import tensorflow as tf


def upsample(x_in, num_filters):
    x = Conv1D(num_filters, kernel_size = 3, padding = 'same')(x_in)
    last = int(x.shape[-1])
    x = tf.reshape(x, (tf.shape(x)[0], -1, last // 2))
    return PReLU(shared_axes = [1, 2])(x)


def res_block(x_in, num_filters, momentum = 0.8, training = False):
    x = Conv1D(num_filters, kernel_size = 3, padding = 'same')(x_in)
    x = BatchNormalization(momentum = momentum)(x, training = training)
    x = PReLU(shared_axes = [1, 2])(x)
    x = Conv1D(num_filters, kernel_size = 3, padding = 'same')(x)
    x = BatchNormalization(momentum = momentum)(x, training = training)
    x = Add()([x_in, x])
    return x


class Model:
    def __init__(
        self, inputs, num_filters = 256, num_res_blocks = 16, training = True
    ):
        x = inputs

        x = Conv1D(num_filters, kernel_size = 9, padding = 'same')(x)
        x = x_1 = PReLU(shared_axes = [1])(x)

        for _ in range(num_res_blocks):
            x = res_block(x, num_filters, training = training)

        x = Conv1D(num_filters, kernel_size = 3, padding = 'same')(x)
        x = BatchNormalization()(x, training = training)
        x = Add()([x_1, x])

        x = upsample(x, num_filters * 2)
        x = upsample(x, num_filters * 2)

        x = Conv1D(1, kernel_size = 9, padding = 'same', activation = 'tanh')(x)
        self.logits = x


def discriminator_block(
    x_in,
    num_filters,
    strides = 1,
    batchnorm = True,
    momentum = 0.8,
    training = False,
):
    x = Conv1D(
        num_filters, kernel_size = 3, strides = strides, padding = 'same'
    )(x_in)
    if batchnorm:
        x = BatchNormalization(momentum = momentum)(x, training = training)
    return LeakyReLU(alpha = 0.2)(x)


class Discriminator:
    def __init__(self, inputs, num_filters = 64, training = True):
        x = discriminator_block(
            inputs, num_filters, batchnorm = False, training = training
        )
        x = discriminator_block(
            x, num_filters, strides = 2, training = training
        )

        x = discriminator_block(x, num_filters * 2, training = training)
        x = discriminator_block(
            x, num_filters * 2, strides = 2, training = training
        )

        x = discriminator_block(x, num_filters * 4, training = training)
        x = discriminator_block(
            x, num_filters * 4, strides = 2, training = training
        )

        x = discriminator_block(x, num_filters * 8, training = training)
        x = discriminator_block(
            x, num_filters * 8, strides = 2, training = training
        )

        x = Flatten()(x)
        print(x)

        x = Dense(1024)(x)
        x = LeakyReLU(alpha = 0.2)(x)
        self.logits = Dense(1, activation = 'sigmoid')(x)