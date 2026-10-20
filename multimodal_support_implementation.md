# Multimodal Support Implementation

This document outlines the implementation plan for adding vision and audio transcription capabilities using secondary GPUs.

## Hardware Overview

| GPU | VRAM | Role |
|-----|------|------|
| Main GPU | - | Primary 120B thinking model |
| GTX 1080 Ti | 11GB | Vision/image description |
| GTX 1060 | 6GB | Audio transcription (Whisper) |

## Vision Model Options

### Recommended Models for 1080 Ti (11GB VRAM)

#### Tier 1: Best Fit (4-6GB VRAM)

| Model | Quantized Size | VRAM Usage | Notes |
|-------|----------------|------------|-------|
| **Gemma 3 4B** | ~3.2GB | ~4GB | Best balance. ~15s/image, 63 t/s generation |
| **SmolVLM 2B** | ~1.5GB | ~2-3GB | Smallest, surprisingly capable |
| **Qwen2.5-VL 7B Q4** | ~4.4GB | ~5-6GB | Excellent quality, strong OCR/document understanding |

#### Tier 2: Full VRAM Usage (8-10GB)

| Model | Quantized Size | VRAM Usage | Notes |
|-------|----------------|------------|-------|
| **MiniCPM-V 2.6** | 8B params | ~6GB (int4) | GPT-4o level on benchmarks, 75% fewer tokens |
| **Llama 3.2 Vision 11B** | Q4: ~6GB | ~8GB | Strong reasoning, tight fit |

### Primary Recommendation

**Qwen2.5-VL 7B Q4** - Excellent image understanding, strong OCR capabilities, fits comfortably in 11GB.

Download: https://huggingface.co/Mungert/Qwen2.5-VL-7B-Instruct-GGUF

### Performance Expectations (1080 Ti)

The GTX 1080 Ti lacks tensor cores, resulting in slower inference compared to modern GPUs:

- Token generation: ~24 t/s (on 14B Q4 models)
- Prompt processing: ~45 t/s
- **Expected image processing time: 15-30 seconds per image**

This is acceptable for a preprocessing step where image descriptions are generated before being passed to the main thinking model.

### Running Vision Models with llama.cpp

Vision support was added to llama.cpp in May 2025 via libmtmd. Two files are required:
- Main GGUF model file
- `mmproj` (multimodal projector) file

```bash
# Download model files
# Main model: Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf
# Projector: mmproj-Qwen2.5-VL-7B-Instruct-f16.gguf

# Start server on specific GPU
CUDA_VISIBLE_DEVICES=1 ./llama-server \
    --model Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf \
    --mmproj mmproj-Qwen2.5-VL-7B-Instruct-f16.gguf \
    --host 0.0.0.0 \
    --port 8081

# Or use CLI for testing
./llama-mtmd-cli -m Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf \
    --mmproj mmproj-Qwen2.5-VL-7B-Instruct-f16.gguf
```

The server exposes an OpenAI-compatible API, allowing integration via `OPENAI_BASE_URL`.

## Audio Transcription (Whisper)

### Recommended Setup for 1060 (6GB VRAM)

Use **faster-whisper** instead of vanilla OpenAI Whisper - it's 4x faster with the same accuracy and lower memory usage.

Repository: https://github.com/SYSTRAN/faster-whisper

### Model Options

| Model | VRAM | Speed (10s audio) | Quality |
|-------|------|-------------------|---------|
| tiny | ~1GB | ~0.2s | Basic |
| base | ~1GB | ~0.3s | Good |
| **small** | ~2GB | ~0.6s | Recommended |
| medium | ~5GB | ~1.1s | High quality |
| large | ~10GB | N/A | Won't fit on 6GB |

### Primary Recommendation

**faster-whisper small** - Best balance of speed and accuracy for 6GB VRAM.

### Installation and Usage

