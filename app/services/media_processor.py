import asyncio
import logging
import os
from typing import Tuple

logger = logging.getLogger("clip_srt_bot")

class MediaProcessor:
    """Handles FFmpeg operations: audio extraction and soft subtitle remuxing."""

    @staticmethod
    async def extract_audio(input_file: str, output_audio: str) -> str:
        """
        Extracts 16kHz mono MP3 audio from input media using lightweight FFmpeg settings.
        Returns the path to the extracted audio file.
        """
        cmd = [
            "ffmpeg",
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
                err_msg = stderr.decode('utf-8', errors='replace')
                logger.error(f"FFmpeg audio extraction failed: {err_msg}")
                raise RuntimeError(f"FFmpeg audio extraction error: {err_msg[:200]}")
                
            logger.info(f"Audio extracted successfully to {output_audio}")
            return output_audio
        except FileNotFoundError:
            raise RuntimeError("FFmpeg executable not found in system PATH. Please ensure ffmpeg is installed.")

    @staticmethod
    async def embed_subtitles_soft(video_path: str, srt_path: str, output_video: str) -> str:
        """
        Fast remuxing of subtitles into video as soft subtitles (mov_text) without re-encoding video stream.
        ffmpeg -i input.mp4 -i subtitle.srt -c copy -c:s mov_text output.mp4
        """
        cmd = [
            "ffmpeg",
            "-y",
            "-i", video_path,
            "-i", srt_path,
            "-c", "copy",
            "-c:s", "mov_text",
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
                err_msg = stderr.decode('utf-8', errors='replace')
                logger.error(f"FFmpeg subtitle remux failed: {err_msg}")
                raise RuntimeError(f"FFmpeg subtitle remux error: {err_msg[:200]}")
                
            logger.info(f"Subtitles embedded successfully in {output_video}")
            return output_video
        except FileNotFoundError:
            raise RuntimeError("FFmpeg executable not found in system PATH.")
