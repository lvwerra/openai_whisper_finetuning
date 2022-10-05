import os
import numpy as np

import torch
import torchaudio

# import pandas as pd
import whisper
import torchaudio.transforms as at

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


class LibriSpeech(torch.utils.data.Dataset):
    """
    A simple class to wrap LibriSpeech and
    trim/pad the audio to 30 seconds.
    It will drop the last few seconds
    of a very small portion of the utterances.
    """

    def __init__(self, split="test-clean", device=DEVICE):
        self.dataset = torchaudio.datasets.LIBRISPEECH(
            root=os.path.expanduser("./data/"),
            url=split,
            download=True,
        )
        self.device = device
        self.dataset = [self.dataset[i] for i in range(10)]

    def __len__(self):
        return len(self.dataset)

    def __getitem__(self, item):
        audio, sample_rate, text, _, _, _ = self.dataset[item]
        assert sample_rate == 16000
        audio = whisper.pad_or_trim(audio.flatten()).to(self.device)
        mel = whisper.log_mel_spectrogram(audio)

        return (mel, text)


class LibriSpeechTraining(torch.utils.data.Dataset):
    def __init__(self, split="test-clean", tokenizer=None, sample_rate=16000) -> None:
        super().__init__()

        self.dataset = torchaudio.datasets.LIBRISPEECH(
            root=os.path.expanduser("./data/"),
            url=split,
            download=True,
        )
        self.dataset = [self.dataset[i] for i in range(100)]
        self.sample_rate = sample_rate
        self.tokenizer = tokenizer

    def load_wave(wave_path, sample_rate: int = 16000) -> torch.Tensor:
        waveform, sr = torchaudio.load(wave_path, normalize=True)
        if sample_rate != sr:
            waveform = at.Resample(sr, sample_rate)(waveform)
        return waveform

    def __len__(self):
        return len(self.dataset)

    def __getitem__(self, id):
        audio, sample_rate, text, _, _, _ = self.dataset[id]

        audio = whisper.pad_or_trim(audio.flatten())
        mel = whisper.log_mel_spectrogram(audio)

        text = [
            *self.tokenizer.sot_sequence_including_notimestamps
        ] + self.tokenizer.encode(text)
        labels = text[1:] + [self.tokenizer.eot]

        return {"input_ids": mel, "labels": labels, "dec_input_ids": text}


class WhisperDataCollatorWhithPadding:
    def __call__(sefl, features):
        input_ids, labels, dec_input_ids = [], [], []
        for f in features:
            input_ids.append(f["input_ids"])
            labels.append(f["labels"])
            dec_input_ids.append(f["dec_input_ids"])

        input_ids = torch.concat([input_id[None, :] for input_id in input_ids])

        label_lengths = [len(lab) for lab in labels]
        dec_input_ids_length = [len(e) for e in dec_input_ids]
        max_label_len = max(label_lengths + dec_input_ids_length)

        labels = [
            np.pad(lab, (0, max_label_len - lab_len), "constant", constant_values=-100)
            for lab, lab_len in zip(labels, label_lengths)
        ]
        dec_input_ids = [
            np.pad(e, (0, max_label_len - e_len), "constant", constant_values=50257)
            for e, e_len in zip(dec_input_ids, dec_input_ids_length)
        ]  # 50257 is eot token id

        batch = {"labels": labels, "dec_input_ids": dec_input_ids}

        batch = {
            k: torch.tensor(np.array(v), requires_grad=False) for k, v in batch.items()
        }
        batch["input_ids"] = input_ids

        return batch


if __name__ == "__main__":
    # dataset = LibriSpeech("test-clean")
    # loader = torch.utils.data.DataLoader(dataset, batch_size=16)
    # sample_mel, sample_text = dataset[0]
    # print(sample_mel.shape)
    # print(sample_text)
    model = whisper.load_model("tiny")
    wtokenizer = whisper.tokenizer.get_tokenizer(True, language="en")
    dataset = LibriSpeechTraining("test-clean", wtokenizer)
    loader = torch.utils.data.DataLoader(
        dataset, batch_size=1, collate_fn=WhisperDataCollatorWhithPadding()
    )
    for b in loader:
        print(b["labels"].shape)
        print(b["input_ids"].shape)
        print(b["dec_input_ids"].shape)

        for token, dec in zip(b["labels"], b["dec_input_ids"]):
            token[token == -100] = wtokenizer.eot
            text = wtokenizer.decode(token, skip_special_tokens=False)
            print(text)

            dec[dec == -100] = wtokenizer.eot
            text = wtokenizer.decode(dec, skip_special_tokens=False)
            print(text)
        break
    # with torch.no_grad():
    #     audio_features = model.encoder(b["input_ids"])
    #     input_ids = b["input_ids"]
    #     labels = b["labels"].long()
    #     dec_input_ids = b["dec_input_ids"].long()

    #     audio_features = model.encoder(input_ids)
    #     print(dec_input_ids)
    #     print(input_ids.shape, dec_input_ids.shape, audio_features.shape)
    #     print(audio_features.shape)
    #     print()
    # # out = model.decoder(dec_input_ids, input_ids)
    # out = model.decoder(dec_input_ids, audio_features)
    # print(out.shape)
    # print(out.view(-1, out.size(-1)).shape)
    # print(b["labels"].view(-1).shape)
    # tokens = torch.argmax(out, dim=2)
    # for token in tokens:
    #     token[token == -100] = wtokenizer.eot
    #     text = wtokenizer.decode(token, skip_special_tokens=True)
    #     print(text)