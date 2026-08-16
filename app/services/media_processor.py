import asyncio
import logging
import os
from typing import Optional, Tuple

logger = logging.getLogger("clip_srt_bot")

class NoAudioTrackError(RuntimeError):
    """Raised when an input media file contains no audio stream."""
    pass

class MediaProcessor:
    """Handles FFmpeg operations: audio stream check, audio extraction and soft subtitle remuxing."""

    @staticmethod
    async def has_audio_stream(input_file: str) -> bool:
        """
        Checks if the media file contains at least one audio stream using ffprobe.
        """
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=codec_type",
            "-of", "default=noprint_wrappers=1:nokey=1",
            input_file
        ]
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                output = stdout.decode('utf-8', errors='replace').strip()
                return "audio" in output
            return True  # Fallback to True if ffprobe returns error, letting ffmpeg attempt extraction
        except Exception as e:
            logger.warning(f"FFprobe check failed for {input_file}: {e}")
            return True

    @staticmethod
    async def extract_audio(input_file: str, output_audio: str) -> str:
        """
        Extracts 16kHz mono MP3 audio from input media using lightweight FFmpeg settings.
        Returns the path to the extracted audio file.
        """
        if not await MediaProcessor.has_audio_stream(input_file):
            logger.warning(f"No audio stream found in {input_file}")
            raise NoAudioTrackError("فایل ارسالی فاقد ترک صوتی است و صدایی برای پردازش ندارد.")

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-i", input_file,
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            "-c:a", "libmp3lame",
            "-q:a", "4",
            output_audio
        ]
        
        logger.info(f"Extracting audio: {' '.join(cmd)}")
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                err_msg = stderr.decode('utf-8', errors='replace').strip()
                if "does not contain any stream" in err_msg.lower() or "matches no streams" in err_msg.lower():
                    raise NoAudioTrackError("فایل ارسالی فاقد ترک صوتی است.")
                logger.error(f"FFmpeg audio extraction failed: {err_msg}")
                err_lines = [line.strip() for line in err_msg.splitlines() if line.strip()]
                summary_err = " | ".join(err_lines[-3:]) if err_lines else err_msg[:200]
                raise RuntimeError(f"FFmpeg audio extraction error: {summary_err}")
                
            logger.info(f"Audio extracted successfully to {output_audio}")
            return output_audio
        except FileNotFoundError:
            raise RuntimeError("FFmpeg executable not found in system PATH. Please ensure ffmpeg is installed.")

    @staticmethod
    async def embed_subtitles_soft(video_path: str, srt_path: str, output_video: str) -> str:
        """
        Fast remuxing of subtitles into video as soft subtitles (subrip) into MKV container without re-encoding video stream.
        Includes default track disposition (-disposition:s:0 default) and language metadata (-metadata:s:s:0 language=fas)
        so media players and Telegram automatically select and render the subtitle track.
        """
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-i", video_path,
            "-i", srt_path,
            "-c", "copy",
            "-c:s", "subrip",
            "-disposition:s:0", "default",
            "-metadata:s:s:0", "language=fas",
            output_video
        ]
        
        logger.info(f"Embedding soft subtitles: {' '.join(cmd)}")
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                err_msg = stderr.decode('utf-8', errors='replace').strip()
                logger.error(f"FFmpeg subtitle remux failed: {err_msg}")
                err_lines = [line.strip() for line in err_msg.splitlines() if line.strip()]
                summary_err = " | ".join(err_lines[-3:]) if err_lines else err_msg[:200]
                raise RuntimeError(f"FFmpeg subtitle remux error: {summary_err}")
                
            logger.info(f"Subtitles embedded successfully in {output_video}")
            return output_video
        except FileNotFoundError:
            raise RuntimeError("FFmpeg executable not found in system PATH.")



