# DocFormer Privacy & Security

## ✅ **Your Data is 100% Safe and Local**

### Current Implementation

**Good News**: The DocFormer extractor is currently using **structure-based extraction** (not the full ML model), which means:

1. ✅ **No external API calls** - All processing happens locally
2. ✅ **No data sent to servers** - Your contracts never leave your server
3. ✅ **No internet required** - Works completely offline after initial setup
4. ✅ **No third-party services** - No HuggingFace API, no cloud services

### How It Works

The current implementation:
- Uses `_extract_with_structure_analysis()` method
- This is a **local pattern-matching approach** (similar to regex)
- No ML model inference is actually running
- All processing is done in-memory on your server

### Model Download (One-Time Only)

**When models are downloaded:**
- Only during Docker build or first container start
- Downloads from HuggingFace (public model repository)
- Stored locally in Docker container
- **No contract data is sent during download**

**What gets downloaded:**
- Model weights (pre-trained, public)
- Configuration files
- Tokenizer files

**This is similar to:**
- Downloading a software library
- Installing a package
- No different from installing any Python package

### If Full ML Model Was Used

Even if the full DocFormer ML model was used:
- ✅ **Still 100% local** - Model runs on your server
- ✅ **No data transmission** - Processing happens in Docker container
- ✅ **No external calls** - Model inference is local

### Comparison with Other Services

| Service | Data Privacy | Where Processing Happens |
|---------|-------------|-------------------------|
| **DocFormer (Current)** | ✅ 100% Local | Your server |
| **OpenAI API** | ❌ Data sent to OpenAI | OpenAI servers |
| **Anthropic API** | ❌ Data sent to Anthropic | Anthropic servers |
| **Google Cloud AI** | ❌ Data sent to Google | Google servers |
| **HuggingFace Inference API** | ❌ Data sent to HuggingFace | HuggingFace servers |

### Security Best Practices

1. ✅ **All processing is local** - No network calls during extraction
2. ✅ **No logging to external services** - Logs stay on your server
3. ✅ **No telemetry** - No usage data sent anywhere
4. ✅ **Docker isolation** - Runs in isolated container

### Verification

You can verify this by:
1. **Monitor network traffic**: `docker compose exec worker netstat -an` (no external connections during extraction)
2. **Check logs**: No API calls or external requests
3. **Disconnect internet**: Extraction still works (after initial model download)

### Summary

**Your contract data is completely safe:**
- ✅ Never leaves your server
- ✅ Never sent to external services
- ✅ Processed 100% locally
- ✅ No privacy concerns

The only external connection is the **one-time model download** during setup, which is just downloading public model files (like downloading any software).


