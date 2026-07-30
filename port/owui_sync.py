#!/usr/bin/env python3
"""
owui_sync — archive tier of the Librarian (ported for the work seat).

The working context stays lean (breadcrumbs); your vector store holds groomed detail;
Open WebUI holds the FULL human-browsable log — text AND pictures. This is the
"recall-faster" bottom tier: complete fidelity, searchable in the UI.

Config via ENV (nothing hardcoded — set these to YOUR instance):
  OWUI_URL    e.g. http://localhost:3000   (your Open WebUI)
  OWUI_KEY    your Open WebUI API key       (REQUIRED — never commit it)
  OWUI_MODEL  the model label to tag messages with (any string)

Usage:
  owui_sync.py upload <image_path>
  owui_sync.py new    --title "Session <sid>" --text-file recap.md
  owui_sync.py append --chat <id> --user "..." --assistant "..."
  owui_sync.py sync   --jsonl <transcript.jsonl> [--chat <id>] [--title ...]   # full log + images
"""
import sys
import os
import json
import uuid
import argparse
import mimetypes
try:
    import requests
except ImportError:
    sys.exit("requests missing — pip install requests (in your WSL/py venv)")

BASE  = os.environ.get("OWUI_URL", "http://localhost:3000").rstrip("/")
KEY   = os.environ.get("OWUI_KEY")            # no default — set it in your env
MODEL = os.environ.get("OWUI_MODEL", "assistant")
if not KEY:
    sys.exit("set OWUI_KEY to your Open WebUI API key (never hardcode it)")
H = {"Authorization": f"Bearer {KEY}"}


def _newid():
    return uuid.uuid4().hex


def upload_image(path):
    """Upload a local image to Open WebUI, returning (file_id, markdown_ref)."""
    ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
    with open(path, "rb") as fh:
        r = requests.post(f"{BASE}/api/v1/files/", headers=H,
                          files={"file": (os.path.basename(path), fh, ctype)}, timeout=60)
    r.raise_for_status()
    fid = r.json()["id"]
    return fid, f"![{os.path.basename(path)}](/api/v1/files/{fid}/content)"


def _msg(role, content, parent=None):
    return {"id": _newid(), "role": role, "content": content, "parentId": parent,
            "childrenIds": [], "timestamp": 0, "models": [MODEL]}


def create_chat(title, pairs):
    """Create a new Open WebUI chat from (user, assistant) message pairs; return its id."""
    msgs, order, prev = {}, [], None
    for u, a in pairs:
        um = _msg("user", u, prev); msgs[um["id"]] = um; order.append(um["id"])
        if prev: msgs[prev]["childrenIds"].append(um["id"])
        am = _msg("assistant", a, um["id"]); um["childrenIds"].append(am["id"])
        msgs[am["id"]] = am; order.append(am["id"]); prev = am["id"]
    body = {"chat": {"title": title, "models": [MODEL],
                     "messages": [msgs[i] for i in order],
                     "history": {"messages": msgs, "currentId": prev}}}
    r = requests.post(f"{BASE}/api/v1/chats/new", headers=H, json=body, timeout=120)
    r.raise_for_status()
    return r.json()["id"]


def append_chat(chat_id, user, assistant):
    """Append one user/assistant turn to an existing chat; return the assistant message id."""
    r = requests.get(f"{BASE}/api/v1/chats/{chat_id}", headers=H, timeout=120); r.raise_for_status()
    chat = r.json()["chat"]
    hist = chat["history"]; cur = hist.get("currentId")
    um = _msg("user", user, cur)
    if cur and cur in hist["messages"]:
        hist["messages"][cur].setdefault("childrenIds", []).append(um["id"])
    am = _msg("assistant", assistant, um["id"]); um["childrenIds"] = [am["id"]]
    hist["messages"][um["id"]] = um; hist["messages"][am["id"]] = am
    hist["currentId"] = am["id"]
    chat.setdefault("messages", []).extend([um, am])
    r = requests.post(f"{BASE}/api/v1/chats/{chat_id}", headers=H, json={"chat": chat}, timeout=120)
    r.raise_for_status()
    return am["id"]


def parse_transcript(path):
    """Extract (role, text) turns + local image paths from a Claude Code .jsonl transcript."""
    turns, images = [], []
    for line in open(path, encoding="utf-8"):
        try: o = json.loads(line)
        except Exception: continue
        m = o.get("message", o); role = m.get("role") if isinstance(m, dict) else None
        c = m.get("content") if isinstance(m, dict) else None
        if role not in ("user", "assistant"): continue
        text = ""
        if isinstance(c, str): text = c
        elif isinstance(c, list):
            for x in c:
                if not isinstance(x, dict): continue
                if x.get("type") == "text": text += x.get("text", "")
                if x.get("type") == "image":
                    src = x.get("source", {})
                    if src.get("type") == "path" and os.path.exists(src.get("path", "")):
                        images.append(src["path"])
        if text.strip(): turns.append((role, text.strip()))
    return turns, images


def cmd_upload(a):
    """Handle the `upload` subcommand: push one image and print its ref."""
    fid, ref = upload_image(a.path); print(f"id={fid}\n{ref}")

def cmd_new(a):
    """Handle the `new` subcommand: create a chat from a text file or inline text."""
    text = open(a.text_file, encoding="utf-8").read() if a.text_file else (a.text or "")
    print(create_chat(a.title, [("(session archive)", text)]))

def cmd_append(a):
    """Handle the `append` subcommand: add one user/assistant turn to a chat."""
    print(append_chat(a.chat, a.user, a.assistant))

def cmd_sync(a):
    """Handle the `sync` subcommand: archive a full transcript (text + images) to a chat."""
    turns, images = parse_transcript(a.jsonl)
    refs = []
    for p in dict.fromkeys(images):
        try: _, ref = upload_image(p); refs.append(ref)
        except Exception as e: refs.append(f"(image {os.path.basename(p)} failed: {e})")
    pairs, pend = [], None
    for role, txt in turns:
        if role == "user": pend = txt
        else: pairs.append((pend or "", txt)); pend = None
    if pend: pairs.append((pend, ""))
    if refs: pairs.append(("(session pictures)", "\n\n".join(refs)))
    title = a.title or f"{MODEL} session {os.path.basename(a.jsonl)[:8]}"
    if a.chat:
        for u, asst in pairs: append_chat(a.chat, u, asst)
        print(f"appended {len(pairs)} turns + {len(refs)} images to {a.chat}")
    else:
        print(f"created chat {create_chat(title, pairs)} ({len(pairs)} turns, {len(refs)} images)")


def main():
    """Parse CLI arguments and dispatch to the selected subcommand handler."""
    ap = argparse.ArgumentParser(prog="owui_sync.py")
    s = ap.add_subparsers(dest="cmd", required=True)
    u = s.add_parser("upload"); u.add_argument("path"); u.set_defaults(fn=cmd_upload)
    n = s.add_parser("new"); n.add_argument("--title", required=True)
    n.add_argument("--text"); n.add_argument("--text-file", dest="text_file"); n.set_defaults(fn=cmd_new)
    p = s.add_parser("append"); p.add_argument("--chat", required=True)
    p.add_argument("--user", required=True); p.add_argument("--assistant", required=True); p.set_defaults(fn=cmd_append)
    y = s.add_parser("sync"); y.add_argument("--jsonl", required=True)
    y.add_argument("--chat"); y.add_argument("--title"); y.set_defaults(fn=cmd_sync)
    a = ap.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
