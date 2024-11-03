# YouTube Playlist Transcriber

This script `youtube_playlist_transcriber.py` downloads all videos (other than those already downloaded) at maximum resolution from a selected YouTube playlist, extracts the audio, transcribes it using OpenAI's Whisper, and saves the transcriptions as text files. Ideal for bulk processing YouTube videos to create text-based transcripts (in this case to use as unstructured knowledge data).

## Features
- **Authenticate with YouTube API** to access playlists and video details.
- **Download videos and audio** from a specified YouTube playlist.
- **Merge audio and video** streams for optimal quality.
- **Extract and transcribe audio** using OpenAI’s Whisper model.
- **Save transcriptions** with playlist and video details for organized storage.

## Requirements
1. **Python 3.7+**
2. **Google API Client Library** for Python
3. **ffmpeg** (for merging video and audio files)

## Installation

1. Clone the repository or download the script.
2. Install required packages:
    ```bash
    pip install -r requirements.txt
    ```

3. Download and set up `ffmpeg`:
   - Ensure `ffmpeg` is installed and accessible in your PATH.

## Setup Guide

1. **Create API Credentials**:
    - Set up a project on Google Cloud and enable the YouTube Data API.
    - Download the `client_secrets.json` file and place it in the project directory.

2. **Environment Variables**:
   - Create a `.env` file in the root directory with the following content:
     ```
     CLIENT_SECRETS_FILE=client_secrets.json
     SCOPES=https://www.googleapis.com/auth/youtube.readonly
     PLAYLIST_ID=YOUR_PLAYLIST_ID
     VIDEO_OUTPUT_PATH=Path/where/videos/will/be/saved
     TRANSCRIPTION_OUTPUT_PATH=Path/where/transcriptions/will/be/saved
     ```
   - Replace `YOUR_PLAYLIST_ID` with the ID of the YouTube playlist you want to transcribe.

3. **Run the Script**:
   - Authenticate the script with your Google account. The first time you run the script, it will prompt for Google account authorization and create a `token.json` file to store credentials.
   ```bash
   python youtube_playlist_transcriber.py
   ```

## Usage Notes

- The script prompts you to choose from playlists associated with your YouTube account.
- It will skip previously transcribed videos and save new ones automatically.
- Audio extraction and transcription may take time, depending on video length.

### Transcription Output
Transcriptions are saved in the specified output directory as `.txt` files, each named with the video title and ID for easy reference.

## Troubleshooting
- **Video Unavailable Errors**: The script handles errors such as videos being private, region-blocked, or members-only.
- **API Limits**: Ensure you stay within the YouTube API quota limits; otherwise, the script may stop with errors.

## Contributing
Contributions are welcome! Feel free to submit a pull request or open an issue for suggestions or bug reports.

## License
This project is licensed under the GNU General Public License (GPL).
