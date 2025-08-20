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
import re

import click
import requests
from dotenv import load_dotenv
from tqdm import tqdm
from deepgram import DeepgramClient, PrerecordedOptions, FileSource
import httpx
import yt_dlp

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
    
    def is_youtube_url(self, url: str) -> bool:
        """Check if the URL is a YouTube URL."""
        youtube_patterns = [
            r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=[\w-]+',
            r'(?:https?://)?(?:www\.)?youtu\.be/[\w-]+',
            r'(?:https?://)?(?:www\.)?youtube\.com/embed/[\w-]+',
            r'(?:https?://)?(?:www\.)?youtube\.com/v/[\w-]+',
            r'(?:https?://)?(?:www\.)?youtube\.com/playlist\?list=[\w-]+',
            r'(?:https?://)?(?:www\.)?youtube\.com/channel/[\w-]+',
            r'(?:https?://)?(?:www\.)?youtube\.com/c/[\w-]+',
            r'(?:https?://)?(?:www\.)?youtube\.com/@[\w-]+',
        ]
        return any(re.match(pattern, url, re.IGNORECASE) for pattern in youtube_patterns)
    
    def sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for cross-platform compatibility."""
        # Remove or replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        # Remove leading/trailing spaces and dots
        filename = filename.strip('. ')
        
        # Limit length
        if len(filename) > 200:
            filename = filename[:200]
        
        # Ensure it's not empty
        if not filename:
            filename = "youtube_audio"
        
        return filename
    
    def extract_youtube_audio_url(self, youtube_url: str, keep_audio: bool = False) -> tuple[str, str]:
        """Extract direct audio stream URL from YouTube using yt-dlp."""
        import tempfile
        import os
        
        # Choose output directory based on keep_audio flag
        if keep_audio:
            output_dir = os.getcwd()  # Current directory
        else:
            output_dir = tempfile.mkdtemp()  # Temporary directory
        
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio[ext=mp4]/bestaudio',
            'quiet': True,
            'no_warnings': True,
            'extractaudio': True,
            'audioformat': 'm4a',
            'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'm4a',
                'preferredquality': '192',
            }],
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                # Download the audio
                info = ydl.extract_info(youtube_url, download=True)
                title = info.get('title', 'YouTube Video')
                
                # Find the downloaded file
                downloaded_file = None
                for file in os.listdir(output_dir):
                    if file.endswith(('.m4a', '.mp4', '.webm', '.opus')):
                        downloaded_file = os.path.join(output_dir, file)
                        break
                
                if not downloaded_file:
                    raise ValueError("No audio file was downloaded")
                
                return downloaded_file, title
                
            except Exception as e:
                # Clean up temp directory on error only if not keeping audio
                if not keep_audio:
                    import shutil
                    shutil.rmtree(output_dir, ignore_errors=True)
                raise ValueError(f"Failed to extract YouTube audio: {str(e)}")
    
    def validate_audio_file(self, file_path: str) -> bool:
        """Validate if the file format is supported by Deepgram."""
        if self.is_url(file_path):
            return True  # URLs (including YouTube) are valid, let Deepgram handle validation
        
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        extension = path.suffix.lower().lstrip('.')
        if extension not in self.supported_formats:
            raise ValueError(f"Unsupported format: {extension}. Supported formats: {', '.join(self.supported_formats)}")
        
        return True
    
    def transcribe_audio(self, audio_source: str, output_format: str = 'srt', 
                        enable_diarization: bool = False, text_replacements: dict = None, 
                        keep_audio: bool = False) -> str:
        """Transcribe audio from file or URL using Deepgram API."""
        
        temp_file_to_cleanup = None
        
        try:
            # Handle YouTube URLs
            if self.is_youtube_url(audio_source):
                click.echo("🎥 Extracting audio from YouTube video...")
                audio_file_path, video_title = self.extract_youtube_audio_url(audio_source, keep_audio)
                click.echo(f"📹 Video: {video_title}")
                click.echo(f"🎵 Downloaded audio file: {Path(audio_file_path).name}")
                if keep_audio:
                    click.echo(f"💾 Audio file saved to: {audio_file_path}")
                audio_source = audio_file_path
                if not keep_audio:
                    temp_file_to_cleanup = audio_file_path
                output_filename = self.sanitize_filename(video_title)
            else:
                # For local files, use the filename without extension
                output_filename = Path(audio_source).stem if not self.is_url(audio_source) else "transcription"
            
            # Validate audio source
            if not self.validate_audio_file(audio_source):
                raise ValueError(f"Unsupported audio format: {audio_source}")
            
            # Prepare transcription options
            options = PrerecordedOptions(
                model="nova-2",
                smart_format=True,
                punctuate=True,
                diarize=enable_diarization,
                language="en-US"
            )
            
            # Create progress bar
            with tqdm(total=100, desc="Transcribing", unit="%") as pbar:
                pbar.update(10)
                
                # Transcribe audio
                if self.is_url(audio_source) and not temp_file_to_cleanup:
                    response = self.client.listen.prerecorded.v("1").transcribe_url(
                        {"url": audio_source}, options
                    )
                else:
                    with open(audio_source, "rb") as audio_file:
                        buffer_data = audio_file.read()
                        response = self.client.listen.prerecorded.v("1").transcribe_file(
                            {"buffer": buffer_data}, options
                        )
                
                pbar.update(90)
                
                # Extract transcript
                transcript = response["results"]["channels"][0]["alternatives"][0]["transcript"]
                if not transcript.strip():
                    raise ValueError("No speech detected in the audio")
                
                # Apply text replacements if provided
                if text_replacements:
                    for old_text, new_text in text_replacements.items():
                        transcript = transcript.replace(old_text, new_text)
                
                # Generate output based on format
                if output_format.lower() == 'srt':
                    output_content = self.generate_srt(response, enable_diarization)
                    output_file = f"{output_filename}.srt"
                elif output_format.lower() == 'vtt':
                    output_content = self.generate_vtt(response, enable_diarization)
                    output_file = f"{output_filename}.vtt"
                else:
                    raise ValueError(f"Unsupported output format: {output_format}")
                
                # Write output file
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(output_content)
                
                pbar.update(100)
                
                return output_file
                
        except Exception as e:
            raise ValueError(f"Transcription failed: {str(e)}")
        
        finally:
            # Clean up temporary file if it was created
            if temp_file_to_cleanup:
                try:
                    import shutil
                    temp_dir = Path(temp_file_to_cleanup).parent
                    shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception:
                    pass  # Ignore cleanup errors
    
    def format_timestamp(self, seconds: float, format_type: str) -> str:
        """Format timestamp for SRT or VTT format."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        
        if format_type == 'srt':
            return f"{hours:02d}:{minutes:02d}:{secs:06.3f}".replace('.', ',')
        else:  # vtt
            return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
    
    def generate_srt(self, transcript_response, enable_diarization: bool = False) -> str:
        """Generate SRT format subtitle content."""
        srt_content = []
        
        # Convert response to dict for consistent handling
        try:
            if hasattr(transcript_response, 'to_dict'):
                transcript_data = transcript_response.to_dict()
            elif hasattr(transcript_response, 'results'):
                # Handle nested object structure
                results = transcript_response.results
                if hasattr(results, 'to_dict'):
                    transcript_data = {'results': results.to_dict()}
                else:
                    # Manual conversion for object attributes
                    channels_data = []
                    for channel in results.channels:
                        alternatives_data = []
                        for alt in channel.alternatives:
                            alt_dict = {
                                'transcript': alt.transcript if hasattr(alt, 'transcript') else '',
                                'confidence': alt.confidence if hasattr(alt, 'confidence') else 0,
                                'words': []
                            }
                            if hasattr(alt, 'words'):
                                for word in alt.words:
                                    alt_dict['words'].append({
                                        'word': word.word,
                                        'start': word.start,
                                        'end': word.end,
                                        'confidence': word.confidence if hasattr(word, 'confidence') else 0
                                    })
                            alternatives_data.append(alt_dict)
                        channels_data.append({'alternatives': alternatives_data})
                    transcript_data = {'results': {'channels': channels_data}}
            else:
                transcript_data = transcript_response
            
            if not transcript_data.get('results', {}).get('channels', []):
                raise ValueError("No transcription results found")
            
            alternatives = transcript_data['results']['channels'][0]['alternatives'][0]
            words = alternatives.get('words', [])
        except Exception as e:
            raise ValueError(f"Error processing transcript response: {str(e)}")
        
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
    
    def generate_vtt(self, transcript_response, enable_diarization: bool = False) -> str:
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
@click.option('--chunk-size', default=100, help='File chunk size in MB for large files (default: 100)')
@click.option('--keep-audio', is_flag=True, help='Keep downloaded YouTube audio file instead of deleting it')
@click.option('--help', is_flag=True, expose_value=False, is_eager=True, help='Show this message and exit.')
def transcribe_command(audio_source, **kwargs):
    """
    Transcribe audio files, URLs, or YouTube videos to SRT/VTT subtitle formats using Deepgram API.
    
    AUDIO_SOURCE can be:
    - Local file path (audio.mp3, video.mp4, etc.)
    - Direct URL to audio/video file
    - YouTube URL (https://youtube.com/watch?v=..., https://youtu.be/...)
    
    Examples:
    
    Basic transcription:
        python transcribe.py audio.mp3
    
    YouTube video transcription:
        python transcribe.py "https://youtube.com/watch?v=dQw4w9WgXcQ" --diarize
    
    With speaker diarization:
        python transcribe.py audio.mp3 --diarize --format vtt
    
    From URL with custom options:
        python transcribe.py "https://example.com/audio.mp3" --language en --model nova-2
    
    Full feature YouTube example:
        python transcribe.py "https://youtu.be/dQw4w9WgXcQ" --diarize --summarize --detect-topics --punctuate --smart-format
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
            
            # Prepare text replacements
            text_replacements = {}
            if kwargs.get('replace'):
                for replacement in kwargs['replace']:
                    if ':' in replacement:
                        old_text, new_text = replacement.split(':', 1)
                        text_replacements[old_text] = new_text
            
            # Call transcribe_audio with correct parameters
            output_file = transcriber.transcribe_audio(
                audio_source,
                output_format=kwargs.get('format', 'srt'),
                enable_diarization=kwargs.get('diarize', False),
                text_replacements=text_replacements if text_replacements else None,
                keep_audio=kwargs.get('keep_audio', False)
            )
            pbar.update(10)  # Complete
        
        # Success message
        click.echo(f"✅ Transcription completed successfully!")
        click.echo(f"📄 Output file: {output_file}")
        
        return output_file
    
    except Exception as e:
        click.echo(f"❌ Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    transcribe_command()
