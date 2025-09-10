#!/usr/bin/env python3
"""
Demo pipeline (Blender 3D):
1) Object stage:
   - Use VLM to list objects in a reference image
   - For each object: (a) VLM-bbox crop; (b) Meshy asset generation (text or crop-based)
   - Generator: prepares code to import assets into the Blender scene; Verifier: render and basic checks
2) Layout stage:
   - Generate a coarse Blender Python layout script via VLM (placements, transforms)
   - Execute in Blender, render the scene; compute similarity versus reference
   - One refine iteration: generator adjusts code; verifier re-renders and re-checks

Blender execution uses your pipeline script to run Blender in background with a template .blend.

Env:
- OPENAI_API_KEY (and optional OPENAI_BASE_URL)
- MESHY_API_KEY (for asset generation)
"""
import os
import sys
import json
import argparse
import base64
import subprocess
from pathlib import Path
from typing import List, Dict, Any
from PIL import Image

from openai import OpenAI

# 将运行时的父目录添加到sys.path
sys.path.append(os.getcwd())

# Local imports
from servers.generator.blender import ImageCropper, add_meshy_asset, add_meshy_asset_from_image


def get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    return OpenAI(api_key=api_key, base_url=base_url)


def vlm_list_objects(client: OpenAI, model: str, image_path: str) -> List[Dict[str, Any]]:
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    data_url = f"data:image/png;base64,{b64}"

    system_prompt = (
        "List distinct objects in the image with concise names and counts. "
        "Return ONLY JSON list of objects, where each item is {name: string}."
    )
    user_text = "Identify the main objects present. Respond strictly with a JSON array."

    resp = client.chat.completions.create(
        model=model,
        temperature=0.0,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
    )
    content = resp.choices[0].message.content if resp.choices else "[]"
    try:
        # Try parse or extract JSON
        return json.loads(content)
    except Exception:
        start = content.find("[")
        end = content.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(content[start:end+1])
            except Exception:
                return []
        return []


def run_blender_code(blender_cmd: str, blender_file: str, pipeline_script: str, code_str: str, render_dir: str) -> Dict[str, Any]:
    """
    Execute Blender python code using the provided pipeline script and render output to render_dir.
    The pipeline script should read the code file and execute it (see data/blendergym_hard/*/pipeline_render_script.py).
    """
    os.makedirs(render_dir, exist_ok=True)
    tmp_code = Path(render_dir) / "generated_code.py"
    tmp_code.write_text(code_str, encoding="utf-8")
    cmd = [
        blender_cmd,
        "--background", blender_file,
        "--python", pipeline_script,
        "--", str(tmp_code), str(render_dir)
    ]
    try:
        proc = subprocess.run(" ".join(cmd), shell=True, capture_output=True, text=True, timeout=1800)
        stdout = proc.stdout
        stderr = proc.stderr
        imgs = sorted([str(p) for p in Path(render_dir).glob("*.png")])
        return {
            "ok": proc.returncode == 0 and len(imgs) > 0,
            "stdout": stdout,
            "stderr": stderr,
            "renders": imgs,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "renders": []}
    except Exception as e:
        return {"ok": False, "error": str(e), "renders": []}


def generate_coarse_layout_code(client: OpenAI, model: str, image_path: str) -> str:
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    data_url = f"data:image/png;base64,{b64}"

    system_prompt = (
        "You are a Blender Python expert. Generate a minimal, runnable Blender Python script that constructs "
        "a coarse scene layout that visually approximates the screenshot: add basic primitives, set transforms, "
        "materials (simple colors), and camera/light. Keep it robust and idempotent (delete existing default objects). "
        "Return ONLY one Python code block."
    )
    user_text = "Generate a coarse Blender Python script for this screenshot."

    resp = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
    )
    content = resp.choices[0].message.content if resp.choices else ""
    # extract python code block
    fences = ["```python", "```Python", "```"]
    start = -1
    for f in fences:
        s = content.find(f)
        if s != -1:
            start = s + len(f)
            break
    if start == -1:
        return content.strip()
    end = content.find("```", start)
    if end == -1:
        return content[start:].strip()
    return content[start:end].strip()


def compute_clip(img1: Image.Image, img2: Image.Image) -> float:
    # Lazy import to avoid heavy deps if not used
    from evaluators.design2code.evaluate import clip_similarity
    return float(clip_similarity(img1, img2))


