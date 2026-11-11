"""Materialize the team's November expansion; reuse immutable local downloads."""

import argparse
import base64
import hashlib
import io
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

from models.normalize import normalize_image

REVISIONS = {
    "tiny": ("TheKernel01/Tiny-GenImage", "89c4fe9efd0ebc7ce5c7641ef57d578ccd639c69"),
    "openfake": ("ComplexDataLab/OpenFake", "00b2f0ae3f5f7684c4b00f794f4c500076a9355d"),
    "community": (
        "OwensLab/CommunityForensics-Small",
        "6c539a534c07917307c381f5af4053c6091b5278",
    ),
}


def records(path):
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def save_json(path, value):
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )


def payload_bytes(payload):
    if isinstance(payload, dict):
        payload = payload.get("bytes")
    if isinstance(payload, str):
        payload = payload.encode("ascii")
    if not isinstance(payload, bytes):
        raise TypeError("Missing image payload")
    try:
        with Image.open(io.BytesIO(payload)):
            return payload
    except OSError:
        return base64.b64decode(payload, validate=True)


def materialize(row, payload, root):
    data = payload_bytes(payload)
    digest = hashlib.sha256(data).hexdigest()
    if row.get("image_sha256") and row["image_sha256"] != digest:
        raise ValueError("Upstream image checksum mismatch")
    with Image.open(io.BytesIO(data)) as image:
        if (
            image.format not in {"JPEG", "PNG", "WEBP"}
            or getattr(image, "n_frames", 1) != 1
        ):
            raise ValueError("Unsupported image format or animation")
        width, height = image.size
        if width * height > 24_000_000 or max(image.size) > 10_000:
            raise ValueError("Image exceeds serving pixel limits")
        extension = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[image.format]
        normalized = normalize_image(image)
    uid = hashlib.sha256(
        repr(
            (
                row["repo"],
                row["revision"],
                row["parquet"],
                row["row_group"],
                row["offset"],
            )
        ).encode()
    ).hexdigest()
    raw = root / "raw" / row["stratum"].replace("/", "_") / (uid + extension)
    processed = root / "processed" / row["stratum"].replace("/", "_") / (uid + ".jpg")
    for path, contents in ((raw, data), (processed, normalized.jpeg)):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_bytes() != contents:
            raise ValueError("Refusing to overwrite a changed image")
        path.write_bytes(contents)
    return {
        **row,
        "uid": uid,
        "raw_path": raw.resolve().as_posix(),
        "filepath": processed.resolve().as_posix(),
        "raw_sha256": digest,
        "normalized_sha256": hashlib.sha256(normalized.jpeg).hexdigest(),
        "pixel_sha256": hashlib.sha256(normalized.image.tobytes()).hexdigest(),
        "width": width,
        "height": height,
        "status": "candidate",
    }


def metadata(source, group, columns):
    return source.read_row_group(group, columns=columns).to_pylist()


