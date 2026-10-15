# Local parsing models

Weights are downloaded into the ignored `.local/docling-models` directory, not committed to this repository. No model training or upstream source modification is performed.

| Component                   | Upstream                                                    | License / provenance                                                                                      | Use                       |
| --------------------------- | ----------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | ------------------------- |
| Heron layout                | https://huggingface.co/docling-project/docling-layout-heron | Apache-2.0, downloaded model card                                                                         | PDF region detection      |
| TableFormer                 | https://huggingface.co/docling-project/docling-models       | CDLA-Permissive-2.0, downloaded model card                                                                | PDF table structure       |
| EasyOCR CRAFT and zh_sim_g2 | https://github.com/JaidedAI/EasyOCR                         | EasyOCR Apache-2.0; release URLs and expected weight MD5 values supplied by installed `easyocr/config.py` | Local Chinese/English OCR |

The preparation script uses fixed Hugging Face repository commits recorded in `models.lock.json`, then verifies every downloaded file against its SHA-256. EasyOCR uses the exact upstream release assets declared by the installed package, checks upstream MD5 and the release SHA-256 manifest, and extracts only the expected weight member. HTTPS certificate validation remains enabled. Layout, ONNX layout and TableFormer model cards are retained with their weights. Complete Apache-2.0 and CDLA-Permissive-2.0 texts are in `licenses/` and bundled under `resources/notices/models`; all Python distribution license files are retained with vendored packages. Model files are unmodified.

Pinned commits: Heron `8f39ad3c0b4c58e9c2d2c84a38465abf757272d8`; Heron ONNX `40bde044036bb181c130ddf6c51792187268748f`; TableFormer repository `fc0f2d45e2218ea24bce5045f58a389aed16dc23`.

Docling 2.135.0's RapidOCR downloader expected an unavailable symbol in RapidOCR 3.10.0. This project uses the supported EasyOCR adapter instead; RapidOCR remains a transitive Docling dependency but is not selected at runtime.
