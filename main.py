import os
import subprocess
import sys
import shutil
import io
import openslide_bin
import openslide
from openslide.deepzoom import DeepZoomGenerator
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# result folder path
results_path = r"C:\Users\asbhoit\Documents\cancer_app\results"
app.mount("/results", StaticFiles(directory=results_path), name="results")

task_status = {}

UPLOAD_DIR = "uploads"
RESULT_DIR = "results"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)

# Cache to hold open DeepZoom generators
slide_cache = {}

def get_dz(filename):
    """Helper function to load and cache the DeepZoom generator."""
    if filename not in slide_cache:
        file_path = os.path.join(UPLOAD_DIR, filename)
        slide = openslide.OpenSlide(file_path)
        slide_cache[filename] = DeepZoomGenerator(slide, tile_size=254, overlap=1, limit_bounds=False)
    return slide_cache[filename]

# --- DEEP ZOOM TILE SERVER ENDPOINTS ---

@app.get("/slide/{slide_name}.dzi")
def get_dzi(slide_name: str):
    """Returns the XML metadata telling OpenSeadragon how big the full slide is."""
    try:
        dz = get_dz(slide_name)
        dzi_xml = dz.get_dzi('jpeg')
        return Response(content=dzi_xml, media_type="application/xml")
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"DZI generation failed: {e}")

@app.get("/slide/{slide_name}_files/{level}/{col}_{row}.{format}")
def get_tile(slide_name: str, level: int, col: int, row: int, format: str):
    """Extracts and returns the exact 256x256 pixel tile for the requested zoom level."""
    try:
        dz = get_dz(slide_name)
        tile = dz.get_tile(level, (col, row))
        
        buf = io.BytesIO()
        tile.save(buf, format, quality=90)
        return Response(content=buf.getvalue(), media_type=f"image/{format}")
    except Exception as e:
        raise HTTPException(status_code=404, detail="Tile not found")

@app.get("/slide/{slide_name}/metadata")
def get_metadata(slide_name: str):
    """Returns slide metadata like Microns Per Pixel (MPP) and dimensions for the scalebar and grid."""
    try:
        file_path = os.path.join(UPLOAD_DIR, slide_name)
        slide = openslide.OpenSlide(file_path)
        mpp_x = slide.properties.get(openslide.PROPERTY_NAME_MPP_X)
        width, height = slide.dimensions
        return {
            "mpp": float(mpp_x) if mpp_x else None,
            "width": width,
            "height": height
        }
    except Exception as e:
        return {"mpp": None, "width": 0, "height": 0}

