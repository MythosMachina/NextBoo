from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import huggingface_hub
import numpy as np
import onnxruntime as ort
from PIL import Image

from app.settings import get_settings


logger = logging.getLogger("worker.tagger")

CAMIE_MODEL_REPO = "Camais03/camie-tagger-v2"
CAMIE_MODEL_FILENAME = "camie-tagger-v2.onnx"
CAMIE_METADATA_FILENAME = "camie-tagger-v2-metadata.json"

GENERAL_THRESHOLD = 0.35
CHARACTER_THRESHOLD = 0.85
DERIVED_NAMESPACE_THRESHOLD = 0.75
CAMIE_THRESHOLDS = {
    "general": 0.35,
    "character": 0.70,
    "copyright": 0.68,
    "artist": 0.65,
    "meta": 0.50,
    "year": 0.90,
}


@dataclass
class TagPrediction:
    rating: str
    rating_score: float
    rating_scores: dict[str, float]
    general_tags: dict[str, float]
    character_tags: dict[str, float]
    copyright_tags: dict[str, float]
    artist_tags: dict[str, float]
    meta_tags: dict[str, float]
    model_version: str


class Tagger(Protocol):
    def predict(self, image_path: Path) -> TagPrediction:
        ...


RATING_PRIORITY = {
    "general": 0,
    "sensitive": 1,
    "questionable": 2,
    "explicit": 3,
}

EXPLICIT_TAGS = {
    "sex",
    "cum",
    "cum_in_pussy",
    "cum_overflow",
    "penis",
    "vaginal",
    "pussy",
    "ejaculation",
    "fellatio",
    "anal",
    "handjob",
    "cunnilingus",
    "paizuri",
}

QUESTIONABLE_TAGS = {
    "nude",
    "completely_nude",
    "nipples",
    "uncensored",
    "topless",
    "bottomless",
    "bare_pussy",
    "pubic_hair",
    "cameltoe",
    "areola_slip",
    "sideboob",
    "underboob",
    "cleft_of_venus",
}

NON_COPYRIGHT_QUALIFIERS = {
    "male",
    "female",
    "young",
    "older",
    "child",
    "ghost",
    "adult",
    "alternate",
    "avenger",
    "archer",
    "assassin",
    "berserker",
    "caster",
    "lancer",
    "rider",
    "saber",
    "shielder",
    "alter",
    "swimsuit",
}


def extract_last_parenthetical(value: str) -> str | None:
    matches = re.findall(r"\(([^)]+)\)", value)
    if not matches:
        return None
    candidate = matches[-1].strip().lower().replace(" ", "_")
    return candidate or None


def derive_namespace_tags(
    general_tags: dict[str, float],
    character_tags: dict[str, float],
) -> tuple[dict[str, float], dict[str, float]]:
    copyright_tags: dict[str, float] = {}
    artist_tags: dict[str, float] = {}

    for name, score in character_tags.items():
        source_name = extract_last_parenthetical(name)
        if not source_name or source_name in NON_COPYRIGHT_QUALIFIERS:
            continue
        if score >= DERIVED_NAMESPACE_THRESHOLD:
            copyright_tags[source_name] = max(copyright_tags.get(source_name, 0.0), score)

    for name, score in general_tags.items():
        if name.endswith("_(artist)") and score >= GENERAL_THRESHOLD:
            artist_tags[name] = max(artist_tags.get(name, 0.0), score)
        elif name.endswith("_(series)") or name.endswith("_(copyright)"):
            copyright_tags[name] = max(copyright_tags.get(name, 0.0), score)

    return copyright_tags, artist_tags


