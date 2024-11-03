import os
import json
import whisper
import subprocess
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from pytubefix import YouTube
from pytubefix.exceptions import (
    MembersOnly, 
    VideoPrivate, 
    VideoRegionBlocked, 
    AgeRestrictedError, 
    LiveStreamError,
    VideoUnavailable  # Add this
)
import sys
import time
from urllib.error import HTTPError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Replace hardcoded paths with environment variables
VIDEO_OUTPUT_PATH = os.getenv('VIDEO_OUTPUT_PATH')
TRANSCRIPTION_OUTPUT_PATH = os.getenv('TRANSCRIPTION_OUTPUT_PATH')

# Set up OAuth2 credentials
CLIENT_SECRETS_FILE = "client_secrets.json"  # Path to the downloaded JSON file
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]

def get_authenticated_service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'client_secrets.json',
                SCOPES
            )
            # Configure the authorization flow separately
            flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='select_account'
            )
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)

# Load transcribed videos record with playlist information
transcribed_videos_file = 'transcribed_videos.json'
def load_transcribed_videos():
    if os.path.exists(transcribed_videos_file):
        with open(transcribed_videos_file, 'r') as file:
            data = json.load(file)
            # Convert old format to new if necessary
            if isinstance(data, list):
                return {'default': data}
            return data
    return {}

def video_exists_in_any_playlist(video_id, transcribed_data):
    """Check if video exists in any playlist."""
    for playlist_data in transcribed_data.values():
        if video_id in playlist_data.get('videos', []):
            return True
    return False

def save_transcribed_video(video_id, playlist_id, playlist_title):
    transcribed_data = load_transcribed_videos()
    
    # Create playlist entry if it doesn't exist
    if playlist_id not in transcribed_data:
        transcribed_data[playlist_id] = {
            'title': playlist_title,
            'videos': []
        }
    
    # Add video if not already in this playlist
    if video_id not in transcribed_data[playlist_id]['videos']:
        transcribed_data[playlist_id]['videos'].append(video_id)
        
    # Save updated data
    with open(transcribed_videos_file, 'w') as file:
        json.dump(transcribed_data, file, indent=2)

def fetch_playlist_videos(youtube, playlist_id):
    videos = []
    next_page_token = None
    
    while True:
        request = youtube.playlistItems().list(
            part='snippet',
            playlistId=playlist_id,
            maxResults=50,
            pageToken=next_page_token
        )
        response = request.execute()
        videos.extend(response['items'])
        
        # Print debugging info
        for item in response['items']:
            print(f"Found video: {item['snippet']['title']} (ID: {item['snippet']['resourceId']['videoId']})")
        
        next_page_token = response.get('nextPageToken')
        if not next_page_token:
            break
    
    print(f"\nTotal videos found in playlist: {len(videos)}")
    return videos

def clean_filename(text):
    """Clean text for use in filenames"""
    return "".join(c for c in text if c.isalnum() or c in (' ', '-', '_')).rstrip()

