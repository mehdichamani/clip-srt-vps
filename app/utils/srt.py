import re
from typing import Any, Dict, List, Union

def seconds_to_srt_time(seconds: float) -> str:
    """Converts seconds (float) to SRT timestamp format HH:MM:SS,mmm."""
    if seconds < 0:
        seconds = 0.0
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        millis = 999
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"

def format_segments_to_srt(segments: List[Union[Dict[str, Any], Any]]) -> str:
    """
    Formats Groq Whisper verbose_json segments into a standard SRT string.
    Each segment should contain 'start', 'end', and 'text'.
    """
    srt_blocks = []
    index = 1
    
    for seg in segments:
        if isinstance(seg, dict):
            start = seg.get("start", 0.0)
            end = seg.get("end", 0.0)
            text = seg.get("text", "").strip()
        else:
            start = getattr(seg, "start", 0.0)
            end = getattr(seg, "end", 0.0)
            text = getattr(seg, "text", "").strip()
            
        if not text:
            continue
            
        start_str = seconds_to_srt_time(float(start))
        end_str = seconds_to_srt_time(float(end))
        
        block = f"{index}\n{start_str} --> {end_str}\n{text}\n"
        srt_blocks.append(block)
        index += 1
        
    return "\n".join(srt_blocks)

def clean_srt_response(raw_text: str) -> str:
    """
    Removes markdown code fences (e.g. ```srt ... ``` or ``` ...) from raw LLM output
    to return pure SRT text.
    """
    text = raw_text.strip()
    # Match markdown code fences
    pattern = r"^```(?:srt|subtitles)?\s*\n?(.*?)\n?```$"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # Strip any stray backticks at top/bottom
    text = re.sub(r"^```(?:srt)?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text).strip()
    return text