class CamieTagger:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._session: ort.InferenceSession | None = None
        self._idx_to_tag: dict[int, str] = {}
        self._tag_to_category: dict[str, str] = {}
        self._target_size = 512
        self._model_version = "camie-tagger-v2"

    def _download_artifacts(self) -> tuple[Path, Path]:
        local_dir = Path(self.settings.model_path) / "camie-tagger-v2"
        local_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = huggingface_hub.hf_hub_download(
            repo_id=CAMIE_MODEL_REPO,
            filename=CAMIE_METADATA_FILENAME,
            local_dir=local_dir,
            local_dir_use_symlinks=False,
        )
        model_path = huggingface_hub.hf_hub_download(
            repo_id=CAMIE_MODEL_REPO,
            filename=CAMIE_MODEL_FILENAME,
            local_dir=local_dir,
            local_dir_use_symlinks=False,
        )
        return Path(metadata_path), Path(model_path)

    def load(self) -> None:
        if self._session is not None:
            return
        metadata_path, model_path = self._download_artifacts()
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        mapping = metadata["dataset_info"]["tag_mapping"]
        self._idx_to_tag = {int(key): value for key, value in mapping["idx_to_tag"].items()}
        self._tag_to_category = {key: value for key, value in mapping["tag_to_category"].items()}
        self._target_size = int(metadata["model_info"]["img_size"])
        self._session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        logger.info("camie tagger loaded repo=%s target_size=%s", CAMIE_MODEL_REPO, self._target_size)

    def _prepare_image(self, image_path: Path) -> np.ndarray:
        with Image.open(image_path) as image:
            rgb = image.convert("RGB")
            width, height = rgb.size
            aspect_ratio = width / height if height else 1.0
            if aspect_ratio > 1:
                new_width = self._target_size
                new_height = int(new_width / aspect_ratio)
            else:
                new_height = self._target_size
                new_width = int(new_height * aspect_ratio)
            resized = rgb.resize((new_width, new_height), Image.Resampling.LANCZOS)
            padded = Image.new("RGB", (self._target_size, self._target_size), (124, 116, 104))
            paste_x = (self._target_size - new_width) // 2
            paste_y = (self._target_size - new_height) // 2
            padded.paste(resized, (paste_x, paste_y))
            array = np.asarray(padded, dtype=np.float32) / 255.0
            mean = np.asarray([0.485, 0.456, 0.406], dtype=np.float32)
            std = np.asarray([0.229, 0.224, 0.225], dtype=np.float32)
            array = (array - mean) / std
            array = np.transpose(array, (2, 0, 1))
            return np.expand_dims(array, axis=0).astype(np.float32)

    def predict(self, image_path: Path) -> TagPrediction:
        self.load()
        assert self._session is not None
        input_name = self._session.get_inputs()[0].name
        outputs = self._session.run(None, {input_name: self._prepare_image(image_path)})
        logits = outputs[1] if len(outputs) >= 2 else outputs[0]
        probs = 1.0 / (1.0 + np.exp(-logits[0].astype(np.float32)))

        general_tags: dict[str, float] = {}
        character_tags: dict[str, float] = {}
        copyright_tags: dict[str, float] = {}
        artist_tags: dict[str, float] = {}
        meta_tags: dict[str, float] = {}
        rating_scores: dict[str, float] = {}

        for index, score in enumerate(probs):
            tag_name = self._idx_to_tag.get(index)
            if not tag_name:
                continue
            category = self._tag_to_category.get(tag_name, "general")
            score_value = float(score)
            if category == "rating":
                mapped_name = "general" if tag_name == "safe" else tag_name
                rating_scores[mapped_name] = score_value
                continue
            threshold = CAMIE_THRESHOLDS.get(category, GENERAL_THRESHOLD)
            if score_value < threshold:
                continue
            if category == "general":
                general_tags[tag_name] = score_value
            elif category == "character":
                character_tags[tag_name] = score_value
            elif category == "copyright":
                copyright_tags[tag_name] = score_value
            elif category == "artist":
                artist_tags[tag_name] = score_value
            elif category in {"meta", "year"}:
                meta_tags[tag_name] = score_value

        if "general" not in rating_scores:
            rating_scores["general"] = 0.0
        if "questionable" not in rating_scores:
            rating_scores["questionable"] = 0.0
        if "explicit" not in rating_scores:
            rating_scores["explicit"] = 0.0
        if "sensitive" not in rating_scores:
            rating_scores["sensitive"] = rating_scores.get("questionable", 0.0)

        mapped_rating, rating_score = decide_rating(rating_scores, general_tags | meta_tags)
        return TagPrediction(
            rating=mapped_rating,
            rating_score=rating_score,
            rating_scores=rating_scores,
            general_tags=general_tags,
            character_tags=character_tags,
            copyright_tags=copyright_tags,
            artist_tags=artist_tags,
            meta_tags=meta_tags,
            model_version=self._model_version,
        )


