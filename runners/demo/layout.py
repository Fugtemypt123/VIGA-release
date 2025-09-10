#!/usr/bin/env python3
"""
Layout generation module for demo pipeline.
Uses VLM to generate coarse Blender layout from reference image.
"""

import os
import sys
import json
import argparse
import base64
import subprocess
from pathlib import Path
from typing import Dict, Any
from PIL import Image

from openai import OpenAI

# 将运行时的父目录添加到sys.path
sys.path.append(os.getcwd())

# Local imports
from evaluators.design2code.evaluate import clip_similarity


def get_openai_client() -> OpenAI:
    """Get OpenAI client with API key from environment."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    return OpenAI(api_key=api_key, base_url=base_url)


def generate_coarse_layout_code(client: OpenAI, model: str, image_path: str) -> str:
    """Generate coarse Blender Python layout code from reference image."""
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    data_url = f"data:image/png;base64,{b64}"

    system_prompt = (
        "You are a Blender Python expert. Generate a minimal, runnable Blender Python script that constructs "
        "a coarse scene layout that visually approximates the screenshot: add basic primitives, set transforms, "
        "materials (simple colors), and camera/light. Keep it robust and idempotent (delete existing default objects). "
        "Focus on the overall composition, object placement, and basic lighting setup. "
        "Return ONLY one Python code block."
    )
    user_text = "Generate a coarse Blender Python script for this screenshot that creates a basic scene layout."

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
    
    # Extract python code block
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


def run_blender_code(
    blender_cmd: str, 
    blender_file: str, 
    pipeline_script: str, 
    code_str: str, 
    render_dir: str
) -> Dict[str, Any]:
    """
    Execute Blender python code using the provided pipeline script and render output to render_dir.
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


def compute_clip_similarity(img1: Image.Image, img2: Image.Image) -> float:
    """Compute CLIP similarity between two images."""
    try:
        return float(clip_similarity(img1, img2))
    except Exception as e:
        print(f"Error computing CLIP similarity: {e}")
        return 0.0


