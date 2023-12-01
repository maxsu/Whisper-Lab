"""
Whisper Runner Module

This module can transcribe an audio file using Whisper.
"""

import logging as log

from pydantic import BaseModel, FilePath
import whisper


# Config


class WhisperModels:
    BASE = "base"


DEFAULT_WHISPER_MODEL = WhisperModels.BASE


# Request Model


class WhisperRequest(BaseModel):
    """
    Whisper Request Model

    Args:
        audio_file (Path): Path to the audio file to transcribe
        args (dict): Arguments to pass to whisper

    Returns:
        dict: The whisper result
    """

    audio_file: FilePath
    args: dict = {}
    model: str = DEFAULT_WHISPER_MODEL


# Use Case


def run_whisper(
    request: WhisperRequest,
):
    """
    Run whisper on an audio file

    Args:
        request (WhisperRequest): The whisper request to process

    Effects:
        Logs the whisper result

    Returns:
        dict: The whisper result
    """

    audio_file = str(request.audio_file)

    # Load the audio file
    audio = whisper.load_audio(audio_file)

    # Trim the audio to 30 seconds
    audio = whisper.pad_or_trim(audio)

    # Log the audio file
    log.info("Transcribing %s", request.audio_file)

    # Fetch the model
    model = whisper.load_model(request.model)

    # Transcribe the audio
    response = model.transcribe(audio, **request.args)

    # Log the result text
    log.info("Transcription:\n%s", response["text"])

    return response
