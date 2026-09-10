# Cancer Diagnostic Information Web App

A full-stack diagnostic interface for analyzing Whole Slide Images (WSIs) using deep learning, the TEPSEG pipeline, and HistoPLUS cell segmentation. 

## Problem Statement
Pathologists face an immense data challenge when diagnosing tissue anomalies, such as oral cavity cancer. A single Whole Slide Image (WSI) contains billions of pixels, making the manual analysis of tumor boundaries, peri-tumoral regions, and individual cell populations incredibly time-consuming and prone to subjective variance. There is a critical need for an automated, accessible application that bridges the gap between complex GPU-accelerated AI models and a user-friendly visual interface, allowing medical professionals to interact with gigapixel images and AI inferences seamlessly in a standard web browser.

## Methodology
The application transforms heavy computational processes into a smooth, interactive web experience through a distinct four-step architecture:

1. **Ingestion & Deep Zoom Server:** Massive `.svs`, `.tif`, or `.tiff` files are uploaded via the interface. Instead of loading the entire image into memory, the FastAPI backend uses OpenSlide to dynamically slice the image into 256x256 pixel tiles, serving them on-demand as the user pans and zooms.
2. **Macroscopic Tumor Segmentation (TEPSEG):** A background GPU task initiates the TEPSEG pipeline. This leverages the UNI foundation model for advanced feature extraction, feeding into a custom PyTorch classifier that identifies macroscopic tissue regions and draws precise annotation polygons around primary tumor zones.
3. **Microscopic Cell Analysis (HistoPLUS):** Using spatial geometry, the backend isolates the exact coordinates of the identified tumor. The HistoPLUS framework, powered by a CellViT segmentor, then executes high-throughput cell classification exclusively within this region, identifying distinct cell types like lymphocytes, fibroblasts, and cancer cells.
4. **Interactive Visualization:** The OpenSeadragon frontend receives these inferences and layers them over the slide. Users can dynamically overlay physical micrometer grids, toggle adjustable peri-tumoral buffers, and view color-coded cell centroids mapped directly onto the tissue.

## Results & Features

| Feature | Description |
| :--- | :--- |
| **Live Deep Zoom** | Google Maps-style panning and zooming for viewing massive histological slides with zero latency. |
| **Diagnostic Overlays** | Instantly switch between Raw Slide, H&E Overlay, Raw Model Map, Refined Mask, and Adaptive ROI views. |
| **Spatial Annotations** | Toggleable SVG polygons highlighting primary tumor bounds with an adjustable peri-tumoral margin slider (50µm–200µm). |
| **Cellular Analytics** | HistoPLUS results panel detailing the AI model utilized, inference MPP, total cell count, and granular percentages for 14 distinct cell types. |
| **Physical Scale Tracking** | Dynamic micrometer scalebars and toggleable 50µm/100µm physical grids that automatically scale with viewport magnification. |

## Technology Stack

**Backend & API**
* Python 3.10+
* FastAPI & Uvicorn (Asynchronous web serving & background tasks)
* `uv` (High-performance dependency management)

**Machine Learning & Computer Vision**
* PyTorch (Model execution)
* TEPSEG Pipeline & UNI Foundation Model (Tissue segmentation)
* HistoPLUS & CellViT (Cellular segmentation and classification)

**Geospatial & Image Processing**
* OpenSlide & `openslide-python` (WSI ingestion and DeepZoom tile generation)
* Shapely (Spatial geometry and polygon filtering)

**Frontend**
* HTML5, CSS3, Vanilla JavaScript
* OpenSeadragon (High-resolution image viewer)
* OpenSeadragonScalebar (Physical measurement rendering)

## Prerequisites

* Python 3.8+
* `uv` package manager installed (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
* OpenSlide binaries installed and added to your system path.
* CUDA-compatible GPU (Required for TEPSEG and HistoPLUS execution).

## Installation

1. **Clone the repository and submodules:**
```bash
git clone --recurse-submodules [https://github.com/Avaneesh122/cancer_diagnostic_information_web_app.git](https://github.com/Avaneesh122/cancer_diagnostic_information_web_app.git)
cd cancer_diagnostic_information_web_app
