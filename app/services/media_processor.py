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

    @staticmethod
    async def embed_lyrics_mp3(
        audio_path: str,
        lrc_content: str,
        output_mp3_path: str,
        title: str = "",
        artist: str = "",
        cover_path: Optional[str] = None
    ) -> str:
        """
        Creates an MP3 file with embedded synchronized lyrics (LRC) and metadata
        specifically formatted for media players like Musicolet.
        Tags written:
        - USLT (Unsynchronized lyrics frame containing timestamped [mm:ss.xx] lines for Musicolet)
        - TXXX:LYRICS (Custom tag with full LRC content for extended player compatibility)
        - TIT2 (Title)
        - TPE1 (Artist/Channel)
        - APIC (Attached picture/cover art if available)
        """
        import shutil
        import mutagen
        from mutagen.id3 import ID3, USLT, TIT2, TPE1, APIC, TXXX, ID3NoHeaderError

        # Copy original audio to target path if different
        if audio_path != output_mp3_path:
            shutil.copyfile(audio_path, output_mp3_path)

        def _tag_sync():
            try:
                tags = ID3(output_mp3_path)
            except ID3NoHeaderError:
                tags = ID3()

            # Set Song Title & Artist
            if title:
                tags["TIT2"] = TIT2(encoding=3, text=title)
            if artist:
                tags["TPE1"] = TPE1(encoding=3, text=artist)

            # Set USLT (Musicolet standard for reading timestamped lyrics in MP3)
            # encoding=3 means UTF-8, lang='eng' or 'fas', desc=''
            tags["USLT::eng"] = USLT(encoding=3, lang="eng", desc="", text=lrc_content)
            tags["USLT::fas"] = USLT(encoding=3, lang="fas", desc="", text=lrc_content)

            # Also set TXXX:LYRICS for additional player compatibility
            tags["TXXX:LYRICS"] = TXXX(encoding=3, desc="LYRICS", text=lrc_content)

            # Attach Cover Image if exists
            if cover_path and os.path.exists(cover_path):
                try:
                    with open(cover_path, "rb") as alb:
                        cover_data = alb.read()
                    tags["APIC"] = APIC(
                        encoding=3,
                        mime="image/jpeg" if cover_path.lower().endswith((".jpg", ".jpeg")) else "image/png",
                        type=3,  # Front cover
                        desc="Cover",
                        data=cover_data
                    )
                except Exception as img_err:
                    logger.warning(f"Could not attach cover image to MP3: {img_err}")

            tags.save(output_mp3_path, v2_version=3)
            logger.info(f"Embedded synced LRC lyrics into MP3: {output_mp3_path}")

        await asyncio.to_thread(_tag_sync)
        return output_mp3_path




