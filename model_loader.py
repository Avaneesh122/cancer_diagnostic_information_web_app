import torch

from your_architecture_file import MyModel 

def get_model():
    model = MyModel()
    # map_location='cpu' is safer for an MVP unless you have a local GPU (CUDA)
    state_dict = torch.load("models/pytorch_model.bin", map_location=torch.device('cpu'))
    model.load_state_dict(state_dict)
    model.eval()
    return model