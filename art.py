#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "pillow", "numpy"]
# ///
"""
Samsung Frame art prep.

Usage (macOS, with uv installed: `brew install uv`):
    uv run frame_art.py # all
    or: uv run frame_art.py --only vermeer-geographer,turner-golden-bough
    or: pip3 install requests pillow numpy && python3 frame_art.py
"""
from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import math
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageCms, ImageFilter, ImageOps

Image.MAX_IMAGE_PIXELS = None

TARGET_W, TARGET_H = 3840, 2160
TARGET_AR = TARGET_W / TARGET_H
MAX_ORIGINAL_BYTES = 450 * 1024 * 1024   # skip originals bigger than this (none on the list are)
SCORE_TOP_N = 6                          # only the N best-resolution candidates get a colour check
MATTE_IF_KEPT_BELOW = 0.62               # write a matted version if the crop keeps < 62% of the image
MAX_OUTPUT_BYTES = 19 * 1024 * 1024      # stay under SmartThings' upload limit

HERE = Path(__file__).resolve().parent
WD_API = "https://www.wikidata.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
UA = os.environ.get(
    "FRAME_ART_UA",
    "FrameArtPrep/1.0 (personal, non-commercial wall-art prep; python-requests)",
)

# ---------------------------------------------------------------------------
# The list. slug, title, artist (surname used to verify the Wikidata match),
# approximate year, extra search queries, note.
# ---------------------------------------------------------------------------
WORKS = [
    ("rubens-four-studies-head", "Four Studies of a Head of a Moor", "Rubens", 1615,
     ["Four studies of the head of a Moor"], ""),
    ("seurat-concert-europeen", "At the Concert Européen", "Seurat", 1887,
     ["Au Concert Européen Seurat"], "Conté crayon drawing (MoMA)"),
    ("feininger-steamer-odin-ii", "Steamer Odin, II", "Feininger", 1927,
     ["Dampfer Odin II Feininger"], "May not be on Commons; if missing, add it via ./manual"),
    ("redon-apparition", "Apparition", "Redon", 1905, [], ""),
    ("munch-vampire-ii", "Vampire II", "Munch", 1896, ["Vampyr II Munch"], "Print"),
    ("bocklin-villa-by-the-sea", "Villa by the Sea", "Böcklin", 1878,
     ["Villa am Meer Böcklin"], "Several versions exist; warmest/most detailed wins"),
    ("vermeer-geographer", "The Geographer", "Vermeer", 1669, [], ""),
    ("seurat-parade-de-cirque", "Circus Sideshow", "Seurat", 1888,
     ["Parade de cirque Seurat"], ""),
    ("stifter-viennese-suburbs", "View of Viennese Suburban Houses", "Stifter", 1839,
     ["Blick auf Wiener Vorstadthäuser Stifter", "Stifter Wiener Vorstadthäuser"], ""),
    ("turner-golden-bough", "The Golden Bough", "Turner", 1834, [], ""),
    ("cezanne-large-bathers", "The Large Bathers", "Cézanne", 1906,
     ["Les Grandes Baigneuses Cézanne"], "Three versions exist; warmest/most detailed wins"),
    ("degas-ballet-rehearsal-on-stage", "Ballet Rehearsal on Stage", "Degas", 1874,
     ["Répétition d'un ballet sur la scène Degas"], "Orsay version"),
    ("degas-rehearsal-of-ballet-onstage", "The Rehearsal of the Ballet Onstage", "Degas", 1874,
     ["Rehearsal of the Ballet Onstage Degas Metropolitan"], "Met version; can't reuse the file picked above"),
    ("degas-dance-class", "The Dance Class", "Degas", 1874, ["La Classe de danse Degas"], ""),
    ("manet-lady-with-fans", "Lady with Fans", "Manet", 1873, ["La Dame aux éventails Manet"],
     "You wrote Degas, but 'Woman with Fans' (1873) is Manet's"),
    ("degas-pagans-and-father", "Lorenzo Pagans and Auguste De Gas", "Degas", 1871,
     ["Degas father listening to Lorenzo Pagans playing the guitar"], ""),
    ("monet-tulip-fields-hague", "Tulip Fields near The Hague", "Monet", 1886,
     ["Champs de tulipes Hollande Monet", "Monet tulip fields 1886"], ""),
    ("monet-gare-saint-lazare", "The Gare Saint-Lazare", "Monet", 1877,
     ["La Gare Saint-Lazare Monet 1877"], "Several versions exist"),
    ("monet-bank-seine-bennecourt", "On the Bank of the Seine, Bennecourt", "Monet", 1868, [], ""),
    ("vangogh-boulevard-de-clichy", "Boulevard de Clichy", "Gogh", 1887, [], ""),
    ("vangogh-bank-of-the-seine", "Bank of the Seine", "Gogh", 1887, [], ""),
    ("vangogh-evening-landscape", "Evening Landscape", "Gogh", 1885,
     ["Avondlandschap Van Gogh 1885", "Van Gogh evening landscape 1885"], ""),
    ("vangogh-undergrowth", "Undergrowth", "Gogh", 1887, [], ""),
    ("kandinsky-swinging", "Swinging", "Kandinsky", 1925, [], ""),
    ("kandinsky-ludwigskirche", "Munich-The Ludwigskirche", "Kandinsky", 1908,
     ["Ludwigskirche in München Kandinsky"], ""),
    ("cezanne-lestaque", "The Bay of Marseilles, Seen from L'Estaque", "Cézanne", 1885,
     ["L'Estaque Cézanne"], "Several versions exist"),
    ("cezanne-ginger-jar", "Still Life with Ginger Jar, Sugar Bowl, and Oranges", "Cézanne", 1902, [], ""),
    ("cezanne-chateau-noir", "Château Noir", "Cézanne", 1903, [], ""),
    ("vermeer-astronomer", "The Astronomer", "Vermeer", 1668, [], ""),
    ("vermeer-love-letter", "The Love Letter", "Vermeer", 1670, [], ""),
    ("turner-fishing-boats-hucksters", "Fishing Boats with Hucksters Bargaining for Fish", "Turner", 1837, [], ""),
    ("turner-dogana", "The Dogano, San Giorgio, Citella, from the Steps of the Europa", "Turner", 1842,
     ["Dogana San Giorgio Citella Europa Turner"], ""),
    ("redon-deaths-head-1886", "Through the Crack a Death's-Head Was Projected", "Redon", 1886,
     ["Redon death's head 1886"], ""),
    ("munch-two-women-shore", "Two Women on the Shore", "Munch", 1898, ["To kvinner på stranden Munch"], "Woodcut"),
    ("munch-the-storm", "The Storm", "Munch", 1893, [], ""),
    ("bellows-dance-in-a-madhouse", "Dance in a Madhouse", "Bellows", 1917, [], "Lithograph"),
    ("soutine-old-mill", "The Old Mill", "Soutine", 1922, [], ""),
    ("boccioni-those-who-stay", "States of Mind III: Those Who Stay", "Boccioni", 1911,
     ["Gli addii quelli che restano Boccioni", "Those Who Stay Boccioni"], ""),
    ("redon-green-death", "The Green Death", "Redon", 1905, ["La Mort verte Redon"], ""),
    ("salucci-seaport", "A Seaport with Figures", "Salucci", 1656,
     ["Alessandro Salucci port capriccio"], ""),
]