def build_tagger() -> Tagger:
    return CamieTagger()


def merge_predictions(predictions: list[TagPrediction]) -> TagPrediction:
    if not predictions:
        raise ValueError("At least one prediction is required")

    merged_general: dict[str, float] = {}
    merged_character: dict[str, float] = {}
    merged_copyright: dict[str, float] = {}
    merged_artist: dict[str, float] = {}
    merged_meta: dict[str, float] = {}
    selected_rating = predictions[0].rating
    selected_score = predictions[0].rating_score

    for prediction in predictions:
        if RATING_PRIORITY.get(prediction.rating, 0) > RATING_PRIORITY.get(selected_rating, 0):
            selected_rating = prediction.rating
            selected_score = prediction.rating_score
        elif prediction.rating == selected_rating:
            selected_score = max(selected_score, prediction.rating_score)

        for name, score in prediction.general_tags.items():
            merged_general[name] = max(merged_general.get(name, 0.0), score)
        for name, score in prediction.character_tags.items():
            merged_character[name] = max(merged_character.get(name, 0.0), score)
        for name, score in prediction.copyright_tags.items():
            merged_copyright[name] = max(merged_copyright.get(name, 0.0), score)
        for name, score in prediction.artist_tags.items():
            merged_artist[name] = max(merged_artist.get(name, 0.0), score)
        for name, score in prediction.meta_tags.items():
            merged_meta[name] = max(merged_meta.get(name, 0.0), score)

    merged_rating_scores: dict[str, float] = {}
    for prediction in predictions:
        for name, score in prediction.rating_scores.items():
            merged_rating_scores[name] = max(merged_rating_scores.get(name, 0.0), score)

    selected_rating, selected_score = decide_rating(merged_rating_scores, merged_general | merged_meta)

    return TagPrediction(
        rating=selected_rating,
        rating_score=selected_score,
        rating_scores=merged_rating_scores,
        general_tags=merged_general,
        character_tags=merged_character,
        copyright_tags=merged_copyright,
        artist_tags=merged_artist,
        meta_tags=merged_meta,
        model_version=predictions[0].model_version,
    )


def decide_rating(rating_scores: dict[str, float], general_tags: dict[str, float]) -> tuple[str, float]:
    general_score = rating_scores.get("general", 0.0)
    sensitive_score = rating_scores.get("sensitive", 0.0)
    questionable_score = rating_scores.get("questionable", 0.0)
    explicit_score = rating_scores.get("explicit", 0.0)
    present_tags = set(general_tags)

    if explicit_score >= 0.55 or present_tags.intersection(EXPLICIT_TAGS):
        return "explicit", max(explicit_score, questionable_score, sensitive_score)

    if present_tags.intersection(QUESTIONABLE_TAGS):
        return "questionable", max(questionable_score, sensitive_score, explicit_score)

    if questionable_score >= 0.70:
        return "questionable", questionable_score

    if sensitive_score >= 0.82 and questionable_score >= 0.20:
        return "questionable", sensitive_score

    if sensitive_score >= 0.55 and sensitive_score >= (general_score * 0.9):
        return "sensitive", sensitive_score

    return "general", max(general_score, 0.0)
