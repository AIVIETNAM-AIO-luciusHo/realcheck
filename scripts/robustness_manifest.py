"""Build robustness manifests (JSONL) for ADV-07 variants and ADV-06 external cohorts.

Each line: sample_id, path, sha256, label, source, cohort, split, group_id, parent_id,
transform. Paths are relative to the manifest file. Variants and Zalo copies keep
the parent's group_id, label and source (AC-18); other external images are roots.

Run from the repo root (outputs stay outside Git, e.g. under .cache/):
    python -m scripts.robustness_manifest variants --parents parents.csv \
        --output .cache/robustness/variants.jsonl
    python -m scripts.robustness_manifest cohort --name phone --dir <folder> \
        --output .cache/robustness/phone.jsonl

Only for evaluating a locked model; never choose a model or thresholds with these.
"""

import argparse
import csv
import hashlib
import io
import json
import os
import shutil
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps

from models.normalize import MIN_SIDE

CROP_KEEP, DOWNSCALE, BRIGHTNESS = 0.8, 0.5, 1.3
GPS_IFD = 0x8825
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
# cohort -> label every image must have; None means declared per file.
EXTERNAL_COHORTS = {"phone": 0, "ai_new": 1, "zalo": None}
# Kinds the ADV-08 helper accepts for rows without a transform of their own.
ROOT_TRANSFORM = {"kind": "original", "params": {}}
ZALO_TRANSFORM = {"kind": "zalo", "params": {}}

Variant = Callable[[Image.Image], tuple[Image.Image, str, dict]]


def _scale_keeping_min_side(scale: float, size: tuple[int, int]) -> float:
    """Shrink by ``scale`` but never below the serving minimum short side."""
    return max(scale, MIN_SIDE / min(size))


def _jpeg(quality: int) -> Variant:
    return lambda image: (image, "JPEG", {"quality": quality})


def _rotate(image: Image.Image) -> tuple[Image.Image, str, dict]:
    return image.transpose(Image.Transpose.ROTATE_90), "PNG", {}


def _crop(image: Image.Image) -> tuple[Image.Image, str, dict]:
    keep = _scale_keeping_min_side(CROP_KEEP, image.size)
    width, height = round(image.width * keep), round(image.height * keep)
    left, top = (image.width - width) // 2, (image.height - height) // 2
    return image.crop((left, top, left + width, top + height)), "PNG", {}


def _downscale(image: Image.Image) -> tuple[Image.Image, str, dict]:
    scale = _scale_keeping_min_side(DOWNSCALE, image.size)
    size = (round(image.width * scale), round(image.height * scale))
    return image.resize(size, Image.Resampling.BICUBIC), "PNG", {}


def _brightness(image: Image.Image) -> tuple[Image.Image, str, dict]:
    return ImageEnhance.Brightness(image).enhance(BRIGHTNESS), "PNG", {}


