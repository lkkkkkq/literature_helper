# Local parsing models

## Parser 0.2.0 additions

The isolated runtime uses MinerU 4.0.12 and Standard local inference. MinerU's installed license is Apache-2.0 **with additional conditions**; retain the complete installed license, including its online attribution and commercial-scale clauses. It is not described here as unconditional Apache-only software.

The ONNX collection is `opendatalab/MinerU-4_models_onnx`. Its manifest names the original PaddlePaddle layout/OCR, FormulaNet and MinerU table repositories and revisions. Downloaded original model metadata declares Apache-2.0; the aggregate collection delegates to original model licenses. VLM GGUF files come from `jinzhenj/MinerU2.5-Pro-2605-1.2B-GGUF`; the original `opendatalab/MinerU2.5-Pro-2605-1.2B` model card declares Apache-2.0. The quantized repository did not provide an independent model card/license field when inspected; original attribution is preserved, and this record is not a blanket commercial-use legal determination.

Exact distributed model file hashes are in `parser-next.models.lock.json`. Model cards, API metadata and ONNX provenance manifest are archived under the release's `resources/notices/parser-next/model-provenance`. No user papers or trained/customized weights are included.

Pandoc 3.6.1 is an unmodified separate executable, GPL version 2 or later with exceptions described in its COPYRIGHT file. Its COPYRIGHT and the matching upstream source archive are bundled in the parser notices. The manual chart digitizer is project code; no WebPlotDigitizer code was copied. Python distribution license files remain with the runtime and are also collected in notices.

## Existing parser models

Weights are downloaded into the ignored `.local/docling-models` directory, not committed to this repository. No model training or upstream source modification is performed.

| Component                   | Upstream                                                    | License / provenance                                                                                      | Use                       |
| --------------------------- | ----------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | ------------------------- |
| Heron layout                | https://huggingface.co/docling-project/docling-layout-heron | Apache-2.0, downloaded model card                                                                         | PDF region detection      |
| TableFormer                 | https://huggingface.co/docling-project/docling-models       | CDLA-Permissive-2.0, downloaded model card                                                                | PDF table structure       |
| EasyOCR CRAFT and zh_sim_g2 | https://github.com/JaidedAI/EasyOCR                         | EasyOCR Apache-2.0; release URLs and expected weight MD5 values supplied by installed `easyocr/config.py` | Local Chinese/English OCR |

The preparation script uses fixed Hugging Face repository commits recorded in `models.lock.json`, then verifies every downloaded file against its SHA-256. EasyOCR uses the exact upstream release assets declared by the installed package, checks upstream MD5 and the release SHA-256 manifest, and extracts only the expected weight member. HTTPS certificate validation remains enabled. Layout, ONNX layout and TableFormer model cards are retained with their weights. Complete Apache-2.0 and CDLA-Permissive-2.0 texts are in `licenses/` and bundled under `resources/notices/models`; all Python distribution license files are retained with vendored packages. Model files are unmodified.

Pinned commits: Heron `8f39ad3c0b4c58e9c2d2c84a38465abf757272d8`; Heron ONNX `40bde044036bb181c130ddf6c51792187268748f`; TableFormer repository `fc0f2d45e2218ea24bce5045f58a389aed16dc23`.

Docling 2.135.0's RapidOCR downloader expected an unavailable symbol in RapidOCR 3.10.0. This project uses the supported EasyOCR adapter instead; RapidOCR remains a transitive Docling dependency but is not selected at runtime.
