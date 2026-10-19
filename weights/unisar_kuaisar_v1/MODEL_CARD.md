# Fixed UniSAR checkpoint for the RoleMap case

This is a checkpoint trained in our research workflow on the UniSAR provider-processed KuaiSAR data. It is supplied to replay the RoleMap model-coverage case. It is not an original-author released checkpoint or a claim to reproduce the original paper's training results.

## Terms and attribution

The numerical checkpoint parts in this directory use **CC BY-NC-SA 4.0**, separately from the resource's MIT code and CC BY-4.0 documentation. Preserve attribution, noncommercial use and ShareAlike terms; the complete license is in `CC_BY_NC_SA_4.0.txt`. The choice follows the underlying dataset's published terms and Creative Commons' conservative guidance for sharing models trained on ShareAlike data:

- [KuaiSAR official dataset and terms](https://kuaisar.github.io/), by Zhongxiang Sun, Zihua Si, Xiaoxue Zang, Dewei Leng, Yanan Niu, Yang Song, Xiao Zhang and Jun Xu, CIKM2023, DOI10.1145/3583780.3615123.
- [UniSAR official implementation and processed-data links](https://github.com/TengShi-RUC/UniSAR), by Teng Shi and colleagues, SIGIR2024, DOI10.1145/3626772.3657811. Source commit: `1a14a246066cd1aa6ee789c57ff2c7499f3d7379`.
- [Creative Commons guidance on model sharing](https://creativecommons.org/using-cc-licensed-works-for-ai-training-2/).

Checkpoint training: Jiandong Ding's research workflow, 2026. These terms apply to rights held in the numerical artifact and preserve upstream dataset terms. They do not license upstream UniSAR source, which has no stated repository license at this review date and is not bundled here. Acquire that implementation directly from its authors. No endorsement by the original authors or data provider is implied.

## What is included

The three parts concatenate to the exact original 142,470,582-byte PyTorch tensor `state_dict`, SHA256 `67d335cdbc08a652f4eebd0e4f0493c01fa50ff388743a28cf34505ce0443de1`. Every part is below50MiB, so it can be stored without a GitHub file exceeding100MiB. Assembly verifies every part and the complete original bytes; there is no quantization or retraining.

There are212 float32 tensor entries, including shared tensor aliases, learned item/user/token embeddings and six contrastive training-only entries. The checkpoint contains no serialized model class, optimizer, raw query text, user histories or vocabulary lookup tables. The learned user embedding has22,700 rows including padding, and the item embedding has673,416 rows including padding/mask handling. Learned embeddings are not a privacy guarantee. Raw identifiers, their lookup tables and request rows are obtained from the provider by the receiver and remain outside this package.

## Training and evaluation scope

The original training log records random seed20230601, batch1024, InfoNCE sample size1024, learning rate0.001, maximum100 epochs and early stopping after25 epochs. The best validation checkpoint is epoch19 (zero based). A compact-item-vocabulary compatibility patch was used for training InfoNCE sampling. `CHECKPOINT.json` records configuration and retained training-record hashes. No additional model training was performed to build this release.

Inference uses the pinned author's implementation on CPU, batch64, four threads and evaluation dropout disabled. Six checkpoint entries belonging only to contrastive training are ignored; all prediction keys are required. NDCG/Hit average exact-score ties under evaluationv3. These values need not equal the original training logger's target-first tie convention.

The [full replay](../../analysis/model_reuse/REPLAY.md) reconstructs observations, preserves the provider's100 candidates, exports all predictions, evaluates the covered subset and reproduces the descriptive diagnostic and tie sensitivity. This checkpoint does not establish shared-SID generator coverage, causal effects, a general ranking gain or external adoption.


## Download

Exact weight parts are [v0.2.4 release attachments](https://github.com/jdding/rolemap/releases/tag/v0.2.4), not Git source blobs. [Replay instructions](../../analysis/model_reuse/REPLAY.md) download and verify them.