# Public domain in Canada (artist died before 1972) but not on Commons, because
# Commons only hosts works that are also public domain in the US. Drop a file in
# ./manual/<slug>.<ext> and it is processed like the rest.
MANUAL_ONLY = [
    ("magritte-harvest", "Harvest (1943), Magritte"),
    ("magritte-empire-of-light", "The Empire of Light (1950), Magritte"),
    ("magritte-the-lovers", "The Lovers (1928), Magritte"),
    ("magritte-false-mirror", "The False Mirror (1929), Magritte"),
    ("magritte-golconda", "Golconda (1953), Magritte"),
    ("varo-the-juggler", "The Juggler / The Magician (1956), Varo"),
    ("pollock-the-flame", "The Flame (c. 1934–38), Pollock"),
    ("harlequinade-1911", "Harlequinade (1911), 'Boch': artist unclear, so add it yourself"),
]

EXCLUDE_NAME = re.compile(
    r"detail|ausschnitt|d[ée]tail|\bframe[sd]?\b|framed|cadre|rahmen|x-?ray|golden mean|overlay|"
    r"infrared|\bverso\b|reverse|r[üu]ckseite|signature|installation|exhibition|in situ|"
    r"\bwall\b|visitor|gartenlaube|\(1[5-9]\d\d\) \d+\.|\bseite\b|\bpage \d|\bplate \d",
    re.I,
)
# Gallery snapshots (perspective, glare, wall colour) vs. proper museum reproductions.
CAMERA_NAME = re.compile(
    r"^File:\(|\bDSC[_ -]?\d|\bIMG[_ -]?\d|\bP\d{7}\b|, 0\d(?:,\d)?\.(?:jpe?g|JPG)$|"
    r"hajotthu|WLA |bañistas|_\d{8}_\d{6}|photograph(?:ed)? (?:at|in)",
    re.I,
)
CAMERA_UPPER_JPG = re.compile(r"\.JPG$")  # phone/camera default extension (case-sensitive)
REPRO_NAME = re.compile(
    r"google art project|\bMET D[PT]\d|\bNGA \d|\bWGA\d|metropolitan|rijksmuseum|SK-[AC]-\d|van gogh museum|"
    r"art institute of chicago|national gallery|\bnga\b|tate|museo|mus[ée]e|munchmuseet|MM\.M\.|"
    r"kunsthaus|belvedere|thyssen|barnes|philadelphia museum|courtauld|google cultural",
    re.I,
)
GENERIC_WORDS = {
    "google", "art", "project", "oil", "canvas", "panel", "paper", "board", "cardboard", "painting",
    "museum", "museo", "musee", "gallery", "national", "collection", "institute", "chicago", "york",
    "metropolitan", "met", "rijksmuseum", "tate", "britain", "paris", "orsay", "london", "version",
    "par", "von", "van", "de", "des", "le", "la", "les", "der", "die", "das", "het", "and", "of",
    "jpg", "jpeg", "png", "tif", "tiff", "file", "by", "edit", "restored", "high", "resolution",
}
# Per-work filename patterns for look-alikes the general rules can't tell apart.
NOT_THIS = {
    "vangogh-evening-landscape": r"moonrise|rising moon|two peasants",
    "cezanne-chateau-noir": r"millstone|maison maria|sainte.?victoire",
    "monet-gare-saint-lazare": r"ext[ée]rieur|pont de l'europe",
}
OK_MIME = {"image/jpeg", "image/png", "image/tiff", "image/webp"}

