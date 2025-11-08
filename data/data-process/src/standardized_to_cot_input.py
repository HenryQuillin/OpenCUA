from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
from typing import Iterable, Optional

import orjson
import re

from src.schema.action import (
    ComputerAction,
    ComputerActionType,
    GUIActionType,
    PyAutoGUIAction,
)


def sanitize_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert standardized trajectories into CoT input JSONL and image frames.",
    )
    parser.add_argument(
        "--standardized-dir",
        type=Path,
        default=Path("datasets/standardized"),
        help="Directory containing standardized *.json trajectories.",
    )
    parser.add_argument(
        "--output-jsonl",
        type=Path,
        default=Path("datasets/cot_input.jsonl"),
        help="Path to write the CoT-ready JSONL file.",
    )
    parser.add_argument(
        "--images-dir",
        type=Path,
        default=Path("datasets/cot_images"),
        help="Directory where extracted PNG frames will be stored.",
    )
    parser.add_argument(
        "--max-recordings",
        type=int,
        default=-1,
        help="Optional limit on number of recordings to process.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing JSONL / frames if they already exist.",
    )
    return parser.parse_args()


def decode_base64_to_file(content: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if content.startswith("data:"):
        # Handle data URI such as "data:image/png;base64,..."
        try:
            content = content.split(",", 1)[1]
        except IndexError:
            raise ValueError("Unsupported data URI format") from None
    normalized = re.sub(r"[^A-Za-z0-9+/=]", "", content)
    core = normalized.rstrip("=")
    trailing_equals = len(normalized) - len(core)
    while core and (len(core) % 4 == 1):
        core = core[:-1]
    remainder = len(core) % 4
    if remainder:
        padding = 4 - remainder
    else:
        padding = 0
    total_equals = max(trailing_equals, padding)
    final_string = core + ("=" * total_equals)
    with path.open("wb") as fp:
        fp.write(base64.b64decode(final_string, validate=False))


def resolve_instruction(content: list[dict]) -> Optional[str]:
    for item in content:
        if (
            isinstance(item, dict)
            and item.get("class_") == "text_observation"
            and item.get("source") in {"user", "task"}
        ):
            return item.get("content")
    return None


def actions_to_code(actions: Iterable[dict]) -> str:
    commands: list[str] = []
    for action in actions:
        action_type = action.get("action_type")
        args = action.get("args") or {}

        if action_type in GUIActionType._value2member_map_:
            py_action = PyAutoGUIAction(action_type=GUIActionType(action_type), args=args)
            commands.append(py_action.to_command())
        elif action_type in ComputerActionType._value2member_map_:
            computer_action = ComputerAction(action_type=ComputerActionType(action_type), args=args)
            commands.append(computer_action.to_command())
        else:
            raise ValueError(f"Unsupported action type: {action_type}")

    return "\n".join(commands)


def process_file(
    file_path: Path,
    images_root: Path,
) -> Optional[dict]:
    data = orjson.loads(file_path.read_bytes())
    content: list[dict] = data.get("content", [])

    instruction = resolve_instruction(content)
    example_id = data.get("example_id") or file_path.stem
    task_id = data.get("task_id") or ""
    if not task_id or task_id.lower() == "agentnet":
        task_id = example_id
    image_folder = sanitize_name(example_id)

    image_counter = 0
    last_image_rel: Optional[str] = None
    trajectory: list[dict] = []

    for item in content:
        if not isinstance(item, dict):
            continue

        if item.get("class_") == "image_observation":
            image_name = f"{image_counter:04d}.png"
            rel_path = Path(image_folder) / image_name
            decode_base64_to_file(item["content"], images_root / rel_path)
            last_image_rel = rel_path.as_posix()
            image_counter += 1
        elif "guiactions" in item:
            if last_image_rel is None or not item["guiactions"]:
                continue
            code = actions_to_code(item["guiactions"])
            trajectory.append(
                {
                    "index": len(trajectory),
                    "image": last_image_rel,
                    "value": {"code": code},
                }
            )

    if not trajectory:
        return None

    return {
        "task_id": task_id,
        "instruction": instruction,
        "traj": trajectory,
        "source_recording_id": data.get("example_id"),
        "raw_type": data.get("type"),
        "image_folder": image_folder,
    }


def main() -> None:
    args = parse_args()

    if args.output_jsonl.exists() and not args.overwrite:
        raise SystemExit(f"{args.output_jsonl} exists. Use --overwrite to replace.")

    if args.overwrite:
        if args.output_jsonl.exists():
            args.output_jsonl.unlink()
        if args.images_dir.exists():
            for png in args.images_dir.rglob("*.png"):
                png.unlink()

    args.images_dir.mkdir(parents=True, exist_ok=True)

    standardized_files = sorted(args.standardized_dir.glob("*.json"))
    if args.max_recordings > -1:
        standardized_files = standardized_files[: args.max_recordings]

    records: list[dict] = []
    for file_path in standardized_files:
        record = process_file(file_path, args.images_dir)
        if record is None:
            continue
        records.append(record)

    with args.output_jsonl.open("w", encoding="utf-8") as jsonl_file:
        for record in records:
            jsonl_file.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()