def demo_pipeline(
    input_image: str,
    output_dir: str,
    model: str = "gpt-4o",
    blender_cmd: str = "utils/blender/infinigen/blender/blender",
    blender_file: str = "data/blendergym_hard/level4/christmas1/blender_file.blend",
    pipeline_script: str = "data/blendergym_hard/level4/christmas1/pipeline_render_script.py",
) -> Dict[str, Any]:
    os.makedirs(output_dir, exist_ok=True)
    client = get_openai_client()

    results: Dict[str, Any] = {"stage1": {}, "stage2": {}}

    # Stage 1: objects -> crops + assets
    objects = vlm_list_objects(client, model, input_image)
    results["stage1"]["objects"] = objects

    cropper = ImageCropper()
    crops_dir = Path(output_dir) / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)

    crop_results = []
    text_assets = []
    image_assets = []

    # For each object name, attempt a crop and a text asset
    for idx, obj in enumerate(objects):
        name = (obj.get("name") or f"obj{idx}").strip().replace(" ", "_")
        crop_out = str(crops_dir / f"crop_{name}.jpg")
        crop_res = cropper.crop_image_by_text(input_image, name, crop_out)
        crop_results.append({"name": name, "result": crop_res})

        # Text-based asset (Meshy)
        try:
            text_asset = add_meshy_asset(
                description=name,
                blender_path="output/test/demo/old_blender_file.blend",
                location="0,0,0",
                scale=1.0,
                api_key=os.getenv("MESHY_API_KEY"),
                refine=False,
            )
        except Exception as e:
            text_asset = {"status": "error", "error": str(e)}
        text_assets.append({"name": name, "result": text_asset})

        # Image-based asset (if crop succeeded)
        if crop_res.get("status") == "success":
            try:
                image_asset = add_meshy_asset_from_image(
                    image_path=crop_out,
                    blender_path="output/test/demo/old_blender_file.blend",
                    location="0,0,0",
                    scale=1.0,
                    prompt=name,
                    api_key=os.getenv("MESHY_API_KEY"),
                    refine=False,
                )
            except Exception as e:
                image_asset = {"status": "error", "error": str(e)}
        else:
            image_asset = {"status": "skipped", "error": "crop_failed"}
        image_assets.append({"name": name, "result": image_asset})

    results["stage1"]["crops"] = crop_results
    results["stage1"]["text_assets"] = text_assets
    results["stage1"]["image_assets"] = image_assets

    # Simple verifier: count successes
    results["stage1"]["verification"] = {
        "num_objects": len(objects),
        "num_crops_success": sum(1 for r in crop_results if r["result"].get("status") == "success"),
        "num_text_assets_success": sum(1 for r in text_assets if r["result"].get("status") == "success"),
        "num_image_assets_success": sum(1 for r in image_assets if r["result"].get("status") == "success"),
    }

    # Stage 2: coarse Blender layout -> render -> refine
    coarse_code = generate_coarse_layout_code(client, model, input_image)
    coarse_render_dir = str(Path(output_dir) / "renders" / "coarse")
    coarse_exec = run_blender_code(blender_cmd, blender_file, pipeline_script, coarse_code, coarse_render_dir)
    coarse_clip = None
    if coarse_exec.get("ok") and coarse_exec.get("renders"):
        img1 = Image.open(coarse_exec["renders"][0])
        img2 = Image.open(input_image)
        coarse_clip = compute_clip(img1, img2)
    results["stage2"]["coarse"] = {
        "renders": coarse_exec.get("renders"),
        "clip": coarse_clip,
        "stdout": coarse_exec.get("stdout"),
        "stderr": coarse_exec.get("stderr"),
    }

    # One refine iteration: ask VLM to improve Blender Python code
    refine_prompt = (
        "Improve this Blender Python script to better match the screenshot. Use simple primitives, "
        "adjust transforms/materials, and keep the code idempotent. Return ONLY a Python code block."
    )
    resp = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": "You refine Blender Python scripts. Return ONLY a Python code block."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": refine_prompt},
                    {"type": "text", "text": coarse_code},
                ],
            },
        ],
    )
    content = resp.choices[0].message.content if resp.choices else ""
    fences = ["```python", "```Python", "```"]
    start = -1
    for fz in fences:
        s = content.find(fz)
        if s != -1:
            start = s + len(fz)
            break
    if start == -1:
        refined_code = content.strip()
    else:
        end = content.find("```", start)
        refined_code = content[start:end].strip() if end != -1 else content[start:].strip()

    refined_render_dir = str(Path(output_dir) / "renders" / "refined")
    refined_exec = run_blender_code(blender_cmd, blender_file, pipeline_script, refined_code, refined_render_dir)
    refined_clip = None
    if refined_exec.get("ok") and refined_exec.get("renders"):
        img1 = Image.open(refined_exec["renders"][0])
        img2 = Image.open(input_image)
        refined_clip = compute_clip(img1, img2)
    results["stage2"]["refine"] = {
        "renders": refined_exec.get("renders"),
        "clip": refined_clip,
        "stdout": refined_exec.get("stdout"),
        "stderr": refined_exec.get("stderr"),
    }

    # Save summary
    with open(Path(output_dir) / "demo_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    return results


def main():
    parser = argparse.ArgumentParser(description="Demo pipeline: objects->assets and coarse/refine layout")
    parser.add_argument("--image", default="data/blendergym_hard/level4/outdoor4/ref2.png", help="Input reference image path")
    parser.add_argument("--output-dir", default="output/test/demo", help="Output directory")
    parser.add_argument("--model", default="gpt-4o", help="VLM model")
    parser.add_argument("--blender-cmd", default="utils/blender/infinigen/blender/blender", help="Blender command path")
    parser.add_argument("--blender-file", default="data/blendergym_hard/level4/christmas1/blender_file.blend", help="Template .blend file")
    parser.add_argument("--pipeline-script", default="data/blendergym_hard/level4/christmas1/pipeline_render_script.py", help="Pipeline render script path")
    args = parser.parse_args()

    res = demo_pipeline(
        input_image=args.image,
        output_dir=args.output_dir,
        model=args.model,
        blender_cmd=args.blender_cmd,
        blender_file=args.blender_file,
        pipeline_script=args.pipeline_script,
    )
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

