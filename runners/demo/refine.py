#!/usr/bin/env python3
"""
Refinement module for demo pipeline.
Uses the agentic verifier framework to iteratively optimize Blender layout.
"""

import os
import sys
import json
import argparse
import base64
import subprocess
from pathlib import Path
from typing import Dict, Any, List
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


def run_blender_code(
    blender_cmd: str, 
    blender_file: str, 
    pipeline_script: str, 
    code_str: str, 
    render_dir: str
) -> Dict[str, Any]:
    """Execute Blender python code and render output."""
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


def analyze_scene_with_vlm(
    client: OpenAI, 
    model: str, 
    reference_image: str, 
    current_render: str
) -> Dict[str, Any]:
    """Use VLM to analyze the current scene and compare with reference."""
    # Load both images
    with open(reference_image, "rb") as f:
        ref_b64 = base64.b64encode(f.read()).decode("utf-8")
    ref_data_url = f"data:image/png;base64,{ref_b64}"
    
    with open(current_render, "rb") as f:
        curr_b64 = base64.b64encode(f.read()).decode("utf-8")
    curr_data_url = f"data:image/png;base64,{curr_b64}"

    system_prompt = (
        "You are a 3D scene analysis expert. Compare the current rendered scene with the reference image. "
        "Identify specific issues and provide actionable feedback for improvement. "
        "Focus on: object placement, lighting, materials, camera angle, composition, and overall visual similarity. "
        "Return a JSON object with: issues (list of specific problems), improvements (list of suggested fixes), "
        "and priority (high/medium/low)."
    )
    
    user_text = (
        "Analyze the current 3D scene render compared to the reference image. "
        "Identify what needs to be improved and provide specific, actionable feedback."
    )

    resp = client.chat.completions.create(
        model=model,
        temperature=0.1,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "text", "text": "Reference image:"},
                    {"type": "image_url", "image_url": {"url": ref_data_url}},
                    {"type": "text", "text": "Current render:"},
                    {"type": "image_url", "image_url": {"url": curr_data_url}},
                ],
            },
        ],
    )
    
    content = resp.choices[0].message.content if resp.choices else "{}"
    try:
        return json.loads(content)
    except Exception:
        # Fallback parsing
        return {
            "issues": ["Failed to parse VLM analysis"],
            "improvements": ["Manual review needed"],
            "priority": "medium"
        }


