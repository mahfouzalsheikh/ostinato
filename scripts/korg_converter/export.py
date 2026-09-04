"""Read actual Win32 tree labels and verify each official converter export."""

import json
import os
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(os.environ["CONVERTER_WORKSPACE"]).resolve()
CONTAINER = os.environ["CONVERTER_CONTAINER"]


def run(*args):
    return subprocess.run(
        ["docker", "exec", CONTAINER, *args],
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    ).stdout.strip()


def ui(*args):
    return run("wine", "/opt/converter-ui.exe", *args)


def windows():
    result = []
    for line in ui("list").splitlines():
        m = re.fullmatch(r"(\w+) id=(-?\d+) (\S+) ?(.*)", line.strip())
        if m:
            result.append(dict(handle=m[1], id=int(m[2]), cls=m[3], text=m[4]))
    return result


def click_toolbar(x):
    run("xdotool", "mousemove", str(x), "291", "click", "1")
    time.sleep(0.06)


def dialog(title):
    for _attempt in range(15):
        rows = windows()
        if any(row["text"] == title for row in rows):
            return rows
        time.sleep(0.1)
    raise RuntimeError("missing dialog " + title)


def field(rows, cls, id):
    return next(row for row in rows if row["cls"] == cls and row["id"] == id)


def tree(handle):
    return [
        (m[1], int(m[2]), m[3].strip())
        for line in ui("tree", handle).splitlines()
        if (m := re.fullmatch(r"(\w+) (\d+) (.*)", line.strip()))
    ]


def save_job(job):
    if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", job["id"]) is None:
        raise ValueError("job id must be a safe lowercase directory slug")
    bank = Path(job["bank"])
    if bank.is_absolute() or ".." in bank.parts or bank.suffix.upper() != ".STY":
        raise ValueError("bank must be a relative .STY path beneath /assets")
    if type(job["slot"]) is not int or job["slot"] < 1:
        raise ValueError("bank slot must be a positive integer")
    dest = ROOT / "verified" / job["id"]
    dest.mkdir(parents=True, exist_ok=True)
    if (dest / "complete.json").exists():
        return
    click_toolbar(495)
    rows = dialog("Open Style Bank File")
    ui(
        "text",
        field(rows, "Edit", 1152)["handle"],
        "Z:\\assets\\" + job["bank"].replace("/", "\\"),
    )
    ui("click", field(rows, "Button", 1)["handle"])
    rows = windows()
    trees = [row["handle"] for row in rows if row["cls"] == "TTreeView"]
    right, left = trees
    entries = [item for item in tree(left) if item[1] == 1]
    selected = entries[job["slot"] - 1]
    if selected[2] != job["name"].strip():
        raise RuntimeError("source slot name mismatch " + str(selected))
    ui("select", left, selected[0], "enter")
    items = tree(right)
    if items[0][2] != job["name"].strip():
        raise RuntimeError("loaded style name mismatch")
    section = ""
    exports = []
    failures = []
    for handle, depth, label in items:
        if depth == 1:
            section = label
        if depth != 2:
            continue
        cv = int(label.rsplit(" ", 1)[1])
        kind, number = section.rsplit(" ", 1)
        prefix = {"Variation": "v", "Intro": "i", "Fill": "f", "Ending": "e"}[kind]
        expected = f"{prefix}{number}cv{cv}"
        path = dest / (expected + ".mid")
        if path.exists():
            exports.append(path.name)
            continue
        ui("select", right, handle)
        click_toolbar(620)
        rows = dialog("Save Standard Midi File")
        edit = field(rows, "Edit", 1152)
        if edit["text"].lower().removesuffix(".mid") != expected:
            raise RuntimeError(
                "unexpected filename " + edit["text"] + " expected " + expected
            )
        ui("text", edit["handle"], f"Z:\\work\\verified\\{job['id']}\\{expected}.mid")
        ui("click", field(rows, "Button", 1)["handle"])
        for _attempt in range(400):
            if path.exists() and path.stat().st_size > 14:
                break
            time.sleep(0.05)
        if not path.exists():
            raise RuntimeError("no output " + expected)
        if path.read_bytes()[:4] != b"MThd":
            failures.append(path.name)
        exports.append(path.name)
    (dest / "complete.json").write_text(
        json.dumps({"job": job, "files": exports, "invalid_smf": failures}, indent=2)
    )
    print(
        "COMPLETE",
        job["id"],
        job["name"],
        len(exports),
        "invalid",
        len(failures),
        flush=True,
    )


if __name__ == "__main__":
    jobs = json.loads((ROOT / "jobs.json").read_text())
    worker = int(os.environ.get("WORKER_ID", "0"))
    count = int(os.environ.get("WORKER_COUNT", "1"))
    for index, job in enumerate(jobs):
        if index % count != worker:
            continue
        try:
            save_job(job)
        except Exception as error:
            print("FAILED", job["id"], str(error), flush=True)
            run("import", "-window", "root", f"/work/worker-{worker}-failure.png")
            raise
