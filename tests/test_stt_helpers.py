"""Tests for STT helpers — PCM→WAV conversion."""
import struct
import sys
sys.path.insert(0, ".")

# conftest.py stubs all HA modules before this runs

from custom_components.venice_ai.stt import _pcm_to_wav


# ── _pcm_to_wav ───────────────────────────────────────────────────────────────

def _parse_wav_header(wav: bytes) -> dict:
    """Parse the 44-byte WAV header and return field values."""
    chunk_id, chunk_size, fmt, sub1_id, sub1_size, audio_fmt, \
    num_ch, sample_rate, byte_rate, block_align, bps, \
    sub2_id, sub2_size = struct.unpack_from("<4sL4s4sLHHLLHH4sL", wav, 0)
    return {
        "chunk_id": chunk_id,
        "fmt": fmt,
        "sub1_id": sub1_id,
        "audio_fmt": audio_fmt,
        "num_channels": num_ch,
        "sample_rate": sample_rate,
        "byte_rate": byte_rate,
        "block_align": block_align,
        "bits_per_sample": bps,
        "sub2_id": sub2_id,
        "data_size": sub2_size,
    }


def test_pcm_to_wav_header_magic_bytes():
    pcm = b"\x00\x01" * 100
    wav = _pcm_to_wav(pcm)
    hdr = _parse_wav_header(wav)
    assert hdr["chunk_id"] == b"RIFF"
    assert hdr["fmt"] == b"WAVE"
    assert hdr["sub1_id"] == b"fmt "
    assert hdr["sub2_id"] == b"data"

def test_pcm_to_wav_audio_format_is_pcm():
    wav = _pcm_to_wav(b"\x00" * 32)
    hdr = _parse_wav_header(wav)
    assert hdr["audio_fmt"] == 1  # PCM = 1

def test_pcm_to_wav_data_size_matches_input():
    pcm = b"\xAB\xCD" * 50
    wav = _pcm_to_wav(pcm)
    hdr = _parse_wav_header(wav)
    assert hdr["data_size"] == len(pcm)

def test_pcm_to_wav_total_length():
    pcm = b"\x00" * 200
    wav = _pcm_to_wav(pcm)
    assert len(wav) == 44 + len(pcm)

def test_pcm_to_wav_default_params():
    pcm = b"\x00" * 64
    wav = _pcm_to_wav(pcm)
    hdr = _parse_wav_header(wav)
    assert hdr["sample_rate"] == 16000
    assert hdr["num_channels"] == 1
    assert hdr["bits_per_sample"] == 16

def test_pcm_to_wav_byte_rate_formula():
    # byte_rate = sample_rate * num_channels * bits_per_sample / 8
    pcm = b"\x00" * 64
    wav = _pcm_to_wav(pcm, sample_rate=16000, num_channels=1, bits_per_sample=16)
    hdr = _parse_wav_header(wav)
    assert hdr["byte_rate"] == 16000 * 1 * 16 // 8

def test_pcm_to_wav_block_align_formula():
    pcm = b"\x00" * 64
    wav = _pcm_to_wav(pcm, num_channels=1, bits_per_sample=16)
    hdr = _parse_wav_header(wav)
    assert hdr["block_align"] == 1 * 16 // 8

def test_pcm_to_wav_empty_input():
    wav = _pcm_to_wav(b"")
    assert len(wav) == 44
    hdr = _parse_wav_header(wav)
    assert hdr["data_size"] == 0

def test_pcm_to_wav_data_appended_correctly():
    pcm = bytes(range(16))
    wav = _pcm_to_wav(pcm)
    assert wav[44:] == pcm