def acquire(output, existing, catalogue):
    import pyarrow.parquet as pq
    from huggingface_hub import HfApi, HfFileSystem, hf_hub_download

    output.mkdir(parents=True, exist_ok=True)
    journal = output / "download-journal.jsonl"
    complete = {r["uid"]: r for r in records(journal)} if journal.exists() else {}
    fs = HfFileSystem()
    rng = random.Random(42)
    old_rows = [r for r in records(existing / "provenance.jsonl") if r.get("raw_path")]
    # Older valid reserve images are reusable; their previous selection is not a new split.
    for row in old_rows:
        if row["uid"] in complete:
            continue
        row = {
            **row,
            "status": "candidate",
            "origin": "reused_20261108",
            "upstream_split": "train",
        }
        row["raw_path"] = (existing / row["raw_path"]).resolve().as_posix()
        row["filepath"] = (existing / row["filepath"]).resolve().as_posix()
        if not Path(row["raw_path"]).is_file() or not Path(row["filepath"]).is_file():
            raise FileNotFoundError("Prior acquisition is incomplete")
        complete[row["uid"]] = row

    # Read lightweight OpenFake type/prompt metadata for the reused training images.
    openfake = defaultdict(list)
    for row in complete.values():
        if row.get("stratum", "").startswith("openfake/"):
            openfake[(row["parquet"], row["row_group"])].append(row)
    repo, revision = REVISIONS["openfake"]
    for i, ((filename, group), members) in enumerate(openfake.items(), 1):
        if all("type" in r for r in members):
            continue
        with fs.open(
            f"datasets/{repo}@{revision}/{filename}", block_size=256 * 1024
        ) as stream:
            source = pq.ParquetFile(stream)
            info = metadata(source, group, ["type", "prompt", "model"])
            for row in members:
                row.update(info[row["offset"]])
        if i % 10 == 0:
            print(f"OpenFake metadata {i}/{len(openfake)}", flush=True)
    save_json(output / "source-revisions.json", REVISIONS)
    with journal.open("w", encoding="utf-8") as stream:
        for row in complete.values():
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Additional diffusion models, matched face/landscape AI, and all 35 VISION devices.
    wanted = {f"data/HFCF_small_{n}.parquet" for n in (0, 2, 52, 74, 75, 114, 115)}
    known = defaultdict(list)
    for row in records(catalogue):
        if (
            row["repo"] == REVISIONS["community"][0]
            and row["parquet"] in wanted
            and row.get("split") == "train"
            and (row["label"] == 1 or row.get("model_name") == "VISION")
        ):
            known[row["parquet"]].append(row)
    community_files = set(known)
    community_files.update(
        r["parquet"] for r in complete.values() if r["stratum"].startswith("community/")
    )
    repo, revision = REVISIONS["community"]
    for filename in sorted(community_files):
        previous = existing / "parquet-cache" / "community" / filename
        local = (
            previous
            if previous.is_file()
            else Path(
                hf_hub_download(
                    repo,
                    filename,
                    repo_type="dataset",
                    revision=revision,
                    local_dir=output / "parquet-cache" / "community",
                )
            )
        )
        source = pq.ParquetFile(local, memory_map=True)
        info = {}
        for group in range(source.num_row_groups):
            for offset, row in enumerate(
                metadata(
                    source,
                    group,
                    [
                        "model_name",
                        "real_source",
                        "architecture",
                        "prompt",
                        "image_name",
                        "nsfw_flag",
                        "label",
                        "split",
                    ],
                )
            ):
                info[group, offset] = row
        for row in complete.values():
            if row.get("repo") == repo and row["parquet"] == filename:
                row.update(info[row["row_group"], row["offset"]])
        pool = known.get(filename, [])
        # Metadata-balanced reserve, at most 18 per diffusion tool; 40 per device.
        rng.shuffle(pool)
        counts = Counter()
        pending = defaultdict(dict)
        for row in pool:
            fields = info[row["row_group"], row["offset"]]
            model = fields["model_name"]
            if fields["label"] == 0:
                key, limit = fields["image_name"].split("_")[0], 40
            else:
                key = model
                limit = (
                    180
                    if fields["real_source"].lower() in {"ffhq", "landscape"}
                    else 18
                )
            if counts[key] >= limit:
                continue
            counts[key] += 1
            uid = hashlib.sha256(
                repr(
                    (repo, revision, filename, row["row_group"], row["offset"])
                ).encode()
            ).hexdigest()
            if uid not in complete:
                pending[row["row_group"]][row["offset"]] = {
                    **row,
                    **fields,
                    "uid": uid,
                    "stratum": "community/vision"
                    if fields["label"] == 0
                    else "community/ai",
                    "source": "community_real"
                    if fields["label"] == 0
                    else "community_ai",
                    "upstream_split": "train",
                }
        with journal.open("a", encoding="utf-8") as log:
            for group, members in pending.items():
                offset = 0
                for batch in source.iter_batches(
                    batch_size=16, row_groups=[group], columns=["image_data"]
                ):
                    for payload in batch.column(0).to_pylist():
                        row = members.get(offset)
                        offset += 1
                        if row is None:
                            continue
                        try:
                            row = materialize(row, payload, output)
                        except (
                            TypeError,
                            ValueError,
                            OSError,
                            SyntaxError,
                            Image.DecompressionBombError,
                        ) as exc:
                            # Disk errors must stop the run rather than reject valid data.
                            if isinstance(exc, OSError) and exc.errno is not None:
                                raise
                            row = {**row, "status": "rejected", "reason": str(exc)}
                        complete[row["uid"]] = row
                        log.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"Community {filename}: {len(complete)} records", flush=True)

    repo, revision = REVISIONS["openfake"]
    files = [
        s.rfilename for s in HfApi().dataset_info(repo, revision=revision).siblings
    ]
    for config, prefix, per_label in (
        ("core_test", "core/test-", 520),
        ("reddit_test", "reddit/test-", 420),
    ):
        selected_files = sorted(
            f for f in files if f.startswith(prefix) and f.endswith(".parquet")
        )
        # Oversample before size/dedup checks, across every upstream evaluation shard.
        reserve_per_file = max(
            25, (per_label * 2 + len(selected_files) - 1) // len(selected_files)
        )
        for filename in selected_files:
            file_marker = (
                output / "completed-eval-files" / (Path(filename).name + ".json")
            )
            if file_marker.exists():
                continue
            with fs.open(
                f"datasets/{repo}@{revision}/{filename}", block_size=1024 * 1024
            ) as stream:
                source = pq.ParquetFile(stream)
                options = []
                # shortcut: a fixed row-group frame bounds transfer; expand it for a full benchmark.
                sampled_group = (
                    int(hashlib.sha256(filename.encode()).hexdigest()[:8], 16)
                    % source.num_row_groups
                )
                frame_groups = []
                for step in range(source.num_row_groups):
                    group = (sampled_group + step) % source.num_row_groups
                    frame_groups.append(group)
                    for offset, row in enumerate(
                        metadata(
                            source,
                            group,
                            [
                                "label",
                                "model",
                                "type",
                                "prompt",
                                "row_id",
                                "image_sha256",
                            ],
                        )
                    ):
                        if row["label"] not in {"real", "fake"}:
                            raise ValueError("Unknown OpenFake label")
                        options.append(
                            {
                                **row,
                                "repo": repo,
                                "revision": revision,
                                "parquet": filename,
                                "row_group": group,
                                "offset": offset,
                                "upstream_split": "test",
                                "stratum": config,
                                "source": "openfake_real"
                                if row["label"] == "real"
                                else "openfake_ai",
                                "label": int(row["label"] == "fake"),
                            }
                        )
                    available = Counter(row["label"] for row in options)
                    if all(available[label] >= reserve_per_file for label in (0, 1)):
                        break
                rng.shuffle(options)
                counts = Counter()
                pending = defaultdict(dict)
                for row in options:
                    if counts[row["label"]] >= reserve_per_file:
                        continue
                    counts[row["label"]] += 1
                    pending[row["row_group"]][row["offset"]] = row
                with journal.open("a", encoding="utf-8") as log:
                    for group, members in pending.items():
                        offset = 0
                        for batch in source.iter_batches(
                            batch_size=16, row_groups=[group], columns=["image"]
                        ):
                            for payload in batch.column(0).to_pylist():
                                row = members.get(offset)
                                offset += 1
                                if row is None:
                                    continue
                                row["uid"] = hashlib.sha256(
                                    repr(
                                        (repo, revision, filename, group, row["offset"])
                                    ).encode()
                                ).hexdigest()
                                if row["uid"] in complete:
                                    continue
                                try:
                                    row = materialize(row, payload, output)
                                except (
                                    TypeError,
                                    ValueError,
                                    OSError,
                                    SyntaxError,
                                    Image.DecompressionBombError,
                                ) as exc:
                                    if (
                                        isinstance(exc, OSError)
                                        and exc.errno is not None
                                    ):
                                        raise
                                    row = {
                                        **row,
                                        "status": "rejected",
                                        "reason": str(exc),
                                    }
                                complete[row["uid"]] = row
                                log.write(json.dumps(row, ensure_ascii=False) + "\n")
            file_marker.parent.mkdir(parents=True, exist_ok=True)
            save_json(
                file_marker,
                {
                    "file": filename,
                    "sampled": sum(counts.values()),
                    "row_groups": frame_groups,
                    "sampling": "seeded row-group frame; not a full upstream benchmark",
                },
            )
            print(f"OpenFake {filename}: {sum(counts.values())} sampled", flush=True)
    # Persist the enriched metadata as well as newly downloaded images.
    with (output / "pool.jsonl").open("w", encoding="utf-8") as stream:
        for row in complete.values():
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = {
        "records": len(complete),
        "by_status": dict(Counter(r["status"] for r in complete.values())),
        "by_stratum": dict(
            Counter(
                r["stratum"] for r in complete.values() if r["status"] == "candidate"
            )
        ),
        "revisions": REVISIONS,
        "test_scored": False,
    }
    save_json(output / "download-summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--existing",
        type=Path,
        default=Path("../outputs/realcheck-domain-expansion/acquired-01"),
    )
    parser.add_argument(
        "--catalogue",
        type=Path,
        default=Path(
            "../outputs/realcheck-backend-mvp-run/expansion-catalogue.local.jsonl"
        ),
    )
    args = parser.parse_args()
    acquire(args.output, args.existing, args.catalogue)


if __name__ == "__main__":
    main()
