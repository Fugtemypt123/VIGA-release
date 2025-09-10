#!/usr/bin/env python3
"""
Asset generation module for demo pipeline.
Generates 3D assets from images and imports them into Blender scene.
"""

import os
import sys
import json
import argparse
import base64
from pathlib import Path
from typing import List, Dict, Any
from PIL import Image

from openai import OpenAI

# 将运行时的父目录添加到sys.path
sys.path.append(os.getcwd())

# Local imports
from servers.generator.blender import ImageCropper, add_meshy_asset, add_meshy_asset_from_image


def get_openai_client() -> OpenAI:
    """Get OpenAI client with API key from environment."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    return OpenAI(api_key=api_key, base_url=base_url)


def vlm_list_objects(client: OpenAI, model: str, image_path: str) -> List[Dict[str, Any]]:
    """Use VLM to list objects in the reference image."""
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


def generate_assets_from_image(
    input_image: str,
    output_dir: str,
    blender_file: str = None,
    model: str = "gpt-4o",
    refine: bool = False
) -> Dict[str, Any]:
    """
    Generate 3D assets from objects detected in the input image.
    
    Args:
        input_image: Path to input reference image
        output_dir: Output directory for crops and results
        blender_file: Blender file to import assets into
        model: VLM model to use
        refine: Whether to refine Meshy assets
        
    Returns:
        Dictionary with generation results
    """
    os.makedirs(output_dir, exist_ok=True)
    client = get_openai_client()

    results = {
        "objects": [],
        "crops": [],
        "text_assets": [],
        "image_assets": [],
        "verification": {}
    }

    # Stage 1: Detect objects using VLM
    print("🔍 Detecting objects in image...")
    objects = vlm_list_objects(client, model, input_image)
    results["objects"] = objects
    print(f"Found {len(objects)} objects: {[obj.get('name', 'unknown') for obj in objects]}")

    # Stage 2: Generate crops and assets
    cropper = ImageCropper()
    crops_dir = Path(output_dir) / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)

    crop_results = []
    text_assets = []
    image_assets = []

    # For each object name, attempt a crop and generate assets
    for idx, obj in enumerate(objects):
        name = (obj.get("name") or f"obj{idx}").strip().replace(" ", "_")
        print(f"🎯 Processing object: {name}")
        
        # Generate crop
        crop_out = str(crops_dir / f"crop_{name}.jpg")
        crop_res = cropper.crop_image_by_text(input_image, name, crop_out)
        crop_results.append({"name": name, "result": crop_res})
        
        if crop_res.get("status") == "success":
            print(f"  ✅ Crop successful: {crop_out}")
        else:
            print(f"  ❌ Crop failed: {crop_res.get('error', 'Unknown error')}")

        # Text-based asset (Meshy)
        print(f"  🎨 Generating text-based asset for: {name}")
        try:
            text_asset = add_meshy_asset(
                description=name,
                location=f"{idx * 2},0,0",  # Spread objects along X axis
                scale=1.0,
                api_key=os.getenv("MESHY_API_KEY"),
                refine=refine,
                save_dir=output_dir,
                blender_path=blender_file,
            )
            if text_asset.get("status") == "success":
                print(f"  ✅ Text asset generated successfully")
            else:
                print(f"  ❌ Text asset failed: {text_asset.get('error', 'Unknown error')}")
        except Exception as e:
            text_asset = {"status": "error", "error": str(e)}
            print(f"  ❌ Text asset exception: {e}")
        text_assets.append({"name": name, "result": text_asset})

        # Image-based asset (if crop succeeded)
        if crop_res.get("status") == "success":
            print(f"  🖼️ Generating image-based asset from crop...")
            try:
                image_asset = add_meshy_asset_from_image(
                    image_path=crop_out,
                    location=f"{idx * 2},2,0",  # Offset Y position for image assets
                    scale=1.0,
                    prompt=name,
                    api_key=os.getenv("MESHY_API_KEY"),
                    refine=refine,
                    save_dir=output_dir,
                    blender_path=blender_file,
                )
                if image_asset.get("status") == "success":
                    print(f"  ✅ Image asset generated successfully")
                else:
                    print(f"  ❌ Image asset failed: {image_asset.get('error', 'Unknown error')}")
            except Exception as e:
                image_asset = {"status": "error", "error": str(e)}
                print(f"  ❌ Image asset exception: {e}")
        else:
            image_asset = {"status": "skipped", "error": "crop_failed"}
            print(f"  ⏭️ Skipping image asset (crop failed)")
        image_assets.append({"name": name, "result": image_asset})

    results["crops"] = crop_results
    results["text_assets"] = text_assets
    results["image_assets"] = image_assets

    # Verification summary
    results["verification"] = {
        "num_objects": len(objects),
        "num_crops_success": sum(1 for r in crop_results if r["result"].get("status") == "success"),
        "num_text_assets_success": sum(1 for r in text_assets if r["result"].get("status") == "success"),
        "num_image_assets_success": sum(1 for r in image_assets if r["result"].get("status") == "success"),
    }

    # Save results
    with open(Path(output_dir) / "asset_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n📊 Asset Generation Summary:")
    print(f"  Objects detected: {results['verification']['num_objects']}")
    print(f"  Successful crops: {results['verification']['num_crops_success']}")
    print(f"  Successful text assets: {results['verification']['num_text_assets_success']}")
    print(f"  Successful image assets: {results['verification']['num_image_assets_success']}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Generate 3D assets from image objects")
    parser.add_argument("--image", required=True, help="Input reference image path")
    parser.add_argument("--output-dir", default="data/blendergym_hard/level4/outdoor4/assets", help="Output directory")
    parser.add_argument("--blender-file", default="output/test/demo/old_blender_file.blend", help="Blender file to import assets into")
    parser.add_argument("--model", default="gpt-4o", help="VLM model")
    parser.add_argument("--refine", action="store_true", help="Refine Meshy assets")
    args = parser.parse_args()

    # Check required environment variables
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY environment variable is required")
        sys.exit(1)
    
    if not os.getenv("MESHY_API_KEY"):
        print("❌ Error: MESHY_API_KEY environment variable is required")
        sys.exit(1)

    # Check if input image exists
    if not os.path.exists(args.image):
        print(f"❌ Error: Input image not found: {args.image}")
        sys.exit(1)

    print(f"🚀 Starting asset generation...")
    print(f"  Input image: {args.image}")
    print(f"  Output directory: {args.output_dir}")
    print(f"  Blender file: {args.blender_file}")
    print(f"  Model: {args.model}")
    print(f"  Refine: {args.refine}")

    try:
        results = generate_assets_from_image(
            input_image=args.image,
            output_dir=args.output_dir,
            blender_file=args.blender_file,
            model=args.model,
            refine=args.refine
        )
        
        print(f"\n✅ Asset generation completed successfully!")
        print(f"Results saved to: {Path(args.output_dir) / 'asset_results.json'}")
        
    except Exception as e:
        print(f"❌ Error during asset generation: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
