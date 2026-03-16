from app.services.board_import.adapters.danbooru import DanbooruAdapter
from app.services.board_import.adapters.e621_like import E621LikeAdapter
from app.services.board_import.adapters.gelbooru_like import GelbooruLikeAdapter
from app.services.board_import.adapters.moebooru import MoebooruAdapter
from app.services.board_import.models import BoardPreset


def build_adapter(preset: BoardPreset):
    if preset.family == "e621-like":
        return E621LikeAdapter(preset)
    if preset.family == "danbooru-like":
        return DanbooruAdapter(preset)
    if preset.family == "gelbooru-like":
        return GelbooruLikeAdapter(preset)
    if preset.family == "moebooru-like":
        return MoebooruAdapter(preset)
    raise ValueError(f"No adapter implemented for preset {preset.name}")
