# Replay the complete fixed-checkpoint case

The exact numerical checkpoint is available as three [v0.2.4 release attachments](https://github.com/jdding/SIDDuet/releases/tag/v0.2.4) under CC BY-NC-SA 4.0. The code checkout contains the manifest, model card and license; model binaries are downloaded only for this optional replay. The weights have their own attribution and noncommercial terms; the scripts retain MIT. The provider-processed data and author's source are acquired directly upstream. This workflow does not need an author-private checkpoint path or retraining.

## Prepare an isolated runtime and inputs

Use a new work directory outside the resource checkout. The tested runtime is CPython 3.9.6 on macOS arm64, torch 2.8.0, NumPy 1.26.4, pandas 2.3.3, PyYAML 6.0.3 and tqdm 4.67.1; inference is CPU with four threads. A full pinned dependency snapshot accompanies the aggregate replay receipt. Reserve about 5 GB for downloaded/extracted inputs, checkpoint and full output scores.

```sh
export WORK=/local/new/rolemap_full_replay
mkdir -p "$WORK"
python3 -m venv "$WORK/venv"
"$WORK/venv/bin/python" -m pip install -r analysis/model_reuse/requirements-replay.txt \
  --constraint reports/model_reuse/replay_environment.txt

curl -fL https://codeload.github.com/TengShi-RUC/UniSAR/zip/1a14a246066cd1aa6ee789c57ff2c7499f3d7379 \
  -o "$WORK/UniSAR.zip"
unzip -q "$WORK/UniSAR.zip" -d "$WORK/source"

curl -fL 'https://drive.usercontent.google.com/download?id=1AgCl3Jd7UxJjGCOvUfx1Yf3SODUpyXiT&export=download&confirm=t' \
  -o "$WORK/KuaiSAR.zip"
unzip -q "$WORK/KuaiSAR.zip" -d "$WORK/provider"
```

The processed ZIP is 558,437,486 bytes, SHA256 `db75d7458f6ec5f942a4f63f03b4bb381c33af3950b7f660a145b4a97d7ab8d2`. Its `dataset/` and `vocab/` directories are at the ZIP root. The official repository supplies this download link. Keep the ZIP and extracted data local; they are not redistributed by SIDDuet. The processed files are trusted provider pickle inputs; the replay checks their expected hashes before loading them. A changed upstream file fails the identity check.

## Download the checkpoint

From the resource root, download the three fixed parts. No authentication is needed:

```sh
for part in checkpoint.part-00 checkpoint.part-01 checkpoint.part-02; do
  curl -fL "https://github.com/jdding/SIDDuet/releases/download/v0.2.4/$part" \
    -o "weights/unisar_kuaisar_v1/$part"
done
```

The manifest records each part's size and SHA256, plus the assembled checkpoint hash.
Assembly checks all of them before inference. The parts are ignored by Git and need
not be downloaded for the synthetic workflow. Their license is separate from MIT.

## Run every stage

From the resource root:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
"$WORK/venv/bin/python" analysis/model_reuse/replay_unisar.py \
  --official-root "$WORK/source/UniSAR-1a14a246066cd1aa6ee789c57ff2c7499f3d7379" \
  --processed-root "$WORK/provider" \
  --out "$WORK/result"
```

`result` must be absent. The script checks all pinned source and provider hashes, reassembles the original checkpoint, reconstructs the 320-item portability example and 9,104-item full view, scores 166,981 original requests, evaluates the public interface, reproduces 2,000-draw diagnostics and checks the previous ID-based tie policy. It verifies all 16,698,100 score values through full CSV hashes and compares every reported per-role diagnostic field. `REPLAY.json` reports successful stages, runtime, identity hashes and numerical differences. Logs and original/generated item/user/request/score rows stay in the local work directory.

The exact byte comparison is tied to the recorded CPU/runtime/batch configuration. Other devices or library versions can differ in floating-point arithmetic; this release does not certify universal cross-platform bitwise identity. The diagnostic comparison tolerance is 1e-12, declared before the receiver run. No thresholds, model weights or smoothing values are selected during replay.

To reassemble just the checkpoint with standard-library Python:

```sh
python3 -I scripts/assemble_checkpoint.py \
  --manifest weights/unisar_kuaisar_v1/CHECKPOINT.json \
  --out "$WORK/checkpoint.pt"
```

Both checkpoint parts and assembled hash are checked. Use `torch.load(...,weights_only=True)` for this tensor state. The [model card](../../weights/unisar_kuaisar_v1/MODEL_CARD.md) records origin, training scope, license and contents. Software tests require no real provider data:

```sh
python3 -I analysis/model_reuse/test_checkpoint_assembly.py
python3 analysis/model_reuse/test_count_import.py
python3 analysis/model_reuse/test_score_contract.py
```

The CPU synthetic quickstart remains `python3 -I scripts/validate_release.py`. The full model replay is optional, requires its declared dependencies and inputs, and is kept separate from that standard-library smoke test.