SESSION = requests.Session()
SESSION.headers["User-Agent"] = UA
CACHE = HERE / "cache"
API_CACHE_FILE = CACHE / "api.json"
_api_cache: dict[str, object] = {}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
LOG_FILE = HERE / "frame_art.log"


def log(msg: str) -> None:
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")


def get_json(url: str, params: dict) -> dict:
    params = {**params, "format": "json"}
    key = url + "?" + json.dumps(params, sort_keys=True)
    if key in _api_cache:
        return _api_cache[key]  # type: ignore[return-value]
    last = None
    for attempt in range(6):
        try:
            r = SESSION.get(url, params=params, timeout=60)
            if r.status_code in (429, 503):
                time.sleep(2 ** attempt * 2)
                continue
            r.raise_for_status()
            data = r.json()
            _api_cache[key] = data
            return data
        except requests.RequestException as e:
            last = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"API request failed: {url} {params} ({last})")


def download(url: str) -> Path:
    CACHE.mkdir(exist_ok=True)
    ext = Path(url.split("?")[0]).suffix.lower() or ".img"
    dest = CACHE / (hashlib.sha1(url.encode()).hexdigest()[:16] + ext)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    tmp = dest.with_suffix(ext + ".part")
    last = ""
    for attempt in range(8):
        try:
            with SESSION.get(url, stream=True, timeout=300) as r:
                if r.status_code in (429, 503):
                    wait = r.headers.get("Retry-After", "")
                    wait = int(wait) if wait.isdigit() else min(15 * 2 ** attempt, 600)
                    last = f"HTTP {r.status_code}, waiting {wait}s"
                    log(f"rate-limited on {url[-80:]}: {last}")
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            tmp.rename(dest)
            time.sleep(2)  # be polite to upload.wikimedia.org
            return dest
        except requests.RequestException as e:
            last = str(e)
            time.sleep(10 * (attempt + 1))
    log(f"download FAILED {url}: {last}")
    raise RuntimeError(f"download failed ({last}): {url}")


# ---------------------------------------------------------------------------
# Wikidata / Commons lookup
# ---------------------------------------------------------------------------
def norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", norm(s)) if len(w) > 2 and w not in {"the", "and", "with", "from"}}


def title_match(fname: str, title: str, artist: str) -> tuple[bool, int]:
    """(all title words present, number of unrelated extra words) for a Commons filename."""
    want = words(title)
    have = words(fname) - GENERIC_WORDS - words(artist) - {"paul", "vincent", "claude", "edgar",
                                                           "johannes", "joseph", "mallord", "william",
                                                           "edvard", "odilon", "georges", "pieter",
                                                           "peter", "wassily", "umberto", "chaim"}
    have = {w for w in have if not re.fullmatch(r"[a-z]?\d+[a-z]?", w)}
    return want <= words(fname), len(have - want)


def wd_entities(ids: list[str], props: str = "claims|labels") -> dict:
    out: dict = {}
    for i in range(0, len(ids), 50):
        j = get_json(WD_API, dict(action="wbgetentities", ids="|".join(ids[i:i + 50]),
                                  props=props, languages="en|fr|de|nl|it|nb"))
        out.update(j.get("entities", {}))
    return out


def claim_values(ent: dict, prop: str) -> list:
    vals = []
    for c in ent.get("claims", {}).get(prop, []):
        dv = c.get("mainsnak", {}).get("datavalue")
        if dv:
            vals.append(dv["value"])
    return vals


def labels(ent: dict) -> list[str]:
    return [v["value"] for v in ent.get("labels", {}).values()]


