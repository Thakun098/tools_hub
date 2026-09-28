# Third-party notices

Image Universal Tools uses the following projects in its separately built engine:

- Pillow — HPND license
- rembg — MIT license
- ONNX Runtime — MIT license
- NumPy — BSD-3-Clause license
- SciPy — BSD-3-Clause license
- scikit-image — BSD-3-Clause license
- pymatting — MIT license
- pooch — BSD-3-Clause license

The license files shipped by the Python distributions used for the release build are consolidated in `licenses/ENGINE_DEPENDENCY_LICENSES.txt`. The file intentionally includes build-time distributions too, so the archive errs on the side of retaining notices.

Downloaded model families:

- U²-Net / u2netp — Apache-2.0
- DIS / isnet-general-use — Apache-2.0
- BiRefNet — MIT

Model weights are not bundled. The user explicitly downloads a selected model from the upstream rembg GitHub release. Source URLs and license names are shown by the Plugin API and UI.
