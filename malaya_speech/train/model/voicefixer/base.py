from malaya_speech.train.model.voicefixer.tools.pytorch_util import *
from malaya_speech.train.model.voicefixer.tools.wav import *
from malaya_speech.train.model.voicefixer.restorer.model import VoiceFixer as voicefixer_fe
from malaya_speech.utils.torch_utils import to_numpy, to_tensor_cuda
import os

EPS = 1e-8


class VoiceFixer(nn.Module):
    def __init__(self, pth, vocoder_pth):
        super(VoiceFixer, self).__init__()
        self._model = voicefixer_fe(channels=2, vocoder_pth=vocoder_pth, sample_rate=44100)
        self._model.load_state_dict(torch.load(pth))
        self._model.eval()

    def _load_wav_energy(self, path, sample_rate, threshold=0.95):
        wav_10k, _ = librosa.load(path, sr=sample_rate)
        stft = np.log10(np.abs(librosa.stft(wav_10k)) + 1.0)
        fbins = stft.shape[0]
        e_stft = np.sum(stft, axis=1)
        for i in range(e_stft.shape[0]):
            e_stft[-i - 1] = np.sum(e_stft[: -i - 1])
        total = e_stft[-1]
        for i in range(e_stft.shape[0]):
            if e_stft[i] < total * threshold:
                continue
            else:
                break
        return wav_10k, int((sample_rate // 2) * (i / fbins))

    def _load_wav(self, path, sample_rate, threshold=0.95):
        wav_10k, _ = librosa.load(path, sr=sample_rate)
        return wav_10k

    def _amp_to_original_f(self, mel_sp_est, mel_sp_target, cutoff=0.2):
        freq_dim = mel_sp_target.size()[-1]
        mel_sp_est_low, mel_sp_target_low = (
            mel_sp_est[..., 5: int(freq_dim * cutoff)],
            mel_sp_target[..., 5: int(freq_dim * cutoff)],
        )
        energy_est, energy_target = torch.mean(mel_sp_est_low, dim=(2, 3)), torch.mean(
            mel_sp_target_low, dim=(2, 3)
        )
        amp_ratio = energy_target / energy_est
        return mel_sp_est * amp_ratio[..., None, None], mel_sp_target

    def _trim_center(self, est, ref):
        diff = np.abs(est.shape[-1] - ref.shape[-1])
        if est.shape[-1] == ref.shape[-1]:
            return est, ref
        elif est.shape[-1] > ref.shape[-1]:
            min_len = min(est.shape[-1], ref.shape[-1])
            est, ref = est[..., int(diff // 2): -int(diff // 2)], ref
            est, ref = est[..., :min_len], ref[..., :min_len]
            return est, ref
        else:
            min_len = min(est.shape[-1], ref.shape[-1])
            est, ref = est, ref[..., int(diff // 2): -int(diff // 2)]
            est, ref = est[..., :min_len], ref[..., :min_len]
            return est, ref

    def _pre(self, model, input, cuda):
        input = input[None, None, ...]
        input = torch.tensor(input)
        input = to_tensor_cuda(input, cuda)
        sp, _, _ = model.f_helper.wav_to_spectrogram_phase(input)
        mel_orig = model.mel(sp.permute(0, 1, 3, 2)).permute(0, 1, 3, 2)
        # return models.to_log(sp), models.to_log(mel_orig)
        return sp, mel_orig

    def remove_higher_frequency(self, wav, ratio=0.95):
        stft = librosa.stft(wav)
        real, img = np.real(stft), np.imag(stft)
        mag = (real**2 + img**2) ** 0.5
        cos, sin = real / (mag + EPS), img / (mag + EPS)
        spec = np.abs(stft)  # [1025,T]
        feature = spec.copy()
        feature = np.log10(feature + EPS)
        feature[feature < 0] = 0
        energy_level = np.sum(feature, axis=1)
        threshold = np.sum(energy_level) * ratio
        curent_level, i = energy_level[0], 0
        while i < energy_level.shape[0] and curent_level < threshold:
            curent_level += energy_level[i + 1, ...]
            i += 1
        spec[i:, ...] = np.zeros_like(spec[i:, ...])
        stft = spec * cos + 1j * spec * sin
        return librosa.istft(stft)