def generate_refined_code(
    client: OpenAI,
    model: str,
    current_code: str,
    analysis: Dict[str, Any],
    reference_image: str
) -> str:
    """Generate refined Blender code based on VLM analysis."""
    
    with open(reference_image, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    data_url = f"data:image/png;base64,{b64}"

    issues_text = "\n".join([f"- {issue}" for issue in analysis.get("issues", [])])
    improvements_text = "\n".join([f"- {improvement}" for improvement in analysis.get("improvements", [])])
    
    system_prompt = (
        "You are a Blender Python expert. Refine the given Blender script based on the analysis feedback. "
        "Make specific improvements to address the identified issues. Keep the code robust and idempotent. "
        "Return ONLY the improved Python code block."
    )
    
    user_text = f"""
Current Blender script:
```python
{current_code}
```

Issues identified:
{issues_text}

Suggested improvements:
{improvements_text}

Please refine the script to address these issues and better match the reference image.
"""

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


def run_agentic_verifier_iteration(
    current_code: str,
    reference_image: str,
    blender_cmd: str,
    blender_file: str,
    pipeline_script: str,
    render_dir: str,
    client: OpenAI,
    model: str,
    iteration: int
) -> Dict[str, Any]:
    """Run one iteration of the agentic verifier refinement process."""
    
    print(f"🔄 Running refinement iteration {iteration}...")
    
    # Step 1: Execute current code
    print(f"  🚀 Executing current code...")
    execution_result = run_blender_code(
        blender_cmd, blender_file, pipeline_script, current_code, render_dir
    )
    
    if not execution_result.get("ok") or not execution_result.get("renders"):
        return {
            "success": False,
            "error": "Execution failed",
            "execution": execution_result
        }
    
    # Step 2: Compute CLIP similarity
    print(f"  🔍 Computing visual similarity...")
    try:
        rendered_img = Image.open(execution_result["renders"][0])
        reference_img = Image.open(reference_image)
        clip_sim = compute_clip_similarity(rendered_img, reference_img)
        print(f"  📊 CLIP similarity: {clip_sim:.4f}")
    except Exception as e:
        print(f"  ❌ Error computing similarity: {e}")
        clip_sim = 0.0
    
    # Step 3: Analyze with VLM
    print(f"  🤖 Analyzing scene with VLM...")
    analysis = analyze_scene_with_vlm(
        client, model, reference_image, execution_result["renders"][0]
    )
    print(f"  📋 Issues found: {len(analysis.get('issues', []))}")
    print(f"  💡 Improvements suggested: {len(analysis.get('improvements', []))}")
    
    # Step 4: Generate refined code
    print(f"  🎨 Generating refined code...")
    refined_code = generate_refined_code(
        client, model, current_code, analysis, reference_image
    )
    
    if not refined_code.strip():
        return {
            "success": False,
            "error": "No refined code generated",
            "execution": execution_result,
            "clip_similarity": clip_sim,
            "analysis": analysis
        }
    
    return {
        "success": True,
        "execution": execution_result,
        "clip_similarity": clip_sim,
        "analysis": analysis,
        "refined_code": refined_code
    }


def refine_layout_with_agentic_verifier(
    initial_code: str,
    reference_image: str,
    output_dir: str,
    blender_cmd: str = "utils/blender/infinigen/blender/blender",
    blender_file: str = "data/blendergym_hard/level4/christmas1/blender_file.blend",
    pipeline_script: str = "data/blendergym_hard/level4/christmas1/pipeline_render_script.py",
    model: str = "gpt-4o",
    max_iterations: int = 3,
    similarity_threshold: float = 0.8
) -> Dict[str, Any]:
    """
    Refine Blender layout using agentic verifier framework.
    
    Args:
        initial_code: Initial Blender Python code
        reference_image: Path to reference image
        output_dir: Output directory for results
        blender_cmd: Blender command path
        blender_file: Template .blend file
        pipeline_script: Pipeline render script path
        model: VLM model to use
        max_iterations: Maximum number of refinement iterations
        similarity_threshold: Target CLIP similarity threshold
        
    Returns:
        Dictionary with refinement results
    """
    os.makedirs(output_dir, exist_ok=True)
    client = get_openai_client()

    results = {
        "iterations": [],
        "final_code": "",
        "best_similarity": 0.0,
        "converged": False,
        "total_iterations": 0
    }

    current_code = initial_code
    best_similarity = 0.0
    best_code = initial_code

    print(f"🚀 Starting agentic verifier refinement...")
    print(f"  Max iterations: {max_iterations}")
    print(f"  Target similarity: {similarity_threshold}")
    print(f"  Reference image: {reference_image}")

    for iteration in range(1, max_iterations + 1):
        print(f"\n--- Iteration {iteration}/{max_iterations} ---")
        
        # Create iteration-specific render directory
        iter_render_dir = str(Path(output_dir) / f"iteration_{iteration}")
        
        # Run one iteration
        iter_result = run_agentic_verifier_iteration(
            current_code=current_code,
            reference_image=reference_image,
            blender_cmd=blender_cmd,
            blender_file=blender_file,
            pipeline_script=pipeline_script,
            render_dir=iter_render_dir,
            client=client,
            model=model,
            iteration=iteration
        )
        
        # Store iteration results
        results["iterations"].append(iter_result)
        results["total_iterations"] = iteration
        
        if not iter_result["success"]:
            print(f"❌ Iteration {iteration} failed: {iter_result.get('error', 'Unknown error')}")
            break
        
        current_similarity = iter_result["clip_similarity"]
        print(f"📊 Iteration {iteration} similarity: {current_similarity:.4f}")
        
        # Update best results
        if current_similarity > best_similarity:
            best_similarity = current_similarity
            best_code = iter_result["refined_code"]
            print(f"🎉 New best similarity achieved!")
        
        # Check convergence
        if current_similarity >= similarity_threshold:
            print(f"🎯 Target similarity achieved! Stopping refinement.")
            results["converged"] = True
            break
        
        # Prepare for next iteration
        if "refined_code" in iter_result:
            current_code = iter_result["refined_code"]
            print(f"✅ Code refined for next iteration")
        else:
            print(f"⚠️ No refined code available, stopping")
            break

    # Final results
    results["final_code"] = best_code
    results["best_similarity"] = best_similarity
    
    # Save final code
    final_code_path = Path(output_dir) / "final_refined_code.py"
    final_code_path.write_text(best_code, encoding="utf-8")
    
    # Save results
    with open(Path(output_dir) / "refinement_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n📊 Refinement Summary:")
    print(f"  Total iterations: {results['total_iterations']}")
    print(f"  Best similarity: {results['best_similarity']:.4f}")
    print(f"  Target achieved: {'✅' if results['converged'] else '❌'}")
    print(f"  Final code saved to: {final_code_path}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Refine Blender layout using agentic verifier")
    parser.add_argument("--code", required=True, help="Initial Blender Python code file")
    parser.add_argument("--reference", required=True, help="Reference image path")
    parser.add_argument("--output-dir", default="output/test/demo/refinement", help="Output directory")
    parser.add_argument("--blender-cmd", default="utils/blender/infinigen/blender/blender", help="Blender command path")
    parser.add_argument("--blender-file", default="data/blendergym_hard/level4/christmas1/blender_file.blend", help="Template .blend file")
    parser.add_argument("--pipeline-script", default="data/blendergym_hard/level4/christmas1/pipeline_render_script.py", help="Pipeline render script path")
    parser.add_argument("--model", default="gpt-4o", help="VLM model")
    parser.add_argument("--max-iterations", type=int, default=3, help="Maximum refinement iterations")
    parser.add_argument("--threshold", type=float, default=0.8, help="Target similarity threshold")
    args = parser.parse_args()

    # Check required environment variables
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY environment variable is required")
        sys.exit(1)

    # Check if input files exist
    if not os.path.exists(args.code):
        print(f"❌ Error: Code file not found: {args.code}")
        sys.exit(1)
        
    if not os.path.exists(args.reference):
        print(f"❌ Error: Reference image not found: {args.reference}")
        sys.exit(1)

    # Load initial code
    try:
        with open(args.code, 'r', encoding='utf-8') as f:
            initial_code = f.read()
    except Exception as e:
        print(f"❌ Error reading code file: {e}")
        sys.exit(1)

    print(f"🚀 Starting agentic verifier refinement...")
    print(f"  Initial code: {args.code}")
    print(f"  Reference image: {args.reference}")
    print(f"  Output directory: {args.output_dir}")
    print(f"  Max iterations: {args.max_iterations}")
    print(f"  Target threshold: {args.threshold}")

    try:
        results = refine_layout_with_agentic_verifier(
            initial_code=initial_code,
            reference_image=args.reference,
            output_dir=args.output_dir,
            blender_cmd=args.blender_cmd,
            blender_file=args.blender_file,
            pipeline_script=args.pipeline_script,
            model=args.model,
            max_iterations=args.max_iterations,
            similarity_threshold=args.threshold
        )
        
        if results["converged"]:
            print(f"\n✅ Refinement completed successfully!")
        else:
            print(f"\n⚠️ Refinement completed but target not reached")
            
        print(f"Results saved to: {Path(args.output_dir) / 'refinement_results.json'}")
        
    except Exception as e:
        print(f"❌ Error during refinement: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
