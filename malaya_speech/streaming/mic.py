# https://github.com/mozilla/DeepSpeech-examples/blob/r0.8/mic_vad_streaming/mic_vad_streaming.py

import threading, collections, queue, os, os.path
import numpy as np
import wave
from datetime import datetime
from malaya_speech.utils.validator import check_pipeline
from herpetologist import check_type

RATE_PROCESS = 16000
CHANNELS = 1
BLOCKS_PER_SECOND = 50


class Audio:
    @check_type
    def __init__(
        self,
        vad,
        callback = None,
        device = None,
        format = None,
        input_rate: int = RATE_PROCESS,
        sample_rate: int = RATE_PROCESS,
        channels: int = CHANNELS,
        blocks_per_second: int = BLOCKS_PER_SECOND,
    ):

        check_pipeline(vad, 'vad')

        import pyaudio

        self.vad = vad
        self.input_rate = input_rate
        self.sample_rate = sample_rate
        self.channels = channels
        self.blocks_per_second = blocks_per_second
        self.block_size = int(self.sample_rate / float(self.blocks_per_second))
        self.block_size_input = int(
            self.input_rate / float(self.blocks_per_second)
        )
        self.frame_duration_ms = 1000 * self.block_size // self.sample_rate

        def proxy_callback(in_data, frame_count, time_info, status):
            if self.chunk is not None:
                in_data = self.wf.readframes(self.chunk)
            callback(in_data)
            return (None, pyaudio.paContinue)

        if callback is None:
            callback = lambda in_data: self.buffer_queue.put(in_data)
        self.buffer_queue = queue.Queue()
        self.device = device
        self.format = format

        self.pa = pyaudio.PyAudio()
        kwargs = {
            'format': format,
            'channels': self.channels,
            'rate': self.input_rate,
            'input': True,
            'frames_per_buffer': self.block_size_input,
            'stream_callback': proxy_callback,
        }

        self.chunk = None
        if self.device:
            kwargs['input_device_index'] = self.device

        self.stream = self.pa.open(**kwargs)
        self.stream.start_stream()

    def resample(self, data, input_rate):
        data16 = np.fromstring(string = data, dtype = np.int16)
        resample_size = int(len(data16) / self.input_rate * self.sample_rate)
        resample = signal.resample(data16, resample_size)
        resample16 = np.array(resample, dtype = np.int16)
        return resample16.tostring()

    def read_resampled(self):
        return self.resample(
            data = self.buffer_queue.get(), input_rate = self.input_rate
        )

    def read(self):
        """Return a block of audio data, blocking if necessary."""
        return self.buffer_queue.get()

    def frame_generator(self):
        if self.input_rate == self.sample_rate:
            while True:
                yield self.read()
        else:
            while True:
                yield self.read_resampled()

    def destroy(self):
        self.stream.stop_stream()
        self.stream.close()
        self.pa.terminate()

    def write_wav(self, filename, data):
        wf = wave.open(filename, 'wb')
        wf.setnchannels(self.channels)
        wf.setsampwidth(2)
        wf.setframerate(self.sample_rate)
        wf.writeframes(data)
        wf.close()

    def vad_collector(self, padding_ms = 300, ratio = 0.75):
        """
        Generator that yields series of consecutive audio frames comprising each utterence, separated by yielding a single None.
        Determines voice activity by ratio of frames in padding_ms. Uses a buffer to include padding_ms prior to being triggered.
        Example: (frame, ..., frame, None, frame, ..., frame, None, ...)
                    |---utterence---|        |---utterence---|
        """
        frames = self.frame_generator()
        num_padding_frames = padding_ms // self.frame_duration_ms
        ring_buffer = collections.deque(maxlen = num_padding_frames)
        triggered = False

        for frame in frames:
            if len(frame) < 640:
                return

            is_speech = self.vad(frame, self.sample_rate)

            if not triggered:
                ring_buffer.append((frame, is_speech))
                num_voiced = len([f for f, speech in ring_buffer if speech])
                if num_voiced > ratio * ring_buffer.maxlen:
                    triggered = True
                    for f, s in ring_buffer:
                        yield f
                    ring_buffer.clear()

            else:
                yield frame
                ring_buffer.append((frame, is_speech))
                num_unvoiced = len(
                    [f for f, speech in ring_buffer if not speech]
                )
                if num_unvoiced > ratio * ring_buffer.maxlen:
                    triggered = False
                    yield None
                    ring_buffer.clear()


def record(
    vad,
    model = None,
    device = None,
    filename: str = None,
    min_length: float = 1.5,
    spinner: bool = True,
):
    try:
        import pyaudio
    except:
        raise ValueError(
            'pyaudio not installed. Please install it by `pip install pyaudio` and try again.'
        )

    audio = Audio(vad, device = device, format = pyaudio.paInt16)
    frames = audio.vad_collector()

    if spinner:
        from halo import Halo

        spinner = Halo(
            text = 'Listening (ctrl-C to exit) ...', spinner = 'line'
        )
    else:
        print('Listening (ctrl-C to exit) ... \n')

    results = []
    wav_data = bytearray()

    try:
        for frame in frames:
            if frame is not None:
                if spinner:
                    spinner.start()
                wav_data.extend(frame)
            else:
                if spinner:
                    spinner.stop()

                buffered = np.frombuffer(wav_data, np.int16)
                duration = buffered.shape[0] / audio.input_rate

                if duration >= min_length:
                    results.append(wav_data)
                    wav_data = bytearray()

    except KeyboardInterrupt:

        if filename is None:
            filename_temp = datetime.now().strftime(
                'savewav_%Y-%m-%d_%H-%M-%S_%f.wav'
            )
        else:
            filename_temp = filename

        print(f'saved audio to {filename_temp}')
        audio.write_wav(filename_temp, b''.join(results))

    if spinner:
        spinner.stop()

    audio.destroy()