def resolve_wikidata(title: str, artist: str, year: int, queries: list[str],
                     alt_titles: list[str] = ()) -> dict | None:
    qids: list[str] = []
    for q in queries:
        j = get_json(WD_API, dict(action="query", list="search", srsearch=q, srlimit=15))
        for h in j.get("query", {}).get("search", []):
            if h["title"].startswith("Q") and h["title"] not in qids:
                qids.append(h["title"])
    if not qids:
        return None
    ents = wd_entities(qids[:45])
    creator_ids = {v["id"] for e in ents.values() for v in claim_values(e, "P170") if isinstance(v, dict)}
    creators = wd_entities(sorted(creator_ids), props="labels") if creator_ids else {}
    want = words(title)
    best, best_score = None, -1e9
    for rank, qid in enumerate(qids):
        e = ents.get(qid)
        if not e or not claim_values(e, "P18"):
            continue
        creator_names = [n for v in claim_values(e, "P170") for n in labels(creators.get(v["id"], {}))]
        if artist and not any(norm(artist) in norm(n) for n in creator_names):
            continue
        years = []
        for t in claim_values(e, "P571"):
            m = re.match(r"[+-](\d+)-", t.get("time", ""))
            if m:
                years.append(int(m.group(1)))
        ydiff = min((abs(y - year) for y in years), default=4)
        if years and ydiff > 6:
            continue  # e.g. Van Gogh's 1889 "Evening Landscape with Rising Moon" vs the 1885 one
        # Jaccard, so "Evening Landscape" doesn't match "Evening Landscape with Rising Moon"
        alts = [want] + [words(t) for t in alt_titles if words(t)]
        sim = max((len(a & words(l)) / max(len(a | words(l)), 1) for l in labels(e) for a in alts), default=0)
        if sim < 0.5:
            continue
        score = sim * 6 - min(ydiff, 15) * 0.35 - rank * 0.3
        if score > best_score:
            best_score, best = score, dict(
                qid=qid, label=(labels(e) or [qid])[0], images=claim_values(e, "P18"),
                category=(claim_values(e, "P373") or [None])[0], sim=sim, ydiff=ydiff)
    return best


def commons_info(titles: list[str], thumb_w: int = 500) -> dict[str, dict]:
    out: dict[str, dict] = {}
    titles = [t if t.startswith("File:") else "File:" + t for t in titles]
    for i in range(0, len(titles), 40):
        j = get_json(COMMONS_API, dict(action="query", titles="|".join(titles[i:i + 40]),
                                       prop="imageinfo", iiprop="url|size|mime",
                                       iiurlwidth=thumb_w))
        for p in j.get("query", {}).get("pages", {}).values():
            ii = p.get("imageinfo")
            if ii:
                out[p["title"]] = ii[0]
    return out


def commons_category_files(cat: str) -> list[str]:
    j = get_json(COMMONS_API, dict(action="query", list="categorymembers",
                                   cmtitle="Category:" + cat, cmtype="file", cmlimit=100))
    return [m["title"] for m in j.get("query", {}).get("categorymembers", [])]


def commons_search(q: str, limit: int = 20) -> list[str]:
    j = get_json(COMMONS_API, dict(action="query", list="search", srsearch=q,
                                   srnamespace=6, srlimit=limit))
    return [h["title"] for h in j.get("query", {}).get("search", [])]


# ---------------------------------------------------------------------------
# Image maths
# ---------------------------------------------------------------------------
def crop_box_size(w: int, h: int) -> tuple[int, int]:
    if w / h >= TARGET_AR:
        return round(h * TARGET_AR), h
    return w, round(w / TARGET_AR)


def lab_stats(img: Image.Image) -> dict:
    a = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0
    lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    L = 116 * f[..., 1] - 16
    A = 500 * (f[..., 0] - f[..., 1])
    B = 200 * (f[..., 1] - f[..., 2])
    chroma = np.hypot(A, B)
    return dict(b=float(B.mean()), white=float(np.mean((L > 88) & (chroma < 10))), L=float(L.mean()))


def to_srgb(im: Image.Image) -> Image.Image:
    im = ImageOps.exif_transpose(im)
    icc = im.info.get("icc_profile")
    if icc and im.mode in ("RGB", "CMYK", "L"):
        try:
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            dst = ImageCms.createProfile("sRGB")
            return ImageCms.profileToProfile(im, src, dst, outputMode="RGB")
        except Exception:
            pass
    if im.mode in ("I;16", "I;16B", "I;16L", "I"):
        arr = np.asarray(im, dtype=np.float32)
        arr = arr / max(arr.max(), 1) * 255
        im = Image.fromarray(arr.astype(np.uint8), "L")
    return im.convert("RGB")