def generate_coarse_layout(
    input_image: str,
    output_dir: str,
    blender_cmd: str = "utils/blender/infinigen/blender/blender",
    blender_file: str = "data/blendergym_hard/level4/christmas1/blender_file.blend",
    pipeline_script: str = "data/blendergym_hard/level4/christmas1/pipeline_render_script.py",
    model: str = "gpt-4o"
) -> Dict[str, Any]:
    """
    Generate coarse Blender layout from reference image.
    
    Args:
        input_image: Path to input reference image
        output_dir: Output directory for results
        blender_cmd: Blender command path
        blender_file: Template .blend file
        pipeline_script: Pipeline render script path
        model: VLM model to use
        
    Returns:
        Dictionary with generation results
    """
    os.makedirs(output_dir, exist_ok=True)
    client = get_openai_client()

    results = {
        "coarse_code": "",
        "execution": {},
        "clip_similarity": None,
        "success": False
    }

    # Stage 1: Generate coarse layout code using VLM
    print("🎨 Generating coarse layout code...")
    try:
        coarse_code = generate_coarse_layout_code(client, model, input_image)
        results["coarse_code"] = coarse_code
        
        if not coarse_code.strip():
            print("❌ No code generated")
            return results
            
        print(f"✅ Generated {len(coarse_code)} characters of Blender code")
        
        # Save the generated code
        code_path = Path(output_dir) / "coarse_layout.py"
        code_path.write_text(coarse_code, encoding="utf-8")
        print(f"💾 Code saved to: {code_path}")
        
    except Exception as e:
        print(f"❌ Error generating layout code: {e}")
        results["error"] = str(e)
        return results

    # Stage 2: Execute the code in Blender
    print("🚀 Executing Blender code...")
    coarse_render_dir = str(Path(output_dir) / "renders")
    
    try:
        execution_result = run_blender_code(
            blender_cmd, blender_file, pipeline_script, coarse_code, coarse_render_dir
        )
        results["execution"] = execution_result
        
        if execution_result.get("ok"):
            print(f"✅ Blender execution successful")
            print(f"📸 Rendered {len(execution_result.get('renders', []))} images")
            for render in execution_result.get("renders", []):
                print(f"  - {render}")
        else:
            print(f"❌ Blender execution failed")
            if execution_result.get("error"):
                print(f"  Error: {execution_result['error']}")
            if execution_result.get("stderr"):
                print(f"  Stderr: {execution_result['stderr']}")
                
    except Exception as e:
        print(f"❌ Error executing Blender code: {e}")
        results["execution"] = {"ok": False, "error": str(e)}
        return results

    # Stage 3: Compute CLIP similarity
    if execution_result.get("ok") and execution_result.get("renders"):
        print("🔍 Computing visual similarity...")
        try:
            # Load the first rendered image
            rendered_img = Image.open(execution_result["renders"][0])
            # Load the reference image
            reference_img = Image.open(input_image)
            
            # Compute CLIP similarity
            clip_sim = compute_clip_similarity(rendered_img, reference_img)
            results["clip_similarity"] = clip_sim
            
            print(f"📊 CLIP similarity: {clip_sim:.4f}")
            
            if clip_sim > 0.7:
                print("🎉 High similarity achieved!")
            elif clip_sim > 0.5:
                print("👍 Moderate similarity achieved")
            else:
                print("⚠️ Low similarity - may need refinement")
                
        except Exception as e:
            print(f"❌ Error computing CLIP similarity: {e}")
            results["clip_error"] = str(e)
    else:
        print("⚠️ Cannot compute similarity - no rendered images")

    # Determine overall success
    results["success"] = (
        execution_result.get("ok", False) and 
        results["clip_similarity"] is not None and
        results["clip_similarity"] > 0.3  # Minimum threshold
    )

    # Save results
    with open(Path(output_dir) / "layout_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n📊 Layout Generation Summary:")
    print(f"  Code generation: {'✅' if results['coarse_code'] else '❌'}")
    print(f"  Blender execution: {'✅' if execution_result.get('ok') else '❌'}")
    print(f"  CLIP similarity: {results['clip_similarity']:.4f if results['clip_similarity'] else 'N/A'}")
    print(f"  Overall success: {'✅' if results['success'] else '❌'}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Generate coarse Blender layout from reference image")
    parser.add_argument("--image", required=True, help="Input reference image path")
    parser.add_argument("--output-dir", default="output/test/demo/layout", help="Output directory")
    parser.add_argument("--blender-cmd", default="utils/blender/infinigen/blender/blender", help="Blender command path")
    parser.add_argument("--blender-file", default="data/blendergym_hard/level4/christmas1/blender_file.blend", help="Template .blend file")
    parser.add_argument("--pipeline-script", default="data/blendergym_hard/level4/christmas1/pipeline_render_script.py", help="Pipeline render script path")
    parser.add_argument("--model", default="gpt-4o", help="VLM model")
    args = parser.parse_args()

    # Check required environment variables
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY environment variable is required")
        sys.exit(1)

    # Check if input image exists
    if not os.path.exists(args.image):
        print(f"❌ Error: Input image not found: {args.image}")
        sys.exit(1)

    # Check if Blender files exist
    if not os.path.exists(args.blender_file):
        print(f"❌ Error: Blender file not found: {args.blender_file}")
        sys.exit(1)
        
    if not os.path.exists(args.pipeline_script):
        print(f"❌ Error: Pipeline script not found: {args.pipeline_script}")
        sys.exit(1)

    print(f"🚀 Starting coarse layout generation...")
    print(f"  Input image: {args.image}")
    print(f"  Output directory: {args.output_dir}")
    print(f"  Blender command: {args.blender_cmd}")
    print(f"  Blender file: {args.blender_file}")
    print(f"  Pipeline script: {args.pipeline_script}")
    print(f"  Model: {args.model}")

    try:
        results = generate_coarse_layout(
            input_image=args.image,
            output_dir=args.output_dir,
            blender_cmd=args.blender_cmd,
            blender_file=args.blender_file,
            pipeline_script=args.pipeline_script,
            model=args.model
        )
        
        if results["success"]:
            print(f"\n✅ Coarse layout generation completed successfully!")
        else:
            print(f"\n⚠️ Coarse layout generation completed with issues")
            
        print(f"Results saved to: {Path(args.output_dir) / 'layout_results.json'}")
        
    except Exception as e:
        print(f"❌ Error during layout generation: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
