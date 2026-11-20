"""python -m gateway_vision.check_model model.onnx : checks the contract and runs one dummy frame."""
import io
import sys
from PIL import Image
from .classifier import OnnxClassifier

if __name__ == "__main__":
    c = OnnxClassifier(sys.argv[1])
    buf = io.BytesIO(); Image.new("RGB", (160, 120), (90, 120, 80)).save(buf, "JPEG")
    print(c.name, c.predict(buf.getvalue()))
