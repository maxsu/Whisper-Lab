from pathlib import Path

import logging

import numpy as np
import pydub
import whisper.audio
import sounddevice

from whisperlab.time import time_ms


log = logging.getLogger("main")

# Constants ===================================================================


SAMPLES_PER_SECOND = 16_000  # Use whisper's 16 kHz framerate


# Exceptions ==================================================================


class EmptyFile(Exception):
    """
    Raised when an audio file is empty
    """


class AudioOverflow(Exception):
    """
    Raised when an audio array contains samples outside [-1, 1]
    """


class EmptyArray(Exception):
    """
    Raised when an audio array is empty
    """


class ArrayTypeError(Exception):
    """
    Raised when an audio array is not the correct type
    """


# Validation ==================================================================


# Verify that the Whisper frame rate has not changed
assert (
    SAMPLES_PER_SECOND == whisper.audio.SAMPLE_RATE
), f"Whisper frame rate has changed to {SAMPLES_PER_SECOND}."


def ValidateAudioFile(audio_file: Path):
    """
    Validate that the audio file is not empty

    Args:
        audio_file (Path): Path to the audio file to validate

    Raises:
        EmptyFile: If the audio file is empty
    """

    # Verify that the audio file is not empty
    if audio_file.stat().st_size == 0:
        raise EmptyFile(f"Audio file is empty: {audio_file}")


def ValidateAudioArray(audio: np.ndarray, dtype=np.float32):
    """
    Validate that the audio array:
    - is not empty
    - is the correct type
    - does not contain samples outside [-1, 1]

    Args:
        audio (np.ndarray): The audio array to validate

    Raises:
        EmptyArray: If the audio array is empty
        ArrayTypeError: If the audio array is not the correct type
    """

    # Verify that the audio array is not empty
    if len(audio) == 0:
        raise EmptyArray(f"Audio array is empty: {audio}")

    # Verify that the audio array is the correct type
    if audio.dtype != dtype:
        raise ArrayTypeError(f"Audio array is not {dtype}: {audio}")

    if np.any(np.abs(audio) > 1):
        raise AudioOverflow("Audio overflow")


# Converters ==================================================================


def float32_to_int16(audio: np.ndarray):
    """
    Convert a float32 array to int16

    Maps the float32 range [-1, 1] to the int16 range [-32768, 32767]

    Args:
        audio (np.ndarray): The audio array to convert

    Returns:
        np.ndarray: The converted audio array

    Raises:
        Exception: If the audio array contains samples outside [-1, 1]
    """
    ValidateAudioArray(audio)

    new_audio = (audio * 32_768).astype(np.int16)
    return new_audio


# Operators ===================================================================


def roll(buffer: np.ndarray, samples: np.ndarray):
    """
    Roll new samples into a numpy array.

    If the samples are longer than the buffer, use use the last samples.

    Example:
        >>> roll(np.zeros(3), np.array([1, 2, 3, 4]))
        array([2., 3., 4.])

        >>> roll(np.zeros(3), np.array([1, 2]))
        array([0., 1., 2.])

        >>> roll(np.array([1, 2, 3]), np.array([4, 5]))
        array([3., 4., 5.])

    Args:
        buffer (np.ndarray): The buffer to roll the samples into
        samples (np.ndarray): The samples to roll into the buffer

    Returns:
        np.ndarray: The updated buffer
    """

    if len(samples) > len(buffer):
        return samples[-len(buffer) :]
    left_shift = -len(samples)
    buffer = np.roll(buffer, left_shift)
    buffer[left_shift:] = samples
    return buffer


# Buffers =====================================================================


class WaveBuffer:
    """
    A model of the plot signal buffer.

    The buffer is a numpy array of audio samples.

    The buffer is updated by calling put() with a new audio array.

    The buffer is read by calling get().

    Child classes may override process() to modify the audio samples before
    they are added to the buffer.
    """

    buffer: np.ndarray

    def __init__(self, buffer_size: int):
        self.buffer = np.zeros(buffer_size)

    def get(self):
        return self.buffer

    def put(self, audio_samples):
        """Convert the audio samples to a plot buffer."""
        self.buffer = self.process(audio_samples)

    def process(self, audio_samples):
        return audio_samples


# Microphone ==================================================================


class Microphone:
    def __init__(self, window_length: int = 5):
        self.window_length = window_length
        self.window_samples = SAMPLES_PER_SECOND * window_length
        self.stream = sounddevice.InputStream(
            channels=1,
            blocksize=self.window_samples,
            samplerate=SAMPLES_PER_SECOND,
        )
        self.stream.start()

    def get(self):
        time = time_ms()
        samples, overflowed = self.stream.read(self.window_samples)
        if overflowed:
            raise Exception("Unexpected overflow")

        samples = samples[:, 0]  # unpack channel 1
        log.debug(
            "Fetched %s samples in %s ms",
            len(samples),
            time_ms() - time,
        )
        return samples


class VirtualMicrophone:
    def __init__(self, audio_file):
        self.audio_file = audio_file
        samples = load_audio_file(audio_file)
        segments = len(samples) // SAMPLES_PER_WINDOW
        self.samples = samples[: segments * SAMPLES_PER_WINDOW].reshape(
            segments, SAMPLES_PER_WINDOW
        )
        self.index = 0

    def get(self):
        if self.index >= self.segments:
            raise Exception("Unexpected end of samples")
        samples = self.samples[self.index]
        self.index += 1


# Loaders =====================================================================


def load_audio_file(audio_file: Path):
    """
    Load an audio file into a numpy array

    Args:
        audio_file (Path): The path to the audio file to load

    Returns:
        np.ndarray: The audio array
    """

    # Validate the audio file
    ValidateAudioFile(audio_file)

    # Load the audio file
    audio = whisper.audio.load_audio(audio_file)

    return audio


# Exporters ===================================================================


def save_audio_segment(audio: np.ndarray, text, base_path: Path):
    """
    Save an audio array to a file

    Args:
        audio (np.ndarray): The audio array to save
        path (Path): The path to save the audio to
    """

    # Create the parent directory if it does not exist
    base_path.parent.mkdir(parents=True, exist_ok=True)

    # Create the path to save the audio and text to
    text_path = base_path.with_suffix(".txt")
    audio_path = base_path.with_suffix(".wav")

    # Export the audio array to a WAV file
    pydub.AudioSegment(
        float32_to_int16(audio).tobytes(),
        frame_rate=SAMPLES_PER_SECOND,
        sample_width=2,
        channels=1,
    ).export(audio_path, format="wav")

    # Export the text to a text file
    text_path.write_text(text)