def download_video_and_audio(video_id, video_title, playlist_title, output_path):
    url = f'https://www.youtube.com/watch?v={video_id}'
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            time.sleep(1)
            # Remove use_po_token, only use OAuth
            yt = YouTube(url, use_oauth=True, allow_oauth_cache=True)
            
            # Clean the video and playlist titles for use in filename
            clean_video_title = clean_filename(video_title)
            clean_playlist = clean_filename(playlist_title)
            filename = f'{clean_playlist} - {video_id} - {clean_video_title}'
            
            # First try adaptive stream for highest quality video
            stream = (yt.streams
                     .filter(adaptive=True, file_extension='mp4', type='video')
                     .order_by('resolution')
                     .desc()
                     .first())
            
            # Also get the audio stream
            audio_stream = (yt.streams
                          .filter(only_audio=True, file_extension='mp4')
                          .first())
            
            if stream and audio_stream:
                print(f"Selected video resolution: {stream.resolution}")
                # Download video
                temp_video_path = os.path.join(output_path, f'temp_video_{filename}.mp4')
                stream.download(output_path=output_path, filename=f'temp_video_{filename}.mp4')
                
                # Download audio
                temp_audio_path = os.path.join(output_path, f'temp_audio_{filename}.mp4')
                audio_stream.download(output_path=output_path, filename=f'temp_audio_{filename}.mp4')
                
                # Merge video and audio using ffmpeg
                final_file_path = os.path.join(output_path, f'{filename}.mp4')
                merge_command = [
                    'ffmpeg',
                    '-i', temp_video_path,
                    '-i', temp_audio_path,
                    '-c:v', 'copy',
                    '-c:a', 'aac',
                    '-y',
                    final_file_path
                ]
                
                subprocess.run(merge_command, check=True, capture_output=True)
                
                # Clean up temporary files
                if os.path.exists(temp_video_path):
                    os.remove(temp_video_path)
                if os.path.exists(temp_audio_path):
                    os.remove(temp_audio_path)
                
                print(f"Video downloaded and merged to: {final_file_path}")
                return final_file_path
            else:
                print("No suitable video/audio streams found, falling back to progressive stream")
                # Fallback to progressive stream if adaptive fails
                stream = (yt.streams
                         .filter(progressive=True, file_extension='mp4')
                         .order_by('resolution')
                         .desc()
                         .first())
                
                if stream:
                    print(f"Selected fallback resolution: {stream.resolution}")
                    final_file_path = os.path.join(output_path, f'{filename}.mp4')
                    stream.download(output_path=output_path, filename=f'{filename}.mp4')
                    print(f"Video downloaded to: {final_file_path}")
                    return final_file_path
                
        except (MembersOnly, VideoPrivate, VideoRegionBlocked, AgeRestrictedError, 
                LiveStreamError, HTTPError, VideoUnavailable) as e:  # Add VideoUnavailable
            print(f"Error downloading video {video_id}: {str(e)}")
            if isinstance(e, (MembersOnly, VideoUnavailable)):  # Special handling for members-only videos
                print(f"Skipping members-only or unavailable video: {video_title}")
                # Add to transcribed videos to avoid retrying
                save_transcribed_video(video_id, PLAYLIST_ID, "Unknown Playlist")
                return None
            
            retry_count += 1
            if retry_count < max_retries:
                print(f"Retrying... (Attempt {retry_count + 1} of {max_retries})")
                time.sleep(2)
                continue
            
    print(f"Failed to download video '{video_id}' after {max_retries} attempts. Skipping...")
    return None

def extract_audio(video_path, audio_path):
    # Normalize paths
    video_path = os.path.normpath(video_path)
    audio_path = os.path.normpath(audio_path)
    
    command = [
        "ffmpeg",
        "-i", video_path,
        "-vn",  # No video
        "-acodec", "pcm_s16le",  # Audio codec
        "-ar", "16000",  # Sample rate
        "-ac", "1",  # Mono
        "-f", "wav",  # Force WAV format
        "-y",  # Overwrite output file
        audio_path
    ]
    
    try:
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(audio_path), exist_ok=True)
        
        # Run ffmpeg command
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True
        )
        
        if os.path.exists(audio_path):
            print(f"Audio extracted successfully to: {audio_path}")
            return True
        else:
            print(f"Audio file not created at: {audio_path}")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"Error extracting audio: {e.stderr}")
        # Print the command that failed
        print(f"Failed command: {' '.join(command)}")
        return False

def transcribe_audio(audio_path):
    model = whisper.load_model("base")
    result = model.transcribe(audio_path)
    return result["text"]

def fetch_user_playlists(youtube):
    """Fetch all playlists owned by the authenticated user."""
    try:
        # First get the user's channel ID
        channel_request = youtube.channels().list(
            part="id",
            mine=True
        ).execute()
        
        if not channel_request['items']:
            print("No channel found for this user.")
            return []
            
        channel_id = channel_request['items'][0]['id']
        
        # Then get all playlists for this channel
        playlists = []
        next_page_token = None
        
        while True:
            request = youtube.playlists().list(
                part="snippet",
                channelId=channel_id,
                maxResults=50,
                pageToken=next_page_token
            )
            response = request.execute()
            
            playlists.extend(response['items'])
            next_page_token = response.get('nextPageToken')
            
            if not next_page_token:
                break
                
        return playlists
        
    except Exception as e:
        print(f"Error fetching playlists: {str(e)}")
        return []

def select_playlist(playlists):
    """Display playlists and let user select one."""
    if not playlists:
        print("No playlists found.")
        sys.exit(1)
        
    print("\nAvailable playlists:")
    for i, playlist in enumerate(playlists, 1):
        print(f"{i}. {playlist['snippet']['title']}")
        
    while True:
        try:
            choice = int(input("\nEnter the number of the playlist you want to process: "))
            if 1 <= choice <= len(playlists):
                return playlists[choice - 1]['id']
            print("Invalid selection. Please try again.")
        except ValueError:
            print("Please enter a valid number.")

def get_current_channel(youtube):
    request = youtube.channels().list(
        part="snippet",
        mine=True
    )
    response = request.execute()
    return response['items'][0]['snippet']['title']