# --- FRONTEND AND PIPELINE ---

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    html_content = """
    <!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Oral Cancer Pathology Viewer</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/openseadragon/4.1.0/openseadragon.min.js"></script>
    <script src="https://cdn.jsdelivr.net/gh/usnistgov/OpenSeadragonScalebar@master/openseadragon-scalebar.js"></script>
    <style>
        body { font-family: Arial, sans-serif; background-color: #121212; color: #ffffff; margin: 0; padding: 0; display: flex; flex-direction: column; height: 100vh; }
        #header { padding: 15px; background-color: #1e1e1e; text-align: center; border-bottom: 1px solid #333; }
        #controls { padding: 10px; text-align: center; background-color: #252526; display: flex; justify-content: center; align-items: center; gap: 15px; flex-wrap: wrap; }
        
        button, select { background-color: #0e639c; color: white; border: none; padding: 10px 15px; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 14px; }
        button:hover, select:hover { background-color: #1177bb; }
        button:disabled, select:disabled { background-color: #555; cursor: not-allowed; }
        
        .checkbox-container { display: flex; align-items: center; gap: 5px; cursor: pointer; font-weight: bold; }
        #status-container { display: flex; flex-direction: column; align-items: flex-start; margin-left: 15px; min-width: 250px; }
        #status { color: #f39c12; font-weight: bold; text-align: left; margin-bottom: 5px; }
        #progress-container { display: none; width: 100%; height: 8px; background-color: #333; border-radius: 4px; overflow: hidden; }
        #progress-bar { width: 0%; height: 100%; background-color: #3498db; transition: width 0.3s ease; }
        
        #viewer-container { position: relative; width: 100%; flex-grow: 1; }
        #openseadragon-viewer { width: 100%; height: 100%; background-color: #000000; }
        #annotation-overlay { position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 10; }
    </style>
</head>
<body>
    <div id="header">
        <h2>TEPSEG Results Viewer</h2>
    </div>
    
    <div id="controls">
        <input type="file" id="slideUpload" accept=".svs,.tif,.tiff">
        <button id="uploadBtn" onclick="uploadAndProcess()">Upload & Process</button>
        
        <span style="color: #666;">|</span>
        
       <select id="viewSelector" onchange="changeView()" disabled>
            <option value="deepzoom">Raw Slide (Live Deep Zoom)</option>
            <option value="thumbnail">Clean Thumbnail</option>
            <option value="overlay_he">H&E Overlay</option>
            <option value="raw_map">Raw Model Map</option>
            <option value="refined_mask">Refined Mask</option>
            <option value="adaptive_roi">Adaptive ROI</option>
        </select>

        <span style="color: #666;">|</span>

        <label class="checkbox-container">
            <input type="checkbox" id="annotationToggle" onchange="toggleAnnotations()" disabled>
            Show Annotations (JSON)
        </label>

        <span style="color: #666;">|</span>

        <select id="gridSelector" onchange="toggleGrid()" disabled>
            <option value="none">No Grid</option>
            <option value="50">50µm Grid</option>
            <option value="100">100µm Grid</option>
        </select>
        
        <div id="status-container">
            <div id="status">Ready for upload.</div>
            <div id="progress-container">
                <div id="progress-bar"></div>
            </div>
        </div>
    </div>

    <div id="viewer-container">
        <div id="openseadragon-viewer"></div>
        <svg id="annotation-overlay"></svg>
    </div>

    <script>
        var viewer = OpenSeadragon({
            id: "openseadragon-viewer",
            prefixUrl: "https://cdnjs.cloudflare.com/ajax/libs/openseadragon/4.1.0/images/",
            showNavigationControl: true,
            showNavigator: true,
            navigatorPosition: "TOP_RIGHT",
            zoomPerClick: 2.0
        });

        let currentFilePaths = {};
        let annotationsData = [];
        let currentBaseName = "";
        let originalFileName = "";
        let pollingInterval;
        let slideMPP = null;
        let slideWidth = null;
        let slideHeight = null;
        const gridOverlayId = "micrometer-grid-overlay";

        function changeView() {
            const selectedKey = document.getElementById("viewSelector").value;
            const isDeepZoom = selectedKey === "deepzoom";
            
            if (isDeepZoom) {
                viewer.open(`/slide/${originalFileName}.dzi`);
            } else if (currentFilePaths[selectedKey]) {
                viewer.open({ type: 'image', url: currentFilePaths[selectedKey] });
            }

            // Hide/Show scalebar based on the view
            if (viewer.scalebarInstance) {
                const displayStyle = isDeepZoom ? "" : "none";
                viewer.scalebarInstance.divElt.style.display = displayStyle;
            } else if (isDeepZoom && originalFileName) {
                loadScalebar();
            }

            // Redraw polygons if toggle is checked after changing views
            setTimeout(() => {
                if (document.getElementById("annotationToggle").checked) drawPolygons();
            }, 500); 
        }

        async function uploadAndProcess() {
            const fileInput = document.getElementById('slideUpload');
            const statusText = document.getElementById('status');
            const uploadBtn = document.getElementById('uploadBtn');
            const viewSelector = document.getElementById('viewSelector');
            const annotationToggle = document.getElementById('annotationToggle');
            const gridSelector = document.getElementById('gridSelector');

            if (fileInput.files.length === 0) {
                alert("Please select an .svs slide to upload.");
                return;
            }

            const file = fileInput.files[0];
            const taskId = file.name; 
            originalFileName = file.name;
            currentBaseName = file.name.substring(0, file.name.lastIndexOf('.')) || file.name;

            const formData = new FormData();
            formData.append("file", file); 

            statusText.innerText = "Uploading to server...";
            statusText.style.color = "#3498db";
            
            const progressContainer = document.getElementById('progress-container');
            const progressBar = document.getElementById('progress-bar');
            progressContainer.style.display = 'block';
            progressBar.style.width = '0%';
            
            uploadBtn.disabled = true;
            viewSelector.disabled = true;
            annotationToggle.disabled = true;
            gridSelector.disabled = true;
            document.getElementById("annotation-overlay").innerHTML = "";

            try {
                const response = await fetch('/upload', { method: 'POST', body: formData });
                
                if (response.ok) {
                    statusText.innerText = "Processing GPU Pipeline...";
                    statusText.style.color = "#f39c12";
                    pollProcessingStatus(taskId);
                } else {
                    statusText.innerText = "Error: Upload failed.";
                    statusText.style.color = "#e74c3c";
                    uploadBtn.disabled = false;
                }
            } catch (error) {
                statusText.innerText = "Error: Server connection lost.";
                statusText.style.color = "#e74c3c";
                uploadBtn.disabled = false;
            }
        }

        function pollProcessingStatus(taskId) {
            const statusText = document.getElementById('status');
            
            pollingInterval = setInterval(async () => {
                try {
                    const res = await fetch(`/status/${taskId}`);
                    const data = await res.json();
                    
                    statusText.innerText = data.status;
                    if (data.progress > 0) {
                        document.getElementById('progress-bar').style.width = data.progress + '%';
                    }

                    if (data.status.includes("Completed")) {
                        clearInterval(pollingInterval);
                        statusText.style.color = "#4CAF50";
                        unlockUIAndLoadImages();
                    } else if (data.status.includes("Error") || data.status.includes("failed")) {
                        clearInterval(pollingInterval);
                        statusText.style.color = "#e74c3c";
                        document.getElementById('uploadBtn').disabled = false;
                    }
                } catch (error) {
                    console.error("Polling error:", error);
                }
            }, 3000); 
        }

        function unlockUIAndLoadImages() {
            const viewSelector = document.getElementById('viewSelector');
            const annotationToggle = document.getElementById('annotationToggle');

            currentFilePaths = {
                thumbnail: `/results/${currentBaseName}/${currentBaseName}/thumbnail.png`,
                overlay_he: `/results/${currentBaseName}/${currentBaseName}/overlay_he.png`,
                raw_map: `/results/${currentBaseName}/${currentBaseName}/raw_map.png`,
                refined_mask: `/results/${currentBaseName}/${currentBaseName}/refined_map.png`,
                adaptive_roi: `/results/${currentBaseName}/${currentBaseName}/adaptive_roi.png`
            };

            document.getElementById('uploadBtn').disabled = false;
            viewSelector.disabled = false;
            annotationToggle.disabled = false;
            annotationToggle.checked = false;
            document.getElementById('gridSelector').disabled = false;
            document.getElementById("annotation-overlay").innerHTML = "";
            document.getElementById("progress-container").style.display = "none";

            // Force dropdown to live deep zoom
            viewSelector.value = "deepzoom";
            changeView();
        }

        async function loadScalebar() {
            if (viewer.scalebarInstance) return; // Already loaded

            try {
                const res = await fetch(`/slide/${originalFileName}/metadata`);
                const data = await res.json();
                if (data.mpp) {
                    slideMPP = data.mpp;
                    slideWidth = data.width;
                    slideHeight = data.height;

                    viewer.scalebar({
                        type: OpenSeadragon.ScalebarType.MICROSCOPY,
                        pixelsPerMeter: (1 / data.mpp) * 1e6,
                        minWidth: "100px",
                        location: OpenSeadragon.ScalebarLocation.BOTTOM_LEFT,
                        xOffset: 20,
                        yOffset: 20,
                        stayInsideImage: false,
                        color: "black",
                        fontColor: "black",
                        backgroundColor: "rgba(255, 255, 255, 0.7)",
                        fontSize: "medium",
                        barThickness: 4
                    });
                }
            } catch (e) {
                console.error("Scalebar metadata load failed", e);
            }
        }

        // --- ANNOTATION ENGINE ---
        async function toggleAnnotations() {
            const isChecked = document.getElementById("annotationToggle").checked;
            const svgOverlay = document.getElementById("annotation-overlay");

            if (isChecked) {
                try {
                    const response = await fetch(`/results/${currentBaseName}/${currentBaseName}/annotations.json`);
                    if (!response.ok) throw new Error("JSON not found");
                    
                    annotationsData = await response.json();
                    drawPolygons();
                } catch (e) {
                    console.error("Could not load annotations.json", e);
                    alert("annotations.json not found. Check if engine.py generated it.");
                    document.getElementById("annotationToggle").checked = false;
                }
            } else {
                svgOverlay.innerHTML = "";
            }
        }

        function drawPolygons() {
            const svgOverlay = document.getElementById("annotation-overlay");
            svgOverlay.innerHTML = ""; 

            const tiledImage = viewer.world.getItemAt(0);
            if (!tiledImage) return;

            let features = [];
            if (annotationsData.type === "FeatureCollection") {
                features = annotationsData.features;
            } else if (Array.isArray(annotationsData)) {
                features = annotationsData;
            }

            features.forEach(feature => {
                let coords = [];
                
                if (feature.geometry && feature.geometry.coordinates) {
                    coords = feature.geometry.coordinates[0];
                } else if (feature.coordinates) {
                    coords = feature.coordinates;
                }

                if (coords && coords.length > 0) {
                    let pointsString = "";
                    coords.forEach(coord => {
                        const viewportPoint = tiledImage.imageToViewportCoordinates(coord[0], coord[1]);
                        const screenPoint = viewer.viewport.pixelFromPoint(viewportPoint);
                        pointsString += `${screenPoint.x},${screenPoint.y} `;
                    });

                    const polygon = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
                    polygon.setAttribute("points", pointsString.trim());
                    polygon.setAttribute("fill", "rgba(0, 255, 0, 0.3)"); 
                    polygon.setAttribute("stroke", "#00ff00");
                    polygon.setAttribute("stroke-width", "2");

                    svgOverlay.appendChild(polygon);
                }
            });
        }

        function toggleGrid() {
            const existing = document.getElementById(gridOverlayId);
            if (existing) {
                viewer.removeOverlay(existing);
            }

            const gridValue = document.getElementById("gridSelector").value;
            if (gridValue === "none") return;

            if (!slideMPP || !slideWidth || !slideHeight) {
                alert("Slide metadata (MPP and dimensions) not available. Cannot draw accurate grid.");
                document.getElementById("gridSelector").value = "none";
                return;
            }

            const microns = parseInt(gridValue, 10);
            const physicalWidthMicrons = slideWidth * slideMPP;
            const gridSpacingViewport = microns / physicalWidthMicrons;
            const aspectRatio = slideHeight / slideWidth;

            const svgNS = "http://www.w3.org/2000/svg";
            const svg = document.createElementNS(svgNS, "svg");
            svg.id = gridOverlayId;
            svg.setAttribute("width", "100%");
            svg.setAttribute("height", "100%");
            svg.setAttribute("preserveAspectRatio", "none");
            svg.setAttribute("viewBox", `0 0 1 ${aspectRatio}`);
            
            // Draw vertical lines
            for (let x = 0; x <= 1; x += gridSpacingViewport) {
                const line = document.createElementNS(svgNS, "line");
                line.setAttribute("x1", x);
                line.setAttribute("y1", 0);
                line.setAttribute("x2", x);
                line.setAttribute("y2", aspectRatio);
                line.setAttribute("stroke", "rgba(52, 152, 219, 0.6)"); // Light blue, semi-transparent
                line.setAttribute("stroke-width", "1");
                line.setAttribute("vector-effect", "non-scaling-stroke");
                svg.appendChild(line);
            }

            // Draw horizontal lines
            for (let y = 0; y <= aspectRatio; y += gridSpacingViewport) {
                const line = document.createElementNS(svgNS, "line");
                line.setAttribute("x1", 0);
                line.setAttribute("y1", y);
                line.setAttribute("x2", 1);
                line.setAttribute("y2", y);
                line.setAttribute("stroke", "rgba(52, 152, 219, 0.6)");
                line.setAttribute("stroke-width", "1");
                line.setAttribute("vector-effect", "non-scaling-stroke");
                svg.appendChild(line);
            }

            viewer.addOverlay({
                element: svg,
                location: new OpenSeadragon.Rect(0, 0, 1, aspectRatio)
            });
        }

        viewer.addHandler('open', () => {
            toggleGrid();
        });

        viewer.addHandler('animation', () => {
            if (document.getElementById("annotationToggle").checked) {
                drawPolygons();
            }
        });
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)

@app.get("/status/{task_id}")
async def get_status(task_id: str):
    info = task_status.get(task_id, {"status": "Unknown Task ID", "progress": 0})
    if isinstance(info, str):
        return {"task_id": task_id, "status": info, "progress": 0}
    return {"task_id": task_id, "status": info["status"], "progress": info.get("progress", 0)}

@app.post("/upload")
async def upload_svs(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    task_id = file.filename 
    
    task_status[task_id] = {"status": "Uploading...", "progress": 0}
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        task_status[task_id] = {"status": f"Upload failed: {str(e)}", "progress": 0}
        raise HTTPException(status_code=500, detail="Could not save file.")

    background_tasks.add_task(run_tepseg_logic, file_path, file.filename, task_id)
    
    return {
        "info": f"File '{file.filename}' uploaded successfully.",
        "status_check": f"http://127.0.0.1:8000/status/{task_id}"
    }

def run_tepseg_logic(file_path: str, filename: str, task_id: str):
    print(f"\n--- BACKGROUND TASK INITIATED FOR {filename} ---")
    try:
        output_subdir = os.path.join(RESULT_DIR, filename.split('.')[0])
        nested_output_dir = os.path.join(output_subdir, filename.split('.')[0])
        os.makedirs(nested_output_dir, exist_ok=True)
        
        print("1. Attempting to extract clean thumbnail via OpenSlide...")
        task_status[task_id] = {"status": "Step 1: Extracting clean thumbnail...", "progress": 5}
        
        try:
            slide = openslide.OpenSlide(file_path)
            thumb = slide.get_thumbnail((2048, 2048)) 
            thumb_path = os.path.join(nested_output_dir, "thumbnail.png")
            thumb.save(thumb_path)
            print(f"-> Thumbnail saved successfully at {thumb_path}")
        except Exception as e:
            print(f"-> Thumbnail extraction failed (skipping): {e}")
        
        print("2. Starting TEPSEG GPU Pipeline...")
        task_status[task_id] = {"status": "Step 2: Running GPU Pipeline...", "progress": 10}
        
        checkpoint_dir = os.path.abspath("TEPSEG/checkpoints_20x256univ2")
        
        cmd = [
            sys.executable, 
            "TEPSEG/run_tepseg.py",
            "--input_path", file_path,
            "--output_dir", output_subdir,
            "--uni_dir", checkpoint_dir,
            "--clf_path", os.path.join(checkpoint_dir, "best_model.pth"),
            "--save_masks"
        ]
        
        import re
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)
        
        buffer = ""
        while True:
            char = process.stdout.read(1)
            if not char:
                break
            if char == '\r' or char == '\n':
                line = buffer.strip()
                buffer = ""
                if line:
                    match = re.search(r'(\d+)%\|', line)
                    if match:
                        pct = int(match.group(1))
                        overall_pct = 10 + int(pct * 0.85)  # Scale GPU processing from 10% to 95%
                        task_status[task_id] = {"status": f"Step 2: GPU Pipeline ({pct}%)...", "progress": overall_pct}
                    elif "Pipeline finished" in line:
                        task_status[task_id] = {"status": "Step 3: Finishing up...", "progress": 98}
            else:
                buffer += char
                
        process.wait()
        
        if process.returncode == 0:
            print("3. TEPSEG Pipeline Completed!")
            task_status[task_id] = {"status": "Completed! Results available in viewer.", "progress": 100}
        else:
            print(f"!!! TEPSEG Subprocess Error (Exit {process.returncode})")
            task_status[task_id] = {"status": "Error: TEPSEG Pipeline Failed.", "progress": 0}
        
    except Exception as e:
        print(f"!!! System Error: {e}")
        task_status[task_id] = {"status": f"Error: System Failure - {str(e)}", "progress": 0}