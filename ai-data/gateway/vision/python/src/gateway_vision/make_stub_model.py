"""Builds the PLUMBING STUB: a colour heuristic in ONNX, used only to test the service. NOT a fire detector."""
import sys
import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper

# mean RGB (after ImageNet normalisation) -> logits (background, fire, smoke)
W = np.array([[0.0, 1.0, 0.0],      # R
              [0.0, -0.3, 0.0],     # G
              [0.0, -1.0, 0.0]],    # B
             dtype=np.float32)
B = np.array([0.5, 0.0, 0.0], dtype=np.float32)
# smoke = low saturation and bright: handled by a second term on the mean of all channels
W[:, 2] = 0.8   # brightness raises smoke
B[2] = -0.2


def build(path):
    x = helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 3, 224, 224])
    y = helper.make_tensor_value_info("logits", TensorProto.FLOAT, [1, 3])
    nodes = [
        helper.make_node("ReduceMean", ["input"], ["m"], axes=[2, 3], keepdims=0),
        helper.make_node("MatMul", ["m", "W"], ["z"]),
        helper.make_node("Add", ["z", "B"], ["logits"]),
    ]
    g = helper.make_graph(nodes, "plumbing_color_stub", [x], [y],
                          [numpy_helper.from_array(W, "W"), numpy_helper.from_array(B, "B")])
    m = helper.make_model(g, opset_imports=[helper.make_opsetid("", 13)])
    m.ir_version = 8
    onnx.checker.check_model(m)
    onnx.save(m, path)


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "plumbing_color_stub.onnx")