def is_video_transcribed(video_id, playlist_title, output_path):
    # Check specifically in this playlist's directory
    playlist_path = os.path.join(output_path, sanitize_filename(playlist_title))
    transcript_file = os.path.join(playlist_path, f"{video_id}.txt")
    
    # Only return True if the file exists AND has content
    if os.path.exists(transcript_file):
        try:
            with open(transcript_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                return bool(content)  # Returns False if file is empty
        except Exception:
            return False
    return False

def process_video(video_id, video_title, playlist_title, output_path):
    print(f"\nProcessing new video: '{video_title}' (ID: {video_id})")
    
    # Check if this specific video is already transcribed in this specific playlist
    if is_video_transcribed(video_id, playlist_title, output_path):
        print(f"Video '{video_title}' already transcribed in playlist '{playlist_title}'")
        return True
    
    # If we find it in another playlist, we should still process it for this playlist
    # Remove or modify this cross-playlist check if you want to process each video fresh for each playlist
    
    # Rest of the function remains the same...

def main():
    print("Authenticating and initializing YouTube API client...")
    youtube = get_authenticated_service()
    
    # Print the current channel and ask if user wants to switch
    current_channel = get_current_channel(youtube)
    print(f"\nCurrently authenticated as: {current_channel}")
    
    while True:
        choice = input("\nDo you want to continue with this channel? (y/n): ").lower()
        if choice == 'y':
            break
        elif choice == 'n':
            # Remove the token file to force re-authentication
            if os.path.exists("token.json"):
                os.remove("token.json")
            print("\nPlease re-authenticate with your desired account...")
            youtube = get_authenticated_service()
            current_channel = get_current_channel(youtube)
            print(f"\nNow authenticated as: {current_channel}")
            break
        else:
            print("Please enter 'y' or 'n'")
    
    print("\nFetching available playlists...")
    playlists = fetch_user_playlists(youtube)
    playlist_id = select_playlist(playlists)
    
    # Get playlist title
    selected_playlist = next((p for p in playlists if p['id'] == playlist_id), None)
    playlist_title = selected_playlist['snippet']['title'] if selected_playlist else 'Unknown Playlist'
    
    print(f"\nFetching videos from playlist: {playlist_title}")
    videos = fetch_playlist_videos(youtube, playlist_id)
    
    # Load transcribed videos with playlist information
    transcribed_data = load_transcribed_videos()
    playlist_videos = transcribed_data.get(playlist_id, {}).get('videos', [])
    
    print(f"\nCurrently transcribed videos in this playlist: {len(playlist_videos)}")
    print("First few transcribed video IDs:", playlist_videos[:5] if playlist_videos else "None")
    
    for video in videos:
        video_id = video['snippet']['resourceId']['videoId']
        video_title = video['snippet']['title']
        
        # Check if video exists in any playlist
        if video_exists_in_any_playlist(video_id, transcribed_data):
            print(f"Video '{video_title}' already transcribed in another playlist. Adding to current playlist...")
            save_transcribed_video(video_id, playlist_id, playlist_title)
            continue
        
        if video_id in playlist_videos:
            print(f"Video '{video_title}' already in current playlist. Skipping...")
            continue
        
        print(f"\nProcessing new video: '{video_title}' (ID: {video_id})")
        print(f"Downloading video '{video_title}'...")
        video_path = download_video_and_audio(video_id, video_title, playlist_title, VIDEO_OUTPUT_PATH)
        
        if not video_path:
            print(f"Failed to download video '{video_title}'. Skipping...")
            continue
        
        # Use the same filename pattern for the audio and transcription
        base_filename = os.path.splitext(os.path.basename(video_path))[0]
        audio_path = os.path.join(VIDEO_OUTPUT_PATH, f'{base_filename}.wav')
        
        print("Extracting audio from video...")
        if not extract_audio(video_path, audio_path):
            print(f"Failed to extract audio from video '{video_title}'. Skipping...")
            continue
            
        if not os.path.exists(audio_path):
            print(f"Audio file not found at: {audio_path}. Skipping...")
            continue
            
        print("Transcribing audio...")
        transcription = transcribe_audio(audio_path)
        
        # Save transcription with playlist info in filename
        transcription_file_path = os.path.join(TRANSCRIPTION_OUTPUT_PATH, f'{base_filename}.txt')
        with open(transcription_file_path, 'w', encoding='utf-8') as file:
            file.write(transcription)
        
        # Update transcribed videos record with playlist info
        save_transcribed_video(video_id, playlist_id, playlist_title)
        
        # Clean up
        os.remove(audio_path)
        
        # After successful transcription, add to newly processed list
        save_transcribed_video(video_id, PLAYLIST_ID, "Unknown Playlist")

if __name__ == "__main__":
    os.makedirs(VIDEO_OUTPUT_PATH, exist_ok=True)
    os.makedirs(TRANSCRIPTION_OUTPUT_PATH, exist_ok=True)
    main()

