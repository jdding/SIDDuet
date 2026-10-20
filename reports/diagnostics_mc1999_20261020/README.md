# 1999-draw reference precision check

The original 199-draw records remain available. Both paired-count references now also have 1999-draw estimates, with unchanged observations, maps, reference rules and seeds. The first 199 aggregate values match exactly. All twelve observed means remain below their corresponding reference mean and central 95% range.

| Dataset / map | Reference | Observed JSD | Mean, 199 | Mean, 1999 | Central 95% range, 1999 |
| --- | --- | ---: | ---: | ---: | --- |
| kuaisar / grid | band | 0.1317 | 0.1584 | 0.1583 | [0.1559, 0.1605] |
| kuaisar / rq-vae | band | 0.0728 | 0.0965 | 0.0965 | [0.0955, 0.0975] |
| kuaisar / resid-gaoq | band | 0.0840 | 0.1536 | 0.1536 | [0.1517, 0.1555] |
| kuaisar / grid | exact | 0.1317 | 0.1538 | 0.1538 | [0.1515, 0.1561] |
| kuaisar / rq-vae | exact | 0.0728 | 0.0938 | 0.0938 | [0.0928, 0.0948] |
| kuaisar / resid-gaoq | exact | 0.0840 | 0.1515 | 0.1516 | [0.1497, 0.1535] |
| qilin / grid | band | 0.0638 | 0.0778 | 0.0778 | [0.0761, 0.0796] |
| qilin / rq-vae | band | 0.0397 | 0.0575 | 0.0575 | [0.0555, 0.0595] |
| qilin / resid-gaoq | band | 0.0864 | 0.1883 | 0.1915 | [0.1581, 0.2261] |
| qilin / grid | exact | 0.0638 | 0.0755 | 0.0755 | [0.0737, 0.0773] |
| qilin / rq-vae | exact | 0.0397 | 0.0557 | 0.0558 | [0.0538, 0.0578] |
| qilin / resid-gaoq | exact | 0.0864 | 0.1849 | 0.1845 | [0.1542, 0.2158] |

The largest mean change is Qilin/ReSID-GAOQ under band matching: +0.0032151, from 0.1882976 to 0.1915127. This mapping has 101 collision groups containing 251 of 20,540 items. The other eleven mean shifts are below 0.0004 in magnitude. Reference ranges describe simulated regroupings, not confidence intervals for an observed effect.

All two-sided estimates reach the new 0.001 resolution floor; BH-adjusted values are 0.001 and BY sensitivity is 0.00245 within each separate six-comparison family. Smaller reported p values reflect the higher simulation budget. More draws add no observations, independent time windows or causal identification.

Observed JSD is 16.80–54.89% below the band reference means and 14.40–53.18% below exact-total means. Both secondary JSD weightings retain direction. The KuaiSAR/GRID item-weighted disjoint-leader contrast is +0.91 percentage points under the extended exact-total reference.

See [COMPARISON.csv](COMPARISON.csv) for unrounded 199/1999 means, reference-range endpoints, effects, p values and changes; [MC1999_RESULTS.json](MC1999_RESULTS.json) retains the full aggregate summaries. [Replay instructions](../../analysis/diagnostic_extension_20261019/protocols/MC1999_PRECISION.md) require lawful corresponding inputs; no raw observations, item/group rows, private manifest or complete draw stream is distributed here.
