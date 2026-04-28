# Cancer Diagnostic Information Web App

This is a web application built with FastAPI that provides an interface for uploading Whole Slide Images (WSIs) and analyzing them using the TEPSEG (Tumor Epithelium Segmentation) GPU pipeline. It includes an interactive image viewer powered by OpenSeadragon to seamlessly explore the original slide alongside generated analytical maps and model inferences.

## Features

- **Slide Upload & Processing**: Upload large `.svs`, `.tif`, or `.tiff` slides directly via the web interface.
- **Background Pipeline Processing**: Automatically initiates the TEPSEG deep learning segmentation pipeline via background tasks.
- **Deep Zoom Viewer**: Efficiently renders massive Whole Slide Images using `openslide-python` and OpenSeadragon.
- **Multiple Result Views**: 
  - Raw Slide (Live Deep Zoom)
  - Clean Thumbnail
  - H&E Overlay
  - Raw Model Map
  - Refined Mask
  - Adaptive ROI
- **Annotation Overlay**: Toggle JSON-based annotation polygons overlaying the slide in the viewer.
- **Status Tracking**: Live polling of pipeline status during GPU processing.

## Prerequisites

- Python 3.8+
- [uv](https://github.com/astral-sh/uv) (for dependency management)
- OpenSlide binaries installed on your system
- CUDA-compatible GPU (for TEPSEG processing)

## Installation

1. Clone the repository (including the TEPSEG submodule):
   ```bash
   git clone --recurse-submodules https://github.com/Avaneesh122/cancer_diagnostic_information_web_app.git
   cd cancer_diagnostic_information_web_app
   ```

2. Sync dependencies using `uv` (as this project uses `pyproject.toml` and `uv.lock`):
   ```bash
   uv sync
   ```

3. **Model Checkpoints**: Ensure you have the necessary model checkpoints for TEPSEG. 
   Place the weights in the `TEPSEG/checkpoints_20x256univ2/` directory (e.g., `pytorch_model.bin`, `best_model.pth`). 
   *Note: Model binaries are excluded from Git due to size.*

## Running the App

Start the FastAPI application using Uvicorn:

```bash
uv run uvicorn main:app --reload
```

Then, open your browser and navigate to:
`http://127.0.0.1:8000`

## File Structure

- `main.py` - Core FastAPI backend, routing, and DeepZoom processing logic.
- `index.html` - The frontend OpenSeadragon viewer interface.
- `TEPSEG/` - The embedded deep learning segmentation pipeline repository.
- `uploads/` - Directory for incoming WSI uploads (git-ignored).
- `results/` - Directory where pipeline outputs (masks, overlays, maps) are saved (git-ignored).
- `model_loader.py` & `model_decipher.py` - Helper utilities for model inferences.
