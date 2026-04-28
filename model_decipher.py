import torch

# Define the path
model_path = r"C:\Users\asbhoit\Documents\cancer_app\models\pytorch_model.bin"

# Load the file
content = torch.load(model_path, map_location="cpu")

# 1. Check if it's a full model or just weights
print(f"Content type: {type(content)}")

# 2. If it's a dictionary (most likely), show the layer names
if isinstance(content, dict):
    print("\nFirst 10 layer keys:")
    keys = list(content.keys())
    for key in keys[:10]:
        print(f" - {key}")
else:
    # If it's the full object, this will tell you the class name directly
    print(f"\nModel Class Name: {content.__class__.__name__}")