# Demo Pipeline Modules

This directory contains three modular components for the demo pipeline, each handling a specific stage of the 3D scene generation process.

## Overview

The demo pipeline consists of three main stages:

1. **Asset Generation** (`asset.py`) - Generate 3D assets from objects detected in images
2. **Layout Generation** (`layout.py`) - Create coarse Blender scene layout using VLM
3. **Refinement** (`refine.py`) - Iteratively optimize layout using agentic verifier framework

## Modules

### 1. Asset Generation (`asset.py`)

Generates 3D assets from objects detected in reference images using Meshy API.

**Features:**
- Object detection using VLM
- Image cropping for object extraction
- Text-to-3D asset generation
- Image-to-3D asset generation
- Automatic asset import into Blender scene

**Usage:**
```bash
python runners/demo/asset.py \
    --image data/blendergym_hard/level4/outdoor4/ref2.png \
    --output-dir output/test/demo/assets \
    --blender-file output/test/demo/old_blender_file.blend \
    --model gpt-4o \
    --refine
```

**Required Environment Variables:**
- `OPENAI_API_KEY` - OpenAI API key for VLM
- `MESHY_API_KEY` - Meshy API key for 3D asset generation

### 2. Layout Generation (`layout.py`)

Uses VLM to generate coarse Blender scene layout from reference images.

**Features:**
- VLM-based scene analysis
- Blender Python code generation
- Automatic code execution in Blender
- CLIP similarity evaluation
- Render output generation

**Usage:**
```bash
python runners/demo/layout.py \
    --image data/blendergym_hard/level4/outdoor4/ref2.png \
    --output-dir output/test/demo/layout \
    --blender-cmd utils/blender/infinigen/blender/blender \
    --blender-file data/blendergym_hard/level4/christmas1/blender_file.blend \
    --pipeline-script data/blendergym_hard/level4/christmas1/pipeline_render_script.py \
    --model gpt-4o
```

**Required Environment Variables:**
- `OPENAI_API_KEY` - OpenAI API key for VLM

### 3. Refinement (`refine.py`)

Implements agentic verifier framework for iterative layout optimization.

**Features:**
- VLM-based scene analysis and comparison
- Iterative code refinement
- CLIP similarity tracking
- Convergence detection
- Multi-iteration optimization

**Usage:**
```bash
python runners/demo/refine.py \
    --code output/test/demo/layout/coarse_layout.py \
    --reference data/blendergym_hard/level4/outdoor4/ref2.png \
    --output-dir output/test/demo/refinement \
    --blender-cmd utils/blender/infinigen/blender/blender \
    --blender-file data/blendergym_hard/level4/christmas1/blender_file.blend \
    --pipeline-script data/blendergym_hard/level4/christmas1/pipeline_render_script.py \
    --model gpt-4o \
    --max-iterations 3 \
    --threshold 0.8
```

**Required Environment Variables:**
- `OPENAI_API_KEY` - OpenAI API key for VLM

## Complete Pipeline Workflow

### Step 1: Generate Assets
```bash
python runners/demo/asset.py \
    --image your_reference_image.png \
    --output-dir output/demo/assets
```

### Step 2: Generate Coarse Layout
```bash
python runners/demo/layout.py \
    --image your_reference_image.png \
    --output-dir output/demo/layout
```

### Step 3: Refine Layout
```bash
python runners/demo/refine.py \
    --code output/demo/layout/coarse_layout.py \
    --reference your_reference_image.png \
    --output-dir output/demo/refinement
```

## Output Structure

Each module generates structured output:

```
output/demo/
├── assets/
│   ├── crops/                    # Cropped object images
│   │   ├── crop_object1.jpg
│   │   └── crop_object2.jpg
│   └── asset_results.json       # Asset generation results
├── layout/
│   ├── renders/                 # Rendered images
│   │   └── render1.png
│   ├── coarse_layout.py         # Generated Blender code
│   └── layout_results.json      # Layout generation results
└── refinement/
    ├── iteration_1/             # Iteration 1 renders
    ├── iteration_2/             # Iteration 2 renders
    ├── iteration_3/             # Iteration 3 renders
    ├── final_refined_code.py    # Final optimized code
    └── refinement_results.json  # Refinement results
```

## Key Features

### Agentic Verifier Framework
The refinement module implements a sophisticated agentic verifier that:
- Analyzes rendered scenes using VLM
- Compares with reference images
- Identifies specific issues and improvements
- Generates refined Blender code
- Tracks similarity metrics across iterations
- Supports convergence detection

### Multi-Modal Analysis
- **Visual Analysis**: CLIP similarity for visual comparison
- **VLM Analysis**: Natural language feedback on scene composition
- **Code Generation**: Automated Blender Python script refinement

### Robust Error Handling
- Graceful fallbacks for missing dependencies
- Comprehensive error reporting
- Timeout protection for long-running operations
- Validation of input files and environment variables

## Dependencies

### Core Dependencies
- `openai` - OpenAI API client
- `PIL` - Image processing
- `pathlib` - File path handling
- `subprocess` - Blender execution

### Optional Dependencies
- `beautifulsoup4` - HTML parsing (for Design2Code metrics)
- `playwright` - Browser automation (for HTML rendering)
- `transformers` - CLIP model (for visual similarity)

## Configuration

### Environment Variables
```bash
export OPENAI_API_KEY="your-openai-api-key"
export MESHY_API_KEY="your-meshy-api-key"
export OPENAI_BASE_URL="https://api.openai.com/v1"  # Optional
```

### Blender Setup
Ensure Blender is properly configured:
- Blender executable path
- Template .blend files
- Pipeline render scripts
- Python environment with required packages

## Troubleshooting

### Common Issues

1. **Missing API Keys**
   - Ensure `OPENAI_API_KEY` and `MESHY_API_KEY` are set
   - Check API key validity and permissions

2. **Blender Execution Failures**
   - Verify Blender executable path
   - Check template .blend file exists
   - Ensure pipeline script is accessible

3. **VLM Analysis Failures**
   - Check OpenAI API quota and rate limits
   - Verify image file formats and sizes
   - Ensure stable internet connection

4. **Low Similarity Scores**
   - Increase max iterations in refinement
   - Adjust similarity threshold
   - Check reference image quality and complexity

### Performance Tips

- Use smaller images for faster VLM processing
- Limit max iterations for quick testing
- Cache generated assets for reuse
- Monitor API usage and costs

## Integration

These modules can be integrated into larger workflows:

- **Batch Processing**: Process multiple images in sequence
- **Pipeline Integration**: Combine with other AgenticVerifier components
- **Custom Workflows**: Extend with domain-specific logic
- **API Integration**: Wrap as web services for remote execution
