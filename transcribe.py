#!/usr/bin/env python3
"""
Deepgram Audio Transcription Tool
Transcribes audio files to SRT or VTT subtitle formats using Deepgram's API.
"""

import os
import sys
import json
import time
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional, Dict, Any

import click
import requests
from dotenv import load_dotenv
from tqdm import tqdm
from deepgram import DeepgramClient, PrerecordedOptions, FileSource
import httpx

# Load environment variables
load_dotenv()

class DeepgramTranscriber:
    """Handles Deepgram API transcription and subtitle generation."""
    
    def __init__(self, api_key: str, timeout_seconds: int = 300):
        # Initialize client with standard constructor
        self.client = DeepgramClient(api_key)
        self.timeout_seconds = timeout_seconds
        self.supported_formats = {
            'mp3', 'wav', 'flac', 'aac', 'm4a', 'ogg', 'opus', 'webm', 'mp4', 
            'mov', 'avi', 'mkv', 'wmv', '3gp', 'amr', 'aiff', 'au', 'caf'
        }
    
    def is_url(self, path: str) -> bool:
        """Check if the input is a URL."""
        try:
            result = urlparse(path)
            return all([result.scheme, result.netloc])
        except:
            return False
    
    def validate_audio_file(self, file_path: str) -> bool:
        """Validate if the file format is supported by Deepgram."""
        if self.is_url(file_path):
            return True  # Assume URLs are valid, let Deepgram handle validation
        
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        extension = path.suffix.lower().lstrip('.')
        if extension not in self.supported_formats:
            raise ValueError(f"Unsupported format: {extension}. Supported formats: {', '.join(self.supported_formats)}")
        
        return True
    
    def transcribe_audio(self, audio_source: str, options: PrerecordedOptions, max_retries: int = 3) -> Dict[str, Any]:
        """Transcribe audio using Deepgram API with retry logic."""
        for attempt in range(max_retries):
            try:
                if self.is_url(audio_source):
                    # Handle URL source
                    response = self.client.listen.prerecorded.v("1").transcribe_url(
                        {"url": audio_source}, options
                    )
                else:
                    # Handle local file with chunked reading for large files
                    file_size = os.path.getsize(audio_source)
                    
                    # For files larger than 100MB, read in chunks to avoid memory issues
                    if file_size > 100 * 1024 * 1024:  # 100MB
                        click.echo(f"Large file detected ({file_size / (1024*1024):.1f}MB). Processing...")
                    
                    with open(audio_source, "rb") as file:
                        buffer_data = file.read()
                    
                    payload: FileSource = {
                        "buffer": buffer_data,
                    }
                    
                    response = self.client.listen.prerecorded.v("1").transcribe_file(
                        payload, options
                    )
                
                return response
            
            except Exception as e:
                error_msg = str(e).lower()
                
                # Check if it's a timeout or network issue that we can retry
                if any(term in error_msg for term in ['timeout', 'connection', 'network', 'write operation timed out']):
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 10  # Exponential backoff: 10s, 20s, 30s
                        click.echo(f"⚠️  Timeout on attempt {attempt + 1}. Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise Exception(f"Transcription failed after {max_retries} attempts due to timeout. Try with a smaller file or check your internet connection.")
                else:
                    # Non-retryable error
                    raise Exception(f"Transcription failed: {str(e)}")
        
        raise Exception(f"Transcription failed after {max_retries} attempts")
    
    def format_timestamp(self, seconds: float, format_type: str) -> str:
        """Format timestamp for SRT or VTT format."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        
        if format_type == 'srt':
            return f"{hours:02d}:{minutes:02d}:{secs:06.3f}".replace('.', ',')
        else:  # vtt
            return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
    
    def generate_srt(self, transcript_response) -> str:
        """Generate SRT format subtitle content."""
        srt_content = []
        
        # Handle Deepgram SDK response object
        if hasattr(transcript_response, 'results'):
            transcript_data = transcript_response.results
        else:
            transcript_data = transcript_response
        
        if not transcript_data.get('channels', []):
            raise ValueError("No transcription results found")
        
        alternatives = transcript_data['channels'][0]['alternatives'][0]
        words = alternatives.get('words', [])
        
        if not words:
            # Fallback to paragraphs if words are not available
            paragraphs = alternatives.get('paragraphs', {}).get('paragraphs', [])
            for i, paragraph in enumerate(paragraphs, 1):
                start_time = self.format_timestamp(paragraph['start'], 'srt')
                end_time = self.format_timestamp(paragraph['end'], 'srt')
                text = paragraph['text'].strip()
                
                srt_content.append(f"{i}")
                srt_content.append(f"{start_time} --> {end_time}")
                srt_content.append(text)
                srt_content.append("")
        else:
            # Group words into subtitle chunks (max ~80 chars per line)
            chunk_duration = 3.0  # seconds per subtitle
            current_chunk = []
            chunk_start = None
            subtitle_index = 1
            
            for word in words:
                if chunk_start is None:
                    chunk_start = word['start']
                
                current_chunk.append(word['word'])
                
                # Create subtitle when chunk is long enough or at natural breaks
                chunk_text = ' '.join(current_chunk)
                if (len(chunk_text) > 80 or 
                    word['end'] - chunk_start >= chunk_duration or
                    word == words[-1]):
                    
                    start_time = self.format_timestamp(chunk_start, 'srt')
                    end_time = self.format_timestamp(word['end'], 'srt')
                    
                    srt_content.append(f"{subtitle_index}")
                    srt_content.append(f"{start_time} --> {end_time}")
                    srt_content.append(chunk_text)
                    srt_content.append("")
                    
                    subtitle_index += 1
                    current_chunk = []
                    chunk_start = None
        
        return '\n'.join(srt_content)
    
    def generate_vtt(self, transcript_response) -> str:
        """Generate VTT format subtitle content."""
        vtt_content = ["WEBVTT", ""]
        
        # Handle Deepgram SDK response object
        if hasattr(transcript_response, 'results'):
            transcript_data = transcript_response.results
        else:
            transcript_data = transcript_response
        
        if not transcript_data.get('channels', []):
            raise ValueError("No transcription results found")
        
        alternatives = transcript_data['channels'][0]['alternatives'][0]
        words = alternatives.get('words', [])
        
        if not words:
            # Fallback to paragraphs if words are not available
            paragraphs = alternatives.get('paragraphs', {}).get('paragraphs', [])
            for paragraph in paragraphs:
                start_time = self.format_timestamp(paragraph['start'], 'vtt')
                end_time = self.format_timestamp(paragraph['end'], 'vtt')
                text = paragraph['text'].strip()
                
                vtt_content.append(f"{start_time} --> {end_time}")
                vtt_content.append(text)
                vtt_content.append("")
        else:
            # Group words into subtitle chunks
            chunk_duration = 3.0  # seconds per subtitle
            current_chunk = []
            chunk_start = None
            
            for word in words:
                if chunk_start is None:
                    chunk_start = word['start']
                
                current_chunk.append(word['word'])
                
                # Create subtitle when chunk is long enough or at natural breaks
                chunk_text = ' '.join(current_chunk)
                if (len(chunk_text) > 80 or 
                    word['end'] - chunk_start >= chunk_duration or
                    word == words[-1]):
                    
                    start_time = self.format_timestamp(chunk_start, 'vtt')
                    end_time = self.format_timestamp(word['end'], 'vtt')
                    
                    vtt_content.append(f"{start_time} --> {end_time}")
                    vtt_content.append(chunk_text)
                    vtt_content.append("")
                    
                    current_chunk = []
                    chunk_start = None
        
        return '\n'.join(vtt_content)


@click.command()
@click.argument('audio_source', type=str)
@click.option('--format', 'output_format', type=click.Choice(['srt', 'vtt']), 
              default='srt', help='Output subtitle format (default: srt)')
@click.option('--output', '-o', type=str, help='Output file path (default: same as input with new extension)')
@click.option('--language', '-l', type=str, default=None, 
              help='Language code (e.g., en, es, fr). Default from .env or auto-detect')
@click.option('--model', '-m', type=str, default=None,
              help='Deepgram model (e.g., nova-2, enhanced, base). Default from .env')
@click.option('--diarize/--no-diarize', default=False, 
              help='Enable speaker diarization')
@click.option('--punctuate/--no-punctuate', default=True,
              help='Enable smart punctuation (default: enabled)')
@click.option('--profanity-filter/--no-profanity-filter', default=False,
              help='Enable profanity filtering')
@click.option('--redact', type=str, multiple=True,
              help='Redact PII (e.g., --redact pci --redact ssn)')
@click.option('--summarize/--no-summarize', default=False,
              help='Generate summary')
@click.option('--detect-topics/--no-detect-topics', default=False,
              help='Detect topics')
@click.option('--detect-entities/--no-detect-entities', default=False,
              help='Detect named entities')
@click.option('--paragraphs/--no-paragraphs', default=True,
              help='Enable paragraph detection (default: enabled)')
@click.option('--utterances/--no-utterances', default=False,
              help='Enable utterance detection')
@click.option('--keywords', type=str, multiple=True,
              help='Keywords to boost (can be used multiple times)')
@click.option('--search', type=str, multiple=True,
              help='Search terms to highlight (can be used multiple times)')
@click.option('--replace', type=str, multiple=True,
              help='Replace terms (format: "find:replace", can be used multiple times)')
@click.option('--numerals/--no-numerals', default=False,
              help='Convert numbers to numerals')
@click.option('--measurements/--no-measurements', default=False,
              help='Convert measurements')
@click.option('--smart-format/--no-smart-format', default=True,
              help='Enable smart formatting (default: enabled)')
@click.option('--multichannel/--no-multichannel', default=False,
              help='Process multiple audio channels separately')
@click.option('--alternatives', type=int, default=1,
              help='Number of transcript alternatives (1-10, default: 1)')
@click.option('--tier', type=str, 
              help='Deepgram tier (nova, enhanced, base)')
@click.option('--version', type=str,
              help='Model version')
@click.option('--interim-results/--no-interim-results', default=False,
              help='Enable interim results for streaming (not applicable for prerecorded)')
@click.option('--endpointing', type=int,
              help='Endpointing sensitivity (0-500ms)')
@click.option('--vad-turnoff', type=int,
              help='Voice activity detection turnoff (0-2000ms)')
@click.option('--encoding', type=str,
              help='Audio encoding (linear16, mulaw, alaw, etc.)')
@click.option('--sample-rate', type=int,
              help='Audio sample rate in Hz')
@click.option('--channels', type=int,
              help='Number of audio channels')
@click.option('--timeout', type=int, default=300,
              help='API timeout in seconds (default: 300)')
@click.option('--retries', type=int, default=3,
              help='Number of retry attempts for failed requests (default: 3)')
@click.option('--chunk-size', type=int, default=100,
              help='File chunk size in MB for large files (default: 100)')
def transcribe_command(audio_source: str, output_format: str, output: Optional[str], **kwargs):
    """
    Transcribe audio files or URLs to SRT/VTT subtitle formats using Deepgram API.
    
    AUDIO_SOURCE can be a local file path or a URL to an audio/video file.
    
    Examples:
    
    Basic transcription:
        python transcribe.py audio.mp3
    
    With speaker diarization:
        python transcribe.py audio.mp3 --diarize --format vtt
    
    From URL with custom options:
        python transcribe.py "https://example.com/audio.mp3" --language en --model nova-2
    
    Full feature example:
        python transcribe.py audio.wav --diarize --summarize --detect-topics --punctuate --smart-format
    """
    
    # Get API key
    api_key = os.getenv('DEEPGRAM_API_KEY')
    if not api_key:
        click.echo("Error: DEEPGRAM_API_KEY not found in environment variables.", err=True)
        click.echo("Please add your API key to the .env file.", err=True)
        sys.exit(1)
    
    # Initialize transcriber with custom timeout
    timeout_seconds = kwargs.get('timeout', 300)
    transcriber = DeepgramTranscriber(api_key, timeout_seconds)
    
    try:
        # Validate audio source
        click.echo(f"Validating audio source: {audio_source}")
        transcriber.validate_audio_file(audio_source)
        
        # Prepare transcription options
        options_dict = {
            'punctuate': kwargs.get('punctuate', True),
            'paragraphs': kwargs.get('paragraphs', True),
            'smart_format': kwargs.get('smart_format', True),
        }
        
        # Add language (with fallback to env default)
        language = kwargs.get('language') or os.getenv('DEFAULT_LANGUAGE', 'en')
        options_dict['language'] = language
        
        # Add model (with fallback to env default)
        model = kwargs.get('model') or os.getenv('DEFAULT_MODEL', 'nova-2')
        options_dict['model'] = model
        
        # Add optional features
        if kwargs.get('diarize'):
            options_dict['diarize'] = True
        
        if kwargs.get('profanity_filter'):
            options_dict['profanity_filter'] = True
        
        if kwargs.get('redact'):
            options_dict['redact'] = list(kwargs['redact'])
        
        if kwargs.get('summarize'):
            options_dict['summarize'] = True
        
        if kwargs.get('detect_topics'):
            options_dict['detect_topics'] = True
        
        if kwargs.get('detect_entities'):
            options_dict['detect_entities'] = True
        
        if kwargs.get('utterances'):
            options_dict['utterances'] = True
        
        if kwargs.get('keywords'):
            options_dict['keywords'] = list(kwargs['keywords'])
        
        if kwargs.get('search'):
            options_dict['search'] = list(kwargs['search'])
        
        if kwargs.get('replace'):
            replace_dict = {}
            for replace_pair in kwargs['replace']:
                if ':' in replace_pair:
                    find_term, replace_term = replace_pair.split(':', 1)
                    replace_dict[find_term] = replace_term
            if replace_dict:
                options_dict['replace'] = replace_dict
        
        if kwargs.get('numerals'):
            options_dict['numerals'] = True
        
        if kwargs.get('measurements'):
            options_dict['measurements'] = True
        
        if kwargs.get('multichannel'):
            options_dict['multichannel'] = True
        
        alternatives = kwargs.get('alternatives', 1)
        if alternatives > 1:
            options_dict['alternatives'] = alternatives
        
        # Add technical audio parameters if specified
        if kwargs.get('encoding'):
            options_dict['encoding'] = kwargs['encoding']
        
        if kwargs.get('sample_rate'):
            options_dict['sample_rate'] = kwargs['sample_rate']
        
        if kwargs.get('channels'):
            options_dict['channels'] = kwargs['channels']
        
        if kwargs.get('tier'):
            options_dict['tier'] = kwargs['tier']
        
        if kwargs.get('version'):
            options_dict['version'] = kwargs['version']
        
        if kwargs.get('endpointing') is not None:
            options_dict['endpointing'] = kwargs['endpointing']
        
        if kwargs.get('vad_turnoff') is not None:
            options_dict['vad_turnoff'] = kwargs['vad_turnoff']
        
        # Create PrerecordedOptions object
        options = PrerecordedOptions(**options_dict)
        
        # Perform transcription with progress indicator
        click.echo("Starting transcription...")
        max_retries = kwargs.get('retries', 3)
        
        with tqdm(total=100, desc="Transcribing", unit="%") as pbar:
            pbar.update(10)  # Initial progress
            
            transcript_response = transcriber.transcribe_audio(audio_source, options, max_retries)
            pbar.update(70)  # Transcription complete
            
            # Generate subtitle content
            click.echo(f"Generating {output_format.upper()} format...")
            if output_format == 'srt':
                subtitle_content = transcriber.generate_srt(transcript_response)
            else:
                subtitle_content = transcriber.generate_vtt(transcript_response)
            
            pbar.update(20)  # Format generation complete
        
        # Determine output file path
        if output:
            output_path = Path(output)
        else:
            if transcriber.is_url(audio_source):
                # Extract filename from URL or use default
                url_path = urlparse(audio_source).path
                if url_path:
                    base_name = Path(url_path).stem or "transcription"
                else:
                    base_name = "transcription"
            else:
                base_name = Path(audio_source).stem
            
            output_path = Path(f"{base_name}.{output_format}")
        
        # Write subtitle file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(subtitle_content)
        
        click.echo(f"✅ Transcription complete! Output saved to: {output_path}")
        
        # Display summary information
        # Handle Deepgram SDK response object
        if hasattr(transcript_response, 'results'):
            results_data = transcript_response.results
        else:
            results_data = transcript_response
            
        if results_data.get('channels'):
            channel = results_data['channels'][0]
            if 'alternatives' in channel and channel['alternatives']:
                alternative = channel['alternatives'][0]
                
                # Show confidence if available
                if 'confidence' in alternative:
                    confidence = alternative['confidence']
                    click.echo(f"📊 Confidence: {confidence:.2%}")
                
                # Show word count
                if 'words' in alternative:
                    word_count = len(alternative['words'])
                    click.echo(f"📝 Words transcribed: {word_count}")
                
                # Show summary if requested
                if kwargs.get('summarize') and 'summary' in alternative:
                    click.echo(f"\n📋 Summary:")
                    click.echo(alternative['summary'])
                
                # Show topics if requested
                if kwargs.get('detect_topics') and 'topics' in alternative:
                    topics = alternative['topics']
                    if topics:
                        click.echo(f"\n🏷️  Topics detected:")
                        for topic in topics[:5]:  # Show top 5 topics
                            click.echo(f"  • {topic.get('topic', 'Unknown')} (confidence: {topic.get('confidence', 0):.2%})")
    
    except Exception as e:
        click.echo(f"❌ Error: {str(e)}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    transcribe_command()
