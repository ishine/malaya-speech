# Youtube videos

## download

Download youtube videos, [download-youtube.ipynb](download-youtube.ipynb).

- HTML files, manually saved youtubes pages, 
- JSON files, parsed HTML files into JSON, 

## Semisupervised ASR + Speaker Diarization

Semisupervised transcription and Unsupervised Speaker Diarization on 5k malay speakers youtube videos, youtube urls at [data](data).

## how-to

1. Semisupervised transcription using PyTorch Conformer Medium and speaker diarization using speaker vector, [process-youtube.ipynb](process-youtube.ipynb), 

2. Group by similar speakers,
  - at least 80% similarity, [combine-youtube-speakers-80.ipynb](combine-youtube-speakers-80.ipynb), [mapping-youtube-speakers-80.json](mapping-youtube-speakers-80.json).
  - at least 70% similarity, [combine-youtube-speakers-70.ipynb](combine-youtube-speakers-70.ipynb), [mapping-youtube-speakers-70.json](mapping-youtube-speakers-70.json).