# cohort -> (locked transform record, function). Geometry and brightness are saved
# as PNG so only the named change applies; JPEG cohorts change only the quality.
VARIANTS: dict[str, tuple[dict, Variant]] = {
    "jpeg90": ({"kind": "jpeg", "params": {"quality": 90}}, _jpeg(90)),
    "jpeg70": ({"kind": "jpeg", "params": {"quality": 70}}, _jpeg(70)),
    "jpeg50": ({"kind": "jpeg", "params": {"quality": 50}}, _jpeg(50)),
    "rotate": ({"kind": "rotate", "params": {"degrees": 90}}, _rotate),
    "crop": (
        {"kind": "center_crop", "params": {"keep": CROP_KEEP, "min_side": MIN_SIDE}},
        _crop,
    ),
    "downscale": (
        {"kind": "downscale", "params": {"scale": DOWNSCALE, "min_side": MIN_SIDE}},
        _downscale,
    ),
    "brightness": (
        {"kind": "brightness", "params": {"factor": BRIGHTNESS}},
        _brightness,
    ),
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _relative(path: Path, manifest: Path) -> str:
    return Path(os.path.relpath(path.resolve(), manifest.parent.resolve())).as_posix()


def _row(
    sample_id: str,
    path: str,
    digest: str,
    cohort: str,
    parent_id: str | None,
    transform: dict,
    *,
    label: int,
    source: str,
    group_id: str,
) -> dict:
    return {
        "sample_id": sample_id,
        "path": path,
        "sha256": digest,
        "label": label,
        "source": source,
        "cohort": cohort,
        "split": "test",
        "group_id": group_id,
        "parent_id": parent_id,
        "transform": transform,
    }


def _read_csv(path: Path) -> list[dict]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    except FileNotFoundError:
        raise ValueError(f"Not found: {path}") from None


def _decode(data: bytes) -> Image.Image:
    """Decoded RGB pixels with EXIF orientation applied, as the normalizer sees them."""
    with Image.open(io.BytesIO(data)) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def _check_parents(parents_csv: Path) -> list[tuple[Path, str, dict]]:
    """Validate every parent row before anything is written; list all problems.

    Returns (path, sha256, lineage) per unique parent. A parent must decode and
    have a short side of at least MIN_SIDE px, like the API requires.
    """
    parents, problems, group_of = [], [], {}
    for number, parent in enumerate(_read_csv(parents_csv), 2):
        where = f"{parents_csv.name}:{number}"
        label, source, group_id, name = (
            (parent.get(key) or "").strip()
            for key in ("label", "source", "group_id", "path")
        )
        if label not in {"0", "1"} or not source or not group_id or not name:
            problems.append(f"{where}: need path, label 0/1, source, group_id")
            continue
        path = (parents_csv.parent / name).resolve()
        try:
            data = path.read_bytes()
            short_side = min(_decode(data).size)
        except FileNotFoundError:
            problems.append(f"{where}: file not found")
            continue
        except (OSError, Image.DecompressionBombError):
            problems.append(f"{where}: cannot be decoded")
            continue
        if short_side < MIN_SIDE:
            problems.append(f"{where}: short side {short_side} px < {MIN_SIDE} px")
            continue
        digest = sha256_bytes(data)
        if digest in group_of:
            if group_of[digest] != group_id:
                problems.append(f"{where}: same bytes as a parent in another group")
            continue
        group_of[digest] = group_id
        lineage = {"label": int(label), "source": source, "group_id": group_id}
        parents.append((path, digest, lineage))
    if problems:
        raise ValueError("Parents refused:\n" + "\n".join(problems))
    return parents


def make_variants(parents_csv: Path, output: Path) -> list[dict]:
    """Write variant images beside the manifest; return parent + variant rows.

    parents_csv columns: path (relative to the CSV), label (0/1), source, group_id.
    Exact duplicate parents must share a group and are listed once. Raises
    ValueError listing every bad parent before writing, FileExistsError if the
    image folder exists; a failure while writing removes the folder it created.
    """
    image_dir = output.parent / output.stem
    if image_dir.exists():
        raise FileExistsError(f"Variant folder already exists: {image_dir}")
    parents = _check_parents(parents_csv)
    rows = []
    image_dir.mkdir(parents=True)
    try:
        for path, digest, lineage in parents:
            data = path.read_bytes()
            if sha256_bytes(data) != digest:
                raise ValueError(f"Parent changed while running: {path.name}")
            parent_id = digest[:16]
            rows.append(
                _row(
                    parent_id,
                    _relative(path, output),
                    digest,
                    "parents",
                    None,
                    ROOT_TRANSFORM,
                    **lineage,
                )
            )
            base = _decode(data)
            for cohort, (transform, apply) in VARIANTS.items():
                image, fmt, save_kwargs = apply(base)
                buffer = io.BytesIO()
                image.save(buffer, fmt, **save_kwargs)
                suffix = ".jpg" if fmt == "JPEG" else ".png"
                target = image_dir / cohort / f"{parent_id}{suffix}"
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(buffer.getvalue())
                rows.append(
                    _row(
                        f"{parent_id}-{cohort}",
                        _relative(target, output),
                        sha256_bytes(buffer.getvalue()),
                        cohort,
                        parent_id,
                        transform,
                        **lineage,
                    )
                )
    except BaseException:
        shutil.rmtree(
            image_dir
        )  # created above by this call; leave no partial variants
        raise
    return rows


def make_cohort(
    name: str, folder: Path, output: Path, parent_manifest: Path | None = None
) -> list[dict]:
    """List one external cohort from folder/sources.csv; return root or child rows.

    sources.csv columns: file, source (device or AI tool), label; Zalo may add
    parent_file, a file name listed in parent_manifest (e.g. the phone cohort), to
    keep that image's group and source. Raises ValueError listing every problem:
    missing or wrong label/source, GPS location in EXIF, duplicates, unknown parent.
    """
    declared = {row["file"]: row for row in _read_csv(folder / "sources.csv")}
    parents = {}
    if parent_manifest is not None:
        for line in parent_manifest.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            parents[Path(row["path"]).name] = row
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    rows, problems, seen = [], [], set()
    required = EXTERNAL_COHORTS[name]
    for path in files:
        info = declared.get(path.name, {})
        label = (info.get("label") or "").strip()
        parent_file = (info.get("parent_file") or "").strip()
        parent = parents.get(parent_file) if parent_file else None
        if parent_file and (parent is None or str(parent["label"]) != label):
            problems.append(f"{path.name}: parent_file not found or label differs")
            continue
        # A Zalo copy keeps its parent's source (the camera); Zalo is the cohort.
        source = parent["source"] if parent else (info.get("source") or "").strip()
        if (
            not source
            or label not in {"0", "1"}
            or (required is not None and int(label) != required)
        ):
            expected = "0/1" if required is None else required
            problems.append(f"{path.name}: need source and label {expected}")
            continue
        data = path.read_bytes()
        try:
            with Image.open(io.BytesIO(data)) as image:
                image.load()
                if image.getexif().get_ifd(GPS_IFD):
                    problems.append(f"{path.name}: has GPS location, remove it first")
        except (OSError, Image.DecompressionBombError):
            problems.append(f"{path.name}: cannot be decoded")
            continue
        digest = sha256_bytes(data)
        if digest in seen:
            problems.append(f"{path.name}: duplicate of another file in this cohort")
        seen.add(digest)
        sample_id = f"{name}-{digest[:16]}"
        rows.append(
            _row(
                sample_id,
                _relative(path, output),
                digest,
                name,
                parent["sample_id"] if parent else None,
                ZALO_TRANSFORM if name == "zalo" else ROOT_TRANSFORM,
                label=int(label),
                source=source,
                group_id=parent["group_id"] if parent else sample_id,
            )
        )
    problems += [
        f"{f}: listed in sources.csv but not in folder"
        for f in sorted(set(declared) - {p.name for p in files})
    ]
    if problems:
        raise ValueError("Cohort not listed:\n" + "\n".join(problems))
    return rows


def write_manifest(rows: list[dict], output: Path) -> None:
    """Write JSONL once; refuses to overwrite an existing manifest."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    variants = sub.add_parser("variants", help="Parents + JPEG/geometry/brightness")
    variants.add_argument("--parents", type=Path, required=True)
    cohort = sub.add_parser("cohort", help="One external cohort: phone, ai_new, zalo")
    cohort.add_argument("--name", choices=list(EXTERNAL_COHORTS), required=True)
    cohort.add_argument("--dir", type=Path, required=True)
    cohort.add_argument("--parent-manifest", type=Path)
    for command in (variants, cohort):
        command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error(f"Output already exists: {args.output}")
    try:
        if args.command == "variants":
            rows = make_variants(args.parents, args.output)
        else:
            rows = make_cohort(args.name, args.dir, args.output, args.parent_manifest)
    except (ValueError, FileExistsError) as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    write_manifest(rows, args.output)
    print(f"Đã ghi {args.output}: {dict(Counter(row['cohort'] for row in rows))}")


if __name__ == "__main__":
    main()