```bash
# Install faster-whisper
pip install faster-whisper

# Python usage
from faster_whisper import WhisperModel

# Load model on specific GPU
model = WhisperModel("small", device="cuda", device_index=2, compute_type="float16")

# Transcribe
segments, info = model.transcribe("audio.mp3", beam_size=5)
for segment in segments:
    print(f"[{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text}")
```

### Running as a Service

```bash
# Using faster-whisper-server (OpenAI-compatible API)
pip install faster-whisper-server

CUDA_VISIBLE_DEVICES=2 faster-whisper-server --model small --host 0.0.0.0 --port 8082
```

## Integration with Existing Backend

### Environment Variables

Add to `.env`:

```bash
# Vision Model (llama.cpp server)
VISION_MODEL_URL=http://localhost:8081/v1
VISION_MODEL=qwen2.5-vl-7b

# Whisper (faster-whisper server)
WHISPER_URL=http://localhost:8082/v1
LOCAL_WHISPER_MODEL=small
USE_LOCAL_WHISPER=true
```

### Architecture Flow

```
User uploads image
       │
       ▼
┌──────────────────┐
│  Vision Model    │  (1080 Ti - Port 8081)
│  Qwen2.5-VL 7B   │
└────────┬─────────┘
         │ Image description (text)
         ▼
┌──────────────────┐
│  Main LLM        │  (Main GPU - Port 8080)
│  120B Model      │
└────────┬─────────┘
         │
         ▼
    Response to user


User uploads audio
       │
       ▼
┌──────────────────┐
│  Whisper         │  (1060 - Port 8082)
│  faster-whisper  │
└────────┬─────────┘
         │ Transcription (text)
         ▼
┌──────────────────┐
│  Main LLM        │  (Main GPU - Port 8080)
│  120B Model      │
└────────┬─────────┘
         │
         ▼
    Response to user
```

## GPU Assignment

Ensure each model runs on its designated GPU:

```bash
# Main model (GPU 0)
CUDA_VISIBLE_DEVICES=0 ./start_main_model.sh

# Vision model (GPU 1 - 1080 Ti)
CUDA_VISIBLE_DEVICES=1 ./llama-server --model qwen2.5-vl-7b-q4.gguf ...

# Whisper (GPU 2 - 1060)
CUDA_VISIBLE_DEVICES=2 faster-whisper-server --model small ...
```

## Performance Summary

| Task | GPU | Expected Latency |
|------|-----|------------------|
| Image description | 1080 Ti | 15-30 seconds |
| Audio transcription (10s) | 1060 | ~0.6 seconds |
| Main LLM response | Main GPU | Varies |

## Alternative: Single-GPU Solution (Intel Arc)

Instead of using multiple older GPUs with USB risers (which bottleneck at 1 Gbps), a single Intel Arc GPU can handle both vision and Whisper workloads.

### Hardware Options

| GPU | VRAM | New Price | Used Price | Notes |
|-----|------|-----------|------------|-------|
| **Intel Arc A770** | 16GB | ~$320 | **~$230** | Best VRAM/$ ratio, recommended |
| **Intel Arc B580** | 12GB | **~$240** | - | Newer architecture, more efficient |
| **Intel Arc A750** | 8GB | ~$200 | ~$170 | Tight for running both models |

### Recommended: Used Intel Arc A770 (~$230)

- **16GB VRAM** - Run vision model (5-6GB) + Whisper (2GB) simultaneously with headroom
- **~70 t/s on Mistral 7B** with IPEX-LLM optimization
- Outperforms RTX 4060 in LLM inference due to higher VRAM
- Single PCIe slot, no riser bottlenecks

