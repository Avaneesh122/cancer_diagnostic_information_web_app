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
    <style>
        body { font-family: Arial, sans-serif; background-color: #121212; color: #ffffff; margin: 0; padding: 0; display: flex; flex-direction: column; height: 100vh; }
        #header { padding: 15px; background-color: #1e1e1e; text-align: center; border-bottom: 1px solid #333; }
        #controls { padding: 10px; text-align: center; background-color: #252526; display: flex; justify-content: center; align-items: center; gap: 15px; flex-wrap: wrap; }
        
        button, select { background-color: #0e639c; color: white; border: none; padding: 10px 15px; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 14px; }
        button:hover, select:hover { background-color: #1177bb; }
        button:disabled, select:disabled { background-color: #555; cursor: not-allowed; }
        
        .checkbox-container { display: flex; align-items: center; gap: 5px; cursor: pointer; font-weight: bold; }
        #status { color: #f39c12; font-weight: bold; margin-left: 15px; min-width: 250px; text-align: left; }
        
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
        
        <div id="status">Ready for upload.</div>
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

        function changeView() {
            const selectedKey = document.getElementById("viewSelector").value;
            
            if (selectedKey === "deepzoom") {
                viewer.open(`/slide/${originalFileName}.dzi`);
            } else if (currentFilePaths[selectedKey]) {
                viewer.open({ type: 'image', url: currentFilePaths[selectedKey] });
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
            uploadBtn.disabled = true;
            viewSelector.disabled = true;
            annotationToggle.disabled = true;
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
            document.getElementById("annotation-overlay").innerHTML = "";

            // Force dropdown to live deep zoom
            viewSelector.value = "deepzoom";
            changeView();
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

            // Step 1: Format-blind check (handles GeoJSON or simple lists)
            let features = [];
            if (annotationsData.type === "FeatureCollection") {
                features = annotationsData.features;
            } else if (Array.isArray(annotationsData)) {
                features = annotationsData;
            }

            // Step 2: Loop through and extract coordinates safely
            features.forEach(feature => {
                let coords = [];
                
                if (feature.geometry && feature.geometry.coordinates) {
                    // GeoJSON format (grabs the outer ring of the polygon)
                    coords = feature.geometry.coordinates[0];
                } else if (feature.coordinates) {
                    // Simple list format
                    coords = feature.coordinates;
                }

                // Step 3: Draw the polygon if we found valid coordinates
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
    return {"task_id": task_id, "status": task_status.get(task_id, "Unknown Task ID")}

@app.post("/upload")
async def upload_svs(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    task_id = file.filename 
    
    task_status[task_id] = "Processing started..."
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        task_status[task_id] = f"Upload failed: {str(e)}"
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
        task_status[task_id] = "Step 1: Extracting clean thumbnail..."
        
        try:
            slide = openslide.OpenSlide(file_path)
            thumb = slide.get_thumbnail((2048, 2048)) 
            thumb_path = os.path.join(nested_output_dir, "thumbnail.png")
            thumb.save(thumb_path)
            print(f"-> Thumbnail saved successfully at {thumb_path}")
        except Exception as e:
            print(f"-> Thumbnail extraction failed (skipping): {e}")
        
        print("2. Starting TEPSEG GPU Pipeline...")
        task_status[task_id] = "Step 2: Running GPU Pipeline (Check terminal)..."
        
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
        
        subprocess.run(cmd, check=True)
        print("3. TEPSEG Pipeline Completed!")
        
        task_status[task_id] = "Completed! Results available in viewer."
        
    except subprocess.CalledProcessError as e:
        print(f"!!! TEPSEG Subprocess Error: {e}")
        task_status[task_id] = f"Error: TEPSEG Pipeline Failed."
    except Exception as e:
        print(f"!!! System Error: {e}")
        task_status[task_id] = f"Error: System Failure."