#!/usr/bin/python

import vlc
import srt
import argparse
import time
from capsender import CaptionSender 

def MovieFinished(event, player):
    print("\nEvent reports - finished")
    player.stop()

def SyncTimeStamp(event, player, caption_sender):
    #sync the start time with the media player time
    start_time = time.time() - (player.get_time()/1000)
    caption_sender.set_start_time(start_time)

def StartFirstTimer(event, movie_start, sig_start, caption_sender):
    start_time = time.time() - movie_start

    caption_sender.set_start_time(start_time)
    
    caption_sender.start_first_timer()

    caption_sender.start_sig_timer(sig_start)

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-s","--subfile", default='Subtitle.srt', help="subtitle filename (default: Subtitle.srt)")
    parser.add_argument("-m","--moviefile", default='Movie', help="movie filename (default: Movie)")
    parser.add_argument("-c","--comport", default='/dev/ttyACM0', help="comport for arduino (default: /dev/ttyACM0)")
    parser.add_argument("-t","--starttime", default=0, type=float, help="time in seconds that the movie will start playing")
    parser.add_argument("-a","--aspectratio", default='', help="force to specified aspect ratio (expressed in X:Y format)")
    parser.add_argument("-g","--signaturetime", default=0, type=float, help="time in seconds to display the signature block (default: signature will never be displayed)")
    return parser.parse_args()

if __name__ == "__main__": 
    #args = get_args(sys.argv[1:])
    args = parse_args()

    #open SRT file
    srtfile = open(args.subfile, "r", encoding="utf-8-sig")

    # create subtitle generator
    subtitle_generator = srt.parse(srtfile)
    

    caption_sender = CaptionSender(subtitle_generator, args.comport)


    # creating vlc media player object
    instance = vlc.Instance()
    media_player = instance.media_player_new()

    #set aspect ratio
    if(args.aspectratio):
        media_player.video_set_aspect_ratio(args.aspectratio)

    # media object
    media = instance.media_new_path(args.moviefile)

    #start movie at a certain timestamp
    movie_start = args.starttime
    media.add_option(f'start-time={movie_start}')

    caption_sender.fast_forward(movie_start)

    #disable VLC player subtitles
    media.add_option("no-sub-autodetect-file")

    # setting media to the media player
    media_player.set_media(media)

    events = media_player.event_manager()
    events.event_attach(vlc.EventType.MediaPlayerEndReached, MovieFinished, media_player)
    events.event_attach(vlc.EventType.MediaPlayerTimeChanged, SyncTimeStamp, media_player, caption_sender)
    events.event_attach(vlc.EventType.MediaPlayerPlaying, StartFirstTimer, movie_start, args.signaturetime, caption_sender)
    #events.event_attach(vlc.EventType.MediaPlayerForward, FastForward, media_player, subtitle_generator)

    # start playing video
    media_player.play()

    input("Press Enter to stop...")

    media_player.stop()
    caption_sender.stop_timers()
    srtfile.close()
