"""Explicit source/label contracts shared by feature extraction and training."""

SOURCE_LABELS = {
    "cifake_real": 0,
    "cifake_ai": 1,
    "genimage_real": 0,
    "genimage_sd14": 1,
    "genimage_glide": 1,
    "genimage_midjourney": 1,
    "genimage_adm": 1,
    "genimage_sd15": 1,
    "genimage_wukong": 1,
    "genimage_biggan": 1,
    "genimage_vqdm": 1,
    "openfake_real": 0,
    "openfake_ai": 1,
    "community_real": 0,
    "community_ai": 1,
}
DATASETS = ("cifake", "genimage", "realcheck_mixed_v2", "realcheck_mixed_v3")
SERVING_DATASETS = {"genimage", "realcheck_mixed_v2", "realcheck_mixed_v3"}
RESERVED_UNSEEN = {"genimage_biggan", "genimage_vqdm"}


def selected_sources(dataset: str) -> frozenset[str]:
    if dataset not in DATASETS:
        raise ValueError(f"Unknown dataset: {dataset}")
    if dataset in {"realcheck_mixed_v2", "realcheck_mixed_v3"}:
        return frozenset(
            source
            for source in SOURCE_LABELS
            if not source.startswith("cifake_")
            and (dataset == "realcheck_mixed_v3" or source != "genimage_sd14")
            and source not in RESERVED_UNSEEN
        )
    return frozenset(
        s
        for s in SOURCE_LABELS
        if s.startswith(dataset + "_") and s not in RESERVED_UNSEEN
    )