def load_image(path: Path) -> Image.Image:
    im = Image.open(path)
    if im.format == "JPEG":
        w, h = im.size
        cw, ch = crop_box_size(w, h)
        scale = max(TARGET_W / cw, TARGET_H / ch)
        if scale < 1:  # let libjpeg decode at 1/2, 1/4, 1/8 when it still covers the target
            im.draft(im.mode, (math.ceil(w * scale), math.ceil(h * scale)))
    im.load()
    return to_srgb(im)


def best_offset(im: Image.Image, cw: int, ch: int, anchor: float | None) -> tuple[int, int]:
    W, H = im.size
    horizontal = cw < W
    slack = (W - cw) if horizontal else (H - ch)
    if slack <= 0:
        return 0, 0
    if anchor is None:
        k = 256 / max(W, H)
        small = np.asarray(im.convert("L").resize((max(2, round(W * k)), max(2, round(H * k)))),
                           dtype=np.float32)
        e = np.zeros_like(small)
        e[:, 1:] += np.abs(np.diff(small, axis=1))
        e[1:, :] += np.abs(np.diff(small, axis=0))
        prof = e.sum(axis=0 if horizontal else 1)
        n = len(prof)
        win = max(1, round(n * (cw / W if horizontal else ch / H)))
        cs = np.concatenate([[0], np.cumsum(prof)])
        sums = cs[win:] - cs[:-win]
        if len(sums) <= 1 or sums.max() <= 0:
            anchor = 0.5
        else:
            pos = np.arange(len(sums))
            prior = np.exp(-(((pos - (len(sums) - 1) / 2) / (len(sums) * 0.35)) ** 2))
            mix = 0.55 * sums / sums.max() + 0.45 * prior
            anchor = int(np.argmax(mix)) / (len(sums) - 1)
    off = round(anchor * slack)
    return (off, 0) if horizontal else (0, off)


def save_jpeg(im: Image.Image, dest: Path) -> None:
    for q in (93, 90, 87, 84, 80):
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=q, subsampling=0, optimize=True,
                icc_profile=ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
        if buf.tell() <= MAX_OUTPUT_BYTES:
            break
    dest.write_bytes(buf.getvalue())


def make_crop(im: Image.Image, anchor: float | None) -> tuple[Image.Image, dict]:
    W, H = im.size
    cw, ch = crop_box_size(W, H)
    x, y = best_offset(im, cw, ch, anchor)
    out = im.crop((x, y, x + cw, y + ch)).resize((TARGET_W, TARGET_H), Image.LANCZOS)
    return out, dict(kept=cw * ch / (W * H), upscale=max(TARGET_H / ch, 1.0), src=f"{W}x{H}")


