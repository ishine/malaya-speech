import tensorflow as tf
from tensorflow.keras.layers import (
    BatchNormalization,
    Concatenate,
    Conv1D,
    Conv2DTranspose,
    Dropout,
    ELU,
    LeakyReLU,
    Multiply,
    ReLU,
    Softmax,
    Add,
    MaxPooling1D,
)
from tensorflow.compat.v1.keras.initializers import he_uniform
from functools import partial


def _get_conv_activation_layer(params):
    """
    :param params:
    :returns: Required Activation function.
    """
    conv_activation = params.get('conv_activation')
    if conv_activation == 'ReLU':
        return ReLU()
    elif conv_activation == 'ELU':
        return ELU()
    return LeakyReLU(0.2)


def _get_deconv_activation_layer(params):
    """
    :param params:
    :returns: Required Activation function.
    """
    deconv_activation = params.get('deconv_activation')
    if deconv_activation == 'LeakyReLU':
        return LeakyReLU(0.2)
    elif deconv_activation == 'ELU':
        return ELU()
    return ReLU()


class Model:
    def __init__(
        self,
        input_tensor,
        num_layers = 6,
        num_initial_filters = 66,
        output_mask_logit = False,
        logging = False,
    ):
        conv_activation_layer = _get_conv_activation_layer({})
        deconv_activation_layer = _get_deconv_activation_layer({})
        kernel_initializer = he_uniform(seed = 50)

        conv1d_factory = partial(
            Conv1D,
            strides = (2),
            padding = 'same',
            kernel_initializer = kernel_initializer,
        )

        conv2d_transpose_factory = partial(
            Conv2DTranspose,
            strides = (2, 1),
            padding = 'same',
            kernel_initializer = kernel_initializer,
        )

        def resnet_block(input_tensor, filter_size):

            res = conv1d_factory(
                filter_size, (1), strides = (1), use_bias = False
            )(input_tensor)
            conv1 = conv1d_factory(filter_size, (5), strides = (1))(
                input_tensor
            )
            batch1 = BatchNormalization(axis = -1)(conv1)
            rel1 = conv_activation_layer(batch1)
            conv2 = conv1d_factory(filter_size, (5), strides = (1))(rel1)
            batch2 = BatchNormalization(axis = -1)(conv2)
            resconnection = Add()([res, batch2])
            rel2 = conv_activation_layer(resconnection)
            return MaxPooling1D(padding = 'same')(rel2)

        enc_outputs = []
        current_layer = input_tensor
        for i in range(num_layers):

            if i < num_layers - 1:
                current_layer = resnet_block(
                    current_layer, num_initial_filters * (2 ** i)
                )
                enc_outputs.append(current_layer)
            else:
                current_layer = conv1d_factory(
                    num_initial_filters * (2 ** i), (5)
                )(current_layer)

            if logging:
                print(current_layer)

        for i in range(num_layers - 1):

            current_layer = conv2d_transpose_factory(
                num_initial_filters * (2 ** (num_layers - i - 2)), (5, 1)
            )((tf.expand_dims(current_layer, 2)))[:, :, 0]
            current_layer = deconv_activation_layer(current_layer)
            current_layer = BatchNormalization(axis = -1)(current_layer)
            if i < 3:
                current_layer = Dropout(0.5)(current_layer)
            current_layer = Concatenate(axis = -1)(
                [enc_outputs[-i - 1], current_layer]
            )
            if logging:
                print(current_layer)

        current_layer = conv2d_transpose_factory(1, (5, 1), strides = (2, 1))(
            (tf.expand_dims(current_layer, 2))
        )[:, :, 0]
        current_layer = deconv_activation_layer(current_layer)
        current_layer = BatchNormalization(axis = -1)(current_layer)

        if not output_mask_logit:
            last = Conv1D(
                1,
                (4),
                dilation_rate = (2),
                activation = None,
                padding = 'same',
                kernel_initializer = kernel_initializer,
            )((current_layer))
            output = Multiply()([last, input_tensor])
            self.logits = output
        else:

            self.logits = Conv1D(
                1,
                (4),
                dilation_rate = (2),
                padding = 'same',
                kernel_initializer = kernel_initializer,
            )((current_layer))
