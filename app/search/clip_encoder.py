#purpose: encode images with CLIP for semantic understanding of images
#CLIP understand image content eg beach, person, code, diagram, etc

import numpy as np
from PIL import Image
from transformers import CLIPProcessor, CLIPModel

#image vector dim for CLIP
IMAGE_VECTOR_DIM = 512

#Load CLIP model
print("[SYSTEM] Loading CLIP model for image understanding...")
_clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
_clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
print("[SYSTEM] CLIP model loaded successfully")

def encode_image(image_path: str) -> np.ndarray:
    """
    Encodes an image into a vector using CLIP

    args:
        image_path: path to the image
    returns:
        numpy array of shape (512,) representing the image
    """
    try:
        # Load and process image
        image = Image.open(image_path).convert("RGB")
        inputs = _clip_processor(images=image, return_tensors="pt")

        # Get image embedding
        image_features = _clip_model.get_image_features(**inputs)

        # Convert to numpy and normalize
        vector = image_features.detach().numpy()[0]
        vector = vector.astype(np.float32)

        # Normalize for better similarity matching
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm

        return vector

    except Exception as e:
        print(f"[ERROR] Failed to encode image {image_path}: {e}")
        raise

def encode_text_for_image_search(text: str) -> np.ndarray:
    """
    Encode text query to search for images
    Eg: "beach sunset" -> finds images of beaches

    args:
        text: search query text
    returns:
        numpy array of shape (512,) in CLIP image space
    """
    try:
        inputs = _clip_processor(text=[text], return_tensors="pt", padding=True)
        text_features = _clip_model.get_text_features(**inputs)

        vector = text_features.detach().numpy()[0]
        vector = vector.astype(np.float32)

        # Normalize
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm

        return vector

    except Exception as e:
        print(f"[ERROR] Failed to encode text query: {e}")
        raise