def make_matted(im: Image.Image) -> Image.Image:
    W, H = im.size
    a = np.asarray(im.resize((max(1, W // 8), max(1, H // 8))), dtype=np.float32)
    bw = max(1, min(a.shape[:2]) // 25)
    border = np.concatenate([a[:bw].reshape(-1, 3), a[-bw:].reshape(-1, 3),
                             a[:, :bw].reshape(-1, 3), a[:, -bw:].reshape(-1, 3)])
    col = np.median(border, axis=0)
    grey = col.mean()
    col = (col * 0.55 + grey * 0.45) * 0.72 + np.array([10, 6, -6])  # darker, calmer, a bit warm
    col = np.clip(col, 25, 200)
    rng = np.random.default_rng(7)
    noise = rng.normal(0, 5.5, (TARGET_H // 2, TARGET_W // 2, 1)).astype(np.float32)
    noise_img = Image.fromarray(np.clip(noise[..., 0] + 128, 0, 255).astype(np.uint8), "L")
    noise_img = noise_img.resize((TARGET_W, TARGET_H), Image.BICUBIC).filter(ImageFilter.GaussianBlur(0.8))
    n = (np.asarray(noise_img, dtype=np.float32) - 128)[..., None]
    canvas = Image.fromarray(np.clip(col + n, 0, 255).astype(np.uint8), "RGB")
    margin = 150
    s = min((TARGET_W - 2 * margin) / W, (TARGET_H - 2 * margin) / H)
    pw, ph = round(W * s), round(H * s)
    art = im.resize((pw, ph), Image.LANCZOS)
    px, py = (TARGET_W - pw) // 2, (TARGET_H - ph) // 2
    shadow = Image.new("L", (TARGET_W, TARGET_H), 0)
    shadow.paste(140, (px + 10, py + 16, px + pw + 10, py + ph + 16))
    shadow = shadow.filter(ImageFilter.GaussianBlur(22))
    canvas.paste(Image.new("RGB", canvas.size, (0, 0, 0)), (0, 0), shadow)
    canvas.paste(art, (px, py))
    return canvas


# ---------------------------------------------------------------------------
# Per-work pipeline
# ---------------------------------------------------------------------------
def gather_candidates(work: tuple, used: set[str]) -> tuple[list[dict], dict]:
    slug, title, artist, year, extra, note = work
    queries = [f"{title} {artist}".strip()] + extra
    meta: dict = {"wikidata": None, "confidence": "high"}
    wd = resolve_wikidata(title, artist, year, queries, extra_titles(work))
    titles: list[str] = []
    verified: set[str] = set()
    if wd:
        meta["wikidata"] = wd
        titles += ["File:" + f.replace("_", " ") for f in wd["images"]]
        if wd.get("category"):
            titles += [t.replace("_", " ") for t in commons_category_files(wd["category"])]
        verified = set(titles)
    else:
        meta["confidence"] = "low (no Wikidata match; Commons search only)"
    for q in queries:
        titles += commons_search(q)
    seen, uniq = set(), []
    for t in titles:
        t = t.replace("_", " ")
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    info = commons_info(uniq)
    cands = []
    for t, ii in info.items():
        if ii.get("mime") not in OK_MIME or t in used:
            continue
        if EXCLUDE_NAME.search(t) and not EXCLUDE_NAME.search(title):
            continue
        w, h = ii.get("width", 0), ii.get("height", 0)
        if min(w, h) < 900:
            continue
        if ii.get("size", 0) > MAX_ORIGINAL_BYTES:
            continue
        if work[0] in NOT_THIS and re.search(NOT_THIS[work[0]], t, re.I):
            continue
        is_verified = t in verified
        full_title, extra = title_match(t, title, artist)
        if not is_verified:
            yrs = [int(y) for y in re.findall(r"(?<![\d.])(1[4-9]\d\d)(?![\d.])", t)]
            if yrs and year and min(abs(y - year) for y in yrs) > 5:
                continue  # dated to some other version, e.g. "c. 1892" when we want 1905
            if extra > 2:
                continue
            # A plain search hit must name the artist and every word of the title.
            if (artist and norm(artist) not in norm(t)) or not (
                    full_title or any(title_match(t, q, artist)[0] for q in extra_titles(work))):
                continue
        cands.append(dict(title=t, w=w, h=h, bytes=ii.get("size", 0), mime=ii["mime"],
                          verified=is_verified, extra=extra,
                          camera=bool(CAMERA_NAME.search(t) or CAMERA_UPPER_JPG.search(t)), repro=bool(REPRO_NAME.search(t)),
                          url=ii["url"], thumb=ii.get("thumburl", ii["url"]),
                          page=ii.get("descriptionurl", ""),
                          primary=bool(wd) and t.replace("File:", "") in [f.replace("_", " ") for f in wd["images"]]))
    if not cands:
        return [], meta
    # Keep only files with the same proportions as the reference image (the
    # Wikidata image if we have one, else the biggest cluster of search hits).
    refs = [c for c in cands if c["primary"]]
    if refs:
        ref_ar = refs[0]["w"] / refs[0]["h"]
    else:
        ars = [c["w"] / c["h"] for c in cands]
        ref_ar = max(ars, key=lambda a: sum(abs(math.log(a / b)) < 0.05 for b in ars))
    cands = [c for c in cands if abs(math.log((c["w"] / c["h"]) / ref_ar)) < 0.05 or c["primary"]]
    return cands, meta


def extra_titles(work: tuple) -> list[str]:
    """Alternative titles from the extra queries, minus the artist's name."""
    artist = work[2]
    out = []
    for q in work[4]:
        ws = words(q) - GENERIC_WORDS - words(artist) - {"painting", "lithograph", "woodcut"}
        if ws:
            out.append(" ".join(sorted(ws)))
    return out


def prelim_score(c: dict) -> float:
    _, ch = crop_box_size(c["w"], c["h"])
    res = min(ch / TARGET_H, 1.6)
    s = 6 * res if res < 1 else 6 + 1.5 * (res - 1)  # below 2160px tall, every pixel counts
    s += 0.4 * c.get("verified", False) + 0.5 * c.get("repro", False) - 1.2 * c.get("camera", False)
    s -= min(0.3 * c.get("extra", 0), 1.5)
    return s


def score_all(cands: list[dict]) -> list[dict]:
    cands = sorted(cands, key=prelim_score, reverse=True)
    for c in cands[SCORE_TOP_N:]:
        c.update(b=0.0, white=0.0, L=0.0, res=min(crop_box_size(c["w"], c["h"])[1] / TARGET_H, 1.6))
        c["score"] = prelim_score(c) - 5  # unscored: only used if all of the top N fail
    for c in cands[:SCORE_TOP_N]:
        try:
            th = Image.open(download(c["thumb"]))
            th.load()
            st = lab_stats(to_srgb(th))
        except Exception as e:
            c["error"] = str(e)
            st = dict(b=0.0, white=0.5, L=50.0)
        c.update(st)
        c["res"] = min(crop_box_size(c["w"], c["h"])[1] / TARGET_H, 1.6)
        # Resolution and source quality first, then warmth; big pure-white areas cost points.
        # warmth is capped so a badly yellowed low-res scan can't beat a sharper one
        c["score"] = prelim_score(c) + 0.05 * min(st["b"], 30) - 3 * st["white"] - 0.15 * (c["mime"] == "image/tiff")
    return sorted(cands, key=lambda c: c["score"], reverse=True)


def fetch_full(c: dict) -> Path:
    return download(c["url"])


def render(slug: str, im: Image.Image, out: Path, anchor: float | None, matte: bool) -> dict:
    cropped, info = make_crop(im, anchor)
    save_jpeg(cropped, out / f"{slug}.jpg")
    info["files"] = [f"{slug}.jpg"]
    if matte and info["kept"] < MATTE_IF_KEPT_BELOW:
        save_jpeg(make_matted(im), out / f"{slug}__matted.jpg")
        info["files"].append(f"{slug}__matted.jpg")
    return info


def process_work(work: tuple, out: Path, overrides: dict, used: set[str], matte: bool) -> dict:
    slug, title, artist, year, extra, note = work
    ov = overrides.get(slug, {})
    rec: dict = dict(slug=slug, title=title, artist=artist, year=year, note=note, flags=[])
    if "local" in ov:
        im = load_image((HERE / ov["local"]).resolve())
        rec.update(render(slug, im, out, ov.get("anchor"), matte), source=ov["local"], candidates=[])
        return rec
    if "file" in ov:
        info = commons_info([ov["file"]])
        if not info:
            rec["flags"].append(f"override file not found: {ov['file']}")
            return rec
        t, ii = next(iter(info.items()))
        cands = [dict(title=t, w=ii["width"], h=ii["height"], bytes=ii.get("size", 0), mime=ii["mime"],
                      url=ii["url"], thumb=ii.get("thumburl", ii["url"]), page=ii.get("descriptionurl", ""),
                      primary=True)]
        meta = {"confidence": "override"}
    else:
        cands, meta = gather_candidates(work, used)
    rec["confidence"] = meta.get("confidence")
    if meta.get("wikidata"):
        rec["wikidata"] = meta["wikidata"]["qid"] + " · " + meta["wikidata"]["label"]
    if not cands:
        rec["flags"].append("NOT FOUND on Commons; add a file in ./manual or an override")
        return rec
    cands = score_all(cands)
    rec["candidates"] = cands
    for c in cands:  # fall back down the list if a file won't decode
        try:
            im = load_image(fetch_full(c))
        except Exception as e:
            c["error"] = f"load failed: {e}"
            log(f"{slug}: skipping {c['title']}: {e}")
            continue
        rec.update(render(slug, im, out, ov.get("anchor"), matte))
        rec["source"] = c["title"]
        rec["source_page"] = c["page"]
        used.add(c["title"])
        break
    else:
        rec["flags"].append("every candidate failed to download/decode")
        return rec
    if rec["upscale"] > 1.01:
        rec["flags"].append(f"upscaled {rec['upscale']:.2f}x (best source too small)")
    if rec["kept"] < MATTE_IF_KEPT_BELOW:
        rec["flags"].append(f"crop keeps only {rec['kept']:.0%} of the picture; see the matted version")
    if not meta.get("wikidata") and "file" not in ov:
        rec["flags"].append("low-confidence match")
    if note.startswith("UNSURE"):
        rec["flags"].append("title uncertain")
    return rec


def process_manual(out: Path, matte: bool) -> list[dict]:
    recs = []
    mdir = HERE / "manual"
    if not mdir.is_dir():
        return recs
    for p in sorted(mdir.iterdir()):
        if p.suffix.lower() not in {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}:
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", norm(p.stem)).strip("-")
        try:
            im = load_image(p)
            rec = dict(slug=slug, title=p.name, artist="", year="", note="from ./manual",
                       flags=[], candidates=[], source=str(p.relative_to(HERE)))
            rec.update(render(slug, im, out, None, matte))
            if rec["upscale"] > 1.01:
                rec["flags"].append(f"upscaled {rec['upscale']:.2f}x")
        except Exception as e:
            rec = dict(slug=slug, title=p.name, flags=[f"failed: {e}"], candidates=[])
        recs.append(rec)
    return recs


# ---------------------------------------------------------------------------
# Review page
# ---------------------------------------------------------------------------
def write_review(recs: list[dict], out: Path) -> Path:
    e = html.escape
    rows = []
    for r in recs:
        files = "".join(f'<a href="{e(f)}"><img class="out" src="{e(f)}"></a>' for f in r.get("files", []))
        flags = "".join(f'<span class="flag">{e(f)}</span>' for f in r.get("flags", []))
        cand_html = []
        for c in r.get("candidates", [])[:8]:
            chosen = " chosen" if c["title"] == r.get("source") else ""
            cand_html.append(
                f'<a class="cand{chosen}" href="{e(c.get("page", ""))}" target="_blank">'
                f'<img src="{e(c["thumb"])}" loading="lazy"><span>{c["w"]}×{c["h"]}<br>'
                f'score {c.get("score", 0):.2f} · b* {c.get("b", 0):.1f} · white {c.get("white", 0):.0%}'
                + (" · museum scan" if c.get("repro") else "") + (" · photo" if c.get("camera") else "")
                + ("" if c.get("verified", True) else " · search hit")
                + f'</span></a>')
        src = r.get("source", "")
        src_html = (f'<a href="{e(r["source_page"])}" target="_blank">{e(src)}</a>'
                    if r.get("source_page") else e(src))
        rows.append(f"""
<section>
  <h2>{e(r['slug'])} <small>{e(str(r.get('title', '')))} · {e(str(r.get('artist', '')))} {e(str(r.get('year', '')))}</small></h2>
  <div class="meta">{e(r.get('note', ''))} {flags}</div>
  <div class="meta">source: {src_html} {e(r.get('src', ''))} · kept {r.get('kept', 0):.0%} · {e(r.get('wikidata', ''))}</div>
  <div class="outs">{files}</div>
  <div class="cands">{''.join(cand_html)}</div>
</section>""")
    manual = "".join(f"<li><code>manual/{e(s)}.jpg</code> ({e(d)})</li>" for s, d in MANUAL_ONLY)
    page = f"""<!doctype html><meta charset="utf-8"><title>Frame art review</title>
<style>
body{{font:14px/1.4 -apple-system,system-ui,sans-serif;background:#1d1a16;color:#e9e2d4;margin:24px}}
h1{{font-weight:600}} h2{{font-size:16px;margin:0 0 4px}} small{{color:#a89f8e;font-weight:400}}
section{{border-top:1px solid #3a342c;padding:18px 0}}
.meta{{color:#b8ae9b;margin:2px 0}} .flag{{background:#7a4b12;color:#fff;border-radius:4px;padding:1px 6px;margin-left:6px}}
.outs img.out{{width:min(46vw,760px);margin:8px 8px 0 0;border:1px solid #3a342c}}
.cands{{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}}
.cand{{display:flex;flex-direction:column;width:150px;color:#b8ae9b;text-decoration:none;font-size:11px}}
.cand img{{width:150px;height:110px;object-fit:contain;background:#000}}
.cand.chosen{{outline:2px solid #e0b04a}}
code{{color:#e0b04a}}
</style>
<h1>Frame art review</h1>
<p>Big images are the files to upload. Small thumbnails are the Commons versions that were considered, best score first; the outlined one was used.
To use a different one, put its filename in <code>frame_art_overrides.json</code> and re-run with <code>--only &lt;slug&gt;</code>.</p>
<p>Public domain in Canada but not hosted on Commons. Drop your own scans here and re-run:</p><ul>{manual}</ul>
{''.join(rows)}"""
    path = out / "review.html"
    path.write_text(page, encoding="utf-8")
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(HERE / "frame_3840x2160"))
    ap.add_argument("--only", default="", help="comma-separated slugs")
    ap.add_argument("--no-matte", action="store_true", help="don't write the matted versions")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(exist_ok=True)
    global _api_cache
    if API_CACHE_FILE.exists():
        _api_cache = json.loads(API_CACHE_FILE.read_text())
    ov_path = HERE / "frame_art_overrides.json"
    overrides = json.loads(ov_path.read_text()) if ov_path.exists() else {}
    only = {s.strip() for s in args.only.split(",") if s.strip()}

    recs, used = [], set()
    todo = [w for w in WORKS if not only or w[0] in only]
    for i, w in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {w[0]} …", flush=True)
        try:
            r = process_work(w, out, overrides, used, not args.no_matte)
        except Exception as e:
            r = dict(slug=w[0], title=w[1], artist=w[2], year=w[3], note=w[5], flags=[f"error: {e}"])
        for f in r.get("flags", []):
            print(f"      ! {f}")
        if r.get("source"):
            print(f"      ✓ {r['source']}  ({r.get('src')}, kept {r.get('kept', 0):.0%})")
        recs.append(r)
        API_CACHE_FILE.write_text(json.dumps(_api_cache))
        write_review(recs, out)  # so a long or interrupted run can be checked as it goes
    if not only:
        recs += process_manual(out, not args.no_matte)
    review = write_review(recs, out)
    (out / "report.json").write_text(json.dumps(
        [{k: v for k, v in r.items() if k != "candidates"} for r in recs], indent=1, default=str))
    done = sum(1 for r in recs if r.get("files"))
    print(f"\n{done}/{len(recs)} done → {out}\nReview: open '{review}'")


if __name__ == "__main__":
    main()
