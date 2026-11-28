#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# # Pinned: the fork renamed its package (samsungtvws -> samsungframetv) in Nov 2026.
# dependencies = ["samsungframetv @ git+https://github.com/NickWaterton/samsung-tv-ws-api.git@bd8fd17aaa5e64eb361cb757b232a8925c22168f"]
# ///
"""
Uploads everything in art/ to the Frame's My Photos over Wi-Fi: no SmartThings app,
no 50-image picker, edge to edge (no mat). Remembers what it sent (temp/uploaded.json),
so later runs only send new or changed images.

    uv run upload.py --tv 192.168.1.50   # first run: accept the prompt on the TV
    uv run upload.py                     # later runs reuse the saved address
    uv run upload.py --dry-run           # show what would happen, without connecting
    uv run upload.py --list              # count what's in My Photos
    uv run upload.py --prune             # also remove uploads whose file left art/
    uv run upload.py --remove-others     # clear My Photos items this script didn't send
                                         # (e.g. earlier SmartThings uploads); asks first
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ART = HERE / "art"
TEMP = HERE / "temp"
STATE = TEMP / "uploaded.json"     # file name -> {sha1, content_id}
CONF = TEMP / "tv.json"            # remembered TV address
TOKEN = TEMP / "tv-token.txt"      # pairing token, so the TV only asks once
MY_PHOTOS = "MY-C0002"             # the TV's "My Photos" category
FILE_TYPES = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG"}


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return default


def save_json(path: Path, data) -> None:
    TEMP.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")


def sha1(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def connect(host: str):
    try:
        from samsungframetv import SamsungTVWS
    except ImportError:
        try:  # older installs of the same library
            from samsungtvws import SamsungTVWS
        except ImportError:
            sys.exit("Needs the samsungframetv library: run with `uv run upload.py`, or\n"
                     "pip3 install git+https://github.com/NickWaterton/samsung-tv-ws-api.git")
    TEMP.mkdir(exist_ok=True)
    hint = "" if TOKEN.exists() else " (first time: accept the prompt on the TV with the remote)"
    print(f"Connecting to {host}{hint}…", flush=True)
    tv = SamsungTVWS(host=host, port=8002, token_file=str(TOKEN), timeout=60, name="FrameArt")
    try:
        art = tv.art(timeout=60)  # newer versions default to 5s, too short for multi-MB uploads
    except TypeError:
        art = tv.art()
    try:
        ok = art.supported()
    except Exception as e:
        sys.exit(f"Couldn't reach the TV at {host}: {e}\n"
                 "Check the TV is on (TV or Art Mode), on the same network, and the address is right.")
    if not ok:
        sys.exit("This TV doesn't report Art Mode support.")
    return art


def my_photos(art) -> set[str]:
    items = art.available(MY_PHOTOS) or []
    return {i.get("content_id") for i in items if isinstance(i, dict) and i.get("content_id")}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tv", help="the TV's IP address (remembered after the first run)")
    ap.add_argument("--dry-run", action="store_true", help="show the plan without connecting")
    ap.add_argument("--list", action="store_true", help="count what's in My Photos and stop")
    ap.add_argument("--prune", action="store_true",
                    help="delete photos this script uploaded whose file is no longer in art/")
    ap.add_argument("--remove-others", action="store_true",
                    help="delete My Photos items this script didn't upload (asks for confirmation)")
    args = ap.parse_args()

    conf = load_json(CONF, {})
    host = args.tv or conf.get("host")
    if not host and not args.dry_run:
        sys.exit("Give the TV's address once: uv run upload.py --tv 192.168.x.x\n"
                 "(On the TV: Settings > General > Network > Network Status, or check your router.)")
    if args.tv:
        save_json(CONF, {"host": args.tv})

    state: dict[str, dict] = load_json(STATE, {})
    files = sorted(p for p in ART.iterdir() if p.suffix.lower() in FILE_TYPES and not p.name.startswith(".")) \
        if ART.is_dir() else []
    if not files:
        sys.exit("Nothing in art/ to upload.")
    hashes = {p.name: sha1(p) for p in files}

    # A renamed file with identical content keeps its upload instead of being sent twice.
    by_hash = {v["sha1"]: k for k, v in state.items()}
    for name, h in hashes.items():
        old = by_hash.get(h)
        if name not in state and old and old not in hashes:
            state[name] = state.pop(old)
            print(f"  renamed: {old} -> {name}")

    if args.dry_run:
        new = [n for n in hashes if n not in state]
        changed = [n for n in hashes if n in state and state[n]["sha1"] != hashes[n]]
        gone = [n for n in state if n not in hashes]
        print(f"{len(files)} images in art/: {len(new)} new, {len(changed)} changed, "
              f"{len(files) - len(new) - len(changed)} already uploaded (per temp/uploaded.json)")
        for n in new + changed:
            print(f"  would upload: {n}")
        for n in gone:
            print(f"  no longer in art/: {n}" + ("  (would delete from TV)" if args.prune else "  (--prune deletes it)"))
        return

    art = connect(host)
    on_tv = my_photos(art)
    ours = {v["content_id"] for v in state.values()}
    print(f"My Photos on the TV: {len(on_tv)} ({len(on_tv & ours)} uploaded by this script)")
    if args.list:
        return
    others = sorted(on_tv - ours)
    if args.remove_others and others:
        print(f"\n{len(others)} photo(s) in My Photos weren't uploaded by this script "
              "(e.g. ones added with the SmartThings app, or your own photos).")
        if input("Delete them from the TV? Type yes to confirm: ").strip().lower() == "yes":
            art.delete_list(others)
            on_tv -= set(others)
            print(f"Deleted {len(others)}.")
        else:
            print("Left them alone.")
    elif others:
        print(f"({len(others)} other photo(s) in My Photos, e.g. from the SmartThings app; "
              "--remove-others clears them to avoid duplicates)")

    sent = skipped = failed = 0
    for i, p in enumerate(files, 1):
        rec = state.get(p.name)
        if rec and rec["sha1"] == hashes[p.name] and rec["content_id"] in on_tv:
            skipped += 1
            continue
        if rec and rec["content_id"] in on_tv:  # file changed since last upload: replace it
            try:
                art.delete(rec["content_id"])
            except Exception as e:
                print(f"  ! couldn't remove the old version of {p.name}: {e}")
        print(f"[{i}/{len(files)}] {p.name} …", end=" ", flush=True)
        try:
            cid = art.upload(p.read_bytes(), file_type=FILE_TYPES[p.suffix.lower()],
                             matte="none", portrait_matte="none")
        except Exception as e:
            print(f"failed: {e}")
            failed += 1
            continue
        if not cid:
            print("failed: the TV didn't return an id (storage full?)")
            failed += 1
            continue
        state[p.name] = {"sha1": hashes[p.name], "content_id": cid}
        save_json(STATE, state)  # after every file, so an interrupted run loses nothing
        print(f"ok ({cid})")
        sent += 1
        time.sleep(1)

    removed = 0
    gone = [n for n in state if n not in hashes]
    if gone and args.prune:
        ids = [state[n]["content_id"] for n in gone if state[n]["content_id"] in on_tv]
        if ids:
            art.delete_list(ids)
        for n in gone:
            print(f"  removed from TV: {n}")
            del state[n]
        removed = len(gone)
    elif gone:
        print(f"{len(gone)} uploaded photo(s) are no longer in art/; --prune removes them from the TV.")
    save_json(STATE, state)
    print(f"\nDone: {sent} uploaded, {skipped} already there, {failed} failed"
          + (f", {removed} removed" if removed else "") + ".")
    if failed:
        print("Re-run to retry the failures; finished uploads aren't sent again.")


if __name__ == "__main__":
    main()