Purchase: [eBay Intel Arc A770 listings](https://www.ebay.com/p/22059285100)

### Software Stack (Intel Arc)

Intel Arc uses IPEX-LLM or OpenVINO instead of CUDA:

```bash
# Option 1: Ollama with OpenVINO backend
pip install openvino openvino-tokenizers
ollama serve  # With Intel GPU detection

# Option 2: IPEX-LLM for llama.cpp
pip install ipex-llm[xpu]

# Run llama.cpp with Intel GPU
python -m ipex_llm.llamacpp.server \
    --model Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf \
    --mmproj mmproj-Qwen2.5-VL-7B-Instruct-f16.gguf \
    --host 0.0.0.0 --port 8081
```

### Whisper on Intel Arc (OpenVINO)

Use OpenVINO Whisper instead of faster-whisper:

```bash
pip install openvino-whisper

# Python usage
from openvino_whisper import WhisperModel

model = WhisperModel("small", device="GPU")
result = model.transcribe("audio.mp3")
print(result["text"])
```

Repository: [OpenVINO Whisper notebooks](https://github.com/openvinotoolkit/openvino_notebooks/tree/main/notebooks/whisper-subtitles-generation)

### Architecture (Single Intel Arc GPU)

```
User uploads image/audio
         │
         ▼
┌────────────────────────┐
│    Intel Arc A770      │  (Port 8081)
│  ┌──────────────────┐  │
│  │ Vision Model     │  │  Qwen2.5-VL 7B (~6GB)
│  │ Whisper          │  │  OpenVINO Whisper (~2GB)
│  └──────────────────┘  │
│     ~8GB used / 16GB   │
└───────────┬────────────┘
            │ Text description/transcription
            ▼
┌──────────────────┐
│  Main LLM        │  (Main GPU - Port 8080)
│  120B Model      │
└────────┬─────────┘
         │
         ▼
    Response to user
```

### Comparison: Multi-GPU vs Single Intel Arc

| Aspect | 1080 Ti + 1060 | Intel Arc A770 |
|--------|----------------|----------------|
| Cost | Already owned | ~$230 used |
| Slots | 2 PCIe (or USB risers) | 1 PCIe |
| VRAM | 11GB + 6GB (separate) | 16GB (shared) |
| Power | ~250W + 120W | ~190W |
| Software | CUDA (mature) | OpenVINO (some tinkering) |
| Performance | Slower (no tensor cores) | ~70 t/s (7B models) |

### Why Not AMD?

The AMD RX 7600 XT 16GB exists (~$300) but ROCm support is unofficial for RDNA3 consumer cards. Requires `HSA_OVERRIDE_GFX_VERSION` workarounds and more troubleshooting than Intel Arc.

## References

- [llama.cpp vision support](https://simonwillison.net/2025/May/10/llama-cpp-vision/)
- [Qwen2.5-VL 7B GGUF](https://huggingface.co/Mungert/Qwen2.5-VL-7B-Instruct-GGUF)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [GTX 1080 Ti for Local LLM](https://getgather.substack.com/p/gtx-1080-ti-for-local-llm)
- [Whisper GPU Benchmarks](https://github.com/openai/whisper/discussions/918)
- [MiniCPM-V](https://github.com/OpenBMB/MiniCPM-V)
- [SmolVLM](https://huggingface.co/blog/smolvlm)
- [Intel Arc A770 eBay listings](https://www.ebay.com/p/22059285100)
- [Intel Arc B580 vs A770 for AI](https://www.propelrc.com/intel-arc-b580-and-a770-for-local-ai-software/)
- [Arc A770 price tracker](https://bestvaluegpu.com/history/new-and-used-a770-price-history-and-specs/)
- [Intel Arc Ollama/OpenVINO guide](https://markaicode.com/intel-arc-gpu-ollama-openvino-tutorial/)
- [OpenVINO Whisper notebooks](https://github.com/openvinotoolkit/openvino_notebooks/tree/main/notebooks/whisper-subtitles-generation)
- [llama.cpp ROCm compatibility](https://rocm.docs.amd.com/en/latest/compatibility/ml-compatibility/llama-cpp-compatibility.html)
