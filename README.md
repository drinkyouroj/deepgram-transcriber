# Deepgram Audio Transcriber

A comprehensive Python CLI tool that transcribes audio files and URLs to SRT/VTT subtitle formats using Deepgram's powerful speech-to-text API.

## Features

- **Multiple Input Sources**: Local audio files or URLs
- **Format Support**: All Deepgram-supported formats (MP3, WAV, FLAC, AAC, M4A, OGG, OPUS, WebM, MP4, MOV, AVI, MKV, WMV, 3GP, AMR, AIFF, AU, CAF)
- **Output Formats**: SRT and VTT subtitle files
- **Full Deepgram API Integration**: Access to all advanced features
- **Progress Tracking**: Visual progress indicator for long transcriptions
- **Smart File Naming**: Automatic output naming based on input file

### Advanced Deepgram Features

- **Speaker Diarization**: Identify different speakers
- **Smart Punctuation**: Automatic punctuation and capitalization
- **Profanity Filtering**: Optional content filtering
- **PII Redaction**: Remove sensitive information (SSN, PCI, etc.)
- **Summarization**: Generate content summaries
- **Topic Detection**: Identify key topics
- **Entity Detection**: Recognize named entities
- **Keyword Boosting**: Enhance recognition of specific terms
- **Search & Replace**: Find and replace terms in transcripts
- **Multi-channel Processing**: Handle stereo/multi-channel audio
- **Multiple Alternatives**: Get alternative transcription options

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure API Key**:
   - Get your Deepgram API key from [Deepgram Console](https://console.deepgram.com/)
   - Add it to the `.env` file:
   ```
   DEEPGRAM_API_KEY=your_actual_api_key_here
   ```

## Usage

### Basic Examples

```bash
# Simple transcription to SRT
python transcribe.py audio.mp3

# Transcribe to VTT format
python transcribe.py audio.wav --format vtt

# Transcribe from URL
python transcribe.py "https://example.com/audio.mp3"

# Custom output file
python transcribe.py audio.mp3 -o my_subtitles.srt
```

### Advanced Examples

```bash
# Speaker diarization with VTT output
python transcribe.py interview.mp3 --diarize --format vtt

# Full feature transcription
python transcribe.py meeting.wav \
  --diarize \
  --summarize \
  --detect-topics \
  --detect-entities \
  --punctuate \
  --smart-format

# Multi-language with specific model
python transcribe.py spanish_audio.mp3 \
  --language es \
  --model nova-2 \
  --punctuate

# Content filtering and PII redaction
python transcribe.py sensitive_audio.wav \
  --profanity-filter \
  --redact ssn \
  --redact pci

# Keyword boosting for technical content
python transcribe.py tech_talk.mp3 \
  --keywords "API" \
  --keywords "machine learning" \
  --keywords "Python"

# Search and replace terms
python transcribe.py audio.mp3 \
  --replace "um:pause" \
  --replace "uh:pause"
```

## Command Line Options

### Basic Options
- `--format`: Output format (`srt` or `vtt`, default: `srt`)
- `--output, -o`: Custom output file path
- `--language, -l`: Language code (e.g., `en`, `es`, `fr`)
- `--model, -m`: Deepgram model (`nova-2`, `enhanced`, `base`)

### Content Enhancement
- `--diarize/--no-diarize`: Enable speaker diarization
- `--punctuate/--no-punctuate`: Smart punctuation (default: enabled)
- `--smart-format/--no-smart-format`: Smart formatting (default: enabled)
- `--paragraphs/--no-paragraphs`: Paragraph detection (default: enabled)
- `--utterances/--no-utterances`: Utterance detection

### Content Analysis
- `--summarize/--no-summarize`: Generate summary
- `--detect-topics/--no-detect-topics`: Detect topics
- `--detect-entities/--no-detect-entities`: Detect named entities

### Content Filtering
- `--profanity-filter/--no-profanity-filter`: Filter profanity
- `--redact`: Redact PII types (e.g., `--redact ssn --redact pci`)

### Customization
- `--keywords`: Boost keyword recognition (repeatable)
- `--search`: Highlight search terms (repeatable)
- `--replace`: Replace terms (`"find:replace"`, repeatable)
- `--numerals/--no-numerals`: Convert numbers to numerals
- `--measurements/--no-measurements`: Convert measurements

### Technical Options
- `--multichannel/--no-multichannel`: Process channels separately
- `--alternatives`: Number of alternatives (1-10)
- `--tier`: Model tier (`nova`, `enhanced`, `base`)
- `--version`: Specific model version
- `--encoding`: Audio encoding
- `--sample-rate`: Sample rate in Hz
- `--channels`: Number of audio channels
- `--endpointing`: Endpointing sensitivity (0-500ms)
- `--vad-turnoff`: VAD turnoff time (0-2000ms)

## Supported Audio Formats

The tool supports all formats that Deepgram accepts:
- **Audio**: MP3, WAV, FLAC, AAC, M4A, OGG, OPUS, AIFF, AU, CAF, AMR
- **Video**: MP4, MOV, AVI, MKV, WebM, WMV, 3GP

## Output

The script generates:
- **Subtitle files** in SRT or VTT format
- **Progress feedback** during transcription
- **Confidence scores** and statistics
- **Summaries and topics** (when requested)

## Error Handling

The tool includes comprehensive error handling for:
- Invalid API keys
- Unsupported file formats
- Network connectivity issues
- Malformed audio files
- API rate limits

## Environment Variables

Configure in `.env`:
```
DEEPGRAM_API_KEY=your_api_key_here
DEFAULT_LANGUAGE=en
DEFAULT_MODEL=nova-2
```

## Examples Output

### SRT Format
```
1
00:00:00,000 --> 00:00:03,500
Welcome to our podcast about artificial intelligence.

2
00:00:03,500 --> 00:00:07,200
Today we'll discuss the latest developments in machine learning.
```

### VTT Format
```
WEBVTT

00:00:00.000 --> 00:00:03.500
Welcome to our podcast about artificial intelligence.

00:00:03.500 --> 00:00:07.200
Today we'll discuss the latest developments in machine learning.
```

## Troubleshooting

1. **API Key Issues**: Ensure your Deepgram API key is valid and has sufficient credits
2. **File Format**: Check that your audio file is in a supported format
3. **Network**: Verify internet connection for URL sources and API calls
4. **Dependencies**: Run `pip install -r requirements.txt` to ensure all packages are installed

## License

This tool is provided as-is for use with Deepgram's API services.
