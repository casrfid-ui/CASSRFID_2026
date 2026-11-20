# Training the gateway CNN (on the team PC)

1. Data: D-Fire (fire/smoke images) plus negatives from the target environment (forest, sun glare, fog, dust, sunset, clouds). Split **by site or sequence**, never by image, so near-duplicates do not leak across splits.
2. Model: a small pretrained backbone fine-tuned (for example MobileNetV3-small or EfficientNet-B0 class) with 3 outputs, order **background, fire, smoke**, input 224×224, ImageNet normalisation.
3. Export: `torch.onnx.export(model, x, "fire_cls.onnx", input_names=["input"], output_names=["logits"], opset_version=13)`, opset ≥ 11.
4. Check: `python -m gateway_vision.check_model fire_cls.onnx` (shape and output contract) then run the service with `--model fire_cls.onnx`.
5. Calibrate: fit a temperature on a held-out set; report precision/recall per class and the false-alarm rate on background-only footage per day. Log the experiment in `docs/research/` with its failures.
6. Camera domain: collect real OV2640 JPEGs (the service stores every frame it receives) and fine-tune on them; the box camera is low quality and a model trained only on D-Fire may transfer badly.
