#!/usr/bin/env python3
"""dance_presets.json에 RC 병합분 추가: media_len_sec(ffprobe 실측)와 rctest 프리셋.

기존 필드(title/credit/offset 등)는 건드리지 않는다. 1회성 병합 도구.
"""
import json
import pathlib

path = pathlib.Path(__file__).parent.parent / "dance_presets.json"
p = json.load(open(path))
lens = {"응원단 fade_out.mp4": 84.5, "straykids.mp4": 22.0, "bad.mp4": 27.5}
for preset in p.values():
    if preset.get("media") in lens:
        preset.setdefault("media_len_sec", lens[preset["media"]])
p.setdefault("rctest", {"motion": "MimicNewMacarena001A545", "media": "straykids.mp4",
                        "clip": "", "seek": 0, "offset_ms": 0, "volume": 30,
                        "media_len_sec": 22.0})
json.dump(p, open(path, "w"), ensure_ascii=False, indent=2)
print("presets:", {k: v.get("media_len_sec") for k, v in p.items()})
