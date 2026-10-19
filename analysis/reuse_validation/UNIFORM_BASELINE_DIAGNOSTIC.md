# Posthoc uniform baseline diagnostic

This is a **posthoc baseline-completeness diagnostic**, computed after the audit results were available. It does not change the approved protocol, frozen estimators, original primary comparison, confidence interval, or pass rule. No training, role shuffle, hyperparameter sweep, model reselection or new inferential gate was run.

For a fixed collision group g, the no-fit predictor is p(i|g)=1/|g|. Its loss on any exposed member is log(|g|). I independently averaged that value equally across a request's exposed collision groups, then averaged requests within each role and the two roles equally, using the exact frozen mapping and original tuning/audit rows. Singleton/no-collision exclusions are unchanged.

| View | Uniform tuning macro loss | Selected blind tuning loss | Uniform audit macro loss | Selected blind audit loss | Selected aware audit loss |
|---|---:|---:|---:|---:|---:|
| GenSAR shared2, PRIMARY | 1.72011833 | 1.67949646 | 1.74835339 | 1.70561434 | 1.69292816 |
| GenSAR semantic complete | 1.23529914 | 1.22094415 | 1.26311611 | 1.25405768 | 1.25048796 |
| GenSAR collaborative complete | 1.68702421 | 1.68561164 | 1.72302845 | 1.72372697 | 1.72374806 |
| GAOQ depth1 | 6.46438380 | 6.36732918 | 6.46437737 | 6.38351546 | 6.37723558 |
| GAOQ depth2 | 2.30787912 | 2.26409363 | 2.30723385 | 2.27096158 | 2.26251940 |
| GAOQ full3 | N/A | N/A | N/A | N/A | N/A |

Uniform is worse on tuning macro loss than the selected blind candidate in every non-control view. Consequently, offering alpha=infinity in the fixed macro-role tuning comparison would not change any of these blind choices. This is a comparison of already-computed point losses, not a retrospective replacement of the frozen selection.

For the primary audit, uniform-to-aware loss differences are search +0.01541218, recommendation +0.09543828 and macro +0.05542523 nats. The aware point loss is below uniform for both roles. Uniform does beat the selected pooled model for SEARCH ALONE: 1.69861323 versus 1.70498445 nats. The pooled model was selected by the declared macro objective, so it should not be called the best roleblind predictor for every individual role. The selected aware search loss is lower still, at 1.68320105. These uniform comparisons have no newly calculated interval; the original primary interval applies only to selected pooled minus selected aware.

Uniform slightly beats both fitted collaborative-complete predictors on audit macro loss. That is consistent with the prior review's near-null/full-view limitation and prevents a universal claim that count fitting helps every view. It does not overturn the prespecified shared-prefix result.

The practical primary interpretation therefore survives this diagnostic: the observed benefit is not merely a comparison against a model worse than an obvious no-fit predictor on the headline macro metric. Including a transparent uniform row is a useful completeness improvement in the supporting report; it is not a new success criterion.

The narrow model-choice wording also survives: the **selected role-aware strategy had lower retrospective allocation forecast loss than the selected roleblind strategy from the declared grid**. Equal alpha grids do not equalize effective shrinkage, because the prior fraction is alpha/(n_role+alpha) for separate counts and alpha/(n_search+n_rec+alpha) for pooled counts. Role conditioning changes empirical member frequencies and effective regularization together. The result supports the tested estimator choice; it does not isolate a causal role signal, prove how much improvement comes from composition rather than shrinkage, or establish superiority to all possible roleblind predictors. The original RSD/ranking/semantic-truth limits remain. No additional sweep is necessary to state this bounded result honestly.
