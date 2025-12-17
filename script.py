"""
09.23.205 - Observe AI missing transcript issues

This script can determine if there are large chunks of missing words in a transcript.
It will return True if there are missing chunks and will print out the timestamp in the audio file where it happens. 

You may adjust the variables for COVERAGE_THRESHOLD, MIN_VAD_DURATION, and SIGNIFICANCE_FACTOR
  - A value of 0.6 for COVERAGE_THRESHOLD means 60% of the duration of a speech event has word timestamps present.
    - If 60% or more of the duration has word timestamps present, it returns False, indicating no missing transcript was detected.
    - In Deepgram internal testing, the 60% threshold was sufficient for capturing these errors.
  - A value of 2.0 for MIN_VAD_DURATION means that speech events shorter than 2 seconds are ignored.
  - A value of 5.0 for SIGNIFICANCE_FACTOR means that the missing portion of a transcript must be longer than 5 seconds to return True.
    - If there is portion of transcript missing that's less than 5 seconds, it might not be a true error/bug but rather just a few missed words.
  
  Before executing the script:
  - Insert your API key on line 45
  - Replace the path to your file with the correct path on line 24

"""

import requests
from silero_vad import load_silero_vad, read_audio, get_speech_timestamps 

PATH_TO_FILE = 'YOUR_PATH_TO_FILE.wav' # Or .mp3 etc

COVERAGE_THRESHOLD = 0.6 # The percentage of the utterance (from Silero) that has words associated (from Deepgram)
MIN_VAD_DURATION = 2.0 # Ignore utterances that are less than 2 seconds.
SIGNIFICANCE_FACTOR = 5.0 # Ignore missing transcripts less than 5 seconds long.

def silero_vad(PATH_TO_FILE):
    model = load_silero_vad()
    wav = read_audio(PATH_TO_FILE)
    speech_timestamps = get_speech_timestamps(
    wav,
    model,
    return_seconds=True,
    min_silence_duration_ms=1000
    )
    return speech_timestamps


def deepgram_words(call):
    URL = "https://api.deepgram.com/v1/listen?multichannel=true&phoneme_lattice=true&model=nova-2-phonecall&language=en&keywords=agree%3A1.5&keywords=yes%3A1.5&keywords=no%3A1.5&keywords=anytime%3A0.8&keywords=afternoon%3A0.8&keywords=bachelors%3A0.8&keywords=college%3A0.8&keywords=degree%3A0.5&keywords=degreesearch%3A1.2&keywords=diploma%3A1.2&keywords=education%3A1.1&keywords=evening%3A0.8&keywords=ged%3A1.5&keywords=immediately%3A0.8&keywords=morning%3A0.8&keywords=name%3A0.8&keywords=partner%3A0.8&keywords=permanent%3A0.8&keywords=representative%3A1.0&keywords=resident%3A0.8&keywords=transfer%3A0.8&keywords=yeah%3A0.8&keywords=high%3A0.8&keywords=school%3A0.8"
    headers = {
        "Authorization": "Token <YOUR_API_KEY_HERE>",
        "Content-Type": "audio/*"
    }
    with open(PATH_TO_FILE, "rb") as audio_file:
        try:
            response = requests.post(URL, headers=headers, data=audio_file)
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
    return response

def build_master_transcript(deepgram_json):
    converted = deepgram_json.json()
    channel_zero_words = converted['results']['channels'][0]["alternatives"][0]["words"]
    channel_one_words = converted['results']['channels'][1]["alternatives"][0]["words"]
    all_words = channel_zero_words + channel_one_words
    for w in all_words:
        w["start"] = round(w["start"], 1)
        w["end"] = round(w["end"], 1)

    # Sort by start time
    all_words.sort(key=lambda w: w["start"])
    return all_words

def find_missing_vad_segments(vad_segments, master_words, coverage_threshold=0.6, min_vad_duration=2.0):
    """
    Identify VAD segments that are likely missing transcript coverage.

    Parameters:
        vad_segments (list of dict): Each dict has "start" and "end" of VAD speech.
        master_words (list of dict): Each dict has "start" and "end" of a word.
        coverage_threshold (float): Minimum ratio of covered duration to VAD duration to consider it "covered".

    Returns:
        list of dict: Each dict contains the VAD segment and coverage info if it's under-covered.
    """
    missing_segments = []

    for vad in vad_segments:
        vs, ve = vad["start"], vad["end"]
        vad_duration = ve - vs
        if vad_duration < min_vad_duration:
            continue  # skip invalid VAD segments

        # Sum durations of words that overlap this VAD segment
        covered_duration = 0.0
        for word in master_words:
            # Overlap check
            word_start, word_end = word["start"], word["end"]
            overlap_start = max(vs, word_start)
            overlap_end = min(ve, word_end)
            if overlap_end > overlap_start:
                covered_duration += overlap_end - overlap_start

        coverage_ratio = covered_duration / vad_duration

        if coverage_ratio < coverage_threshold:
            missing_segments.append({
                "vad_start": vs,
                "vad_end": ve,
                "vad_duration": vad_duration,
                "covered_duration": covered_duration,
                "coverage_ratio": coverage_ratio
            })

    return missing_segments

def main(PATH_TO_FILE, COVERAGE_THRESHOLD, MIN_VAD_DURATION, SIGNIFICANCE_FACTOR):
    silero_timestamps = silero_vad(PATH_TO_FILE)
    transcript = deepgram_words(PATH_TO_FILE)
    all_words = build_master_transcript(transcript)
    missing_segments = find_missing_vad_segments(silero_timestamps, all_words, COVERAGE_THRESHOLD, MIN_VAD_DURATION)
    result = False
    filtered_segments = []


    # Iterate through the list of missing segments and remove any that are less than our SIGNIFICANCE_FACTOR
    if len(missing_segments) > 0:
        for segment in missing_segments:
            if segment['vad_end'] - segment['vad_start'] > SIGNIFICANCE_FACTOR:
                result = True
                filtered_segments.append(segment)
    
    missing_segments = filtered_segments

    if result:
        for segment in missing_segments:
            print(f"In your file {PATH_TO_FILE}, a missing transcript was detected between {segment['vad_start']} seconds - {segment['vad_end']} seconds.")
    else:
        print(f"There were no missing transcripts detected in your file {PATH_TO_FILE}")
    return result

main(PATH_TO_FILE, COVERAGE_THRESHOLD, MIN_VAD_DURATION, SIGNIFICANCE_FACTOR)
