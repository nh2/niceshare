#!/usr/bin/env python3

import argparse
import itertools
import shlex
import subprocess
import re
import socket
import sys
import wx


def list_screen_sizes():
  app = wx.App(False)
  num_displays = wx.Display.GetCount()
  geometries = [wx.Display(i).GetGeometry() for i in range(num_displays)]
  single_screen_strings = [f'{g.Width}x{g.Height}+{g.X},{g.Y}' for g in geometries]
  return single_screen_strings


def get_all_screens_size():
  app = wx.App(False)
  all_screens_mode = wx.Display(0).GetCurrentMode()
  all_w = all_screens_mode.Width
  all_h = all_screens_mode.Height
  return f'{all_w}x{all_h},0+0'


def concat_lists(list_of_lists):
  return list(itertools.chain.from_iterable(list_of_lists))


screenshare_argument_regex = r'(\d+)x(\d+)\+(\d+),(\d+)'

# Returns (w, h, x, y) on success, None on failure.
def parse_screenshare_argument(screenshare_arg):
  m = re.match(screenshare_argument_regex, screenshare_arg)
  if not m:
    return None
  return (
    int(m.group(1)),
    int(m.group(2)),
    int(m.group(3)),
    int(m.group(4)),
  )


def main(use_gooey=False):
  desc = 'GUI for gstreamer-based screen sharing.'

  if use_gooey:
    import gooey
    parser = gooey.GooeyParser(description=desc)
  else:
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
      '--ignore-gooey', action='store_true',
      help='Ingored; just for compatibility with Gooey when plain argparse is used.',
    )

  connection_group = parser.add_mutually_exclusive_group(required=True)
  connection_group.add_argument(
    '--listen-port', type=str,  # we accept str to support gstreamer SRT URL params
    help='Port number. You likely need to open this in your firewall/NAT. Example: 5000',
  )
  connection_group.add_argument(
    '--call', type=str,  # we accept str to support gstreamer SRT URL params
    help='Connect to host:port. Example: localhost:5000',
  )

  mode_group = parser.add_mutually_exclusive_group(required=True)
  mode_group.add_argument(
    '--view', action='store_true',
    help='Receive video from the other side.',
  )
  for i, screen_size in enumerate(list_screen_sizes()):
    mode_group.add_argument(
      f'--screenshare-screen-{i}', metavar=f'Screenshare screen {i}',
      dest='screenshare', action='store_const', const=screen_size,
      help=screen_size,
    )
  all_screens_size = get_all_screens_size()
  mode_group.add_argument(
    f'--screenshare-all', metavar='Screenshare all screens',
    dest='screenshare', action='store_const', const=all_screens_size,
    help=all_screens_size,
  )

  mode_group.add_argument(
    '--screenshare-rectangle', metavar="Screenshare custom rectangle",
    dest='screenshare_rectangle',
    help='Format: WxH+OFFSET_X,OFFSET_Y. Example: 1920x1080+0,0',
    **({} if not use_gooey else {
      'gooey_options': {
        'validator': {
          'test': f"__import__('re').match(r'{screenshare_argument_regex}', user_input)",  # gets eval()d
          'message': 'Must be of format WIDTHxHEIGHT+OFFSET_X,OFFSET_Y',
        },
      },
    }),
  )

  parser.add_argument(
    '--bitrate', type=int, default=2048,
    help='Bitrate in KBit/s',
  )

  parser.add_argument(
    # TODO: Enable by default when this crash is fixed: https://github.com/Haivision/srt/issues/1594
    '--fec', action='store_true', default=False,
    help='Forward Error Correction costs more bandwidth but helps with packet loss. Both sides must use the same value.',
  )

  parser.add_argument(
    '--latency', type=int, default=1000,
    help='Acceptable latency in milliseconds. The video transmission will have that much delay. Too small values will result in corruption artifacts. Should be 4x the ping time to the destination.',
  )

  parser.add_argument(
    '--fps', type=int, default=30,
    help='Frames per second.',
  )

  parser.add_argument(
    '--passphrase', type=str,
    help='Encrypt traffic with this passphrase',
    **({} if not use_gooey else {
      'widget': 'PasswordField',
    })
  )

  parser.add_argument(
    '--print-command', action='store_true', default=False,
    help='Only print the command, do not run it.',
  )

  args = parser.parse_args()

  # print(args)

  if args.listen_port:
    uri = 'srt://:' + args.listen_port
  elif args.call:
    hostname, port = args.call.split(':')
    ip = socket.gethostbyname(hostname)
    uri = f'srt://{ip}:{port}'

  # Cannot use `dest='screenshare` for that flag because then Gooey renders
  # the validation error into the wrong place; thus translate it manually.
  if args.screenshare_rectangle:
    args.screenshare = args.screenshare_rectangle

  if args.screenshare is not None:
    width, height, startx, starty = parse_screenshare_argument(args.screenshare)
    endx = startx + width - 1
    endy = starty + height - 1
    gst_launch_args = [
      'gst-launch-1.0',
      f'ximagesrc startx={startx} endx={endx} starty={starty} endy={endy} show-pointer=true use-damage=0',
      '! queue',
      '! videoconvert',
      '! clockoverlay',
      f'! x264enc tune=zerolatency speed-preset=fast bitrate={args.bitrate} threads=1 byte-stream=true key-int-max=60 intra-refresh=true',
      f'! video/x-h264, profile=baseline, framerate={args.fps}/1',
      '! mpegtsmux',
      '! queue',
      f'! srtsink uri={uri} latency={args.latency} ' + ' '.join(concat_lists([
        ['packetfilter=fec,cols:3,rows:-3,layout:staircase,arq:always'] if args.fec else [],
        [f'passphrase={args.passphrase}'] if args.passphrase else [],
      ])),
    ]
  elif args.view is not None:
    gst_launch_args = [
      'gst-launch-1.0',
      f'srtsrc uri={uri} ' + ' '.join(concat_lists([
        ['packetfilter=fec'] if args.fec else [],
        [f'passphrase={args.passphrase}'] if args.passphrase else [],
      ])),
      '! queue',
      '! tsdemux',
      '! h264parse',
      '! video/x-h264',
      '! avdec_h264',
      '! autovideosink sync=false',
    ]

  quoted_in_nix_shell_command = shlex.quote(' '.join(gst_launch_args))
  command = ' '.join([
    'NIX_PATH=nixpkgs=https://github.com/nh2/nixpkgs/archive/6dc03726f61868c0b8020e9ca98ac71972528d8f.tar.gz',
    'nix-shell',
    '-p gst_all_1.gstreamer',
    '-p gst_all_1.gst-plugins-good',
    '-p gst_all_1.gst-plugins-base',
    '-p gst_all_1.gst-plugins-bad',
    '-p gst_all_1.gst-plugins-ugly',
    '-p gst_all_1.gst-libav',
    f'--run {quoted_in_nix_shell_command}',
  ])

  cli_flags = ' '.join(a for a in sys.argv if a not in ['--ignore-gooey', '--print-command'])
  print(f'\nYour CLI flags:\n\n{cli_flags}\n')
  print(f'\nYour gstreamer invocation:\n\n{command}\n')

  if not args.print_command:
    subprocess.run(command, shell=True)


def gooey_main():
  import gooey
  gooey.Gooey(
    program_name="NiceShare GUI",
  )(main)(use_gooey=True)


if __name__ == "__main__":
  if '--gui' in sys.argv:
    gooey_main()
  else:
    main()
